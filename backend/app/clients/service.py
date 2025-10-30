"""Device registry service."""

import secrets

from backend.app.clients.devices.models import Device


class DeviceService:
    """Device management service."""

    async def create_device(
        self, client_id: str, device_name: str
    ) -> tuple[Device, str]:
        """Create a new device.

        Args:
            client_id: Client ID
            device_name: Device name

        Returns:
            Tuple of (device, secret) where secret is returned once to user
        """
        # Generate HMAC secret
        secret = secrets.token_urlsafe(32)
        # Hash the secret for storage
        import hashlib

        secret_hash = hashlib.sha256(secret.encode()).hexdigest()

        device = Device(
            client_id=client_id,
            device_name=device_name,
            hmac_key_hash=secret_hash,
            is_active=True,
            revoked=False,
        )
        return device, secret

    async def list_devices(self, client_id: str):
        """List devices for a client."""
        pass

    async def update_device(self, device_id: str, device_name: str):
        """Update device name."""
        pass

    async def revoke_device(self, device_id: str):
        """Revoke a device."""
        pass
