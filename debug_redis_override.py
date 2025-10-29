"""Debug script to check if Redis dependency override works."""

import asyncio
import os
from unittest.mock import AsyncMock

from httpx import ASGITransport, AsyncClient

# Set environment variables
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["APP_ENV"] = "development"


async def main():
    """Test Redis override."""
    from backend.app.core.redis import get_redis

    # Mock Redis
    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.delete = AsyncMock(return_value=1)

    async def override_get_redis():
        """Return mock Redis."""
        return mock_redis

    # Import app AFTER setting up override
    from backend.app.orchestrator.main import app

    # Set dependency overrides
    print(f"Before override: {app.dependency_overrides}")
    app.dependency_overrides[get_redis] = override_get_redis
    print(f"After override: {app.dependency_overrides}")

    # Try making a request
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            print("Attempting GET /health...")
            response = await client.get("/health")
            print(f"Response: {response.status_code}")
            print("Success! Redis override is working.")
    except Exception as e:
        print(f"Error: {e}")
        print(f"Error type: {type(e)}")


if __name__ == "__main__":
    asyncio.run(main())
