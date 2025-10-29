"""Add revoked column to devices table.

Revision ID: 013
Revises: 012_add_marketing_clicks
Create Date: 2025-10-29 08:52:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "013_add_device_revoked"
down_revision = "012_add_marketing_clicks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add revoked column to devices table."""
    op.add_column(
        "devices",
        sa.Column(
            "revoked",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
            doc="Whether device has been revoked (permanent disable)",
        ),
    )
    op.create_index("ix_devices_revoked", "devices", ["revoked"])


def downgrade() -> None:
    """Remove revoked column from devices table."""
    op.drop_index("ix_devices_revoked", table_name="devices")
    op.drop_column("devices", "revoked")
