"""
Knowledge Base Routes

CRUD operations for articles:
- Admin/Owner: Create, Read, Update, Publish, Reject, Archive
- Public: Read published articles only

Security: JWT required for writes, public read-only for published articles.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.dependencies import get_current_user, require_owner
from backend.app.auth.models import User, UserRole
from backend.app.core.db import get_db
from backend.app.kb.models import ArticleStatus
from backend.app.kb.schemas import (
    ArticleCreateIn,
    ArticleDetailOut,
    ArticleListResponse,
    ArticlePublishIn,
    ArticleRejectIn,
    ArticleUpdateIn,
    ArticleVersionsResponse,
    ArticleViewStatsOut,
)
from backend.app.kb.service import KnowledgeBaseService

router = APIRouter(prefix="/api/v1/kb", tags=["knowledge-base"])
logger = logging.getLogger(__name__)


def require_admin_or_owner(current_user: User = Depends(get_current_user)) -> User:
    """Dependency to require admin or owner role."""
    if current_user.role not in (UserRole.ADMIN, UserRole.OWNER):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or owner access required",
        )
    return current_user


# ===== PUBLIC ENDPOINTS (Read-only) =====


@router.get("/articles", response_model=ArticleListResponse)
async def list_articles(
    locale: str = "en",
    tags: str | None = None,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """
    List published articles.

    - **locale**: Filter by locale (e.g., 'en', 'es')
    - **tags**: Comma-separated tag names to filter
    - **skip**: Pagination offset
    - **limit**: Pagination limit (max 100)

    Returns only published articles. Good for Education Hub UI.
    """
    if limit > 100:
        limit = 100

    tag_list = [t.strip() for t in tags.split(",")] if tags else None

    articles, total = await KnowledgeBaseService.list_articles(
        db=db,
        locale=locale,
        status=ArticleStatus.PUBLISHED,
        tags=tag_list,
        skip=skip,
        limit=limit,
    )

    # Convert Article models to ArticleListOut schemas
    article_schemas = [ArticleListOut.model_validate(article) for article in articles]
    return ArticleListResponse(articles=article_schemas, total=total, skip=skip, limit=limit)


@router.get("/articles/{slug}", response_model=ArticleDetailOut)
async def get_article_public(
    slug: str,
    locale: str = "en",
    db: AsyncSession = Depends(get_db),
):
    """
    Get published article by slug.

    - **slug**: Article slug
    - **locale**: Locale code

    Records a view for telemetry. Returns 404 if not published.
    """
    article = await KnowledgeBaseService.get_article_by_slug(
        db=db, slug=slug, locale=locale, include_draft=False
    )

    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Article not found"
        )

    # Record view (fire and forget)
    try:
        await KnowledgeBaseService.record_view(
            db=db, article_id=article.id, locale=locale
        )
    except Exception as e:
        logger.warning(f"Failed to record article view: {e}")

    return article


# ===== ADMIN/OWNER ENDPOINTS (Write access) =====


@router.post(
    "/articles", response_model=ArticleDetailOut, status_code=status.HTTP_201_CREATED
)
async def create_article(
    request: ArticleCreateIn,
    current_user: User = Depends(require_admin_or_owner),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new article (Admin/Owner only).

    Admin-only: Creates article with optional approval requirement.
    """
    try:
        article = await KnowledgeBaseService.create_article(
            db=db,
            title=request.title,
            content=request.content,
            author_id=current_user.id,
            tags=request.tags,
            locale=request.locale,
            status=ArticleStatus.DRAFT,  # Always start as draft
            meta=request.meta,
            requires_approval=request.requires_approval,
        )

        logger.info(
            "Article created",
            extra={"article_id": str(article.id), "author": current_user.email},
        )

        return article

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating article: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


@router.get("/articles/{article_id}/detail", response_model=ArticleDetailOut)
async def get_article_detail(
    article_id: UUID,
    current_user: User = Depends(require_admin_or_owner),
    db: AsyncSession = Depends(get_db),
):
    """
    Get article details including draft articles (Admin/Owner only).
    """
    article = await KnowledgeBaseService.get_article(
        db=db, article_id=article_id, include_draft=True
    )

    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Article not found"
        )

    return article


