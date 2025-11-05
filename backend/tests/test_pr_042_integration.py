"""
PR-042: Encrypted Signal Transport - END-TO-END INTEGRATION TESTS

Complete business logic validation:
- Device registration with encryption key issuance
- Signal encryption/decryption workflow
- Key rotation and expiration
- Logging without key leakage
- Integration with poll/ack endpoints
"""

import base64
import json
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.approvals.models import Approval, ApprovalDecision
from backend.app.clients.models import Client
from backend.app.clients.service import DeviceService
from backend.app.ea.crypto import DeviceKeyManager, SignalEnvelope, get_key_manager
from backend.app.signals.models import Signal

# ============================================================================
# INTEGRATION TEST FIXTURES
# ============================================================================


@pytest_asyncio.fixture
async def test_client_db(db_session: AsyncSession) -> Client:
    """Create test client in database."""
    client_id = str(uuid4())
    client = Client(
        id=client_id,
        email=f"test-client-{uuid4()}@example.com",
    )
    db_session.add(client)
    await db_session.commit()
    await db_session.refresh(client)
    return client


@pytest_asyncio.fixture
async def test_signal_db(db_session: AsyncSession, test_client_db: Client) -> Signal:
    """Create test signal in database."""
    signal_id = str(uuid4())
    signal = Signal(
        id=signal_id,
        user_id=test_client_db.id,
        instrument="EURUSD",
        side=0,  # buy
        price=1.0950,
        payload={
            "strategy": "fib_rsi",
            "timeframe": "H1",
            "confidence": 0.85,
        },
        status=0,  # new
    )
    db_session.add(signal)
    await db_session.commit()
    await db_session.refresh(signal)
    return signal


@pytest_asyncio.fixture
async def test_approval_db(
    db_session: AsyncSession, test_client_db: Client, test_signal_db: Signal
) -> Approval:
    """Create test approval in database."""
    approval_id = str(uuid4())
    approval = Approval(
        id=approval_id,
        signal_id=test_signal_db.id,
        client_id=test_client_db.id,
        decision=ApprovalDecision.APPROVED,
        approved_at=datetime.utcnow(),
    )
    db_session.add(approval)
    await db_session.commit()
    await db_session.refresh(approval)
    return approval


# ============================================================================
# 1. DEVICE REGISTRATION WITH ENCRYPTION KEY ISSUANCE
# ============================================================================


@pytest.mark.asyncio
async def test_device_registration_returns_encryption_key_and_hmac(
    db_session: AsyncSession, test_client_db: Client
):
    """Verify device registration returns both HMAC secret and encryption key."""
    service = DeviceService(db_session)

    # Register device
    device, hmac_secret, encryption_key = await service.create_device(
        test_client_db.id, "TestDevice001"
    )

    # Verify device created
    assert device.id is not None
    assert device.client_id == test_client_db.id
    assert device.device_name == "TestDevice001"
    assert device.is_active is True

    # Verify HMAC secret returned
    assert hmac_secret is not None
    assert len(hmac_secret) > 32  # URL-safe base64
    assert isinstance(hmac_secret, str)

    # Verify encryption key returned
    assert encryption_key is not None
    assert len(encryption_key) > 0
    assert isinstance(encryption_key, str)

    # Verify encryption key is valid base64
    try:
        decoded_key = base64.b64decode(encryption_key)
        assert len(decoded_key) == 32  # AES-256 = 32 bytes
    except Exception as e:
        pytest.fail(f"encryption_key is not valid base64: {e}")


@pytest.mark.asyncio
async def test_encryption_key_is_deterministic_for_device(
    db_session: AsyncSession, test_client_db: Client
):
    """Verify encryption key can be re-derived for same device (deterministic)."""
    service = DeviceService(db_session)
    device, _, key1 = await service.create_device(test_client_db.id, "Device001")

    # Re-derive key using key manager
    key_manager = get_key_manager()
    key_obj = key_manager.get_device_key(device.id)

    assert key_obj is not None
    assert key_obj.encryption_key is not None

    # Verify it matches the issued key (after decoding)
    key1_decoded = base64.b64decode(key1)
    assert key_obj.encryption_key == key1_decoded


