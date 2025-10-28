"""
Device authentication middleware for HMAC-based EA device verification (PR-024a).

This module provides the DeviceAuth dependency for FastAPI that validates:
1. Required headers: X-Device-Id, X-Nonce, X-Timestamp, X-Signature
2. Device exists and is not revoked
3. HMAC signature is valid
4. Timestamp is fresh (within skew window)
5. Nonce has not been replayed

Example:
    >>> device = await DeviceAuthDependency(
    ...     device_id="dev_123",
    ...     nonce="nonce_abc",
    ...     timestamp="2025-10-26T10:30:45Z",
    ...     signature="base64_hmac_signature",
    ...     db=db_session,
    ...     redis=redis_client,
    ...     request=request,
    ... )
    >>> assert device.device.id == "dev_123"
    >>> assert not device.device.revoked
"""

import logging
from datetime import datetime
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.clients.models import Client, Device
from backend.app.core.db import get_db
from backend.app.core.redis import get_redis
from backend.app.ea.hmac import HMACBuilder

logger = logging.getLogger(__name__)


class DeviceAuthError(HTTPException):
    """Device authentication error (401/400)."""

    def __init__(self, detail: str, status_code: int = 401):
        super().__init__(status_code=status_code, detail=detail)


class DeviceAuthDependency:
    """
    FastAPI dependency for device HMAC authentication.

    Validates headers, device status, signature, and nonce freshness.
    """

    def __init__(
        self,
        request: Request,
        device_id: str,
        nonce: str,
        timestamp: str,
        signature: str,
        db: AsyncSession = Depends(get_db),  # noqa: B008
        redis: Redis = Depends(get_redis),  # noqa: B008
        timestamp_skew_seconds: int = 300,
        nonce_ttl_seconds: int = 600,
    ):
        self.request = request
        self.device_id = device_id
        self.nonce = nonce
        self.timestamp_str = timestamp
        self.signature = signature
        self.db = db
        self.redis = redis
        self.timestamp_skew_seconds = timestamp_skew_seconds
        self.nonce_ttl_seconds = nonce_ttl_seconds

        # Will be populated after validation
        self.device: Device | None = None
        self.client: Client | None = None

    async def __call__(self) -> "DeviceAuthDependency":
        """
        Validate device authentication.

        This is called as a FastAPI dependency. It performs all validation
        steps and either returns self or raises HTTPException (401/400).

        Returns:
            Self with device and client populated.

        Raises:
            HTTPException: 401 if auth fails, 400 if malformed.
        """
        await self._validate_timestamp()
        await self._validate_nonce()
        await self._load_device()
        await self._validate_signature()
        return self

    async def _validate_timestamp(self) -> None:
        """
        Validate timestamp is fresh (within skew window).

        Raises:
            HTTPException: 400 if timestamp format invalid or outside skew window.
        """
        try:
            ts = datetime.fromisoformat(self.timestamp_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError) as e:
            logger.warning(
                f"Invalid timestamp format: {self.timestamp_str}",
                extra={"device_id": self.device_id},
            )
            raise DeviceAuthError("Invalid timestamp format", 400) from e

        now = (
            datetime.utcnow().replace(tzinfo=ts.tzinfo)
            if ts.tzinfo
            else datetime.utcnow()
        )
        skew = (
            abs((now - ts).total_seconds())
            if ts.tzinfo
            else abs(
                (now.replace(tzinfo=None) - ts.replace(tzinfo=None)).total_seconds()
            )
        )

        if skew > self.timestamp_skew_seconds:
            logger.warning(
                f"Timestamp skew exceeded: {skew}s > {self.timestamp_skew_seconds}s",
                extra={"device_id": self.device_id, "skew_seconds": skew},
            )
            raise DeviceAuthError("Request timestamp outside acceptable window")

    async def _validate_nonce(self) -> None:
        """
        Validate nonce has not been replayed.

        Uses Redis SETNX (set if not exists) to prevent replay attacks.
        Nonce is stored with TTL equal to timestamp skew + nonce TTL.

        Raises:
            HTTPException: 401 if nonce has been replayed.
        """
        nonce_key = f"nonce:{self.device_id}:{self.nonce}"
        ttl = self.timestamp_skew_seconds + self.nonce_ttl_seconds

        result = await self.redis.set(nonce_key, "1", nx=True, ex=ttl)

        if not result:
            logger.warning(
                "Nonce replay detected",
                extra={"device_id": self.device_id, "nonce": self.nonce},
            )
            raise DeviceAuthError("Nonce has been replayed")

    async def _load_device(self) -> None:
        """
        Load device from database.

        Raises:
            HTTPException: 404 if device not found, 401 if revoked.
        """
        try:
            device_uuid = UUID(self.device_id)
        except (ValueError, AttributeError) as e:
            logger.warning(
                "Invalid device ID format", extra={"device_id": self.device_id}
            )
            raise DeviceAuthError("Invalid device ID format", 400) from e

        # Load device with client relationship
        stmt = select(Device).where(Device.id == device_uuid)
        result = await self.db.execute(stmt)
        device = result.scalar_one_or_none()

        if not device:
            logger.warning("Device not found", extra={"device_id": self.device_id})
            raise DeviceAuthError("Device not found", 404)

        if device.revoked or not device.is_active:
            logger.warning(
                "Device is revoked or inactive",
                extra={"device_id": self.device_id, "revoked": device.revoked},
            )
            raise DeviceAuthError("Device is revoked")

        self.device = device
        self.client = device.client

    async def _validate_signature(self) -> None:
        """
        Validate HMAC signature.

        Constructs canonical string from request and verifies signature
        against device's secret (stored as hash).

        Raises:
            HTTPException: 401 if signature invalid.
        """
        if not self.device or not self.device.hmac_key_hash:
            logger.error(
                "Device loaded but secret not available",
                extra={"device_id": self.device_id},
            )
            raise DeviceAuthError("Device secret not configured")

        # Get request body
        try:
            if self.request.method in ("POST", "PUT", "PATCH"):
                body = (await self.request.body()).decode("utf-8")
            else:
                body = ""
        except Exception as e:
            logger.error(
                "Failed to read request body",
                extra={"device_id": self.device_id, "error": str(e)},
            )
            raise DeviceAuthError("Failed to read request body", 400) from e

        # Build canonical string
        canonical = HMACBuilder.build_canonical_string(
            method=self.request.method,
            path=self.request.url.path,
            body=body,
            device_id=self.device_id,
            nonce=self.nonce,
            timestamp=self.timestamp_str,
        )

        # Verify signature against device secret
        verified = HMACBuilder.verify(
            canonical, self.signature, self.device.hmac_key_hash.encode()
        )

        if not verified:
            logger.warning(
                "Signature verification failed", extra={"device_id": self.device_id}
            )
            raise DeviceAuthError("Invalid signature")

    @property
    def user_id(self) -> UUID:
        """Get user ID from client."""
        if not self.client:
            raise ValueError("Device not authenticated")
        return self.client.user_id

    @property
    def client_id(self) -> UUID:
        """Get client ID from device."""
        if not self.device:
            raise ValueError("Device not authenticated")
        return self.device.client_id


async def get_device_auth(
    device_id: str | None = None,
    nonce: str | None = None,
    timestamp: str | None = None,
    signature: str | None = None,
) -> DeviceAuthDependency:
    """
    FastAPI dependency that validates device headers.

    Extracts X-Device-Id, X-Nonce, X-Timestamp, X-Signature from request headers
    and validates them.

    Returns:
        DeviceAuthDependency instance with device and client populated.

    Raises:
        HTTPException: 401 if auth fails, 400 if malformed.
    """
    if not all([device_id, nonce, timestamp, signature]):
        raise DeviceAuthError(
            "Missing required headers: X-Device-Id, X-Nonce, X-Timestamp, X-Signature"
        )

    return await DeviceAuthDependency(
        device_id=device_id,
        nonce=nonce,
        timestamp=timestamp,
        signature=signature,
    )()
