"""
Knowledge Base Tests - Comprehensive Coverage

Tests cover:
- CRUD operations (create, read, update, delete/archive)
- Version history and tracking
- Approval workflow
- Locale fallback and filtering
- Security (owner/admin only writes)
- Telemetry (view tracking)
- Tag operations
- Error scenarios and edge cases
"""

from datetime import datetime
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.models import User
from backend.app.kb.models import ArticleStatus, ArticleTag
from backend.app.kb.service import KnowledgeBaseService


class TestKBServiceCreate:
    """Test article creation."""

    @pytest.mark.asyncio
    async def test_create_article_minimal(
        self, db_session: AsyncSession, owner_user: User
    ):
        """Test creating article with minimal fields."""
        article = await KnowledgeBaseService.create_article(
            db=db_session,
            title="Getting Started",
            content="# Introduction\n\nThis is a guide.",
            author_id=owner_user.id,
        )

        assert article.id is not None
        assert article.title == "Getting Started"
        assert article.slug == "getting-started"
        assert article.status == ArticleStatus.DRAFT
        assert article.version == 1
        assert str(article.author_id) == owner_user.id
        assert article.locale == "en"
        assert not article.approved_by_id
        assert article.meta == {}

    @pytest.mark.asyncio
    async def test_create_article_with_tags(
        self, db_session: AsyncSession, owner_user: User
    ):
        """Test creating article with tags."""
        article = await KnowledgeBaseService.create_article(
            db=db_session,
            title="Python Tutorial",
            content="# Learn Python\n\nFull course.",
            author_id=owner_user.id,
            tags=["python", "tutorial", "beginner"],
        )

        # Verify tags were created by counting them
        assert article.id is not None
        # Reload article to get tags in proper session context
        reloaded = await KnowledgeBaseService.get_article(
            db=db_session, article_id=article.id, include_draft=True
        )
        assert reloaded is not None
        assert len(reloaded.tags) == 3

    @pytest.mark.asyncio
    async def test_create_article_with_locale(
        self, db_session: AsyncSession, owner_user: User
    ):
        """Test creating article in specific locale."""
        article_en = await KnowledgeBaseService.create_article(
            db=db_session,
            title="Welcome",
            content="Welcome to our platform",
            author_id=owner_user.id,
            locale="en",
        )

        article_es = await KnowledgeBaseService.create_article(
            db=db_session,
            title="Welcome",  # Same title to have same slug
            content="Bienvenido a nuestra plataforma",
            author_id=owner_user.id,
            locale="es",
        )

        assert article_en.locale == "en"
        assert article_es.locale == "es"
        assert article_en.slug == article_es.slug  # Same slug but different locale
        # Both should exist since slug uniqueness is enforced per-locale
        assert article_en.id != article_es.id

    @pytest.mark.asyncio
    async def test_create_article_duplicate_slug_same_locale_fails(
        self, db_session: AsyncSession, owner_user: User
    ):
        """Test that duplicate slug in same locale raises error."""
        await KnowledgeBaseService.create_article(
            db=db_session,
            title="Unique Article",
            content="Content here",
            author_id=owner_user.id,
            locale="en",
        )

        # Try to create another with same title/slug but same locale
        with pytest.raises(ValueError, match="already exists"):
            await KnowledgeBaseService.create_article(
                db=db_session,
                title="Unique Article",
                content="Different content",
                author_id=owner_user.id,
                locale="en",
            )

    @pytest.mark.asyncio
    async def test_create_article_with_metadata(
        self, db_session: AsyncSession, owner_user: User
    ):
        """Test creating article with SEO metadata."""
        meta = {
            "seo_title": "Best Python Tutorials | Our Platform",
            "seo_description": "Learn Python from experts",
            "keywords": ["python", "programming"],
        }

        article = await KnowledgeBaseService.create_article(
            db=db_session,
            title="Python Guide",
            content="# Python Content",
            author_id=owner_user.id,
            meta=meta,
        )

        assert article.meta == meta

    @pytest.mark.asyncio
    async def test_create_article_version_record_created(
        self, db_session: AsyncSession, owner_user: User
    ):
        """Test that initial version record is created."""
        article = await KnowledgeBaseService.create_article(
            db=db_session,
            title="Test Article",
            content="Initial content",
            author_id=owner_user.id,
        )

        versions = await KnowledgeBaseService.get_article_versions(
            db=db_session, article_id=article.id
        )

        assert len(versions) == 1
        assert versions[0].version == 1
        assert versions[0].title == "Test Article"
        assert versions[0].content == "Initial content"


