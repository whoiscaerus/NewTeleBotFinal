"""
Poll Protocol V2: Compression, ETags, Conditional Requests, Adaptive Backoff (PR-49).

Features:
- Response compression (gzip, brotli, zstd)
- ETag generation and validation (SHA256)
- Conditional requests (If-Modified-Since → 304 Not Modified)
- Adaptive backoff algorithm (10-60 seconds)
- Batch size limiting
"""

import gzip
import hashlib
import json
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

try:
    import brotli

    BROTLI_AVAILABLE = True
except ImportError:
    BROTLI_AVAILABLE = False

try:
    import zstandard as zstd

    ZSTD_AVAILABLE = True
except ImportError:
    ZSTD_AVAILABLE = False

logger = logging.getLogger(__name__)


def compress_response(data: dict, accept_encoding: str) -> tuple[bytes, str]:
    """
    Compress response data based on Accept-Encoding header.

    Args:
        data: Response data to compress
        accept_encoding: Accept-Encoding header value (comma-separated algorithms)

    Returns:
        Tuple of (compressed_bytes, algorithm_used)
        If no compression: (json_bytes, "identity")

    Example:
        >>> data = {"approvals": [...]}
        >>> compressed, algo = compress_response(data, "gzip, deflate")
        >>> assert algo == "gzip"
        >>> assert len(compressed) < len(json.dumps(data))
    """
    # Convert data to JSON bytes
    json_bytes = json.dumps(data).encode("utf-8")

    # Parse Accept-Encoding header
    encodings = [e.strip().lower() for e in accept_encoding.split(",")]

    # Try compression in order of preference
    if "br" in encodings and BROTLI_AVAILABLE:
        try:
            compressed = brotli.compress(json_bytes, quality=4)
            logger.debug(
                "Response compressed with brotli",
                extra={
                    "original_size": len(json_bytes),
                    "compressed_size": len(compressed),
                },
            )
            return compressed, "br"
        except Exception as e:
            logger.warning(f"Brotli compression failed: {e}")

    if "gzip" in encodings or "x-gzip" in encodings:
        try:
            compressed = gzip.compress(json_bytes, compresslevel=6)
            logger.debug(
                "Response compressed with gzip",
                extra={
                    "original_size": len(json_bytes),
                    "compressed_size": len(compressed),
                },
            )
            return compressed, "gzip"
        except Exception as e:
            logger.warning(f"Gzip compression failed: {e}")

    if "zstd" in encodings and ZSTD_AVAILABLE:
        try:
            cctx = zstd.ZstdCompressor(level=10)
            compressed = cctx.compress(json_bytes)
            logger.debug(
                "Response compressed with zstd",
                extra={
                    "original_size": len(json_bytes),
                    "compressed_size": len(compressed),
                },
            )
            return compressed, "zstd"
        except Exception as e:
            logger.warning(f"Zstd compression failed: {e}")

    # No compression
    return json_bytes, "identity"


def generate_etag(data: dict) -> str:
    """
    Generate ETag for response data using SHA256 hash.

    Args:
        data: Response data to hash

    Returns:
        SHA256 hash as hex string, prefixed with "sha256:"

    Example:
        >>> data = {"approvals": [{"id": "123"}]}
        >>> etag = generate_etag(data)
        >>> assert etag.startswith("sha256:")
        >>> len(etag) == 71  # 7 prefix + 64 hex chars
    """
    # Deterministic JSON serialization (sorted keys)
    json_str = json.dumps(data, sort_keys=True, separators=(",", ":"))
    json_bytes = json_str.encode("utf-8")

    # SHA256 hash
    hash_hex = hashlib.sha256(json_bytes).hexdigest()
    etag = f"sha256:{hash_hex}"

    logger.debug(f"Generated ETag: {etag}", extra={"data_size": len(json_bytes)})
    return etag


def check_if_modified(approvals: list, since: Optional[datetime]) -> bool:
    """
    Check if any approvals were created after 'since' timestamp.

    Args:
        approvals: List of Approval objects with created_at attribute
        since: Timestamp to compare against (ISO format datetime)

    Returns:
        True if any approval created after 'since', False otherwise

    Example:
        >>> from datetime import datetime, timedelta
        >>> now = datetime.utcnow()
        >>> past = now - timedelta(hours=1)
        >>> approvals = [type('Approval', (), {'created_at': now})()]
        >>> assert check_if_modified(approvals, past) == True
    """
    if not since:
        return True  # No since timestamp, return all

    for approval in approvals:
        if approval.created_at >= since:
            return True  # Found newer approval

    return False  # No newer approvals


def calculate_backoff(device_id: UUID, has_approvals: bool, poll_count: int) -> int:
    """
    Calculate adaptive polling interval based on recent activity.

    Adaptive backoff strategy:
    - If has_approvals: Fast polling (10s)
    - If no approvals: Exponential backoff (10s, 20s, 30s, ... 60s)
    - Reset to 10s when approvals received

    Args:
        device_id: Device ID for logging
        has_approvals: Whether this poll returned approvals
        poll_count: Number of consecutive empty polls (0 if has_approvals)

    Returns:
        Next poll interval in seconds (10-60)

    Example:
        >>> # Fast polling when active
        >>> interval = calculate_backoff(UUID('123'), True, 0)
        >>> assert interval == 10
        >>> # Exponential backoff
        >>> interval = calculate_backoff(UUID('123'), False, 3)
        >>> assert interval == 40
        >>> # Cap at 60
        >>> interval = calculate_backoff(UUID('123'), False, 10)
        >>> assert interval == 60
    """
    MIN_INTERVAL = 10
    MAX_INTERVAL = 60

    if has_approvals:
        # Fast polling when active
        logger.debug(
            "Approvals found, using fast poll interval",
            extra={"device_id": str(device_id), "interval": MIN_INTERVAL},
        )
        return MIN_INTERVAL

    # Exponential backoff: 10 * (poll_count + 1), capped at MAX_INTERVAL
    backoff = min(MIN_INTERVAL * (poll_count + 1), MAX_INTERVAL)

    logger.debug(
        "No approvals, using adaptive backoff",
        extra={
            "device_id": str(device_id),
            "poll_count": poll_count,
            "interval": backoff,
        },
    )
    return backoff


def calculate_compression_ratio(original_size: int, compressed_size: int) -> float:
    """
    Calculate compression ratio as decimal (0-1).

    Args:
        original_size: Original data size in bytes
        compressed_size: Compressed data size in bytes

    Returns:
        Compression ratio (0.0 = perfect, 1.0 = no compression)

    Example:
        >>> ratio = calculate_compression_ratio(2800, 1000)
        >>> assert ratio == pytest.approx(0.357, rel=0.01)
    """
    if original_size == 0:
        return 0.0

    ratio = compressed_size / original_size
    return round(ratio, 3)
