"""Add price alerts tables.

Revision ID: 011
Revises: 010
Create Date: 2025-10-31

Tables:
- price_alerts: User-specific price alert rules
- alert_notifications: Sent notifications for deduplication/throttling
"""

import sqlalchemy as sa
from alembic import op

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create price alert tables."""
    # Create price_alerts table
    op.create_table(
        "price_alerts",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("symbol", sa.String(50), nullable=False),
        sa.Column("operator", sa.String(20), nullable=False),  # "above" or "below"
        sa.Column("price_level", sa.Float, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="1"),
        sa.Column("last_triggered_at", sa.DateTime),
        sa.Column(
            "created_at", sa.DateTime, nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_price_alerts_user", "price_alerts", ["user_id"])
    op.create_index(
        "ix_price_alerts_user_symbol", "price_alerts", ["user_id", "symbol"]
    )
    op.create_index("ix_price_alerts_active", "price_alerts", ["is_active", "symbol"])

    # Create alert_notifications table (for deduplication/throttling)
    op.create_table(
        "alert_notifications",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("alert_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("price_triggered", sa.Float, nullable=False),
        sa.Column("channel", sa.String(50), nullable=False),  # "telegram" or "miniapp"
        sa.Column("sent_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["alert_id"], ["price_alerts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alert_notif_alert", "alert_notifications", ["alert_id"])
    op.create_index("ix_alert_notif_user", "alert_notifications", ["user_id"])
    op.create_index(
        "ix_alert_notif_alert_user", "alert_notifications", ["alert_id", "user_id"]
    )


def downgrade() -> None:
    """Drop price alert tables."""
    op.drop_table("alert_notifications")
    op.drop_table("price_alerts")