class TestKBServiceUpdate:
    """Test article updates and versioning."""

    @pytest.mark.asyncio
    async def test_update_article_title(
        self, db_session: AsyncSession, owner_user: User
    ):
        """Test updating article title."""
        article = await KnowledgeBaseService.create_article(
            db=db_session,
            title="Original Title",
            content="Content",
            author_id=owner_user.id,
        )

        updated = await KnowledgeBaseService.update_article(
            db=db_session,
            article_id=article.id,
            title="New Title",
            author_id=owner_user.id,
        )

        assert updated.title == "New Title"
        assert updated.slug == "new-title"
        assert updated.version == 2

    @pytest.mark.asyncio
    async def test_update_article_content(
        self, db_session: AsyncSession, owner_user: User
    ):
        """Test updating article content."""
        article = await KnowledgeBaseService.create_article(
            db=db_session,
            title="Test",
            content="Original content",
            author_id=owner_user.id,
        )

        updated = await KnowledgeBaseService.update_article(
            db=db_session,
            article_id=article.id,
            content="Updated content with new information",
            author_id=owner_user.id,
            change_note="Fixed typos and added examples",
        )

        assert updated.content == "Updated content with new information"
        assert updated.version == 2

    @pytest.mark.asyncio
    async def test_update_article_resets_approval_on_content_change(
        self, db_session: AsyncSession, owner_user: User
    ):
        """Test that content changes reset approval."""
        from uuid import UUID

        article = await KnowledgeBaseService.create_article(
            db=db_session,
            title="Article",
            content="Content",
            author_id=owner_user.id,
            requires_approval=True,
        )

        # Manually approve (simulate approval flow)
        article.approved_by_id = (
            UUID(owner_user.id) if isinstance(owner_user.id, str) else owner_user.id
        )
        article.approved_at = datetime.utcnow()
        db_session.add(article)
        await db_session.commit()

        # Update content
        updated = await KnowledgeBaseService.update_article(
            db=db_session,
            article_id=article.id,
            content="Changed content",
            author_id=owner_user.id,
        )

        # Approval should be reset
        assert updated.approved_by_id is None
        assert updated.approved_at is None
        assert updated.requires_approval is True

    @pytest.mark.asyncio
    async def test_update_article_creates_version_record(
        self, db_session: AsyncSession, owner_user: User
    ):
        """Test that update creates new version record."""
        article = await KnowledgeBaseService.create_article(
            db=db_session,
            title="Test",
            content="v1",
            author_id=owner_user.id,
        )

        await KnowledgeBaseService.update_article(
            db=db_session,
            article_id=article.id,
            content="v2",
            author_id=owner_user.id,
        )

        versions = await KnowledgeBaseService.get_article_versions(
            db=db_session, article_id=article.id
        )

        assert len(versions) == 2
        assert versions[0].version == 2
        assert versions[0].content == "v2"
        assert versions[1].version == 1
        assert versions[1].content == "v1"

    @pytest.mark.asyncio
    async def test_update_article_tags(
        self, db_session: AsyncSession, owner_user: User
    ):
        """Test updating article tags."""
        article = await KnowledgeBaseService.create_article(
            db=db_session,
            title="Article",
            content="Content",
            author_id=owner_user.id,
            tags=["old-tag"],
        )

        updated = await KnowledgeBaseService.update_article(
            db=db_session,
            article_id=article.id,
            tags=["new-tag-1", "new-tag-2"],
            author_id=owner_user.id,
        )

        # Verify by directly querying the database
        from sqlalchemy import select

        result = await db_session.execute(
            select(ArticleTag).where(ArticleTag.article_id == updated.id)
        )
        article_tags = result.scalars().all()
        assert len(article_tags) == 2
        # Tags were updated successfully
        assert updated.id is not None

    @pytest.mark.asyncio
    async def test_update_nonexistent_article_fails(
        self, db_session: AsyncSession, owner_user: User
    ):
        """Test updating nonexistent article raises error."""
        with pytest.raises(ValueError, match="not found"):
            await KnowledgeBaseService.update_article(
                db=db_session,
                article_id=uuid4(),
                title="New Title",
                author_id=owner_user.id,
            )


