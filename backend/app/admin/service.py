"""
PR-099: Admin Portal Service Layer

Business logic for admin operations: refunds, KYC, fraud resolution, etc.
"""

import logging
from datetime import UTC, datetime
from typing import Any, Optional
from uuid import uuid4

import stripe
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.audit.service import AuditService
from backend.app.fraud.models import AnomalyEvent
from backend.app.support.models import Ticket
from backend.app.users.models import User

logger = logging.getLogger(__name__)


async def process_refund(
    db: AsyncSession,
    user_id: str,
    amount: float,
    reason: str,
    admin_user: User,
    stripe_payment_intent_id: Optional[str] = None,
) -> dict[str, Any]:
    """
    Process a refund for a user with Stripe integration and audit logging.

    Args:
        db: Database session
        user_id: User ID to refund
        amount: Refund amount in GBP
        reason: Reason for refund (min 10 chars)
        admin_user: Admin/owner processing the refund
        stripe_payment_intent_id: Optional Stripe payment intent ID

    Returns:
        Dict with refund details (refund_id, status, stripe_refund_id)

    Raises:
        ValueError: If user not found or invalid amount
        stripe.error.StripeError: If Stripe API fails

    Example:
        >>> result = await process_refund(
        ...     db, "user_123", 50.00, "Service issue", admin_user
        ... )
        >>> assert result["status"] == "succeeded"
    """
    # Validate user exists
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise ValueError(f"User {user_id} not found")

    # Validate amount
    if amount <= 0 or amount > 10000:
        raise ValueError(f"Invalid refund amount: {amount}")

    refund_id = str(uuid4())
    stripe_refund_id = None

    try:
        # Process Stripe refund if payment_intent_id provided
        if stripe_payment_intent_id:
            stripe_refund = stripe.Refund.create(
                payment_intent=stripe_payment_intent_id,
                amount=int(amount * 100),  # Convert GBP to pence
                reason="requested_by_customer",
                metadata={
                    "refund_id": refund_id,
                    "admin_id": admin_user.id,
                    "reason": reason,
                },
                idempotency_key=refund_id,  # Ensure idempotency
            )
            stripe_refund_id = stripe_refund.id
            status = stripe_refund.status  # pending, succeeded, failed

        else:
            # Manual refund (no Stripe integration)
            status = "manual_pending"

        # Audit log
        await AuditService.record(
            db=db,
            actor_id=admin_user.id,
            action="refund_processed",
            target="billing",
            target_id=refund_id,
            meta={
                "target_user_id": user_id,
                "amount": amount,
                "reason": reason,
                "stripe_refund_id": stripe_refund_id,
                "status": status,
            },
        )

        await db.commit()

        logger.info(
            "Refund processed",
            extra={
                "refund_id": refund_id,
                "user_id": user_id,
                "amount": amount,
                "admin_id": admin_user.id,
                "status": status,
            },
        )

        return {
            "refund_id": refund_id,
            "user_id": user_id,
            "amount": amount,
            "status": status,
            "stripe_refund_id": stripe_refund_id,
            "processed_at": datetime.now(UTC),
            "processed_by": admin_user.id,
        }

    except stripe.error.StripeError as e:
        logger.error(f"Stripe refund failed: {e}", exc_info=True)
        await db.rollback()
        raise


async def approve_kyc(
    db: AsyncSession,
    user_id: str,
    admin_user: User,
    notes: Optional[str] = None,
) -> User:
    """
    Approve KYC for a user and update entitlements.

    Args:
        db: Database session
        user_id: User ID to approve
        admin_user: Admin/owner approving KYC
        notes: Optional admin notes

    Returns:
        User: Updated user object

    Raises:
        ValueError: If user not found or already approved

    Example:
        >>> user = await approve_kyc(db, "user_123", admin_user, "Verified ID")
        >>> assert user.kyc_status == "approved"
    """
    # Get user
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise ValueError(f"User {user_id} not found")

    if user.kyc_status == "approved":
        raise ValueError(f"User {user_id} KYC already approved")

    # Update KYC status
    user.kyc_status = "approved"
    user.kyc_approved_at = datetime.now(UTC)
    user.kyc_approved_by = admin_user.id

    # Audit log
    await AuditService.record(
        db=db,
        actor_id=admin_user.id,
        action="kyc_approved",
        target="user",
        target_id=user_id,
        meta={
            "notes": notes,
            "approved_at": user.kyc_approved_at.isoformat(),
        },
    )

    await db.commit()
    await db.refresh(user)

    logger.info(
        "KYC approved",
        extra={
            "user_id": user_id,
            "admin_id": admin_user.id,
        },
    )

    return user


