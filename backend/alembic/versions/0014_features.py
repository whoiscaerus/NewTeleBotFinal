"""Create feature_snapshots table for PR-079.

Feature Store & Data Quality Monitor

Revision ID: 0014_features
Revises: 0013_knowledge_base
Create Date: 2025-11-09 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "0014_features"
down_revision: Union[str, None] = "0013_knowledge_base"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create feature_snapshots table with indexes."""
    op.create_table(
        "feature_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("features", JSONB, nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # Single-column indexes
    op.create_index(
        op.f("ix_feature_snapshots_symbol"),
        "feature_snapshots",
        ["symbol"],
        unique=False,
    )
    op.create_index(
        op.f("ix_feature_snapshots_timestamp"),
        "feature_snapshots",
        ["timestamp"],
        unique=False,
    )

    # Composite indexes for common queries
    op.create_index(
        "ix_features_symbol_timestamp",
        "feature_snapshots",
        ["symbol", "timestamp"],
        unique=False,
    )
    op.create_index(
        "ix_features_symbol_quality",
        "feature_snapshots",
        ["symbol", "quality_score"],
        unique=False,
    )

    # Descending index for latest queries
    op.create_index(
        "ix_features_timestamp_desc",
        "feature_snapshots",
        [sa.text("timestamp DESC")],
        unique=False,
    )


def downgrade() -> None:
    """Drop feature_snapshots table and indexes."""
    op.drop_index("ix_features_timestamp_desc", table_name="feature_snapshots")
    op.drop_index("ix_features_symbol_quality", table_name="feature_snapshots")
    op.drop_index("ix_features_symbol_timestamp", table_name="feature_snapshots")
    op.drop_index(
        op.f("ix_feature_snapshots_timestamp"), table_name="feature_snapshots"
    )
    op.drop_index(op.f("ix_feature_snapshots_symbol"), table_name="feature_snapshots")
    op.drop_table("feature_snapshots")
