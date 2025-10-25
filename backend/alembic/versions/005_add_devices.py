"""Add device registry for trading terminals.

Revision ID: 005_add_devices
Revises: 004_add_affiliates
Create Date: 2024-01-01 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "005_add_devices"
down_revision = "004_add_affiliates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create device registry table.

    Table:
    - devices: Trading terminal/EA device registration with HMAC auth
    """
    op.create_table(
        "devices",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("device_name", sa.String(100), nullable=False),
        sa.Column("hmac_key", sa.String(64), nullable=False),
        sa.Column("last_poll", sa.DateTime, nullable=True),
        sa.Column("last_ack", sa.DateTime, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("hmac_key"),
    )
    op.create_index("ix_devices_user_active", "devices", ["user_id", "is_active"])
    op.create_index("ix_devices_user_created", "devices", ["user_id", "created_at"])
    op.create_index("ix_devices_hmac", "devices", ["hmac_key"])


def downgrade() -> None:
    """Drop device registry table."""
    op.drop_index("ix_devices_hmac", table_name="devices")
    op.drop_index("ix_devices_user_created", table_name="devices")
    op.drop_index("ix_devices_user_active", table_name="devices")
    op.drop_table("devices")
