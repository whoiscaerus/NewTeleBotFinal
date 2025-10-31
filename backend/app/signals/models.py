"""Database models for signals."""

from datetime import datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import JSON, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.db import Base


class SignalStatus(Enum):
    """Signal lifecycle status."""

    NEW = 0
    APPROVED = 1
    REJECTED = 2
    EXECUTED = 3
    CLOSED = 4
    CANCELLED = 5


class Signal(Base):
    """Trading signal model.

    Represents a signal to buy/sell an instrument at a specific price.
    Signals are created via API ingestion and approved by users before execution.

    Fields:
        id: Unique signal identifier (UUID)
        user_id: Associated user (foreign key)
        instrument: Trading instrument (XAUUSD, EURUSD, etc.)
        side: Trade direction (0=buy, 1=sell)
        price: Entry price in quote currency
        status: Lifecycle status (new, approved, executed, etc.)
        payload: JSON metadata from strategy (RSI, Fib level, etc.) - VISIBLE to clients
        owner_only: Encrypted owner-only data (SL/TP/strategy) - NEVER exposed to clients
        created_at: Signal creation timestamp (UTC)
        updated_at: Last modification timestamp
        external_id: External system ID for deduplication (optional)

    Security:
        The owner_only field stores sensitive data that must NEVER be exposed to clients:
        - stop_loss: Hidden stop loss level
        - take_profit: Hidden take profit level
        - strategy: Strategy reasoning/name

        This prevents signal reselling and protects intellectual property.
    """

    __tablename__ = "signals"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
        doc="Unique signal ID",
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
        doc="User who receives this signal",
    )
    instrument: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        doc="Trading instrument",
    )
    side: Mapped[int] = mapped_column(
        nullable=False,
        doc="0=buy, 1=sell",
    )
    price: Mapped[float] = mapped_column(
        nullable=False,
        doc="Entry price",
    )
    status: Mapped[int] = mapped_column(
        nullable=False,
        default=SignalStatus.NEW.value,
        index=True,
        doc="Lifecycle status code",
    )
    payload: Mapped[dict] = mapped_column(
        JSON,
        nullable=True,
        doc="Strategy metadata (JSON)",
    )
    owner_only: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
        doc="Encrypted owner-only data (SL/TP/strategy) - NEVER exposed to clients",
    )
    external_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        unique=True,
        index=True,
        doc="External system ID for deduplication",
    )
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="1.0",
        index=True,
        doc="Signal schema version for deduplication",
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # Indexes for common query patterns
    __table_args__ = (
        Index("ix_signal_user_created", "user_id", "created_at"),
        Index("ix_signal_instrument_status", "instrument", "status"),
        Index("ix_signal_external", "external_id"),
    )

    def __repr__(self) -> str:
        """Readable signal representation."""
        side_str = "BUY" if self.side == 0 else "SELL"
        return f"<Signal {self.id[:8]}: {self.instrument} {side_str} @ {self.price}>"

    def is_pending(self) -> bool:
        """Check if signal is awaiting approval."""
        return self.status == SignalStatus.NEW.value

    def is_approved(self) -> bool:
        """Check if signal has been approved."""
        return self.status == SignalStatus.APPROVED.value

    def is_executed(self) -> bool:
        """Check if signal has been executed."""
        return self.status == SignalStatus.EXECUTED.value
