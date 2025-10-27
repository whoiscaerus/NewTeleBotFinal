"""
Phase 6 Redis Caching Layer - Distributed cache for Phase 5 API endpoints

Provides decorators and utilities for caching with Redis:
- Reconciliation status (5s TTL)
- Open positions (5s TTL)
- Guard status (5s TTL)

Uses Redis for distributed caching suitable for scaling.
Complements existing in-memory cache manager.

Author: Trading System
Date: 2024-10-26
"""

import json
import logging
from collections.abc import Callable
from functools import wraps
from typing import Any, Optional, TypeVar
from uuid import UUID

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Global Redis client (initialized at app startup if available)
_redis_client: Optional[Any] = None


async def init_redis(redis_url: str) -> Optional[Any]:
    """
    Initialize Redis client for caching.

    Args:
        redis_url: Redis connection URL (e.g., "redis://localhost:6379")

    Returns:
        Redis client instance or None if connection fails
    """
    global _redis_client
    try:
        # Try to import redis - it may not be installed
        try:
            import aioredis
        except ImportError:
            logger.warning("aioredis not installed - caching disabled")
            return None

        _redis_client = await aioredis.create_redis_pool(redis_url, encoding="utf8")
        logger.info("Redis cache initialized successfully", extra={"url": redis_url})
        return _redis_client
    except Exception as e:
        logger.warning(f"Failed to initialize Redis cache: {e}")
        return None


async def close_redis():
    """Close Redis connection."""
    global _redis_client
    if _redis_client:
        try:
            _redis_client.close()
            await _redis_client.wait_closed()
            logger.info("Redis cache connection closed")
        except Exception as e:
            logger.warning(f"Error closing Redis: {e}")
        _redis_client = None


def get_redis_client() -> Optional[Any]:
    """Get global Redis client."""
    return _redis_client


def cache_key(prefix: str, *args, **kwargs) -> str:
    """
    Generate cache key from prefix and arguments.

    Args:
        prefix: Key prefix
        *args: Positional arguments
        **kwargs: Keyword arguments

    Returns:
        Cache key string
    """
    key_parts = [prefix]

    # Add string representations of args
    for arg in args:
        if isinstance(arg, UUID):
            key_parts.append(str(arg))
        elif isinstance(arg, (str, int, float, bool)):
            key_parts.append(str(arg))
        elif arg is None:
            key_parts.append("none")

    # Add sorted kwargs
    for k in sorted(kwargs.keys()):
        v = kwargs[k]
        if isinstance(v, UUID):
            key_parts.append(f"{k}:{str(v)}")
        elif isinstance(v, (str, int, float, bool)):
            key_parts.append(f"{k}:{str(v)}")
        elif v is None:
            key_parts.append(f"{k}:none")

    return ":".join(key_parts)


async def get_cached(key: str, ttl_seconds: int = 300) -> Optional[Any]:
    """
    Get value from Redis cache.

    Args:
        key: Cache key
        ttl_seconds: Unused (for consistency)

    Returns:
        Cached value or None if not found/expired
    """
    try:
        redis = get_redis_client()
        if not redis:
            return None

        value = await redis.get(key)
        if value:
            logger.debug(f"Cache hit: {key}")
            return json.loads(value)
        else:
            logger.debug(f"Cache miss: {key}")
            return None

    except Exception as e:
        logger.debug(f"Error retrieving cache key {key}: {e}")
        return None


async def set_cached(
    key: str,
    value: Any,
    ttl_seconds: int = 300,
) -> bool:
    """
    Set value in Redis cache with TTL.

    Args:
        key: Cache key
        value: Value to cache (must be JSON-serializable)
        ttl_seconds: Time to live in seconds

    Returns:
        True if successful, False otherwise
    """
    try:
        redis = get_redis_client()
        if not redis:
            return False

        json_value = json.dumps(value, default=str)
        await redis.setex(key, ttl_seconds, json_value)
        logger.debug(f"Cache set: {key} (TTL: {ttl_seconds}s)")
        return True

    except Exception as e:
        logger.debug(f"Error setting cache key {key}: {e}")
        return False


