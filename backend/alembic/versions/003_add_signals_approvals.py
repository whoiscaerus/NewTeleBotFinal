"""Add signals and approvals tables.

Revision ID: 003
Revises: 002
Create Date: 2025-10-25 10:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create signals and approvals tables."""
    # Create signals table
    op.create_table(
        "signals",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("instrument", sa.String(20), nullable=False),
        sa.Column("side", sa.Integer(), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("status", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("external_id", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_id", name="uq_signals_external_id"),
    )
    op.create_index("ix_signal_user_created", "signals", ["user_id", "created_at"])
    op.create_index("ix_signal_instrument_status", "signals", ["instrument", "status"])
    op.create_index("ix_signal_external", "signals", ["external_id"])
    op.create_index("ix_signals_user_id", "signals", ["user_id"])

    # Create approvals table
    op.create_table(
        "approvals",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("signal_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("decision", sa.Integer(), nullable=False),
        sa.Column("consent_version", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["signal_id"], ["signals.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_approval_user_created", "approvals", ["user_id", "created_at"])
    op.create_index("ix_approval_signal_user", "approvals", ["signal_id", "user_id"])


def downgrade() -> None:
    """Drop signals and approvals tables."""
    op.drop_index("ix_approval_signal_user", table_name="approvals")
    op.drop_index("ix_approval_user_created", table_name="approvals")
    op.drop_table("approvals")

    op.drop_index("ix_signals_user_id", table_name="signals")
    op.drop_index("ix_signal_external", table_name="signals")
    op.drop_index("ix_signal_instrument_status", table_name="signals")
    op.drop_index("ix_signal_user_created", table_name="signals")
    op.drop_table("signals")
