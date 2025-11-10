"""
Add upsell tables.

Revision ID: 097_upsell_engine
Revises: 094_social_verification
Create Date: 2025-11-10 12:00:00
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision = "097_upsell_engine"
down_revision = "094_social_verification"
branch_labels = None
depends_on = None


def upgrade():
    """Create upsell tables."""
    # Experiments table
    op.create_table(
        "experiments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("recommendation_type", sa.String(50), nullable=False),
        sa.Column(
            "traffic_split_percent", sa.Integer, nullable=False, server_default="50"
        ),
        sa.Column("min_sample_size", sa.Integer, nullable=False, server_default="100"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("min_ctr", sa.Float, nullable=True),
        sa.Column("max_duration_days", sa.Integer, nullable=True),
        sa.Column("control_exposures", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "control_conversions", sa.Integer, nullable=False, server_default="0"
        ),
        sa.Column("variant_exposures", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "variant_conversions", sa.Integer, nullable=False, server_default="0"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "traffic_split_percent >= 0 AND traffic_split_percent <= 100",
            name="ck_experiment_split_range",
        ),
    )
    op.create_index("ix_experiments_status", "experiments", ["status"])
    op.create_index("ix_experiments_type", "experiments", ["recommendation_type"])

    # Variants table
    op.create_table(
        "variants",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "experiment_id",
            sa.String(36),
            sa.ForeignKey("experiments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("headline", sa.String(200), nullable=False),
        sa.Column("copy", sa.Text, nullable=False),
        sa.Column(
            "cta_text", sa.String(100), nullable=False, server_default="Upgrade Now"
        ),
        sa.Column("discount_percent", sa.Integer, nullable=True),
        sa.Column("is_control", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "discount_percent IS NULL OR (discount_percent >= 0 AND discount_percent <= 100)",
            name="ck_variant_discount_range",
        ),
    )
    op.create_index("ix_variants_experiment", "variants", ["experiment_id"])
    op.create_index("ix_variants_control", "variants", ["is_control"])

    # Recommendations table
    op.create_table(
        "recommendations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("recommendation_type", sa.String(50), nullable=False),
        sa.Column("score", sa.Float, nullable=False),
        sa.Column(
            "variant_id",
            sa.String(36),
            sa.ForeignKey("variants.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("usage_score", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("performance_score", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("intent_score", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("cohort_score", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("headline", sa.String(200), nullable=False),
        sa.Column("copy", sa.Text, nullable=False),
        sa.Column("discount_percent", sa.Integer, nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("shown", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("clicked", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("converted", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("shown_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clicked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("converted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "score >= 0.0 AND score <= 1.0", name="ck_recommendation_score_range"
        ),
        sa.CheckConstraint(
            "discount_percent IS NULL OR (discount_percent >= 0 AND discount_percent <= 100)",
            name="ck_recommendation_discount_range",
        ),
    )
    op.create_index(
        "ix_recommendations_user_type",
        "recommendations",
        ["user_id", "recommendation_type"],
    )
    op.create_index("ix_recommendations_score", "recommendations", ["score"])
    op.create_index("ix_recommendations_created", "recommendations", ["created_at"])

    # Exposures table
    op.create_table(
        "exposures",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "experiment_id",
            sa.String(36),
            sa.ForeignKey("experiments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "variant_id",
            sa.String(36),
            sa.ForeignKey("variants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "recommendation_id",
            sa.String(36),
            sa.ForeignKey("recommendations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("converted", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("converted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("channel", sa.String(50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_exposures_user_experiment",
        "exposures",
        ["user_id", "experiment_id"],
        unique=True,
    )
    op.create_index("ix_exposures_variant", "exposures", ["variant_id"])
    op.create_index("ix_exposures_converted", "exposures", ["converted"])
    op.create_index("ix_exposures_created", "exposures", ["created_at"])


def downgrade():
    """Drop upsell tables."""
    op.drop_table("exposures")
    op.drop_table("recommendations")
    op.drop_table("variants")
    op.drop_table("experiments")
