"""Add owner_only field to signals table

Revision ID: 0003b
Revises: 0003
Create Date: 2025-10-30

Description:
    Add encrypted owner_only JSONB field to signals table for storing
    hidden SL/TP levels and strategy metadata that should never be
    exposed to clients (anti-reselling protection).
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision = "0003b"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    """Add owner_only field to signals table."""
    # Add owner_only column (encrypted JSON storage)
    op.add_column("signals", sa.Column("owner_only", sa.Text(), nullable=True))

    # Add comment explaining purpose
    op.execute(
        """
        COMMENT ON COLUMN signals.owner_only IS
        'Encrypted owner-only data (SL/TP/strategy) - NEVER exposed to clients'
    """
    )


def downgrade():
    """Remove owner_only field from signals table."""
    op.drop_column("signals", "owner_only")
