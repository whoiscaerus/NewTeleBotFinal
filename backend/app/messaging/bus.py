"""Messaging Bus: Redis/Celery queue facade with priority lanes.

This module provides a centralized message queue for all outbound notifications:
- Transactional lane: Alerts, position failures, execution failures (URGENT)
- Campaign lane: Marketing, education, non-urgent (BATCHED)

Architecture:
    Feature → enqueue_message() → Redis queue → Celery worker → Sender → Channel

Integration points:
- PR-059 (User Preferences): Filter by enabled channels/instruments before enqueueing
- PR-104 (Position Tracking): Send position failure alerts via transactional lane
- PR-044 (Price Alerts): Send price alert notifications via transactional lane

Example:
    # Enqueue transactional message (immediate delivery)
    message_id = await enqueue_message(
        user_id="user-uuid",
        channel="telegram",
        template_name="position_failure_entry",
        template_vars={"instrument": "GOLD", "side": "buy", ...},
        priority="transactional"
    )

    # Enqueue campaign messages in batches
    result = await enqueue_campaign(
        user_ids=["user1", "user2", ...],
        channel="email",
        template_name="daily_outlook",
        template_vars_fn=lambda user_id: {"user_name": get_name(user_id)},
        batch_size=100
    )
"""

import asyncio
import json
import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Literal, cast

import redis.asyncio as aioredis

from backend.app.core.settings import get_settings
from backend.app.observability.metrics import (
    message_fail_total,
    messages_enqueued_total,
)

UTC = UTC

logger = logging.getLogger(__name__)
settings = get_settings()

# Redis queue names
TRANSACTIONAL_QUEUE = "messaging:queue:transactional"
CAMPAIGN_QUEUE = "messaging:queue:campaign"
DEAD_LETTER_QUEUE = "messaging:queue:dlq"

# Retry configuration
MAX_RETRIES = 5
RETRY_DELAYS = [1, 2, 4, 8, 16]  # Exponential backoff (seconds)

# Priority type
PriorityType = Literal["transactional", "campaign"]
ChannelType = Literal["email", "telegram", "push"]


