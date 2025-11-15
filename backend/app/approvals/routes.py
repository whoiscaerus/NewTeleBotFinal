"""Approvals API routes."""

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.approvals.models import Approval, ApprovalDecision
from backend.app.approvals.schema import ApprovalCreate, ApprovalOut, PendingApprovalOut
from backend.app.approvals.service import ApprovalService
from backend.app.audit.service import AuditService
from backend.app.auth.dependencies import get_current_user
from backend.app.auth.jwt_handler import JWTHandler
from backend.app.auth.models import User
from backend.app.core.db import get_db
from backend.app.observability import get_metrics
from backend.app.risk.service import RiskService
from backend.app.signals.models import Signal, SignalStatus

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["approvals"])


def get_client_ip(request: Request) -> str:
    """Extract client IP from request."""
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/approvals", response_model=ApprovalOut, status_code=201)
async def create_approval(
    approval_create: ApprovalCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApprovalOut:
    """Create approval for a signal.

    Submits user's approval/rejection decision for a pending signal.
    Returns 201 on success, 400 if signal not found or already decided.

    Args:
        approval_create: Approval decision (signal_id, decision, reason, consent_version)
        request: HTTP request (for IP/UA)
        db: Database session
        current_user: Authenticated user making decision

    Returns:
        ApprovalOut: Created approval record

    Raises:
        HTTPException: 401 if not authenticated, 404 if signal not found,
                      409 if already approved/rejected, 422 if validation fails

    Security:
        - Users can only approve/reject their own signals
        - Requires JWT authentication
        - IP and User-Agent logged for audit trail

    Example:
        >>> response = await create_approval(
        ...     ApprovalCreate(signal_id="sig-123", decision="approved"),
        ...     request, db, current_user
        ... )
        >>> response.status_code == 201
        True
    """
    try:
        service = ApprovalService(db)

        # Get client IP and User-Agent for audit logging
        client_ip = get_client_ip(request)
        user_agent = request.headers.get("user-agent", "unknown")

        # Create approval
        approval = await service.approve_signal(
            signal_id=approval_create.signal_id,
            user_id=str(current_user.id),
            decision=approval_create.decision,
            reason=approval_create.reason,
            ip=client_ip,
            ua=user_agent,
            consent_version=approval_create.consent_version,
        )

        # Convert decision from int to string ("approved" or "rejected")
        decision_str = "approved" if approval.decision == 1 else "rejected"

        # Return success response
        return ApprovalOut(
            id=approval.id,
            signal_id=approval.signal_id,
            user_id=approval.user_id,
            decision=decision_str,
            reason=approval.reason,
            consent_version=approval.consent_version,
            created_at=approval.created_at,
        )

    except ValueError as e:
        error_msg = str(e)
        logger.warning(f"Approval validation error: {error_msg}")

        # Different error codes based on the error message
        if "already exists" in error_msg.lower():
            raise HTTPException(status_code=409, detail=error_msg)
        elif "not found" in error_msg.lower():
            raise HTTPException(status_code=404, detail=error_msg)
        elif "not signal owner" in error_msg.lower():
            raise HTTPException(status_code=403, detail=error_msg)
        else:
            raise HTTPException(status_code=400, detail=error_msg)
    except Exception as e:
        logger.error(f"Error creating approval: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create approval")


@router.get("/approvals/pending", response_model=list[PendingApprovalOut])
async def get_pending_approvals(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    since: datetime | None = Query(
        None,
        description="Only fetch approvals created after this timestamp (ISO format)",
    ),
    skip: int = Query(0, ge=0, description="Pagination: number of records to skip"),
    limit: int = Query(
        50, ge=1, le=100, description="Pagination: max records to return"
    ),
) -> list[PendingApprovalOut]:
    """Get pending (unapproved) signals for mini app approval console.

    Returns list of signals waiting for user approval, with approval tokens.
    Used by mini app to fetch pending approvals for real-time polling.

    Args:
        db: Database session
        current_user: Authenticated user
        since: Optional timestamp to fetch only newer approvals (for polling efficiency)
        skip: Pagination offset (default: 0)
        limit: Pagination limit, max 100 (default: 50)

    Returns:
        list[PendingApprovalOut]: List of pending approvals with signal details

    Raises:
        HTTPException: 401 if not authenticated, 400 if invalid since parameter

    Security:
        - Returns only user's own approvals (signal.user_id == current_user.id)
        - Never returns TP/SL data (stored in owner_only field, not exposed)
        - Tokens valid for 5 minutes only
        - Requires JWT authentication

    Example:
        >>> # Fetch pending approvals
        >>> response = await get_pending_approvals(db=db, current_user=user)
        >>> len(response) > 0
        True
        >>> response[0].signal_id is not None
        True
    """
    try:
        # Build query: approvals without decision (pending), owned by current user
        query = (
            select(Approval, Signal)
            .join(Signal, Approval.signal_id == Signal.id)
            .where(
                and_(
                    Approval.user_id == str(current_user.id),
                    Approval.decision.is_(
                        None
                    ),  # Type: ignore # NULL decision = pending
                    Signal.status
                    == SignalStatus.NEW.value,  # Only NEW signals are pending
                )
            )
            .order_by(Approval.created_at.desc())
        )

        # Optional: filter by since parameter for polling efficiency
        if since:
            try:
                since_dt = (
                    since
                    if isinstance(since, datetime)
                    else datetime.fromisoformat(
                        since.isoformat() if hasattr(since, "isoformat") else str(since)
                    )
                )
                query = query.where(Approval.created_at > since_dt)
            except (ValueError, TypeError):
                logger.warning(f"Invalid since parameter: {since}")
                raise HTTPException(
                    status_code=400, detail="Invalid since parameter format"
                )

        # Execute query with pagination
        result = await db.execute(query.offset(skip).limit(limit))
        rows = result.all()

        # Generate approval tokens for each pending approval
        jwt_handler = JWTHandler()
        pending_approvals: list[PendingApprovalOut] = []

        for approval, signal in rows:
            # Generate 5-minute approval token if not already stored
            if not approval.approval_token:
                token_expires_delta = timedelta(minutes=5)
                token = jwt_handler.create_token(
                    user_id=str(current_user.id),
                    audience="miniapp_approval",
                    expires_delta=token_expires_delta,
                    role="user",
                    jti=str(approval.id),  # Unique identifier for this approval token
                )
                expires_at = datetime.now(UTC) + token_expires_delta

                # Update approval record with token (for audit trail)
                approval.approval_token = token
                approval.expires_at = expires_at
                db.add(approval)
            else:
                expires_at = approval.expires_at
                token = approval.approval_token

            # Determine lot_size from signal payload or default
            lot_size = 0.04  # Default fallback
            if signal.payload and isinstance(signal.payload, dict):
                lot_size = float(signal.payload.get("lot_size", 0.04))

            # Build response (safe: no SL/TP exposed)
            pending_approvals.append(
                PendingApprovalOut(
                    signal_id=signal.id,
                    instrument=signal.instrument,
                    side="buy" if signal.side == 0 else "sell",
                    lot_size=lot_size,
                    created_at=signal.created_at,
                    approval_token=token,
                    expires_at=expires_at,
                )
            )

        # Commit token updates to DB (for audit trail)
        if pending_approvals:
            await db.commit()

        # Record telemetry
        try:
            metrics = get_metrics()
            metrics.miniapp_approvals_viewed_total.inc()  # Counter for page views
        except Exception as e:
            logger.warning(
                f"Failed to record miniapp_approvals_viewed_total metric: {e}"
            )

        logger.info(
            "Pending approvals fetched for mini app",
            extra={
                "user_id": str(current_user.id),
                "count": len(pending_approvals),
            },
        )

        return pending_approvals

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch pending approvals: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


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
