"""0011_revenue_snapshots

Revision ID: 0011
Revises: 0010
Create Date: 2025-11-01 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create revenue snapshot and cohort tables."""
    # Create revenue_snapshots table
    op.create_table(
        "revenue_snapshots",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("mrr_gbp", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("arr_gbp", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column(
            "active_subscribers", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "annual_plan_subscribers", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "monthly_plan_subscribers", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "churned_this_month", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "churn_rate_percent", sa.Float(), nullable=False, server_default="0.0"
        ),
        sa.Column("arpu_gbp", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("cohorts_by_month", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("snapshot_date"),
    )
    op.create_index("ix_revenue_snapshots_date", "revenue_snapshots", ["snapshot_date"])

    # Create subscription_cohorts table
    op.create_table(
        "subscription_cohorts",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("cohort_month", sa.String(7), nullable=False),
        sa.Column(
            "initial_subscribers", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("retention_data", sa.JSON(), nullable=False),
        sa.Column(
            "month_0_revenue_gbp", sa.Float(), nullable=False, server_default="0.0"
        ),
        sa.Column(
            "total_revenue_gbp", sa.Float(), nullable=False, server_default="0.0"
        ),
        sa.Column(
            "average_lifetime_value_gbp",
            sa.Float(),
            nullable=False,
            server_default="0.0",
        ),
        sa.Column("churn_rate_by_month", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cohort_month"),
    )
    op.create_index("ix_cohorts_month", "subscription_cohorts", ["cohort_month"])


def downgrade() -> None:
    """Drop revenue snapshot and cohort tables."""
    op.drop_index("ix_cohorts_month", table_name="subscription_cohorts")
    op.drop_table("subscription_cohorts")
    op.drop_index("ix_revenue_snapshots_date", table_name="revenue_snapshots")
    op.drop_table("revenue_snapshots")
