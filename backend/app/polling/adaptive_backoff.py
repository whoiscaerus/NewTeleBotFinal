"""
Adaptive Backoff Manager: Track poll history and calculate optimal intervals (PR-49).

Maintains poll history per device in Redis to enable adaptive polling intervals
that reduce server load during inactive periods while maintaining responsiveness
during active trading.
"""

import logging
from uuid import UUID

from redis import Redis

logger = logging.getLogger(__name__)

# Redis key format for poll history
POLL_HISTORY_KEY = "poll_history:{device_id}"
POLL_HISTORY_TTL = 3600  # 1 hour


class AdaptiveBackoffManager:
    """Manage adaptive polling intervals for devices using Redis."""

    def __init__(self, redis_client: Redis):
        """
        Initialize backoff manager.

        Args:
            redis_client: Redis client for storing poll history
        """
        self.redis = redis_client

    def record_poll(self, device_id: UUID, has_approvals: bool) -> None:
        """
        Record a poll event and update history.

        Args:
            device_id: Device ID
            has_approvals: Whether poll returned any approvals

        Example:
            >>> manager = AdaptiveBackoffManager(redis_client)
            >>> manager.record_poll(UUID('123'), False)  # No approvals
            >>> manager.record_poll(UUID('123'), False)  # Still none
            >>> manager.record_poll(UUID('123'), True)   # Got one!
        """
        key = POLL_HISTORY_KEY.format(device_id=str(device_id))

        # Get current history
        try:
            history_str = self.redis.get(key)
            history = history_str.decode("utf-8").split(",") if history_str else []
        except Exception as e:
            logger.warning(f"Failed to read poll history: {e}")
            history = []

        # Record event (0=no approvals, 1=has approvals)
        event = "1" if has_approvals else "0"
        history.append(event)

        # Keep only last 100 polls
        history = history[-100:]

        # Store updated history
        try:
            history_str = ",".join(history)
            self.redis.setex(key, POLL_HISTORY_TTL, history_str)
        except Exception as e:
            logger.error(f"Failed to store poll history: {e}")

    def get_backoff_interval(self, device_id: UUID) -> int:
        """
        Get next poll interval based on history.

        Returns:
            Poll interval in seconds (10-60)

        Strategy:
        1. If last poll had approvals: Return 10s (fast poll)
        2. Count consecutive empty polls from end of history
        3. Calculate: 10s * (empty_count + 1), capped at 60s

        Example:
            >>> manager = AdaptiveBackoffManager(redis_client)
            >>> # After empty polls
            >>> manager.record_poll(UUID('123'), False)
            >>> manager.record_poll(UUID('123'), False)
            >>> manager.record_poll(UUID('123'), False)
            >>> interval = manager.get_backoff_interval(UUID('123'))
            >>> assert interval == 40  # 10 * (3 + 1) = 40
        """
        key = POLL_HISTORY_KEY.format(device_id=str(device_id))

        try:
            history_str = self.redis.get(key)
            if not history_str:
                # No history yet, start fast
                return 10

            history = history_str.decode("utf-8").split(",")

            # Check last poll
            if history[-1] == "1":
                # Last poll had approvals, fast poll
                return 10

            # Count consecutive empty polls from end
            empty_count = 0
            for event in reversed(history):
                if event == "0":
                    empty_count += 1
                else:
                    break

            # Calculate backoff: 10 * (empty_count + 1), capped at 60
            MIN_INTERVAL = 10
            MAX_INTERVAL = 60
            backoff = min(MIN_INTERVAL * (empty_count + 1), MAX_INTERVAL)

            logger.debug(
                "Calculated backoff",
                extra={
                    "device_id": str(device_id),
                    "empty_count": empty_count,
                    "backoff": backoff,
                },
            )
            return backoff

        except Exception as e:
            logger.error(f"Failed to calculate backoff: {e}")
            return 10  # Default to fast poll on error

    def reset_history(self, device_id: UUID) -> None:
        """
        Reset poll history for a device.

        Args:
            device_id: Device ID

        Example:
            >>> manager = AdaptiveBackoffManager(redis_client)
            >>> manager.reset_history(UUID('123'))
        """
        key = POLL_HISTORY_KEY.format(device_id=str(device_id))
        try:
            self.redis.delete(key)
            logger.debug(f"Reset poll history for {device_id}")
        except Exception as e:
            logger.error(f"Failed to reset poll history: {e}")

    def get_history(self, device_id: UUID) -> list[int]:
        """
        Get poll history for a device.

        Returns:
            List of poll events (0=no approvals, 1=has approvals)

        Example:
            >>> manager = AdaptiveBackoffManager(redis_client)
            >>> history = manager.get_history(UUID('123'))
            >>> assert history == [0, 0, 1, 0]  # Last 4 polls
        """
        key = POLL_HISTORY_KEY.format(device_id=str(device_id))

        try:
            history_str = self.redis.get(key)
            if not history_str:
                return []

            history_list = history_str.decode("utf-8").split(",")
            return [int(e) for e in history_list]

        except Exception as e:
            logger.error(f"Failed to read poll history: {e}")
            return []
