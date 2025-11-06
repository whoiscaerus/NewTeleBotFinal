"""PR-057: Export tokens table

Revision ID: 0012_export_tokens
Revises: 0011_revenue_snapshots
Create Date: 2025-11-06 22:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0012_export_tokens"
down_revision = "0011_revenue_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create export_tokens table
    op.create_table(
        "export_tokens",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("format", sa.String(length=10), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("accessed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_accesses", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("last_accessed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes
    op.create_index("ix_export_tokens_user_id", "export_tokens", ["user_id"])
    op.create_index("ix_export_tokens_token", "export_tokens", ["token"], unique=True)


def downgrade() -> None:
    # Drop indexes
    op.drop_index("ix_export_tokens_token", table_name="export_tokens")
    op.drop_index("ix_export_tokens_user_id", table_name="export_tokens")

    # Drop table
    op.drop_table("export_tokens")
