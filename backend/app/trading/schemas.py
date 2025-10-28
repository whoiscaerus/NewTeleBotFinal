"""
Phase 5 Request/Response Schemas

Pydantic v2 models for REST API endpoints:
- ReconciliationStatusRequest/Response
- PositionsListRequest/Response
- GuardsStatusRequest/Response

Author: Trading System
Date: 2024-10-26
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

# ================================================================
# Enums
# ================================================================


class EventType(str, Enum):
    """Reconciliation event types."""

    POSITION_SYNCED = "position_synced"
    POSITION_MATCHED = "position_matched"
    DIVERGENCE_DETECTED = "divergence_detected"
    POSITION_CLOSED = "position_closed"
    DRAWDOWN_ALERT = "drawdown_alert"
    MARKET_CONDITION_ALERT = "market_condition_alert"


class DivergenceReason(str, Enum):
    """Reasons for position divergence."""

    ENTRY_SLIPPAGE = "entry_slippage"
    VOLUME_MISMATCH = "volume_mismatch"
    TP_MISMATCH = "tp_mismatch"
    SL_MISMATCH = "sl_mismatch"
    PARTIAL_FILL = "partial_fill"
    BROKER_CLOSED = "broker_closed"
    UNKNOWN = "unknown"


class AlertType(str, Enum):
    """Guard alert types."""

    NORMAL = "normal"
    WARNING = "warning"
    CRITICAL = "critical"


class ConditionType(str, Enum):
    """Market condition alert types."""

    PRICE_GAP = "price_gap"
    LIQUIDITY_CRISIS = "liquidity_crisis"


class PositionStatus(str, Enum):
    """Position status."""

    OPEN = "open"
    CLOSED = "closed"
    PENDING = "pending"


# ================================================================
# Reconciliation Models
# ================================================================


class ReconciliationEventOut(BaseModel):
    """Single reconciliation event."""

    event_id: str = Field(..., description="Unique event ID")
    event_type: EventType = Field(..., description="Type of reconciliation event")
    user_id: str = Field(..., description="User ID")
    created_at: datetime = Field(..., description="Event timestamp (UTC)")
    divergence_reason: DivergenceReason | None = Field(
        None, description="If divergence detected, reason why"
    )
    description: str = Field(..., description="Human-readable description")
    metadata: dict = Field(default_factory=dict, description="Additional context")

    class Config:
        json_schema_extra = {
            "example": {
                "event_id": "evt_abc123",
                "event_type": "position_matched",
                "user_id": "user_456",
                "created_at": "2024-10-26T19:55:37Z",
                "divergence_reason": None,
                "description": "Position XAUUSD matched with bot trade (0.1 lot)",
                "metadata": {"bot_ticket": 12345, "broker_ticket": 54321},
            }
        }


class ReconciliationStatusOut(BaseModel):
    """Reconciliation sync status."""

    user_id: str = Field(..., description="User ID")
    status: str = Field(
        ..., description="Overall sync status (healthy, degraded, error)"
    )
    last_sync_at: datetime | None = Field(
        None, description="Last successful sync timestamp"
    )
    total_syncs: int = Field(..., ge=0, description="Total sync attempts")
    last_sync_duration_ms: int | None = Field(
        None, ge=0, description="Duration of last sync (ms)"
    )
    open_positions_count: int = Field(..., ge=0, description="Number of open positions")
    matched_positions: int = Field(
        ..., ge=0, description="Positions matched with bot trades"
    )
    divergences_detected: int = Field(
        ..., ge=0, description="Positions with detected divergence"
    )
    recent_events: list[ReconciliationEventOut] = Field(
        default_factory=list, description="Last 10 events"
    )
    error_message: str | None = Field(
        None, description="Error description if status=error"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "user_456",
                "status": "healthy",
                "last_sync_at": "2024-10-26T19:55:37Z",
                "total_syncs": 850,
                "last_sync_duration_ms": 245,
                "open_positions_count": 3,
                "matched_positions": 3,
                "divergences_detected": 0,
                "recent_events": [],
                "error_message": None,
            }
        }


# ================================================================
# Position Models
# ================================================================


class PositionOut(BaseModel):
    """Single open position."""

    position_id: str = Field(..., description="Bot database position ID")
    ticket: int = Field(..., description="MT5 ticket number")
    symbol: str = Field(..., description="Trading symbol (e.g., XAUUSD)")
    direction: str = Field(
        ..., pattern="^(buy|sell)$", description="Position direction"
    )
    volume: float = Field(..., gt=0, description="Position size (lots)")
    entry_price: float = Field(..., gt=0, description="Entry price")
    entry_time: datetime = Field(..., description="Entry time (UTC)")
    current_price: float = Field(..., gt=0, description="Current market price")
    unrealized_pnl: float = Field(..., description="Unrealized P&L (GBP)")
    unrealized_pnl_pct: float = Field(..., description="Unrealized P&L (percent)")
    take_profit: float | None = Field(None, gt=0, description="Take profit price")
    stop_loss: float | None = Field(None, gt=0, description="Stop loss price")
    status: PositionStatus = Field(..., description="Position status")
    matched_with_bot: bool = Field(..., description="True if matched with bot signal")
    last_updated_at: datetime = Field(..., description="Last price update timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "position_id": "pos_123",
                "ticket": 12345,
                "symbol": "XAUUSD",
                "direction": "buy",
                "volume": 0.1,
                "entry_price": 1950.50,
                "entry_time": "2024-10-26T18:00:00Z",
                "current_price": 1955.75,
                "unrealized_pnl": 52.50,
                "unrealized_pnl_pct": 0.27,
                "take_profit": 1960.00,
                "stop_loss": 1945.00,
                "status": "open",
                "matched_with_bot": True,
                "last_updated_at": "2024-10-26T19:55:37Z",
            }
        }


class PositionsListOut(BaseModel):
    """List of open positions."""

    user_id: str = Field(..., description="User ID")
    total_positions: int = Field(..., ge=0, description="Total open positions")
    total_unrealized_pnl: float = Field(
        ..., description="Sum of all unrealized P&L (GBP)"
    )
    total_unrealized_pnl_pct: float = Field(
        ..., description="Total P&L as percentage of account equity"
    )
    positions: list[PositionOut] = Field(
        default_factory=list, description="List of positions"
    )
    last_updated_at: datetime = Field(..., description="Last update timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "user_456",
                "total_positions": 2,
                "total_unrealized_pnl": 125.50,
                "total_unrealized_pnl_pct": 0.63,
                "positions": [],
                "last_updated_at": "2024-10-26T19:55:37Z",
            }
        }


# ================================================================
# Guard Models
# ================================================================


class DrawdownAlertOut(BaseModel):
    """Drawdown guard alert."""

    user_id: str = Field(..., description="User ID")
    current_equity: float = Field(..., gt=0, description="Current account equity (GBP)")
    peak_equity: float = Field(..., gt=0, description="Peak equity on record (GBP)")
    current_drawdown_pct: float = Field(
        ..., ge=0, le=100, description="Current drawdown percentage"
    )
    alert_type: AlertType = Field(
        ..., description="Alert severity (normal/warning/critical)"
    )
    alert_threshold_pct: float = Field(
        ..., ge=0, le=100, description="Threshold that triggered alert"
    )
    should_close_all: bool = Field(..., description="True if auto-close should trigger")
    time_to_liquidation_seconds: int | None = Field(
        None, ge=0, description="Seconds before forced close (if critical)"
    )
    last_checked_at: datetime = Field(..., description="Last check timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "user_456",
                "current_equity": 8000.00,
                "peak_equity": 10000.00,
                "current_drawdown_pct": 20.0,
                "alert_type": "critical",
                "alert_threshold_pct": 20.0,
                "should_close_all": True,
                "time_to_liquidation_seconds": 10,
                "last_checked_at": "2024-10-26T19:55:37Z",
            }
        }


class MarketConditionAlertOut(BaseModel):
    """Market condition guard alert."""

    symbol: str = Field(..., description="Trading symbol")
    condition_type: ConditionType = Field(..., description="Type of condition detected")
    alert_type: AlertType = Field(..., description="Alert severity")
    price_gap_pct: float | None = Field(
        None, ge=0, description="Price gap percentage (if applicable)"
    )
    bid_ask_spread_pct: float | None = Field(
        None, ge=0, description="Bid-ask spread percentage (if applicable)"
    )
    open_price: float | None = Field(None, gt=0, description="Open price")
    close_price: float | None = Field(None, gt=0, description="Close/current price")
    bid: float | None = Field(None, gt=0, description="Current bid price")
    ask: float | None = Field(None, gt=0, description="Current ask price")
    should_close_positions: bool = Field(
        ..., description="True if positions should close"
    )
    detected_at: datetime = Field(..., description="Detection timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "symbol": "XAUUSD",
                "condition_type": "price_gap",
                "alert_type": "warning",
                "price_gap_pct": 5.5,
                "bid_ask_spread_pct": None,
                "open_price": 1950.00,
                "close_price": 2053.75,
                "bid": None,
                "ask": None,
                "should_close_positions": True,
                "detected_at": "2024-10-26T19:55:37Z",
            }
        }


class GuardsStatusOut(BaseModel):
    """Combined guard status."""

    user_id: str = Field(..., description="User ID")
    system_status: str = Field(
        ..., description="Overall guard status (healthy/degraded/error)"
    )
    drawdown_guard: DrawdownAlertOut = Field(
        ..., description="Drawdown guard alert state"
    )
    market_guard_alerts: list[MarketConditionAlertOut] = Field(
        default_factory=list, description="Market condition alerts by symbol"
    )
    any_positions_should_close: bool = Field(
        ..., description="True if any guard recommends closing positions"
    )
    last_evaluated_at: datetime = Field(..., description="Last evaluation timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "user_456",
                "system_status": "healthy",
                "drawdown_guard": {},
                "market_guard_alerts": [],
                "any_positions_should_close": False,
                "last_evaluated_at": "2024-10-26T19:55:37Z",
            }
        }


# ================================================================
# Error Models
# ================================================================


class ErrorDetail(BaseModel):
    """Error detail structure."""

    code: str = Field(..., description="Error code (e.g., 'POSITION_NOT_FOUND')")
    message: str = Field(..., description="Error message")
    detail: str | None = Field(None, description="Additional detail")

    class Config:
        json_schema_extra = {
            "example": {
                "code": "POSITION_NOT_FOUND",
                "message": "Position not found",
                "detail": "Position ID 'pos_999' does not exist",
            }
        }


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: ErrorDetail = Field(..., description="Error information")
    request_id: str = Field(..., description="Request ID for tracing")
    timestamp: datetime = Field(..., description="Error timestamp (UTC)")

    class Config:
        json_schema_extra = {
            "example": {
                "error": {
                    "code": "INVALID_INPUT",
                    "message": "Invalid request parameters",
                    "detail": "user_id must be non-empty",
                },
                "request_id": "req_abc123",
                "timestamp": "2024-10-26T19:55:37Z",
            }
        }