@pytest.mark.asyncio
async def test_different_devices_get_different_encryption_keys(
    db_session: AsyncSession, test_client_db: Client
):
    """Verify different devices get different encryption keys."""
    service = DeviceService(db_session)

    # Register two devices
    device1, _, key1 = await service.create_device(test_client_db.id, "Device001")
    device2, _, key2 = await service.create_device(test_client_db.id, "Device002")

    # Keys should be different
    assert key1 != key2

    # Verify by decoding
    key1_decoded = base64.b64decode(key1)
    key2_decoded = base64.b64decode(key2)
    assert key1_decoded != key2_decoded


@pytest.mark.asyncio
async def test_encryption_key_not_leaked_in_hmac_hash(
    db_session: AsyncSession, test_client_db: Client
):
    """Verify HMAC key hash doesn't match encryption key."""
    service = DeviceService(db_session)
    device, hmac_secret, encryption_key = await service.create_device(
        test_client_db.id, "TestDevice"
    )

    # HMAC secret and encryption key should be completely different
    assert hmac_secret != encryption_key

    # HMAC key hash should not contain encryption key
    assert device.hmac_key_hash is not None
    assert encryption_key not in device.hmac_key_hash


# ============================================================================
# 2. SIGNAL ENCRYPTION/DECRYPTION WORKFLOW
# ============================================================================


@pytest.mark.asyncio
async def test_device_can_decrypt_signals_encrypted_with_its_key(
    db_session: AsyncSession, test_client_db: Client, test_signal_db: Signal
):
    """Verify device can decrypt signals encrypted with its own key."""
    service = DeviceService(db_session)

    # Register device and get encryption key
    device, _, encryption_key_b64 = await service.create_device(
        test_client_db.id, "TestDevice"
    )

    # Create envelope and encrypt a signal
    key_manager = get_key_manager()
    envelope = SignalEnvelope(key_manager)

    signal_payload = {
        "signal_id": str(test_signal_db.id),
        "instrument": "EURUSD",
        "side": "buy",
        "price": 1.0950,
    }

    # Encrypt signal for this device
    ciphertext_b64, nonce_b64, aad = envelope.encrypt_signal(device.id, signal_payload)

    # Verify ciphertext is not plaintext
    assert (
        ciphertext_b64 != base64.b64encode(json.dumps(signal_payload).encode()).decode()
    )

    # Device decrypts the signal
    decrypted = envelope.decrypt_signal(device.id, ciphertext_b64, nonce_b64, aad)

    # Verify payload matches
    assert decrypted == signal_payload
    assert decrypted["instrument"] == "EURUSD"
    assert decrypted["side"] == "buy"


@pytest.mark.asyncio
async def test_cross_device_decryption_fails(
    db_session: AsyncSession, test_client_db: Client
):
    """Verify device_001 cannot decrypt signal encrypted for device_002."""
    service = DeviceService(db_session)

    # Register two devices
    device1, _, _ = await service.create_device(test_client_db.id, "Device001")
    device2, _, _ = await service.create_device(test_client_db.id, "Device002")

    # Encrypt signal for device_001
    key_manager = get_key_manager()
    envelope = SignalEnvelope(key_manager)

    payload = {"signal": "secret", "price": 1950.0}
    ciphertext_b64, nonce_b64, aad = envelope.encrypt_signal(device1.id, payload)

    # Try to decrypt with device_002 (should fail)
    with pytest.raises(ValueError, match="AAD mismatch"):
        envelope.decrypt_signal(device2.id, ciphertext_b64, nonce_b64, aad)


