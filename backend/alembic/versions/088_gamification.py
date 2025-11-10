"""PR-088: Add gamification tables for badges, levels, and leaderboard

Revision ID: 088_gamification
Revises: 073_decision_logs
Create Date: 2025-11-09

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "088_gamification"
down_revision = "073_decision_logs"
branch_labels = None
depends_on = None


def upgrade():
    """Create gamification tables for PR-088."""

    # Create badges table
    op.create_table(
        "badges",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("icon", sa.String(50), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("xp_reward", sa.Integer(), nullable=False, default=100),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_badges_name", "badges", ["name"])
    op.create_index("ix_badges_category", "badges", ["category"])

    # Create earned_badges table
    op.create_table(
        "earned_badges",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("badge_id", sa.String(36), nullable=False),
        sa.Column(
            "earned_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("context", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["badge_id"], ["badges.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "badge_id", name="uq_user_badge"),
    )
    op.create_index("ix_earned_badges_user_id", "earned_badges", ["user_id"])
    op.create_index("ix_earned_badges_badge_id", "earned_badges", ["badge_id"])
    op.create_index(
        "ix_earned_badges_user_earned_at", "earned_badges", ["user_id", "earned_at"]
    )

    # Create levels table
    op.create_table(
        "levels",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(50), nullable=False, unique=True),
        sa.Column("min_xp", sa.Integer(), nullable=False, unique=True),
        sa.Column("max_xp", sa.Integer(), nullable=True),
        sa.Column("icon", sa.String(50), nullable=False),
        sa.Column("color", sa.String(20), nullable=False),
        sa.Column("perks", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_levels_name", "levels", ["name"])
    op.create_index("ix_levels_min_xp", "levels", ["min_xp"])

    # Create leaderboard_optins table
    op.create_table(
        "leaderboard_optins",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False, unique=True),
        sa.Column("opted_in", sa.Boolean(), nullable=False, default=True),
        sa.Column("display_name", sa.String(50), nullable=True),
        sa.Column(
            "opted_in_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("opted_out_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_leaderboard_opted_in", "leaderboard_optins", ["opted_in"])


def downgrade():
    """Drop gamification tables."""

    op.drop_table("leaderboard_optins")
    op.drop_table("earned_badges")
    op.drop_table("levels")
    op.drop_table("badges")
