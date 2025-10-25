"""
PR-042: Encrypted Signal Transport - AEAD envelope for EA signals

Implements AES-GCM encryption for signal payloads to protect against MITM attacks.
HMAC verifies integrity; GCM provides confidentiality.
"""

import base64
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


@dataclass
class EncryptionKey:
    """Device encryption key with metadata."""

    key_id: str
    device_id: str
    encryption_key: bytes
    created_at: datetime
    expires_at: datetime
    is_active: bool = True


class DeviceKeyManager:
    """
    Manages per-device encryption keys with rotation support.
    Keys are derived from master secret + device ID using KDF.
    """

    def __init__(self, kdf_secret: str, key_rotate_days: int = 90):
        """
        Initialize key manager.

        Args:
            kdf_secret: Master KDF secret (from env)
            key_rotate_days: Rotation period in days
        """
        self.kdf_secret = (
            kdf_secret.encode() if isinstance(kdf_secret, str) else kdf_secret
        )
        self.key_rotate_days = key_rotate_days
        self.active_keys: dict[str, EncryptionKey] = {}  # device_id -> key

    def derive_device_key(self, device_id: str, date_tag: str | None = None) -> bytes:
        """
        Derive device encryption key using PBKDF2.

        Args:
            device_id: Unique device identifier
            date_tag: Optional date tag for key rotation (YYYY-MM-DD)

        Returns:
            32-byte encryption key
        """
        if date_tag is None:
            date_tag = datetime.utcnow().strftime("%Y-%m-%d")
        # Combine KDF secret + device ID + date tag
        salt = (device_id + "::" + date_tag).encode()

        # PBKDF2 with 100k iterations
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,  # 256-bit key
            salt=salt,
            iterations=100000,
        )

        key = kdf.derive(self.kdf_secret)
        return key

    def create_device_key(self, device_id: str) -> EncryptionKey:
        """
        Create a new device encryption key.

        Args:
            device_id: Device identifier

        Returns:
            EncryptionKey instance
        """
        key_bytes = self.derive_device_key(device_id)
        key_id = f"{device_id}_{datetime.utcnow().isoformat()}"

        key = EncryptionKey(
            key_id=key_id,
            device_id=device_id,
            encryption_key=key_bytes,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=self.key_rotate_days),
            is_active=True,
        )

        self.active_keys[device_id] = key
        return key

    def get_device_key(self, device_id: str) -> EncryptionKey | None:
        """
        Get current active key for device.

        Args:
            device_id: Device identifier

        Returns:
            EncryptionKey or None if expired/inactive
        """
        key = self.active_keys.get(device_id)

        if key is None:
            # Try to derive key for today
            key_bytes = self.derive_device_key(device_id)
            key = EncryptionKey(
                key_id=f"{device_id}_derived",
                device_id=device_id,
                encryption_key=key_bytes,
                created_at=datetime.utcnow(),
                expires_at=datetime.utcnow() + timedelta(days=self.key_rotate_days),
                is_active=True,
            )
            self.active_keys[device_id] = key

        # Check if expired
        if datetime.utcnow() > key.expires_at:
            return None

        return key if key.is_active else None

    def revoke_device_key(self, device_id: str):
        """
        Revoke device key (triggers re-registration).

        Args:
            device_id: Device identifier
        """
        if device_id in self.active_keys:
            self.active_keys[device_id].is_active = False