async def invalidate_cache(key: str) -> bool:
    """
    Invalidate a cache key.

    Args:
        key: Cache key to invalidate

    Returns:
        True if successful
    """
    try:
        redis = get_redis_client()
        if not redis:
            return False

        await redis.delete(key)
        logger.debug(f"Cache invalidated: {key}")
        return True

    except Exception as e:
        logger.debug(f"Error invalidating cache key {key}: {e}")
        return False


async def invalidate_pattern(pattern: str) -> int:
    """
    Invalidate all keys matching pattern.

    Args:
        pattern: Redis pattern (e.g., "reconciliation:user_123:*")

    Returns:
        Number of keys deleted
    """
    try:
        redis = get_redis_client()
        if not redis:
            return 0

        keys = await redis.keys(pattern)
        if keys:
            await redis.delete(*keys)
            logger.debug(f"Cache invalidated pattern {pattern}: {len(keys)} keys")
            return len(keys)
        return 0

    except Exception as e:
        logger.debug(f"Error invalidating cache pattern {pattern}: {e}")
        return 0


def cached(
    prefix: str,
    ttl_seconds: int = 300,
    key_builder: Optional[Callable] = None,
):
    """
    Decorator for caching async function results in Redis.

    If Redis is not available, function is called without caching.

    Args:
        prefix: Cache key prefix
        ttl_seconds: Time to live in seconds
        key_builder: Optional custom key builder function

    Returns:
        Decorated function with optional caching

    Example:
        @cached("reconciliation_status", ttl_seconds=5)
        async def get_reconciliation_status(user_id: UUID):
            # Expensive operation
            return result
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            # If Redis not available, just call function
            if not get_redis_client():
                return await func(*args, **kwargs)

            # Build cache key
            if key_builder:
                key = key_builder(*args, **kwargs)
            else:
                key = cache_key(prefix, *args, **kwargs)

            # Try to get from cache
            cached_value = await get_cached(key, ttl_seconds)
            if cached_value is not None:
                logger.debug(f"Cache hit for {key}")
                return cached_value

            # Cache miss - call function
            logger.debug(f"Cache miss for {key} - calling function")
            result = await func(*args, **kwargs)

            # Store in cache (non-blocking)
            # Don't await to keep response time fast
            try:
                await set_cached(key, result, ttl_seconds)
            except Exception as e:
                logger.debug(f"Error caching result for {key}: {e}")

            return result

        return wrapper

    return decorator


# ================================================================
# Common cache key patterns for Phase 5 endpoints
# ================================================================


def get_reconciliation_cache_key(user_id: UUID) -> str:
    """Get cache key for reconciliation status."""
    return f"reconciliation:user:{str(user_id)}:status"


def get_positions_cache_key(user_id: UUID, symbol: Optional[str] = None) -> str:
    """Get cache key for open positions."""
    symbol_part = symbol or "all"
    return f"positions:user:{str(user_id)}:{symbol_part}"


def get_guards_cache_key(user_id: UUID) -> str:
    """Get cache key for guard status."""
    return f"guards:user:{str(user_id)}:status"


def get_drawdown_cache_key(user_id: UUID) -> str:
    """Get cache key for drawdown alert."""
    return f"guards:user:{str(user_id)}:drawdown"


def get_market_alerts_cache_key(user_id: UUID) -> str:
    """Get cache key for market condition alerts."""
    return f"guards:user:{str(user_id)}:market_alerts"


# ================================================================
# Cache invalidation helpers
# ================================================================


async def invalidate_user_cache(user_id: UUID) -> int:
    """
    Invalidate all cache for a user.

    Args:
        user_id: User ID

    Returns:
        Number of cache keys invalidated
    """
    pattern = f"*:user:{str(user_id)}:*"
    return await invalidate_pattern(pattern)


async def invalidate_reconciliation_cache(user_id: UUID) -> bool:
    """Invalidate reconciliation cache for user."""
    key = get_reconciliation_cache_key(user_id)
    return await invalidate_cache(key)


async def invalidate_positions_cache(
    user_id: UUID, symbol: Optional[str] = None
) -> bool:
    """Invalidate positions cache for user."""
    key = get_positions_cache_key(user_id, symbol)
    return await invalidate_cache(key)


async def invalidate_guards_cache(user_id: UUID) -> int:
    """Invalidate all guard cache for user."""
    pattern = f"guards:user:{str(user_id)}:*"
    return await invalidate_pattern(pattern)
