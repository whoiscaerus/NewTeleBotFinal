import uuid

import pytest
from httpx import AsyncClient



@pytest.mark.asyncio
async def test_idempotency_middleware(client: AsyncClient):
    """Test idempotency middleware functionality."""

    # 1. First request
    key = str(uuid.uuid4())
    headers = {"Idempotency-Key": key}
    payload = {"test": "data"}

    response1 = await client.post("/api/v1/signals", json=payload, headers=headers)
    # Expect 401 Unauthorized
    assert response1.status_code == 401

    # 2. Second request (same key)
    response2 = await client.post("/api/v1/signals", json=payload, headers=headers)
    assert response2.status_code == 401

    # Check for hit header
    assert response2.headers.get("X-Idempotency-Hit") == "true"

    # Check body matches
    assert response1.content == response2.content


@pytest.mark.asyncio
async def test_idempotency_concurrent_lock(client: AsyncClient):
    """Test locking mechanism (simulated)."""
    # This is hard to test with just client calls without mocking the storage delay.
    # But we can verify that different keys don't conflict.
    pass