class TestKBServicePublishing:
    """Test article publishing and approval workflow."""

    @pytest.mark.asyncio
    async def test_publish_article_from_draft(
        self, db_session: AsyncSession, owner_user: User
    ):
        """Test publishing draft article."""
        article = await KnowledgeBaseService.create_article(
            db=db_session,
            title="Article",
            content="Content",
            author_id=owner_user.id,
        )

        assert article.status == ArticleStatus.DRAFT

        published = await KnowledgeBaseService.publish_article(
            db=db_session,
            article_id=article.id,
            approved_by_id=owner_user.id,
            approval_note="Looks good!",
        )

        assert published.status == ArticleStatus.PUBLISHED
        assert published.published_at is not None
        assert str(published.approved_by_id) == owner_user.id
        assert published.approval_note == "Looks good!"

    @pytest.mark.asyncio
    async def test_publish_already_published_fails(
        self, db_session: AsyncSession, owner_user: User
    ):
        """Test publishing already published article fails."""
        article = await KnowledgeBaseService.create_article(
            db=db_session,
            title="Article",
            content="Content",
            author_id=owner_user.id,
        )

        await KnowledgeBaseService.publish_article(
            db=db_session,
            article_id=article.id,
            approved_by_id=owner_user.id,
        )

        # Try to publish again
        with pytest.raises(ValueError, match="already published"):
            await KnowledgeBaseService.publish_article(
                db=db_session,
                article_id=article.id,
                approved_by_id=owner_user.id,
            )

    @pytest.mark.asyncio
    async def test_reject_article(self, db_session: AsyncSession, owner_user: User):
        """Test rejecting article for revision."""
        article = await KnowledgeBaseService.create_article(
            db=db_session,
            title="Article",
            content="Content",
            author_id=owner_user.id,
        )

        rejected = await KnowledgeBaseService.reject_article(
            db=db_session,
            article_id=article.id,
            rejected_by_id=owner_user.id,
            rejection_reason="Content needs more examples",
        )

        assert rejected.approval_note == "REJECTED: Content needs more examples"
        assert rejected.status == ArticleStatus.DRAFT

    @pytest.mark.asyncio
    async def test_archive_article(self, db_session: AsyncSession, owner_user: User):
        """Test archiving article (soft delete)."""
        article = await KnowledgeBaseService.create_article(
            db=db_session,
            title="Article",
            content="Content",
            author_id=owner_user.id,
        )

        await KnowledgeBaseService.publish_article(
            db=db_session,
            article_id=article.id,
            approved_by_id=owner_user.id,
        )

        archived = await KnowledgeBaseService.archive_article(
            db=db_session,
            article_id=article.id,
        )

        assert archived.status == ArticleStatus.ARCHIVED
        assert archived.archived_at is not None


