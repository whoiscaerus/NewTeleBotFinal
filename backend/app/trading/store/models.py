"""Trade store models for Postgres-backed trade persistence."""

from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.db import Base


class Trade(Base):
    """Represents a completed or open trade in the system.

    Stores all trade details including entry/exit prices, P&L calculations,
    and metadata for analytics and reconciliation.

    Attributes:
        trade_id: Unique identifier (UUID)
        signal_id: Reference to originating signal
        device_id: Reference to device that executed trade (if applicable)
        symbol: Trading symbol (GOLD, EURUSD, etc.)
        strategy: Strategy name (fib_rsi, channel, etc.)
        timeframe: Candle timeframe (H1, H15, M15, etc.)
        setup_id: Original setup identifier
        trade_type: BUY or SELL
        direction: 0=BUY, 1=SELL (legacy compatibility)
        entry_price: Entry level
        entry_time: Entry timestamp (UTC)
        entry_comment: Reason for entry
        exit_price: Exit level (None if open)
        exit_time: Exit timestamp (None if open)
        exit_reason: Reason for exit (TP_HIT, SL_HIT, MANUAL_CLOSE, etc.)
        stop_loss: Stop loss level
        take_profit: Take profit level
        volume: Position size in lots
        profit: P&L in account currency (None if open)
        pips: Profit in pips (None if open)
        risk_reward_ratio: Actual R:R ratio (None if open)
        percent_equity_return: % of equity risked
        status: OPEN, CLOSED, or CANCELLED
        duration_hours: How long trade was open
        created_at: Record creation timestamp (UTC)
        updated_at: Last modification timestamp (UTC)

    Constraints:
        - For BUY: stop_loss < entry_price < take_profit
        - For SELL: take_profit < entry_price < stop_loss
        - volume: 0.01 to 100.0
        - Status transitions: OPEN → CLOSED/CANCELLED only
    """

    __tablename__ = "trades"

    # Primary Key
    trade_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )

    # Foreign Keys
    user_id: Mapped[str] = mapped_column(
        String(36), nullable=False, index=True, doc="User who owns this trade"
    )
    signal_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    device_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    # Trade Metadata
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    strategy: Mapped[str] = mapped_column(String(50), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)
    setup_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # Trade Direction & Type
    trade_type: Mapped[str] = mapped_column(String(10), nullable=False)  # BUY, SELL
    direction: Mapped[int] = mapped_column(nullable=False)  # 0=BUY, 1=SELL

    # Entry Details
    entry_price: Mapped[Decimal] = mapped_column(nullable=False)
    entry_time: Mapped[datetime] = mapped_column(nullable=False)
    entry_comment: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Exit Details
    exit_price: Mapped[Decimal | None] = mapped_column(nullable=True)
    exit_time: Mapped[datetime | None] = mapped_column(nullable=True)
    exit_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Risk Management
    stop_loss: Mapped[Decimal] = mapped_column(nullable=False)
    take_profit: Mapped[Decimal] = mapped_column(nullable=False)
    volume: Mapped[Decimal] = mapped_column(nullable=False)

    # Performance Metrics
    profit: Mapped[Decimal | None] = mapped_column(nullable=True)
    pips: Mapped[Decimal | None] = mapped_column(nullable=True)
    risk_reward_ratio: Mapped[Decimal | None] = mapped_column(nullable=True)
    percent_equity_return: Mapped[Decimal | None] = mapped_column(nullable=True)

    # Trade State
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="OPEN"
    )  # OPEN, CLOSED, CANCELLED

    # Duration
    duration_hours: Mapped[float | None] = mapped_column(nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Indexes for common queries
    __table_args__ = (
        Index("ix_trades_symbol_time", "symbol", "entry_time"),
        Index("ix_trades_status_created", "status", "created_at"),
        Index("ix_trades_strategy_symbol", "strategy", "symbol"),
    )

    def __repr__(self) -> str:
        """String representation of trade."""
        status_str = f" → {self.exit_price}" if self.exit_price else " (OPEN)"
        return f"<Trade {self.trade_id}: {self.symbol} {self.trade_type} {self.entry_price}{status_str}>"


class Position(Base):
    """Represents a currently open position.

    Tracks live positions with current market price and unrealized P&L.

    Attributes:
        position_id: Unique identifier (UUID)
        trade_id: Reference to corresponding trade
        symbol: Trading symbol
        side: 0=BUY, 1=SELL
        volume: Current position size
        entry_price: Entry level
        current_price: Last market price
        stop_loss: Stop loss level
        take_profit: Take profit level
        unrealized_profit: Current P&L
        opened_at: When position opened
    """

    __tablename__ = "positions"

    # Primary Key
    position_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    trade_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    # Position Details
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    side: Mapped[int] = mapped_column(nullable=False)  # 0=BUY, 1=SELL
    volume: Mapped[Decimal] = mapped_column(nullable=False)

    # Prices
    entry_price: Mapped[Decimal] = mapped_column(nullable=False)
    current_price: Mapped[Decimal] = mapped_column(nullable=False)
    stop_loss: Mapped[Decimal] = mapped_column(nullable=False)
    take_profit: Mapped[Decimal] = mapped_column(nullable=False)

    # P&L
    unrealized_profit: Mapped[Decimal] = mapped_column(nullable=True)

    # Timestamps
    opened_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __repr__(self) -> str:
        """String representation of position."""
        return f"<Position {self.symbol} {self.volume} lots @ {self.current_price}>"


class EquityPoint(Base):
    """Snapshot of account equity at a point in time.

    Used for tracking equity curve, drawdown analysis, and performance metrics.

    Attributes:
        equity_id: Unique identifier (UUID)
        timestamp: When measured (UTC)
        equity: Account equity in GBP
        balance: Account balance in GBP
        drawdown_percent: Current drawdown %
        trades_open: Count of open trades
    """

    __tablename__ = "equity_points"

    # Primary Key
    equity_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )

    # Equity Data
    timestamp: Mapped[datetime] = mapped_column(nullable=False, index=True)
    equity: Mapped[Decimal] = mapped_column(nullable=False)
    balance: Mapped[Decimal] = mapped_column(nullable=False)
    drawdown_percent: Mapped[Decimal] = mapped_column(nullable=False)
    trades_open: Mapped[int] = mapped_column(nullable=False, default=0)

    def __repr__(self) -> str:
        """String representation of equity point."""
        return f"<EquityPoint {self.timestamp}: £{self.equity} (dd: {self.drawdown_percent}%)>"


class ValidationLog(Base):
    """Audit trail for trade validation and state changes.

    Records all significant events for a trade (creation, execution, closure, errors).

    Attributes:
        log_id: Unique identifier (UUID)
        trade_id: Reference to associated trade
        timestamp: When event occurred (UTC)
        event_type: Type of event (CREATED, EXECUTED, CLOSED, ERROR, etc.)
        message: Human-readable description
        details: JSON metadata (optional)
    """

    __tablename__ = "validation_logs"

    # Primary Key
    log_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    trade_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    # Event Details
    timestamp: Mapped[datetime] = mapped_column(nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # CREATED, EXECUTED, CLOSED, ERROR, etc.
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    details: Mapped[str | None] = mapped_column(nullable=True)  # JSON string

    __table_args__ = (Index("ix_validation_logs_trade_time", "trade_id", "timestamp"),)

    def __repr__(self) -> str:
        """String representation of validation log."""
        return f"<ValidationLog {self.event_type}: {self.message[:50]}>"
