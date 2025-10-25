"""Order parameter schemas for trade submission."""

from datetime import datetime
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field, validator


class OrderType(str, Enum):
    """Order types for pending orders."""

    PENDING_BUY = "PENDING_BUY"
    PENDING_SELL = "PENDING_SELL"


class OrderParams(BaseModel):
    """
    Complete order parameters for broker submission.

    Represents a fully-constructed trade order with all constraints
    validated and applied. Includes risk/reward calculations and
    expiry timing for terminal consumption.

    Example:
        >>> order = OrderParams(
        ...     order_id="oid-123",
        ...     signal_id="sig-456",
        ...     symbol="GOLD",
        ...     order_type=OrderType.PENDING_BUY,
        ...     volume=0.1,
        ...     entry_price=1950.50,
        ...     stop_loss=1945.00,
        ...     take_profit=1960.00,
        ...     expiry_time=datetime(2025, 10, 25, 15, 30, 0),
        ...     risk_amount=5.50,
        ...     reward_amount=9.50,
        ...     risk_reward_ratio=1.73,
        ...     min_stop_distance_pips=5
        ... )
    """

    # IDs and Symbols
    order_id: str = Field(
        default_factory=lambda: str(uuid4()), description="Unique order ID"
    )
    signal_id: str = Field(..., description="Originating signal ID")
    symbol: str = Field(..., description="Trading symbol (e.g., GOLD, XAUUSD)")

    # Order Details
    order_type: OrderType = Field(..., description="PENDING_BUY or PENDING_SELL")
    volume: float = Field(..., gt=0, description="Position size in lots")

    # Price Levels
    entry_price: float = Field(..., gt=0, description="Entry level")
    stop_loss: float = Field(..., gt=0, description="Stop loss level")
    take_profit: float = Field(..., gt=0, description="Take profit level")

    # Timing
    expiry_time: datetime = Field(..., description="Order expiry (NOW + hours)")
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Creation timestamp"
    )

    # Risk/Reward
    risk_amount: float = Field(
        ..., ge=0, description="Risk in points (SL - Entry for SELL)"
    )
    reward_amount: float = Field(
        ..., gt=0, description="Reward in points (TP - Entry magnitude)"
    )
    risk_reward_ratio: float = Field(..., ge=1.0, description="Reward / Risk ratio")

    # Constraints
    min_stop_distance_pips: int = Field(
        default=5, ge=1, description="Broker minimum SL distance"
    )

    # Metadata
    strategy_name: str = Field(
        default="fib_rsi", description="Strategy that generated signal"
    )

    # Validation
    class Config:
        use_enum_values = True
        json_schema_extra = {
            "example": {
                "order_id": "oid-123abc",
                "signal_id": "sig-456def",
                "symbol": "GOLD",
                "order_type": "PENDING_BUY",
                "volume": 0.1,
                "entry_price": 1950.50,
                "stop_loss": 1945.00,
                "take_profit": 1960.00,
                "expiry_time": "2025-10-25T15:30:00Z",
                "risk_amount": 5.50,
                "reward_amount": 9.50,
                "risk_reward_ratio": 1.73,
                "min_stop_distance_pips": 5,
                "strategy_name": "fib_rsi",
                "created_at": "2025-10-24T12:00:00Z",
            }
        }

    @validator("symbol")
    def validate_symbol(cls, v: str) -> str:
        """Validate symbol is known."""
        valid_symbols = {"GOLD", "XAUUSD"}
        if v.upper() not in valid_symbols:
            raise ValueError(f"Unknown symbol: {v}. Valid: {valid_symbols}")
        return v.upper()

    @validator("order_type")
    def validate_order_type(cls, v):
        """Validate order type is valid."""
        if isinstance(v, str):
            if v not in [OrderType.PENDING_BUY.value, OrderType.PENDING_SELL.value]:
                raise ValueError(f"Invalid order type: {v}")
        return v

    @validator("risk_reward_ratio")
    def validate_rr_ratio(cls, v: float) -> float:
        """Validate R:R ratio is at least 1.0."""
        if v < 1.0:
            raise ValueError(
                f"R:R ratio too low: {v:.2f}. Minimum: 1.0. "
                f"Adjust entry or TP to improve ratio."
            )
        return v

    @validator("entry_price", "stop_loss", "take_profit", pre=True)
    def validate_positive_prices(cls, v: float) -> float:
        """Validate prices are positive."""
        if v is not None and v <= 0:
            raise ValueError(f"Prices must be positive: {v}")
        return v

    @validator("take_profit", always=True)
    def validate_tp_vs_sl(cls, v: float, values: dict) -> float:
        """Validate TP and SL are not the same."""
        if "stop_loss" in values and v == values["stop_loss"]:
            raise ValueError("Take profit and stop loss cannot be the same price")
        return v

    @validator("volume")
    def validate_volume(cls, v: float) -> float:
        """Validate volume is reasonable."""
        if v <= 0:
            raise ValueError(f"Volume must be positive: {v}")
        if v > 100:
            raise ValueError(f"Volume too large: {v} (max 100)")
        return round(v, 2)

    @validator("expiry_time")
    def validate_expiry_future(cls, v: datetime, values: dict) -> datetime:
        """Validate expiry is in future."""
        if "created_at" in values:
            created = values["created_at"]
            if v <= created:
                raise ValueError(
                    f"Expiry time must be after creation: {v} <= {created}"
                )
        return v

    def calculate_risk(self) -> float:
        """Calculate actual risk (SL distance)."""
        return abs(self.entry_price - self.stop_loss)

    def calculate_reward(self) -> float:
        """Calculate actual reward (TP distance)."""
        return abs(self.take_profit - self.entry_price)

    def is_buy_order(self) -> bool:
        """Check if this is a buy order."""
        return (
            self.order_type == OrderType.PENDING_BUY or self.order_type == "PENDING_BUY"
        )

    def is_sell_order(self) -> bool:
        """Check if this is a sell order."""
        return (
            self.order_type == OrderType.PENDING_SELL
            or self.order_type == "PENDING_SELL"
        )


