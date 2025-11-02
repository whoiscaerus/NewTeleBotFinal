"""
PR-042: Encrypted Signal Transport - Comprehensive Test Suite

Tests for signal encryption/decryption with AES-256-GCM AEAD:
- Roundtrip encrypt/decrypt
- Tampering detection (AAD mismatch)
- Key rotation and expiration
- Nonce uniqueness
- Edge cases (large payloads, empty payloads)
- Concurrent operations
- Integration scenarios
"""

import base64
import json
from datetime import datetime, timedelta

import pytest

from backend.app.ea.crypto import (
    DeviceKeyManager,
    EncryptionSettings,
    SignalEnvelope,
    decrypt_payload,
    encrypt_payload,
    get_key_manager,
)

# ============================================================================
# TEST FIXTURES
# ============================================================================


@pytest.fixture
def kdf_secret():
    """KDF secret for testing."""
    return "test-kdf-secret-at-least-32-chars-long-for-proper-pbkdf2"


@pytest.fixture
def key_manager(kdf_secret):
    """Initialize DeviceKeyManager for testing."""
    return DeviceKeyManager(kdf_secret, key_rotate_days=90)


@pytest.fixture
def envelope(key_manager):
    """Initialize SignalEnvelope for testing."""
    return SignalEnvelope(key_manager)


@pytest.fixture
def test_device_id():
    """Test device ID."""
    return "device_test_12345"


@pytest.fixture
def test_payload():
    """Sample signal payload."""
    return {
        "instrument": "GOLD",
        "side": "buy",
        "price": 1950.50,
        "volume": 1.0,
        "entry_time": "2025-10-31T12:00:00Z",
    }


# ============================================================================
# 1. ROUNDTRIP ENCRYPTION/DECRYPTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_encrypt_decrypt_roundtrip(envelope, test_device_id, test_payload):
    """Test basic encrypt → decrypt → verify payload integrity."""
    # Encrypt
    ciphertext_b64, nonce_b64, aad = envelope.encrypt_signal(
        test_device_id, test_payload
    )

    # Verify not plaintext (basic sanity)
    assert (
        ciphertext_b64 != base64.b64encode(json.dumps(test_payload).encode()).decode()
    )
    assert nonce_b64 is not None
    assert aad == test_device_id

    # Decrypt
    decrypted = envelope.decrypt_signal(test_device_id, ciphertext_b64, nonce_b64, aad)

    # Verify exact match
    assert decrypted == test_payload
    assert decrypted["instrument"] == "GOLD"
    assert decrypted["side"] == "buy"
    assert decrypted["price"] == 1950.50


@pytest.mark.asyncio
async def test_encrypt_decrypt_empty_payload(envelope, test_device_id):
    """Test encryption of empty payload."""
    payload = {}

    ciphertext_b64, nonce_b64, aad = envelope.encrypt_signal(test_device_id, payload)
    decrypted = envelope.decrypt_signal(test_device_id, ciphertext_b64, nonce_b64, aad)

    assert decrypted == payload


@pytest.mark.asyncio
async def test_encrypt_decrypt_large_payload(envelope, test_device_id):
    """Test encryption of large payload (>1MB)."""
    # Create large payload
    payload = {
        "data": "x" * (2 * 1024 * 1024),  # 2MB string
        "instrument": "GOLD",
    }

    ciphertext_b64, nonce_b64, aad = envelope.encrypt_signal(test_device_id, payload)
    decrypted = envelope.decrypt_signal(test_device_id, ciphertext_b64, nonce_b64, aad)

    assert decrypted == payload
    assert len(decrypted["data"]) == 2 * 1024 * 1024


@pytest.mark.asyncio
async def test_encrypt_decrypt_nested_payload(envelope, test_device_id):
    """Test encryption of deeply nested payload."""
    payload = {
        "signal": {
            "entry": {
                "price": 1950.50,
                "time": "2025-10-31T12:00:00Z",
            },
            "exit": {
                "tp": 1960.00,
                "sl": 1940.00,
            },
        },
        "metadata": {
            "strategy": "fib_rsi",
            "timeframe": "H1",
        },
    }

    ciphertext_b64, nonce_b64, aad = envelope.encrypt_signal(test_device_id, payload)
    decrypted = envelope.decrypt_signal(test_device_id, ciphertext_b64, nonce_b64, aad)

    assert decrypted == payload
    assert decrypted["signal"]["entry"]["price"] == 1950.50


