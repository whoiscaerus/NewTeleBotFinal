"""Risk management models for per-client risk profiles and exposure tracking."""

from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import JSON, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.db import Base


class RiskProfile(Base):
    """Per-client risk management configuration.

    Defines risk limits and parameters for each client including:
    - Maximum drawdown percentage before trading halt
    - Maximum position size per trade
    - Maximum number of open positions
    - Daily loss limits
    - Risk percentage per trade
    - Correlation exposure limits

    Attributes:
        id: Unique profile ID (UUID)
        client_id: Associated client (foreign key, unique)
        max_drawdown_percent: Stop trading if account drawdown exceeds this % (default: 20%)
        max_daily_loss: Maximum loss in dollars per day (optional)
        max_position_size: Maximum lot size per trade (default: 1.0 lot)
        max_open_positions: Maximum concurrent open positions (default: 5)
        max_correlation_exposure: Maximum correlation exposure (default: 70%)
        risk_per_trade_percent: Risk per trade as % of account (default: 2%)
        updated_at: Last modification timestamp

    Constraints:
        - client_id: UNIQUE (one profile per client)
        - max_drawdown_percent: 0-100
        - max_position_size: > 0
        - max_open_positions: > 0
        - risk_per_trade_percent: 0-100
    """

    __tablename__ = "risk_profiles"

    # Primary Key
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
        doc="Unique profile ID",
    )

    # Foreign Key
    client_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        unique=True,
        doc="Client ID (unique - one profile per client)",
    )

    # Risk Limits - Drawdown
    max_drawdown_percent: Mapped[Decimal] = mapped_column(
        nullable=False,
        default=Decimal("20.00"),
        doc="Maximum drawdown % before trading halt (default: 20%)",
    )

    # Risk Limits - Daily Loss
    max_daily_loss: Mapped[Decimal | None] = mapped_column(
        nullable=True,
        doc="Maximum loss in account currency per day (optional)",
    )

    # Risk Limits - Position Size
    max_position_size: Mapped[Decimal] = mapped_column(
        nullable=False,
        default=Decimal("1.0"),
        doc="Maximum lot size per trade (default: 1.0)",
    )

    # Risk Limits - Open Positions
    max_open_positions: Mapped[int] = mapped_column(
        nullable=False,
        default=5,
        doc="Maximum concurrent open positions (default: 5)",
    )

    # Risk Limits - Correlation
    max_correlation_exposure: Mapped[Decimal] = mapped_column(
        nullable=False,
        default=Decimal("0.70"),
        doc="Maximum correlation exposure (default: 70%)",
    )

    # Risk Limits - Per-Trade Risk
    risk_per_trade_percent: Mapped[Decimal] = mapped_column(
        nullable=False,
        default=Decimal("2.00"),
        doc="Risk per trade as % of account (default: 2%)",
    )

    # Timestamps
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        doc="Last modification timestamp",
    )

    # Indexes
    __table_args__ = ()  # UNIQUE constraint on client_id handles indexing

    def __repr__(self) -> str:
        return (
            f"<RiskProfile {self.client_id}: "
            f"DD={self.max_drawdown_percent}%, "
            f"Pos={self.max_open_positions}, "
            f"PosSize={self.max_position_size}>"
        )


class ExposureSnapshot(Base):
    """Current exposure state snapshot for a client.

    Captures the current position exposure metrics including:
    - Total exposure in lots
    - Exposure breakdown by instrument
    - Exposure breakdown by direction (long/short)
    - Count of open positions
    - Current account drawdown
    - Daily P&L

    Snapshots are created periodically (every 5 minutes) and used to:
    - Verify risk limits before signal approval
    - Track exposure trends
    - Calculate current drawdown
    - Generate risk reports

    Attributes:
        id: Unique snapshot ID (UUID)
        client_id: Associated client (foreign key)
        timestamp: When snapshot was taken
        total_exposure: Total position size in lots
        exposure_by_instrument: JSON dict of exposure per instrument
        exposure_by_direction: JSON dict of exposure by direction (buy/sell)
        open_positions_count: Number of open trades
        current_drawdown_percent: Current drawdown % from peak
        daily_pnl: Daily profit/loss in account currency
    """

    __tablename__ = "exposure_snapshots"

    # Primary Key
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
        doc="Unique snapshot ID",
    )

    # Foreign Key
    client_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
        doc="Client ID",
    )

    # Timestamp
    timestamp: Mapped[datetime] = mapped_column(
        nullable=False,
        default=datetime.utcnow,
        index=True,
        doc="When snapshot was taken",
    )

    # Total Exposure
    total_exposure: Mapped[Decimal] = mapped_column(
        nullable=False,
        default=Decimal("0.0"),
        doc="Total position size in lots",
    )

    # Exposure by Instrument (JSON)
    exposure_by_instrument: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        doc="Exposure per instrument: {EURUSD: 1.5, GOLD: 2.0}",
    )

    # Exposure by Direction (JSON)
    exposure_by_direction: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        doc="Exposure by direction: {buy: 2.0, sell: 1.5}",
    )

    # Position Count
    open_positions_count: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
        doc="Number of open positions",
    )

    # Drawdown
    current_drawdown_percent: Mapped[Decimal] = mapped_column(
        nullable=False,
        default=Decimal("0.0"),
        doc="Current drawdown % from peak balance",
    )

    # Daily P&L
    daily_pnl: Mapped[Decimal] = mapped_column(
        nullable=False,
        default=Decimal("0.0"),
        doc="Daily profit/loss in account currency",
    )

    # Indexes
    __table_args__ = (
        Index("ix_exposure_snapshots_client_timestamp", "client_id", "timestamp"),
        Index("ix_exposure_snapshots_client_latest", "client_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<ExposureSnapshot {self.client_id} "
            f"@{self.timestamp.isoformat()}: "
            f"Exposure={self.total_exposure}, "
            f"DD={self.current_drawdown_percent}%>"
        )
