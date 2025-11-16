"""Add telegram_user_id to users table

Revision ID: 0002b_add_telegram_user_id
Revises: 0001
Create Date: 2025-10-30 17:20:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0002b_add_telegram_user_id"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add telegram_user_id column and last_login_at to users table."""
    # Add telegram_user_id column (nullable, unique, indexed)
    op.add_column(
        "users", sa.Column("telegram_user_id", sa.String(length=50), nullable=True)
    )
    op.create_index(
        op.f("ix_users_telegram_user_id"), "users", ["telegram_user_id"], unique=True
    )

    # Add last_login_at column (nullable)
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Remove telegram_user_id and last_login_at columns."""
    op.drop_index(op.f("ix_users_telegram_user_id"), table_name="users")
    op.drop_column("users", "telegram_user_id")
    op.drop_column("users", "last_login_at")
