"""Create trading store tables for trade persistence.

Revision ID: 0002_create_trading_store
Revises: 0001_initial_schema
Create Date: 2024-10-24 10:30:00.000000

This migration creates the core trading store tables:
- trades: Complete trade records with entry/exit details
- positions: Open positions with unrealized P&L tracking
- equity_points: Equity curve snapshots for drawdown analysis
- validation_logs: Audit trail for all state changes

All tables use UUID primary keys, UTC timestamps, and Decimal for financial precision.
"""

import sqlalchemy as sa
from alembic import op

# Revision identifiers
revision = "0002_create_trading_store"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create trading store tables."""

    # Create trades table
    op.create_table(
        "trades",
        sa.Column("trade_id", sa.String(36), nullable=False, primary_key=True),
        sa.Column("symbol", sa.String(20), nullable=False, index=True),
        sa.Column("trade_type", sa.String(4), nullable=False),
        sa.Column("direction", sa.Integer, nullable=False),  # 0=BUY, 1=SELL
        sa.Column("entry_price", sa.Numeric(12, 5), nullable=False),
        sa.Column("entry_time", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("entry_comment", sa.String(500), nullable=True),
        sa.Column("stop_loss", sa.Numeric(12, 5), nullable=False),
        sa.Column("take_profit", sa.Numeric(12, 5), nullable=False),
        sa.Column("exit_price", sa.Numeric(12, 5), nullable=True),
        sa.Column("exit_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exit_reason", sa.String(50), nullable=True),
        sa.Column("volume", sa.Numeric(8, 2), nullable=False),
        sa.Column("profit", sa.Numeric(12, 2), nullable=True),
        sa.Column("pips", sa.Numeric(8, 2), nullable=True),
        sa.Column("duration_hours", sa.Float, nullable=True),
        sa.Column("risk_reward_ratio", sa.Numeric(5, 2), nullable=True),
        sa.Column("strategy", sa.String(50), nullable=False, index=True),
        sa.Column("timeframe", sa.String(10), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, index=True),
        sa.Column("signal_id", sa.String(36), nullable=True),
        sa.Column("device_id", sa.String(36), nullable=True),
        sa.Column("setup_id", sa.String(100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )

    # Create indexes on trades table
    op.create_index("ix_trades_symbol_time", "trades", ["symbol", "entry_time"])
    op.create_index("ix_trades_status_created", "trades", ["status", "created_at"])
    op.create_index("ix_trades_strategy_symbol", "trades", ["strategy", "symbol"])

    # Create positions table
    op.create_table(
        "positions",
        sa.Column("position_id", sa.String(36), nullable=False, primary_key=True),
        sa.Column("symbol", sa.String(20), nullable=False, index=True),
        sa.Column("direction", sa.String(4), nullable=False),  # BUY or SELL
        sa.Column("volume", sa.Numeric(8, 2), nullable=False),
        sa.Column("entry_price", sa.Numeric(12, 5), nullable=False),
        sa.Column("current_price", sa.Numeric(12, 5), nullable=False),
        sa.Column("stop_loss", sa.Numeric(12, 5), nullable=False),
        sa.Column("take_profit", sa.Numeric(12, 5), nullable=False),
        sa.Column("unrealized_profit", sa.Numeric(12, 2), nullable=True),
        sa.Column("duration_hours", sa.Float, nullable=False),
        sa.Column(
            "opened_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.Column("trade_ids", sa.JSON, nullable=True),
    )

    # Create equity_points table
    op.create_table(
        "equity_points",
        sa.Column("point_id", sa.String(36), nullable=False, primary_key=True),
        sa.Column("equity", sa.Numeric(12, 2), nullable=False),
        sa.Column("balance", sa.Numeric(12, 2), nullable=False),
        sa.Column("margin_used", sa.Numeric(12, 2), nullable=False),
        sa.Column("margin_available", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            index=True,
            server_default=sa.func.now(),
        ),
        sa.Column("trade_count", sa.Integer, nullable=False, default=0),
        sa.Column("closed_trade_count", sa.Integer, nullable=False, default=0),
    )

    # Create indexes on equity_points
    op.create_index("ix_equity_points_timestamp", "equity_points", ["timestamp"])

    # Create validation_logs table
    op.create_table(
        "validation_logs",
        sa.Column("log_id", sa.String(36), nullable=False, primary_key=True),
        sa.Column("trade_id", sa.String(36), nullable=False, index=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("message", sa.String(500), nullable=False),
        sa.Column("details", sa.JSON, nullable=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            index=True,
            server_default=sa.func.now(),
        ),
    )

    # Create indexes on validation_logs
    op.create_index(
        "ix_validation_logs_trade_time", "validation_logs", ["trade_id", "timestamp"]
    )


def downgrade() -> None:
    """Drop trading store tables."""

    # Drop indexes
    op.drop_index("ix_validation_logs_trade_time", table_name="validation_logs")
    op.drop_index("ix_equity_points_timestamp", table_name="equity_points")
    op.drop_index("ix_trades_strategy_symbol", table_name="trades")
    op.drop_index("ix_trades_status_created", table_name="trades")
    op.drop_index("ix_trades_symbol_time", table_name="trades")

    # Drop tables
    op.drop_table("validation_logs")
    op.drop_table("equity_points")
    op.drop_table("positions")
    op.drop_table("trades")
