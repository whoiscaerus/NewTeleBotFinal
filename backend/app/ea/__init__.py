"""
EA (Expert Advisor) Integration Module

Provides MT5 EA SDK support, encrypted signal transport, and device management.
"""

from backend.app.ea.auth import DeviceAuthDependency, DeviceAuthError
from backend.app.ea.crypto import SignalEnvelope, decrypt_payload, encrypt_payload

__all__ = [
    "DeviceAuthDependency",
    "DeviceAuthError",
    "SignalEnvelope",
    "encrypt_payload",
    "decrypt_payload",
]
