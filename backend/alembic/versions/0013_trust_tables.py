"""Add trust scoring tables: endorsements, user_trust_scores, calculation logs.

Revision ID: 0013_trust_tables
Revises: 0012_previous_migration
Create Date: 2025-11-01

Tables:
- endorsements: User-to-user verification of trading ability
- user_trust_scores: Cached computed trust scores
- trust_calculation_logs: Audit trail of score calculations
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0013_trust_tables"
down_revision = "0012_previous_migration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create trust scoring tables."""

    # Endorsements table
    op.create_table(
        "endorsements",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("endorser_id", sa.String(36), nullable=False),
        sa.Column("endorsee_id", sa.String(36), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False, server_default="0.3"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["endorsee_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["endorser_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_endorsements_endorsee_created",
        "endorsements",
        ["endorsee_id", "created_at"],
    )
    op.create_index(
        "ix_endorsements_endorser_created",
        "endorsements",
        ["endorser_id", "created_at"],
    )
    op.create_index("ix_endorsements_endorsee_id", "endorsements", ["endorsee_id"])
    op.create_index("ix_endorsements_endorser_id", "endorsements", ["endorser_id"])
    op.create_index("ix_endorsements_created_at", "endorsements", ["created_at"])

    # User trust scores table
    op.create_table(
        "user_trust_scores",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column(
            "performance_component", sa.Float(), nullable=False, server_default="0.0"
        ),
        sa.Column("tenure_component", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column(
            "endorsement_component", sa.Float(), nullable=False, server_default="0.0"
        ),
        sa.Column("tier", sa.String(20), nullable=False, server_default="bronze"),
        sa.Column("percentile", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "calculated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "valid_until", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_user_trust_scores_user_id", "user_trust_scores", ["user_id"])
    op.create_index("ix_trust_scores_tier", "user_trust_scores", ["tier"])
    op.create_index("ix_trust_scores_score", "user_trust_scores", ["score"])

    # Trust calculation logs table
    op.create_table(
        "trust_calculation_logs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("previous_score", sa.Float(), nullable=True),
        sa.Column("new_score", sa.Float(), nullable=False),
        sa.Column(
            "input_graph_nodes", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "input_graph_edges", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "algorithm_version", sa.String(20), nullable=False, server_default="1.0"
        ),
        sa.Column(
            "calculated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_calc_logs_user_id", "trust_calculation_logs", ["user_id"])
    op.create_index(
        "ix_calc_logs_calculated_at", "trust_calculation_logs", ["calculated_at"]
    )
    op.create_index(
        "ix_calc_logs_user_date", "trust_calculation_logs", ["user_id", "calculated_at"]
    )


def downgrade() -> None:
    """Drop trust scoring tables."""

    op.drop_index("ix_calc_logs_user_date", table_name="trust_calculation_logs")
    op.drop_index("ix_calc_logs_calculated_at", table_name="trust_calculation_logs")
    op.drop_index("ix_calc_logs_user_id", table_name="trust_calculation_logs")
    op.drop_table("trust_calculation_logs")

    op.drop_index("ix_trust_scores_score", table_name="user_trust_scores")
    op.drop_index("ix_trust_scores_tier", table_name="user_trust_scores")
    op.drop_index("ix_user_trust_scores_user_id", table_name="user_trust_scores")
    op.drop_table("user_trust_scores")

    op.drop_index("ix_endorsements_created_at", table_name="endorsements")
    op.drop_index("ix_endorsements_endorser_id", table_name="endorsements")
    op.drop_index("ix_endorsements_endorsee_id", table_name="endorsements")
    op.drop_index("ix_endorsements_endorser_created", table_name="endorsements")
    op.drop_index("ix_endorsements_endorsee_created", table_name="endorsements")
    op.drop_table("endorsements")
