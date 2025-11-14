"""Reward issuance service.

Handles discount/credit rewards for course completion.
Integrates with billing system for redemption tracking.

PR-064 Implementation.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.education.models import Reward

logger = logging.getLogger(__name__)


async def grant_discount(
    db: AsyncSession,
    user_id: str,
    course_id: str,
    percent: float,
    expires_days: int = 30,
) -> Reward:
    """Grant a discount reward to a user for course completion.

    Args:
        db: Database session
        user_id: User UUID
        course_id: Course UUID
        percent: Discount percentage (0-100)
        expires_days: Days until reward expires

    Returns:
        Created Reward record

    Raises:
        ValueError: If percent out of range

    Example:
        >>> reward = await grant_discount(db, user_id, course_id, 10.0, 30)
        >>> assert reward.reward_value == 10.0
        >>> assert reward.reward_type == "discount"
    """
    if not (0 < percent <= 100):
        raise ValueError(
            f"Invalid discount percent: {percent}. Must be between 0 and 100."
        )

    # Calculate expiration
    issued_at = datetime.now(UTC)
    expires_at = issued_at + timedelta(days=expires_days)

    # Create reward
    reward = Reward(
        user_id=user_id,
        course_id=course_id,
        reward_type="discount",
        reward_value=percent,
        currency=None,  # Discount is percentage, not currency-specific
        issued_at=issued_at,
        expires_at=expires_at,
    )

    db.add(reward)
    await db.commit()
    await db.refresh(reward)

    logger.info(
        f"Discount granted: {reward.id} user={user_id} course={course_id} {percent}% expires={expires_at.isoformat()}",
        extra={
            "reward_id": reward.id,
            "user_id": user_id,
            "course_id": course_id,
            "discount_percent": percent,
            "expires_at": expires_at.isoformat(),
        },
    )

    return reward


async def grant_credit(
    db: AsyncSession,
    user_id: str,
    course_id: str,
    amount: float,
    currency: str = "GBP",
    expires_days: int = 30,
) -> Reward:
    """Grant a credit reward to a user for course completion.

    Args:
        db: Database session
        user_id: User UUID
        course_id: Course UUID
        amount: Credit amount
        currency: Currency code (GBP, USD, EUR, etc.)
        expires_days: Days until reward expires

    Returns:
        Created Reward record

    Raises:
        ValueError: If amount <= 0

    Example:
        >>> reward = await grant_credit(db, user_id, course_id, 5.0, "GBP", 30)
        >>> assert reward.reward_value == 5.0
        >>> assert reward.currency == "GBP"
    """
    if amount <= 0:
        raise ValueError(f"Invalid credit amount: {amount}. Must be positive.")

    # Calculate expiration
    issued_at = datetime.now(UTC)
    expires_at = issued_at + timedelta(days=expires_days)

    # Create reward
    reward = Reward(
        user_id=user_id,
        course_id=course_id,
        reward_type="credit",
        reward_value=amount,
        currency=currency.upper(),
        issued_at=issued_at,
        expires_at=expires_at,
    )

    db.add(reward)
    await db.commit()
    await db.refresh(reward)

    logger.info(
        f"Credit granted: {reward.id} user={user_id} course={course_id} {amount} {currency} expires={expires_at.isoformat()}",
        extra={
            "reward_id": reward.id,
            "user_id": user_id,
            "course_id": course_id,
            "credit_amount": amount,
            "currency": currency,
            "expires_at": expires_at.isoformat(),
        },
    )

    return reward


async def redeem_reward(
    db: AsyncSession,
    reward_id: str,
    order_id: str,
) -> Reward:
    """Mark a reward as redeemed.

    Args:
        db: Database session
        reward_id: Reward UUID
        order_id: Billing order/transaction ID

    Returns:
        Updated Reward record

    Raises:
        ValueError: If reward not found, already redeemed, or expired
    """
    from sqlalchemy.future import select

    # Get reward
    result = await db.execute(select(Reward).where(Reward.id == reward_id))
    reward = result.scalar_one_or_none()

    if not reward:
        raise ValueError(f"Reward not found: {reward_id}")

    if reward.redeemed_at:
        raise ValueError(
            f"Reward already redeemed: {reward_id} at {reward.redeemed_at.isoformat()}"
        )

    # Check expiration - handle SQLite naive datetimes
    now = datetime.now(UTC)
    expires_at = reward.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    
    if now > expires_at:
        raise ValueError(
            f"Reward expired: {reward_id} at {reward.expires_at.isoformat()}"
        )

    # Mark as redeemed
    reward.redeemed_at = now
    reward.redemption_order_id = order_id

    await db.commit()
    await db.refresh(reward)

    logger.info(
        f"Reward redeemed: {reward_id} order={order_id}",
        extra={
            "reward_id": reward_id,
            "order_id": order_id,
            "redeemed_at": now.isoformat(),
        },
    )

    return reward


async def get_active_rewards(
    db: AsyncSession,
    user_id: str,
    reward_type: Optional[str] = None,
) -> list[Reward]:
    """Get user's active (unredeemed, unexpired) rewards.

    Args:
        db: Database session
        user_id: User UUID
        reward_type: Filter by reward type (discount/credit) or None for all

    Returns:
        List of active rewards

    Example:
        >>> rewards = await get_active_rewards(db, user_id, "discount")
        >>> assert all(r.redeemed_at is None for r in rewards)
    """
    from sqlalchemy import and_
    from sqlalchemy.future import select

    now = datetime.now(UTC)

    # Note: Can't use expires_at > now in SQLAlchemy query with SQLite naive datetimes
    # So we query all unredeemed rewards and filter expiration in Python
    query = select(Reward).where(
        and_(
            Reward.user_id == user_id,
            Reward.redeemed_at.is_(None),
        )
    )

    if reward_type:
        query = query.where(Reward.reward_type == reward_type)

    query = query.order_by(Reward.expires_at)

    result = await db.execute(query)
    all_rewards = list(result.scalars().all())

    # Filter expired rewards (handle SQLite naive datetimes)
    active_rewards = []
    for reward in all_rewards:
        expires_at = reward.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if now <= expires_at:
            active_rewards.append(reward)

    logger.debug(
        f"Active rewards: user={user_id} type={reward_type} count={len(active_rewards)}",
        extra={"user_id": user_id, "reward_type": reward_type, "count": len(active_rewards)},
    )

    return active_rewards
