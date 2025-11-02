"""API routes for device registry."""

import logging
from typing import cast

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.dependencies import get_current_user
from backend.app.clients.devices.schema import (
    DeviceCreateResponse,
    DeviceOut,
    DeviceRegister,
)
from backend.app.clients.service import DeviceService
from backend.app.core.db import get_db
from backend.app.core.errors import APIError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/devices", tags=["devices"])


@router.post("", status_code=201, response_model=DeviceCreateResponse)
async def register_device(
    request: DeviceRegister,
    db: AsyncSession = Depends(get_db),  # noqa: B008
    current_user=Depends(get_current_user),  # noqa: B008
) -> DeviceCreateResponse:
    """Register new device with HMAC authentication and encryption key.

    Args:
        request: Device registration request

    Returns:
        Device info with HMAC secret and encryption key (shown once only)

    PR-042: Device receives encryption_key for decrypting signal payloads.
    """
    try:
        service = DeviceService(db)
        device, hmac_secret, encryption_key = await service.create_device(
            current_user.id, request.device_name
        )

        logger.info(
            f"Device registered: {current_user.id} - {request.device_name}",
            extra={"user_id": current_user.id, "device_name": request.device_name},
        )

        # Return device with secrets (shown once)
        device_dict = {
            "id": device.id,
            "client_id": device.client_id,
            "device_name": device.device_name,
            "hmac_key_hash": device.hmac_key_hash,
            "last_poll": device.last_poll,
            "last_ack": device.last_ack,
            "is_active": device.is_active,
            "created_at": device.created_at,
            "secret": hmac_secret,
            "encryption_key": encryption_key,
        }
        return DeviceCreateResponse(**device_dict)

    except APIError as e:
        raise e.to_http_exception() from e
    except ValueError as e:
        logger.warning(f"Device registration validation failed: {e}")
        raise APIError(
            status_code=400,
            code="REGISTER_VALIDATION_ERROR",
            message=str(e),
        ).to_http_exception() from e
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
        device = await service.get_device(device_id)

        # Verify ownership
        if device.client_id != current_user.id:
            raise APIError(
                status_code=403,
                code="FORBIDDEN",
                message="You do not have access to this device",
            )

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


@router.patch("/{device_id}", response_model=DeviceOut)
async def rename_device(
    device_id: str,
    request: DeviceRegister,
    db: AsyncSession = Depends(get_db),  # noqa: B008
    current_user=Depends(get_current_user),  # noqa: B008
) -> DeviceOut:
    """Rename device."""
    try:
        service = DeviceService(db)

        # Verify ownership first
        device = await service.get_device(device_id)
        if device.client_id != current_user.id:
            raise APIError(
                status_code=403,
                code="FORBIDDEN",
                message="You do not have access to this device",
            )

        updated = await service.update_device_name(device_id, request.device_name)

        logger.info(
            f"Device renamed: {current_user.id}",
            extra={"user_id": current_user.id, "device_id": device_id},
        )

        return updated

    except APIError as e:
        raise e.to_http_exception() from e
    except ValueError as e:
        logger.warning(f"Device rename validation failed: {e}")
        raise APIError(
            status_code=400,
            code="RENAME_VALIDATION_ERROR",
            message=str(e),
        ).to_http_exception() from e
    except Exception as e:
        logger.error(f"Renaming failed: {e}", exc_info=True)
        raise APIError(
            status_code=500,
            code="RENAME_ERROR",
            message="Failed to rename device",
        ).to_http_exception() from e


@router.post("/{device_id}/revoke", status_code=204)
async def revoke_device(
    device_id: str,
    db: AsyncSession = Depends(get_db),  # noqa: B008
    current_user=Depends(get_current_user),  # noqa: B008
):
    """Revoke (permanently disable) device."""
    try:
        service = DeviceService(db)

        # Verify ownership first
        device = await service.get_device(device_id)
        if device.client_id != current_user.id:
            raise APIError(
                status_code=403,
                code="FORBIDDEN",
                message="You do not have access to this device",
            )

        await service.revoke_device(device_id)

        logger.info(
            f"Device revoked: {current_user.id}",
            extra={"user_id": current_user.id, "device_id": device_id},
        )

    except APIError as e:
        raise e.to_http_exception() from e
    except ValueError as e:
        logger.warning(f"Device revoke validation failed: {e}")
        raise APIError(
            status_code=400,
            code="REVOKE_VALIDATION_ERROR",
            message=str(e),
        ).to_http_exception() from e
    except Exception as e:
        logger.error(f"Revocation failed: {e}", exc_info=True)
        raise APIError(
            status_code=500,
            code="REVOKE_ERROR",
            message="Failed to revoke device",
        ).to_http_exception() from e
