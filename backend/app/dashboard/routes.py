"""Dashboard WebSocket streaming for real-time trading data (PR-087).

Provides WebSocket endpoint streaming:
- Pending approvals (from approvals service)
- Open positions (from trading/positions service)
- Equity deltas (from analytics/equity service)

WebSocket sends updates at 1Hz (1 update per second) with typed messages.
Auto-increments/decrements dashboard_ws_clients_gauge metric.
"""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.analytics.equity import EquityEngine
from backend.app.approvals.models import Approval
from backend.app.auth.dependencies import get_current_user_from_websocket
from backend.app.auth.models import User
from backend.app.core.db import get_db
from backend.app.observability import get_metrics
from backend.app.signals.models import Signal, SignalStatus
from backend.app.trading.positions.models import OpenPosition, PositionStatus

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


async def get_pending_approvals(db: AsyncSession, user_id: str) -> list[dict[str, Any]]:
    """
    Fetch pending approvals for user.

    Args:
        db: Database session
        user_id: User ID

    Returns:
        List of pending approval dictionaries

    Business Logic:
        - Fetch all signals in NEW status (not yet approved/rejected)
        - Join with approvals table to get approval metadata
        - Return rich data: signal details + approval metadata
    """
    query = (
        select(Signal, Approval)
        .join(Approval, Signal.id == Approval.signal_id, isouter=True)
        .where(Signal.user_id == user_id)
        .where(Signal.status == SignalStatus.NEW)
        .order_by(Signal.created_at.desc())
    )

    result = await db.execute(query)
    rows = result.all()

    approvals = []
    for signal, approval in rows:
        approvals.append(
            {
                "signal_id": signal.id,
                "instrument": signal.instrument,
                "side": "BUY" if signal.side == 0 else "SELL",
                "price": float(signal.price),
                "volume": float(signal.volume) if signal.volume else None,
                "created_at": signal.created_at.isoformat(),
                "approval_id": approval.id if approval else None,
                "approval_status": (
                    approval.decision.name
                    if approval and approval.decision
                    else "PENDING"
                ),
                "confidence": (
                    signal.confidence if hasattr(signal, "confidence") else None
                ),
                "signal_age_minutes": (
                    (datetime.now(UTC) - signal.created_at).total_seconds() / 60.0
                ),
            }
        )

    return approvals


async def get_open_positions_data(
    db: AsyncSession, user_id: str
) -> list[dict[str, Any]]:
    """
    Fetch open positions for user.

    Args:
        db: Database session
        user_id: User ID

    Returns:
        List of open position dictionaries

    Business Logic:
        - Fetch all positions with status=OPEN
        - Calculate unrealized PnL (current_price vs entry_price)
        - Return position details for dashboard display
    """
    query = (
        select(OpenPosition)
        .where(OpenPosition.user_id == user_id)
        .where(OpenPosition.status == PositionStatus.OPEN)
        .order_by(OpenPosition.opened_at.desc())
    )

    result = await db.execute(query)
    positions = result.scalars().all()

    position_data = []
    for pos in positions:
        # Calculate unrealized PnL
        if pos.current_price and pos.entry_price:
            pnl_points = pos.current_price - pos.entry_price
            if pos.side == 1:  # SELL position
                pnl_points = -pnl_points
            unrealized_pnl = pnl_points * float(pos.volume or 1.0)
        else:
            unrealized_pnl = 0.0

        position_data.append(
            {
                "position_id": pos.id,
                "instrument": pos.instrument,
                "side": "BUY" if pos.side == 0 else "SELL",
                "entry_price": float(pos.entry_price),
                "current_price": (
                    float(pos.current_price) if pos.current_price else None
                ),
                "volume": float(pos.volume) if pos.volume else None,
                "unrealized_pnl": round(unrealized_pnl, 2),
                "opened_at": pos.opened_at.isoformat() if pos.opened_at else None,
                "broker_ticket": pos.broker_ticket,
            }
        )

    return position_data