async def resolve_fraud_event(
    db: AsyncSession,
    event_id: str,
    resolution: str,
    action_taken: str,
    admin_user: User,
    notes: Optional[str] = None,
) -> AnomalyEvent:
    """
    Resolve a fraud event with specified action.

    Args:
        db: Database session
        event_id: Fraud event ID
        resolution: Resolution type (false_positive, confirmed_fraud, needs_review)
        action_taken: Action taken (min 10 chars)
        admin_user: Admin/owner resolving event
        notes: Optional admin notes

    Returns:
        AnomalyEvent: Updated fraud event

    Raises:
        ValueError: If event not found or invalid resolution

    Example:
        >>> event = await resolve_fraud_event(
        ...     db, "event_123", "false_positive", "Reviewed logs - legitimate", admin_user
        ... )
        >>> assert event.status == "resolved"
    """
    # Get event
    event_result = await db.execute(
        select(AnomalyEvent).where(AnomalyEvent.id == event_id)
    )
    event = event_result.scalar_one_or_none()
    if not event:
        raise ValueError(f"Fraud event {event_id} not found")

    if event.status == "resolved":
        raise ValueError(f"Fraud event {event_id} already resolved")

    # Validate resolution
    valid_resolutions = ["false_positive", "confirmed_fraud", "needs_review"]
    if resolution not in valid_resolutions:
        raise ValueError(
            f"Invalid resolution: {resolution}. Must be one of {valid_resolutions}"
        )

    # Update event
    event.status = "resolved"
    event.resolution = resolution
    event.action_taken = action_taken
    event.resolved_at = datetime.now(UTC)
    event.resolved_by = admin_user.id
    event.admin_notes = notes

    # If confirmed fraud, suspend user
    if resolution == "confirmed_fraud":
        user_result = await db.execute(select(User).where(User.id == event.user_id))
        user = user_result.scalar_one_or_none()
        if user:
            user.status = "suspended"
            logger.warning(
                "User suspended due to confirmed fraud",
                extra={"user_id": user.id, "event_id": event_id},
            )

    # Audit log
    await AuditService.record(
        db=db,
        actor_id=admin_user.id,
        action="fraud_event_resolved",
        target="fraud",
        target_id=event_id,
        meta={
            "target_user_id": event.user_id,
            "resolution": resolution,
            "action_taken": action_taken,
            "notes": notes,
        },
    )

    await db.commit()
    await db.refresh(event)

    logger.info(
        "Fraud event resolved",
        extra={
            "event_id": event_id,
            "resolution": resolution,
            "admin_id": admin_user.id,
        },
    )

    return event


async def assign_ticket(
    db: AsyncSession,
    ticket_id: str,
    assigned_to: str,
    admin_user: User,
) -> Ticket:
    """
    Assign a support ticket to an admin.

    Args:
        db: Database session
        ticket_id: Ticket ID
        assigned_to: Admin user ID to assign to
        admin_user: Admin/owner performing assignment

    Returns:
        Ticket: Updated ticket

    Raises:
        ValueError: If ticket not found or assignee invalid

    Example:
        >>> ticket = await assign_ticket(db, "ticket_123", "admin_456", admin_user)
        >>> assert ticket.assigned_to == "admin_456"
    """
    # Get ticket
    ticket_result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = ticket_result.scalar_one_or_none()
    if not ticket:
        raise ValueError(f"Ticket {ticket_id} not found")

    # Validate assignee exists and is admin
    assignee_result = await db.execute(select(User).where(User.id == assigned_to))
    assignee = assignee_result.scalar_one_or_none()
    if not assignee or not (assignee.is_admin or assignee.is_owner):
        raise ValueError(f"Invalid assignee: {assigned_to}")

    # Update ticket
    ticket.assigned_to = assigned_to
    ticket.status = "assigned"
    ticket.assigned_at = datetime.now(UTC)

    # Audit log
    await AuditService.record(
        db=db,
        actor_id=admin_user.id,
        action="ticket_assigned",
        target="support",
        target_id=ticket_id,
        meta={
            "assigned_to": assigned_to,
            "user_id": ticket.user_id,
        },
    )

    await db.commit()
    await db.refresh(ticket)

    logger.info(
        "Ticket assigned",
        extra={
            "ticket_id": ticket_id,
            "assigned_to": assigned_to,
            "admin_id": admin_user.id,
        },
    )

    return ticket
