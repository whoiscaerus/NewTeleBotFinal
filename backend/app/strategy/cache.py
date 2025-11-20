"""Persistent cache for duplicate prevention using Redis.

Provides Redis-backed caching for candle detection and signal publishing
to enable duplicate prevention across process restarts and distributed deployments.

Features:
    - Redis-backed cache with TTL (time-to-live)
    - Fallback to in-memory cache if Redis unavailable
    - Automatic cleanup of expired entries
    - Support for distributed systems (multiple processes)

Example:
    >>> from backend.app.strategy.cache import get_candle_cache
    >>>
    >>> cache = await get_candle_cache()
    >>> key = "GOLD_15m_2025-01-01T10:15:00"
    >>> if await cache.get(key) is None:
    ...     await cache.set(key, "processed", ttl=3600)  # 1 hour TTL
"""

import json
import logging
from datetime import datetime
from typing import Any

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


class CandleCache:
    """Persistent cache for candle processing status.

    Supports both Redis (distributed) and in-memory (fallback) backends.
    """

    def __init__(self, redis_client: aioredis.Redis | None = None):
        """Initialize candle cache.

        Args:
            redis_client: Optional Redis client (uses in-memory if None)
        """
        self.redis_client = redis_client
        self._in_memory_cache: dict[str, tuple[Any, float]] = {}  # value, expiry_time
        self._use_redis = redis_client is not None

    async def get(self, key: str) -> Any | None:
        """Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found or expired

        Example:
            >>> cache = CandleCache()
            >>> value = await cache.get("GOLD_15m_2025-01-01T10:15:00")
        """
        try:
            if self._use_redis and self.redis_client is not None:
                value = await self.redis_client.get(key)
                if value:
                    return json.loads(value)
                return None
            else:
                # In-memory cache
                if key in self._in_memory_cache:
                    value, expiry_time = self._in_memory_cache[key]
                    if datetime.utcnow().timestamp() < expiry_time:
                        return value
                    else:
                        # Expired, remove it
                        del self._in_memory_cache[key]
                        return None
                return None

        except Exception as e:
            logger.error(f"Failed to get cache key {key}: {e}", exc_info=True)
            return None

    async def set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        """Set value in cache with TTL.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (default: 1 hour)

        Returns:
            True if successful, False otherwise

        Example:
            >>> cache = CandleCache()
            >>> success = await cache.set("GOLD_15m_2025-01-01T10:15:00", "processed", ttl=3600)
        """
        try:
            if self._use_redis and self.redis_client is not None:
                json_value = json.dumps(value) if not isinstance(value, str) else value
                await self.redis_client.setex(key, ttl, json_value)
                return True
            else:
                # In-memory cache
                expiry_time = datetime.utcnow().timestamp() + ttl
                self._in_memory_cache[key] = (value, expiry_time)
                return True

        except Exception as e:
            logger.error(f"Failed to set cache key {key}: {e}", exc_info=True)
            return False

    async def delete(self, key: str) -> bool:
        """Delete key from cache.

        Args:
            key: Cache key

        Returns:
            True if successful, False otherwise
        """
        try:
            if self._use_redis and self.redis_client is not None:
                await self.redis_client.delete(key)
                return True
            else:
                if key in self._in_memory_cache:
                    del self._in_memory_cache[key]
                return True

        except Exception as e:
            logger.error(f"Failed to delete cache key {key}: {e}", exc_info=True)
            return False

    async def exists(self, key: str) -> bool:
        """Check if key exists and is not expired.

        Args:
            key: Cache key

        Returns:
            True if key exists and is not expired, False otherwise

        Example:
            >>> cache = CandleCache()
            >>> if await cache.exists("GOLD_15m_2025-01-01T10:15:00"):
            ...     # Already processed this candle
            ...     pass
        """
        value = await self.get(key)
        return value is not None

    async def clear(self) -> bool:
        """Clear all cache entries.

        Returns:
            True if successful, False otherwise
        """
        try:
            if self._use_redis and self.redis_client is not None:
                # Delete all keys matching pattern
                pattern = "candle:*"
                async for key in self.redis_client.scan_iter(match=pattern):
                    await self.redis_client.delete(key)
                return True
            else:
                self._in_memory_cache.clear()
                return True

        except Exception as e:
            logger.error(f"Failed to clear cache: {e}", exc_info=True)
            return False

    def close(self) -> None:
        """Close cache connection (if Redis)."""
        if self._use_redis and self.redis_client:
            # Redis client will be closed by context manager
            pass


