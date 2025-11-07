"""Create Knowledge Base tables

Revision ID: 0013_knowledge_base
Revises:
Create Date: 2025-01-15 10:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0013_knowledge_base"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create kb_tags table
    op.create_table(
        "kb_tags",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_kb_tags_name"),
        sa.UniqueConstraint("slug", name="uq_kb_tags_slug"),
    )
    op.create_index("ix_kb_tags_name", "kb_tags", ["name"])
    op.create_index("ix_kb_tags_slug", "kb_tags", ["slug"])

    # Create kb_articles table
    op.create_table(
        "kb_articles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("slug", sa.String(500), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("draft", "published", "archived", name="articlestatus"),
            nullable=False,
        ),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("locale", sa.String(10), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("requires_approval", sa.Boolean(), nullable=False),
        sa.Column("approved_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("approval_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
        sa.Column("meta", postgresql.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", "locale", name="uq_kb_articles_slug_locale"),
    )
    op.create_index(
        "ix_kb_articles_status_published_at", "kb_articles", ["status", "published_at"]
    )
    op.create_index("ix_kb_articles_locale", "kb_articles", ["locale"])
    op.create_index("ix_kb_articles_author_id", "kb_articles", ["author_id"])
    op.create_index("ix_kb_articles_slug", "kb_articles", ["slug"])
    op.create_index("ix_kb_articles_status", "kb_articles", ["status"])

    # Create kb_article_tags association table
    op.create_table(
        "kb_article_tags",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("article_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tag_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["article_id"],
            ["kb_articles.id"],
        ),
        sa.ForeignKeyConstraint(
            ["tag_id"],
            ["kb_tags.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_kb_article_tags_article_id", "kb_article_tags", ["article_id"])

    # Create kb_article_versions table
    op.create_table(
        "kb_article_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("article_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("draft", "published", "archived", name="articlestatus"),
            nullable=False,
        ),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("change_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["article_id"],
            ["kb_articles.id"],
        ),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_kb_article_versions_article_id", "kb_article_versions", ["article_id"]
    )
    op.create_index(
        "ix_kb_article_versions_version",
        "kb_article_versions",
        ["article_id", "version"],
    )

    # Create kb_attachments table
    op.create_table(
        "kb_attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("article_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("file_type", sa.String(50), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("s3_key", sa.String(500), nullable=False),
        sa.Column("uploaded_by_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["article_id"],
            ["kb_articles.id"],
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("s3_key", name="uq_kb_attachments_s3_key"),
    )
    op.create_index("ix_kb_attachments_article_id", "kb_attachments", ["article_id"])

    # Create kb_article_views table
    op.create_table(
        "kb_article_views",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("article_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("locale", sa.String(10), nullable=False),
        sa.Column("viewed_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["article_id"],
            ["kb_articles.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_kb_article_views_article_id_viewed_at",
        "kb_article_views",
        ["article_id", "viewed_at"],
    )
    op.create_index("ix_kb_article_views_user_id", "kb_article_views", ["user_id"])


def downgrade() -> None:
    # Drop indexes
    op.drop_index("ix_kb_article_views_user_id", table_name="kb_article_views")
    op.drop_index(
        "ix_kb_article_views_article_id_viewed_at", table_name="kb_article_views"
    )
    op.drop_table("kb_article_views")

    op.drop_index("ix_kb_attachments_article_id", table_name="kb_attachments")
    op.drop_table("kb_attachments")

    op.drop_index("ix_kb_article_versions_version", table_name="kb_article_versions")
    op.drop_index("ix_kb_article_versions_article_id", table_name="kb_article_versions")
    op.drop_table("kb_article_versions")

    op.drop_index("ix_kb_article_tags_article_id", table_name="kb_article_tags")
    op.drop_table("kb_article_tags")

    op.drop_index("ix_kb_articles_status", table_name="kb_articles")
    op.drop_index("ix_kb_articles_slug", table_name="kb_articles")
    op.drop_index("ix_kb_articles_author_id", table_name="kb_articles")
    op.drop_index("ix_kb_articles_locale", table_name="kb_articles")
    op.drop_index("ix_kb_articles_status_published_at", table_name="kb_articles")
    op.drop_table("kb_articles")

    op.drop_index("ix_kb_tags_slug", table_name="kb_tags")
    op.drop_index("ix_kb_tags_name", table_name="kb_tags")
    op.drop_table("kb_tags")