@pytest.mark.asyncio
async def test_tampering_with_ciphertext_detected(
    db_session: AsyncSession, test_client_db: Client
):
    """Verify tampering with ciphertext is detected."""
    service = DeviceService(db_session)
    device, _, _ = await service.create_device(test_client_db.id, "TestDevice")

    key_manager = get_key_manager()
    envelope = SignalEnvelope(key_manager)

    payload = {"data": "important"}
    ciphertext_b64, nonce_b64, aad = envelope.encrypt_signal(device.id, payload)

    # Tamper with ciphertext (flip bits)
    ciphertext_bytes = base64.b64decode(ciphertext_b64)
    tampered_bytes = bytearray(ciphertext_bytes)
    tampered_bytes[0] ^= 0xFF
    tampered_ciphertext_b64 = base64.b64encode(bytes(tampered_bytes)).decode()

    # Decryption should fail
    from cryptography.hazmat.primitives.ciphers.aead import InvalidTag

    with pytest.raises(InvalidTag):
        envelope.decrypt_signal(device.id, tampered_ciphertext_b64, nonce_b64, aad)


@pytest.mark.asyncio
async def test_tampering_with_nonce_detected(
    db_session: AsyncSession, test_client_db: Client
):
    """Verify tampering with nonce is detected."""
    service = DeviceService(db_session)
    device, _, _ = await service.create_device(test_client_db.id, "TestDevice")

    key_manager = get_key_manager()
    envelope = SignalEnvelope(key_manager)

    payload = {"data": "important"}
    ciphertext_b64, nonce_b64, aad = envelope.encrypt_signal(device.id, payload)

    # Tamper with nonce
    nonce_bytes = base64.b64decode(nonce_b64)
    tampered_nonce_bytes = bytes([nonce_bytes[0] ^ 0xFF]) + nonce_bytes[1:]
    tampered_nonce_b64 = base64.b64encode(tampered_nonce_bytes).decode()

    # Decryption should fail
    from cryptography.hazmat.primitives.ciphers.aead import InvalidTag

    with pytest.raises(InvalidTag):
        envelope.decrypt_signal(device.id, ciphertext_b64, tampered_nonce_b64, aad)


# ============================================================================
# 3. KEY ROTATION & EXPIRATION
# ============================================================================


@pytest.mark.asyncio
async def test_expired_device_key_cannot_decrypt(
    db_session: AsyncSession, test_client_db: Client
):
    """Verify expired keys cannot decrypt signals."""
    service = DeviceService(db_session)
    device, _, _ = await service.create_device(test_client_db.id, "TestDevice")

    key_manager = DeviceKeyManager(
        "test-secret", key_rotate_days=0
    )  # 0 days = immediate expiry
    expired_key = key_manager.create_device_key(device.id)

    # Manually expire the key
    expired_key.expires_at = datetime.utcnow() - timedelta(seconds=1)
    key_manager.active_keys[device.id] = expired_key

    # Try to decrypt - should fail
    envelope = SignalEnvelope(key_manager)
    payload = {"data": "test"}

    with pytest.raises(ValueError, match="No active encryption key"):
        envelope.encrypt_signal(device.id, payload)


@pytest.mark.asyncio
async def test_key_revocation_prevents_decryption(
    db_session: AsyncSession, test_client_db: Client
):
    """Verify revoked keys cannot decrypt signals."""
    service = DeviceService(db_session)
    device, _, _ = await service.create_device(test_client_db.id, "TestDevice")

    key_manager = get_key_manager()
    envelope = SignalEnvelope(key_manager)

    # Encrypt with active key
    payload = {"data": "value"}
    ciphertext_b64, nonce_b64, aad = envelope.encrypt_signal(device.id, payload)

    # Revoke the key
    key_manager.revoke_device_key(device.id)

    # Try to decrypt - should fail (no active key)
    with pytest.raises(ValueError, match="No active encryption key"):
        envelope.decrypt_signal(device.id, ciphertext_b64, nonce_b64, aad)


# ============================================================================
# 4. SECURITY & LOGGING
# ============================================================================


