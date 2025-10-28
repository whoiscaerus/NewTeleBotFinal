"""Create marketing clicks table for tracking CTA interactions.

Revision ID: 012_add_marketing_clicks
Created: 2025-10-28
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "012_add_marketing_clicks"
down_revision = "011_add_distribution"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create marketing clicks table."""
    op.create_table(
        "marketing_clicks",
        sa.Column("id", sa.String(36), primary_key=True, comment="Unique click ID"),
        sa.Column("user_id", sa.String(36), nullable=False, comment="Telegram user ID"),
        sa.Column("promo_id", sa.String(100), nullable=False, comment="Promo ID"),
        sa.Column("cta_text", sa.String(255), nullable=False, comment="CTA text"),
        sa.Column("chat_id", sa.Integer, nullable=True, comment="Telegram chat ID"),
        sa.Column(
            "message_id", sa.Integer, nullable=True, comment="Telegram message ID"
        ),
        sa.Column(
            "click_metadata",
            sa.JSON,
            nullable=False,
            comment="JSON metadata (conversion, source, plan, etc.)",
        ),
        sa.Column(
            "clicked_at",
            sa.DateTime,
            nullable=False,
            comment="Click timestamp (UTC)",
        ),
    )

    # Create indexes for common queries
    op.create_index("ix_marketing_clicks_user_id", "marketing_clicks", ["user_id"])
    op.create_index("ix_marketing_clicks_promo_id", "marketing_clicks", ["promo_id"])
    op.create_index(
        "ix_marketing_clicks_user_promo",
        "marketing_clicks",
        ["user_id", "promo_id"],
    )
    op.create_index(
        "ix_marketing_clicks_clicked_at", "marketing_clicks", ["clicked_at"]
    )


def downgrade() -> None:
    """Drop marketing clicks table."""
    op.drop_index("ix_marketing_clicks_clicked_at")
    op.drop_index("ix_marketing_clicks_user_promo")
    op.drop_index("ix_marketing_clicks_promo_id")
    op.drop_index("ix_marketing_clicks_user_id")
    op.drop_table("marketing_clicks")
