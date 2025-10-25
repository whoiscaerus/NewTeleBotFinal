"""Add execution store for device reporting.

Revision ID: 006_add_execution_store
Revises: 005_add_devices
Create Date: 2024-01-01 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "006_add_execution_store"
down_revision = "005_add_devices"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create execution store table.

    Table:
    - execution_records: Device execution reports (ACKs, fills, errors)
    """
    op.create_table(
        "execution_records",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("device_id", sa.String(36), nullable=False),
        sa.Column("signal_id", sa.String(36), nullable=False),
        sa.Column("trade_id", sa.String(36), nullable=True),
        sa.Column("execution_type", sa.Integer, nullable=False),
        sa.Column("status_code", sa.Integer, nullable=True),
        sa.Column("error_message", sa.String(255), nullable=True),
        sa.Column("fill_price", sa.Float, nullable=True),
        sa.Column("fill_size", sa.Float, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"]),
        sa.ForeignKeyConstraint(["signal_id"], ["signals.id"]),
        sa.ForeignKeyConstraint(["trade_id"], ["trades.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_execution_records_device_created",
        "execution_records",
        ["device_id", "created_at"],
    )
    op.create_index(
        "ix_execution_records_signal_type",
        "execution_records",
        ["signal_id", "execution_type"],
    )
    op.create_index("ix_execution_records_trade", "execution_records", ["trade_id"])


def downgrade() -> None:
    """Drop execution store table."""
    op.drop_index("ix_execution_records_trade", table_name="execution_records")
    op.drop_index("ix_execution_records_signal_type", table_name="execution_records")
    op.drop_index("ix_execution_records_device_created", table_name="execution_records")
    op.drop_table("execution_records")
