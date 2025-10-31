"""Unit tests for owner_only encryption utilities.

Tests:
    - Encrypt/decrypt round-trip
    - Tamper detection
    - Empty data handling
    - Key validation
    - Error scenarios
"""

import os
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet

from backend.app.signals.encryption import (
    OwnerOnlyEncryption,
    decrypt_owner_only,
    encrypt_owner_only,
)


class TestOwnerOnlyEncryption:
    """Test encryption/decryption of owner-only signal data."""

    @pytest.fixture
    def valid_key(self):
        """Generate valid Fernet key."""
        return Fernet.generate_key().decode()

    @pytest.fixture
    def encryption(self, valid_key):
        """Create encryption instance with valid key."""
        with patch.dict(os.environ, {"OWNER_ONLY_ENCRYPTION_KEY": valid_key}):
            return OwnerOnlyEncryption()

    def test_encrypt_decrypt_round_trip(self, encryption):
        """Test data survives encrypt → decrypt cycle."""
        original_data = {"sl": 2645.0, "tp": 2670.0, "strategy": "fib_rsi_confluence"}

        # Encrypt
        encrypted = encryption.encrypt(original_data)
        assert isinstance(encrypted, str)
        assert encrypted != str(original_data)  # Should be encrypted

        # Decrypt
        decrypted = encryption.decrypt(encrypted)
        assert decrypted == original_data

    def test_encrypt_with_none_values(self, encryption):
        """Test encryption handles None values correctly."""
        data_with_nones = {"sl": None, "tp": 2670.0, "strategy": "breakout"}

        encrypted = encryption.encrypt(data_with_nones)
        decrypted = encryption.decrypt(encrypted)

        assert decrypted["sl"] is None
        assert decrypted["tp"] == 2670.0
        assert decrypted["strategy"] == "breakout"

    def test_encrypt_empty_dict(self, encryption):
        """Test encryption handles empty dict."""
        empty_data = {}

        encrypted = encryption.encrypt(empty_data)
        decrypted = encryption.decrypt(encrypted)

        assert decrypted == {}

    def test_decrypt_with_wrong_key_raises_error(self, valid_key):
        """Test decryption with wrong key raises ValueError."""
        # Encrypt with one key
        with patch.dict(os.environ, {"OWNER_ONLY_ENCRYPTION_KEY": valid_key}):
            encryption1 = OwnerOnlyEncryption()
            encrypted = encryption1.encrypt({"sl": 2645.0})

        # Try to decrypt with different key
        different_key = Fernet.generate_key().decode()
        with patch.dict(os.environ, {"OWNER_ONLY_ENCRYPTION_KEY": different_key}):
            encryption2 = OwnerOnlyEncryption()

            with pytest.raises(ValueError, match="Failed to decrypt"):
                encryption2.decrypt(encrypted)

    def test_decrypt_tampered_data_raises_error(self, encryption):
        """Test decryption of tampered data raises ValueError."""
        original_data = {"sl": 2645.0, "tp": 2670.0}
        encrypted = encryption.encrypt(original_data)

        # Tamper with encrypted string
        tampered = encrypted[:-5] + "XXXXX"

        with pytest.raises(ValueError, match="Failed to decrypt"):
            encryption.decrypt(tampered)

    def test_decrypt_invalid_json_raises_error(self, encryption, valid_key):
        """Test decryption of non-JSON data raises ValueError."""
        # Create valid encrypted data but not JSON
        with patch.dict(os.environ, {"OWNER_ONLY_ENCRYPTION_KEY": valid_key}):
            fernet = Fernet(valid_key.encode())
            non_json_encrypted = fernet.encrypt(b"not valid json").decode()

            with pytest.raises(ValueError, match="Failed to decrypt"):
                encryption.decrypt(non_json_encrypted)

    def test_missing_encryption_key_raises_error(self):
        """Test initialization without key raises ValueError."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(
                ValueError,
                match="OWNER_ONLY_ENCRYPTION_KEY environment variable not set",
            ):
                OwnerOnlyEncryption()

    def test_invalid_encryption_key_raises_error(self):
        """Test initialization with invalid key raises ValueError."""
        with patch.dict(os.environ, {"OWNER_ONLY_ENCRYPTION_KEY": "invalid_key"}):
            with pytest.raises(ValueError, match="Fernet key must be"):
                OwnerOnlyEncryption()

    def test_encrypt_preserves_nested_data(self, encryption):
        """Test encryption handles nested dictionaries."""
        nested_data = {
            "sl": 2645.0,
            "tp": 2670.0,
            "strategy": "complex",
            "params": {"rsi_period": 14, "fib_levels": [0.382, 0.5, 0.618]},
        }

        encrypted = encryption.encrypt(nested_data)
        decrypted = encryption.decrypt(encrypted)

        assert decrypted == nested_data
        assert decrypted["params"]["rsi_period"] == 14
        assert decrypted["params"]["fib_levels"] == [0.382, 0.5, 0.618]


class TestConvenienceFunctions:
    """Test module-level convenience functions."""

    @pytest.fixture
    def valid_key(self):
        """Generate valid Fernet key."""
        return Fernet.generate_key().decode()

    def test_encrypt_owner_only_convenience_function(self, valid_key):
        """Test encrypt_owner_only convenience function."""
        with patch.dict(os.environ, {"OWNER_ONLY_ENCRYPTION_KEY": valid_key}):
            data = {"sl": 2645.0, "tp": 2670.0}
            encrypted = encrypt_owner_only(data)

            assert isinstance(encrypted, str)
            assert len(encrypted) > 0

    def test_decrypt_owner_only_convenience_function(self, valid_key):
        """Test decrypt_owner_only convenience function."""
        with patch.dict(os.environ, {"OWNER_ONLY_ENCRYPTION_KEY": valid_key}):
            original_data = {"sl": 2645.0, "tp": 2670.0}
            encrypted = encrypt_owner_only(original_data)
            decrypted = decrypt_owner_only(encrypted)

            assert decrypted == original_data

    def test_convenience_functions_use_singleton(self, valid_key):
        """Test convenience functions reuse same encryption instance."""
        with patch.dict(os.environ, {"OWNER_ONLY_ENCRYPTION_KEY": valid_key}):
            data = {"sl": 2645.0}

            # Multiple calls should use same instance
            encrypted1 = encrypt_owner_only(data)
            encrypted2 = encrypt_owner_only(data)

            # Decrypt both
            decrypted1 = decrypt_owner_only(encrypted1)
            decrypted2 = decrypt_owner_only(encrypted2)

            assert decrypted1 == data
            assert decrypted2 == data


class TestRealWorldScenarios:
    """Test realistic usage scenarios."""

    @pytest.fixture
    def valid_key(self):
        """Generate valid Fernet key."""
        return Fernet.generate_key().decode()

    def test_encrypt_typical_signal_data(self, valid_key):
        """Test encrypting typical trading signal owner data."""
        with patch.dict(os.environ, {"OWNER_ONLY_ENCRYPTION_KEY": valid_key}):
            signal_owner_data = {
                "sl": 2645.50,
                "tp": 2670.00,
                "strategy": "fibonacci_retracement_rsi_confluence",
                "entry_reason": "0.618 fib level + RSI oversold + bullish engulfing",
                "risk_reward": 2.5,
                "confidence": 0.85,
            }

            encrypted = encrypt_owner_only(signal_owner_data)
            decrypted = decrypt_owner_only(encrypted)

            assert decrypted == signal_owner_data
            assert decrypted["sl"] == 2645.50
            assert decrypted["tp"] == 2670.00
            assert decrypted["risk_reward"] == 2.5

    def test_encrypt_minimal_signal_data(self, valid_key):
        """Test encrypting minimal signal with only SL/TP."""
        with patch.dict(os.environ, {"OWNER_ONLY_ENCRYPTION_KEY": valid_key}):
            minimal_data = {"sl": 2645.0, "tp": 2670.0}

            encrypted = encrypt_owner_only(minimal_data)
            decrypted = decrypt_owner_only(encrypted)

            assert decrypted == minimal_data

    def test_encrypted_string_length_reasonable(self, valid_key):
        """Test encrypted string is not excessively long."""
        with patch.dict(os.environ, {"OWNER_ONLY_ENCRYPTION_KEY": valid_key}):
            data = {"sl": 2645.0, "tp": 2670.0, "strategy": "test"}
            encrypted = encrypt_owner_only(data)

            # Fernet overhead is ~140 bytes + base64 encoding
            # Should be < 500 bytes for typical data
            assert len(encrypted) < 500

    def test_encryption_determinism(self, valid_key):
        """Test same data encrypted twice produces different ciphertexts."""
        with patch.dict(os.environ, {"OWNER_ONLY_ENCRYPTION_KEY": valid_key}):
            data = {"sl": 2645.0, "tp": 2670.0}

            encrypted1 = encrypt_owner_only(data)
            encrypted2 = encrypt_owner_only(data)

            # Different ciphertexts (Fernet includes timestamp + nonce)
            assert encrypted1 != encrypted2

            # But both decrypt to same data
            assert decrypt_owner_only(encrypted1) == data
            assert decrypt_owner_only(encrypted2) == data
