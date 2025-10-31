"""Create open_positions table

Revision ID: 0007
Revises: 0006
Create Date: 2025-10-30

Description:
    Create open_positions table for server-side position tracking with
    hidden owner SL/TP levels. Enables auto-close when owner's levels
    are hit while hiding exit strategy from clients (anti-reselling).
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    """Create open_positions table."""
    op.create_table(
        "open_positions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "execution_id",
            sa.String(36),
            sa.ForeignKey("executions.id"),
            nullable=False,
        ),
        sa.Column(
            "signal_id", sa.String(36), sa.ForeignKey("signals.id"), nullable=False
        ),
        sa.Column(
            "approval_id", sa.String(36), sa.ForeignKey("approvals.id"), nullable=False
        ),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "device_id", sa.String(36), sa.ForeignKey("devices.id"), nullable=False
        ),
        # Trade details
        sa.Column("instrument", sa.String(20), nullable=False),
        sa.Column("side", sa.Integer, nullable=False),
        sa.Column("entry_price", sa.Float, nullable=False),
        sa.Column("volume", sa.Float, nullable=False),
        sa.Column("broker_ticket", sa.String(128), nullable=True),
        # Hidden owner levels (NEVER exposed to clients)
        sa.Column("owner_sl", sa.Float, nullable=True),
        sa.Column("owner_tp", sa.Float, nullable=True),
        # Status tracking
        sa.Column("status", sa.Integer, nullable=False, default=0),
        sa.Column(
            "opened_at", sa.DateTime, nullable=False, server_default=sa.func.now()
        ),
        sa.Column("closed_at", sa.DateTime, nullable=True),
        sa.Column("close_price", sa.Float, nullable=True),
        sa.Column("close_reason", sa.String(255), nullable=True),
    )

    # Create indexes
    op.create_index(
        "ix_open_positions_execution_id", "open_positions", ["execution_id"]
    )
    op.create_index("ix_open_positions_signal_id", "open_positions", ["signal_id"])
    op.create_index("ix_open_positions_approval_id", "open_positions", ["approval_id"])
    op.create_index("ix_open_positions_user_id", "open_positions", ["user_id"])
    op.create_index("ix_open_positions_device_id", "open_positions", ["device_id"])
    op.create_index("ix_open_positions_instrument", "open_positions", ["instrument"])
    op.create_index(
        "ix_open_positions_broker_ticket", "open_positions", ["broker_ticket"]
    )
    op.create_index("ix_open_positions_status", "open_positions", ["status"])
    op.create_index(
        "ix_open_positions_user_status", "open_positions", ["user_id", "status"]
    )
    op.create_index(
        "ix_open_positions_instrument_status",
        "open_positions",
        ["instrument", "status"],
    )
    op.create_index("ix_open_positions_opened_at", "open_positions", ["opened_at"])

    # Add comments
    op.execute(
        """
        COMMENT ON TABLE open_positions IS
        'Server-side position tracking with hidden owner SL/TP for auto-close'
    """
    )
    op.execute(
        """
        COMMENT ON COLUMN open_positions.owner_sl IS
        'Hidden stop loss level - NEVER exposed to client APIs'
    """
    )
    op.execute(
        """
        COMMENT ON COLUMN open_positions.owner_tp IS
        'Hidden take profit level - NEVER exposed to client APIs'
    """
    )


def downgrade():
    """Drop open_positions table."""
    op.drop_table("open_positions")
