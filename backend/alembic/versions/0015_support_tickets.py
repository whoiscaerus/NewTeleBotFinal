"""Alembic migration: Create support tickets table.

Revision ID: 0015_support_tickets
Revises: 0014_ai_chat
Create Date: 2025-01-XX
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0015_support_tickets"
down_revision = "0014_ai_chat"
branch_labels = None
depends_on = None


def upgrade():
    """Create tickets table for human escalation support system."""
    op.create_table(
        "tickets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("severity", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("status", sa.String(30), nullable=False, server_default="open"),
        sa.Column("channel", sa.String(20), nullable=False, server_default="web"),
        sa.Column("context", sa.JSON, nullable=True),
        sa.Column(
            "created_at", sa.DateTime, nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.Column("resolved_at", sa.DateTime, nullable=True),
        sa.Column("closed_at", sa.DateTime, nullable=True),
        sa.Column(
            "assigned_to", sa.String(36), sa.ForeignKey("users.id"), nullable=True
        ),
        sa.Column("resolution_note", sa.Text, nullable=True),
        sa.Column("internal_notes", sa.Text, nullable=True),
    )

    # Create indexes for common query patterns
    op.create_index("ix_tickets_user_id", "tickets", ["user_id"])
    op.create_index("ix_tickets_severity", "tickets", ["severity"])
    op.create_index("ix_tickets_status", "tickets", ["status"])
    op.create_index("ix_tickets_created_at", "tickets", ["created_at"])
    op.create_index("ix_tickets_assigned_to", "tickets", ["assigned_to"])

    # Composite indexes for common filter combinations
    op.create_index("ix_tickets_status_severity", "tickets", ["status", "severity"])
    op.create_index("ix_tickets_user_status", "tickets", ["user_id", "status"])
    op.create_index("ix_tickets_assignee_status", "tickets", ["assigned_to", "status"])
    op.create_index("ix_tickets_created_status", "tickets", ["created_at", "status"])


def downgrade():
    """Drop tickets table."""
    op.drop_index("ix_tickets_created_status", table_name="tickets")
    op.drop_index("ix_tickets_assignee_status", table_name="tickets")
    op.drop_index("ix_tickets_user_status", table_name="tickets")
    op.drop_index("ix_tickets_status_severity", table_name="tickets")
    op.drop_index("ix_tickets_assigned_to", table_name="tickets")
    op.drop_index("ix_tickets_created_at", table_name="tickets")
    op.drop_index("ix_tickets_status", table_name="tickets")
    op.drop_index("ix_tickets_severity", table_name="tickets")
    op.drop_index("ix_tickets_user_id", table_name="tickets")
    op.drop_table("tickets")
