"""
Poll and Ack endpoints for EA devices (PR-024a).

Endpoints:
- GET /api/v1/client/poll: Retrieve approved signals for this device's client
- POST /api/v1/client/ack: Acknowledge execution attempt

All endpoints require HMAC device authentication headers.
"""

import logging
import time
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.approvals.models import Approval, ApprovalDecision
from backend.app.core.db import get_db
from backend.app.ea.auth import DeviceAuthDependency, get_device_auth
from backend.app.ea.models import Execution, ExecutionStatus
from backend.app.ea.schemas import (
    AckRequest,
    AckResponse,
    ApprovedSignalOut,
    ExecutionParamsOut,
    PollResponse,
)
from backend.app.observability.metrics import metrics

router = APIRouter(prefix="/api/v1/client", tags=["client"])
logger = logging.getLogger(__name__)


@router.get("/poll", response_model=PollResponse)
async def poll_approved_signals(
    db: AsyncSession = Depends(get_db),
    device_auth: DeviceAuthDependency = Depends(get_device_auth),
    since: datetime | None = Query(
        None, description="Only return signals approved after this time"
    ),
    x_device_id: str = Header(..., alias="X-Device-Id"),
    x_nonce: str = Header(..., alias="X-Nonce"),
    x_timestamp: str = Header(..., alias="X-Timestamp"),
    x_signature: str = Header(..., alias="X-Signature"),
) -> PollResponse:
    """
    Poll for approved signals ready for execution.

    Returns only signals that:
    1. Are approved (decision=approved)
    2. Belong to this device's client
    3. Have NOT been acknowledged yet
    4. Are newer than 'since' timestamp (if provided)

    Headers (required):
    - X-Device-Id: Device UUID
    - X-Nonce: Unique request nonce
    - X-Timestamp: RFC3339 timestamp
    - X-Signature: Base64 HMAC-SHA256 signature

    Args:
        db: Database session
        device_auth: Device authentication (from dependency)
        since: Optional timestamp filter (ISO format)

    Returns:
        PollResponse with list of approved signals

    Example:
        GET /api/v1/client/poll
        X-Device-Id: dev_123
        X-Nonce: nonce_abc
        X-Timestamp: 2025-10-26T10:30:45Z
        X-Signature: base64_signature
    """
    start_time = time.time()
    metrics.record_ea_request("/poll")

    try:
        logger.info(
            "Poll request",
            extra={
                "device_id": device_auth.device_id,
                "client_id": device_auth.client_id,
                "since": since,
            },
        )

        # Query approvals for this client that are approved and not yet acknowledged
        stmt = select(Approval).where(
            and_(
                Approval.client_id == device_auth.client_id,
                Approval.decision == ApprovalDecision.APPROVED,
            )
        )

        if since:
            stmt = stmt.where(Approval.created_at >= since)

        result = await db.execute(stmt)
        approvals = result.scalars().all()

        # Filter out approvals that have already been executed on this device
        approved_signals = []
        for approval in approvals:
            # Check if this approval has been executed on this device already
            exec_stmt = select(Execution).where(
                and_(
                    Execution.approval_id == approval.id,
                    Execution.device_id == device_auth.device_id,
                )
            )
            exec_result = await db.execute(exec_stmt)
            if exec_result.scalar_one_or_none():
                continue  # Already executed on this device

            # Load signal for details
            signal = approval.signal
            if not signal:
                continue

            # Build execution params from signal payload
            payload = signal.payload or {}
            try:
                exec_params = ExecutionParamsOut(
                    entry_price=float(
                        payload.get("entry_price", signal.entry_price or 0)
                    ),
                    stop_loss=float(payload.get("stop_loss", signal.stop_loss or 0)),
                    take_profit=float(
                        payload.get("take_profit", signal.take_profit or 0)
                    ),
                    volume=float(payload.get("volume", 0.1)),
                    ttl_minutes=int(payload.get("ttl_minutes", 240)),
                )
            except (ValueError, TypeError) as e:
                logger.warning(
                    "Failed to build execution params",
                    extra={"signal_id": signal.id, "error": str(e)},
                )
                continue

            approved_signals.append(
                ApprovedSignalOut(
                    approval_id=approval.id,
                    instrument=signal.instrument,
                    side="buy" if signal.side == 0 else "sell",
                    execution_params=exec_params,
                    approved_at=approval.created_at,
                    created_at=signal.created_at,
                )
            )

        logger.info(
            "Poll response",
            extra={
                "device_id": device_auth.device_id,
                "signals_count": len(approved_signals),
            },
        )

        # Record duration
        duration = time.time() - start_time
        metrics.record_ea_poll_duration(duration)

        return PollResponse(
            approvals=approved_signals,
            count=len(approved_signals),
            polled_at=datetime.utcnow(),
            next_poll_seconds=10,
        )

    except Exception as e:
        logger.error(
            f"Poll request failed: {e}", extra={"error": str(e)}, exc_info=True
        )
        metrics.record_ea_error("/poll", "internal_error")
        raise


