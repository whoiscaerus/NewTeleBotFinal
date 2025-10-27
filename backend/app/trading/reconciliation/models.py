"""Reconciliation models for MT5 account sync and position monitoring."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import UUID as UUIDType
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    desc,
)
from sqlalchemy.orm import relationship

from backend.app.core.db import Base


class ReconciliationLog(Base):
    """
    Tracks position reconciliation events between MT5 and bot expectations.

    Records every sync event, divergences, and auto-close decisions.
    Used for audit trail and performance analysis.
    """

    __tablename__ = "reconciliation_logs"

    id = Column(UUIDType(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(
        UUIDType(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    signal_id = Column(
        UUIDType(as_uuid=True), ForeignKey("signals.id"), nullable=True, index=True
    )
    approval_id = Column(
        UUIDType(as_uuid=True), ForeignKey("approvals.id"), nullable=True, index=True
    )

    # MT5 Position Details
    mt5_position_id = Column(Integer, nullable=False)  # MT5 ticket number
    symbol = Column(String(20), nullable=False, index=True)
    direction = Column(String(10), nullable=False)  # 'buy' or 'sell'
    volume = Column(Float, nullable=False)  # Position size in lots
    entry_price = Column(Float, nullable=False)
    current_price = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=True)

    # Reconciliation Status
    matched = Column(
        Integer, nullable=False, default=0
    )  # 0=not matched, 1=matched, 2=divergence
    divergence_reason = Column(
        String(100), nullable=True
    )  # 'slippage', 'partial_fill', 'manual_close', 'gap', 'other'
    slippage_pips = Column(
        Float, nullable=True
    )  # Difference between expected vs actual entry

    # Close Information (if applicable)
    close_reason = Column(
        String(100), nullable=True
    )  # 'drawdown', 'market_guard', 'tp_hit', 'sl_hit', 'manual', 'expiry'
    closed_price = Column(Float, nullable=True)
    pnl_gbp = Column(Float, nullable=True)
    pnl_percent = Column(Float, nullable=True)

    # Metadata
    event_type = Column(
        String(50), nullable=False
    )  # 'sync', 'close', 'guard_trigger', 'warning'
    status = Column(
        String(50), nullable=False
    )  # 'success', 'partial', 'failed', 'warning'
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    user = relationship("User", lazy="select")
    signal = relationship("Signal", lazy="select")
    approval = relationship("Approval", lazy="select")

    # Indexes
    __table_args__ = (
        Index("ix_reconciliation_user_created", "user_id", "created_at"),
        Index("ix_reconciliation_symbol_created", "symbol", "created_at"),
        Index("ix_reconciliation_event_type", "event_type"),
        Index("ix_reconciliation_status", "status"),
    )

    def __repr__(self):
        return (
            f"<ReconciliationLog {self.id}: {self.symbol} {self.direction} "
            f"matched={self.matched} event={self.event_type}>"
        )


class PositionSnapshot(Base):
    """
    Snapshot of account equity and open positions at point in time.

    Used to track drawdown from peak equity and detect account stress conditions.
    """

    __tablename__ = "position_snapshots"

    id = Column(UUIDType(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(
        UUIDType(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )

    # Account Status
    equity_gbp = Column(Float, nullable=False)  # Current account equity
    balance_gbp = Column(
        Float, nullable=False
    )  # Account balance (equity minus open P&L)
    peak_equity_gbp = Column(
        Float, nullable=False
    )  # Historical peak equity (for drawdown calc)
    drawdown_percent = Column(Float, nullable=False)  # Current drawdown from peak

    # Position Summary
    open_positions_count = Column(Integer, nullable=False, default=0)
    total_volume_lots = Column(Float, nullable=False, default=0.0)
    open_pnl_gbp = Column(Float, nullable=False, default=0.0)
    margin_used_percent = Column(Float, nullable=False, default=0.0)

    # Market Conditions
    last_sync_at = Column(DateTime, nullable=True)
    sync_error = Column(String(200), nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Indexes
    __table_args__ = (
        Index("ix_position_snapshot_user_created", "user_id", "created_at"),
        Index("ix_position_snapshot_user_latest", "user_id", desc("created_at")),
    )

    def __repr__(self):
        return (
            f"<PositionSnapshot {self.user_id}: equity=£{self.equity_gbp:.2f} "
            f"drawdown={self.drawdown_percent:.1f}% positions={self.open_positions_count}>"
        )


class DrawdownAlert(Base):
    """
    Record of drawdown guard triggers and warnings.

    Used to track when positions were auto-closed due to equity protection rules.
    """

    __tablename__ = "drawdown_alerts"

    id = Column(UUIDType(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(
        UUIDType(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )

    # Alert Details
    alert_type = Column(String(50), nullable=False)  # 'warning' or 'execution'
    drawdown_percent = Column(Float, nullable=False)
    equity_gbp = Column(Float, nullable=False)
    threshold_percent = Column(Float, nullable=False)

    # Action Taken
    positions_closed_count = Column(Integer, nullable=False, default=0)
    total_loss_gbp = Column(Float, nullable=True)
    action_taken = Column(
        String(200), nullable=False
    )  # 'warning_sent', 'positions_closed', 'failed'
    status = Column(String(50), nullable=False)  # 'success', 'failed', 'pending_manual'

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    executed_at = Column(DateTime, nullable=True)

    # Indexes
    __table_args__ = (
        Index("ix_drawdown_alert_user_created", "user_id", "created_at"),
        Index("ix_drawdown_alert_type", "alert_type"),
        Index("ix_drawdown_alert_status", "status"),
    )

    def __repr__(self):
        return (
            f"<DrawdownAlert {self.id}: {self.alert_type} {self.drawdown_percent:.1f}% "
            f"action={self.action_taken}>"
        )