# ============================================================================
# 2. TAMPERING DETECTION TESTS (AAD MISMATCH)
# ============================================================================


@pytest.mark.asyncio
async def test_tampering_aad_mismatch(envelope, test_device_id, test_payload):
    """Test that AAD mismatch (tampering) is detected."""
    # Encrypt
    ciphertext_b64, nonce_b64, aad = envelope.encrypt_signal(
        test_device_id, test_payload
    )

    # Try to decrypt with wrong AAD (device ID)
    wrong_aad = "wrong_device_id"

    with pytest.raises(ValueError, match="AAD mismatch"):
        envelope.decrypt_signal(test_device_id, ciphertext_b64, nonce_b64, wrong_aad)


@pytest.mark.asyncio
async def test_tampering_modified_ciphertext(envelope, test_device_id, test_payload):
    """Test that modified ciphertext is rejected."""
    # Encrypt
    ciphertext_b64, nonce_b64, aad = envelope.encrypt_signal(
        test_device_id, test_payload
    )

    # Tamper with ciphertext (flip a bit)
    ciphertext_bytes = base64.b64decode(ciphertext_b64)
    tampered_bytes = bytearray(ciphertext_bytes)
    tampered_bytes[0] ^= 0xFF  # Flip bits
    tampered_ciphertext_b64 = base64.b64encode(bytes(tampered_bytes)).decode()

    # Decryption should fail (authentication tag mismatch)
    with pytest.raises(Exception):  # cryptography raises InvalidTag
        envelope.decrypt_signal(test_device_id, tampered_ciphertext_b64, nonce_b64, aad)


@pytest.mark.asyncio
async def test_tampering_modified_nonce(envelope, test_device_id, test_payload):
    """Test that modified nonce invalidates the ciphertext."""
    # Encrypt
    ciphertext_b64, nonce_b64, aad = envelope.encrypt_signal(
        test_device_id, test_payload
    )

    # Tamper with nonce
    nonce_bytes = base64.b64decode(nonce_b64)
    tampered_nonce = base64.b64encode(
        bytes([nonce_bytes[0] ^ 0xFF]) + nonce_bytes[1:]
    ).decode()

    # Decryption should fail
    with pytest.raises(Exception):  # cryptography raises InvalidTag
        envelope.decrypt_signal(test_device_id, ciphertext_b64, tampered_nonce, aad)


# ============================================================================
# 3. KEY ROTATION & EXPIRATION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_key_expiration(key_manager, test_device_id):
    """Test that expired keys return None."""
    # Create key with 0-day TTL (immediately expired)
    expired_manager = DeviceKeyManager("test-secret", key_rotate_days=0)

    # Create key
    key = expired_manager.create_device_key(test_device_id)
    assert key.is_active is True

    # Manually expire the key (move expiration to past)
    key.expires_at = datetime.utcnow() - timedelta(seconds=1)
    expired_manager.active_keys[test_device_id] = key

    # Try to get key
    retrieved = expired_manager.get_device_key(test_device_id)

    # Should return None for expired key
    assert retrieved is None


@pytest.mark.asyncio
async def test_key_derivation_deterministic(key_manager):
    """Test that key derivation is deterministic for same inputs."""
    device_id = "test_device"
    date_tag = "2025-10-31"

    # Derive same key twice
    key1 = key_manager.derive_device_key(device_id, date_tag)
    key2 = key_manager.derive_device_key(device_id, date_tag)

    # Should be identical
    assert key1 == key2


@pytest.mark.asyncio
async def test_key_derivation_different_dates(key_manager):
    """Test that different dates produce different keys."""
    device_id = "test_device"

    # Derive keys for different dates
    key_day1 = key_manager.derive_device_key(device_id, "2025-10-31")
    key_day2 = key_manager.derive_device_key(device_id, "2025-11-01")

    # Should be different
    assert key_day1 != key_day2


@pytest.mark.asyncio
async def test_key_revocation(key_manager, test_device_id):
    """Test device key revocation."""
    # Create key
    key = key_manager.create_device_key(test_device_id)
    assert key.is_active is True

    # Revoke key
    key_manager.revoke_device_key(test_device_id)

    # Try to get revoked key
    retrieved = key_manager.get_device_key(test_device_id)

    # Should return None
    assert retrieved is None


