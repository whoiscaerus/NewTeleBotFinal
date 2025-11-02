"""
Poll and Ack endpoints for EA devices (PR-024a + PR-104).

Endpoints:
- GET /api/v1/client/poll: Retrieve approved signals for this device's client
- POST /api/v1/client/ack: Acknowledge execution attempt

All endpoints require HMAC device authentication headers.

SECURITY NOTE (PR-104):
The poll endpoint returns REDACTED execution params (no SL/TP) to prevent
signal reselling. Hidden levels are stored in Signal.owner_only (encrypted)
and will be used server-side for automatic position closing.
"""

import logging
import time
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.approvals.models import Approval, ApprovalDecision
from backend.app.core.db import get_db
from backend.app.ea.auth import DeviceAuthDependency, get_device_auth
from backend.app.ea.close_schemas import (  # PR-104 Phase 5
    CloseAckRequest,
    CloseAckResponse,
    CloseCommandOut,
    CloseCommandsResponse,
)
from backend.app.ea.crypto import SignalEnvelope, get_key_manager  # PR-042
from backend.app.ea.models import Execution, ExecutionStatus
from backend.app.ea.schemas import (
    AckRequest,
    AckResponse,
    EncryptedPollResponse,
    EncryptedSignalEnvelope,
    ExecutionParamsOut,
)
from backend.app.observability.metrics import metrics
from backend.app.signals.encryption import decrypt_owner_only  # PR-104
from backend.app.signals.models import Signal
from backend.app.trading.positions.close_commands import (  # PR-104 Phase 5
    complete_command,
    get_pending_commands,
)
from backend.app.trading.positions.models import (  # PR-104 Phase 3
    OpenPosition,
    PositionStatus,
)
from backend.app.trading.positions.monitor import close_position  # PR-104 Phase 5

router = APIRouter(prefix="/api/v1/client", tags=["client"])
logger = logging.getLogger(__name__)


