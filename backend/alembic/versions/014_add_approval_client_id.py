"""add_client_id_to_approvals

Revision ID: 014_add_approval_client_id
Revises: 013_add_device_revoked
Create Date: 2025-10-29 17:20:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "014_add_approval_client_id"
down_revision = "013_add_device_revoked"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add client_id column to approvals table
    op.add_column("approvals", sa.Column("client_id", sa.String(36), nullable=True))

    # Create the indexes
    op.create_index(
        "ix_approval_client_created", "approvals", ["client_id", "created_at"]
    )
    op.create_index(
        "ix_approval_client_decision", "approvals", ["client_id", "decision"]
    )

    # NOTE: Keeping client_id nullable for now since:
    # 1. Business logic hasn't defined where client_id comes from
    # 2. Signal model doesn't have client_id field to derive from
    # 3. Tests don't provide client_id in approval creation
    # TODO: In future, determine if client_id should come from:
    #   - Request headers (device identifier)
    #   - User account (primary device)
    #   - Signal metadata
    # Then populate existing records and make NOT NULL


def downgrade() -> None:
    # Drop indexes
    op.drop_index("ix_approval_client_decision", "approvals")
    op.drop_index("ix_approval_client_created", "approvals")

    # Drop column
    op.drop_column("approvals", "client_id")