@router.put("/articles/{article_id}", response_model=ArticleDetailOut)
async def update_article(
    article_id: UUID,
    request: ArticleUpdateIn,
    current_user: User = Depends(require_admin_or_owner),
    db: AsyncSession = Depends(get_db),
):
    """
    Update an article (Admin/Owner only).

    Creates new version in history. Resets approval if content changes.
    """
    try:
        article = await KnowledgeBaseService.update_article(
            db=db,
            article_id=article_id,
            title=request.title,
            content=request.content,
            author_id=current_user.id,
            tags=request.tags,
            change_note=request.change_note,
            meta=request.meta,
        )

        logger.info(
            "Article updated",
            extra={
                "article_id": str(article_id),
                "editor": current_user.email,
                "version": article.version,
            },
        )

        return article

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating article: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


@router.post("/articles/{article_id}/publish", response_model=ArticleDetailOut)
async def publish_article(
    article_id: UUID,
    request: ArticlePublishIn,
    current_user: User = Depends(require_owner),  # Owner only for publishing
    db: AsyncSession = Depends(get_db),
):
    """
    Publish an article (Owner only).

    Changes status from DRAFT to PUBLISHED. Requires owner approval.
    """
    try:
        article = await KnowledgeBaseService.publish_article(
            db=db,
            article_id=article_id,
            approved_by_id=current_user.id,
            approval_note=request.approval_note,
        )

        logger.info(
            "Article published",
            extra={"article_id": str(article_id), "approved_by": current_user.email},
        )

        return article

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error publishing article: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


@router.post("/articles/{article_id}/reject", response_model=ArticleDetailOut)
async def reject_article(
    article_id: UUID,
    request: ArticleRejectIn,
    current_user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    """
    Reject an article (Owner only).

    Leaves as DRAFT with rejection reason. Author can revise and resubmit.
    """
    try:
        article = await KnowledgeBaseService.reject_article(
            db=db,
            article_id=article_id,
            rejected_by_id=current_user.id,
            rejection_reason=request.rejection_reason,
        )

        logger.info(
            "Article rejected",
            extra={"article_id": str(article_id), "rejected_by": current_user.email},
        )

        return article

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error rejecting article: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


@router.post("/articles/{article_id}/archive", response_model=ArticleDetailOut)
async def archive_article(
    article_id: UUID,
    current_user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    """
    Archive an article (Owner only).

    Soft delete - article remains in DB but is hidden from listings.
    """
    try:
        article = await KnowledgeBaseService.archive_article(
            db=db, article_id=article_id
        )

        logger.info(
            "Article archived",
            extra={"article_id": str(article_id), "archived_by": current_user.email},
        )

        return article

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error archiving article: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ===== VERSION HISTORY =====


@router.get("/articles/{article_id}/versions", response_model=ArticleVersionsResponse)
async def get_article_versions(
    article_id: UUID,
    current_user: User = Depends(require_admin_or_owner),
    db: AsyncSession = Depends(get_db),
):
    """
    Get version history for an article (Admin/Owner only).
    """
    # Verify article exists
    article = await KnowledgeBaseService.get_article(
        db=db, article_id=article_id, include_draft=True
    )
    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Article not found"
        )

    versions = await KnowledgeBaseService.get_article_versions(
        db=db, article_id=article_id
    )

    # Convert ArticleVersion models to ArticleVersionOut schemas
    version_schemas = [ArticleVersionOut.model_validate(version) for version in versions]
    return ArticleVersionsResponse(
        article_id=article_id, versions=version_schemas, total=len(versions)
    )


@router.get(
    "/articles/{article_id}/versions/{version}", response_model=ArticleDetailOut
)
async def get_article_version(
    article_id: UUID,
    version: int,
    current_user: User = Depends(require_admin_or_owner),
    db: AsyncSession = Depends(get_db),
):
    """
    Get specific version of an article (Admin/Owner only).
    """
    version_record = await KnowledgeBaseService.get_article_version(
        db=db, article_id=article_id, version=version
    )

    if not version_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Version not found"
        )

    # Return article at that version state
    article = await KnowledgeBaseService.get_article(
        db=db, article_id=article_id, include_draft=True
    )
    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Article not found"
        )

    return article


# ===== TELEMETRY & STATS =====


@router.get("/articles/{article_id}/stats", response_model=ArticleViewStatsOut)
async def get_article_stats(
    article_id: UUID,
    days: int = 30,
    current_user: User = Depends(require_admin_or_owner),
    db: AsyncSession = Depends(get_db),
):
    """
    Get view statistics for an article (Admin/Owner only).

    - **days**: Look-back period (default: 30)

    Returns total views, unique users, etc.
    """
    if days < 1 or days > 365:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Days must be 1-365"
        )

    stats = await KnowledgeBaseService.get_view_stats(
        db=db, article_id=article_id, days=days
    )
    return ArticleViewStatsOut(**stats)
