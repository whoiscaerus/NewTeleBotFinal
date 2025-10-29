"""Root conftest - runs BEFORE all backend tests."""

import sys

# CRITICAL: Apply gevent monkey-patch BEFORE any imports that use ssl, jwt, anyio, redis
# This must happen before locust or any other package imports ssl
try:
    from gevent import monkey

    monkey.patch_all(ssl=True)
    print("ROOT CONFTEST: gevent monkey-patch applied", file=sys.stderr)
except ImportError:
    print("ROOT CONFTEST: gevent not available, skipping monkey-patch", file=sys.stderr)

from unittest.mock import AsyncMock

from redis.asyncio import Redis as AsyncRedis

# Monkeypatch Redis.from_url at IMPORT TIME before ANY app imports happen
print("ROOT CONFTEST: Patching Redis.from_url for test mode", file=sys.stderr)


async def mock_redis_from_url(*args, **kwargs):
    """Mock Redis.from_url to return AsyncMock instead of connecting."""
    mock = AsyncMock()
    mock.set = AsyncMock(return_value=True)
    mock.get = AsyncMock(return_value=None)
    mock.delete = AsyncMock(return_value=1)
    return mock


# Store original
original_from_url = AsyncRedis.from_url

# Replace with mock
AsyncRedis.from_url = classmethod(
    lambda cls, *args, **kwargs: mock_redis_from_url(*args, **kwargs)
)

print("ROOT CONFTEST: Redis.from_url patched successfully", file=sys.stderr)
