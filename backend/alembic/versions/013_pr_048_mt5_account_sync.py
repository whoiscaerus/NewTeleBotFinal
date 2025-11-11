"""
PR-048: MT5 Account Sync & Fixed Risk Management - Database Migration

Adds tables for:
- UserMT5Account: Live MT5 account state (balance, leverage, margin)
- UserMT5SyncLog: Audit trail of sync operations
- TradeSetupRiskLog: Risk validation logs for multi-entry setups
- Adds tier field to copy_trade_settings for risk allocation

Revision ID: 013_pr_048_mt5_account_sync
Revises: 012_pr_046_risk_compliance
Create Date: 2025-11-05
"""

import sqlalchemy as sa
from alembic import op

# Revision identifiers
revision = "013_pr_048_mt5_account_sync"
down_revision = "012_pr_046_risk_compliance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply PR-048 migrations."""

    # Step 1: Add tier column to copy_trade_settings
    op.add_column(
        "copy_trade_settings",
        sa.Column("tier", sa.String(50), nullable=False, server_default="standard"),
    )
    op.create_index("ix_copy_tier", "copy_trade_settings", ["tier"], unique=False)

    # Step 2: Create user_mt5_accounts table
    op.create_table(
        "user_mt5_accounts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("mt5_account_id", sa.Integer, nullable=False),
        sa.Column("mt5_server", sa.String(100), nullable=False),
        sa.Column("broker_name", sa.String(100), nullable=False),
        sa.Column("balance", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("equity", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("margin_used", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("margin_free", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("margin_level_percent", sa.Float, nullable=True),
        sa.Column("account_leverage", sa.Integer, nullable=False, server_default="100"),
        sa.Column(
            "open_positions_count", sa.Integer, nullable=False, server_default="0"
        ),
        sa.Column(
            "total_positions_volume", sa.Float, nullable=False, server_default="0.0"
        ),
        sa.Column(
            "account_currency", sa.String(10), nullable=False, server_default="GBP"
        ),
        sa.Column("last_synced_at", sa.DateTime, nullable=False),
        sa.Column(
            "sync_status", sa.String(50), nullable=False, server_default="active"
        ),
        sa.Column("sync_error_message", sa.String(500), nullable=True),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("is_demo", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    # Indexes for user_mt5_accounts
    op.create_index("ix_mt5_user_id", "user_mt5_accounts", ["user_id"], unique=True)
    op.create_index(
        "ix_mt5_sync_status",
        "user_mt5_accounts",
        ["sync_status", "last_synced_at"],
        unique=False,
    )
    op.create_index(
        "ix_mt5_account_id", "user_mt5_accounts", ["mt5_account_id"], unique=False
    )

    # Step 3: Create user_mt5_sync_logs table
    op.create_table(
        "user_mt5_sync_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("mt5_account_id", sa.Integer, nullable=False),
        sa.Column("sync_status", sa.String(50), nullable=False),
        sa.Column("sync_duration_ms", sa.Integer, nullable=True),
        sa.Column("balance_before", sa.Float, nullable=True),
        sa.Column("balance_after", sa.Float, nullable=True),
        sa.Column("equity_after", sa.Float, nullable=True),
        sa.Column("margin_free_after", sa.Float, nullable=True),
        sa.Column("leverage_after", sa.Integer, nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("error_message", sa.String(1000), nullable=True),
        sa.Column("synced_at", sa.DateTime, nullable=False),
    )

    # Indexes for user_mt5_sync_logs
    op.create_index(
        "ix_mt5_sync_log_user_time",
        "user_mt5_sync_logs",
        ["user_id", "synced_at"],
        unique=False,
    )
    op.create_index(
        "ix_mt5_sync_log_status", "user_mt5_sync_logs", ["sync_status"], unique=False
    )

    # Step 4: Create trade_setup_risk_logs table
    op.create_table(
        "trade_setup_risk_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("setup_id", sa.String(100), nullable=False),
        sa.Column("account_balance", sa.Float, nullable=False),
        sa.Column("account_equity", sa.Float, nullable=False),
        sa.Column("margin_available", sa.Float, nullable=False),
        sa.Column("account_leverage", sa.Integer, nullable=False),
        sa.Column("user_tier", sa.String(50), nullable=False),
        sa.Column("allocated_risk_percent", sa.Float, nullable=False),
        sa.Column("allocated_risk_amount", sa.Float, nullable=False),
        sa.Column("total_positions_count", sa.Integer, nullable=False),
        sa.Column("entry_1_size_lots", sa.Float, nullable=True),
        sa.Column("entry_2_size_lots", sa.Float, nullable=True),
        sa.Column("entry_3_size_lots", sa.Float, nullable=True),
        sa.Column("total_stop_loss_amount", sa.Float, nullable=False),
        sa.Column("total_stop_loss_percent", sa.Float, nullable=False),
        sa.Column("total_margin_required", sa.Float, nullable=False),
        sa.Column("validation_status", sa.String(50), nullable=False),
        sa.Column("rejection_reason", sa.String(500), nullable=True),
        sa.Column(
            "execution_status", sa.String(50), nullable=False, server_default="pending"
        ),
        sa.Column("executed_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )

    # Indexes for trade_setup_risk_logs
    op.create_index(
        "ix_risk_log_user_status",
        "trade_setup_risk_logs",
        ["user_id", "validation_status"],
        unique=False,
    )
    op.create_index(
        "ix_risk_log_setup", "trade_setup_risk_logs", ["setup_id"], unique=False
    )
    op.create_index(
        "ix_risk_log_created", "trade_setup_risk_logs", ["created_at"], unique=False
    )

    # Step 4: Create risk_configuration table (single row - owner-controlled global config)
    op.create_table(
        "risk_configuration",
        sa.Column("id", sa.Integer, primary_key=True, server_default="1"),
        sa.Column("fixed_risk_percent", sa.Float, nullable=False, server_default="3.0"),
        sa.Column("entry_1_percent", sa.Float, nullable=False, server_default="0.50"),
        sa.Column("entry_2_percent", sa.Float, nullable=False, server_default="0.35"),
        sa.Column("entry_3_percent", sa.Float, nullable=False, server_default="0.15"),
        sa.Column(
            "margin_buffer_percent", sa.Float, nullable=False, server_default="20.0"
        ),
        sa.Column("updated_by", sa.String(36), nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=True),
        sa.Column(
            "created_at", sa.DateTime, nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    """Revert PR-048 migrations."""
    op.drop_table("risk_configuration")

    op.drop_index("ix_risk_log_created", "trade_setup_risk_logs")
    op.drop_index("ix_risk_log_setup", "trade_setup_risk_logs")
    op.drop_index("ix_risk_log_user_status", "trade_setup_risk_logs")
    op.drop_table("trade_setup_risk_logs")

    op.drop_index("ix_mt5_sync_log_status", "user_mt5_sync_logs")
    op.drop_index("ix_mt5_sync_log_user_time", "user_mt5_sync_logs")
    op.drop_table("user_mt5_sync_logs")

    op.drop_index("ix_mt5_account_id", "user_mt5_accounts")
    op.drop_index("ix_mt5_sync_status", "user_mt5_accounts")
    op.drop_index("ix_mt5_user_id", "user_mt5_accounts")
    op.drop_table("user_mt5_accounts")

    op.drop_index("ix_copy_tier", "copy_trade_settings")
    op.drop_column("copy_trade_settings", "tier")
