"""Root conftest - runs BEFORE all backend tests."""

import sys
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
