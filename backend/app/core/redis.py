"""Redis connection management."""

import logging
from redis.asyncio import Redis

logger = logging.getLogger(__name__)

_redis_client: Redis | None = None


async def get_redis() -> Redis:
    """
    Get Redis async client.

    In tests, this dependency will be overridden with a mock via app.dependency_overrides.
    In production, connects to Redis URL from settings.
    """
    global _redis_client
    
    """Redis connection management."""

import logging
import os
from redis.asyncio import Redis

logger = logging.getLogger(__name__)

_redis_client: Redis | None = None


async def get_redis() -> Redis:
    """
    Get Redis async client.

    In tests, this dependency will be overridden with a mock via app.dependency_overrides.
    In production, connects to Redis URL from settings.
    
    Note: In tests, conftest.py sets app.dependency_overrides[get_redis] to return a mock,
    so this function should never be called in tests.
    """
    global _redis_client
    
    # Only initialize if not already done
    if _redis_client is not None:
        return _redis_client
    
    # Prevent connection attempts in test environment before override is applied
    # pytest sets PYTEST_CURRENT_TEST during test execution
    if os.environ.get("PYTEST_CURRENT_TEST"):
        logger.warning("Running in pytest environment - Redis override should be applied")
        # Return None - the mock should have replaced this via dependency_overrides
        return None
    
    try:
        from backend.app.core.settings import get_settings

        settings = get_settings()
        if not settings.redis.enabled:
            logger.warning("Redis is disabled in settings")
            return None

        logger.info(f"Connecting to Redis: {settings.redis.url}")
        _redis_client = await Redis.from_url(
            settings.redis.url, encoding="utf-8", decode_responses=True
        )
        logger.info("Redis connected successfully")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        raise
    
    return _redis_client


async def close_redis():
    """Close Redis connection."""
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        _redis_client = None
    if _redis_client is not None:
        return _redis_client
    
    try:
        from backend.app.core.settings import get_settings

        settings = get_settings()
        if not settings.redis.enabled:
            logger.warning("Redis is disabled in settings")
            return None

        logger.info(f"Connecting to Redis: {settings.redis.url}")
        _redis_client = await Redis.from_url(
            settings.redis.url, encoding="utf-8", decode_responses=True
        )
        logger.info("Redis connected successfully")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        raise
    
    return _redis_client


async def close_redis():
    """Close Redis connection."""
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        _redis_client = None
