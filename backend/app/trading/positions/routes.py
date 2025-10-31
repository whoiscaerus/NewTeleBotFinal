"""Position API Routes - View open positions (owner SL/TP hidden from clients).

Provides REST API for viewing positions. The owner_sl and owner_tp fields
are NEVER included in responses to maintain anti-reselling security.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.db import get_db
from backend.app.trading.positions.monitor import get_open_positions, get_position_by_id
from backend.app.trading.schemas import PositionOut, PositionsListOut

router = APIRouter(prefix="/api/v1/positions", tags=["positions"])


@router.get("", response_model=PositionsListOut)
async def list_positions(
    user_id: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """
    List open positions for a user.

    Args:
        user_id: Optional user filter (None = all users, admin only)
        db: Database session

    Returns:
        PositionsListOut with list of positions

    Security:
        - owner_sl and owner_tp fields are NEVER included in response
        - Only publicly visible position details are returned
        - Hidden levels remain server-side for monitoring

    Example Response:
        {
            "positions": [
                {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "instrument": "XAUUSD",
                    "side": 0,
                    "entry_price": 2655.50,
                    "volume": 0.1,
                    "broker_ticket": "123456789",
                    "status": 0,
                    "opened_at": "2024-10-30T10:30:00Z"
                }
            ],
            "count": 1
        }

    Note: owner_sl and owner_tp are NOT in response - hidden for security
    """
    positions = await get_open_positions(db, user_id=user_id)

    # Convert to Pydantic models (automatically excludes owner_sl/owner_tp)
    position_outs = [PositionOut.from_orm(p) for p in positions]

    return PositionsListOut(positions=position_outs, count=len(position_outs))


@router.get("/{position_id}", response_model=PositionOut)
async def get_position(
    position_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Get details of a specific position.

    Args:
        position_id: Position UUID
        db: Database session

    Returns:
        PositionOut with position details (owner_sl/owner_tp excluded)

    Raises:
        HTTPException 404: Position not found

    Security:
        - owner_sl and owner_tp fields are NEVER included in response
        - Even if user owns the position, hidden levels stay server-side
        - Only the position monitor service accesses hidden levels

    Example Response:
        {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "instrument": "XAUUSD",
            "side": 0,
            "entry_price": 2655.50,
            "volume": 0.1,
            "broker_ticket": "123456789",
            "status": 0,
            "opened_at": "2024-10-30T10:30:00Z",
            "closed_at": null,
            "close_price": null,
            "close_reason": null
        }

    Note: owner_sl and owner_tp are NOT in response - server-only fields
    """
    position = await get_position_by_id(db, position_id)

    if position is None:
        raise HTTPException(status_code=404, detail="Position not found")

    # Convert to Pydantic model (automatically excludes owner_sl/owner_tp)
    return PositionOut.from_orm(position)
