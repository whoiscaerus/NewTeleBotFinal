"""Pydantic models for trade store API responses and validation."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class TradeOut(BaseModel):
    """Trade response model for API endpoints.

    Example:
        {
            "trade_id": "550e8400-e29b-41d4-a716-446655440000",
            "symbol": "GOLD",
            "trade_type": "BUY",
            "entry_price": "1950.50",
            "entry_time": "2024-10-24T10:30:00Z",
            "exit_price": "1955.50",
            "exit_time": "2024-10-24T12:00:00Z",
            "stop_loss": "1945.00",
            "take_profit": "1960.00",
            "volume": "0.1",
            "profit": "51.00",
            "status": "CLOSED"
        }
    """

    trade_id: str = Field(..., description="Unique trade identifier")
    symbol: str = Field(..., description="Trading symbol (GOLD, EURUSD, etc.)")
    trade_type: str = Field(..., description="BUY or SELL")
    entry_price: Decimal = Field(..., description="Entry level")
    entry_time: datetime = Field(..., description="Entry timestamp")
    entry_comment: str | None = Field(None, description="Entry comment")
    exit_price: Decimal | None = Field(None, description="Exit level")
    exit_time: datetime | None = Field(None, description="Exit timestamp")
    exit_reason: str | None = Field(None, description="Reason for exit")
    stop_loss: Decimal = Field(..., description="Stop loss level")
    take_profit: Decimal = Field(..., description="Take profit level")
    volume: Decimal = Field(..., description="Position size in lots")
    profit: Decimal | None = Field(None, description="Realized profit/loss in GBP")
    pips: Decimal | None = Field(None, description="Pips gained/lost")
    duration_hours: float | None = Field(None, description="Trade duration in hours")
    risk_reward_ratio: Decimal | None = Field(None, description="Risk to reward ratio")
    strategy: str = Field(..., description="Strategy name")
    timeframe: str = Field(..., description="Candle timeframe")
    status: str = Field(..., description="OPEN, CLOSED, or CANCELLED")
    signal_id: str | None = Field(None, description="Reference to signal PR-015")
    device_id: str | None = Field(None, description="Device that created trade")
    setup_id: str | None = Field(None, description="Setup identifier")
    created_at: datetime = Field(..., description="Record creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    model_config = ConfigDict(from_attributes=True)


class PositionOut(BaseModel):
    """Open position response model.

    Example:
        {
            "position_id": "550e8400-e29b-41d4-a716-446655440001",
            "symbol": "GOLD",
            "direction": "BUY",
            "volume": "0.1",
            "entry_price": "1950.50",
            "current_price": "1952.00",
            "unrealized_profit": "15.00",
            "duration_hours": 2.5
        }
    """

    position_id: str = Field(..., description="Unique position identifier")
    symbol: str = Field(..., description="Trading symbol")
    direction: str = Field(..., description="BUY or SELL")
    volume: Decimal = Field(..., description="Position size")
    entry_price: Decimal = Field(..., description="Entry level")
    current_price: Decimal = Field(..., description="Current price")
    stop_loss: Decimal = Field(..., description="Stop loss level")
    take_profit: Decimal = Field(..., description="Take profit level")
    unrealized_profit: Decimal | None = Field(None, description="Unrealized P&L")
    duration_hours: float = Field(..., description="Hours position open")
    opened_at: datetime = Field(..., description="Position open timestamp")
    trade_ids: list[str] = Field(default_factory=list, description="Related trade IDs")

    model_config = ConfigDict(from_attributes=True)


class EquityPointOut(BaseModel):
    """Equity curve point response model.

    Example:
        {
            "point_id": "550e8400-e29b-41d4-a716-446655440002",
            "equity": "10500.00",
            "timestamp": "2024-10-24T10:30:00Z",
            "trade_count": 5,
            "closed_trade_count": 3
        }
    """

    point_id: str = Field(..., description="Unique point identifier")
    equity: Decimal = Field(..., description="Account equity")
    balance: Decimal = Field(..., description="Account balance")
    margin_used: Decimal = Field(..., description="Used margin")
    margin_available: Decimal = Field(..., description="Available margin")
    timestamp: datetime = Field(..., description="Snapshot timestamp")
    trade_count: int = Field(..., description="Total open trades")
    closed_trade_count: int = Field(..., description="Total closed trades")

    model_config = ConfigDict(from_attributes=True)


class TradeStatsOut(BaseModel):
    """Trade statistics response model.

    Example:
        {
            "total_trades": 25,
            "win_rate": 0.64,
            "profit_factor": 2.15,
            "avg_profit": "150.00",
            "avg_loss": "-70.00",
            "largest_win": "500.00",
            "largest_loss": "-200.00",
            "total_profit": "3250.00"
        }
    """

    total_trades: int = Field(..., description="Total closed trades")
    win_rate: float = Field(..., description="Percentage of winning trades (0-1)")
    profit_factor: float = Field(..., description="Total profit / total loss ratio")
    avg_profit: Decimal = Field(..., description="Average profit per winning trade")
    avg_loss: Decimal = Field(..., description="Average loss per losing trade")
    largest_win: Decimal = Field(..., description="Largest single profit")
    largest_loss: Decimal = Field(..., description="Largest single loss")
    total_profit: Decimal = Field(..., description="Total profit/loss")
    symbol: str | None = Field(None, description="Filtered by symbol if provided")

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "properties": {
                "avg_profit": {"type": "string"},
                "avg_loss": {"type": "string"},
                "largest_win": {"type": "string"},
                "largest_loss": {"type": "string"},
                "total_profit": {"type": "string"},
            }
        },
    )


class DrawdownOut(BaseModel):
    """Drawdown peak/trough response model.

    Example:
        {
            "peak_time": "2024-10-20T10:00:00Z",
            "peak_equity": "11000.00",
            "trough_time": "2024-10-21T14:00:00Z",
            "trough_equity": "10200.00",
            "drawdown_pct": 7.27,
            "recovery_time": "2024-10-22T09:00:00Z"
        }
    """

    peak_time: datetime = Field(..., description="Time of peak equity")
    peak_equity: Decimal = Field(..., description="Peak equity value")
    trough_time: datetime = Field(..., description="Time of trough")
    trough_equity: Decimal = Field(..., description="Trough equity value")
    drawdown_pct: float = Field(..., description="Drawdown percentage")
    recovery_time: datetime | None = Field(
        None, description="Recovery time if applicable"
    )

    model_config = ConfigDict(from_attributes=True)


class PositionSummaryOut(BaseModel):
    """Summary of all open positions.

    Example:
        {
            "total_positions": 3,
            "total_volume": "0.3",
            "total_unrealized_profit": "45.50",
            "by_symbol": {
                "GOLD": {
                    "count": 2,
                    "volume": "0.2",
                    "profit": "30.00"
                },
                "EURUSD": {
                    "count": 1,
                    "volume": "0.1",
                    "profit": "15.50"
                }
            }
        }
    """

    total_positions: int = Field(..., description="Total open positions")
    total_volume: Decimal = Field(..., description="Combined volume")
    total_unrealized_profit: Decimal = Field(..., description="Total unrealized P&L")
    by_symbol: dict[str, dict] = Field(..., description="Positions grouped by symbol")

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "properties": {
                "total_volume": {"type": "string"},
                "total_unrealized_profit": {"type": "string"},
            }
        },
    )


class SyncResultOut(BaseModel):
    """MT5 synchronization result response model.

    Example:
        {
            "synced": 15,
            "mismatches": 2,
            "orphaned": 1,
            "mismatch_details": [
                {
                    "trade_id": "550e8400-e29b-41d4-a716-446655440000",
                    "issue": "volume_mismatch",
                    "our_volume": "0.1",
                    "mt5_volume": 0.15
                }
            ],
            "actions": []
        }
    """

    synced: int = Field(..., description="Number of synced positions")
    mismatches: int = Field(..., description="Number of mismatches found")
    orphaned: int = Field(..., description="Number of orphaned trades")
    mismatch_details: list[dict] = Field(..., description="Details of each mismatch")
    actions: list[dict] = Field(..., description="Recommended actions")

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "properties": {
                "mismatch_details": {
                    "items": {
                        "properties": {
                            "our_volume": {"type": "string"},
                        }
                    }
                }
            }
        },
    )


class TradeCreateRequest(BaseModel):
    """Request model for creating a trade.

    Example:
        {
            "symbol": "GOLD",
            "trade_type": "BUY",
            "entry_price": "1950.50",
            "stop_loss": "1945.00",
            "take_profit": "1960.00",
            "volume": "0.1",
            "strategy": "scalp_5m",
            "timeframe": "M5"
        }
    """

    symbol: str = Field(..., min_length=2, max_length=20, description="Trading symbol")
    trade_type: str = Field(..., pattern="^(BUY|SELL)$", description="BUY or SELL")
    entry_price: Decimal = Field(..., gt=0, description="Entry level")
    stop_loss: Decimal = Field(..., gt=0, description="Stop loss level")
    take_profit: Decimal = Field(..., gt=0, description="Take profit level")
    volume: Decimal = Field(..., ge=0.01, le=100.0, description="Position size")
    strategy: str = Field("manual", description="Strategy name")
    timeframe: str = Field("H1", description="Candle timeframe")
    signal_id: str | None = Field(None, description="Reference to signal")
    device_id: str | None = Field(None, description="Device creating trade")
    entry_comment: str | None = Field(None, max_length=500, description="Entry comment")


class TradeCloseRequest(BaseModel):
    """Request model for closing a trade.

    Example:
        {
            "trade_id": "550e8400-e29b-41d4-a716-446655440000",
            "exit_price": "1955.50",
            "exit_reason": "TP_HIT"
        }
    """

    trade_id: str = Field(..., description="Trade ID to close")
    exit_price: Decimal = Field(..., gt=0, description="Exit level")
    exit_reason: str = Field("MANUAL_CLOSE", description="Reason for exit")
