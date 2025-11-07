"""
Knowledge Base Request/Response Schemas
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class TagOut(BaseModel):
    """Tag output model."""

    id: UUID
    name: str
    slug: str
    description: str | None = None

    class Config:
        from_attributes = True


class ArticleVersionOut(BaseModel):
    """Article version history output."""

    version: int
    title: str
    change_note: str | None = None
    author_id: UUID
    created_at: datetime

    class Config:
        from_attributes = True


class ArticleViewStatsOut(BaseModel):
    """Article view statistics."""

    article_id: UUID
    total_views: int
    unique_users: int
    period_days: int


class ArticleDetailOut(BaseModel):
    """Full article with all details (admin view)."""

    id: UUID
    title: str
    slug: str
    content: str
    status: str
    author_id: UUID
    locale: str
    version: int
    requires_approval: bool
    approved_by_id: UUID | None = None
    approved_at: datetime | None = None
    approval_note: str | None = None
    tags: list[TagOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None = None
    archived_at: datetime | None = None
    meta: dict[str, Any] = Field(default_factory=dict)

    class Config:
        from_attributes = True


class ArticleListOut(BaseModel):
    """Article for list view (public)."""

    id: UUID
    title: str
    slug: str
    locale: str
    tags: list[TagOut] = Field(default_factory=list)
    published_at: datetime | None = None
    meta: dict[str, Any] = Field(default_factory=dict)

    class Config:
        from_attributes = True


class ArticleCreateIn(BaseModel):
    """Article creation request."""

    title: str = Field(..., min_length=3, max_length=500)
    content: str = Field(..., min_length=10)
    tags: list[str] | None = Field(default_factory=list)
    locale: str = Field(default="en", pattern="^[a-z]{2}(?:-[A-Z]{2})?$")
    requires_approval: bool = Field(default=True)
    meta: dict[str, Any] | None = Field(default_factory=dict)


class ArticleUpdateIn(BaseModel):
    """Article update request."""

    title: str | None = Field(None, min_length=3, max_length=500)
    content: str | None = Field(None, min_length=10)
    tags: list[str] | None = None
    change_note: str | None = Field(None, max_length=500)
    meta: dict[str, Any] | None = None


class ArticlePublishIn(BaseModel):
    """Publish article request."""

    approval_note: str | None = Field(None, max_length=500)


class ArticleRejectIn(BaseModel):
    """Reject article request."""

    rejection_reason: str = Field(..., min_length=5, max_length=500)


class ArticleListResponse(BaseModel):
    """Paginated article list response."""

    articles: list[ArticleListOut]
    total: int
    skip: int
    limit: int


class ArticleVersionsResponse(BaseModel):
    """Article versions response."""

    article_id: UUID
    versions: list[ArticleVersionOut]
    total: int
