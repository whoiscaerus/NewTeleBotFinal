"""PR-065: Add smart alert rules and multi-channel support

Revision ID: 065_smart_alert_rules
Revises: 064_education_tables
Create Date: 2025-11-08

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "065_smart_alert_rules"
down_revision = "064_education_tables"
branch_labels = None
depends_on = None


def upgrade():
    """Create smart alert rules tables for PR-065."""

    # Create smart_alert_rules table
    op.create_table(
        "smart_alert_rules",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("symbol", sa.String(50), nullable=False),
        sa.Column("rule_type", sa.String(50), nullable=False),
        sa.Column("threshold_value", sa.Float(), nullable=False),
        sa.Column("window_minutes", sa.Integer(), nullable=True),
        sa.Column("rsi_period", sa.Integer(), nullable=True),
        sa.Column(
            "cooldown_minutes", sa.Integer(), nullable=False, server_default="60"
        ),
        sa.Column("is_muted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("channels", sa.JSON(), nullable=False),
        sa.Column("last_triggered_at", sa.DateTime(), nullable=True),
        sa.Column("previous_price", sa.Float(), nullable=True),
        sa.Column("last_evaluation_at", sa.DateTime(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes for smart_alert_rules
    op.create_index(
        "ix_smart_rules_user_symbol", "smart_alert_rules", ["user_id", "symbol"]
    )
    op.create_index(
        "ix_smart_rules_active", "smart_alert_rules", ["is_active", "is_muted"]
    )
    op.create_index(
        "ix_smart_rules_evaluation",
        "smart_alert_rules",
        ["is_active", "last_evaluation_at"],
    )

    # Create rule_notifications table
    op.create_table(
        "rule_notifications",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("rule_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("channel", sa.String(50), nullable=False),
        sa.Column("message", sa.String(1000), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=False),
        sa.Column("delivered", sa.Boolean(), nullable=True, server_default="false"),
        sa.Column("error_message", sa.String(500), nullable=True),
        sa.ForeignKeyConstraint(
            ["rule_id"], ["smart_alert_rules.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes for rule_notifications
    op.create_index(
        "ix_rule_notifications_rule", "rule_notifications", ["rule_id", "sent_at"]
    )
    op.create_index(
        "ix_rule_notifications_user", "rule_notifications", ["user_id", "sent_at"]
    )


def downgrade():
    """Drop smart alert rules tables."""

    # Drop indexes first
    op.drop_index("ix_rule_notifications_user", table_name="rule_notifications")
    op.drop_index("ix_rule_notifications_rule", table_name="rule_notifications")
    op.drop_index("ix_smart_rules_evaluation", table_name="smart_alert_rules")
    op.drop_index("ix_smart_rules_active", table_name="smart_alert_rules")
    op.drop_index("ix_smart_rules_user_symbol", table_name="smart_alert_rules")

    # Drop tables
    op.drop_table("rule_notifications")
    op.drop_table("smart_alert_rules")
