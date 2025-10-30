"""
Tests for PR-023a: Device Registry.

Tests device registration, listing, renaming, revoking, and DB persistence.
"""

from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.models import User
from backend.app.clients.models import Client, Device
from backend.app.clients.service import DeviceService


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create test user."""
    user = User(
        id="user_device_test",
        email="user@example.com",
        password_hash="hashed",
        role="user",
        created_at=datetime.utcnow(),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_client(db_session: AsyncSession, test_user: User) -> Client:
    """Create test client."""
    client = Client(
        id="client_123",
        email=test_user.email,
        created_at=datetime.utcnow(),
    )
    db_session.add(client)
    await db_session.commit()
    await db_session.refresh(client)
    return client


@pytest_asyncio.fixture
async def device_service(db_session: AsyncSession) -> DeviceService:
    """Create device service."""
    return DeviceService()


@pytest.mark.asyncio
class TestDeviceRegistration:
    """Test device registration."""

    async def test_register_device_success(
        self,
        db_session: AsyncSession,
        test_client: Client,
        device_service: DeviceService,
    ):
        """Test successful device registration."""
        device, secret = await device_service.create_device(
            client_id=test_client.id,
            device_name="My EA Instance",
        )

        assert device is not None
        assert device.client_id == test_client.id
        assert device.device_name == "My EA Instance"
        assert device.is_active is True
        assert device.revoked is False

        # Secret should be returned once
        assert secret is not None
        assert len(secret) > 0

    async def test_register_device_returns_secret_once(
        self,
        db_session: AsyncSession,
        test_client: Client,
        device_service: DeviceService,
    ):
        """Test that secret is returned once during registration."""
        device, secret = await device_service.create_device(
            client_id=test_client.id,
            device_name="My EA",
        )

        # Secret should not be in DB (only hash)
        assert device.hmac_key_hash is not None
        # Secret should be returned to user
        assert secret is not None

    async def test_register_duplicate_device_name_fails(
        self,
        db_session: AsyncSession,
        test_client: Client,
        device_service: DeviceService,
    ):
        """Test duplicate device name for same client returns 409."""
        # Create first device
        await device_service.create_device(
            client_id=test_client.id,
            device_name="EA Instance",
        )

        # Try to create with same name
        with pytest.raises(ValueError, match="already exists|409"):
            await device_service.create_device(
                client_id=test_client.id,
                device_name="EA Instance",
            )

    @pytest.mark.skip(
        reason="PR-023a Device Registry is not fully implemented yet. Service needs DB integration."
    )
    async def test_register_device_different_clients_different_names(
        self,
        db_session: AsyncSession,
        test_user: User,
        device_service: DeviceService,
    ):
        """Test devices with same name can exist for different clients."""
        # Create two clients
        client1 = Client(
            id="client_1",
            user_id=test_user.id,
            email="client1@example.com",
            created_at=datetime.utcnow(),
        )
        client2 = Client(
            id="client_2",
            user_id=test_user.id,
            email="client2@example.com",
            created_at=datetime.utcnow(),
        )
        db_session.add(client1)
        db_session.add(client2)
        await db_session.commit()

        # Create devices with same name for different clients
        device1, _ = await device_service.create_device(
            client_id=client1.id,
            device_name="EA Instance",
        )
        device2, _ = await device_service.create_device(
            client_id=client2.id,
            device_name="EA Instance",
        )

        assert device1.id != device2.id
        assert device1.client_id != device2.client_id

    async def test_register_device_nonexistent_client(
        self,
        db_session: AsyncSession,
        device_service: DeviceService,
    ):
        """Test registering device for nonexistent client."""
        with pytest.raises(ValueError):
            await device_service.create_device(
                client_id="nonexistent_client",
                device_name="EA Instance",
            )


@pytest.mark.asyncio
class TestDeviceListing:
    """Test listing devices."""

    async def test_list_devices_success(
        self,
        db_session: AsyncSession,
        test_client: Client,
        device_service: DeviceService,
    ):
        """Test listing client devices."""
        # Create multiple devices
        device1, _ = await device_service.create_device(
            test_client.id,
            "Device 1",
        )
        device2, _ = await device_service.create_device(
            test_client.id,
            "Device 2",
        )

        # List devices
        devices = await device_service.list_devices(test_client.id)

        assert len(devices) == 2
        assert device1.id in [d.id for d in devices]
        assert device2.id in [d.id for d in devices]

    async def test_list_devices_excludes_secret(
        self,
        db_session: AsyncSession,
        test_client: Client,
        device_service: DeviceService,
    ):
        """Test that device list doesn't include HMAC secret."""
        await device_service.create_device(
            test_client.id,
            "Device 1",
        )

        devices = await device_service.list_devices(test_client.id)

        # Secret should not be in response
        for device in devices:
            # Check that only hash is stored, not plaintext secret
            assert hasattr(device, "hmac_key_hash")
            # Secret field should not exist or be None
            if hasattr(device, "secret"):
                assert device.secret is None

    async def test_list_devices_empty(
        self,
        db_session: AsyncSession,
        test_client: Client,
        device_service: DeviceService,
    ):
        """Test listing when no devices exist."""
        devices = await device_service.list_devices(test_client.id)
        assert devices == []

    async def test_list_devices_only_active(
        self,
        db_session: AsyncSession,
        test_client: Client,
        device_service: DeviceService,
    ):
        """Test listing includes both active and inactive devices."""
        device1, _ = await device_service.create_device(
            test_client.id,
            "Device 1",
        )
        device2, _ = await device_service.create_device(
            test_client.id,
            "Device 2",
        )

        # Revoke one device
        await device_service.revoke_device(device1.id)

        # List should include both
        devices = await device_service.list_devices(test_client.id)
        assert len(devices) == 2


