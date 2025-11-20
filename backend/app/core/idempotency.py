"""
Idempotency & Replay Protection for Payment Flows

Generic idempotency handler for request deduplication.
Used by payment flows (PR-040) and other services.

Implements:
- Idempotent request handling with Redis cache
- Webhook replay protection with time windows
- Duplicate charge prevention
- Error recovery with safe retries
"""

import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, cast

import redis
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class IdempotencyError(Exception):
    """Raised when idempotency check fails."""

    pass


class ReplayError(Exception):
    """Raised when webhook replay is detected."""

    pass


# ============================================================================
# DATABASE MODELS
# ============================================================================


class IdempotencyKey(BaseModel):
    """Pydantic model for idempotency tracking."""

    key: str = Field(..., description="Unique idempotency key from client")
    response: dict[str, Any] = Field(..., description="Cached response")
    status_code: int = Field(..., description="HTTP status code")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime = Field(
        default_factory=lambda: datetime.utcnow() + timedelta(hours=24),
        description="Expiry time (default 24h)",
    )


class WebhookReplayLog(BaseModel):
    """Tracks webhook processing to prevent replays."""

    webhook_id: str = Field(..., description="Stripe/Telegram webhook event ID")
    event_type: str = Field(..., description="Event type (charge.succeeded, etc)")
    payload_hash: str = Field(..., description="HMAC-SHA256 of normalized payload")
    processed_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = Field(default="processed", description="processed | failed | pending")


# ============================================================================
# IDEMPOTENCY HANDLER
# ============================================================================