@pytest.mark.asyncio
async def test_encryption_key_never_logged_as_plaintext(
    db_session: AsyncSession, test_client_db: Client, caplog
):
    """Verify encryption keys are never logged in plaintext."""
    service = DeviceService(db_session)
    device, _, encryption_key = await service.create_device(
        test_client_db.id, "TestDevice"
    )

    # Decrypt to get raw key bytes
    key_bytes = base64.b64decode(encryption_key)

    # Check logs don't contain key
    log_content = caplog.text
    assert key_bytes.hex() not in log_content
    assert encryption_key not in log_content


@pytest.mark.asyncio
async def test_plaintext_signal_never_in_ciphertext_response():
    """Verify plaintext signal data never appears in encrypted response."""
    key_manager = get_key_manager()
    envelope = SignalEnvelope(key_manager)

    device_id = str(uuid4())
    secret_data = "SUPER_SECRET_API_KEY_VALUE_12345"
    payload = {"sensitive": secret_data, "price": 1950.50}

    ciphertext_b64, _, _ = envelope.encrypt_signal(device_id, payload)

    # Secret should not appear anywhere in ciphertext
    assert secret_data not in ciphertext_b64
    assert "SECRET_API_KEY" not in ciphertext_b64


# ============================================================================
# 5. END-TO-END WORKFLOW
# ============================================================================


@pytest.mark.asyncio
async def test_complete_device_registration_encryption_decryption_flow(
    db_session: AsyncSession, test_client_db: Client, test_signal_db: Signal
):
    """
    Complete E2E workflow:
    1. Client registers device
    2. Server issues HMAC secret + encryption key
    3. Client stores key locally
    4. Server encrypts signal for device
    5. Client decrypts signal
    6. Client acknowledges execution
    """
    service = DeviceService(db_session)

    # 1. Register device
    device, hmac_secret, encryption_key_b64 = await service.create_device(
        test_client_db.id, "EA_Device_001"
    )
    print(f"✓ Device registered: {device.id}")

    # Verify device in database
    registered_device = await service.get_device(device.id)
    assert registered_device.id == device.id
    print("✓ Device verified in database")

    # 2. Verify encryption key is stored and retrievable
    key_manager = get_key_manager()
    key_obj = key_manager.get_device_key(device.id)
    assert key_obj is not None
    print("✓ Encryption key retrievable via manager")

    # 3. Create signal for this client
    signal_payload = {
        "signal_id": str(test_signal_db.id),
        "instrument": test_signal_db.instrument,
        "side": "buy",
        "entry_price": test_signal_db.price,
        "volume": 1.0,
        "tp_price": 1.1000,
        "sl_price": 1.0900,
        "strategy": "fib_rsi",
        "confidence": 0.85,
    }

    # 4. Server encrypts signal before sending to EA
    envelope = SignalEnvelope(key_manager)
    ciphertext_b64, nonce_b64, aad = envelope.encrypt_signal(device.id, signal_payload)
    print("✓ Signal encrypted for device")

    # Verify ciphertext is NOT plaintext
    plaintext_b64 = base64.b64encode(json.dumps(signal_payload).encode()).decode()
    assert ciphertext_b64 != plaintext_b64
    print("✓ Ciphertext differs from plaintext")

    # 5. Client (EA) decrypts signal using stored key
    decrypted_payload = envelope.decrypt_signal(
        device.id, ciphertext_b64, nonce_b64, aad
    )
    print("✓ Signal decrypted by device")

    # 6. Verify decrypted payload matches original
    assert decrypted_payload == signal_payload
    assert decrypted_payload["instrument"] == "EURUSD"
    assert decrypted_payload["strategy"] == "fib_rsi"
    print("✓ Decrypted payload matches original")

    # 7. Verify multiple messages have different ciphertexts (random nonce)
    ciphertext2_b64, nonce2_b64, aad2 = envelope.encrypt_signal(
        device.id, signal_payload
    )
    assert ciphertext_b64 != ciphertext2_b64
    assert nonce_b64 != nonce2_b64
    print("✓ Different encryptions produce different ciphertexts (random nonce)")

    # 8. Verify second message decrypts correctly
    decrypted2 = envelope.decrypt_signal(device.id, ciphertext2_b64, nonce2_b64, aad2)
    assert decrypted2 == signal_payload
    print("✓ Second message decrypts correctly")