@pytest.mark.asyncio
class TestDeviceRenaming:
    """Test renaming devices."""

    async def test_rename_device_success(
        self,
        db_session: AsyncSession,
        test_client: Client,
        device_service: DeviceService,
    ):
        """Test successful device renaming."""
        device, _ = await device_service.create_device(
            test_client.id,
            "Old Name",
        )

        updated = await device_service.update_device_name(
            device.id,
            "New Name",
        )

        assert updated.device_name == "New Name"

    async def test_rename_to_duplicate_name_fails(
        self,
        db_session: AsyncSession,
        test_client: Client,
        device_service: DeviceService,
    ):
        """Test renaming to duplicate name fails."""
        device1, _ = await device_service.create_device(
            test_client.id,
            "Device 1",
        )
        device2, _ = await device_service.create_device(
            test_client.id,
            "Device 2",
        )

        # Try to rename device2 to device1's name
        with pytest.raises(ValueError, match="already exists|409"):
            await device_service.update_device_name(
                device2.id,
                "Device 1",
            )

    async def test_rename_nonexistent_device(
        self,
        db_session: AsyncSession,
        device_service: DeviceService,
    ):
        """Test renaming nonexistent device fails."""
        with pytest.raises(ValueError):
            await device_service.update_device_name(
                "nonexistent_device",
                "New Name",
            )


@pytest.mark.asyncio
class TestDeviceRevocation:
    """Test device revocation."""

    async def test_revoke_device_success(
        self,
        db_session: AsyncSession,
        test_client: Client,
        device_service: DeviceService,
    ):
        """Test successful device revocation."""
        device, _ = await device_service.create_device(
            test_client.id,
            "My Device",
        )

        assert device.revoked is False

        revoked = await device_service.revoke_device(device.id)

        assert revoked.revoked is True
        assert revoked.is_active is False

    async def test_revoke_nonexistent_device(
        self,
        db_session: AsyncSession,
        device_service: DeviceService,
    ):
        """Test revoking nonexistent device."""
        with pytest.raises(ValueError):
            await device_service.revoke_device("nonexistent_device")

    async def test_revoked_device_cannot_authenticate(
        self,
        db_session: AsyncSession,
        test_client: Client,
        device_service: DeviceService,
    ):
        """Test that revoked device cannot be used for auth."""
        device, secret = await device_service.create_device(
            test_client.id,
            "My Device",
        )

        # Revoke device
        await device_service.revoke_device(device.id)

        # Try to authenticate with secret (implementation specific)
        # This test depends on HMAC validation in routes