class IdempotencyHandler:
    """
    Manages idempotent payment requests.

    Prevents duplicate processing by caching responses with idempotency keys.
    Example:
        handler = IdempotencyHandler(redis_client)
        cached_response = handler.get_or_process_idempotent(
            key="idempotency-key-123",
            process_fn=lambda: create_charge(...)
        )
    """

    def __init__(self, redis_client: redis.Redis, ttl_seconds: int = 86400):
        """
        Initialize idempotency handler.

        Args:
            redis_client: Redis connection
            ttl_seconds: Key expiry time (default 24h)
        """
        self.redis = redis_client
        self.ttl = ttl_seconds

    async def get_cached(self, key: str) -> dict[str, Any] | None:
        """
        Retrieve cached response if exists.

        Args:
            key: Idempotency key

        Returns:
            Cached response dict or None if not found/expired
        """
        try:
            cached = self.redis.get(f"idempotency:{key}")
            if cached:
                logger.info(f"Idempotency hit for key: {key}")
                cached_str = cast(str | bytes | bytearray, cached)
                return cast(dict[str, Any], json.loads(cached_str))
        except Exception as e:
            logger.warning(f"Error retrieving cached idempotency: {e}")

        return None

    async def set_cached(self, key: str, response: dict[str, Any]) -> bool:
        """
        Cache response with idempotency key.

        Args:
            key: Idempotency key
            response: Response to cache

        Returns:
            True if cached successfully
        """
        try:
            self.redis.setex(
                f"idempotency:{key}",
                self.ttl,
                json.dumps(response),
            )
            logger.info(
                f"Idempotency cached for key: {key}", extra={"ttl_seconds": self.ttl}
            )
            return True
        except Exception as e:
            logger.error(f"Error caching idempotency: {e}")
            return False

    async def process_idempotent(
        self,
        key: str,
        process_fn,
        *args,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Execute function with idempotency guarantee.

        If key exists in cache, returns cached response.
        Otherwise, executes process_fn, caches result, and returns.

        Args:
            key: Idempotency key
            process_fn: Async function to execute
            *args, **kwargs: Arguments to pass to process_fn

        Returns:
            Response dict (from cache or fresh)

        Raises:
            IdempotencyError: If processing fails
        """
        # Check cache first
        cached = await self.get_cached(key)
        if cached:
            return cached

        # Process fresh
        try:
            logger.info(f"Processing idempotent request: {key}")
            response = await process_fn(*args, **kwargs)

            # Cache for future retries
            await self.set_cached(key, response)

            return cast(dict[str, Any], response)

        except Exception as e:
            logger.error(f"Idempotent processing failed: {e}", exc_info=True)
            raise IdempotencyError(f"Processing failed: {str(e)}")


# ============================================================================
# REPLAY PROTECTION
# ============================================================================


class ReplayProtector:
    """
    Prevents webhook replay attacks.

    Tracks processed webhooks and rejects replayed events within time window.
    Example:
        protector = ReplayProtector(redis_client, replay_ttl_seconds=600)
        protector.check_and_mark_webhook(
            webhook_id="evt_1234567890",
            event_type="charge.succeeded",
            payload=webhook_data
        )
    """

    def __init__(self, redis_client: redis.Redis, replay_ttl_seconds: int = 600):
        """
        Initialize replay protector.

        Args:
            redis_client: Redis connection
            replay_ttl_seconds: Time window for replay detection (default 10m)
        """
        self.redis = redis_client
        self.replay_ttl = replay_ttl_seconds

    def _hash_payload(self, payload: dict[str, Any]) -> str:
        """
        Create deterministic hash of webhook payload.

        Normalizes JSON to ensure same payload always produces same hash.

        Args:
            payload: Webhook payload dict

        Returns:
            HMAC-SHA256 hex digest
        """
        # Normalize: sort keys, exclude timestamp for stability
        normalized = json.dumps(
            {
                k: v
                for k, v in sorted(payload.items())
                if k not in ["timestamp", "received_at"]
            },
            sort_keys=True,
        )
        return hashlib.sha256(normalized.encode()).hexdigest()

    def check_replay(self, webhook_id: str, payload: dict[str, Any]) -> bool:
        """
        Check if webhook is a replay.

        Args:
            webhook_id: Unique webhook event ID
            payload: Webhook payload

        Returns:
            True if replay detected (already processed), False if fresh

        Raises:
            ReplayError: If replay detected
        """
        payload_hash = self._hash_payload(payload)
        cache_key = f"webhook_replay:{webhook_id}"

        # Check if already processed
        try:
            existing_hash = self.redis.get(cache_key)

            if existing_hash:
                existing_str = (
                    existing_hash.decode()
                    if isinstance(existing_hash, bytes)
                    else existing_hash
                )
                if existing_str == payload_hash:
                    logger.warning(
                        f"Webhook replay detected: {webhook_id}",
                        extra={"webhook_id": webhook_id, "status": "replay"},
                    )
                    raise ReplayError(f"Webhook already processed: {webhook_id}")
                else:
                    logger.error(
                        f"Webhook hash mismatch (possible tampering): {webhook_id}",
                        extra={"webhook_id": webhook_id, "status": "hash_mismatch"},
                    )
                    raise ReplayError(f"Webhook payload tampered: {webhook_id}")

        except redis.RedisError as e:
            logger.error(f"Error checking webhook replay: {e}")
            # Fail open: allow processing (but log)
            pass

        return False

    def mark_processed(self, webhook_id: str, payload: dict[str, Any]) -> bool:
        """
        Mark webhook as processed to prevent replays.

        Args:
            webhook_id: Unique webhook event ID
            payload: Webhook payload

        Returns:
            True if marked successfully
        """
        payload_hash = self._hash_payload(payload)
        cache_key = f"webhook_replay:{webhook_id}"

        try:
            self.redis.setex(cache_key, self.replay_ttl, payload_hash)
            logger.info(
                f"Webhook marked as processed: {webhook_id}",
                extra={"webhook_id": webhook_id},
            )
            return True
        except redis.RedisError as e:
            logger.error(f"Error marking webhook processed: {e}")
            return False


# ============================================================================
# DECORATORS
# ============================================================================


def with_idempotency(ttl_hours: int = 24):
    """
    Decorator for idempotent endpoint handlers.

    Requires 'Idempotency-Key' header in request.
    Caches response and returns cached value on retries.

    Usage:
        @with_idempotency(ttl_hours=24)
        async def create_checkout_session(request: CheckoutRequest):
            ...
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(request_or_self, *args, **kwargs):
            # Extract from request/self context (framework dependent)
            # This is a generic template; integrate with FastAPI/etc as needed
            idempotency_key = getattr(request_or_self, "headers", {}).get(
                "Idempotency-Key"
            )

            if not idempotency_key:
                logger.warning("Missing Idempotency-Key header")
                return await func(request_or_self, *args, **kwargs)

            # Process with idempotency
            redis_client = kwargs.get("redis_client") or getattr(
                request_or_self, "redis", None
            )
            if not redis_client:
                logger.warning("No Redis client available for idempotency")
                return await func(request_or_self, *args, **kwargs)

            handler = IdempotencyHandler(redis_client, ttl_seconds=ttl_hours * 3600)
            return await handler.process_idempotent(
                idempotency_key, func, request_or_self, *args, **kwargs
            )

        return wrapper

    return decorator


def with_replay_protection(replay_ttl_seconds: int = 600):
    """
    Decorator for webhook handlers with replay protection.

    Requires 'X-Webhook-ID' and 'X-Webhook-Signature' headers.
    Rejects replayed webhooks within time window.

    Usage:
        @with_replay_protection(replay_ttl_seconds=600)
        async def handle_stripe_webhook(request: StripeWebhookRequest):
            ...
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(request_or_self, *args, **kwargs):
            webhook_id = getattr(request_or_self, "headers", {}).get("X-Webhook-ID")
            if not webhook_id:
                logger.warning("Missing X-Webhook-ID header")
                raise ReplayError("Missing webhook ID")

            # Get payload
            payload = (
                getattr(request_or_self, "json", lambda: {})()
                if callable(getattr(request_or_self, "json", None))
                else kwargs.get("payload", {})
            )

            # Check replay
            redis_client = kwargs.get("redis_client") or getattr(
                request_or_self, "redis", None
            )
            if redis_client:
                protector = ReplayProtector(redis_client, replay_ttl_seconds)
                is_replay = protector.check_replay(webhook_id, payload)

                if is_replay:
                    raise ReplayError(f"Webhook replayed: {webhook_id}")

            # Process
            result = await func(request_or_self, *args, **kwargs)

            # Mark as processed
            if redis_client:
                protector.mark_processed(webhook_id, payload)

            return result

        return wrapper

    return decorator


# ============================================================================
# SETTINGS
# ============================================================================


class IdempotencySettings:
    """Configuration for idempotency & replay protection."""

    IDEMPOTENCY_KEY_TTL_HOURS: int = 24
    WEBHOOK_REPLAY_TTL_SECONDS: int = 600  # 10 minutes
    MAX_RETRY_ATTEMPTS: int = 3
    RETRY_BACKOFF_SECONDS: int = 5

    def __init__(
        self,
        key_ttl_hours: int = 24,
        replay_ttl_seconds: int = 600,
        max_retries: int = 3,
        backoff_seconds: int = 5,
    ):
        self.IDEMPOTENCY_KEY_TTL_HOURS = key_ttl_hours
        self.WEBHOOK_REPLAY_TTL_SECONDS = replay_ttl_seconds
        self.MAX_RETRY_ATTEMPTS = max_retries
        self.RETRY_BACKOFF_SECONDS = backoff_seconds


# ============================================================================
# UTILITIES
# ============================================================================


def generate_idempotency_key(user_id: str, action: str, unique_id: str) -> str:
    """
    Generate deterministic idempotency key.

    Args:
        user_id: User identifier
        action: Action type (checkout, refund, etc)
        unique_id: Unique identifier (signal_id, order_id, etc)

    Returns:
        Idempotency key string
    """
    key_source = f"{user_id}:{action}:{unique_id}"
    return hashlib.sha256(key_source.encode()).hexdigest()[:32]


async def verify_stripe_signature(
    payload: str,
    signature: str,
    webhook_secret: str,
) -> bool:
    """
    Verify Stripe webhook signature.

    Args:
        payload: Raw request body string
        signature: X-Stripe-Signature header value
        webhook_secret: Stripe webhook secret from settings

    Returns:
        True if signature valid

    Raises:
        ValueError: If signature invalid
    """
    try:
        # Parse timestamp and signatures from header
        # Format: t=timestamp,v1=signature1,v1=signature2,...
        timestamp = None
        signatures = []

        for pair in signature.split(","):
            if pair.startswith("t="):
                timestamp = int(pair[2:])
            elif pair.startswith("v1="):
                signatures.append(pair[3:])

        if not timestamp or not signatures:
            raise ValueError("Missing timestamp or signature in header")

        # Check timestamp within 5 minutes
        current_time = int(datetime.utcnow().timestamp())
        if abs(current_time - timestamp) > 300:  # 5 minutes
            raise ValueError("Signature timestamp outside acceptable window")

        # Verify signature
        signed_content = f"{timestamp}.{payload}"
        expected_sig = hmac.new(
            webhook_secret.encode(),
            signed_content.encode(),
            hashlib.sha256,
        ).hexdigest()

        if not any(hmac.compare_digest(expected_sig, sig) for sig in signatures):
            raise ValueError("Signature mismatch")

        logger.info("Stripe signature verified")
        return True

    except Exception as e:
        logger.error(f"Stripe signature verification failed: {e}")
        raise ValueError(f"Signature verification failed: {str(e)}")


# ============================================================================
# GENERIC IDEMPOTENCY STORAGE (PR-110)
# ============================================================================


class IdempotencyStorage:
    """Abstract base class for idempotency storage backends."""

    async def get(self, key: str) -> dict[str, Any] | None:
        """Retrieve cached response."""
        raise NotImplementedError

    async def set(self, key: str, response: dict[str, Any], ttl: int) -> bool:
        """Cache response."""
        raise NotImplementedError

    async def lock(self, key: str, ttl: int) -> bool:
        """Acquire processing lock for key."""
        raise NotImplementedError

    async def unlock(self, key: str) -> bool:
        """Release processing lock."""
        raise NotImplementedError


class RedisIdempotencyStorage(IdempotencyStorage):
    """Redis implementation of idempotency storage."""

    def __init__(self, redis_client: Any):
        self.redis = redis_client

    async def get(self, key: str) -> dict[str, Any] | None:
        try:
            cached = await self.redis.get(f"idempotency:response:{key}")
            if cached:
                return dict(json.loads(cached))
        except Exception as e:
            logger.error(f"Redis get error: {e}")
        return None

    async def set(self, key: str, response: dict[str, Any], ttl: int) -> bool:
        try:
            await self.redis.setex(
                f"idempotency:response:{key}", ttl, json.dumps(response)
            )
            return True
        except Exception as e:
            logger.error(f"Redis set error: {e}")
            return False

    async def lock(self, key: str, ttl: int) -> bool:
        """
        Acquire a lock to prevent concurrent processing of the same key.
        Returns True if lock acquired, False if already locked.
        """
        try:
            # NX=True (Only set if not exists)
            result = await self.redis.set(
                f"idempotency:lock:{key}", "locked", ex=ttl, nx=True
            )
            return bool(result)
        except Exception as e:
            logger.error(f"Redis lock error: {e}")
            return False

    async def unlock(self, key: str) -> bool:
        try:
            await self.redis.delete(f"idempotency:lock:{key}")
            return True
        except Exception as e:
            logger.error(f"Redis unlock error: {e}")
            return False
