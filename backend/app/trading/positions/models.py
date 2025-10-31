"""Database models for open positions (server-side position tracking)."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.db import Base

if TYPE_CHECKING:
    pass


class PositionStatus(Enum):
    """Position lifecycle status."""

    OPEN = 0  # Position is currently open
    CLOSED_SL = 1  # Position closed by stop loss
    CLOSED_TP = 2  # Position closed by take profit
    CLOSED_MANUAL = 3  # Position closed manually by user/admin
    CLOSED_ERROR = 4  # Position close failed/error
    CLOSED_DRAWDOWN = 5  # Position closed by drawdown guard
    CLOSED_MARKET = 6  # Position closed by market condition guard


class OpenPosition(Base):
    """Open position tracking model.

    Tracks client positions with hidden owner SL/TP levels for server-side
    auto-close when levels are hit. This enables anti-reselling protection
    by hiding exit levels from clients.

    Fields:
        id: Unique position identifier
        execution_id: Link to execution record (EA ack)
        signal_id: Link to original signal
        approval_id: Link to user approval
        user_id: User who owns this position
        device_id: Device that executed the trade

        instrument: Trading instrument (GOLD, EURUSD, etc.)
        side: Trade direction (0=buy, 1=sell)
        entry_price: Actual entry price from broker
        volume: Position size in lots
        broker_ticket: MT5/broker ticket number

        owner_sl: Hidden stop loss level (NEVER exposed to client)
        owner_tp: Hidden take profit level (NEVER exposed to client)

        status: Position lifecycle status
        opened_at: Position open timestamp
        closed_at: Position close timestamp (None if still open)
        close_price: Actual close price
        close_reason: Reason for close (sl_hit, tp_hit, manual, etc.)

    Security:
        The owner_sl and owner_tp fields must NEVER be exposed to client APIs.
        Only server-side position monitor service should access these values.
    """

    __tablename__ = "open_positions"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
        doc="Unique position ID",
    )

    # Foreign key relationships
    execution_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("executions.id"),
        nullable=False,
        index=True,
        doc="Link to execution record",
    )
    signal_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("signals.id"),
        nullable=False,
        index=True,
        doc="Link to original signal",
    )
    approval_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("approvals.id"),
        nullable=False,
        index=True,
        doc="Link to user approval",
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id"),
        nullable=False,
        index=True,
        doc="User who owns this position",
    )
    device_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("devices.id"),
        nullable=False,
        index=True,
        doc="Device that executed the trade",
    )

    # Trade details
    instrument: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        doc="Trading instrument",
    )
    side: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="0=buy, 1=sell",
    )
    entry_price: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        doc="Actual entry price from broker",
    )
    volume: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        doc="Position size in lots",
    )
    broker_ticket: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        index=True,
        doc="MT5/broker ticket number",
    )

    # Hidden owner levels (NEVER exposed to clients)
    owner_sl: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        doc="Hidden stop loss level - NEVER exposed to client",
    )
    owner_tp: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        doc="Hidden take profit level - NEVER exposed to client",
    )

    # Status tracking
    status: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=PositionStatus.OPEN.value,
        doc="Position lifecycle status",
    )
    opened_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=datetime.utcnow,
        doc="Position open timestamp",
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        doc="Position close timestamp",
    )
    close_price: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        doc="Actual close price",
    )
    close_reason: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        doc="Reason for close (sl_hit, tp_hit, manual, drawdown, etc.)",
    )

    # Relationships (commented to avoid circular import - CloseCommand can query via FK)
    # close_commands = relationship("CloseCommand", back_populates="position", cascade="all, delete-orphan")

    # Indexes for efficient queries
    __table_args__ = (
        Index("ix_open_positions_status", "status"),
        Index("ix_open_positions_user_status", "user_id", "status"),
        Index("ix_open_positions_instrument_status", "instrument", "status"),
        Index("ix_open_positions_opened_at", "opened_at"),
    )

    def __repr__(self) -> str:
        """Readable position representation."""
        side_str = "BUY" if self.side == 0 else "SELL"
        status_name = PositionStatus(self.status).name
        return f"<OpenPosition {self.id[:8]}: {self.instrument} {side_str} @ {self.entry_price} [{status_name}]>"

    def is_open(self) -> bool:
        """Check if position is currently open."""
        return self.status == PositionStatus.OPEN.value

    def is_closed(self) -> bool:
        """Check if position has been closed."""
        return self.status != PositionStatus.OPEN.value

    def calculate_pnl(self, current_price: float) -> float:
        """
        Calculate unrealized PnL for open position.

        Args:
            current_price: Current market price

        Returns:
            PnL in points (positive = profit, negative = loss)

        Example:
            >>> position = OpenPosition(side=0, entry_price=2650.0, volume=0.1)
            >>> pnl = position.calculate_pnl(2670.0)  # BUY position, price up
            >>> print(pnl)  # +20.0 points profit
        """
        if self.side == 0:  # BUY
            return current_price - self.entry_price
        else:  # SELL
            return self.entry_price - current_price
