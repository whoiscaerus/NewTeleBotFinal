"""
Copy Registry API Routes

REST endpoints for managing copy entries and resolving text.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.copy.schemas import (
    CopyConversionRequest,
    CopyEntryCreate,
    CopyEntryResponse,
    CopyEntryUpdate,
    CopyImpressionRequest,
    CopyResolveRequest,
    CopyResolveResponse,
    CopyVariantCreate,
    CopyVariantResponse,
)
from backend.app.copy.service import CopyService
from backend.app.core.db import get_db
from backend.app.auth.models import User

router = APIRouter(prefix="/api/v1/copy", tags=["copy"])


def get_current_user() -> User:
    """Placeholder for auth dependency."""
    # TODO: Replace with actual JWT auth from PR-006
    return User(id="test-user-id", email="test@example.com")


def get_copy_service(db: AsyncSession = Depends(get_db)) -> CopyService:
    """Dependency for copy service."""
    return CopyService(db)


@router.post(
    "/entries", status_code=status.HTTP_201_CREATED, response_model=CopyEntryResponse
)
async def create_entry(
    data: CopyEntryCreate,
    service: CopyService = Depends(get_copy_service),
    current_user: User = Depends(get_current_user),
):
    """
    Create a new copy entry with variants.

    Requires admin/editor permissions.
    """
    try:
        entry = await service.create_entry(data, user_id=current_user.id)
        return entry
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/entries", response_model=list[CopyEntryResponse])
async def list_entries(
    type: str | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
    service: CopyService = Depends(get_copy_service),
    current_user: User = Depends(get_current_user),
):
    """
    List copy entries with optional filters.

    Requires admin/editor permissions.
    """
    entries = await service.list_entries(
        type=type, status=status, limit=limit, offset=offset
    )
    return entries


@router.get("/entries/{entry_id}", response_model=CopyEntryResponse)
async def get_entry(
    entry_id: str,
    service: CopyService = Depends(get_copy_service),
    current_user: User = Depends(get_current_user),
):
    """
    Get copy entry by ID.

    Requires admin/editor permissions.
    """
    entry = await service.get_entry(entry_id)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Copy entry not found"
        )
    return entry


@router.patch("/entries/{entry_id}", response_model=CopyEntryResponse)
async def update_entry(
    entry_id: str,
    data: CopyEntryUpdate,
    service: CopyService = Depends(get_copy_service),
    current_user: User = Depends(get_current_user),
):
    """
    Update copy entry.

    Requires admin/editor permissions.
    """
    entry = await service.update_entry(entry_id, data, user_id=current_user.id)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Copy entry not found"
        )
    return entry


@router.delete("/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entry(
    entry_id: str,
    service: CopyService = Depends(get_copy_service),
    current_user: User = Depends(get_current_user),
):
    """
    Delete copy entry (and cascade variants).

    Requires admin permissions.
    """
    deleted = await service.delete_entry(entry_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Copy entry not found"
        )


@router.post(
    "/entries/{entry_id}/variants",
    status_code=status.HTTP_201_CREATED,
    response_model=CopyVariantResponse,
)
async def add_variant(
    entry_id: str,
    data: CopyVariantCreate,
    service: CopyService = Depends(get_copy_service),
    current_user: User = Depends(get_current_user),
):
    """
    Add variant to existing entry.

    Requires admin/editor permissions.
    """
    variant = await service.add_variant(entry_id, data)
    if not variant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Copy entry not found"
        )
    return variant


@router.post("/resolve", response_model=CopyResolveResponse)
async def resolve_copy(
    data: CopyResolveRequest,
    service: CopyService = Depends(get_copy_service),
):
    """
    Resolve copy text for given keys.

    Public endpoint (no auth required) for frontend use.
    Optionally records impressions for A/B testing.
    """
    resolved, missing = await service.resolve_copy(
        keys=data.keys,
        locale=data.locale,
        ab_group=data.ab_group,
        record_impression=data.record_impression,
    )

    return CopyResolveResponse(
        locale=data.locale, ab_group=data.ab_group, copy=resolved, missing=missing
    )


@router.post("/impression", status_code=status.HTTP_204_NO_CONTENT)
async def record_impression(
    data: CopyImpressionRequest, service: CopyService = Depends(get_copy_service)
):
    """
    Record impression for copy variant.

    Used for A/B testing metrics.
    """
    recorded = await service.record_impression(
        key=data.key, locale=data.locale, ab_group=data.ab_group
    )
    if not recorded:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Copy variant not found"
        )


@router.post("/conversion", status_code=status.HTTP_204_NO_CONTENT)
async def record_conversion(
    data: CopyConversionRequest, service: CopyService = Depends(get_copy_service)
):
    """
    Record conversion for copy variant.

    Used for A/B testing metrics.
    """
    recorded = await service.record_conversion(
        key=data.key, locale=data.locale, ab_group=data.ab_group
    )
    if not recorded:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Copy variant not found"
        )
