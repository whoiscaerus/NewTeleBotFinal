"""HMAC-SHA256 signature generation and verification for signal authentication."""

import base64
import hashlib
import hmac
import re
from datetime import datetime

from backend.app.trading.outbound.exceptions import OutboundSignatureError


def build_signature(
    secret: bytes,
    body: bytes,
    timestamp: str,
    producer_id: str,
) -> str:
    """Generate HMAC-SHA256 signature for signed signal delivery.

    Creates a canonical request from the provided components and signs it with
    HMAC-SHA256. The signature is base64-encoded for transmission in HTTP headers.

    Canonical Request Format:
        METHOD:POST
        ENDPOINT:/api/v1/signals/ingest
        TIMESTAMP:<RFC3339-timestamp>
        PRODUCER_ID:<producer-id>
        BODY_SHA256:<base64(sha256(body))>

    Algorithm:
        1. Create canonical request string (fields in order above)
        2. Compute SHA256 hash of request body
        3. Include body hash in canonical request
        4. Sign canonical request with HMAC-SHA256
        5. Base64-encode signature
        6. Return as base64 string

    Args:
        secret: HMAC secret key (minimum 16 bytes recommended)
        body: Request body bytes to sign
        timestamp: RFC3339 ISO format timestamp (e.g., "2025-10-25T14:30:45.123456Z")
        producer_id: Producer identifier

    Returns:
        str: Base64-encoded HMAC-SHA256 signature

    Raises:
        OutboundSignatureError: If parameters are invalid or timestamp malformed

    Example:
        >>> signature = build_signature(
        ...     secret=b"my-secret-key-min-16-bytes",
        ...     body=b'{"instrument":"GOLD","side":"buy"}',
        ...     timestamp="2025-10-25T14:30:45.123456Z",
        ...     producer_id="mt5-trader-1"
        ... )
        >>> isinstance(signature, str)
        True
        >>> len(signature) > 0
        True
        >>> # Same inputs produce same signature (deterministic)
        >>> sig2 = build_signature(
        ...     secret=b"my-secret-key-min-16-bytes",
        ...     body=b'{"instrument":"GOLD","side":"buy"}',
        ...     timestamp="2025-10-25T14:30:45.123456Z",
        ...     producer_id="mt5-trader-1"
        ... )
        >>> signature == sig2
        True
    """
    # Validate inputs
    if not secret:
        raise OutboundSignatureError("secret must not be empty")

    if not body:
        raise OutboundSignatureError("body must not be empty")

    if not timestamp:
        raise OutboundSignatureError("timestamp must not be empty")

    if not producer_id:
        raise OutboundSignatureError("producer_id must not be empty")

    # Validate timestamp format (RFC3339)
    if not _is_valid_rfc3339(timestamp):
        raise OutboundSignatureError(
            f"timestamp must be RFC3339 format (e.g., "
            f"2025-10-25T14:30:45.123456Z), got {timestamp!r}"
        )

    # Compute SHA256 hash of body
    body_sha256 = hashlib.sha256(body).digest()
    body_hash_b64 = base64.b64encode(body_sha256).decode("ascii")

    # Build canonical request
    canonical_request = (
        f"METHOD:POST\n"
        f"ENDPOINT:/api/v1/signals/ingest\n"
        f"TIMESTAMP:{timestamp}\n"
        f"PRODUCER_ID:{producer_id}\n"
        f"BODY_SHA256:{body_hash_b64}"
    )

    # Sign with HMAC-SHA256
    signature_bytes = hmac.new(
        secret,
        canonical_request.encode("utf-8"),
        hashlib.sha256,
    ).digest()

    # Encode as base64
    signature_b64 = base64.b64encode(signature_bytes).decode("ascii")

    return signature_b64


def verify_signature(
    secret: bytes,
    body: bytes,
    timestamp: str,
    producer_id: str,
    provided_signature: str,
) -> bool:
    """Verify an HMAC-SHA256 signature using timing-safe comparison.

    Regenerates the signature from the provided components and compares it
    with the provided signature using timing-safe string comparison to prevent
    timing attacks.

    Args:
        secret: HMAC secret key (must match signing secret)
        body: Request body that was signed
        timestamp: RFC3339 timestamp used for signing
        producer_id: Producer ID used for signing
        provided_signature: Base64-encoded signature to verify

    Returns:
        bool: True if signature is valid, False otherwise

    Raises:
        OutboundSignatureError: If inputs are invalid

    Example:
        >>> secret = b"my-secret-key-min-16-bytes"
        >>> body = b'{"instrument":"GOLD"}'
        >>> timestamp = "2025-10-25T14:30:45.123456Z"
        >>> producer_id = "mt5-trader-1"
        >>> sig = build_signature(secret, body, timestamp, producer_id)
        >>> verify_signature(secret, body, timestamp, producer_id, sig)
        True
        >>> verify_signature(secret, body, timestamp, producer_id, "invalid_sig")
        False
        >>> # Different body fails verification
        >>> verify_signature(secret, b'{"different":"body"}', timestamp, producer_id, sig)
        False
    """
    try:
        # Regenerate signature from components
        expected_signature = build_signature(secret, body, timestamp, producer_id)
    except OutboundSignatureError:
        raise

    # Use timing-safe comparison to prevent timing attacks
    # This ensures comparison time is constant regardless of where strings differ
    return hmac.compare_digest(expected_signature, provided_signature)


def _is_valid_rfc3339(timestamp: str) -> bool:
    """Validate RFC3339 timestamp format.

    Accepts ISO 8601 timestamps with timezone info.

    Valid formats:
        - 2025-10-25T14:30:45Z
        - 2025-10-25T14:30:45.123456Z
        - 2025-10-25T14:30:45+00:00
        - 2025-10-25T14:30:45.123456+00:00

    Args:
        timestamp: Timestamp string to validate

    Returns:
        bool: True if timestamp is valid RFC3339 format

    Example:
        >>> _is_valid_rfc3339("2025-10-25T14:30:45.123456Z")
        True
        >>> _is_valid_rfc3339("2025-10-25T14:30:45Z")
        True
        >>> _is_valid_rfc3339("not-a-timestamp")
        False
    """
    if not timestamp:
        return False

    # RFC3339 pattern with optional microseconds
    # Allows Z or +/-HH:MM timezone
    pattern = (
        r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
        r"(?:\.\d{1,6})?"
        r"(?:Z|[+-]\d{2}:\d{2})$"
    )

    if not re.match(pattern, timestamp):
        return False

    # Try parsing to ensure it's a valid datetime
    try:
        # Remove timezone for parsing
        base_timestamp = timestamp.replace("Z", "+00:00")
        datetime.fromisoformat(base_timestamp)
        return True
    except (ValueError, TypeError):
        return False