class TestKBServiceRetrieval:
    """Test article retrieval and filtering."""

    @pytest.mark.asyncio
    async def test_get_article_by_id(self, db_session: AsyncSession, owner_user: User):
        """Test retrieving article by ID."""
        created = await KnowledgeBaseService.create_article(
            db=db_session,
            title="Article",
            content="Content",
            author_id=owner_user.id,
        )

        retrieved = await KnowledgeBaseService.get_article(
            db=db_session,
            article_id=created.id,
            include_draft=True,
        )

        assert retrieved.id == created.id
        assert retrieved.title == "Article"

    @pytest.mark.asyncio
    async def test_get_article_excludes_draft_by_default(
        self, db_session: AsyncSession, owner_user: User
    ):
        """Test that draft articles are excluded from public queries."""
        article = await KnowledgeBaseService.create_article(
            db=db_session,
            title="Draft",
            content="Content",
            author_id=owner_user.id,
        )

        # Should not find draft
        found = await KnowledgeBaseService.get_article(
            db=db_session,
            article_id=article.id,
            include_draft=False,
        )

        assert found is None

        # Publish and try again
        await KnowledgeBaseService.publish_article(
            db=db_session,
            article_id=article.id,
            approved_by_id=owner_user.id,
        )

        found = await KnowledgeBaseService.get_article(
            db=db_session,
            article_id=article.id,
            include_draft=False,
        )

        assert found is not None

    @pytest.mark.asyncio
    async def test_get_article_by_slug(
        self, db_session: AsyncSession, owner_user: User
    ):
        """Test retrieving article by slug."""
        article = await KnowledgeBaseService.create_article(
            db=db_session,
            title="Python Basics",
            content="Learn Python",
            author_id=owner_user.id,
        )

        await KnowledgeBaseService.publish_article(
            db=db_session,
            article_id=article.id,
            approved_by_id=owner_user.id,
        )

        retrieved = await KnowledgeBaseService.get_article_by_slug(
            db=db_session,
            slug="python-basics",
            locale="en",
            include_draft=False,
        )

        assert retrieved.id == article.id

    @pytest.mark.asyncio
    async def test_list_articles_filtered_by_locale(
        self, db_session: AsyncSession, owner_user: User
    ):
        """Test listing articles by locale."""
        # Create English articles
        for i in range(2):
            article = await KnowledgeBaseService.create_article(
                db=db_session,
                title=f"English Article {i}",
                content="Content",
                author_id=owner_user.id,
                locale="en",
            )
            await KnowledgeBaseService.publish_article(
                db=db_session,
                article_id=article.id,
                approved_by_id=owner_user.id,
            )

        # Create Spanish articles
        for i in range(3):
            article = await KnowledgeBaseService.create_article(
                db=db_session,
                title=f"Spanish Article {i}",
                content="Contenido",
                author_id=owner_user.id,
                locale="es",
            )
            await KnowledgeBaseService.publish_article(
                db=db_session,
                article_id=article.id,
                approved_by_id=owner_user.id,
            )

        en_articles, en_count = await KnowledgeBaseService.list_articles(
            db=db_session,
            locale="en",
            status=ArticleStatus.PUBLISHED,
        )

        es_articles, es_count = await KnowledgeBaseService.list_articles(
            db=db_session,
            locale="es",
            status=ArticleStatus.PUBLISHED,
        )

        assert en_count == 2
        assert es_count == 3

    @pytest.mark.asyncio
    async def test_list_articles_filtered_by_tags(
        self, db_session: AsyncSession, owner_user: User
    ):
        """Test filtering articles by tags."""
        # Article with multiple tags
        article1 = await KnowledgeBaseService.create_article(
            db=db_session,
            title="Python Tutorial",
            content="Content",
            author_id=owner_user.id,
            tags=["python", "tutorial"],
        )
        await KnowledgeBaseService.publish_article(
            db=db_session,
            article_id=article1.id,
            approved_by_id=owner_user.id,
        )

        # Different article
        article2 = await KnowledgeBaseService.create_article(
            db=db_session,
            title="JavaScript Guide",
            content="Content",
            author_id=owner_user.id,
            tags=["javascript"],
        )
        await KnowledgeBaseService.publish_article(
            db=db_session,
            article_id=article2.id,
            approved_by_id=owner_user.id,
        )

        # Filter by python tag
        results, count = await KnowledgeBaseService.list_articles(
            db=db_session,
            locale="en",
            tags=["python"],
        )

        assert count == 1
        assert results[0].id == article1.id

    @pytest.mark.asyncio
    async def test_list_articles_pagination(
        self, db_session: AsyncSession, owner_user: User
    ):
        """Test article list pagination."""
        # Create 5 articles
        for i in range(5):
            article = await KnowledgeBaseService.create_article(
                db=db_session,
                title=f"Article {i:02d}",
                content="Content",
                author_id=owner_user.id,
            )
            await KnowledgeBaseService.publish_article(
                db=db_session,
                article_id=article.id,
                approved_by_id=owner_user.id,
            )

        # Get first page
        page1, total = await KnowledgeBaseService.list_articles(
            db=db_session,
            skip=0,
            limit=2,
        )

        # Get second page
        page2, _ = await KnowledgeBaseService.list_articles(
            db=db_session,
            skip=2,
            limit=2,
        )

        assert total == 5
        assert len(page1) == 2
        assert len(page2) == 2
        assert page1[0].id != page2[0].id


class TestKBVersionHistory:
    """Test version tracking and history."""

    @pytest.mark.asyncio
    async def test_get_article_versions(
        self, db_session: AsyncSession, owner_user: User
    ):
        """Test retrieving article version history."""
        article = await KnowledgeBaseService.create_article(
            db=db_session,
            title="Article",
            content="v1",
            author_id=owner_user.id,
        )

        await KnowledgeBaseService.update_article(
            db=db_session,
            article_id=article.id,
            content="v2",
            author_id=owner_user.id,
        )

        await KnowledgeBaseService.update_article(
            db=db_session,
            article_id=article.id,
            content="v3",
            author_id=owner_user.id,
        )

        versions = await KnowledgeBaseService.get_article_versions(
            db=db_session,
            article_id=article.id,
        )

        assert len(versions) == 3
        # Should be in reverse order (newest first)
        assert versions[0].version == 3
        assert versions[1].version == 2
        assert versions[2].version == 1

    @pytest.mark.asyncio
    async def test_get_specific_version(
        self, db_session: AsyncSession, owner_user: User
    ):
        """Test retrieving specific version."""
        article = await KnowledgeBaseService.create_article(
            db=db_session,
            title="Article",
            content="Initial",
            author_id=owner_user.id,
        )

        await KnowledgeBaseService.update_article(
            db=db_session,
            article_id=article.id,
            content="Updated",
            author_id=owner_user.id,
        )

        v1 = await KnowledgeBaseService.get_article_version(
            db=db_session,
            article_id=article.id,
            version=1,
        )

        v2 = await KnowledgeBaseService.get_article_version(
            db=db_session,
            article_id=article.id,
            version=2,
        )

        assert v1.content == "Initial"
        assert v2.content == "Updated"


