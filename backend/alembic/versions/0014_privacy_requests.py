"""Add privacy requests table.

Revision ID: 0014_privacy_requests
Revises: 0013_journeys
Create Date: 2025-01-18 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0014_privacy_requests"
down_revision = "0013_journeys"
branch_labels = None
depends_on = None


def upgrade():
    """Create privacy_requests table for GDPR compliance."""
    op.create_table(
        "privacy_requests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("request_type", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.Column("scheduled_deletion_at", sa.DateTime(), nullable=True),
        sa.Column("metadata", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("export_url", sa.String(length=500), nullable=True),
        sa.Column("export_expires_at", sa.DateTime(), nullable=True),
        sa.Column("hold_reason", sa.String(length=500), nullable=True),
        sa.Column("hold_by", sa.String(length=36), nullable=True),
        sa.Column("hold_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    # Indexes for efficient queries
    op.create_index("ix_privacy_requests_user_id", "privacy_requests", ["user_id"])
    op.create_index("ix_privacy_requests_status", "privacy_requests", ["status"])
    op.create_index(
        "ix_privacy_requests_user_type", "privacy_requests", ["user_id", "request_type"]
    )
    op.create_index(
        "ix_privacy_requests_status_created",
        "privacy_requests",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_privacy_requests_scheduled_deletion",
        "privacy_requests",
        ["scheduled_deletion_at"],
    )


def downgrade():
    """Drop privacy_requests table."""
    op.drop_index(
        "ix_privacy_requests_scheduled_deletion", table_name="privacy_requests"
    )
    op.drop_index("ix_privacy_requests_status_created", table_name="privacy_requests")
    op.drop_index("ix_privacy_requests_user_type", table_name="privacy_requests")
    op.drop_index("ix_privacy_requests_status", table_name="privacy_requests")
    op.drop_index("ix_privacy_requests_user_id", table_name="privacy_requests")
    op.drop_table("privacy_requests")
