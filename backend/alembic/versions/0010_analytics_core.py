"""Create analytics warehouse schema.

Revision ID: 0010_analytics_core
Revises: 0009_copytrading_compliance
Create Date: 2025-10-31 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0010_analytics_core"
down_revision = "0009_copytrading_compliance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create analytics warehouse tables."""
    # Create dim_symbol dimension table
    op.create_table(
        "dim_symbol",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("asset_class", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("symbol", name="uq_dim_symbol_symbol"),
    )
    op.create_index("ix_dim_symbol_symbol", "dim_symbol", ["symbol"])

    # Create dim_day dimension table
    op.create_table(
        "dim_day",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("day_of_week", sa.Integer(), nullable=False),
        sa.Column("week_of_year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("is_trading_day", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("date", name="uq_dim_day_date"),
    )
    op.create_index("ix_dim_day_date", "dim_day", ["date"])

    # Create trades_fact fact table
    op.create_table(
        "trades_fact",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("symbol_id", sa.Integer(), nullable=False),
        sa.Column("entry_date_id", sa.Integer(), nullable=False),
        sa.Column("exit_date_id", sa.Integer(), nullable=False),
        sa.Column("side", sa.Integer(), nullable=False),
        sa.Column("entry_price", sa.Numeric(18, 8), nullable=False),
        sa.Column("exit_price", sa.Numeric(18, 8), nullable=False),
        sa.Column("stop_loss", sa.Numeric(18, 8), nullable=True),
        sa.Column("take_profit", sa.Numeric(18, 8), nullable=True),
        sa.Column("volume", sa.Numeric(18, 8), nullable=False),
        sa.Column("gross_pnl", sa.Numeric(18, 8), nullable=False),
        sa.Column("pnl_percent", sa.Numeric(10, 6), nullable=False),
        sa.Column("commission", sa.Numeric(18, 8), nullable=False),
        sa.Column("net_pnl", sa.Numeric(18, 8), nullable=False),
        sa.Column("r_multiple", sa.Numeric(10, 4), nullable=True),
        sa.Column("bars_held", sa.Integer(), nullable=False),
        sa.Column("winning_trade", sa.Integer(), nullable=False),
        sa.Column("risk_amount", sa.Numeric(18, 8), nullable=False),
        sa.Column("max_run_up", sa.Numeric(18, 8), nullable=False),
        sa.Column("max_drawdown", sa.Numeric(18, 8), nullable=False),
        sa.Column("entry_time", sa.DateTime(), nullable=False),
        sa.Column("exit_time", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("signal_id", sa.String(36), nullable=True),
        sa.ForeignKeyConstraint(["entry_date_id"], ["dim_day.id"]),
        sa.ForeignKeyConstraint(["exit_date_id"], ["dim_day.id"]),
        sa.ForeignKeyConstraint(["symbol_id"], ["dim_symbol.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trades_fact_user_id", "trades_fact", ["user_id"])
    op.create_index("ix_trades_fact_symbol_id", "trades_fact", ["symbol_id"])
    op.create_index(
        "ix_trades_fact_user_id_exit_date", "trades_fact", ["user_id", "exit_date_id"]
    )
    op.create_index(
        "ix_trades_fact_symbol_id_exit_date",
        "trades_fact",
        ["symbol_id", "exit_date_id"],
    )
    op.create_index("ix_trades_fact_entry_time", "trades_fact", ["entry_time"])
    op.create_index("ix_trades_fact_exit_time", "trades_fact", ["exit_time"])

    # Create daily_rollups aggregation table
    op.create_table(
        "daily_rollups",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("symbol_id", sa.Integer(), nullable=False),
        sa.Column("day_id", sa.Integer(), nullable=False),
        sa.Column("total_trades", sa.Integer(), nullable=False),
        sa.Column("winning_trades", sa.Integer(), nullable=False),
        sa.Column("losing_trades", sa.Integer(), nullable=False),
        sa.Column("gross_pnl", sa.Numeric(18, 8), nullable=False),
        sa.Column("total_commission", sa.Numeric(18, 8), nullable=False),
        sa.Column("net_pnl", sa.Numeric(18, 8), nullable=False),
        sa.Column("win_rate", sa.Numeric(5, 4), nullable=False),
        sa.Column("profit_factor", sa.Numeric(10, 4), nullable=False),
        sa.Column("avg_r_multiple", sa.Numeric(10, 4), nullable=False),
        sa.Column("avg_win", sa.Numeric(18, 8), nullable=False),
        sa.Column("avg_loss", sa.Numeric(18, 8), nullable=False),
        sa.Column("largest_win", sa.Numeric(18, 8), nullable=False),
        sa.Column("largest_loss", sa.Numeric(18, 8), nullable=False),
        sa.Column("max_run_up", sa.Numeric(18, 8), nullable=False),
        sa.Column("max_drawdown", sa.Numeric(18, 8), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["day_id"], ["dim_day.id"]),
        sa.ForeignKeyConstraint(["symbol_id"], ["dim_symbol.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "symbol_id", "day_id", name="uq_daily_rollups_user_symbol_day"
        ),
    )
    op.create_index("ix_daily_rollups_user_id", "daily_rollups", ["user_id"])
    op.create_index("ix_daily_rollups_symbol_id", "daily_rollups", ["symbol_id"])
    op.create_index(
        "ix_daily_rollups_user_id_day_id", "daily_rollups", ["user_id", "day_id"]
    )
    op.create_index(
        "ix_daily_rollups_symbol_id_day_id", "daily_rollups", ["symbol_id", "day_id"]
    )

    # Create equity_curve snapshots table
    op.create_table(
        "equity_curve",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("equity", sa.Numeric(18, 8), nullable=False),
        sa.Column("cumulative_pnl", sa.Numeric(18, 8), nullable=False),
        sa.Column("peak_equity", sa.Numeric(18, 8), nullable=False),
        sa.Column("drawdown", sa.Numeric(10, 6), nullable=False),
        sa.Column("daily_change", sa.Numeric(18, 8), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "date", name="uq_equity_curve_user_id_date"),
    )
    op.create_index("ix_equity_curve_user_id", "equity_curve", ["user_id"])
    op.create_index("ix_equity_curve_user_id_date", "equity_curve", ["user_id", "date"])


def downgrade() -> None:
    """Drop analytics warehouse tables."""
    op.drop_index("ix_equity_curve_user_id_date", table_name="equity_curve")
    op.drop_index("ix_equity_curve_user_id", table_name="equity_curve")
    op.drop_table("equity_curve")

    op.drop_index("ix_daily_rollups_symbol_id_day_id", table_name="daily_rollups")
    op.drop_index("ix_daily_rollups_user_id_day_id", table_name="daily_rollups")
    op.drop_index("ix_daily_rollups_symbol_id", table_name="daily_rollups")
    op.drop_index("ix_daily_rollups_user_id", table_name="daily_rollups")
    op.drop_table("daily_rollups")

    op.drop_index("ix_trades_fact_exit_time", table_name="trades_fact")
    op.drop_index("ix_trades_fact_entry_time", table_name="trades_fact")
    op.drop_index("ix_trades_fact_symbol_id_exit_date", table_name="trades_fact")
    op.drop_index("ix_trades_fact_user_id_exit_date", table_name="trades_fact")
    op.drop_index("ix_trades_fact_symbol_id", table_name="trades_fact")
    op.drop_index("ix_trades_fact_user_id", table_name="trades_fact")
    op.drop_table("trades_fact")

    op.drop_index("ix_dim_day_date", table_name="dim_day")
    op.drop_table("dim_day")

    op.drop_index("ix_dim_symbol_symbol", table_name="dim_symbol")
    op.drop_table("dim_symbol")
