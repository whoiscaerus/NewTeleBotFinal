"""PR-073: Add decision logs for trade audit trails

Revision ID: 073_decision_logs
Revises: 066_journey_automation
Create Date: 2025-11-08

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = "073_decision_logs"
down_revision = "066_journey_automation"
branch_labels = None
depends_on = None


def upgrade():
    """Create decision_logs table for PR-073."""

    # Create decision outcome enum
    op.execute(
        """
        CREATE TYPE decision_outcome_enum AS ENUM (
            'entered',
            'skipped',
            'rejected',
            'pending',
            'error'
        )
        """
    )

    # Create decision_logs table
    op.create_table(
        "decision_logs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False, index=True),
        sa.Column("strategy", sa.String(100), nullable=False, index=True),
        sa.Column("symbol", sa.String(20), nullable=False, index=True),
        sa.Column("features", JSONB, nullable=False),
        sa.Column(
            "outcome",
            sa.Enum(
                "entered",
                "skipped",
                "rejected",
                "pending",
                "error",
                name="decision_outcome_enum",
            ),
            nullable=False,
            index=True,
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create composite indexes for common query patterns
    op.create_index(
        "ix_decision_logs_strategy_timestamp",
        "decision_logs",
        ["strategy", "timestamp"],
    )
    op.create_index(
        "ix_decision_logs_symbol_timestamp", "decision_logs", ["symbol", "timestamp"]
    )
    op.create_index(
        "ix_decision_logs_outcome_timestamp", "decision_logs", ["outcome", "timestamp"]
    )
    op.create_index(
        "ix_decision_logs_strategy_symbol_timestamp",
        "decision_logs",
        ["strategy", "symbol", "timestamp"],
    )


def downgrade():
    """Drop decision_logs table and enum."""

    # Drop indexes
    op.drop_index("ix_decision_logs_strategy_symbol_timestamp", "decision_logs")
    op.drop_index("ix_decision_logs_outcome_timestamp", "decision_logs")
    op.drop_index("ix_decision_logs_symbol_timestamp", "decision_logs")
    op.drop_index("ix_decision_logs_strategy_timestamp", "decision_logs")

    # Drop table
    op.drop_table("decision_logs")

    # Drop enum
    op.execute("DROP TYPE decision_outcome_enum")
