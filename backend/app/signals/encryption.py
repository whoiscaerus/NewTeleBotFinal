"""
Encryption utilities for owner-only signal data (SL/TP protection).

This module provides encryption/decryption for the Signal.owner_only field
to prevent clients from seeing stop-loss and take-profit levels.
"""

import json
import os
from typing import Any

from cryptography.fernet import Fernet


class OwnerOnlyEncryption:
    """Encrypt/decrypt owner-only signal data using Fernet symmetric encryption."""

    def __init__(self):
        """Initialize with encryption key from settings."""
        # Key should be generated with: Fernet.generate_key()
        # and stored in secrets manager (PR-007) or environment variable
        key_str = os.getenv("OWNER_ONLY_ENCRYPTION_KEY")
        if not key_str:
            raise ValueError("OWNER_ONLY_ENCRYPTION_KEY environment variable not set")

        # Ensure key is bytes
        key: bytes = key_str.encode("utf-8") if isinstance(key_str, str) else key_str

        self.fernet = Fernet(key)

    def encrypt(self, data: dict[str, Any]) -> str:
        """
        Encrypt owner-only data to JSON string.

        Args:
            data: Dictionary containing owner-only fields (sl, tp, strategy, etc.)

        Returns:
            Base64-encoded encrypted JSON string

        Example:
            >>> encryptor = OwnerOnlyEncryption()
            >>> encrypted = encryptor.encrypt({"sl": 2645.0, "tp": 2670.0})
            >>> # Returns: "gAAAAABl..."
        """
        if not data:
            return ""

        # Serialize to JSON
        json_str = json.dumps(data, sort_keys=True)
        json_bytes = json_str.encode("utf-8")

        # Encrypt
        encrypted_bytes = self.fernet.encrypt(json_bytes)

        # Return as base64 string for storage
        return encrypted_bytes.decode("utf-8")

    def decrypt(self, encrypted_str: str) -> dict[str, Any]:
        """
        Decrypt owner-only data from JSON string.

        Args:
            encrypted_str: Base64-encoded encrypted JSON string

        Returns:
            Dictionary containing decrypted owner-only fields

        Raises:
            ValueError: If decryption fails (invalid key, tampered data)

        Example:
            >>> encryptor = OwnerOnlyEncryption()
            >>> data = encryptor.decrypt("gAAAAABl...")
            >>> print(data["sl"])  # 2645.0
        """
        if not encrypted_str:
            return {}

        try:
            # Decrypt
            encrypted_bytes = encrypted_str.encode("utf-8")
            decrypted_bytes = self.fernet.decrypt(encrypted_bytes)

            # Deserialize from JSON
            json_str = decrypted_bytes.decode("utf-8")
            data: dict[str, Any] = json.loads(json_str)

            return data

        except Exception as e:
            raise ValueError(f"Failed to decrypt owner_only data: {e}") from e


# Singleton instance
_encryptor: OwnerOnlyEncryption | None = None


def get_encryptor() -> OwnerOnlyEncryption:
    """Get singleton encryption instance."""
    global _encryptor
    if _encryptor is None:
        _encryptor = OwnerOnlyEncryption()
    return _encryptor


def encrypt_owner_only(data: dict[str, Any]) -> str:
    """
    Convenience function to encrypt owner-only data.

    Args:
        data: Dictionary containing sl, tp, strategy, etc.

    Returns:
        Encrypted string safe for database storage

    Example:
        >>> encrypted = encrypt_owner_only({"sl": 2645.0, "tp": 2670.0})
    """
    return get_encryptor().encrypt(data)


def decrypt_owner_only(encrypted_str: str) -> dict[str, Any]:
    """
    Convenience function to decrypt owner-only data.

    Args:
        encrypted_str: Encrypted string from database

    Returns:
        Decrypted dictionary with sl, tp, strategy fields

    Example:
        >>> data = decrypt_owner_only(signal.owner_only)
        >>> print(data["sl"])  # 2645.0
    """
    return get_encryptor().decrypt(encrypted_str)
