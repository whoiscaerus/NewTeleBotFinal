"""API routes for device registry."""

import logging
from typing import cast

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.rbac import get_current_user
from backend.app.clients.devices.schema import DeviceOut, DeviceRegister
from backend.app.clients.devices.service import DeviceService
from backend.app.core.db import get_db
from backend.app.core.errors import APIError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/devices", tags=["devices"])


@router.post("", status_code=201, response_model=DeviceOut)
async def register_device(
    request: DeviceRegister,
    db: AsyncSession = Depends(get_db),  # noqa: B008
    current_user=Depends(get_current_user),  # noqa: B008
) -> DeviceOut:
    """Register new device.

    Args:
        request: Device registration request

    Returns:
        Device info with HMAC key for authentication
    """
    try:
        service = DeviceService(db)
        device = await service.register_device(current_user.id, request.device_name)

        logger.info(
            f"Device registered: {current_user.id} - {request.device_name}",
            extra={"user_id": current_user.id, "device_name": request.device_name},
        )

        return device

    except APIError as e:
        raise e.to_http_exception() from e
    except Exception as e:
        logger.error(f"Registration failed: {e}", exc_info=True)
        raise APIError(
            status_code=500,
            code="REGISTER_ERROR",
            message="Failed to register device",
        ).to_http_exception() from e


@router.get("", response_model=list[DeviceOut])
async def list_devices(
    db: AsyncSession = Depends(get_db),  # noqa: B008
    current_user=Depends(get_current_user),  # noqa: B008
) -> list[DeviceOut]:
    """List user's devices."""
    try:
        service = DeviceService(db)
        result = await service.list_devices(current_user.id)
        return cast(list[DeviceOut], result)

    except APIError as e:
        raise e.to_http_exception() from e
    except Exception as e:
        logger.error(f"Listing failed: {e}", exc_info=True)
        raise APIError(
            status_code=500,
            code="LIST_ERROR",
            message="Failed to list devices",
        ).to_http_exception() from e


@router.get("/{device_id}", response_model=DeviceOut)
async def get_device(
    device_id: str,
    db: AsyncSession = Depends(get_db),  # noqa: B008
    current_user=Depends(get_current_user),  # noqa: B008
) -> DeviceOut:
    """Get specific device."""
    try:
        service = DeviceService(db)
        device = await service.get_device(current_user.id, device_id)
        return device

    except APIError as e:
        raise e.to_http_exception() from e
    except Exception as e:
        logger.error(f"Retrieval failed: {e}", exc_info=True)
        raise APIError(
            status_code=500,
            code="GET_ERROR",
            message="Failed to get device",
        ).to_http_exception() from e


@router.delete("/{device_id}", status_code=204)
async def unlink_device(
    device_id: str,
    db: AsyncSession = Depends(get_db),  # noqa: B008
    current_user=Depends(get_current_user),  # noqa: B008
):
    """Unlink (deactivate) device."""
    try:
        service = DeviceService(db)
        await service.unlink_device(current_user.id, device_id)

        logger.info(
            f"Device unlinked: {current_user.id}",
            extra={"user_id": current_user.id, "device_id": device_id},
        )

    except APIError as e:
        raise e.to_http_exception() from e
    except Exception as e:
        logger.error(f"Unlinking failed: {e}", exc_info=True)
        raise APIError(
            status_code=500,
            code="UNLINK_ERROR",
            message="Failed to unlink device",
        ).to_http_exception() from e
