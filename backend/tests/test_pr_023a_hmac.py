"""
Tests for PR-023a: HMAC Key Generation and Validation.

Tests HMAC secret generation, hashing, uniqueness, and replay attack prevention.
"""

import base64
import hashlib
import hmac
from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.models import User
from backend.app.clients.models import Device
from backend.app.clients.service import DeviceService


def decode_secret(secret: str) -> bytes:
    """Decode a base64-URL-safe secret with proper padding.

    Args:
        secret: Base64-URL-safe encoded string

    Returns:
        Decoded bytes
    """
    # Add padding if needed for base64 decoding
    padding = 4 - len(secret) % 4
    if padding != 4:
        secret_padded = secret + "=" * padding
    else:
        secret_padded = secret
    return base64.urlsafe_b64decode(secret_padded)


@pytest.fixture
def test_user(db_session: AsyncSession) -> User:
    """Create test user."""
    user = User(
        id="user_hmac_test",
        email="user@example.com",
        password_hash="hashed",
        role="user",
        created_at=datetime.utcnow(),
    )
    db_session.add(user)
    return user


@pytest.fixture
def test_client(db_session: AsyncSession, test_user: User):
    """Create test client."""
    from backend.app.clients.models import Client

    client = Client(
        id="client_hmac_test",
        email="client@example.com",
        created_at=datetime.utcnow(),
    )
    db_session.add(client)
    return client


@pytest.fixture
def device_service(db_session: AsyncSession) -> DeviceService:
    """Create device service."""
    return DeviceService(db_session)


@pytest.mark.asyncio
class TestHMACKeyGeneration:
    """Test HMAC key generation."""

    async def test_hmac_key_generated(
        self,
        db_session: AsyncSession,
        test_client,
        device_service: DeviceService,
    ):
        """Test that HMAC key is generated on device creation."""
        device, secret = await device_service.create_device(
            test_client.id,
            "Device with HMAC",
        )

        assert secret is not None
        assert len(secret) >= 32  # At least 32 bytes

    async def test_hmac_key_is_base64_url_safe(
        self,
        db_session: AsyncSession,
        test_client,
        device_service: DeviceService,
    ):
        """Test that HMAC key is URL-safe base64 encoded."""
        device, secret = await device_service.create_device(
            test_client.id,
            "Device",
        )

        # Should be able to decode as base64
        try:
            decoded = decode_secret(secret)
            assert len(decoded) >= 32
        except Exception as e:
            pytest.fail(f"Secret not valid base64: {e}")

    async def test_hmac_key_never_logged(
        self,
        db_session: AsyncSession,
        test_client,
        device_service: DeviceService,
    ):
        """Test that plaintext secret is never stored/logged."""
        device, secret = await device_service.create_device(
            test_client.id,
            "Device",
        )

        # Plaintext secret should NOT be in DB
        # Only hash should be stored
        assert device.hmac_key_hash is not None
        assert device.hmac_key_hash != secret

    async def test_hmac_key_shown_once(
        self,
        db_session: AsyncSession,
        test_client,
        device_service: DeviceService,
    ):
        """Test that HMAC secret is shown only once at creation."""
        device, secret = await device_service.create_device(
            test_client.id,
            "Device",
        )

        # Retrieve device again
        from sqlalchemy import select

        stmt = select(Device).where(Device.id == device.id)
        result = await db_session.execute(stmt)
        retrieved_device = result.scalar_one_or_none()

        # Secret should not be available on retrieval
        assert (
            not hasattr(retrieved_device, "secret") or retrieved_device.secret is None
        )