@router.get("/poll", response_model=EncryptedPollResponse)
async def poll_approved_signals(
    db: AsyncSession = Depends(get_db),
    device_auth: DeviceAuthDependency = Depends(get_device_auth),
    since: datetime | None = Query(
        None, description="Only return signals approved after this time"
    ),
) -> EncryptedPollResponse:
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
                Approval.decision == ApprovalDecision.APPROVED.value,
            )
        )

        if since:
            stmt = stmt.where(Approval.created_at >= since)

        result = await db.execute(stmt)
        approvals = result.scalars().all()

        # Filter out approvals that have already been executed on this device
        # PR-042: Wrap signals in encryption envelope
        key_manager = get_key_manager()
        envelope = SignalEnvelope(key_manager)
        encrypted_signals = []

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
            signal_stmt = select(Signal).where(Signal.id == approval.signal_id)
            signal_result = await db.execute(signal_stmt)
            signal = signal_result.scalar_one_or_none()
            if not signal:
                continue

            # Build execution params from signal payload
            payload = signal.payload or {}

            # PR-104: Decrypt owner_only field to access hidden SL/TP (server-side only)
            # These levels are used for position monitoring but NEVER sent to client
            owner_data = {}
            if signal.owner_only:
                try:
                    owner_data = decrypt_owner_only(signal.owner_only)
                    logger.info(
                        "Decrypted owner_only for position tracking",
                        extra={
                            "signal_id": signal.id,
                            "has_sl": "sl" in owner_data,
                            "has_tp": "tp" in owner_data,
                        },
                    )
                except Exception as e:
                    logger.error(
                        "Failed to decrypt owner_only",
                        extra={"signal_id": signal.id, "error": str(e)},
                    )
                    # Continue without owner_only data (fallback to payload if present)

            try:
                # Extract execution params from payload, using sensible defaults
                entry_price = payload.get("entry_price") or signal.price
                volume = payload.get("volume", 0.1)
                ttl_minutes = payload.get("ttl_minutes", 240)

                # PR-104: Build REDACTED execution params (NO SL/TP sent to client)
                # The hidden owner_sl/owner_tp from owner_data will be stored in
                # OpenPosition when EA acknowledges (Phase 3) but NOT sent here
                exec_params = ExecutionParamsOut(
                    entry_price=float(entry_price),
                    volume=float(volume),
                    ttl_minutes=int(ttl_minutes),
                    # CRITICAL: stop_loss and take_profit are INTENTIONALLY OMITTED
                    # Client EAs receive ONLY entry price, volume, and TTL
                    # Server will auto-close when hidden levels hit (position monitor)
                )
            except (ValueError, TypeError) as e:
                logger.warning(
                    "Failed to build execution params",
                    extra={"signal_id": signal.id, "error": str(e)},
                )
                continue

            # PR-042: Build plaintext signal object before encryption
            signal_data = {
                "approval_id": str(approval.id),
                "instrument": signal.instrument,
                "side": "buy" if signal.side == 0 else "sell",
                "entry_price": float(entry_price),
                "volume": float(volume),
                "ttl_minutes": int(ttl_minutes),
                "approved_at": approval.created_at.isoformat(),
                "created_at": signal.created_at.isoformat(),
            }

            # Encrypt the signal payload
            try:
                ciphertext_b64, nonce_b64, aad = envelope.encrypt_signal(
                    device_auth.device_id, signal_data
                )

                logger.info(
                    "Signal encrypted for device",
                    extra={
                        "device_id": device_auth.device_id,
                        "approval_id": str(approval.id),
                        "ciphertext_length": len(ciphertext_b64),
                    },
                )

                encrypted_signals.append(
                    EncryptedSignalEnvelope(
                        approval_id=approval.id,
                        ciphertext=ciphertext_b64,
                        nonce=nonce_b64,
                        aad=aad,
                    )
                )
            except Exception as e:
                logger.error(
                    "Failed to encrypt signal",
                    extra={"approval_id": str(approval.id), "error": str(e)},
                    exc_info=True,
                )
                # Skip this signal if encryption fails
                continue

        logger.info(
            "Poll response",
            extra={
                "device_id": device_auth.device_id,
                "signals_count": len(encrypted_signals),
            },
        )

        # Record duration
        duration = time.time() - start_time
        metrics.record_ea_poll_duration(duration)

        return EncryptedPollResponse(
            approvals=encrypted_signals,
            count=len(encrypted_signals),
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
        # Convert UUID to string for SQLite compatibility
        approval_id_str = str(request.approval_id)

        approval_stmt = select(Approval).where(Approval.id == approval_id_str)
        approval_result = await db.execute(approval_stmt)
        approval = approval_result.scalar_one_or_none()

        if not approval:
            logger.warning("Approval not found", extra={"approval_id": approval_id_str})
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
            approval_id=approval_id_str,  # Use string version for SQLite compatibility
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

        # PR-104 Phase 3: Create OpenPosition for successful placements
        if request.status == "placed":
            try:
                # Load signal to access owner_only and payload
                signal_stmt = select(Signal).where(Signal.id == approval.signal_id)
                signal_result = await db.execute(signal_stmt)
                signal = signal_result.scalar_one_or_none()

                if signal:
                    # Extract trade details from signal payload
                    payload = signal.payload or {}
                    instrument = payload.get("instrument", "UNKNOWN")
                    side = signal.side  # 0=buy, 1=sell
                    entry_price = payload.get("entry_price", 0.0)
                    volume = payload.get("volume", 0.0)

                    # Decrypt owner_only to get hidden SL/TP levels
                    owner_sl = None
                    owner_tp = None
                    if signal.owner_only:
                        try:
                            owner_data = decrypt_owner_only(signal.owner_only)
                            owner_sl = owner_data.get("stop_loss")
                            owner_tp = owner_data.get("take_profit")
                            logger.info(
                                "Decrypted owner_only for position tracking",
                                extra={
                                    "signal_id": signal.id,
                                    "has_sl": owner_sl is not None,
                                    "has_tp": owner_tp is not None,
                                },
                            )
                        except Exception as decrypt_err:
                            logger.error(
                                f"Failed to decrypt owner_only: {decrypt_err}",
                                extra={"signal_id": signal.id},
                                exc_info=True,
                            )

                    # Create OpenPosition record
                    position = OpenPosition(
                        id=str(uuid4()),
                        execution_id=execution.id,
                        signal_id=approval.signal_id,
                        approval_id=approval.id,
                        user_id=approval.user_id,
                        device_id=device_auth.device_id,
                        instrument=instrument,
                        side=side,
                        entry_price=float(entry_price),
                        volume=float(volume),
                        broker_ticket=request.broker_ticket,
                        owner_sl=float(owner_sl) if owner_sl is not None else None,
                        owner_tp=float(owner_tp) if owner_tp is not None else None,
                        status=PositionStatus.OPEN.value,
                        opened_at=datetime.utcnow(),
                    )

                    db.add(position)
                    await db.commit()
                    await db.refresh(position)

                    logger.info(
                        "OpenPosition created for trade execution",
                        extra={
                            "position_id": position.id,
                            "execution_id": execution.id,
                            "signal_id": signal.id,
                            "instrument": instrument,
                            "side": side,
                            "has_hidden_sl": owner_sl is not None,
                            "has_hidden_tp": owner_tp is not None,
                        },
                    )
                else:
                    logger.warning(
                        "Signal not found for OpenPosition creation",
                        extra={
                            "signal_id": approval.signal_id,
                            "execution_id": execution.id,
                        },
                    )

            except Exception as position_err:
                logger.error(
                    f"Failed to create OpenPosition: {position_err}",
                    extra={
                        "execution_id": execution.id,
                        "signal_id": approval.signal_id,
                    },
                    exc_info=True,
                )
                # Don't fail the ack if position creation fails
                # Position can be created manually later if needed

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


@router.get("/close-commands", response_model=CloseCommandsResponse)
async def poll_close_commands(
    db: AsyncSession = Depends(get_db),
    device_auth: DeviceAuthDependency = Depends(get_device_auth),
):
    """
    Poll for pending close commands (PR-104 Phase 5).

    The EA periodically calls this endpoint to check if the server wants
    any positions closed. This enables server-side autonomous closes when
    hidden owner SL/TP levels are hit.

    Workflow:
        1. Position monitor detects SL/TP breach
        2. Monitor creates CloseCommand (status=PENDING)
        3. EA polls this endpoint → receives close command
        4. EA attempts to close position in MT5
        5. EA sends acknowledgment to /close-ack

    Args:
        db: Database session
        device_auth: Device authentication (from HMAC headers)

    Returns:
        CloseCommandsResponse with list of pending commands

    Authentication:
        Requires HMAC device authentication (same as /poll)

    Security:
        - Only returns commands for authenticated device
        - Commands contain position_id and reason (sl_hit, tp_hit)
        - EA never sees the actual SL/TP values (anti-reselling)

    Example Response:
        {
            "commands": [
                {
                    "id": "cmd-uuid-123",
                    "position_id": "pos-uuid-456",
                    "reason": "sl_hit",
                    "expected_price": 2645.50,
                    "created_at": "2024-10-30T10:30:00Z"
                }
            ],
            "count": 1
        }
    """
    try:
        # Get pending commands for this device
        commands = await get_pending_commands(db, device_auth.device_id)

        # Convert to response format
        command_outs = [CloseCommandOut.from_orm(cmd) for cmd in commands]

        logger.info(
            f"Close commands poll: device={device_auth.device_id} count={len(commands)}"
        )

        return CloseCommandsResponse(
            commands=command_outs,
            count=len(command_outs),
        )

    except Exception as e:
        logger.error(
            f"Close commands poll failed: {e}",
            extra={"device_id": device_auth.device_id, "error": str(e)},
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/close-ack", response_model=CloseAckResponse, status_code=201)
async def acknowledge_close(
    request: CloseAckRequest,
    db: AsyncSession = Depends(get_db),
    device_auth: DeviceAuthDependency = Depends(get_device_auth),
):
    """
    Acknowledge close command execution (PR-104 Phase 5).

    After the EA receives a close command from /close-commands and attempts
    to execute it, the EA calls this endpoint to report the result.

    Workflow:
        1. EA receives close command from /close-commands poll
        2. EA attempts to close position in MT5
        3. EA calls this endpoint with result (executed or failed)
        4. Server updates CloseCommand and OpenPosition status

    Args:
        request: CloseAckRequest with execution result
        db: Database session
        device_auth: Device authentication (from HMAC headers)

    Returns:
        CloseAckResponse confirming acknowledgment recorded

    Request Body:
        {
            "command_id": "cmd-uuid-123",
            "status": "executed",  # or "failed"
            "actual_close_price": 2645.75,  # if executed
            "error_message": "...",  # if failed
            "timestamp": "2024-10-30T10:31:00Z"
        }

    Response:
        {
            "command_id": "cmd-uuid-123",
            "position_id": "pos-uuid-456",
            "status": "executed",
            "recorded_at": "2024-10-30T10:31:05Z"
        }

    Security:
        - Requires HMAC device authentication
        - Only device that owns the command can acknowledge
        - Updates both CloseCommand and OpenPosition status
    """
    try:
        # Validate status
        if request.status not in ("executed", "failed"):
            raise HTTPException(
                status_code=400,
                detail="Status must be 'executed' or 'failed'",
            )

        # Validate required fields
        if request.status == "executed" and request.actual_close_price is None:
            raise HTTPException(
                status_code=400,
                detail="actual_close_price required when status=executed",
            )

        if request.status == "failed" and request.error_message is None:
            raise HTTPException(
                status_code=400,
                detail="error_message required when status=failed",
            )

        # Complete the close command
        success = request.status == "executed"
        command = await complete_command(
            db,
            command_id=request.command_id,
            success=success,
            actual_close_price=request.actual_close_price,
            error_message=request.error_message,
        )

        # Update the OpenPosition status
        position = await db.get(OpenPosition, command.position_id)
        if position is None:
            raise HTTPException(
                status_code=404,
                detail=f"Position {command.position_id} not found",
            )

        if success:
            # Close the position successfully
            await close_position(
                db,
                position,
                close_price=request.actual_close_price,
                reason=command.reason,  # sl_hit, tp_hit, etc.
            )
            logger.info(
                f"Position closed: position={position.id} reason={command.reason} "
                f"price={request.actual_close_price}"
            )
        else:
            # Close failed - mark position as CLOSED_ERROR
            position.status = PositionStatus.CLOSED_ERROR.value
            await db.commit()

            logger.error(
                f"Position close failed: position={position.id} "
                f"reason={command.reason} error={request.error_message}"
            )
            # TODO: Trigger notification to user (PR-060 integration)
            # await send_close_failure_notification(position, request.error_message)

        return CloseAckResponse(
            command_id=command.id,
            position_id=command.position_id,
            status=request.status,
            recorded_at=datetime.utcnow(),
        )

    except HTTPException:
        raise
    except ValueError as e:
        # CloseCommand not found
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(
            f"Close ack failed: {e}",
            extra={"command_id": request.command_id, "error": str(e)},
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Internal server error")