# ============================================================================
# 4. NONCE UNIQUENESS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_nonce_uniqueness_multiple_encryptions(
    envelope, test_device_id, test_payload
):
    """Test that multiple encryptions produce different nonces."""
    nonces = []

    for _ in range(10):
        _, nonce_b64, _ = envelope.encrypt_signal(test_device_id, test_payload)
        nonces.append(nonce_b64)

    # All nonces should be unique
    assert len(nonces) == len(set(nonces))


@pytest.mark.asyncio
async def test_ciphertext_different_per_nonce(envelope, test_device_id, test_payload):
    """Test that same payload encrypts to different ciphertexts (due to random nonce)."""
    ciphertexts = []

    for _ in range(5):
        ciphertext_b64, _, _ = envelope.encrypt_signal(test_device_id, test_payload)
        ciphertexts.append(ciphertext_b64)

    # All ciphertexts should be different (GCM uses random nonce)
    assert len(ciphertexts) == len(set(ciphertexts))


# ============================================================================
# 5. METADATA EXTRACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_metadata_extraction(envelope, test_device_id, test_payload):
    """Test envelope metadata extraction."""
    ciphertext_b64, nonce_b64, aad = envelope.encrypt_signal(
        test_device_id, test_payload
    )

    metadata = envelope.get_envelope_metadata(ciphertext_b64)

    assert "ciphertext_length" in metadata
    assert "created_at" in metadata
    assert metadata["ciphertext_length"] > 0
    assert isinstance(metadata["created_at"], str)


# ============================================================================
# 6. EDGE CASES & ERROR HANDLING
# ============================================================================


@pytest.mark.asyncio
async def test_decrypt_no_active_key(envelope, test_device_id, test_payload):
    """Test decryption fails when no active key exists."""
    # Encrypt with valid key
    ciphertext_b64, nonce_b64, aad = envelope.encrypt_signal(
        test_device_id, test_payload
    )

    # Revoke the key
    envelope.key_manager.revoke_device_key(test_device_id)

    # Try to decrypt
    with pytest.raises(ValueError, match="No active encryption key"):
        envelope.decrypt_signal(test_device_id, ciphertext_b64, nonce_b64, aad)


@pytest.mark.asyncio
async def test_encrypt_invalid_device_id_after_revocation(key_manager, envelope):
    """Test encryption fails for revoked device."""
    device_id = "revoked_device"

    # Create and revoke key
    key_manager.create_device_key(device_id)
    key_manager.revoke_device_key(device_id)

    # Try to encrypt
    with pytest.raises(ValueError, match="No active encryption key"):
        envelope.encrypt_signal(device_id, {"data": "test"})


@pytest.mark.asyncio
async def test_special_characters_in_payload(envelope, test_device_id):
    """Test encryption of payload with special characters."""
    payload = {
        "text": "Special chars: äöü€™©®¥ 中文 العربية",
        "emoji": "🔐🔒🔑",
        "escapes": "newline\ncarriage\rreturn\ttab",
    }

    ciphertext_b64, nonce_b64, aad = envelope.encrypt_signal(test_device_id, payload)
    decrypted = envelope.decrypt_signal(test_device_id, ciphertext_b64, nonce_b64, aad)

    assert decrypted == payload
    assert decrypted["text"] == payload["text"]
    assert decrypted["emoji"] == "🔐🔒🔑"


@pytest.mark.asyncio
async def test_numeric_edge_cases(envelope, test_device_id):
    """Test encryption of numeric edge cases."""
    payload = {
        "large_int": 999999999999999999,
        "negative": -1000.50,
        "float": 3.14159265359,
        "zero": 0,
        "scientific": 1.23e-10,
    }

    ciphertext_b64, nonce_b64, aad = envelope.encrypt_signal(test_device_id, payload)
    decrypted = envelope.decrypt_signal(test_device_id, ciphertext_b64, nonce_b64, aad)

    assert decrypted == payload


# ============================================================================
# 7. CONVENIENCE FUNCTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_encrypt_payload_function(test_device_id, test_payload):
    """Test convenience encrypt_payload function."""
    result = encrypt_payload(test_device_id, test_payload)

    assert "ciphertext" in result
    assert "nonce" in result
    assert "aad" in result
    assert "metadata" in result
    assert result["aad"] == test_device_id


