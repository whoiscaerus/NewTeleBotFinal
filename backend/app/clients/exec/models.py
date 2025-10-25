"""Execution store models - device ACK/fill records."""

from datetime import datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.db import Base


class ExecutionType(Enum):
    """Type of execution record."""

    ACK = 0  # Device acknowledged signal received
    FILL = 1  # Device reported trade fill
    ERROR = 2  # Device reported error


class ExecutionRecord(Base):
    """Device execution record.

    Records when device ACKs signals or reports fills,
    for reconciliation with signals and trades.
    """

    __tablename__ = "execution_records"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
        doc="Execution record ID",
    )
    device_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
        doc="Device ID that sent execution",
    )
    signal_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
        doc="Signal ID being executed",
    )
    trade_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        index=True,
        doc="Trade ID if fill (optional)",
    )
    execution_type: Mapped[int] = mapped_column(
        nullable=False,
        doc="Type of execution (ACK=0, FILL=1, ERROR=2)",
    )
    status_code: Mapped[int | None] = mapped_column(
        nullable=True,
        doc="HTTP status code from device",
    )
    error_message: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        doc="Error message if execution failed",
    )
    fill_price: Mapped[float | None] = mapped_column(
        nullable=True,
        doc="Fill price if trade executed",
    )
    fill_size: Mapped[float | None] = mapped_column(
        nullable=True,
        doc="Fill size if trade executed",
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=datetime.utcnow,
    )

    __table_args__ = (
        Index("ix_exec_device", "device_id", "created_at"),
        Index("ix_exec_signal", "signal_id", "execution_type"),
        Index("ix_exec_trade", "trade_id"),
    )
