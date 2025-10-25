"""Device registry service."""

import logging
from datetime import datetime

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.clients.devices.models import Device
from backend.app.clients.devices.schema import DeviceOut
from backend.app.core.errors import APIError

logger = logging.getLogger(__name__)


class DeviceService:
    """Service for device management.

    Responsibilities:
    - Register devices with HMAC keys
    - Track device status and polling
    - Manage device lifecycle (enable/disable)
    """

    def __init__(self, db: AsyncSession):
        """Initialize service.

        Args:
            db: Database session
        """
        self.db = db

    async def register_device(self, user_id: str, device_name: str) -> DeviceOut:
        """Register new device for user.

        Args:
            user_id: User ID
            device_name: Name for device (e.g., 'Trading PC')

        Returns:
            Device info with HMAC key

        Raises:
            APIError: If registration fails
        """
        try:
            # Generate HMAC key
            hmac_key = Device.generate_hmac_key()

            # Create device
            device = Device(
                user_id=user_id,
                device_name=device_name,
                hmac_key=hmac_key,
                is_active=True,
            )

            self.db.add(device)
            await self.db.commit()
            await self.db.refresh(device)

            logger.info(
                f"Device registered: {user_id} - {device_name}",
                extra={"user_id": user_id, "device_id": device.id},
            )

            return DeviceOut.model_validate(device)

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Device registration failed: {e}", exc_info=True)
            raise APIError(
                status_code=500,
                code="DEVICE_REGISTER_ERROR",
                message="Failed to register device",
            ) from e

    async def list_devices(self, user_id: str) -> list[DeviceOut]:
        """List all devices for user.

        Args:
            user_id: User ID

        Returns:
            List of user's devices
        """
        try:
            result = await self.db.execute(
                select(Device)
                .where(Device.user_id == user_id)
                .order_by(Device.created_at.desc())
            )
            devices = result.scalars().all()

            return [DeviceOut.model_validate(d) for d in devices]

        except Exception as e:
            logger.error(f"Device listing failed: {e}", exc_info=True)
            raise APIError(
                status_code=500,
                code="DEVICE_LIST_ERROR",
                message="Failed to list devices",
            ) from e

    async def get_device(self, user_id: str, device_id: str) -> DeviceOut:
        """Get specific device for user.

        Args:
            user_id: User ID
            device_id: Device ID

        Returns:
            Device info

        Raises:
            APIError: If device not found
        """
        try:
            result = await self.db.execute(
                select(Device).where(
                    and_(
                        Device.user_id == user_id,
                        Device.id == device_id,
                    )
                )
            )
            device = result.scalar()

            if not device:
                raise APIError(
                    status_code=404,
                    code="DEVICE_NOT_FOUND",
                    message="Device not found",
                )

            return DeviceOut.model_validate(device)

        except APIError:
            raise
        except Exception as e:
            logger.error(f"Device retrieval failed: {e}", exc_info=True)
            raise APIError(
                status_code=500,
                code="DEVICE_GET_ERROR",
                message="Failed to retrieve device",
            ) from e

    async def unlink_device(self, user_id: str, device_id: str) -> None:
        """Unlink (deactivate) device for user.

        Args:
            user_id: User ID
            device_id: Device ID

        Raises:
            APIError: If device not found
        """
        try:
            result = await self.db.execute(
                select(Device).where(
                    and_(
                        Device.user_id == user_id,
                        Device.id == device_id,
                    )
                )
            )
            device = result.scalar()

            if not device:
                raise APIError(
                    status_code=404,
                    code="DEVICE_NOT_FOUND",
                    message="Device not found",
                )

            device.is_active = False
            await self.db.commit()

            logger.info(
                f"Device unlinked: {user_id} - {device.device_name}",
                extra={"user_id": user_id, "device_id": device_id},
            )

        except APIError:
            raise
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Device unlinking failed: {e}", exc_info=True)
            raise APIError(
                status_code=500,
                code="DEVICE_UNLINK_ERROR",
                message="Failed to unlink device",
            ) from e

    async def record_poll(self, device_id: str) -> None:
        """Record device polling activity.

        Args:
            device_id: Device ID
        """
        try:
            result = await self.db.execute(select(Device).where(Device.id == device_id))
            device = result.scalar()

            if device:
                device.last_poll = datetime.utcnow()
                await self.db.commit()

        except Exception as e:
            logger.error(f"Poll recording failed: {e}", exc_info=True)
            # Don't raise - poll still succeeds

    async def record_ack(self, device_id: str) -> None:
        """Record device ACK activity.

        Args:
            device_id: Device ID
        """
        try:
            result = await self.db.execute(select(Device).where(Device.id == device_id))
            device = result.scalar()

            if device:
                device.last_ack = datetime.utcnow()
                await self.db.commit()

        except Exception as e:
            logger.error(f"ACK recording failed: {e}", exc_info=True)
            # Don't raise - ACK still succeeds

    async def get_device_by_hmac(self, hmac_key: str) -> Device | None:
        """Get device by HMAC key (for authentication).

        Args:
            hmac_key: HMAC key

        Returns:
            Device or None if not found
        """
        try:
            result = await self.db.execute(
                select(Device).where(
                    and_(
                        Device.hmac_key == hmac_key,
                        Device.is_active == True,  # noqa: E712
                    )
                )
            )
            return result.scalar()

        except Exception as e:
            logger.error(f"HMAC lookup failed: {e}", exc_info=True)
            return None