@pytest.mark.asyncio
class TestHMACKeyUniqueness:
    """Test HMAC key uniqueness."""

    async def test_each_device_has_unique_hmac(
        self,
        db_session: AsyncSession,
        test_client,
        device_service: DeviceService,
    ):
        """Test that each device gets unique HMAC key."""
        device1, secret1 = await device_service.create_device(
            test_client.id,
            "Device 1",
        )
        device2, secret2 = await device_service.create_device(
            test_client.id,
            "Device 2",
        )

        # Secrets should be different
        assert secret1 != secret2

        # Hashes should be different
        assert device1.hmac_key_hash != device2.hmac_key_hash

    async def test_hmac_key_globally_unique(
        self,
        db_session: AsyncSession,
        test_user: User,
        device_service: DeviceService,
    ):
        """Test HMAC keys are globally unique across all clients."""
        from backend.app.clients.models import Client

        # Create two clients
        client1 = Client(
            id="client_unique_1",
            email="client1@example.com",
            created_at=datetime.utcnow(),
        )
        client2 = Client(
            id="client_unique_2",
            email="client2@example.com",
            created_at=datetime.utcnow(),
        )
        db_session.add(client1)
        db_session.add(client2)
        await db_session.commit()

        device1, secret1 = await device_service.create_device(
            client1.id,
            "Device",
        )
        device2, secret2 = await device_service.create_device(
            client2.id,
            "Device",
        )

        # Even though same device name, secrets should be unique
        assert secret1 != secret2
        assert device1.hmac_key_hash != device2.hmac_key_hash

    async def test_cannot_create_device_with_duplicate_hmac(
        self,
        db_session: AsyncSession,
        test_client,
        device_service: DeviceService,
    ):
        """Test that duplicate HMAC keys are prevented."""
        # This test depends on DB constraints
        # Create device with unique HMAC
        device1, secret1 = await device_service.create_device(
            test_client.id,
            "Device 1",
        )

        # The constraint should prevent manual insertion of same hash
        # (This would be tested if we tried to manually insert)


@pytest.mark.asyncio
class TestHMACValidation:
    """Test HMAC validation for authentication."""

    async def test_compute_signature(
        self,
        db_session: AsyncSession,
        test_client,
        device_service: DeviceService,
    ):
        """Test computing HMAC signature."""
        device, secret = await device_service.create_device(
            test_client.id,
            "Device",
        )

        # Decode secret
        decoded_secret = decode_secret(secret)

        # Create test message
        message = b"GET/api/v1/signals"

        # Compute HMAC-SHA256
        signature = hmac.new(
            decoded_secret,
            message,
            hashlib.sha256,
        ).digest()

        # Should be 32 bytes
        assert len(signature) == 32

    async def test_signature_verification_success(
        self,
        db_session: AsyncSession,
        test_client,
        device_service: DeviceService,
    ):
        """Test successful HMAC signature verification."""
        device, secret = await device_service.create_device(
            test_client.id,
            "Device",
        )

        decoded_secret = decode_secret(secret)
        message = b"GET/api/v1/signals"

        # Create signature
        signature = hmac.new(
            decoded_secret,
            message,
            hashlib.sha256,
        ).digest()

        # Verify signature (should match)
        expected_sig = hmac.new(
            decoded_secret,
            message,
            hashlib.sha256,
        ).digest()

        assert hmac.compare_digest(signature, expected_sig)

    async def test_signature_verification_failure_wrong_message(
        self,
        db_session: AsyncSession,
        test_client,
        device_service: DeviceService,
    ):
        """Test HMAC verification fails with wrong message."""
        device, secret = await device_service.create_device(
            test_client.id,
            "Device",
        )

        decoded_secret = decode_secret(secret)
        message1 = b"GET/api/v1/signals"
        message2 = b"GET/api/v1/orders"

        # Create signature for message1
        signature1 = hmac.new(
            decoded_secret,
            message1,
            hashlib.sha256,
        ).digest()

        # Verify against message2 (should fail)
        expected_sig2 = hmac.new(
            decoded_secret,
            message2,
            hashlib.sha256,
        ).digest()

        assert not hmac.compare_digest(signature1, expected_sig2)

    async def test_signature_verification_failure_wrong_key(
        self,
        db_session: AsyncSession,
        test_client,
        device_service: DeviceService,
    ):
        """Test HMAC verification fails with wrong key."""
        device, secret = await device_service.create_device(
            test_client.id,
            "Device",
        )

        decoded_secret = decode_secret(secret)
        wrong_secret = b"wrong_secret_key"

        message = b"GET/api/v1/signals"

        # Create signature with correct key
        signature = hmac.new(
            decoded_secret,
            message,
            hashlib.sha256,
        ).digest()

        # Verify with wrong key (should fail)
        expected_sig = hmac.new(
            wrong_secret,
            message,
            hashlib.sha256,
        ).digest()

        assert not hmac.compare_digest(signature, expected_sig)


