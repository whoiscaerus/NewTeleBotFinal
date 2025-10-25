"""Trade store package exports.

Provides clean public API for trade persistence and management.

Example:
    >>> from backend.app.trading.store import TradeService, TradeOut, models
    >>> service = TradeService(db_session)
    >>> trade = await service.create_trade(...)
"""

from backend.app.trading.store.models import EquityPoint, Position, Trade, ValidationLog
from backend.app.trading.store.schemas import (
    DrawdownOut,
    EquityPointOut,
    PositionOut,
    PositionSummaryOut,
    SyncResultOut,
    TradeCloseRequest,
    TradeCreateRequest,
    TradeOut,
    TradeStatsOut,
)
from backend.app.trading.store.service import TradeService

__all__ = [
    # Models
    "Trade",
    "Position",
    "EquityPoint",
    "ValidationLog",
    # Service
    "TradeService",
    # Schemas
    "TradeOut",
    "TradeCreateRequest",
    "TradeCloseRequest",
    "PositionOut",
    "EquityPointOut",
    "TradeStatsOut",
    "DrawdownOut",
    "PositionSummaryOut",
    "SyncResultOut",
]
