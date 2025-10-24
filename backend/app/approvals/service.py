"""Approval domain business logic."""

import logging
from typing import Optional
from uuid import uuid4

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from backend.app.approvals.models import Approval
from backend.app.approvals.schemas import ApprovalOut, ApprovalRequest
from backend.app.signals.models import Signal


logger = logging.getLogger(__name__)


async def create_approval(
    db: AsyncSession,
    user_id: str,
    request: ApprovalRequest,
) -> ApprovalOut:
    """Create an approval decision for a signal.

    Validates signal exists, enforces one approval per user per signal.

    Args:
        db: Database session
        user_id: User making the approval decision
        request: Approval request data

    Returns:
        ApprovalOut: Created approval

    Raises:
        ValueError: If signal not found, already approved by user, or invalid decision

    Example:
        >>> approval = await create_approval(
        ...     db,
        ...     user_id="user-123",
        ...     request=ApprovalRequest(
        ...         signal_id="sig-456",
        ...         decision=0,
        ...         consent_version="2024-01-15",
        ...         ip="192.168.1.1",
        ...         ua="Mozilla/5.0"
        ...     )
        ... )
        >>> assert approval.decision == 0
    """
    # Validate signal exists
    signal_result = await db.execute(
        select(Signal).where(Signal.id == request.signal_id)
    )
    signal = signal_result.scalars().first()
    if not signal:
        logger.warning(
            f"Signal not found for approval",
            extra={"signal_id": request.signal_id, "user_id": user_id},
        )
        raise ValueError(f"Signal {request.signal_id} not found")

    # Check for existing approval (unique constraint)
    existing_result = await db.execute(
        select(Approval).where(
            and_(
                Approval.signal_id == request.signal_id,
                Approval.user_id == user_id,
            )
        )
    )
    existing = existing_result.scalars().first()
    if existing:
        logger.warning(
            f"Duplicate approval attempt",
            extra={
                "signal_id": request.signal_id,
                "user_id": user_id,
                "existing_id": existing.id,
            },
        )
        raise ValueError(
            f"User {user_id} has already approved signal {request.signal_id}"
        )

    # Create approval
    approval = Approval(
        id=str(uuid4()),
        signal_id=request.signal_id,
        user_id=user_id,
        device_id=request.device_id,
        decision=request.decision,
        consent_version=request.consent_version,
        ip=request.ip,
        ua=request.ua,
    )

    db.add(approval)
    try:
        await db.commit()
        await db.refresh(approval)
        logger.info(
            f"Approval created",
            extra={
                "approval_id": approval.id,
                "signal_id": request.signal_id,
                "user_id": user_id,
                "decision": request.decision,
            },
        )
        return ApprovalOut(
            id=approval.id,
            signal_id=approval.signal_id,
            user_id=approval.user_id,
            decision=approval.decision,
            created_at=approval.created_at,
        )
    except IntegrityError as e:
        await db.rollback()
        logger.error(
            f"Integrity error creating approval",
            exc_info=True,
            extra={"signal_id": request.signal_id, "user_id": user_id},
        )
        raise ValueError("Failed to create approval (duplicate or constraint violation)")


async def get_approval(db: AsyncSession, approval_id: str) -> Optional[ApprovalOut]:
    """Get an approval by ID.

    Args:
        db: Database session
        approval_id: Approval ID

    Returns:
        ApprovalOut if found, None otherwise

    Example:
        >>> approval = await get_approval(db, "apr-123")
        >>> assert approval is None or approval.id == "apr-123"
    """
    result = await db.execute(select(Approval).where(Approval.id == approval_id))
    approval = result.scalars().first()
    if not approval:
        return None

    return ApprovalOut(
        id=approval.id,
        signal_id=approval.signal_id,
        user_id=approval.user_id,
        decision=approval.decision,
        created_at=approval.created_at,
    )


async def get_user_approvals(
    db: AsyncSession, user_id: str, limit: int = 100, offset: int = 0
) -> list[ApprovalOut]:
    """Get all approvals by a user.

    Args:
        db: Database session
        user_id: User ID
        limit: Max results (default 100, max 1000)
        offset: Result offset for pagination

    Returns:
        List of ApprovalOut objects

    Example:
        >>> approvals = await get_user_approvals(db, "user-123")
        >>> assert all(a.user_id == "user-123" for a in approvals)
    """
    # Validate limit
    limit = min(limit, 1000)
    limit = max(limit, 1)
    offset = max(offset, 0)

    result = await db.execute(
        select(Approval)
        .where(Approval.user_id == user_id)
        .order_by(Approval.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    approvals = result.scalars().all()

    return [
        ApprovalOut(
            id=a.id,
            signal_id=a.signal_id,
            user_id=a.user_id,
            decision=a.decision,
            created_at=a.created_at,
        )
        for a in approvals
    ]


async def get_signal_approvals(
    db: AsyncSession, signal_id: str, limit: int = 100, offset: int = 0
) -> list[ApprovalOut]:
    """Get all approvals for a signal.

    Args:
        db: Database session
        signal_id: Signal ID
        limit: Max results (default 100, max 1000)
        offset: Result offset for pagination

    Returns:
        List of ApprovalOut objects

    Example:
        >>> approvals = await get_signal_approvals(db, "sig-123")
        >>> assert all(a.signal_id == "sig-123" for a in approvals)
    """
    # Validate limit
    limit = min(limit, 1000)
    limit = max(limit, 1)
    offset = max(offset, 0)

    result = await db.execute(
        select(Approval)
        .where(Approval.signal_id == signal_id)
        .order_by(Approval.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    approvals = result.scalars().all()

    return [
        ApprovalOut(
            id=a.id,
            signal_id=a.signal_id,
            user_id=a.user_id,
            decision=a.decision,
            created_at=a.created_at,
        )
        for a in approvals
    ]
