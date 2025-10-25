"""
EA (Expert Advisor) Integration Module

Provides MT5 EA SDK support, encrypted signal transport, and device management.
"""

from backend.app.ea.auth import DeviceAuthService, DeviceEncryptionKey
from backend.app.ea.crypto import (
    DeviceKeyManager,
    SignalEnvelope,
    decrypt_payload,
    encrypt_payload,
)
from backend.app.ea.verification import (
    AccountLinkVerification,
    AccountVerificationService,
    VerificationChallenge,
)

__all__ = [
    "DeviceKeyManager",
    "SignalEnvelope",
    "encrypt_payload",
    "decrypt_payload",
    "DeviceAuthService",
    "DeviceEncryptionKey",
    "AccountVerificationService",
    "AccountLinkVerification",
    "VerificationChallenge",
]