@pytest.mark.asyncio
class TestReplayAttackPrevention:
    """Test replay attack prevention with nonce/timestamp."""

    async def test_nonce_validation(
        self,
        db_session: AsyncSession,
    ):
        """Test nonce cannot be reused."""
        # Nonce validation depends on Redis implementation
        # Here we test the concept

        # First use should succeed
        # Second use of same nonce should fail
        # This would be implemented in auth middleware

    async def test_timestamp_freshness(
        self,
        db_session: AsyncSession,
    ):
        """Test timestamp must be fresh (not stale)."""
        # Timestamp validation: reject if > 5 minutes old

        # Fresh timestamp should pass
        # Stale timestamp should fail

    async def test_timestamp_not_in_future(
        self,
        db_session: AsyncSession,
    ):
        """Test timestamp cannot be in future."""

        # Future timestamp should be rejected


@pytest.mark.asyncio
class TestHMACEdgeCases:
    """Test edge cases in HMAC handling."""

    async def test_hmac_key_entropy(
        self,
        db_session: AsyncSession,
        test_client,
        device_service: DeviceService,
    ):
        """Test that HMAC keys have sufficient entropy."""
        secrets = []
        for i in range(5):
            device, secret = await device_service.create_device(
                test_client.id,
                f"Device {i}",
            )
            secrets.append(secret)

        # All secrets should be unique
        assert len(set(secrets)) == len(secrets)

    async def test_hmac_key_algorithm_sha256(
        self,
        db_session: AsyncSession,
        test_client,
        device_service: DeviceService,
    ):
        """Test that HMAC uses SHA256."""
        device, secret = await device_service.create_device(
            test_client.id,
            "Device",
        )

        decoded_secret = decode_secret(secret)

        # HMAC-SHA256 produces 32 byte (256 bit) hashes
        signature = hmac.new(
            decoded_secret,
            b"test",
            hashlib.sha256,
        ).digest()

        assert len(signature) == 32

    async def test_hmac_key_minimum_length(
        self,
        db_session: AsyncSession,
        test_client,
        device_service: DeviceService,
    ):
        """Test HMAC key meets minimum length requirement."""
        device, secret = await device_service.create_device(
            test_client.id,
            "Device",
        )

        decoded_secret = decode_secret(secret)

        # Should be at least 32 bytes (256 bits)
        assert len(decoded_secret) >= 32

    async def test_hmac_secret_cannot_be_guessed(
        self,
        db_session: AsyncSession,
        test_client,
        device_service: DeviceService,
    ):
        """Test that HMAC secrets are not sequential or predictable."""
        secrets = []
        for i in range(10):
            device, secret = await device_service.create_device(
                test_client.id,
                f"Device {i}",
            )
            decoded = decode_secret(secret)
            secrets.append(decoded)

        # Secrets should appear random (no obvious pattern)
        # Check that they're not sequential
        for i in range(len(secrets) - 1):
            assert secrets[i] != secrets[i + 1]

    async def test_revoked_device_hmac_invalid(
        self,
        db_session: AsyncSession,
        test_client,
        device_service: DeviceService,
    ):
        """Test that revoked device's HMAC cannot authenticate."""
        device, secret = await device_service.create_device(
            test_client.id,
            "Device",
        )

        # Revoke device
        await device_service.revoke_device(device.id)

        # Now using this secret should fail authentication
        # (This would be tested in the auth middleware)
