"""SQLAlchemy models for trading signals domain."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Column, String, Integer, DateTime, Index, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.app.core.db import Base


class Signal(Base):
    """
    Trading signal model.

    Represents a signal to buy/sell an instrument at a specific price.
    Signals are created by external producers (e.g., strategy engines)
    and stored with validation and audit metadata.

    Attributes:
        id: Unique identifier (UUID)
        instrument: Trading pair (e.g., "XAUUSD", "EURUSD")
        side: Trade direction (0=buy, 1=sell)
        time: Signal creation timestamp
        payload: JSON strategy data (RSI, Bollinger Bands, etc.) - max 32KB
        version: Signal format version (default 1)
        status: Signal lifecycle state (0=new, 1=queued, 2=closed)
        created_at: When signal was ingested (auto-set)
        updated_at: Last modification time (auto-updated)

    Example:
        >>> signal = Signal(
        ...     instrument="XAUUSD",
        ...     side=0,  # buy
        ...     time=datetime.utcnow(),
        ...     payload={"rsi": 75, "macd": -0.5},
        ...     status=0,
        ... )
        >>> session.add(signal)
        >>> await session.commit()
    """

    __tablename__ = "signals"

    # Primary Key
    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
        doc="Unique signal identifier (UUID v4)",
    )

    # Signal Content
    instrument = Column(
        String(20),
        nullable=False,
        index=True,
        doc="Trading instrument code (e.g., XAUUSD, EURUSD)",
    )

    side = Column(
        Integer,
        nullable=False,
        doc="Trade direction: 0=buy, 1=sell",
    )

    time = Column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        doc="Signal creation timestamp (UTC)",
    )

    payload = Column(
        JSON,
        nullable=True,
        doc="Strategy-specific data (RSI, Bollinger Bands, etc.) - max 32KB",
    )

    version = Column(
        Integer,
        nullable=False,
        default=1,
        doc="Signal format version for backward compatibility",
    )

    # Signal State
    status = Column(
        Integer,
        nullable=False,
        default=0,
        doc="Signal state: 0=new, 1=queued, 2=closed",
    )

    # Audit Timestamps
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        doc="When signal was ingested",
    )

    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        onupdate=func.now(),
        doc="Last modification timestamp",
    )

    # Indexes for common queries
    __table_args__ = (
        Index("ix_signals_instrument_time", "instrument", "time"),
        Index("ix_signals_status", "status"),
    )

    # Relationships
    approvals = relationship("Approval", back_populates="signal", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        """Return string representation of signal."""
        side_str = "BUY" if self.side == 0 else "SELL"
        return f"<Signal {self.id[:8]}... {self.instrument} {side_str} @ {self.time}>"
