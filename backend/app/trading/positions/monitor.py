"""Position Monitor Service - Breach Detection for Owner SL/TP Levels.

This service monitors open positions and detects when current market price
breaches the hidden owner_sl or owner_tp levels. When a breach is detected,
it generates a close command for the EA to execute.

This is a critical component of PR-104's anti-reselling protection:
- Clients never see the SL/TP levels
- Server monitors positions autonomously
- Close commands sent when levels are hit
- Prevents signal reselling by hiding exit strategy
"""

from datetime import datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.trading.positions.models import OpenPosition, PositionStatus


async def check_position_breach(
    position: OpenPosition, current_price: float
) -> Literal["sl_hit", "tp_hit"] | None:
    """
    Check if current market price breaches the position's owner SL/TP levels.

    This function implements the core breach detection logic for anti-reselling
    protection. The owner_sl and owner_tp values are NEVER exposed to clients,
    only used server-side for autonomous monitoring.

    Args:
        position: OpenPosition with owner_sl and owner_tp (may be None)
        current_price: Current market price for the instrument

    Returns:
        "sl_hit": Stop loss level breached
        "tp_hit": Take profit level breached
        None: No breach detected

    Business Logic:
        BUY positions (side=0):
            - SL hit when price drops to or below owner_sl
            - TP hit when price rises to or above owner_tp

        SELL positions (side=1):
            - SL hit when price rises to or above owner_sl
            - TP hit when price drops to or below owner_tp

    Examples:
        >>> position = OpenPosition(
        ...     instrument="XAUUSD",
        ...     side=0,  # BUY
        ...     entry_price=2655.00,
        ...     owner_sl=2645.00,
        ...     owner_tp=2670.00,
        ... )
        >>> check_position_breach(position, 2643.00)
        "sl_hit"
        >>> check_position_breach(position, 2672.00)
        "tp_hit"
        >>> check_position_breach(position, 2660.00)
        None
    """
    # Skip if no owner levels set
    if position.owner_sl is None and position.owner_tp is None:
        return None

    if position.side == 0:  # BUY position
        # SL: Price drops to or below owner_sl
        if position.owner_sl is not None and current_price <= position.owner_sl:
            return "sl_hit"

        # TP: Price rises to or above owner_tp
        if position.owner_tp is not None and current_price >= position.owner_tp:
            return "tp_hit"

    else:  # SELL position (side == 1)
        # SL: Price rises to or above owner_sl
        if position.owner_sl is not None and current_price >= position.owner_sl:
            return "sl_hit"

        # TP: Price drops to or below owner_tp
        if position.owner_tp is not None and current_price <= position.owner_tp:
            return "tp_hit"

    return None


async def get_open_positions(
    db: AsyncSession, user_id: str | None = None
) -> list[OpenPosition]:
    """
    Retrieve all open positions for monitoring.

    Args:
        db: Database session
        user_id: Optional user filter (for user-specific monitoring)

    Returns:
        List of OpenPosition records with status=OPEN

    Notes:
        - Only returns positions with status=PositionStatus.OPEN
        - Ordered by opened_at descending (newest first)
        - Includes positions with NULL owner_sl/owner_tp (will be skipped in breach check)
    """
    query = select(OpenPosition).where(OpenPosition.status == PositionStatus.OPEN.value)

    if user_id is not None:
        query = query.where(OpenPosition.user_id == user_id)

    query = query.order_by(OpenPosition.opened_at.desc())

    result = await db.execute(query)
    return list(result.scalars().all())


async def get_position_by_id(db: AsyncSession, position_id: str) -> OpenPosition | None:
    """
    Retrieve a single position by ID.

    Args:
        db: Database session
        position_id: Position UUID

    Returns:
        OpenPosition if found, None otherwise
    """
    result = await db.execute(
        select(OpenPosition).where(OpenPosition.id == position_id)
    )
    return result.scalar_one_or_none()


async def close_position(
    db: AsyncSession,
    position: OpenPosition,
    close_price: float,
    reason: Literal["sl_hit", "tp_hit", "manual", "error"],
) -> OpenPosition:
    """
    Mark a position as closed in the database.

    Args:
        db: Database session
        position: OpenPosition to close
        close_price: Final close price
        reason: Reason for close

    Returns:
        Updated OpenPosition with closed status

    Notes:
        - Updates status based on reason
        - Sets closed_at timestamp
        - Sets close_price and close_reason
        - Commits to database
    """
    # Map reason to status
    status_map = {
        "sl_hit": PositionStatus.CLOSED_SL,
        "tp_hit": PositionStatus.CLOSED_TP,
        "manual": PositionStatus.CLOSED_MANUAL,
        "error": PositionStatus.CLOSED_ERROR,
    }

    position.status = status_map[reason].value
    position.closed_at = datetime.utcnow()
    position.close_price = close_price
    position.close_reason = reason

    await db.commit()
    await db.refresh(position)

    return position