class BrokerConstraints(BaseModel):
    """
    Broker-specific trading constraints.

    Defines minimum/maximum distances, tick sizes, and other
    constraints for a specific symbol.

    Example:
        >>> constraints = BrokerConstraints(
        ...     symbol="GOLD",
        ...     tick_size=0.01,
        ...     min_stop_distance_pips=5,
        ...     min_tp_distance_pips=5,
        ...     max_stop_distance_pips=200,
        ...     point_value=10
        ... )
    """

    symbol: str = Field(..., description="Trading symbol")
    tick_size: float = Field(default=0.01, description="Minimum price increment")
    min_stop_distance_pips: int = Field(
        default=5, description="Minimum SL distance in points"
    )
    min_tp_distance_pips: int = Field(
        default=5, description="Minimum TP distance in points"
    )
    max_stop_distance_pips: int = Field(
        default=200, description="Maximum SL distance in points"
    )
    point_value: float = Field(default=10, description="Value per point")

    @validator("symbol")
    def validate_symbol(cls, v: str) -> str:
        """Validate symbol."""
        if v.upper() not in {"GOLD", "XAUUSD"}:
            raise ValueError(f"Unknown symbol: {v}")
        return v.upper()

    def round_price(self, price: float, direction: str = "nearest") -> float:
        """
        Round price to tick size.

        Args:
            price: Price to round
            direction: "up", "down", or "nearest"

        Returns:
            Rounded price
        """
        if direction == "up":
            import math

            return math.ceil(price / self.tick_size) * self.tick_size
        elif direction == "down":
            import math

            return math.floor(price / self.tick_size) * self.tick_size
        else:  # nearest
            return round(price / self.tick_size) * self.tick_size

    def distance_in_pips(self, price1: float, price2: float) -> float:
        """Calculate distance between two prices in points."""
        return abs(price1 - price2) / self.tick_size


# Predefined broker constraints for known symbols
DEFAULT_CONSTRAINTS = {
    "GOLD": BrokerConstraints(
        symbol="GOLD",
        tick_size=0.01,
        min_stop_distance_pips=5,
        min_tp_distance_pips=5,
        max_stop_distance_pips=200,
        point_value=10,
    ),
    "XAUUSD": BrokerConstraints(
        symbol="XAUUSD",
        tick_size=0.01,
        min_stop_distance_pips=5,
        min_tp_distance_pips=5,
        max_stop_distance_pips=200,
        point_value=10,
    ),
}


def get_constraints(symbol: str) -> BrokerConstraints:
    """Get broker constraints for a symbol."""
    symbol_upper = symbol.upper()
    if symbol_upper not in DEFAULT_CONSTRAINTS:
        raise ValueError(f"No constraints defined for symbol: {symbol}")
    return DEFAULT_CONSTRAINTS[symbol_upper]
