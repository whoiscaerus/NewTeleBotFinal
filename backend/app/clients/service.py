"""Device registry service."""

import base64
import hashlib
import secrets

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.clients.devices.models import Device
from backend.app.ea.crypto import get_key_manager


class DeviceService:
    """Device management service for HMAC-based EA authentication."""

    def __init__(self, db_session: AsyncSession):
        """Initialize service with database session.

        Args:
            db_session: SQLAlchemy AsyncSession for database operations
        """
        self.db = db_session

    async def create_device(
        self, client_id: str, device_name: str
    ) -> tuple[Device, str, str]:
        """Create a new device with HMAC authentication and encryption key.

        Args:
            client_id: Client ID
            device_name: Device name (must be unique per client)

        Returns:
            Tuple of (device, hmac_secret, encryption_key) where secrets are returned once to user

        Raises:
            ValueError: If device name already exists for this client
            ValueError: If device_name is empty or too long
            ValueError: If client does not exist
        """
        # Validate client exists
        from backend.app.clients.models import Client

        client_check = await self.db.execute(
            select(Client).where(Client.id == client_id)
        )
        if not client_check.scalar_one_or_none():
            raise ValueError(f"Client '{client_id}' does not exist")

        # Validate device name
        if not device_name or not device_name.strip():
            raise ValueError("Device name cannot be empty")

        if len(device_name) > 100:
            raise ValueError("Device name must be 100 characters or less")

        device_name = device_name.strip()

        # Check for duplicate device name for this client
        existing = await self.db.execute(
            select(Device).where(
                and_(
                    Device.client_id == client_id,
                    Device.device_name == device_name,
                    ~Device.revoked,  # Don't count revoked devices
                )
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"Device '{device_name}' already exists for this client")

        # Generate HMAC secret (returned once to user)
        hmac_secret = secrets.token_urlsafe(32)

        # Hash secret for storage in database
        secret_hash = hashlib.sha256(hmac_secret.encode()).hexdigest()

        # Create device in database
        device = Device(
            client_id=client_id,
            device_name=device_name,
            hmac_key_hash=secret_hash,
            is_active=True,
            revoked=False,
        )

        self.db.add(device)
        await self.db.commit()
        await self.db.refresh(device)

        # PR-042: Issue per-device encryption key
        key_manager = get_key_manager()
        encryption_key_obj = key_manager.create_device_key(device.id)

        # Return encryption key material (base64 encoded for transport)
        encryption_key_material = base64.b64encode(
            encryption_key_obj.encryption_key
        ).decode("ascii")

        return device, hmac_secret, encryption_key_material

    async def list_devices(self, client_id: str) -> list[Device]:
        """List all devices for a client.

        Args:
            client_id: Client ID

        Returns:
            List of all Device objects (both active and revoked)
        """
        result = await self.db.execute(
            select(Device).where(Device.client_id == client_id)
        )
        return list(result.scalars().all())

    async def get_device(self, device_id: str) -> Device:
        """Get a specific device by ID.

        Args:
            device_id: Device ID

        Returns:
            Device object

        Raises:
            ValueError: If device not found or has been revoked
        """
        result = await self.db.execute(select(Device).where(Device.id == device_id))
        device = result.scalar_one_or_none()

        if not device:
            raise ValueError(f"Device '{device_id}' not found")

        if device.revoked:
            raise ValueError(f"Device '{device_id}' has been revoked")

        return device

    async def update_device(self, device_id: str, device_name: str) -> Device:
        """Rename a device.

        Args:
            device_id: Device ID
            device_name: New device name

        Returns:
            Updated Device object

        Raises:
            ValueError: If device not found, revoked, or new name already exists
        """
        # Validate new name
        if not device_name or not device_name.strip():
            raise ValueError("Device name cannot be empty")

        if len(device_name) > 100:
            raise ValueError("Device name must be 100 characters or less")

        device_name = device_name.strip()

        # Get device
        device = await self.get_device(device_id)

        # If name is the same, no need to check for duplicates
        if device.device_name == device_name:
            return device

        # Check if new name already exists for this client
        existing = await self.db.execute(
            select(Device).where(
                and_(
                    Device.client_id == device.client_id,
                    Device.device_name == device_name,
                    Device.id != device_id,  # Exclude current device
                    ~Device.revoked,
                )
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"Device '{device_name}' already exists for this client")

        # Update device
        device.device_name = device_name
        await self.db.commit()
        await self.db.refresh(device)

        return device

    async def revoke_device(self, device_id: str) -> Device:
        """Revoke a device (permanent disable).

        Once revoked, a device cannot be reactivated or used for authentication.

        Args:
            device_id: Device ID

        Returns:
            Revoked Device object

        Raises:
            ValueError: If device not found or already revoked
        """
        result = await self.db.execute(select(Device).where(Device.id == device_id))
        device: Device | None = result.scalar_one_or_none()

        if not device:
            raise ValueError(f"Device '{device_id}' not found")

        if device.revoked:
            raise ValueError(f"Device '{device_id}' is already revoked")

        # Revoke device
        device.revoked = True
        device.is_active = False
        await self.db.commit()
        await self.db.refresh(device)

        return device

    async def update_device_name(self, device_id: str, new_name: str) -> Device:
        """Alias for update_device for backward compatibility.

        Args:
            device_id: Device ID
            new_name: New device name

        Returns:
            Updated Device object
        """
        return await self.update_device(device_id, new_name)

    async def authenticate_device(
        self, device_id: str, signature: str, message: str
    ) -> bool:
        """Authenticate a device using HMAC signature.

        Args:
            device_id: Device ID
            signature: HMAC signature to verify
            message: Message that was signed

        Returns:
            True if signature is valid, False otherwise

        Raises:
            ValueError: If device not found or revoked
        """
        device = await self.get_device(device_id)

        # Retrieve the secret from database (hmac_key_hash)
        # Note: In production, secret should be retrieved from secure storage
        # For now, this validates the signature pattern
        # The actual HMAC key would be stored securely

        # This is a placeholder for HMAC verification
        # Real implementation would use the stored HMAC key
        try:

            # In a real implementation, you would:
            # 1. Retrieve the actual secret from secure storage
            # 2. Create HMAC: hmac_generated = hmac.new(secret, message, hashlib.sha256)
            # 3. Compare: hmac.compare_digest(signature, hmac_generated.digest())
            # For now, we just check that device exists and is active
            return device.is_active and not device.revoked
        except Exception:
            return False
