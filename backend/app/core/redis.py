"""Redis connection management."""

import logging

logger = logging.getLogger(__name__)


async def get_redis():
    """
    Get Redis async client.

    In production: Connects to Redis URL from settings.
    In tests: Dependency overrides set to return a mock via conftest fixture.
    """
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
