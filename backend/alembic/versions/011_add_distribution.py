"""Create distribution audit log table for PR-030.

Revision ID: 011_add_distribution
Created: 2025-10-27
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "011_add_distribution"
down_revision = "010_add_stripe_and_accounts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create distribution audit log table."""
    op.create_table(
        "distribution_audit_log",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("keywords", sa.JSON, nullable=False, comment="List of keywords used"),
        sa.Column(
            "matched_groups",
            sa.JSON,
            nullable=False,
            comment="Keyword to group IDs mapping",
        ),
        sa.Column(
            "messages_sent",
            sa.Integer,
            nullable=False,
            default=0,
            comment="Count of successfully sent messages",
        ),
        sa.Column(
            "messages_failed",
            sa.Integer,
            nullable=False,
            default=0,
            comment="Count of failed sends",
        ),
        sa.Column(
            "results", sa.JSON, nullable=False, comment="Detailed results per keyword"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="Timestamp of distribution",
        ),
    )

    # Create indexes for common queries
    op.create_index(
        "ix_distribution_audit_log_created_at",
        "distribution_audit_log",
        ["created_at"],
        comment="Index for ordering by creation time",
    )

    op.create_index(
        "ix_distribution_audit_log_keywords",
        "distribution_audit_log",
        ["keywords"],
        comment="Index for keyword searches",
    )


def downgrade() -> None:
    """Drop distribution audit log table."""
    op.drop_table("distribution_audit_log")
