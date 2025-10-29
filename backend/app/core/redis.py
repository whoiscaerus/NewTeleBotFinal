"""Redis connection management."""

import logging
import os

logger = logging.getLogger(__name__)

# Module-level cache for test fakeredis instance
_test_redis_instance = None


async def get_redis():
    """
    Get Redis async client.

    In production: Connects to Redis URL from settings.
    In tests: Returns in-memory fakeredis instead of connecting (shared instance).
    """
    global _test_redis_instance

    # Check if we're in test mode
    if os.getenv("PYTEST_CURRENT_TEST"):
        # In tests, use fakeredis (reuse same instance for nonce replay detection)
        try:
            import fakeredis.aioredis

            # Create once and reuse to preserve state between requests in a test
            if _test_redis_instance is None:
                _test_redis_instance = fakeredis.aioredis.FakeRedis()
            return _test_redis_instance
        except ImportError:
            logger.warning("fakeredis not available, will fail to connect")
            raise

    # Production: connect to real Redis
    try:
        from redis.asyncio import Redis

        from backend.app.core.settings import get_settings

        settings = get_settings()
        if not settings.redis.enabled:
            logger.warning("Redis is disabled in settings")
            raise RuntimeError("Redis is disabled in settings")

        logger.info(f"Connecting to Redis: {settings.redis.url}")
        redis_client = await Redis.from_url(
            settings.redis.url, encoding="utf-8", decode_responses=True
        )
        logger.info("Redis connected successfully")
        return redis_client
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        raise


async def close_redis() -> None:
    """Close Redis connection (no-op now that we don't cache globally)."""
    pass
