"""PR-040: Payment Security Hardening.

Implements webhook signature verification, replay attack prevention, and
idempotency for payment webhooks. Prevents duplicate webhook processing.
"""

import hashlib
import hmac
import logging
import time
from typing import Any

import redis

from backend.app.observability.metrics import metrics

logger = logging.getLogger(__name__)

# Webhook signature TTL (600 seconds = 10 minutes)
WEBHOOK_REPLAY_TTL_SECONDS = 600

# Redis keys
WEBHOOK_IDEMPOTENCY_KEY_PREFIX = "webhook:idempotency:"
WEBHOOK_REPLAY_CACHE_PREFIX = "webhook:replay:"


class WebhookReplayProtection:
    """Prevents replay attacks on webhook endpoints.

    Validates:
    - Signature matches webhook secret
    - Timestamp is within TTL window (600 seconds)
    - Signature hasn't been seen before (idempotency)
    """

    def __init__(self, redis_client: redis.Redis):
        """Initialize with Redis client."""
        self.redis = redis_client

    def verify_stripe_signature(
        self,
        payload: bytes,
        signature: str,
        webhook_secret: str,
    ) -> bool:
        """Verify Stripe webhook signature.

        Args:
            payload: Raw webhook payload bytes
            signature: Signature header from Stripe (t=timestamp,v1=hash)
            webhook_secret: Stripe webhook secret

        Returns:
            True if signature is valid, False otherwise

        Raises:
            ValueError: If signature format invalid
        """
        try:
            # Parse signature header: "t=1677836800,v1=hash1,v1=hash2"
            parts = signature.split(",")
            timestamp = None
            signatures = []

            for part in parts:
                if part.startswith("t="):
                    timestamp = int(part[2:])
                elif part.startswith("v1="):
                    signatures.append(part[3:])

            if timestamp is None or not signatures:
                logger.warning("Invalid signature format: missing t or v1")
                metrics.record_billing_webhook_invalid_sig()
                return False

            # Check timestamp freshness (prevent replay attacks)
            now = time.time()
            age_seconds = int(now - timestamp)

            if age_seconds > WEBHOOK_REPLAY_TTL_SECONDS:
                logger.warning(
                    f"Webhook timestamp too old: {age_seconds}s > {WEBHOOK_REPLAY_TTL_SECONDS}s"
                )
                metrics.record_billing_webhook_invalid_sig()
                return False

            if age_seconds < -300:  # Allow 5 min clock skew
                logger.warning(f"Webhook timestamp in future: {age_seconds}s")
                metrics.record_billing_webhook_invalid_sig()
                return False

            # Compute expected signature
            signed_content = f"{timestamp}.{payload.decode('utf-8')}"
            expected = hmac.new(
                webhook_secret.encode("utf-8"),
                signed_content.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()

            # Compare signatures (constant time)
            for sig in signatures:
                if hmac.compare_digest(sig, expected):
                    logger.info("Webhook signature verified")
                    return True

            logger.warning("Webhook signature mismatch")
            metrics.record_billing_webhook_invalid_sig()
            return False

        except Exception as e:
            logger.error(f"Error verifying webhook signature: {e}", exc_info=True)
            metrics.record_billing_webhook_invalid_sig()
            return False

    def check_replay_cache(self, event_id: str) -> bool:
        """Check if this event has already been processed (idempotency).

        Args:
            event_id: Unique event ID from Stripe (e.g., "evt_123456")

        Returns:
            True if event is NEW (not seen before), False if DUPLICATE
        """
        cache_key = f"{WEBHOOK_REPLAY_CACHE_PREFIX}{event_id}"

        try:
            # Check if key exists (SETNX = SET if Not eXists)
            is_new = self.redis.set(
                cache_key,
                "1",
                ex=WEBHOOK_REPLAY_TTL_SECONDS,  # Expire after TTL
                nx=True,  # Only set if doesn't exist
            )

            if is_new:
                logger.info(f"New webhook event: {event_id}")
                return True
            else:
                logger.warning(f"Duplicate webhook event: {event_id}")
                metrics.record_billing_webhook_replay_block()
                return False

        except Exception as e:
            logger.error(f"Error checking replay cache: {e}", exc_info=True)
            # If Redis fails, allow event (fail-open, log for monitoring)
            return True

    def mark_idempotent_result(self, event_id: str, result: dict[str, Any]) -> None:
        """Store idempotent result for replayed requests.

        Args:
            event_id: Webhook event ID
            result: Result dict from processing
        """
        import json

        cache_key = f"{WEBHOOK_IDEMPOTENCY_KEY_PREFIX}{event_id}"

        try:
            self.redis.setex(
                cache_key,
                WEBHOOK_REPLAY_TTL_SECONDS,
                json.dumps(result),
            )
            logger.info(f"Stored idempotent result for {event_id}")
        except Exception as e:
            logger.error(f"Error storing idempotent result: {e}", exc_info=True)

    def get_idempotent_result(self, event_id: str) -> dict[str, Any] | None:
        """Retrieve previously computed result for replayed request.

        Args:
            event_id: Webhook event ID

        Returns:
            Result dict if found, None otherwise
        """
        import json
        from typing import cast

        cache_key = f"{WEBHOOK_IDEMPOTENCY_KEY_PREFIX}{event_id}"

        try:
            result = self.redis.get(cache_key)
            if result:
                logger.info(f"Returning cached result for {event_id}")
                cached_str = cast(str | bytes | bytearray, result)
                return cast(dict[str, Any], json.loads(cached_str))
            return None
        except Exception as e:
            logger.error(f"Error retrieving idempotent result: {e}", exc_info=True)
            return None


class WebhookSecurityValidator:
    """Multi-layer webhook validation."""

    def __init__(self, redis_client: redis.Redis, webhook_secret: str):
        """Initialize validator.

        Args:
            redis_client: Redis instance for caching
            webhook_secret: Stripe webhook secret
        """
        self.replay_protection = WebhookReplayProtection(redis_client)
        self.webhook_secret = webhook_secret

    def validate_webhook(
        self,
        payload: bytes,
        signature: str,
        event_id: str,
    ) -> tuple[bool, dict[str, Any] | None]:
        """Comprehensive webhook validation.

        Args:
            payload: Raw webhook payload
            signature: Signature header from Stripe
            event_id: Event ID from webhook

        Returns:
            (is_valid, cached_result)
            - is_valid: True if webhook should be processed
            - cached_result: Previous result if replayed event, None if new
        """
        # Layer 1: Signature verification
        if not self.replay_protection.verify_stripe_signature(
            payload,
            signature,
            self.webhook_secret,
        ):
            logger.error(f"Invalid webhook signature for {event_id}")
            return False, None

        # Layer 2: Replay protection + idempotency
        if not self.replay_protection.check_replay_cache(event_id):
            # Event was already processed, return cached result
            cached = self.replay_protection.get_idempotent_result(event_id)
            logger.info("Replayed webhook detected, returning cached result")
            return True, cached

        # Layer 3: Event is new and valid
        logger.info(f"Webhook validation passed: {event_id}")
        return True, None
