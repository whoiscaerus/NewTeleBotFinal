"""PR-023a: Add clients and devices tables for device registry.

Revision ID: 0005_clients_devices
Revises: 0004_approvals
Create Date: 2025-10-26 10:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0005_clients_devices"
down_revision = "0004_approvals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create clients and devices tables for device registry."""
    # Create clients table
    op.create_table(
        "clients",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("telegram_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="ix_clients_email_unique"),
        sa.UniqueConstraint("user_id", name="ix_clients_user_id_unique"),
    )

    # Create index on user_id for fast lookups
    op.create_index("ix_clients_user_id", "clients", ["user_id"])
    op.create_index("ix_clients_created_at", "clients", ["created_at"])

    # Create devices table
    op.create_table(
        "devices",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("client_id", sa.String(36), nullable=False),
        sa.Column("device_name", sa.String(100), nullable=False),
        sa.Column("hmac_key_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["client_id"],
            ["clients.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "client_id", "device_name", name="ix_devices_client_name_unique"
        ),
        sa.UniqueConstraint("hmac_key_hash", name="ix_devices_hmac_unique"),
    )

    # Create indexes for efficient queries
    op.create_index("ix_devices_client_id", "devices", ["client_id"])
    op.create_index("ix_devices_is_active", "devices", ["is_active"])
    op.create_index("ix_devices_created_at", "devices", ["created_at"])
    op.create_index("ix_devices_last_seen", "devices", ["last_seen"])

    # Create composite index for common queries
    op.create_index(
        "ix_devices_client_active",
        "devices",
        ["client_id", "is_active"],
    )


def downgrade() -> None:
    """Drop clients and devices tables."""
    # Drop indexes
    op.drop_index("ix_devices_client_active", table_name="devices")
    op.drop_index("ix_devices_last_seen", table_name="devices")
    op.drop_index("ix_devices_created_at", table_name="devices")
    op.drop_index("ix_devices_is_active", table_name="devices")
    op.drop_index("ix_devices_client_id", table_name="devices")

    # Drop devices table
    op.drop_table("devices")

    # Drop clients indexes
    op.drop_index("ix_clients_created_at", table_name="clients")
    op.drop_index("ix_clients_user_id", table_name="clients")

    # Drop clients table
    op.drop_table("clients")
