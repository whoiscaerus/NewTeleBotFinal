"""Device registry service."""

from backend.app.clients.models import Device


class DeviceService:
    """Device management service."""

    async def create_device(
        self, client_id: str, name: str, secret_hash: str
    ) -> Device:
        """Create a new device."""
        device = Device(client_id=client_id, name=name, secret_hash=secret_hash)
        return device

    async def list_devices(self, client_id: str):
        """List devices for a client."""
        pass

    async def update_device(self, device_id: str, name: str):
        """Update device name."""
        pass

    async def revoke_device(self, device_id: str):
        """Revoke a device."""
        pass
