"""
Knowledge Base CMS Models

Provides article management with versioning, approvals, localization, and attachments.
Articles can be in draft/published status, support locale fallback, and track edit history.
"""

from datetime import datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import JSON, Boolean, Column, DateTime
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from backend.app.core.db import Base


class ArticleStatus(str, Enum):
    """Article publication status."""

    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class Article(Base):
    """
    Knowledge Base Article.

    Represents a versioned article with markdown content, tags, locales, and approval tracking.
    """

    __tablename__ = "kb_articles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    title = Column(String(500), nullable=False, index=True)
    slug = Column(String(500), nullable=False, index=True)
    content = Column(Text, nullable=False)  # Markdown content
    status: ArticleStatus | None = Column(  # type: ignore[assignment]
        SQLEnum(ArticleStatus), nullable=False, default=ArticleStatus.DRAFT, index=True
    )
    author_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    locale = Column(String(10), nullable=False, default="en")  # e.g., en, es, fr
    version = Column(Integer, nullable=False, default=1)
    requires_approval = Column(Boolean, nullable=False, default=True)
    approved_by_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    approval_note = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    published_at = Column(DateTime, nullable=True)
    archived_at = Column(DateTime, nullable=True)
    meta = Column(JSON, nullable=False, default=dict)  # SEO, custom fields

    # Relationships
    tags = relationship(
        "ArticleTag", back_populates="article", cascade="all, delete-orphan"
    )
    versions = relationship(
        "ArticleVersion", back_populates="article", cascade="all, delete-orphan"
    )
    attachments = relationship(
        "ArticleAttachment", back_populates="article", cascade="all, delete-orphan"
    )
    views = relationship(
        "ArticleView", back_populates="article", cascade="all, delete-orphan"
    )

    # Indexes
    __table_args__ = (
        Index("ix_kb_articles_status_published_at", "status", "published_at"),
        Index("ix_kb_articles_locale", "locale"),
        Index("ix_kb_articles_author_id", "author_id"),
        UniqueConstraint("slug", "locale", name="uq_kb_articles_slug_locale"),
    )

    def __repr__(self):
        return f"<Article {self.id}: {self.title} v{self.version} ({self.status})>"


class Tag(Base):
    """Article tag for categorization."""

    __tablename__ = "kb_tags"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(100), nullable=False, unique=True, index=True)
    slug = Column(String(100), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    articles = relationship(
        "ArticleTag", back_populates="tag", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Tag {self.slug}>"


class ArticleTag(Base):
    """Association table for articles and tags."""

    __tablename__ = "kb_article_tags"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    article_id = Column(
        UUID(as_uuid=True), ForeignKey("kb_articles.id"), nullable=False
    )
    tag_id = Column(UUID(as_uuid=True), ForeignKey("kb_tags.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    article = relationship("Article", back_populates="tags")
    tag = relationship("Tag", back_populates="articles")

    # Indexes
    __table_args__ = (Index("ix_kb_article_tags_article_id", "article_id"),)

    def __repr__(self):
        return f"<ArticleTag {self.article_id} -> {self.tag_id}>"


class ArticleVersion(Base):
    """Version history for articles (audit trail)."""

    __tablename__ = "kb_article_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    article_id = Column(
        UUID(as_uuid=True), ForeignKey("kb_articles.id"), nullable=False
    )
    version = Column(Integer, nullable=False)
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=False)
    status: ArticleStatus | None = Column(SQLEnum(ArticleStatus), nullable=False)  # type: ignore[assignment]
    author_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    change_note = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    article = relationship("Article", back_populates="versions")

    # Indexes
    __table_args__ = (
        Index("ix_kb_article_versions_article_id", "article_id"),
        Index("ix_kb_article_versions_version", "article_id", "version"),
    )

    def __repr__(self):
        return f"<ArticleVersion {self.article_id} v{self.version}>"


class ArticleAttachment(Base):
    """Attachments (images, documents) for articles."""

    __tablename__ = "kb_attachments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    article_id = Column(
        UUID(as_uuid=True), ForeignKey("kb_articles.id"), nullable=False
    )
    filename = Column(String(255), nullable=False)
    file_type = Column(
        String(50), nullable=False
    )  # image/png, image/jpg, application/pdf, etc.
    file_size = Column(Integer, nullable=False)  # bytes
    s3_key = Column(String(500), nullable=False, unique=True)  # S3 storage path
    uploaded_by_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    article = relationship("Article", back_populates="attachments")

    # Indexes
    __table_args__ = (Index("ix_kb_attachments_article_id", "article_id"),)

    def __repr__(self):
        return f"<ArticleAttachment {self.filename}>"


class ArticleView(Base):
    """Tracks article views for telemetry."""

    __tablename__ = "kb_article_views"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    article_id = Column(
        UUID(as_uuid=True), ForeignKey("kb_articles.id"), nullable=False
    )
    user_id = Column(
        String(36), ForeignKey("users.id"), nullable=True
    )  # Anonymous if null
    locale = Column(String(10), nullable=False, default="en")
    viewed_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    article = relationship("Article", back_populates="views")

    # Indexes
    __table_args__ = (
        Index("ix_kb_article_views_article_id_viewed_at", "article_id", "viewed_at"),
        Index("ix_kb_article_views_user_id", "user_id"),
    )

    def __repr__(self):
        return f"<ArticleView {self.article_id}>"
