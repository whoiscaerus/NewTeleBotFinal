"""Service layer for signals domain business logic."""

import base64
import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.signals.models import Signal
from backend.app.signals.schemas import SignalCreate

# Get logger
logger = logging.getLogger(__name__)


async def create_signal(
    db: AsyncSession,
    signal_data: SignalCreate,
    producer_id: Optional[str] = None,
) -> Signal:
    """
    Create and persist a new trading signal.

    Args:
        db: Database session
        signal_data: Validated signal creation request
        producer_id: Optional producer identifier for audit trail

    Returns:
        Created Signal instance (not yet committed)

    Raises:
        Exception: If signal creation fails (propagated for error handling)

    Example:
        >>> signal = await create_signal(
        ...     db=session,
        ...     signal_data=SignalCreate(
        ...         instrument="XAUUSD",
        ...         side=0,
        ...         time=datetime.utcnow(timezone.utc),
        ...         payload={"rsi": 75}
        ...     ),
        ...     producer_id="producer-1"
        ... )
        >>> await db.commit()
        >>> await db.refresh(signal)
    """
    try:
        signal = Signal(
            instrument=signal_data.instrument,
            side=signal_data.side,
            time=signal_data.time,
            payload=signal_data.payload,
            version=signal_data.version,
            status=0,  # new
        )

        db.add(signal)

        logger.info(
            "Signal created",
            extra={
                "signal_id": signal.id,
                "instrument": signal.instrument,
                "side": signal.side,
                "producer_id": producer_id,
            },
        )

        return signal

    except Exception as e:
        logger.error(
            f"Failed to create signal: {e}",
            extra={
                "instrument": signal_data.instrument,
                "producer_id": producer_id,
            },
            exc_info=True,
        )
        raise


def validate_hmac_signature(
    body: str,
    timestamp: str,
    producer_id: str,
    signature: str,
    secret: str,
) -> bool:
    """
    Validate HMAC-SHA256 signature of signal request.

    Canonical format: {body}{timestamp}{producer_id}

    Args:
        body: Request body JSON string (not parsed)
        timestamp: ISO8601 timestamp header value
        producer_id: Producer ID header value
        signature: Base64-encoded HMAC-SHA256 signature
        secret: HMAC secret key

    Returns:
        True if signature is valid, False otherwise

    Raises:
        ValueError: If signature format is invalid (not base64)

    Example:
        >>> is_valid = validate_hmac_signature(
        ...     body='{"instrument":"XAUUSD","side":0}',
        ...     timestamp="2024-01-15T10:30:45Z",
        ...     producer_id="producer-1",
        ...     signature="dGVzdA==",
        ...     secret="secret-key"
        ... )
    """
    try:
        # Decode base64 signature
        try:
            expected_signature_bytes = base64.b64decode(signature)
        except Exception as e:
            logger.warning(f"Invalid base64 signature: {e}")
            return False

        # Build canonical string
        canonical = f"{body}{timestamp}{producer_id}"

        # Calculate expected HMAC
        calculated_hmac = hmac.new(
            secret.encode("utf-8"),
            canonical.encode("utf-8"),
            hashlib.sha256,
        ).digest()

        # Constant-time comparison (prevent timing attacks)
        is_valid = hmac.compare_digest(
            calculated_hmac,
            expected_signature_bytes,
        )

        if is_valid:
            logger.info(
                "HMAC validation successful",
                extra={"producer_id": producer_id},
            )
        else:
            logger.warning(
                "HMAC validation failed",
                extra={"producer_id": producer_id},
            )

        return is_valid

    except Exception as e:
        logger.error(
            f"HMAC validation error: {e}",
            extra={"producer_id": producer_id},
            exc_info=True,
        )
        return False


def validate_timestamp_freshness(
    timestamp_str: str,
    tolerance_seconds: int = 300,
) -> tuple[bool, str]:
    """
    Validate that timestamp is within acceptable window.

    Args:
        timestamp_str: ISO8601 timestamp string
        tolerance_seconds: Max age of timestamp (default 5 minutes)

    Returns:
        Tuple of (is_valid, reason_if_invalid)

    Example:
        >>> is_valid, reason = validate_timestamp_freshness("2024-01-15T10:30:45Z")
        >>> if not is_valid:
        ...     raise ValueError(f"Invalid timestamp: {reason}")
    """
    try:
        # Parse timestamp
        if timestamp_str.endswith("Z"):
            timestamp_str = timestamp_str[:-1] + "+00:00"

        request_time = datetime.fromisoformat(timestamp_str)
        current_time = datetime.now(timezone.utc)

        # Calculate time difference
        diff = abs((current_time - request_time).total_seconds())

        # Allow small epsilon for execution time (100ms)
        if diff > (tolerance_seconds + 0.1):
            return (
                False,
                f"Timestamp is {diff:.0f}s old (max {tolerance_seconds}s allowed)",
            )

        return True, ""

    except Exception as e:
        return False, f"Invalid timestamp format: {e}"


def validate_signal_payload(payload: Optional[dict]) -> bool:
    """
    Validate signal payload structure and size.

    Args:
        payload: Payload dict to validate

    Returns:
        True if valid, False otherwise

    Example:
        >>> is_valid = validate_signal_payload({"rsi": 75})
        >>> assert is_valid
    """
    if payload is None:
        return True

    if not isinstance(payload, dict):
        logger.warning(f"Payload is not dict: {type(payload)}")
        return False

    # Check size
    try:
        payload_size = len(json.dumps(payload).encode("utf-8"))
        max_size = 32768

        if payload_size > max_size:
            logger.warning(
                f"Payload size {payload_size} exceeds {max_size}",
            )
            return False

        return True

    except Exception as e:
        logger.error(f"Payload validation error: {e}", exc_info=True)
        return False
