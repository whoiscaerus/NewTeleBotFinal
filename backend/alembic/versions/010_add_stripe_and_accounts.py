"""Add Stripe events and account linking tables.

Revision ID: 010
Revises: 009
Create Date: 2025-10-25

Tables:
- stripe_events: Track webhook events for idempotent processing
- account_links: Map users to MT5 accounts (multi-account support)
- account_info: Cache account balance/equity/drawdown
- position_snapshots: Live position snapshots from MT5 (30s TTL cache)
"""

import sqlalchemy as sa
from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create Stripe and account tables."""
    # Create stripe_events table
    op.create_table(
        "stripe_events",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("event_id", sa.String(255), nullable=False, unique=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("payment_method", sa.String(50), nullable=False),
        sa.Column("customer_id", sa.String(255)),
        sa.Column("amount_cents", sa.Integer, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("status", sa.Integer, nullable=False, server_default="0"),
        sa.Column("idempotency_key", sa.String(255)),
        sa.Column("processed_at", sa.DateTime),
        sa.Column("error_message", sa.Text),
        sa.Column("webhook_timestamp", sa.DateTime, nullable=False),
        sa.Column(
            "received_at", sa.DateTime, nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "created_at", sa.DateTime, nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_event_id", "stripe_events", ["event_id"])
    op.create_index("ix_idempotency_key", "stripe_events", ["idempotency_key"])
    op.create_index("ix_status_created", "stripe_events", ["status", "created_at"])

    # Create account_links table
    op.create_table(
        "account_links",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("mt5_account_id", sa.String(50), nullable=False),
        sa.Column("mt5_login", sa.String(50), nullable=False),
        sa.Column("broker_name", sa.String(100)),
        sa.Column("is_primary", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="1"),
        sa.Column("verified_at", sa.DateTime),
        sa.Column(
            "created_at", sa.DateTime, nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "mt5_account_id", name="unique_user_mt5"),
    )
    op.create_index("ix_user_id", "account_links", ["user_id"])
    op.create_index("ix_mt5_login", "account_links", ["mt5_login"])

    # Create account_info table
    op.create_table(
        "account_info",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("account_link_id", sa.String(36), nullable=False),
        sa.Column("balance", sa.Numeric(20, 2)),
        sa.Column("equity", sa.Numeric(20, 2)),
        sa.Column("free_margin", sa.Numeric(20, 2)),
        sa.Column("margin_used", sa.Numeric(20, 2)),
        sa.Column("margin_level", sa.Numeric(10, 2)),
        sa.Column("drawdown_percent", sa.Numeric(6, 2)),
        sa.Column("open_positions_count", sa.Integer, server_default="0"),
        sa.Column(
            "last_updated", sa.DateTime, nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["account_link_id"], ["account_links.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_account_link_id", "account_info", ["account_link_id"])

    # Create live_positions table for individual open position tracking
    op.create_table(
        "live_positions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("account_link_id", sa.String(36), nullable=False),
        sa.Column("ticket", sa.String(255), nullable=False),  # MT5 ticket
        sa.Column("instrument", sa.String(20), nullable=False, index=True),
        sa.Column("side", sa.Integer, nullable=False),  # 0=buy, 1=sell
        sa.Column("volume", sa.Numeric(12, 2), nullable=False),
        sa.Column("entry_price", sa.Numeric(20, 6), nullable=False),
        sa.Column("current_price", sa.Numeric(20, 6), nullable=False),
        sa.Column("stop_loss", sa.Numeric(20, 6)),
        sa.Column("take_profit", sa.Numeric(20, 6)),
        sa.Column("pnl_points", sa.Numeric(10, 2), nullable=False),
        sa.Column("pnl_usd", sa.Numeric(12, 2), nullable=False),
        sa.Column("pnl_percent", sa.Numeric(8, 4), nullable=False),
        sa.Column("opened_at", sa.DateTime),
        sa.Column(
            "created_at", sa.DateTime, nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["account_link_id"], ["account_links.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_live_positions_account_time",
        "live_positions",
        ["account_link_id", "created_at"],
    )
    op.create_index("ix_live_positions_instrument", "live_positions", ["instrument"])


def downgrade() -> None:
    """Drop Stripe and account tables."""
    op.drop_table("live_positions")
    op.drop_table("account_info")
    op.drop_table("account_links")
    op.drop_table("stripe_events")