class TestKBTelemetry:
    """Test view tracking and statistics."""

    @pytest.mark.asyncio
    async def test_record_view(self, db_session: AsyncSession, owner_user: User):
        """Test recording article view."""
        article = await KnowledgeBaseService.create_article(
            db=db_session,
            title="Article",
            content="Content",
            author_id=owner_user.id,
        )

        view = await KnowledgeBaseService.record_view(
            db=db_session,
            article_id=article.id,
            user_id=owner_user.id,
            locale="en",
        )

        assert view.article_id == article.id
        assert str(view.user_id) == owner_user.id
        assert view.locale == "en"

    @pytest.mark.asyncio
    async def test_record_anonymous_view(
        self, db_session: AsyncSession, owner_user: User
    ):
        """Test recording anonymous article view."""
        article = await KnowledgeBaseService.create_article(
            db=db_session,
            title="Article",
            content="Content",
            author_id=owner_user.id,
        )

        view = await KnowledgeBaseService.record_view(
            db=db_session,
            article_id=article.id,
            user_id=None,  # Anonymous
            locale="en",
        )

        assert view.user_id is None

    @pytest.mark.asyncio
    async def test_get_view_stats(self, db_session: AsyncSession, owner_user: User):
        """Test view statistics calculation."""
        article = await KnowledgeBaseService.create_article(
            db=db_session,
            title="Article",
            content="Content",
            author_id=owner_user.id,
        )

        # Create multiple views from same user
        for _ in range(3):
            await KnowledgeBaseService.record_view(
                db=db_session,
                article_id=article.id,
                user_id=owner_user.id,
            )

        # Anonymous views
        for _ in range(2):
            await KnowledgeBaseService.record_view(
                db=db_session,
                article_id=article.id,
                user_id=None,
            )

        stats = await KnowledgeBaseService.get_view_stats(
            db=db_session,
            article_id=article.id,
            days=30,
        )

        assert stats["total_views"] == 5
        assert stats["unique_users"] == 1  # Only owner_user


# API Tests
class TestKBRoutes:
    """Test KB API routes."""

    @pytest.mark.asyncio
    async def test_create_article_requires_auth(self, client: AsyncClient):
        """Test that create requires authentication."""
        response = await client.post(
            "/api/v1/kb/articles",
            json={
                "title": "Article",
                "content": "Content",
            },
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_article_requires_admin_role(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        regular_user: User,
        regular_auth_headers: dict,
    ):
        """Test that create requires admin or owner role."""
        response = await client.post(
            "/api/v1/kb/articles",
            json={
                "title": "Article",
                "content": "Content",
            },
            headers=regular_auth_headers,
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_list_public_articles(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        owner_user: User,
    ):
        """Test listing published articles is public."""
        # Create and publish article
        article = await KnowledgeBaseService.create_article(
            db=db_session,
            title="Public Article",
            content="Visible to all",
            author_id=owner_user.id,
        )

        await KnowledgeBaseService.publish_article(
            db=db_session,
            article_id=article.id,
            approved_by_id=owner_user.id,
        )

        response = await client.get("/api/v1/kb/articles")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["articles"][0]["title"] == "Public Article"

    @pytest.mark.asyncio
    async def test_get_article_by_slug_records_view(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        owner_user: User,
    ):
        """Test that getting article records a view."""
        article = await KnowledgeBaseService.create_article(
            db=db_session,
            title="Viewed Article",
            content="Content",
            author_id=owner_user.id,
        )

        await KnowledgeBaseService.publish_article(
            db=db_session,
            article_id=article.id,
            approved_by_id=owner_user.id,
        )

        # Get article
        response = await client.get("/api/v1/kb/articles/viewed-article")

        assert response.status_code == 200

        # Check view was recorded
        stats = await KnowledgeBaseService.get_view_stats(
            db=db_session,
            article_id=article.id,
        )

        assert stats["total_views"] == 1
