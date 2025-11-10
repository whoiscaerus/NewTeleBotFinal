"""PR-091: Add feature_flags table for AI Analyst toggle

Revision ID: 091_feature_flags
Revises: 090_user_theme
Create Date: 2024-01-15
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = "091_feature_flags"
down_revision = "090_user_theme"
branch_labels = None
depends_on = None


def upgrade():
    """Add feature_flags table for owner-controlled feature toggles."""
    # Create feature_flags table
    op.create_table(
        "feature_flags",
        sa.Column("name", sa.String(100), primary_key=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("owner_only", sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "updated_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.Column("updated_by", sa.String(36), nullable=True),  # User ID who toggled
        sa.Column("description", sa.Text, nullable=True),  # Feature description
    )

    # Create index on enabled for fast lookups
    op.create_index("ix_feature_flags_enabled", "feature_flags", ["enabled"])

    # Insert default row for AI Analyst (disabled, owner-only)
    op.execute(
        """
        INSERT INTO feature_flags (name, enabled, owner_only, description)
        VALUES (
            'ai_analyst',
            FALSE,
            TRUE,
            'Daily AI-written Market Outlook with volatility zones and correlations'
        )
    """
    )


def downgrade():
    """Drop feature_flags table."""
    op.drop_index("ix_feature_flags_enabled", table_name="feature_flags")
    op.drop_table("feature_flags")
