"""Privacy request API routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import get_current_user
from backend.app.core.db import get_db
from backend.app.core.logging import get_logger
from backend.app.privacy.schemas import (
    PrivacyRequestCancel,
    PrivacyRequestCreate,
    PrivacyRequestHold,
    PrivacyRequestResponse,
)
from backend.app.privacy.service import PrivacyService
from backend.app.auth.models import User

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/privacy", tags=["privacy"])


@router.post(
    "/requests",
    status_code=status.HTTP_201_CREATED,
    response_model=PrivacyRequestResponse,
)
async def create_privacy_request(
    request_data: PrivacyRequestCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new privacy request (export or delete).

    **Export Request**: Generates ZIP bundle with user data (JSON/CSV).
    **Delete Request**: Schedules deletion after cooling-off period (72 hours).

    **Restrictions**:
    - Only one pending request of each type allowed
    - Delete requests can be held by admin for active disputes
    """
    service = PrivacyService(db)

    try:
        request = await service.create_request(current_user.id, request_data)

        logger.info(
            "Privacy request created",
            extra={
                "user_id": current_user.id,
                "request_id": request.id,
                "request_type": request.request_type,
            },
        )

        return request

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/requests", response_model=list[PrivacyRequestResponse])
async def list_privacy_requests(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List all privacy requests for current user.

    Returns requests in descending order by creation date.
    """
    service = PrivacyService(db)
    requests = await service.list_requests(current_user.id)
    return requests


@router.get("/requests/{request_id}", response_model=PrivacyRequestResponse)
async def get_privacy_request(
    request_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get privacy request by ID.

    **Authorization**: Users can only access their own requests.
    """
    service = PrivacyService(db)
    request = await service.get_request(request_id, current_user.id)

    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Request not found"
        )

    return request


@router.post("/requests/{request_id}/cancel", response_model=PrivacyRequestResponse)
async def cancel_privacy_request(
    request_id: str,
    cancel_data: PrivacyRequestCancel,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Cancel a pending privacy request.

    **Allowed for**: Pending or on-hold requests only.
    """
    service = PrivacyService(db)

    try:
        request = await service.cancel_request(
            request_id, current_user.id, cancel_data.reason
        )

        logger.info(
            "Privacy request cancelled",
            extra={
                "user_id": current_user.id,
                "request_id": request_id,
                "reason": cancel_data.reason,
            },
        )

        return request

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/requests/{request_id}/hold", response_model=PrivacyRequestResponse)
async def place_hold_on_request(
    request_id: str,
    hold_data: PrivacyRequestHold,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Place admin hold on delete request.

    **Admin Only**: Prevents deletion during active disputes/chargebacks.
    **Allowed for**: Delete requests only.

    **Example Reasons**:
    - Active chargeback dispute
    - Pending refund investigation
    - Legal hold
    """
    # Check admin permission
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin permission required",
        )

    service = PrivacyService(db)

    try:
        request = await service.place_hold(
            request_id, hold_data.reason, current_user.id
        )

        logger.info(
            "Hold placed on privacy request",
            extra={
                "admin_id": current_user.id,
                "request_id": request_id,
                "reason": hold_data.reason,
            },
        )

        return request

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/requests/{request_id}/release-hold", response_model=PrivacyRequestResponse
)
async def release_hold_on_request(
    request_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Release admin hold on delete request.

    **Admin Only**: Allows deletion to proceed after dispute resolution.
    """
    # Check admin permission
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin permission required",
        )

    service = PrivacyService(db)

    try:
        request = await service.release_hold(request_id, current_user.id)

        logger.info(
            "Hold released on privacy request",
            extra={
                "admin_id": current_user.id,
                "request_id": request_id,
            },
        )

        return request

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# Background job endpoints (called by scheduler/worker)


@router.post("/internal/process-export/{request_id}", include_in_schema=False)
async def process_export_request_internal(
    request_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Internal endpoint to process export request.

    Called by background worker/scheduler.
    """
    service = PrivacyService(db)

    try:
        request = await service.process_export_request(request_id)
        return {
            "status": "completed",
            "request_id": request.id,
            "export_url": request.export_url,
        }

    except ValueError as e:
        logger.error(f"Export processing failed: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    except Exception as e:
        logger.error(f"Export processing error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Export processing failed",
        )


@router.post("/internal/process-delete/{request_id}", include_in_schema=False)
async def process_delete_request_internal(
    request_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Internal endpoint to process delete request.

    Called by background worker/scheduler after cooling-off period.
    """
    service = PrivacyService(db)

    try:
        request = await service.process_delete_request(request_id)
        return {"status": "completed", "request_id": request.id}

    except ValueError as e:
        logger.error(f"Delete processing failed: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    except Exception as e:
        logger.error(f"Delete processing error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Delete processing failed",
        )
