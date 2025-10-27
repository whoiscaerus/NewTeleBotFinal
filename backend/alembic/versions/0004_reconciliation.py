"""Add reconciliation models for MT5 account sync.

Revision ID: 0004_reconciliation
Revises: 003_add_signals_approvals
Create Date: 2024-10-26 19:30:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision = "0004_reconciliation"
down_revision = "003_add_signals_approvals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create reconciliation tables."""

    # ReconciliationLog table
    op.create_table(
        "reconciliation_logs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("signal_id", sa.UUID(), nullable=True),
        sa.Column("approval_id", sa.UUID(), nullable=True),
        sa.Column("mt5_position_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("direction", sa.String(10), nullable=False),
        sa.Column("volume", sa.Float(), nullable=False),
        sa.Column("entry_price", sa.Float(), nullable=False),
        sa.Column("current_price", sa.Float(), nullable=True),
        sa.Column("take_profit", sa.Float(), nullable=True),
        sa.Column("stop_loss", sa.Float(), nullable=True),
        sa.Column("matched", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("divergence_reason", sa.String(100), nullable=True),
        sa.Column("slippage_pips", sa.Float(), nullable=True),
        sa.Column("close_reason", sa.String(100), nullable=True),
        sa.Column("closed_price", sa.Float(), nullable=True),
        sa.Column("pnl_gbp", sa.Float(), nullable=True),
        sa.Column("pnl_percent", sa.Float(), nullable=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["approval_id"], ["approvals.id"]),
        sa.ForeignKeyConstraint(["signal_id"], ["signals.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes for ReconciliationLog
    op.create_index(
        "ix_reconciliation_user_created",
        "reconciliation_logs",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_reconciliation_symbol_created",
        "reconciliation_logs",
        ["symbol", "created_at"],
    )
    op.create_index(
        "ix_reconciliation_event_type", "reconciliation_logs", ["event_type"]
    )
    op.create_index("ix_reconciliation_status", "reconciliation_logs", ["status"])
    op.create_index(
        "ix_reconciliation_logs_user_id", "reconciliation_logs", ["user_id"]
    )
    op.create_index(
        "ix_reconciliation_logs_signal_id", "reconciliation_logs", ["signal_id"]
    )
    op.create_index(
        "ix_reconciliation_logs_approval_id", "reconciliation_logs", ["approval_id"]
    )

    # PositionSnapshot table
    op.create_table(
        "position_snapshots",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("equity_gbp", sa.Float(), nullable=False),
        sa.Column("balance_gbp", sa.Float(), nullable=False),
        sa.Column("peak_equity_gbp", sa.Float(), nullable=False),
        sa.Column("drawdown_percent", sa.Float(), nullable=False),
        sa.Column(
            "open_positions_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "total_volume_lots", sa.Float(), nullable=False, server_default="0.0"
        ),
        sa.Column("open_pnl_gbp", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column(
            "margin_used_percent", sa.Float(), nullable=False, server_default="0.0"
        ),
        sa.Column("last_sync_at", sa.DateTime(), nullable=True),
        sa.Column("sync_error", sa.String(200), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes for PositionSnapshot
    op.create_index(
        "ix_position_snapshot_user_created",
        "position_snapshots",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_position_snapshot_user_latest",
        "position_snapshots",
        ["user_id", "created_at DESC"],
    )
    op.create_index("ix_position_snapshots_user_id", "position_snapshots", ["user_id"])

    # DrawdownAlert table
    op.create_table(
        "drawdown_alerts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("alert_type", sa.String(50), nullable=False),
        sa.Column("drawdown_percent", sa.Float(), nullable=False),
        sa.Column("equity_gbp", sa.Float(), nullable=False),
        sa.Column("threshold_percent", sa.Float(), nullable=False),
        sa.Column(
            "positions_closed_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("total_loss_gbp", sa.Float(), nullable=True),
        sa.Column("action_taken", sa.String(200), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("executed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes for DrawdownAlert
    op.create_index(
        "ix_drawdown_alert_user_created", "drawdown_alerts", ["user_id", "created_at"]
    )
    op.create_index("ix_drawdown_alert_type", "drawdown_alerts", ["alert_type"])
    op.create_index("ix_drawdown_alert_status", "drawdown_alerts", ["status"])
    op.create_index("ix_drawdown_alerts_user_id", "drawdown_alerts", ["user_id"])


def downgrade() -> None:
    """Drop reconciliation tables."""

    # Drop DrawdownAlert
    op.drop_index("ix_drawdown_alerts_user_id", table_name="drawdown_alerts")
    op.drop_index("ix_drawdown_alert_status", table_name="drawdown_alerts")
    op.drop_index("ix_drawdown_alert_type", table_name="drawdown_alerts")
    op.drop_index("ix_drawdown_alert_user_created", table_name="drawdown_alerts")
    op.drop_table("drawdown_alerts")

    # Drop PositionSnapshot
    op.drop_index("ix_position_snapshots_user_id", table_name="position_snapshots")
    op.drop_index("ix_position_snapshot_user_latest", table_name="position_snapshots")
    op.drop_index("ix_position_snapshot_user_created", table_name="position_snapshots")
    op.drop_table("position_snapshots")

    # Drop ReconciliationLog
    op.drop_index(
        "ix_reconciliation_logs_approval_id", table_name="reconciliation_logs"
    )
    op.drop_index("ix_reconciliation_logs_signal_id", table_name="reconciliation_logs")
    op.drop_index("ix_reconciliation_logs_user_id", table_name="reconciliation_logs")
    op.drop_index("ix_reconciliation_status", table_name="reconciliation_logs")
    op.drop_index("ix_reconciliation_event_type", table_name="reconciliation_logs")
    op.drop_index("ix_reconciliation_symbol_created", table_name="reconciliation_logs")
    op.drop_index("ix_reconciliation_user_created", table_name="reconciliation_logs")
    op.drop_table("reconciliation_logs")
