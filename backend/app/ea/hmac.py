"""
HMAC-SHA256 signature building and verification for device authentication.

This module provides utilities for constructing canonical request strings and
validating HMAC signatures for secure EA (Expert Advisor) device communication.
All signatures use HMAC-SHA256 with base64 encoding.

Example:
    >>> secret = b"device_secret_key_32_bytes_long"
    >>> canonical = HMACBuilder.build_canonical_string(
    ...     method="GET",
    ...     path="/api/v1/client/poll",
    ...     body="",
    ...     device_id="dev_123",
    ...     nonce="nonce_abc",
    ...     timestamp="2025-10-26T10:30:45Z"
    ... )
    >>> signature = HMACBuilder.sign(canonical, secret)
    >>> assert HMACBuilder.verify(canonical, signature, secret)
"""

import base64
import hashlib
import hmac


class HMACBuilder:
    """Builds and verifies HMAC-SHA256 signatures for device authentication."""

    @staticmethod
    def build_canonical_string(
        method: str,
        path: str,
        body: str,
        device_id: str,
        nonce: str,
        timestamp: str,
    ) -> str:
        """
        Construct canonical request string for signature.

        The canonical format is: METHOD|PATH|BODY|DEVICE_ID|NONCE|TIMESTAMP

        Args:
            method: HTTP method (GET, POST, etc.)
            path: Request path (e.g., /api/v1/client/poll)
            body: Request body (empty string for GET)
            device_id: Device ID from header
            nonce: Nonce from header
            timestamp: RFC3339 timestamp from header

        Returns:
            Canonical string ready for HMAC signing.

        Example:
            >>> canonical = HMACBuilder.build_canonical_string(
            ...     "GET", "/api/v1/client/poll", "", "dev_123", "nonce", "2025-10-26T10:30:45Z"
            ... )
            >>> assert "GET|/api/v1/client/poll" in canonical
        """
        parts = [method, path, body, device_id, nonce, timestamp]
        return "|".join(parts)

    @staticmethod
    def sign(canonical: str, secret: bytes) -> str:
        """
        Sign canonical string with HMAC-SHA256.

        Args:
            canonical: Canonical request string from build_canonical_string()
            secret: Secret key (device secret, stored as bytes)

        Returns:
            Base64-encoded signature.

        Example:
            >>> secret = b"test_secret_key_32_bytes_long!!"
            >>> canonical = "GET|/api/v1/client/poll||dev_123|nonce|2025-10-26T10:30:45Z"
            >>> sig = HMACBuilder.sign(canonical, secret)
            >>> assert isinstance(sig, str)
            >>> assert len(sig) > 0
        """
        signature = hmac.new(secret, canonical.encode("utf-8"), hashlib.sha256).digest()
        return base64.b64encode(signature).decode("utf-8")

    @staticmethod
    def verify(canonical: str, signature: str, secret: bytes) -> bool:
        """
        Verify HMAC signature.

        Args:
            canonical: Canonical request string
            signature: Base64-encoded signature to verify
            secret: Secret key (device secret)

        Returns:
            True if signature is valid, False otherwise.

        Example:
            >>> secret = b"test_secret_key_32_bytes_long!!"
            >>> canonical = "GET|/api/v1/client/poll||dev_123|nonce|2025-10-26T10:30:45Z"
            >>> sig = HMACBuilder.sign(canonical, secret)
            >>> assert HMACBuilder.verify(canonical, sig, secret) is True
            >>> assert HMACBuilder.verify(canonical, "invalid", secret) is False
        """
        try:
            expected_signature = HMACBuilder.sign(canonical, secret)
            return hmac.compare_digest(signature, expected_signature)
        except Exception:
            return False

    @staticmethod
    def extract_headers_for_signature(
        method: str,
        path: str,
        body: str,
        device_id: str,
        nonce: str,
        timestamp: str,
    ) -> tuple[str, str]:
        """
        Build canonical string and compute expected signature.

        Convenience method combining build and sign steps.

        Args:
            method: HTTP method
            path: Request path
            body: Request body
            device_id: Device ID
            nonce: Nonce value
            timestamp: RFC3339 timestamp

        Returns:
            Tuple of (canonical_string, signature)
        """
        canonical = HMACBuilder.build_canonical_string(
            method, path, body, device_id, nonce, timestamp
        )
        signature = HMACBuilder.sign(canonical, device_id.encode())  # placeholder
        return canonical, signature