@router.post("/ack", response_model=AckResponse, status_code=201)
async def acknowledge_execution(
    request: AckRequest,
    db: AsyncSession = Depends(get_db),
    device_auth: DeviceAuthDependency = Depends(get_device_auth),
    x_device_id: str = Header(..., alias="X-Device-Id"),
    x_nonce: str = Header(..., alias="X-Nonce"),
    x_timestamp: str = Header(..., alias="X-Timestamp"),
    x_signature: str = Header(..., alias="X-Signature"),
) -> AckResponse:
    """
    Acknowledge execution attempt.

    Device submits execution result (placed or failed). Creates Execution record
    linking approval to device and broker outcome.

    Headers (required):
    - X-Device-Id: Device UUID
    - X-Nonce: Unique request nonce
    - X-Timestamp: RFC3339 timestamp
    - X-Signature: Base64 HMAC-SHA256 signature

    Args:
        request: AckRequest with status and details
        db: Database session
        device_auth: Device authentication
        x_device_id: Device ID (from header)
        x_nonce: Nonce (from header)
        x_timestamp: Timestamp (from header)
        x_signature: Signature (from header)

    Returns:
        AckResponse with execution ID and confirmation

    Raises:
        HTTPException: 404 if approval not found or not owned by this client
        HTTPException: 409 if execution already exists for this approval+device

    Example:
        POST /api/v1/client/ack
        X-Device-Id: dev_123
        X-Nonce: nonce_def
        X-Timestamp: 2025-10-26T10:31:15Z
        X-Signature: base64_signature

        {
            "approval_id": "550e8400-e29b-41d4-a716-446655440000",
            "status": "placed",
            "broker_ticket": "123456789",
            "error": null
        }
    """
    start_time = time.time()
    metrics.record_ea_request("/ack")

    try:
        logger.info(
            "Ack request",
            extra={
                "device_id": device_auth.device_id,
                "approval_id": request.approval_id,
                "status": request.status,
            },
        )

        # Load approval and verify it belongs to this client
        approval_stmt = select(Approval).where(Approval.id == request.approval_id)
        approval_result = await db.execute(approval_stmt)
        approval = approval_result.scalar_one_or_none()

        if not approval:
            logger.warning(
                "Approval not found", extra={"approval_id": request.approval_id}
            )
            metrics.record_ea_error("/ack", "approval_not_found")
            raise HTTPException(status_code=404, detail="Approval not found")

        if approval.client_id != device_auth.client_id:
            logger.warning(
                "Approval does not belong to this client",
                extra={
                    "approval_id": request.approval_id,
                    "client_id": device_auth.client_id,
                    "approval_client_id": approval.client_id,
                },
            )
            metrics.record_ea_error("/ack", "forbidden")
            raise HTTPException(
                status_code=403, detail="Approval does not belong to this client"
            )

        # Check for duplicate execution
        dup_stmt = select(Execution).where(
            and_(
                Execution.approval_id == request.approval_id,
                Execution.device_id == device_auth.device_id,
            )
        )
        dup_result = await db.execute(dup_stmt)
        if dup_result.scalar_one_or_none():
            logger.warning(
                "Execution already exists",
                extra={
                    "approval_id": request.approval_id,
                    "device_id": device_auth.device_id,
                },
            )
            metrics.record_ea_error("/ack", "duplicate_execution")
            raise HTTPException(
                status_code=409,
                detail="Execution already exists for this approval+device",
            )

        # Create execution record
        execution = Execution(
            approval_id=request.approval_id,
            device_id=device_auth.device_id,
            status=(
                ExecutionStatus.PLACED
                if request.status == "placed"
                else ExecutionStatus.FAILED
            ),
            broker_ticket=request.broker_ticket,
            error=request.error,
        )

        db.add(execution)
        await db.commit()
        await db.refresh(execution)

        logger.info(
            "Execution recorded",
            extra={
                "execution_id": execution.id,
                "approval_id": request.approval_id,
                "device_id": device_auth.device_id,
                "status": request.status,
            },
        )

        # Record duration
        duration = time.time() - start_time
        metrics.record_ea_ack_duration(duration)

        return AckResponse(
            execution_id=execution.id,
            approval_id=execution.approval_id,
            status=request.status,
            recorded_at=execution.created_at,
        )

    except HTTPException:
        # Re-raise HTTP exceptions (don't double-record as they're already recorded above)
        raise
    except Exception as e:
        logger.error(f"Ack request failed: {e}", extra={"error": str(e)}, exc_info=True)
        metrics.record_ea_error("/ack", "internal_error")
        raise HTTPException(status_code=500, detail="Internal server error")
