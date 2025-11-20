"""
Analytics data warehouse models.

Provides normalized, denormalized, and rollup tables for fast analytics queries.
Implements star schema: trades_fact, dim_symbol, dim_day, daily_rollups.
"""

from datetime import datetime

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from backend.app.core.db import Base


class DimSymbol(Base):
    """Dimension table for trading symbols.

    Normalizes symbol names to prevent duplication.
    Example: 'GOLD', 'EURUSD', 'AAPL'
    """

    __tablename__ = "dim_symbol"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), unique=True, nullable=False, index=True)
    description = Column(String(255), nullable=True)
    asset_class = Column(
        String(50), nullable=True
    )  # 'forex', 'commodity', 'crypto', 'stock'
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    trades = relationship("TradesFact", back_populates="dim_symbol", lazy="selectin")
    rollups = relationship("DailyRollups", back_populates="dim_symbol", lazy="selectin")

    def __repr__(self):
        return f"<DimSymbol {self.symbol}>"


class DimDay(Base):
    """Dimension table for trading days.

    Normalizes dates with metadata (day of week, is_trading_day).
    Enables efficient time-based queries.
    """

    __tablename__ = "dim_day"

    id = Column(Integer, primary_key=True)
    date = Column(Date, unique=True, nullable=False, index=True)
    day_of_week = Column(Integer, nullable=False)  # 0=Monday, 6=Sunday
    week_of_year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    year = Column(Integer, nullable=False)
    is_trading_day = Column(
        Integer, nullable=False, default=1
    )  # 1=yes, 0=no (weekend/holiday)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    rollups = relationship("DailyRollups", back_populates="dim_day", lazy="selectin")

    def __repr__(self):
        return f"<DimDay {self.date}>"


class TradesFact(Base):
    """Fact table for individual trades.

    Stores denormalized trade data for fast queries.
    Each row = one closed trade with all metrics pre-calculated.
    """

    __tablename__ = "trades_fact"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), nullable=False, index=True)
    symbol_id = Column(Integer, ForeignKey("dim_symbol.id"), nullable=False, index=True)
    entry_date_id = Column(Integer, ForeignKey("dim_day.id"), nullable=False)
    exit_date_id = Column(Integer, ForeignKey("dim_day.id"), nullable=False)

    # Trade details
    side = Column(Integer, nullable=False)  # 0=buy, 1=sell
    entry_price = Column(Numeric(18, 8), nullable=False)
    exit_price = Column(Numeric(18, 8), nullable=False)
    stop_loss = Column(Numeric(18, 8), nullable=True)
    take_profit = Column(Numeric(18, 8), nullable=True)
    volume = Column(Numeric(18, 8), nullable=False)

    # Calculated metrics
    gross_pnl = Column(Numeric(18, 8), nullable=False)  # Profit/Loss in quote currency
    pnl_percent = Column(Numeric(10, 6), nullable=False)  # As percentage
    commission = Column(Numeric(18, 8), nullable=False, default=0)
    net_pnl = Column(Numeric(18, 8), nullable=False)  # gross_pnl - commission
    r_multiple = Column(Numeric(10, 4), nullable=True)  # Risk/Reward ratio
    bars_held = Column(Integer, nullable=False, default=1)
    winning_trade = Column(Integer, nullable=False)  # 1=win, 0=loss

    # Risk metrics
    risk_amount = Column(Numeric(18, 8), nullable=False)  # Entry - Stop Loss
    max_run_up = Column(
        Numeric(18, 8), nullable=False, default=0
    )  # Max profit during trade
    max_drawdown = Column(
        Numeric(18, 8), nullable=False, default=0
    )  # Max loss during trade

    # Timestamps
    entry_time = Column(DateTime, nullable=False)
    exit_time = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Source tracking
    source = Column(String(50), nullable=False)  # 'signal', 'manual', 'copy_trading'
    signal_id = Column(String(36), nullable=True)  # Links to signal if bot-generated

    # Relationships
    dim_symbol = relationship("DimSymbol", back_populates="trades", lazy="selectin")

    # Indexes
    __table_args__ = (
        Index("ix_trades_fact_user_id_exit_date", "user_id", "exit_date_id"),
        Index("ix_trades_fact_symbol_id_exit_date", "symbol_id", "exit_date_id"),
        Index("ix_trades_fact_entry_time", "entry_time"),
        Index("ix_trades_fact_exit_time", "exit_time"),
    )

    def __repr__(self):
        return f"<TradesFact {self.id}: {self.side} @ {self.entry_price}>"


