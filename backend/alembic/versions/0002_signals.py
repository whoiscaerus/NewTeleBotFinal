"""Create signals table with JSONB payload support.

Revision ID: 0002_signals
Revises: 0001_baseline
Create Date: 2025-10-23 10:00:00.000000

This migration creates the signals table for trading signal ingestion with:
- UUID primary key
- JSONB payload for strategy data
- Indexes for common queries (instrument, time, status)
- Timestamps with automatic updates
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0002_signals"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create signals table and indexes."""
    # Create the signals table
    op.create_table(
        "signals",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column(
            "instrument",
            sa.String(20),
            nullable=False,
        ),
        sa.Column("side", sa.Integer(), nullable=False),
        sa.Column(
            "time",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "payload",
            postgresql.JSON(),
            nullable=True,
        ),
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default=sa.literal(1),
        ),
        sa.Column(
            "status",
            sa.Integer(),
            nullable=False,
            server_default=sa.literal(0),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes for common queries
    op.create_index(
        "ix_signals_instrument_time",
        "signals",
        ["instrument", "time"],
        unique=False,
    )
    op.create_index(
        "ix_signals_status",
        "signals",
        ["status"],
        unique=False,
    )

    # Create trigger for automatic updated_at timestamp
    op.execute(
        """
        CREATE OR REPLACE FUNCTION update_signals_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER signals_updated_at_trigger
        BEFORE UPDATE ON signals
        FOR EACH ROW
        EXECUTE PROCEDURE update_signals_updated_at();
        """
    )


def downgrade() -> None:
    """Drop signals table and all related objects."""
    # Drop trigger and function
    op.execute("DROP TRIGGER IF EXISTS signals_updated_at_trigger ON signals;")
    op.execute(
        "DROP FUNCTION IF EXISTS update_signals_updated_at();"
    )

    # Drop indexes
    op.drop_index("ix_signals_time", table_name="signals")
    op.drop_index("ix_signals_status", table_name="signals")
    op.drop_index("ix_signals_instrument", table_name="signals")
    op.drop_index("ix_signals_instrument_time", table_name="signals")

    # Drop table
    op.drop_table("signals")
