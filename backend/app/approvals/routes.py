"""Approvals API routes."""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.approvals.models import Approval, ApprovalDecision
from backend.app.approvals.schema import ApprovalCreate, ApprovalOut
from backend.app.approvals.service import ApprovalService
from backend.app.audit.service import AuditService
from backend.app.auth.dependencies import get_current_user
from backend.app.auth.models import User
from backend.app.core.db import get_db
from backend.app.observability import get_metrics
from backend.app.risk.service import RiskService
from backend.app.signals.models import Signal

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["approvals"])


def get_client_ip(request: Request) -> str:
    """Extract client IP from request."""
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/approvals", status_code=201, response_model=ApprovalOut)
async def create_approval(
    request_data: ApprovalCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApprovalOut:
    """Create approval for a signal.

    Args:
        request_data: Approval creation request
        db: Database session
        current_user: Authenticated user
        request: HTTP request (for IP and UA)

    Returns:
        ApprovalOut: Created approval

    Raises:
        HTTPException: 400 if invalid, 401 if unauthorized, 404 if signal not found, 409 if duplicate

    Example:
        >>> response = await create_approval(
        ...     ApprovalCreate(signal_id="sig123", decision="approved"),
        ...     db=db_session,
        ...     current_user=user,
        ...     request=request
        ... )
        >>> assert response.status_code == 201
    """
    start_time = datetime.utcnow()

    try:
        # Get signal
        result = await db.execute(
            select(Signal).where(Signal.id == request_data.signal_id)
        )
        signal = result.scalar()
        if not signal:
            logger.warning(
                f"Signal not found: {request_data.signal_id}",
                extra={"signal_id": request_data.signal_id, "user_id": current_user.id},
            )
            raise HTTPException(status_code=404, detail="Signal not found")

        # Check ownership
        if signal.user_id != current_user.id:
            logger.warning(
                "Unauthorized approval attempt",
                extra={"signal_id": request_data.signal_id, "user_id": current_user.id},
            )
            raise HTTPException(status_code=403, detail="Not signal owner")

        # ===== NEW: Risk Check (PR-048 Integration) =====
        # Validate signal against client risk limits before approval
        risk_check = await RiskService.check_risk_limits(current_user.id, signal, db)
        if not risk_check["passes"]:
            # Log violations for audit
            violation_details = [v["message"] for v in risk_check["violations"]]
            logger.warning(
                f"Signal {request_data.signal_id} rejected due to risk violations",
                extra={
                    "signal_id": request_data.signal_id,
                    "user_id": current_user.id,
                    "violations": violation_details,
                },
            )
            # Return 403 with violation details
            raise HTTPException(
                status_code=403,
                detail={
                    "message": "Signal violates risk limits",
                    "violations": risk_check["violations"],
                },
            )
        # ===== END: Risk Check =====

        # Check for duplicate approval (signal_id, user_id)
        existing = await db.execute(
            select(Approval).where(
                (Approval.signal_id == request_data.signal_id)
                & (Approval.user_id == current_user.id)
            )
        )
        if existing.scalar():
            logger.warning(
                "Duplicate approval attempt",
                extra={"signal_id": request_data.signal_id, "user_id": current_user.id},
            )
            raise HTTPException(
                status_code=409, detail="Approval already exists for this signal"
            )

        # Capture request context
        client_ip = get_client_ip(request)
        user_agent = request.headers.get("user-agent", "unknown")[:500]

        # Create approval
        approval_service = ApprovalService(db)
        approval = await approval_service.approve_signal(
            signal_id=request_data.signal_id,
            user_id=str(current_user.id),
            decision=request_data.decision,
            reason=request_data.reason,
            ip=client_ip,
            ua=user_agent,
            consent_version=request_data.consent_version,
        )

        # Record audit log
        await AuditService.record(
            db=db,
            action=f"approval.{request_data.decision}",
            target="approval",
            actor_id=str(current_user.id),
            actor_role=current_user.role,
            target_id=str(approval.id),
            meta={
                "signal_id": request_data.signal_id,
                "decision": request_data.decision,
                "reason": request_data.reason,
            },
            ip_address=client_ip,
            user_agent=user_agent,
            status="success",
        )

        # Record metrics
        try:
            metrics = get_metrics()
            decision_label = (
                "approved" if request_data.decision == "approved" else "rejected"
            )
            metrics.approvals_total.labels(decision=decision_label).inc()

            duration_seconds = (datetime.utcnow() - start_time).total_seconds()
            metrics.approval_latency_seconds.observe(duration_seconds)
        except Exception as e:
            logger.warning(f"Failed to record metrics: {e}")

        logger.info(
            f"Approval created: {approval.id}",
            extra={
                "approval_id": approval.id,
                "signal_id": request_data.signal_id,
                "user_id": current_user.id,
                "decision": request_data.decision,
            },
        )

        return ApprovalOut(
            id=approval.id,
            signal_id=approval.signal_id,
            user_id=approval.user_id,
            decision=(
                "approved"
                if approval.decision == ApprovalDecision.APPROVED.value
                else "rejected"
            ),
            reason=approval.reason,
            consent_version=approval.consent_version,
            created_at=approval.created_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Approval creation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/approvals/{approval_id}", response_model=ApprovalOut)
async def get_approval(
    approval_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApprovalOut:
    """Get approval by ID.

    Args:
        approval_id: Approval ID
        db: Database session
        current_user: Authenticated user

    Returns:
        ApprovalOut: Approval details

    Raises:
        HTTPException: 404 if not found, 403 if not authorized
    """
    try:
        result = await db.execute(
            select(Approval).where(
                (Approval.id == approval_id) & (Approval.user_id == current_user.id)
            )
        )
        approval = result.scalar()
        if not approval:
            raise HTTPException(status_code=404, detail="Approval not found")

        return ApprovalOut(
            id=approval.id,
            signal_id=approval.signal_id,
            user_id=approval.user_id,
            decision=(
                "approved"
                if approval.decision == ApprovalDecision.APPROVED.value
                else "rejected"
            ),
            reason=approval.reason,
            consent_version=approval.consent_version,
            created_at=approval.created_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get approval: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/approvals", response_model=list[ApprovalOut])
async def list_approvals(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    skip: int = 0,
    limit: int = 50,
) -> list[ApprovalOut]:
    """List approvals for current user.

    Args:
        db: Database session
        current_user: Authenticated user
        skip: Pagination skip
        limit: Pagination limit

    Returns:
        list[ApprovalOut]: List of approvals
    """
    try:
        result = await db.execute(
            select(Approval)
            .where(Approval.user_id == current_user.id)
            .order_by(Approval.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        approvals = result.scalars().all()

        return [
            ApprovalOut(
                id=a.id,
                signal_id=a.signal_id,
                user_id=a.user_id,
                decision=(
                    "approved"
                    if a.decision == ApprovalDecision.APPROVED.value
                    else "rejected"
                ),
                reason=a.reason,
                consent_version=a.consent_version,
                created_at=a.created_at,
            )
            for a in approvals
        ]

    except Exception as e:
        logger.error(f"Failed to list approvals: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e
