"""Add risk management tables: risk_profiles and exposure_snapshots.

Revision ID: 048_add_risk_tables
Revises:
Create Date: 2025-11-01 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "048_add_risk_tables"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create risk_profiles and exposure_snapshots tables."""

    # Create risk_profiles table
    op.create_table(
        "risk_profiles",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("client_id", sa.String(36), nullable=False),
        sa.Column(
            "max_drawdown_percent",
            sa.Numeric(precision=5, scale=2),
            nullable=False,
            server_default="20.00",
        ),
        sa.Column("max_daily_loss", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column(
            "max_position_size",
            sa.Numeric(precision=10, scale=2),
            nullable=False,
            server_default="1.0",
        ),
        sa.Column(
            "max_open_positions", sa.Integer(), nullable=False, server_default="5"
        ),
        sa.Column(
            "max_correlation_exposure",
            sa.Numeric(precision=5, scale=2),
            nullable=False,
            server_default="0.70",
        ),
        sa.Column(
            "risk_per_trade_percent",
            sa.Numeric(precision=5, scale=2),
            nullable=False,
            server_default="2.00",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_risk_profiles")),
        sa.UniqueConstraint("client_id", name=op.f("uq_risk_profiles_client_id")),
    )

    op.create_index(
        op.f("ix_risk_profiles_client_id"),
        "risk_profiles",
        ["client_id"],
        unique=False,
    )

    # Create exposure_snapshots table
    op.create_table(
        "exposure_snapshots",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("client_id", sa.String(36), nullable=False),
        sa.Column(
            "timestamp",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "total_exposure",
            sa.Numeric(precision=10, scale=2),
            nullable=False,
            server_default="0.0",
        ),
        sa.Column(
            "exposure_by_instrument",
            postgresql.JSON(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "exposure_by_direction",
            postgresql.JSON(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "open_positions_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "current_drawdown_percent",
            sa.Numeric(precision=5, scale=2),
            nullable=False,
            server_default="0.0",
        ),
        sa.Column(
            "daily_pnl",
            sa.Numeric(precision=10, scale=2),
            nullable=False,
            server_default="0.0",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_exposure_snapshots")),
    )

    op.create_index(
        op.f("ix_exposure_snapshots_client_timestamp"),
        "exposure_snapshots",
        ["client_id", "timestamp"],
        unique=False,
    )

    op.create_index(
        op.f("ix_exposure_snapshots_client_latest"),
        "exposure_snapshots",
        ["client_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop risk management tables."""
    op.drop_index(
        op.f("ix_exposure_snapshots_client_latest"),
        table_name="exposure_snapshots",
    )
    op.drop_index(
        op.f("ix_exposure_snapshots_client_timestamp"),
        table_name="exposure_snapshots",
    )
    op.drop_table("exposure_snapshots")

    op.drop_index(op.f("ix_risk_profiles_client_id"), table_name="risk_profiles")
    op.drop_table("risk_profiles")
