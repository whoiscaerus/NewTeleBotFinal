"""Test helpers for messaging bus - provides backward-compatible API for tests."""

from backend.app.messaging.bus import (
    CAMPAIGN_QUEUE,
    DEAD_LETTER_QUEUE,
    MAX_RETRIES,
    RETRY_DELAYS,
    TRANSACTIONAL_QUEUE,
    MessagingBus,
)
from backend.app.messaging.bus import enqueue_campaign as _enqueue_campaign
from backend.app.messaging.bus import enqueue_message as _enqueue_message
from backend.app.messaging.bus import get_messaging_bus


async def get_bus() -> MessagingBus:
    """Get messaging bus instance (backward compatible with tests)."""
    # Always get fresh instance from bus.py (respects fixture reset)
    return await get_messaging_bus()


async def dequeue_message(priority="transactional"):
    """Dequeue message from bus (backward compatible wrapper)."""
    bus = await get_bus()
    return await bus.dequeue_message(priority=priority)


async def retry_message(message: dict):
    """Retry message (backward compatible wrapper)."""
    bus = await get_bus()
    return await bus.retry_message(message)


# Re-export module-level functions
enqueue_message = _enqueue_message
enqueue_campaign = _enqueue_campaign

# Re-export constants
__all__ = [
    "CAMPAIGN_QUEUE",
    "DEAD_LETTER_QUEUE",
    "MAX_RETRIES",
    "RETRY_DELAYS",
    "TRANSACTIONAL_QUEUE",
    "MessagingBus",
    "get_bus",
    "enqueue_message",
    "enqueue_campaign",
    "dequeue_message",
    "retry_message",
    "get_messaging_bus",
]
