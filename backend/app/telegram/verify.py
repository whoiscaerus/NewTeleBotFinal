"""Telegram webhook request verification (IP allowlist, secret header)."""

import logging
from ipaddress import IPv4Network, ip_address

from fastapi import Request

from backend.app.core.settings import settings

logger = logging.getLogger(__name__)


def parse_cidrs(cidr_string: str | None) -> list[IPv4Network]:
    """Parse comma-separated CIDR strings into network objects.

    Args:
        cidr_string: Comma-separated CIDR strings (e.g., "192.168.1.0/24,10.0.0.0/8")

    Returns:
        List of IPv4Network objects

    Raises:
        ValueError: If CIDR format is invalid
    """
    if not cidr_string:
        return []

    cidrs = []
    for cidr in cidr_string.split(","):
        cidr = cidr.strip()
        if not cidr:
            continue
        try:
            cidrs.append(IPv4Network(cidr, strict=False))
        except ValueError as e:
            logger.error(f"Invalid CIDR format: {cidr} - {e}")
            raise ValueError(f"Invalid CIDR format: {cidr}") from e

    return cidrs


def is_ip_allowed(client_ip: str, allowed_cidrs: list[IPv4Network]) -> bool:
    """Check if client IP is in allowed CIDR ranges.

    Args:
        client_ip: Client IP address
        allowed_cidrs: List of allowed CIDR networks

    Returns:
        True if IP is allowed, False otherwise
    """
    if not allowed_cidrs:
        # No allowlist configured - allow all
        logger.debug("No IP allowlist configured - allowing all IPs")
        return True

    try:
        ip = ip_address(client_ip)
        for cidr in allowed_cidrs:
            if ip in cidr:
                logger.debug(f"IP {client_ip} allowed (matches {cidr})")
                return True

        logger.warning(f"IP {client_ip} denied (not in allowlist)")
        return False

    except ValueError as e:
        logger.error(f"Invalid IP address: {client_ip} - {e}")
        return False


def verify_secret_header(header_value: str | None, expected_secret: str | None) -> bool:
    """Verify optional X-Telegram-Webhook-Secret header.

    If both header and expected secret are configured, compare them.
    If only expected secret is configured, require the header.
    If neither configured, verification passes.

    Args:
        header_value: Value of X-Telegram-Webhook-Secret header
        expected_secret: Expected secret from settings

    Returns:
        True if verification passes, False if it fails
    """
    # If no expected secret configured, verification always passes
    if not expected_secret:
        logger.debug("No secret header requirement configured - verification skipped")
        return True

    # Expected secret configured but header missing
    if not header_value:
        logger.warning("Secret header required but not provided")
        return False

    # Both configured - use constant-time comparison to prevent timing attacks
    import hmac

    if not hmac.compare_digest(header_value, expected_secret):
        logger.warning("Secret header provided but value mismatch")
        return False

    logger.debug("Secret header verified successfully")
    return True


async def verify_webhook_request(request: Request) -> dict[str, bool]:
    """Verify all aspects of webhook request security.

    Checks:
    1. Client IP is in allowlist (if configured)
    2. Secret header matches (if configured)

    Args:
        request: FastAPI Request object

    Returns:
        Dict with keys:
        - ip_verified: IP passed allowlist check
        - secret_verified: Secret header passed verification
        - overall: All checks passed

    Raises:
        None - returns verification status dict instead
    """
    verification = {"ip_verified": True, "secret_verified": True, "overall": True}

    # Get client IP
    client_ip = request.client.host if request.client else "unknown"

    # 1. Verify IP allowlist
    try:
        allowed_cidrs = parse_cidrs(settings.TELEGRAM_IP_ALLOWLIST)
        ip_allowed = is_ip_allowed(client_ip, allowed_cidrs)
        verification["ip_verified"] = ip_allowed

        if not ip_allowed:
            logger.warning(f"Webhook rejected: IP {client_ip} not in allowlist")
            verification["overall"] = False

    except ValueError as e:
        logger.error(f"IP verification error: {e}")
        verification["ip_verified"] = False
        verification["overall"] = False

    # 2. Verify secret header
    secret_header = request.headers.get("X-Telegram-Webhook-Secret")
    secret_verified = verify_secret_header(
        secret_header, settings.TELEGRAM_WEBHOOK_SECRET
    )
    verification["secret_verified"] = secret_verified

    if not secret_verified:
        logger.warning("Webhook rejected: Secret header verification failed")
        verification["overall"] = False

    return verification


async def should_reject_webhook(request: Request) -> bool:
    """Determine if webhook should be rejected based on verification.

    Args:
        request: FastAPI Request object

    Returns:
        True if webhook should be rejected, False if it should be processed
    """
    verification = await verify_webhook_request(request)
    return not verification["overall"]