@pytest.mark.asyncio
async def test_decrypt_payload_function(test_device_id, test_payload):
    """Test convenience decrypt_payload function."""
    # Encrypt
    encrypted = encrypt_payload(test_device_id, test_payload)

    # Decrypt
    decrypted = decrypt_payload(
        test_device_id,
        encrypted["ciphertext"],
        encrypted["nonce"],
        encrypted["aad"],
    )

    assert decrypted == test_payload


@pytest.mark.asyncio
async def test_encrypt_payload_error_handling(test_device_id):
    """Test encrypt_payload error handling."""
    # Revoke key first
    manager = get_key_manager()
    manager.revoke_device_key(test_device_id)

    result = encrypt_payload(test_device_id, {"data": "test"})

    assert "error" in result


# ============================================================================
# 8. INTEGRATION SCENARIOS
# ============================================================================


@pytest.mark.asyncio
async def test_multi_device_isolation(envelope, test_payload):
    """Test that different devices have isolated keys."""
    device1 = "device_1"
    device2 = "device_2"

    # Encrypt same payload with different devices
    ct1, nonce1, aad1 = envelope.encrypt_signal(device1, test_payload)
    ct2, nonce2, aad2 = envelope.encrypt_signal(device2, test_payload)

    # Ciphertexts should be different
    assert ct1 != ct2

    # Decryption should fail if device doesn't match
    with pytest.raises(ValueError, match="AAD mismatch"):
        envelope.decrypt_signal(device1, ct2, nonce2, aad2)

    # But should work with correct device
    decrypted2 = envelope.decrypt_signal(device2, ct2, nonce2, aad2)
    assert decrypted2 == test_payload


@pytest.mark.asyncio
async def test_key_manager_singleton_behavior():
    """Test that get_key_manager returns same instance."""
    manager1 = get_key_manager()
    manager2 = get_key_manager()

    assert manager1 is manager2


@pytest.mark.asyncio
async def test_settings_env_var_override(monkeypatch):
    """Test EncryptionSettings respects env variables."""
    monkeypatch.setenv("DEVICE_KEY_ROTATE_DAYS", "180")
    monkeypatch.setenv("ENABLE_SIGNAL_ENCRYPTION", "false")

    settings = EncryptionSettings()

    assert settings.key_rotate_days == 180
    assert settings.enable_encryption is False


@pytest.mark.asyncio
async def test_full_trade_signal_encryption_flow(envelope, test_device_id):
    """Test realistic trade signal encryption flow."""
    # Simulate trade signal from strategy
    trade_signal = {
        "id": "signal_001",
        "instrument": "EURUSD",
        "side": "buy",
        "entry_price": 1.0950,
        "stop_loss": 1.0900,
        "take_profit": 1.1050,
        "volume": 1.0,
        "timeframe": "H1",
        "strategy": "fib_rsi",
        "confidence": 0.85,
        "created_at": "2025-10-31T12:00:00Z",
    }

    # Encrypt for EA transmission
    ciphertext_b64, nonce_b64, aad = envelope.encrypt_signal(
        test_device_id, trade_signal
    )

    # Simulate transmission (no modification)

    # EA receives and decrypts
    decrypted_signal = envelope.decrypt_signal(
        test_device_id, ciphertext_b64, nonce_b64, aad
    )

    # Verify trade signal integrity
    assert decrypted_signal["id"] == "signal_001"
    assert decrypted_signal["instrument"] == "EURUSD"
    assert decrypted_signal["confidence"] == 0.85
    assert len(decrypted_signal) == len(trade_signal)


@pytest.mark.asyncio
async def test_concurrent_device_encryption(envelope, test_payload):
    """Test encryption across multiple devices concurrently."""
    import asyncio

    devices = [f"device_{i}" for i in range(5)]
    results = []

    async def encrypt_device(device_id):
        ct, nonce, aad = envelope.encrypt_signal(device_id, test_payload)
        decrypted = envelope.decrypt_signal(device_id, ct, nonce, aad)
        return decrypted

    # Simulate concurrent operations
    tasks = [encrypt_device(device) for device in devices]
    results = await asyncio.gather(*tasks)

    # All should succeed
    assert len(results) == len(devices)
    assert all(r == test_payload for r in results)


# ============================================================================
# 9. PERFORMANCE & STRESS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_many_encryptions_same_key(envelope, test_device_id, test_payload):
    """Test many encryptions with same device key."""
    for _ in range(100):
        ciphertext_b64, nonce_b64, aad = envelope.encrypt_signal(
            test_device_id, test_payload
        )
        decrypted = envelope.decrypt_signal(
            test_device_id, ciphertext_b64, nonce_b64, aad
        )

        assert decrypted == test_payload