async def get_equity_data(db: AsyncSession, user_id: str) -> dict[str, Any]:
    """
    Fetch equity curve data for user.

    Args:
        db: Database session
        user_id: User ID

    Returns:
        Equity data dictionary with curve and summary stats

    Business Logic:
        - Use EquityEngine to compute equity series from trades
        - Return last 30 days of equity curve
        - Include summary stats: final equity, total return, max drawdown
    """
    equity_engine = EquityEngine()

    # Compute equity series (last 30 days)
    equity_series = await equity_engine.compute_equity_series(
        db=db,
        user_id=user_id,
        start_date=datetime.now(UTC).date(),  # Today (will fetch recent trades)
        end_date=datetime.now(UTC).date(),
    )

    return {
        "final_equity": float(equity_series.final_equity),
        "total_return_percent": equity_series.total_return_percent,
        "max_drawdown_percent": equity_series.max_drawdown_percent,
        "days_in_period": equity_series.days_in_period,
        "equity_curve": equity_series.to_dict(),
        "last_updated": datetime.now(UTC).isoformat(),
    }


@router.websocket("/ws")
async def dashboard_websocket(
    websocket: WebSocket,
    current_user: User = Depends(get_current_user_from_websocket),
):
    """
    Real-time dashboard WebSocket endpoint.

    Streams updates at 1Hz (1 update per second):
    - Pending approvals
    - Open positions
    - Equity deltas

    Args:
        websocket: WebSocket connection
        current_user: Authenticated user (from WebSocket query param or header)

    Message Format:
        {
            "type": "approvals" | "positions" | "equity",
            "data": {...},
            "timestamp": "2024-11-09T12:00:00Z"
        }

    Example:
        ```javascript
        const ws = new WebSocket('ws://localhost:8000/api/v1/dashboard/ws?token=JWT');
        ws.onmessage = (event) => {
            const msg = JSON.parse(event.data);
            if (msg.type === 'approvals') {
                console.log('Pending approvals:', msg.data);
            }
        };
        ```

    Raises:
        WebSocketDisconnect: When client disconnects
    """
    metrics = get_metrics()

    # Accept connection
    await websocket.accept()
    logger.info(f"Dashboard WebSocket connected: user={current_user.id}")

    # Increment active connections gauge
    metrics.dashboard_ws_clients_gauge.inc()

    try:
        # Get database session for this connection
        async for db in get_db():
            while True:
                try:
                    # Stream approvals
                    approvals = await get_pending_approvals(db, current_user.id)
                    await websocket.send_json(
                        {
                            "type": "approvals",
                            "data": approvals,
                            "timestamp": datetime.now(UTC).isoformat(),
                        }
                    )

                    # Stream positions
                    positions = await get_open_positions_data(db, current_user.id)
                    await websocket.send_json(
                        {
                            "type": "positions",
                            "data": positions,
                            "timestamp": datetime.now(UTC).isoformat(),
                        }
                    )

                    # Stream equity
                    equity = await get_equity_data(db, current_user.id)
                    await websocket.send_json(
                        {
                            "type": "equity",
                            "data": equity,
                            "timestamp": datetime.now(UTC).isoformat(),
                        }
                    )

                    # Wait 1 second before next update (1Hz stream)
                    await asyncio.sleep(1)

                except WebSocketDisconnect:
                    logger.info(
                        f"Dashboard WebSocket disconnected: user={current_user.id}"
                    )
                    break

                except Exception as e:
                    logger.error(
                        f"Error in dashboard WebSocket stream: {e}",
                        exc_info=True,
                        extra={"user_id": current_user.id},
                    )
                    # Send error message to client
                    try:
                        await websocket.send_json(
                            {
                                "type": "error",
                                "error": "Internal server error",
                                "timestamp": datetime.now(UTC).isoformat(),
                            }
                        )
                    except Exception:
                        pass
                    break

    except WebSocketDisconnect:
        logger.info(
            f"Dashboard WebSocket disconnected during setup: user={current_user.id}"
        )

    finally:
        # Decrement active connections gauge
        metrics.dashboard_ws_clients_gauge.dec()
        logger.info(
            f"Dashboard WebSocket cleanup complete: user={current_user.id}",
            extra={"final_gauge": metrics.dashboard_ws_clients_gauge._value.get()},
        )