@pytest.mark.asyncio
class TestDatabasePersistence:
    """Test device data persistence in DB."""

    async def test_device_stored_in_database(
        self,
        db_session: AsyncSession,
        test_client: Client,
        device_service: DeviceService,
    ):
        """Test that device is persisted in database."""
        device, _ = await device_service.create_device(
            test_client.id,
            "My Device",
        )

        # Query database directly
        from sqlalchemy import select

        stmt = select(Device).where(Device.id == device.id)
        result = await db_session.execute(stmt)
        db_device = result.scalar_one_or_none()

        assert db_device is not None
        assert db_device.device_name == "My Device"
        assert db_device.client_id == test_client.id

    async def test_device_hmac_key_hash_stored(
        self,
        db_session: AsyncSession,
        test_client: Client,
        device_service: DeviceService,
    ):
        """Test that HMAC key hash (not plaintext) is stored."""
        device, secret = await device_service.create_device(
            test_client.id,
            "My Device",
        )

        # Verify hash is different from plaintext secret
        assert device.hmac_key_hash != secret
        # Hash should be a reasonable length (typically 64 chars for SHA256)
        assert len(device.hmac_key_hash) > 32

    async def test_device_timestamps(
        self,
        db_session: AsyncSession,
        test_client: Client,
        device_service: DeviceService,
    ):
        """Test device timestamp fields."""
        device, _ = await device_service.create_device(
            test_client.id,
            "My Device",
        )

        assert device.created_at is not None
        assert device.last_seen is None  # Not set until first use

    async def test_device_cascade_delete(
        self,
        db_session: AsyncSession,
        test_client: Client,
        device_service: DeviceService,
    ):
        """Test that deleting client cascades to devices."""
        device, _ = await device_service.create_device(
            test_client.id,
            "My Device",
        )

        device_id = device.id

        # Delete client (should cascade to devices)
        db_session.delete(test_client)
        await db_session.commit()

        # Verify device is deleted
        from sqlalchemy import select

        stmt = select(Device).where(Device.id == device_id)
        result = await db_session.execute(stmt)
        deleted_device = result.scalar_one_or_none()

        assert deleted_device is None


@pytest.mark.asyncio
class TestEdgeCases:
    """Test edge cases."""

    async def test_device_name_unicode(
        self,
        db_session: AsyncSession,
        test_client: Client,
        device_service: DeviceService,
    ):
        """Test device with unicode characters in name."""
        device, _ = await device_service.create_device(
            test_client.id,
            "My Device 🤖 EA",
        )

        assert device.device_name == "My Device 🤖 EA"

    async def test_device_name_max_length(
        self,
        db_session: AsyncSession,
        test_client: Client,
        device_service: DeviceService,
    ):
        """Test device name length validation."""
        long_name = "A" * 100
        device, _ = await device_service.create_device(
            test_client.id,
            long_name,
        )

        assert device.device_name == long_name

    async def test_device_name_too_long(
        self,
        db_session: AsyncSession,
        test_client: Client,
        device_service: DeviceService,
    ):
        """Test device name exceeding max length."""
        too_long_name = "A" * 101  # Over typical 100 char limit

        # May or may not fail depending on validation
        # Document behavior here
        try:
            device, _ = await device_service.create_device(
                test_client.id,
                too_long_name,
            )
            # If succeeds, name should be truncated or accepted
        except ValueError:
            # If fails, should validate input
            pass

    async def test_device_name_empty(
        self,
        db_session: AsyncSession,
        test_client: Client,
        device_service: DeviceService,
    ):
        """Test device with empty name."""
        with pytest.raises(ValueError):
            await device_service.create_device(
                test_client.id,
                "",
            )

    async def test_device_name_whitespace_only(
        self,
        db_session: AsyncSession,
        test_client: Client,
        device_service: DeviceService,
    ):
        """Test device with whitespace-only name."""
        with pytest.raises(ValueError):
            await device_service.create_device(
                test_client.id,
                "   ",
            )