class SignalEnvelope:
    """
    AEAD envelope for signal payloads.
    Provides authenticated encryption with associated data.
    """

    def __init__(self, key_manager: DeviceKeyManager):
        """
        Initialize envelope handler.

        Args:
            key_manager: DeviceKeyManager instance
        """
        self.key_manager = key_manager

    def encrypt_signal(self, device_id: str, payload: dict) -> tuple[str, str, str]:
        """
        Encrypt signal payload with AES-256-GCM.

        Args:
            device_id: Target device ID
            payload: Signal data (dict)

        Returns:
            Tuple of (ciphertext_b64, nonce_b64, aad)
            - ciphertext_b64: Base64-encoded (nonce || ciphertext || tag)
            - nonce_b64: Base64-encoded 12-byte nonce
            - aad: Additional authenticated data (device_id)

        Raises:
            ValueError: If device key not found or expired
        """
        key_obj = self.key_manager.get_device_key(device_id)
        if not key_obj:
            raise ValueError(f"No active encryption key for device: {device_id}")

        # Generate random nonce (12 bytes for GCM)
        nonce = os.urandom(12)

        # Prepare plaintext
        plaintext = json.dumps(payload).encode()

        # Additional authenticated data (cannot be decrypted, but authenticated)
        aad = device_id.encode()

        # Encrypt using AES-256-GCM
        cipher = AESGCM(key_obj.encryption_key)
        ciphertext = cipher.encrypt(nonce, plaintext, aad)

        # Return envelope: ciphertext || tag (combined by AESGCM)
        ciphertext_b64 = base64.b64encode(ciphertext).decode()
        nonce_b64 = base64.b64encode(nonce).decode()

        return ciphertext_b64, nonce_b64, device_id

    def decrypt_signal(
        self, device_id: str, ciphertext_b64: str, nonce_b64: str, aad: str
    ) -> dict:
        """
        Decrypt signal payload.

        Args:
            device_id: Source device ID
            ciphertext_b64: Base64-encoded ciphertext
            nonce_b64: Base64-encoded nonce
            aad: Additional authenticated data (must match encryption)

        Returns:
            Decrypted payload (dict)

        Raises:
            ValueError: If key not found, AAD mismatch, or decryption fails
        """
        key_obj = self.key_manager.get_device_key(device_id)
        if not key_obj:
            raise ValueError(f"No active encryption key for device: {device_id}")

        # Verify AAD
        if aad != device_id:
            raise ValueError("AAD mismatch - possible tampering detected")

        # Decode from base64
        ciphertext = base64.b64decode(ciphertext_b64)
        nonce = base64.b64decode(nonce_b64)

        # Decrypt using AES-256-GCM
        cipher = AESGCM(key_obj.encryption_key)
        aad_bytes = device_id.encode()

        plaintext = cipher.decrypt(nonce, ciphertext, aad_bytes)
        payload = json.loads(plaintext.decode())

        return payload

    def get_envelope_metadata(self, ciphertext_b64: str) -> dict:
        """
        Extract envelope metadata (size only, no decryption).

        Args:
            ciphertext_b64: Base64-encoded ciphertext

        Returns:
            Metadata dict with ciphertext_length
        """
        ciphertext = base64.b64decode(ciphertext_b64)
        return {
            "ciphertext_length": len(ciphertext),
            "created_at": datetime.utcnow().isoformat(),
        }


class EncryptionSettings:
    """Configuration for encryption system."""

    def __init__(self):
        """Initialize from environment."""
        self.kdf_secret = os.getenv(
            "DEVICE_KEY_KDF_SECRET", "dev-kdf-secret-do-not-use-prod"
        )
        self.key_rotate_days = int(os.getenv("DEVICE_KEY_ROTATE_DAYS", "90"))
        self.enable_encryption = (
            os.getenv("ENABLE_SIGNAL_ENCRYPTION", "true").lower() == "true"
        )


# Global manager instance
_key_manager: DeviceKeyManager | None = None


def get_key_manager() -> DeviceKeyManager:
    """Get or create global key manager."""
    global _key_manager
    if _key_manager is None:
        settings = EncryptionSettings()
        _key_manager = DeviceKeyManager(settings.kdf_secret, settings.key_rotate_days)
    return _key_manager


def encrypt_payload(device_id: str, payload: dict) -> dict:
    """
    Convenience function to encrypt signal payload.

    Args:
        device_id: Target device ID
        payload: Signal data

    Returns:
        Dict with encrypted envelope
    """
    key_manager = get_key_manager()
    envelope = SignalEnvelope(key_manager)

    try:
        ciphertext_b64, nonce_b64, aad = envelope.encrypt_signal(device_id, payload)
        return {
            "ciphertext": ciphertext_b64,
            "nonce": nonce_b64,
            "aad": aad,
            "metadata": envelope.get_envelope_metadata(ciphertext_b64),
        }
    except ValueError as e:
        return {"error": str(e)}


def decrypt_payload(
    device_id: str, ciphertext_b64: str, nonce_b64: str, aad: str
) -> dict:
    """
    Convenience function to decrypt signal payload.

    Args:
        device_id: Source device ID
        ciphertext_b64: Base64-encoded ciphertext
        nonce_b64: Base64-encoded nonce
        aad: Additional authenticated data

    Returns:
        Decrypted payload (dict)
    """
    key_manager = get_key_manager()
    envelope = SignalEnvelope(key_manager)

    try:
        return envelope.decrypt_signal(device_id, ciphertext_b64, nonce_b64, aad)
    except Exception as e:
        return {"error": str(e)}