class SignalPublishCache:
    """Persistent cache for signal publishing status.

    Tracks which signals have been published to prevent duplicates
    across process restarts and distributed deployments.
    """

    def __init__(self, redis_client: aioredis.Redis | None = None):
        """Initialize signal publish cache.

        Args:
            redis_client: Optional Redis client (uses in-memory if None)
        """
        self.redis_client = redis_client
        self._in_memory_cache: dict[str, tuple[str, float]] = (
            {}
        )  # signal_id, expiry_time
        self._use_redis = redis_client is not None

    def _make_key(self, instrument: str, candle_start: datetime) -> str:
        """Create cache key from instrument and candle start.

        Args:
            instrument: Trading instrument (e.g., "GOLD", "EURUSD")
            candle_start: Candle start timestamp

        Returns:
            Cache key string
        """
        return f"signal:publish:{instrument}:{candle_start.isoformat()}"

    async def mark_published(
        self,
        instrument: str,
        candle_start: datetime,
        signal_id: str,
        ttl: int = 86400,
    ) -> bool:
        """Mark signal as published.

        Args:
            instrument: Trading instrument
            candle_start: Candle start timestamp
            signal_id: Signal ID returned from API
            ttl: Time-to-live in seconds (default: 24 hours)

        Returns:
            True if successful, False otherwise

        Example:
            >>> cache = SignalPublishCache()
            >>> success = await cache.mark_published("GOLD", candle_start, "sig-123")
        """
        key = self._make_key(instrument, candle_start)
        try:
            if self._use_redis and self.redis_client is not None:
                await self.redis_client.setex(key, ttl, signal_id)
                return True
            else:
                expiry_time = datetime.utcnow().timestamp() + ttl
                self._in_memory_cache[key] = (signal_id, expiry_time)
                return True

        except Exception as e:
            logger.error(f"Failed to mark signal published: {key}: {e}", exc_info=True)
            return False

    async def was_published(self, instrument: str, candle_start: datetime) -> bool:
        """Check if signal was already published for this candle.

        Args:
            instrument: Trading instrument
            candle_start: Candle start timestamp

        Returns:
            True if already published, False otherwise

        Example:
            >>> cache = SignalPublishCache()
            >>> if await cache.was_published("GOLD", candle_start):
            ...     # Signal already published for this candle
            ...     return None  # Skip
        """
        key = self._make_key(instrument, candle_start)
        try:
            if self._use_redis and self.redis_client is not None:
                value = await self.redis_client.get(key)
                return value is not None
            else:
                # In-memory cache
                if key in self._in_memory_cache:
                    signal_id, expiry_time = self._in_memory_cache[key]
                    if datetime.utcnow().timestamp() < expiry_time:
                        return True
                    else:
                        # Expired, remove it
                        del self._in_memory_cache[key]
                        return False
                return False

        except Exception as e:
            logger.error(
                f"Failed to check signal published status: {key}: {e}", exc_info=True
            )
            return False

    async def get_signal_id(
        self, instrument: str, candle_start: datetime
    ) -> str | None:
        """Get signal ID if already published for this candle.

        Args:
            instrument: Trading instrument
            candle_start: Candle start timestamp

        Returns:
            Signal ID if published, None otherwise
        """
        key = self._make_key(instrument, candle_start)
        try:
            if self._use_redis and self.redis_client is not None:
                value = await self.redis_client.get(key)
                return value if value else None
            else:
                # In-memory cache
                if key in self._in_memory_cache:
                    signal_id, expiry_time = self._in_memory_cache[key]
                    if datetime.utcnow().timestamp() < expiry_time:
                        return signal_id
                    else:
                        del self._in_memory_cache[key]
                        return None
                return None

        except Exception as e:
            logger.error(f"Failed to get signal ID: {key}: {e}", exc_info=True)
            return None


# Global cache instances
_candle_cache: CandleCache | None = None
_signal_publish_cache: SignalPublishCache | None = None
_redis_client: aioredis.Redis | None = None


async def initialize_caches() -> tuple[CandleCache, SignalPublishCache]:
    """Initialize Redis-backed caches.

    Returns:
        Tuple of (CandleCache, SignalPublishCache) instances

    Example:
        >>> candle_cache, signal_cache = await initialize_caches()
    """
    global _candle_cache, _signal_publish_cache, _redis_client

    try:
        # Import settings here to avoid circular imports
        from backend.app.core.settings import get_settings

        settings = get_settings()

        if settings.redis.enabled:
            # Connect to Redis
            _redis_client = await aioredis.from_url(
                settings.redis.url, decode_responses=True
            )
            if _redis_client is not None:
                await _redis_client.ping()

                logger.info(
                    "Redis caches initialized",
                    extra={"redis_url": settings.redis.url},
                )

                _candle_cache = CandleCache(redis_client=_redis_client)
                _signal_publish_cache = SignalPublishCache(redis_client=_redis_client)
            else:
                raise RuntimeError("Failed to connect to Redis")
        else:
            logger.info("Redis disabled, using in-memory caches")
            _candle_cache = CandleCache()
            _signal_publish_cache = SignalPublishCache()

    except Exception as e:
        logger.warning(
            f"Failed to initialize Redis caches, using in-memory fallback: {e}",
            exc_info=True,
        )
        _candle_cache = CandleCache()
        _signal_publish_cache = SignalPublishCache()

    return _candle_cache, _signal_publish_cache


async def get_candle_cache() -> CandleCache:
    """Get global candle cache instance.

    Returns:
        CandleCache instance (initializes if needed)
    """
    global _candle_cache

    if _candle_cache is None:
        _candle_cache, _ = await initialize_caches()

    return _candle_cache


async def get_signal_publish_cache() -> SignalPublishCache:
    """Get global signal publish cache instance.

    Returns:
        SignalPublishCache instance (initializes if needed)
    """
    global _signal_publish_cache

    if _signal_publish_cache is None:
        _, _signal_publish_cache = await initialize_caches()

    return _signal_publish_cache


async def close_caches() -> None:
    """Close cache connections."""
    global _redis_client

    if _redis_client:
        await _redis_client.close()
        logger.info("Redis caches closed")
