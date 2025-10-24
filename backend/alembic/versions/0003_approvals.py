"""Create approvals table.

Revision ID: 0003_approvals
Revises: 0002_signals
Create Date: 2025-10-24 23:59:59.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0003_approvals"
down_revision = "0002_signals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create approvals table with audit trail and duplicate prevention."""
    op.create_table(
        "approvals",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("signal_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("device_id", sa.String(36), nullable=True),
        sa.Column("decision", sa.SmallInteger(), nullable=False),
        sa.Column("consent_version", sa.Text(), nullable=False),
        sa.Column("ip", sa.String(45), nullable=True),
        sa.Column("ua", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["signal_id"], ["signals.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create unique index on signal_id, user_id to prevent duplicate approvals
    op.create_index(
        "ix_approvals_signal_user",
        "approvals",
        ["signal_id", "user_id"],
        unique=True,
    )

    # Create index on user_id, created_at for efficient queries
    op.create_index(
        "ix_approvals_user_created", "approvals", ["user_id", "created_at"]
    )

    # Create index on signal_id for efficient lookups
    op.create_index("ix_approvals_signal", "approvals", ["signal_id"])


def downgrade() -> None:
    """Drop approvals table and indexes."""
    op.drop_index("ix_approvals_signal", table_name="approvals")
    op.drop_index("ix_approvals_user_created", table_name="approvals")
    op.drop_index("ix_approvals_signal_user", table_name="approvals")
    op.drop_table("approvals")
