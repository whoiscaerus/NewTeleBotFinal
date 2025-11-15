"""Theme API routes."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.dependencies import get_current_user
from backend.app.auth.models import User
from backend.app.core.db import get_db
from backend.app.observability.metrics import get_metrics
from backend.app.profile.theme import ThemeService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/profile", tags=["profile", "theme"])


class ThemeResponse(BaseModel):
    """Response model for theme."""

    theme: str = Field(..., description="Current theme name")


class ThemeUpdateRequest(BaseModel):
    """Request model for updating theme."""

    theme: str = Field(
        ...,
        description="Theme name to set",
        examples=["professional", "darkTrader", "goldMinimal"],
    )


class ThemeListResponse(BaseModel):
    """Response model for available themes."""

    themes: list[str] = Field(..., description="List of available theme names")


@router.get("/theme", response_model=ThemeResponse)
async def get_theme(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get user's current theme preference.

    Returns the theme stored in the user's profile, which is also
    included in JWT claims for consistency across SSR/CSR.

    Args:
        current_user: Authenticated user
        db: Database session

    Returns:
        ThemeResponse: Current theme name

    Example:
        >>> GET /api/v1/profile/theme
        >>> {"theme": "darkTrader"}
    """
    service = ThemeService(db)
    theme = await service.get_theme(current_user)

    logger.info(
        f"Theme retrieved for user {current_user.id}: {theme}",
        extra={"user_id": current_user.id, "theme": theme},
    )

    return ThemeResponse(theme=theme)


@router.put("/theme", response_model=ThemeResponse)
async def update_theme(
    request: ThemeUpdateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Update user's theme preference.

    Persists theme to database and increments telemetry counter.
    Theme is also included in subsequent JWT tokens for SSR/CSR consistency.

    Args:
        request: Theme update request
        current_user: Authenticated user
        db: Database session

    Returns:
        ThemeResponse: Updated theme name

    Raises:
        HTTPException: 400 if theme name is invalid

    Example:
        >>> PUT /api/v1/profile/theme
        >>> {"theme": "goldMinimal"}
        >>> Response: {"theme": "goldMinimal"}
    """
    service = ThemeService(db)
    metrics = get_metrics()

    try:
        theme = await service.set_theme(current_user, request.theme)

        # Increment telemetry counter (PR-090 requirement)
        metrics.theme_selected_total.labels(name=theme).inc()

        logger.info(
            f"Theme updated for user {current_user.id}: {theme}",
            extra={"user_id": current_user.id, "theme": theme},
        )

        return ThemeResponse(theme=theme)

    except ValueError as e:
        logger.warning(
            f"Invalid theme requested by user {current_user.id}: {request.theme}",
            extra={"user_id": current_user.id, "requested_theme": request.theme},
        )
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/themes", response_model=ThemeListResponse)
async def list_themes():
    """Get list of available themes.

    Public endpoint (no auth required) for discovery.

    Returns:
        ThemeListResponse: List of available theme names

    Example:
        >>> GET /api/v1/profile/themes
        >>> {"themes": ["darkTrader", "goldMinimal", "professional"]}
    """
    themes = ThemeService.get_valid_themes()

    return ThemeListResponse(themes=themes)