@pytest.mark.asyncio
async def test_encryption_performance(envelope, test_device_id, test_payload):
    """Test encryption performance is acceptable."""
    import time

    start = time.time()

    for _ in range(50):
        envelope.encrypt_signal(test_device_id, test_payload)

    elapsed = time.time() - start

    # Should complete 50 encryptions in <5 seconds (very generous limit)
    assert elapsed < 5.0


# ============================================================================
# 10. COMPLIANCE & STANDARDS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_aes_key_size(key_manager, test_device_id):
    """Test that generated keys are 256-bit."""
    key_bytes = key_manager.derive_device_key(test_device_id)

    # AES-256 requires exactly 256 bits = 32 bytes
    assert len(key_bytes) == 32


@pytest.mark.asyncio
async def test_nonce_size(envelope, test_device_id, test_payload):
    """Test that nonce is 12 bytes (GCM standard)."""
    _, nonce_b64, _ = envelope.encrypt_signal(test_device_id, test_payload)

    nonce_bytes = base64.b64decode(nonce_b64)

    # GCM standard nonce is 12 bytes (96 bits)
    assert len(nonce_bytes) == 12


@pytest.mark.asyncio
async def test_base64_encoding_standard(envelope, test_device_id, test_payload):
    """Test that output uses standard base64 encoding."""
    ciphertext_b64, nonce_b64, _ = envelope.encrypt_signal(test_device_id, test_payload)

    # Should be valid base64
    try:
        base64.b64decode(ciphertext_b64)
        base64.b64decode(nonce_b64)
    except Exception:
        pytest.fail("Invalid base64 encoding")


# ============================================================================
# 11. INTEGRATION WITH PR-024A (EA POLL/ACK) SCENARIOS
# ============================================================================


@pytest.mark.asyncio
async def test_signal_envelope_for_ea_poll(envelope, test_device_id):
    """Test signal envelope suitable for EA poll response."""
    # Simulate poll response with encrypted signals
    signals = [
        {
            "id": "sig_001",
            "instrument": "EURUSD",
            "side": "buy",
            "entry": 1.0950,
        },
        {
            "id": "sig_002",
            "instrument": "GBPUSD",
            "side": "sell",
            "entry": 1.2750,
        },
    ]

    encrypted_signals = []

    for signal in signals:
        ct, nonce, aad = envelope.encrypt_signal(test_device_id, signal)
        encrypted_signals.append(
            {
                "ciphertext": ct,
                "nonce": nonce,
                "aad": aad,
            }
        )

    # Simulate EA receiving and decrypting
    decrypted_signals = []
    for enc_sig in encrypted_signals:
        decrypted = envelope.decrypt_signal(
            test_device_id,
            enc_sig["ciphertext"],
            enc_sig["nonce"],
            enc_sig["aad"],
        )
        decrypted_signals.append(decrypted)

    # Verify all signals decrypted correctly
    assert len(decrypted_signals) == len(signals)
    assert decrypted_signals[0]["id"] == "sig_001"
    assert decrypted_signals[1]["id"] == "sig_002"


# ============================================================================
# 12. SECURITY BOUNDARIES & ISOLATION
# ============================================================================


@pytest.mark.asyncio
async def test_no_key_leakage_in_logs(envelope, test_device_id, test_payload, caplog):
    """Test that keys are never logged."""
    ciphertext_b64, nonce_b64, aad = envelope.encrypt_signal(
        test_device_id, test_payload
    )

    log_content = caplog.text

    # Key should not appear in logs
    key_bytes = envelope.key_manager.derive_device_key(test_device_id)
    assert key_bytes.hex() not in log_content


@pytest.mark.asyncio
async def test_plaintext_never_in_ciphertext_format(envelope, test_device_id):
    """Test that plaintext doesn't appear in ciphertext."""
    secret_data = "SUPER_SECRET_API_KEY_12345"
    payload = {"secret": secret_data}

    ciphertext_b64, _, _ = envelope.encrypt_signal(test_device_id, payload)

    # Secret should not appear in ciphertext
    assert secret_data not in ciphertext_b64
    assert "SUPER_SECRET" not in ciphertext_b64
