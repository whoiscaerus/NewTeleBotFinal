"""
Knowledge Base Service Layer

Implements all business logic for article CRUD, versioning, approvals, and localization.
"""

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_
from sqlalchemy import delete as sa_delete
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.core.utils import slugify
from backend.app.kb.models import (
    Article,
    ArticleStatus,
    ArticleTag,
    ArticleVersion,
    ArticleView,
    Tag,
)

logger = logging.getLogger(__name__)


class KnowledgeBaseService:
    """Service for managing Knowledge Base articles."""

    @staticmethod
    async def create_article(
        db: AsyncSession,
        title: str,
        content: str,
        author_id,  # UUID or str
        tags: list[str] | None = None,
        locale: str = "en",
        status: ArticleStatus = ArticleStatus.DRAFT,
        meta: dict[str, Any] | None = None,
        requires_approval: bool = True,
    ) -> Article:
        """
        Create a new article.

        Args:
            db: Database session
            title: Article title
            content: Markdown content
            author_id: Author user ID (UUID or string)
            tags: List of tag names
            locale: Locale code (e.g., 'en', 'es')
            status: Initial status (default: DRAFT)
            meta: Additional metadata (SEO, etc.)
            requires_approval: Whether article needs approval before publishing

        Returns:
            Created Article

        Raises:
            ValueError: If article slug already exists for locale
        """
        # Convert string to UUID if needed
        if isinstance(author_id, str):
            author_id = UUID(author_id)

        slug = slugify(title)

        # Check uniqueness for locale
        existing = await db.execute(
            select(Article).where(and_(Article.slug == slug, Article.locale == locale))
        )
        if existing.scalar_one_or_none():
            raise ValueError(
                f"Article slug '{slug}' already exists for locale '{locale}'"
            )

        article = Article(
            title=title,
            slug=slug,
            content=content,
            author_id=author_id,
            locale=locale,
            status=status,
            meta=meta or {},
            requires_approval=requires_approval,
            version=1,
        )

        db.add(article)
        await db.flush()

        # Create initial version record
        version_record = ArticleVersion(
            article_id=article.id,
            version=1,
            title=title,
            content=content,
            status=status,
            author_id=author_id,
            change_note="Initial version",
        )
        db.add(version_record)

        # Add tags
        if tags:
            for tag_name in tags:
                tag_slug = slugify(tag_name)
                # Get or create tag
                result = await db.execute(select(Tag).where(Tag.slug == tag_slug))
                tag = result.scalar_one_or_none()
                if not tag:
                    tag = Tag(name=tag_name, slug=tag_slug)
                    db.add(tag)
                    await db.flush()

                article_tag = ArticleTag(article_id=article.id, tag_id=tag.id)
                db.add(article_tag)

        await db.commit()
        await db.refresh(article, ["tags", "versions"])

        logger.info(
            f"Article created: {article.id}",
            extra={
                "article_id": str(article.id),
                "author_id": str(author_id),
                "locale": locale,
            },
        )

        return article

    @staticmethod
    async def update_article(
        db: AsyncSession,
        article_id,  # UUID or str
        title: str | None = None,
        content: str | None = None,
        author_id=None,  # UUID or str
        tags: list[str] | None = None,
        change_note: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> Article:
        """
        Update an article and create version history.

        Args:
            db: Database session
            article_id: Article ID to update (UUID or string)
            title: New title (optional)
            content: New content (optional)
            author_id: Editor user ID (UUID or string)
            tags: New tags list
            change_note: What changed in this version
            meta: Updated metadata

        Returns:
            Updated Article

        Raises:
            ValueError: If article not found or update invalid
        """
        # Convert strings to UUIDs if needed
        if isinstance(article_id, str):
            article_id = UUID(article_id)
        if isinstance(author_id, str):
            author_id = UUID(author_id)

        result = await db.execute(select(Article).where(Article.id == article_id))
        article = result.scalar_one_or_none()
        if not article:
            raise ValueError(f"Article {article_id} not found")

        # Track what changed
        changes = []
        if title and title != article.title:
            article.title = title
            changes.append("title")
            # Update slug if title changed
            article.slug = slugify(title)

        if content and content != article.content:
            article.content = content
            changes.append("content")

        if meta is not None:
            article.meta = meta
            changes.append("metadata")

        article.updated_at = datetime.utcnow()
        article.version += 1

        # Reset approval if significant changes
        if changes and article.requires_approval:
            article.approved_by_id = None
            article.approved_at = None
            logger.info(f"Article approval reset due to changes: {changes}")

        # Create version record
        version_record = ArticleVersion(
            article_id=article_id,
            version=article.version,
            title=article.title,
            content=article.content,
            status=article.status,
            author_id=author_id or article.author_id,
            change_note=change_note or f"Changes: {', '.join(changes)}",
        )
        db.add(version_record)

        # Update tags
        if tags is not None:
            # Clear existing tags
            await db.execute(
                sa_delete(ArticleTag).where(ArticleTag.article_id == article_id)
            )

            for tag_name in tags:
                tag_slug = slugify(tag_name)
                result = await db.execute(select(Tag).where(Tag.slug == tag_slug))
                tag = result.scalar_one_or_none()
                if not tag:
                    tag = Tag(name=tag_name, slug=tag_slug)
                    db.add(tag)
                    await db.flush()

                article_tag = ArticleTag(article_id=article_id, tag_id=tag.id)
                db.add(article_tag)

        await db.commit()
        await db.refresh(article, ["tags", "versions"])

        logger.info(
            f"Article updated: {article_id}",
            extra={"article_id": str(article_id), "version": article.version},
        )

        return article

    @staticmethod
    async def publish_article(
        db: AsyncSession,
        article_id,
        approved_by_id,
        approval_note: str | None = None,  # UUID or str
    ) -> Article:
        """
        Publish an article (moves from draft to published).

        Args:
            db: Database session
            article_id: Article ID to publish (UUID or string)
            approved_by_id: Admin/owner approving publication (UUID or string)
            approval_note: Optional approval note

        Returns:
            Published Article

        Raises:
            ValueError: If article not found or already published
        """
        # Convert strings to UUIDs if needed
        if isinstance(article_id, str):
            article_id = UUID(article_id)
        if isinstance(approved_by_id, str):
            approved_by_id = UUID(approved_by_id)

        result = await db.execute(select(Article).where(Article.id == article_id))
        article = result.scalar_one_or_none()
        if not article:
            raise ValueError(f"Article {article_id} not found")

        if article.status == ArticleStatus.PUBLISHED:
            raise ValueError(f"Article {article_id} is already published")

        article.status = ArticleStatus.PUBLISHED
        article.published_at = datetime.utcnow()
        article.approved_by_id = approved_by_id
        article.approved_at = datetime.utcnow()
        article.approval_note = approval_note

        await db.commit()
        await db.refresh(article)

        logger.info(
            f"Article published: {article_id}",
            extra={"article_id": str(article_id), "approved_by": str(approved_by_id)},
        )

        return article

    @staticmethod
    async def reject_article(
        db: AsyncSession,
        article_id,
        rejected_by_id,
        rejection_reason: str,  # UUID or str
    ) -> Article:
        """
        Reject an article (keeps as draft with rejection note).

        Args:
            db: Database session
            article_id: Article ID to reject (UUID or string)
            rejected_by_id: Admin/owner rejecting (UUID or string)
            rejection_reason: Why article was rejected

        Returns:
            Rejected Article

        Raises:
            ValueError: If article not found
        """
        # Convert strings to UUIDs if needed
        if isinstance(article_id, str):
            article_id = UUID(article_id)
        if isinstance(rejected_by_id, str):
            rejected_by_id = UUID(rejected_by_id)

        result = await db.execute(select(Article).where(Article.id == article_id))
        article = result.scalar_one_or_none()
        if not article:
            raise ValueError(f"Article {article_id} not found")

        article.approval_note = f"REJECTED: {rejection_reason}"
        # Keep as draft for revision

        await db.commit()
        await db.refresh(article)

        logger.info(
            f"Article rejected: {article_id}",
            extra={"article_id": str(article_id), "rejected_by": str(rejected_by_id)},
        )

        return article

    @staticmethod
    async def archive_article(db: AsyncSession, article_id) -> Article:  # UUID or str
        """
        Archive an article (soft delete).

        Args:
            db: Database session
            article_id: Article ID to archive (UUID or string)

        Returns:
            Archived Article

        Raises:
            ValueError: If article not found
        """
        # Convert string to UUID if needed
        if isinstance(article_id, str):
            article_id = UUID(article_id)

        result = await db.execute(select(Article).where(Article.id == article_id))
        article = result.scalar_one_or_none()
        if not article:
            raise ValueError(f"Article {article_id} not found")

        article.status = ArticleStatus.ARCHIVED
        article.archived_at = datetime.utcnow()

        await db.commit()
        await db.refresh(article)

        logger.info(
            f"Article archived: {article_id}", extra={"article_id": str(article_id)}
        )

        return article

    @staticmethod
    async def get_article(
        db: AsyncSession, article_id, include_draft: bool = False  # UUID or str
    ) -> Article | None:
        """
        Get article by ID.

        Args:
            db: Database session
            article_id: Article ID (UUID or string)
            include_draft: Whether to include draft articles

        Returns:
            Article or None

        Raises:
            ValueError: If article not found and not draft-included
        """
        # Convert string to UUID if needed
        if isinstance(article_id, str):
            article_id = UUID(article_id)

        query = select(Article).where(Article.id == article_id)

        if not include_draft:
            query = query.where(Article.status == ArticleStatus.PUBLISHED)

        query = query.options(
            selectinload(Article.tags), selectinload(Article.versions)
        )

        result = await db.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_article_by_slug(
        db: AsyncSession, slug: str, locale: str = "en", include_draft: bool = False
    ) -> Article | None:
        """
        Get article by slug and locale.

        Args:
            db: Database session
            slug: Article slug
            locale: Locale code
            include_draft: Include draft articles

        Returns:
            Article or None
        """
        query = select(Article).where(
            and_(Article.slug == slug, Article.locale == locale)
        )

        if not include_draft:
            query = query.where(Article.status == ArticleStatus.PUBLISHED)

        query = query.options(
            selectinload(Article.tags), selectinload(Article.versions)
        )

        result = await db.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_articles(
        db: AsyncSession,
        locale: str = "en",
        status: ArticleStatus | None = ArticleStatus.PUBLISHED,
        tags: list[str] | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[Article], int]:
        """
        List articles with pagination and filtering.

        Args:
            db: Database session
            locale: Filter by locale
            status: Filter by status (None = all)
            tags: Filter by tag names
            skip: Pagination offset
            limit: Pagination limit

        Returns:
            Tuple of (articles list, total count)
        """
        query = select(Article)

        filters = [Article.locale == locale]
        if status:
            filters.append(Article.status == status)

        # Filter by tags if provided
        if tags:
            # Get tag IDs
            tag_slugs = [slugify(tag) for tag in tags]
            tag_result = await db.execute(select(Tag).where(Tag.slug.in_(tag_slugs)))
            tag_ids = [tag.id for tag in tag_result.scalars().all()]

            if tag_ids:
                # Only articles with ALL specified tags
                for tag_id in tag_ids:
                    subquery = select(ArticleTag.article_id).where(
                        ArticleTag.tag_id == tag_id
                    )
                    filters.append(Article.id.in_(subquery))

        query = query.where(and_(*filters))

        # Get total count
        count_query = select(func.count(Article.id)).where(and_(*filters))
        count_result = await db.execute(count_query)
        total = count_result.scalar() or 0

        # Get paginated results
        query = query.options(selectinload(Article.tags))
        query = query.order_by(desc(Article.published_at)).offset(skip).limit(limit)

        result = await db.execute(query)
        articles = result.scalars().all()

        return list(articles), total

    @staticmethod
    async def get_article_versions(
        db: AsyncSession, article_id
    ) -> list[ArticleVersion]:  # UUID or str
        """
        Get all versions of an article.

        Args:
            db: Database session
            article_id: Article ID (UUID or string)

        Returns:
            List of ArticleVersion records
        """
        # Convert string to UUID if needed
        if isinstance(article_id, str):
            article_id = UUID(article_id)

        result = await db.execute(
            select(ArticleVersion)
            .where(ArticleVersion.article_id == article_id)
            .order_by(desc(ArticleVersion.version))
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_article_version(
        db: AsyncSession, article_id, version: int  # UUID or str
    ) -> ArticleVersion | None:
        """
        Get specific version of an article.

        Args:
            db: Database session
            article_id: Article ID (UUID or string)
            version: Version number

        Returns:
            ArticleVersion or None
        """
        # Convert string to UUID if needed
        if isinstance(article_id, str):
            article_id = UUID(article_id)

        result = await db.execute(
            select(ArticleVersion).where(
                and_(
                    ArticleVersion.article_id == article_id,
                    ArticleVersion.version == version,
                )
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def record_view(
        db: AsyncSession, article_id, user_id=None, locale: str = "en"  # UUID or str
    ) -> ArticleView:
        """
        Record an article view for telemetry.

        Args:
            db: Database session
            article_id: Article ID (UUID or string)
            user_id: Viewing user ID (optional for anonymous, UUID or string)
            locale: User's locale

        Returns:
            ArticleView record
        """
        # Convert strings to UUIDs if needed
        if isinstance(article_id, str):
            article_id = UUID(article_id)
        if isinstance(user_id, str):
            user_id = UUID(user_id)

        view = ArticleView(article_id=article_id, user_id=user_id, locale=locale)
        db.add(view)
        await db.commit()
        return view

    @staticmethod
    async def get_view_stats(
        db: AsyncSession, article_id, days: int = 30  # UUID or str
    ) -> dict[str, Any]:
        """
        Get view statistics for an article.

        Args:
            db: Database session
            article_id: Article ID (UUID or string)
            days: Look back period

        Returns:
            Statistics dict with total views, unique users, etc.
        """
        # Convert string to UUID if needed
        if isinstance(article_id, str):
            article_id = UUID(article_id)

        from datetime import timedelta

        start_date = datetime.utcnow() - timedelta(days=days)

        result = await db.execute(
            select(ArticleView).where(
                and_(
                    ArticleView.article_id == article_id,
                    ArticleView.viewed_at >= start_date,
                )
            )
        )
        views = result.scalars().all()

        unique_users = len({v.user_id for v in views if v.user_id})
        total_views = len(views)

        return {
            "article_id": str(article_id),
            "total_views": total_views,
            "unique_users": unique_users,
            "period_days": days,
        }