class MessagingBus:
    """Redis-backed message queue with priority lanes and retry logic.

    Features:
    - Priority lanes: Transactional (immediate) vs Campaign (batched)
    - Retry logic: Exponential backoff with configurable delays
    - Dead letter queue: After MAX_RETRIES failures, message moved to DLQ
    - Metrics: messages_enqueued_total, message_fail_total, etc.
    """

    def __init__(self):
        """Initialize messaging bus (requires Redis)."""
        self.redis_client: aioredis.Redis | None = None
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize Redis connection.

        Raises:
            RuntimeError: If Redis not enabled in settings
        """
        if not settings.redis.enabled:
            logger.warning("Redis disabled - messaging bus inactive")
            self._initialized = False
            return

        try:
            self.redis_client = aioredis.from_url(
                settings.redis.url, decode_responses=True
            )
            await self.redis_client.ping()
            self._initialized = True
            logger.info("Messaging bus initialized")
        except Exception as e:
            logger.error(f"Failed to initialize messaging bus: {e}", exc_info=True)
            self._initialized = False
            raise RuntimeError(f"Messaging bus initialization failed: {e}") from e

    async def close(self) -> None:
        """Close Redis connection."""
        if self.redis_client:
            await self.redis_client.close()
            logger.info("Messaging bus closed")

    async def enqueue_message(
        self,
        user_id: str,
        channel: ChannelType,
        template_name: str,
        template_vars: dict[str, Any],
        priority: PriorityType = "transactional",
        retry_count: int = 0,
    ) -> str:
        """Enqueue message to Redis queue.

        Args:
            user_id: User ID to send message to
            channel: Delivery channel (email, telegram, push)
            template_name: Template name (e.g., "position_failure_entry")
            template_vars: Template variables (e.g., {"instrument": "GOLD"})
            priority: Priority lane (transactional=immediate, campaign=batched)
            retry_count: Current retry count (internal use)

        Returns:
            str: Message ID for tracking

        Raises:
            RuntimeError: If messaging bus not initialized
            ValueError: If channel or priority invalid

        Example:
            message_id = await bus.enqueue_message(
                user_id="user-uuid",
                channel="telegram",
                template_name="position_failure_entry",
                template_vars={"instrument": "GOLD", "side": "buy", "entry_price": 1950.50},
                priority="transactional"
            )
        """
        if not self._initialized or self.redis_client is None:
            raise RuntimeError(
                "Messaging bus not initialized - call initialize() first"
            )

        # Validate inputs
        if channel not in ("email", "telegram", "push"):
            raise ValueError(f"Invalid channel: {channel}")
        if priority not in ("transactional", "campaign"):
            raise ValueError(f"Invalid priority: {priority}")

        # Generate message ID
        message_id = str(uuid.uuid4())

        # Create message payload
        message = {
            "message_id": message_id,
            "user_id": user_id,
            "channel": channel,
            "template_name": template_name,
            "template_vars": template_vars,
            "priority": priority,
            "retry_count": retry_count,
            "enqueued_at": datetime.now(UTC).isoformat(),
        }

        # Serialize to JSON
        message_json = json.dumps(message)

        # Select queue based on priority
        queue_name = (
            TRANSACTIONAL_QUEUE if priority == "transactional" else CAMPAIGN_QUEUE
        )

        try:
            # Add to Redis list (RPUSH = append to tail, LPOP = pop from head = FIFO)
            await self.redis_client.rpush(queue_name, message_json)

            # Track metrics
            messages_enqueued_total.labels(priority=priority, channel=channel).inc()

            logger.info(
                f"Message enqueued: {message_id}",
                extra={
                    "message_id": message_id,
                    "user_id": user_id,
                    "channel": channel,
                    "template_name": template_name,
                    "priority": priority,
                    "queue": queue_name,
                },
            )

            return message_id

        except Exception as e:
            logger.error(
                f"Failed to enqueue message: {e}",
                exc_info=True,
                extra={
                    "user_id": user_id,
                    "channel": channel,
                    "template_name": template_name,
                    "priority": priority,
                },
            )
            message_fail_total.labels(reason="enqueue_error", channel=channel).inc()
            raise

    async def enqueue_campaign(
        self,
        user_ids: list[str],
        channel: ChannelType,
        template_name: str,
        template_vars_fn: Callable[[str], dict[str, Any]],
        batch_size: int = 100,
    ) -> dict[str, int]:
        """Enqueue campaign messages in batches.

        Args:
            user_ids: List of user IDs to send message to
            channel: Delivery channel (email, telegram, push)
            template_name: Template name (e.g., "daily_outlook")
            template_vars_fn: Function to get template vars for each user
            batch_size: Number of messages to enqueue in each batch

        Returns:
            dict: {"queued": 1234, "failed": 5}

        Example:
            result = await bus.enqueue_campaign(
                user_ids=["user1", "user2", ...],
                channel="email",
                template_name="daily_outlook",
                template_vars_fn=lambda user_id: {"user_name": get_name(user_id)},
                batch_size=100
            )
        """
        if not self._initialized or self.redis_client is None:
            raise RuntimeError(
                "Messaging bus not initialized - call initialize() first"
            )

        queued = 0
        failed = 0

        # Process in batches to avoid overwhelming Redis
        for i in range(0, len(user_ids), batch_size):
            batch = user_ids[i : i + batch_size]

            # Enqueue each message in batch
            tasks = []
            for user_id in batch:
                try:
                    # Get template vars for this user
                    template_vars = template_vars_fn(user_id)

                    # Enqueue with campaign priority
                    task = self.enqueue_message(
                        user_id=user_id,
                        channel=channel,
                        template_name=template_name,
                        template_vars=template_vars,
                        priority="campaign",
                    )
                    tasks.append(task)

                except Exception as e:
                    logger.error(
                        f"Failed to prepare campaign message for user {user_id}: {e}",
                        exc_info=True,
                    )
                    failed += 1

            # Execute batch concurrently
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Count successes/failures
            for result in results:
                if isinstance(result, Exception):
                    failed += 1
                else:
                    queued += 1

            # Brief pause between batches to avoid overwhelming Redis
            if i + batch_size < len(user_ids):
                await asyncio.sleep(0.1)

        logger.info(
            f"Campaign enqueued: {queued} queued, {failed} failed",
            extra={
                "channel": channel,
                "template_name": template_name,
                "total_users": len(user_ids),
                "queued": queued,
                "failed": failed,
            },
        )

        return {"queued": queued, "failed": failed}

    async def dequeue_message(
        self, priority: PriorityType = "transactional"
    ) -> dict[str, Any] | None:
        """Dequeue message from Redis queue (INTERNAL USE - called by Celery worker).

        Args:
            priority: Priority lane to dequeue from

        Returns:
            dict: Message payload or None if queue empty

        Example:
            message = await bus.dequeue_message(priority="transactional")
            if message:
                # Process message
                await send_message(message)
        """
        if not self._initialized or self.redis_client is None:
            raise RuntimeError("Messaging bus not initialized")

        queue_name = (
            TRANSACTIONAL_QUEUE if priority == "transactional" else CAMPAIGN_QUEUE
        )

        try:
            # LPOP = pop from head (FIFO)
            message_json = await self.redis_client.lpop(queue_name)

            if not message_json:
                return None

            # Deserialize
            message = json.loads(message_json)

            logger.debug(
                f"Message dequeued: {message['message_id']}",
                extra={"message_id": message["message_id"], "queue": queue_name},
            )

            return cast(dict[str, Any], message)

        except Exception as e:
            logger.error(f"Failed to dequeue message: {e}", exc_info=True)
            return None

    async def retry_message(self, message: dict[str, Any]) -> None:
        """Retry failed message with exponential backoff.

        Args:
            message: Message payload from dequeue_message()

        Behavior:
            - If retry_count < MAX_RETRIES: Re-enqueue with incremented retry_count
            - If retry_count >= MAX_RETRIES: Move to dead letter queue (DLQ)

        Example:
            message = await bus.dequeue_message()
            try:
                await send_message(message)
            except Exception:
                await bus.retry_message(message)
        """
        if not self._initialized or self.redis_client is None:
            raise RuntimeError("Messaging bus not initialized")

        retry_count = message.get("retry_count", 0)

        if retry_count >= MAX_RETRIES:
            # Max retries exceeded - move to DLQ
            await self._move_to_dlq(message, reason="max_retries_exceeded")
            logger.warning(
                f"Message moved to DLQ (max retries): {message['message_id']}",
                extra={
                    "message_id": message["message_id"],
                    "retry_count": retry_count,
                    "user_id": message["user_id"],
                    "channel": message["channel"],
                },
            )
            message_fail_total.labels(
                reason="max_retries", channel=message["channel"]
            ).inc()
            return

        # Calculate delay (exponential backoff)
        delay_seconds = RETRY_DELAYS[min(retry_count, len(RETRY_DELAYS) - 1)]

        logger.info(
            f"Retrying message: {message['message_id']} (attempt {retry_count + 1}/{MAX_RETRIES})",
            extra={
                "message_id": message["message_id"],
                "retry_count": retry_count + 1,
                "delay_seconds": delay_seconds,
            },
        )

        # Wait for delay
        await asyncio.sleep(delay_seconds)

        # Re-enqueue with incremented retry count
        await self.enqueue_message(
            user_id=message["user_id"],
            channel=message["channel"],
            template_name=message["template_name"],
            template_vars=message["template_vars"],
            priority=message["priority"],
            retry_count=retry_count + 1,
        )

    async def _move_to_dlq(self, message: dict[str, Any], reason: str) -> None:
        """Move message to dead letter queue (INTERNAL USE).

        Args:
            message: Message payload
            reason: Reason for DLQ (e.g., "max_retries_exceeded", "invalid_template")
        """
        if not self.redis_client:
            return

        # Add metadata
        dlq_message = {
            **message,
            "dlq_reason": reason,
            "dlq_timestamp": datetime.now(UTC).isoformat(),
        }

        # Serialize to JSON
        message_json = json.dumps(dlq_message)

        try:
            # Add to DLQ
            await self.redis_client.rpush(DEAD_LETTER_QUEUE, message_json)

            logger.error(
                f"Message moved to DLQ: {message['message_id']}",
                extra={
                    "message_id": message["message_id"],
                    "dlq_reason": reason,
                    "user_id": message["user_id"],
                    "channel": message["channel"],
                },
            )

        except Exception as e:
            logger.error(f"Failed to move message to DLQ: {e}", exc_info=True)

    async def get_queue_size(self, priority: PriorityType = "transactional") -> int:
        """Get current queue size (UTILITY METHOD).

        Args:
            priority: Priority lane to check

        Returns:
            int: Number of messages in queue
        """
        if not self._initialized or self.redis_client is None:
            return 0

        queue_name = (
            TRANSACTIONAL_QUEUE if priority == "transactional" else CAMPAIGN_QUEUE
        )

        try:
            size = await self.redis_client.llen(queue_name)
            return size

        except Exception as e:
            logger.error(f"Failed to get queue size: {e}", exc_info=True)
            return 0

    async def get_dlq_size(self) -> int:
        """Get dead letter queue size (UTILITY METHOD).

        Returns:
            int: Number of messages in DLQ
        """
        if not self._initialized or self.redis_client is None:
            return 0

        try:
            size = await self.redis_client.llen(DEAD_LETTER_QUEUE)
            return size

        except Exception as e:
            logger.error(f"Failed to get DLQ size: {e}", exc_info=True)
            return 0


# Global singleton instance
_bus = MessagingBus()


async def get_messaging_bus() -> MessagingBus:
    """Get global messaging bus instance (dependency injection).

    Example:
        bus = await get_messaging_bus()
        await bus.enqueue_message(...)
    """
    if not _bus._initialized:
        await _bus.initialize()
    return _bus


async def enqueue_message(
    user_id: str,
    channel: ChannelType,
    template_name: str,
    template_vars: dict[str, Any],
    priority: PriorityType = "transactional",
) -> str:
    """Convenience function to enqueue message (uses global singleton).

    Example:
        message_id = await enqueue_message(
            user_id="user-uuid",
            channel="telegram",
            template_name="position_failure_entry",
            template_vars={"instrument": "GOLD"},
        )
    """
    bus = await get_messaging_bus()
    return await bus.enqueue_message(
        user_id, channel, template_name, template_vars, priority
    )


async def enqueue_campaign(
    user_ids: list[str],
    channel: ChannelType,
    template_name: str,
    template_vars_fn: Callable[[str], dict[str, Any]],
    batch_size: int = 100,
) -> dict[str, int]:
    """Convenience function to enqueue campaign (uses global singleton).

    Example:
        result = await enqueue_campaign(
            user_ids=["user1", "user2"],
            channel="email",
            template_name="daily_outlook",
            template_vars_fn=lambda user_id: {"name": get_name(user_id)},
        )
    """
    bus = await get_messaging_bus()
    return await bus.enqueue_campaign(
        user_ids, channel, template_name, template_vars_fn, batch_size
    )
