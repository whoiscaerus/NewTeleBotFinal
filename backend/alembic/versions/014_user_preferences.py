"""
PR-059: Add user_preferences table

Revision ID: 014_user_preferences
Revises: 013_pr_048_mt5_account_sync
Create Date: 2025-11-06 10:00:00.000000

Manages user notification preferences, instrument filters, alert settings,
quiet hours, and digest frequency.

Integrates with:
- PR-044 (Price Alerts)
- PR-033/034 (Billing reminders)
- PR-032 (Marketing nudges)
- PR-104 (Position Tracking - execution failure alerts)
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "014_user_preferences"
down_revision = "013_pr_048_mt5_account_sync"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Create user_preferences table with all notification and alert settings.

    Default Values (safety-first approach):
    - instruments_enabled: all instruments enabled
    - alert_types_enabled: all alert types enabled
    - notify_via_telegram: true
    - notify_via_email: true
    - notify_via_push: false
    - quiet_hours_enabled: false
    - timezone: UTC
    - digest_frequency: immediate
    - notify_entry_failure: true (safety-first for PR-104)
    - notify_exit_failure: true (safety-first for PR-104)
    - max_alerts_per_hour: 10

    Note: Using JSON for array storage (SQLite-compatible, also works with PostgreSQL)
    """
    op.create_table(
        "user_preferences",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        # Instrument filters (JSON for SQLite compatibility)
        sa.Column(
            "instruments_enabled",
            sa.JSON(),
            nullable=False,
            server_default='["gold","sp500","crypto","forex","indices"]',
        ),
        # Alert type filters (JSON for SQLite compatibility)
        sa.Column(
            "alert_types_enabled",
            sa.JSON(),
            nullable=False,
            server_default='["price","drawdown","copy_risk","execution_failure"]',
        ),
        # Notification channels
        sa.Column(
            "notify_via_telegram", sa.Boolean(), nullable=False, server_default="true"
        ),
        sa.Column(
            "notify_via_email", sa.Boolean(), nullable=False, server_default="true"
        ),
        sa.Column(
            "notify_via_push", sa.Boolean(), nullable=False, server_default="false"
        ),
        # Quiet hours (do not disturb)
        sa.Column(
            "quiet_hours_enabled", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column("quiet_hours_start", sa.Time(), nullable=True),
        sa.Column("quiet_hours_end", sa.Time(), nullable=True),
        sa.Column(
            "timezone", sa.String(length=50), nullable=False, server_default="UTC"
        ),
        # Digest frequency
        sa.Column(
            "digest_frequency",
            sa.String(length=20),
            nullable=False,
            server_default="immediate",
        ),
        # Execution failure alerts (PR-104 integration - default ON for safety)
        sa.Column(
            "notify_entry_failure", sa.Boolean(), nullable=False, server_default="true"
        ),
        sa.Column(
            "notify_exit_failure", sa.Boolean(), nullable=False, server_default="true"
        ),
        # Alert throttling
        sa.Column(
            "max_alerts_per_hour", sa.Integer(), nullable=False, server_default="10"
        ),
        # Metadata
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")
        ),
        # Primary key
        sa.PrimaryKeyConstraint("id"),
        # Foreign keys
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        # Unique constraint (one preferences row per user)
        sa.UniqueConstraint("user_id", name="uq_user_preferences_user_id"),
    )

    # Indexes for fast lookups
    op.create_index("ix_user_preferences_id", "user_preferences", ["id"], unique=False)
    op.create_index(
        "ix_user_preferences_user_id", "user_preferences", ["user_id"], unique=True
    )


def downgrade() -> None:
    """
    Drop user_preferences table.

    Warning: This will permanently delete all user notification preferences.
    """
    op.drop_index("ix_user_preferences_user_id", table_name="user_preferences")
    op.drop_index("ix_user_preferences_id", table_name="user_preferences")
    op.drop_table("user_preferences")