class DailyRollups(Base):
    """Rollup table for daily aggregated metrics.

    Pre-aggregates trades by day and symbol for fast charting.
    One row per day per symbol per user.
    """

    __tablename__ = "daily_rollups"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), nullable=False, index=True)
    symbol_id = Column(Integer, ForeignKey("dim_symbol.id"), nullable=False, index=True)
    day_id = Column(Integer, ForeignKey("dim_day.id"), nullable=False, index=True)

    # Trade counts
    total_trades = Column(Integer, nullable=False, default=0)
    winning_trades = Column(Integer, nullable=False, default=0)
    losing_trades = Column(Integer, nullable=False, default=0)

    # PnL metrics (in quote currency)
    gross_pnl = Column(Numeric(18, 8), nullable=False, default=0)
    total_commission = Column(Numeric(18, 8), nullable=False, default=0)
    net_pnl = Column(Numeric(18, 8), nullable=False, default=0)

    # Win rate and ratio metrics
    win_rate = Column(Numeric(5, 4), nullable=False, default=0)  # 0.0 to 1.0
    profit_factor = Column(
        Numeric(10, 4), nullable=False, default=0
    )  # Gross wins / Gross losses
    avg_r_multiple = Column(Numeric(10, 4), nullable=False, default=0)

    # Risk metrics
    avg_win = Column(Numeric(18, 8), nullable=False, default=0)
    avg_loss = Column(Numeric(18, 8), nullable=False, default=0)
    largest_win = Column(Numeric(18, 8), nullable=False, default=0)
    largest_loss = Column(Numeric(18, 8), nullable=False, default=0)
    max_run_up = Column(Numeric(18, 8), nullable=False, default=0)
    max_drawdown = Column(Numeric(18, 8), nullable=False, default=0)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    dim_symbol = relationship("DimSymbol", back_populates="rollups", lazy="selectin")
    dim_day = relationship("DimDay", back_populates="rollups", lazy="selectin")

    # Indexes
    __table_args__ = (
        Index("ix_daily_rollups_user_id_day_id", "user_id", "day_id"),
        Index("ix_daily_rollups_symbol_id_day_id", "symbol_id", "day_id"),
        UniqueConstraint(
            "user_id", "symbol_id", "day_id", name="uq_daily_rollups_user_symbol_day"
        ),
    )

    def __repr__(self):
        return (
            f"<DailyRollups user={self.user_id} day={self.day_id} pnl={self.net_pnl}>"
        )


class EquityCurve(Base):
    """Equity curve snapshots by date.

    Tracks account equity at end of each trading day.
    Used for drawdown calculation and equity charts.
    """

    __tablename__ = "equity_curve"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), nullable=False, index=True)
    date = Column(Date, nullable=False)
    equity = Column(Numeric(18, 8), nullable=False)  # Account equity balance
    cumulative_pnl = Column(Numeric(18, 8), nullable=False)  # Total PnL from start
    peak_equity = Column(Numeric(18, 8), nullable=False)  # Peak equity to date
    drawdown = Column(Numeric(10, 6), nullable=False)  # Current drawdown as %
    daily_change = Column(
        Numeric(18, 8), nullable=False, default=0
    )  # PnL for this day only

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Indexes
    __table_args__ = (
        Index("ix_equity_curve_user_id_date", "user_id", "date"),
        UniqueConstraint("user_id", "date", name="uq_equity_curve_user_id_date"),
    )

    def __repr__(self):
        return (
            f"<EquityCurve user={self.user_id} date={self.date} equity={self.equity}>"
        )
