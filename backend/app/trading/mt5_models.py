"""
PR-048: MT5 Account Sync & Margin Management

Models for tracking live MT5 account state:
- Account balance, equity, leverage
- Margin available and used
- Per-user account synchronization
- Integration with risk validation
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
)

from backend.app.core.db import Base


class UserMT5Account(Base):
    """
    Live MT5 account state synchronized from user's trading account.

    Critical for risk management:
    - Calculate margin requirements before trade execution
    - Validate position sizes don't exceed available margin
    - Track leverage to compute correct position sizing
    - Detect account changes (deposits/withdrawals) that affect risk budget

    Synchronized via EA or MT5 API polling (every 30-60 seconds).
    """

    __tablename__ = "user_mt5_accounts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String(36), ForeignKey("users.id"), nullable=False, index=True, unique=True
    )

    # MT5 Account Identification
    mt5_account_id = Column(Integer, nullable=False)  # MT5 login number
    mt5_server = Column(String(100), nullable=False)  # "FxPro-MT5 Demo"
    broker_name = Column(String(100), nullable=False)  # "FxPro"

    # Account State (synced from MT5)
    balance = Column(Float, nullable=False, default=0.0)  # Account balance (£/$/€)
    equity = Column(Float, nullable=False, default=0.0)  # Current equity (unrealized)
    margin_used = Column(
        Float, nullable=False, default=0.0
    )  # Margin for open positions
    margin_free = Column(
        Float, nullable=False, default=0.0
    )  # Margin available for new positions
    margin_level_percent = Column(
        Float, nullable=True
    )  # (Equity / Margin) * 100 (None if no positions)

    # Leverage (critical for margin calculation)
    account_leverage = Column(
        Integer, nullable=False, default=100
    )  # 100:1, 200:1, 500:1, etc.

    # Position Metrics
    open_positions_count = Column(Integer, nullable=False, default=0)
    total_positions_volume = Column(
        Float, nullable=False, default=0.0
    )  # Total lots across all positions

    # Account Currency
    account_currency = Column(
        String(10), nullable=False, default="GBP"
    )  # "GBP", "USD", "EUR"

    # Sync Metadata
    last_synced_at = Column(
        DateTime, nullable=False, default=datetime.utcnow
    )  # Last successful sync
    sync_status = Column(
        String(50), nullable=False, default="active"
    )  # "active", "stale", "error"
    sync_error_message = Column(String(500), nullable=True)

    # Status
    is_active = Column(Boolean, default=True)  # False if user disconnects account
    is_demo = Column(Boolean, default=True)  # True for demo accounts

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        Index("ix_mt5_user_id", "user_id"),
        Index("ix_mt5_sync_status", "sync_status", "last_synced_at"),
        Index("ix_mt5_account_id", "mt5_account_id"),
    )


class UserMT5SyncLog(Base):
    """
    Audit log for MT5 account sync operations.

    Tracks every sync attempt to debug issues and monitor sync health.
    Retained for 90 days for compliance and troubleshooting.
    """

    __tablename__ = "user_mt5_sync_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    mt5_account_id = Column(Integer, nullable=False)

    # Sync Result
    sync_status = Column(String(50), nullable=False)  # "success", "failed", "timeout"
    sync_duration_ms = Column(Integer, nullable=True)  # Sync time in milliseconds

    # Synced Data Snapshot
    balance_before = Column(Float, nullable=True)
    balance_after = Column(Float, nullable=True)
    equity_after = Column(Float, nullable=True)
    margin_free_after = Column(Float, nullable=True)
    leverage_after = Column(Integer, nullable=True)

    # Error Details (if failed)
    error_code = Column(String(100), nullable=True)
    error_message = Column(String(1000), nullable=True)

    synced_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index("ix_mt5_sync_log_user_time", "user_id", "synced_at"),
        Index("ix_mt5_sync_log_status", "sync_status"),
    )


class TradeSetupRiskLog(Base):
    """
    Risk validation log for trade setups with multiple entries.

    Records every risk validation decision:
    - Total SL amount for all positions in setup
    - Margin required vs available
    - Approval/rejection reason
    - Account state at validation time

    Critical for debugging why trades were blocked or allowed.
    """

    __tablename__ = "trade_setup_risk_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    setup_id = Column(String(100), nullable=False, index=True)  # TradeSetup identifier

    # Account State at Validation
    account_balance = Column(Float, nullable=False)
    account_equity = Column(Float, nullable=False)
    margin_available = Column(Float, nullable=False)
    account_leverage = Column(Integer, nullable=False)

    # Risk Budget
    user_tier = Column(String(50), nullable=False)  # "standard", "premium", "elite"
    allocated_risk_percent = Column(Float, nullable=False)  # 3%, 5%, 7%
    allocated_risk_amount = Column(Float, nullable=False)  # £1,500 for 3% of £50k

    # Position Details
    total_positions_count = Column(Integer, nullable=False)  # 3 entries
    entry_1_size_lots = Column(Float, nullable=True)
    entry_2_size_lots = Column(Float, nullable=True)
    entry_3_size_lots = Column(Float, nullable=True)

    # Risk Metrics
    total_stop_loss_amount = Column(
        Float, nullable=False
    )  # Total £ risk across all positions
    total_stop_loss_percent = Column(Float, nullable=False)  # % of account balance
    total_margin_required = Column(Float, nullable=False)  # Margin for all positions

    # Validation Result
    validation_status = Column(
        String(50), nullable=False
    )  # "approved", "rejected_risk", "rejected_margin"
    rejection_reason = Column(String(500), nullable=True)

    # Execution Status
    execution_status = Column(
        String(50), nullable=False, default="pending"
    )  # "pending", "executed", "failed"
    executed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index("ix_risk_log_user_status", "user_id", "validation_status"),
        Index("ix_risk_log_setup", "setup_id"),
        Index("ix_risk_log_created", "created_at"),
    )
