"""
PR-069: Internationalization & Copy Registry

Revision ID: 0015_i18n_copy_registry
Revises: 0014_privacy_requests
Create Date: 2025-11-08
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "0015_i18n_copy_registry"
down_revision = "0014_privacy_requests"
branch_labels = None
depends_on = None


def upgrade():
    """Create copy registry tables."""
    # Create copy_entries table
    op.create_table(
        "copy_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("key", sa.String(255), nullable=False, unique=True),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("created_by", sa.String(36), nullable=True),
        sa.Column("updated_by", sa.String(36), nullable=True),
    )

    # Create indexes for copy_entries
    op.create_index("ix_copy_entries_key", "copy_entries", ["key"])
    op.create_index("ix_copy_entries_type_status", "copy_entries", ["type", "status"])

    # Create copy_variants table
    op.create_table(
        "copy_variants",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "entry_id",
            sa.String(36),
            sa.ForeignKey("copy_entries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("locale", sa.String(10), nullable=False),
        sa.Column("ab_group", sa.String(50), nullable=True),
        sa.Column("is_control", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("impressions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("conversions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("conversion_rate", sa.Float(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")
        ),
    )

    # Create indexes for copy_variants
    op.create_index("ix_copy_variants_locale", "copy_variants", ["locale"])
    op.create_index(
        "ix_copy_variants_entry_locale", "copy_variants", ["entry_id", "locale"]
    )
    op.create_index(
        "ix_copy_variants_entry_ab", "copy_variants", ["entry_id", "ab_group"]
    )


def downgrade():
    """Drop copy registry tables."""
    # Drop indexes first
    op.drop_index("ix_copy_variants_entry_ab", "copy_variants")
    op.drop_index("ix_copy_variants_entry_locale", "copy_variants")
    op.drop_index("ix_copy_variants_locale", "copy_variants")
    op.drop_index("ix_copy_entries_type_status", "copy_entries")
    op.drop_index("ix_copy_entries_key", "copy_entries")

    # Drop tables
    op.drop_table("copy_variants")
    op.drop_table("copy_entries")
