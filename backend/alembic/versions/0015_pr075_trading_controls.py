"""Add trading_controls table for PR-075

Revision ID: 0015_pr075_trading_controls
Revises: 0014_add_positions_table
Create Date: 2025-11-08 22:46:10

Business Purpose:
- Store user-scoped trading control state (pause/resume, position size, notifications)
- Enable trading pause without closing existing positions
- Support position size overrides for manual control
- Track actor (user/admin/system) for audit trail

Integration:
- PR-074 guards: pause flag checked before signal generation
- PR-019 runtime: resume triggers on next candle boundary
- PR-060 messaging: notification toggles respect preferences
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0015_pr075_trading_controls"
down_revision: str | None = "0014_add_positions_table"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create trading_controls table."""
    op.create_table(
        "trading_controls",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False, unique=True),
        # Pause/Resume state
        sa.Column("is_paused", sa.Boolean, nullable=False, default=False),
        sa.Column("paused_at", sa.DateTime, nullable=True),
        sa.Column("paused_by", sa.String(50), nullable=True),  # user, admin, system
        sa.Column("pause_reason", sa.String(500), nullable=True),
        # Position sizing override (None = use default risk %)
        sa.Column("position_size_override", sa.Float, nullable=True),
        # Notification toggles
        sa.Column("notifications_enabled", sa.Boolean, nullable=False, default=True),
        # Audit fields
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    # Index for fast lookups by user_id (most common query)
    op.create_index(
        "ix_trading_controls_user_id",
        "trading_controls",
        ["user_id"],
        unique=True,
    )

    # Index for finding all paused users (system monitoring)
    op.create_index(
        "ix_trading_controls_is_paused",
        "trading_controls",
        ["is_paused"],
    )


def downgrade() -> None:
    """Drop trading_controls table."""
    op.drop_index("ix_trading_controls_is_paused", table_name="trading_controls")
    op.drop_index("ix_trading_controls_user_id", table_name="trading_controls")
    op.drop_table("trading_controls")