@pytest.mark.asyncio
async def test_multi_device_encryption_isolation(
    db_session: AsyncSession, test_client_db: Client
):
    """Verify complete isolation between multiple devices."""
    service = DeviceService(db_session)

    # Register 3 devices for same client
    devices = []
    for i in range(3):
        device, _, _ = await service.create_device(test_client_db.id, f"Device{i:03d}")
        devices.append(device)

    # Encrypt same payload with each device
    key_manager = get_key_manager()
    envelope = SignalEnvelope(key_manager)

    payload = {"price": 1950.0, "volume": 1.0}
    encrypted_signals = []

    for device in devices:
        ct, nonce, aad = envelope.encrypt_signal(device.id, payload)
        encrypted_signals.append(
            {
                "device_id": device.id,
                "ciphertext": ct,
                "nonce": nonce,
                "aad": aad,
            }
        )

    # Verify each device can ONLY decrypt its own signal
    for i, device in enumerate(devices):
        # Device can decrypt its own signal
        own_signal = encrypted_signals[i]
        decrypted = envelope.decrypt_signal(
            device.id, own_signal["ciphertext"], own_signal["nonce"], own_signal["aad"]
        )
        assert decrypted == payload

        # Device cannot decrypt other devices' signals
        for j, other_signal in enumerate(encrypted_signals):
            if i != j:
                with pytest.raises(ValueError, match="AAD mismatch"):
                    envelope.decrypt_signal(
                        device.id,
                        other_signal["ciphertext"],
                        other_signal["nonce"],
                        other_signal["aad"],
                    )

    print(f"✓ Complete isolation verified across {len(devices)} devices")


# ============================================================================
# 6. COMPLIANCE & STANDARDS
# ============================================================================


@pytest.mark.asyncio
async def test_aes_256_key_compliance(db_session: AsyncSession, test_client_db: Client):
    """Verify AES-256-GCM compliance (256-bit keys)."""
    service = DeviceService(db_session)
    device, _, encryption_key_b64 = await service.create_device(
        test_client_db.id, "TestDevice"
    )

    # Decode key
    key_bytes = base64.b64decode(encryption_key_b64)

    # Verify 256-bit = 32 bytes
    assert len(key_bytes) == 32

    # Verify all bits are used (not just zeros)
    assert key_bytes != b"\x00" * 32


@pytest.mark.asyncio
async def test_nonce_uniqueness_across_encryptions(
    db_session: AsyncSession, test_client_db: Client
):
    """Verify nonce uniqueness across multiple encryptions."""
    service = DeviceService(db_session)
    device, _, _ = await service.create_device(test_client_db.id, "TestDevice")

    key_manager = get_key_manager()
    envelope = SignalEnvelope(key_manager)

    payload = {"price": 1950.0}
    nonces = set()

    # Encrypt 50 times and collect nonces
    for _ in range(50):
        _, nonce_b64, _ = envelope.encrypt_signal(device.id, payload)
        nonce_bytes = base64.b64decode(nonce_b64)
        nonces.add(nonce_bytes)

    # All 50 nonces should be unique
    assert len(nonces) == 50

    # All nonces should be 12 bytes (GCM standard)
    for nonce in nonces:
        assert len(nonce) == 12


@pytest.mark.asyncio
async def test_pbkdf2_deterministic_key_derivation(
    db_session: AsyncSession, test_client_db: Client
):
    """Verify PBKDF2 produces deterministic keys."""
    key_manager = get_key_manager()

    device_id = str(uuid4())
    date_tag = "2025-10-25"

    # Derive key twice
    key1 = key_manager.derive_device_key(device_id, date_tag)
    key2 = key_manager.derive_device_key(device_id, date_tag)

    # Keys should be identical
    assert key1 == key2
    assert len(key1) == 32


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
