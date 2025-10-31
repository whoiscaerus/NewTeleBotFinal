"""Add close_commands table for PR-104 Phase 5

Revision ID: 015_add_close_commands
Revises: 014_add_approval_client_id
Create Date: 2024-10-30 00:00:00.000000

This migration adds the close_commands table for server-initiated position closes.
When the position monitor detects SL/TP breaches, it creates close commands that
the EA polls and executes.
"""

from datetime import datetime

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "015_add_close_commands"
down_revision = "014_add_approval_client_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create close_commands table."""
    op.create_table(
        "close_commands",
        # Primary key
        sa.Column("id", sa.String(length=36), nullable=False, primary_key=True),
        # Foreign keys
        sa.Column(
            "position_id",
            sa.String(length=36),
            sa.ForeignKey("open_positions.id"),
            nullable=False,
        ),
        sa.Column(
            "device_id",
            sa.String(length=36),
            sa.ForeignKey("devices.id"),
            nullable=False,
        ),
        # Command details
        sa.Column("reason", sa.String(length=50), nullable=False),
        sa.Column("expected_price", sa.Float(), nullable=False),
        # Status tracking
        sa.Column("status", sa.Integer(), nullable=False, default=0),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            default=datetime.utcnow,
        ),
        sa.Column("acknowledged_at", sa.DateTime(), nullable=True),
        sa.Column("executed_at", sa.DateTime(), nullable=True),
        # Execution results
        sa.Column("actual_close_price", sa.Float(), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
    )

    # Create indexes for efficient queries
    op.create_index(
        "ix_close_commands_device_status",
        "close_commands",
        ["device_id", "status"],
    )
    op.create_index(
        "ix_close_commands_position",
        "close_commands",
        ["position_id"],
    )
    op.create_index(
        "ix_close_commands_created",
        "close_commands",
        ["created_at"],
    )


def downgrade() -> None:
    """Drop close_commands table."""
    op.drop_index("ix_close_commands_created", table_name="close_commands")
    op.drop_index("ix_close_commands_position", table_name="close_commands")
    op.drop_index("ix_close_commands_device_status", table_name="close_commands")
    op.drop_table("close_commands")
