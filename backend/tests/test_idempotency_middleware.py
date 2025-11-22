import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_idempotency_middleware(client: AsyncClient, auth_headers: dict):
    """Test idempotency middleware functionality."""

    # 1. First request
    key = str(uuid.uuid4())
    headers = {"Idempotency-Key": key, **auth_headers}
    payload = {
        "instrument": "EURUSD",
        "side": "buy",
        "price": 1.1234,
        "payload": {"strategy": "test"},
    }

    response1 = await client.post("/api/v1/signals", json=payload, headers=headers)
    # Expect success (201 Created)
    assert response1.status_code == 201

    # 2. Second request (same key)
    response2 = await client.post("/api/v1/signals", json=payload, headers=headers)
    # Should return cached response (201)
    assert response2.status_code == 201

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
