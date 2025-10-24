#!/usr/bin/env python3
"""Test if awaiting a mock works."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


async def get_rate_limiter():
    """Get rate limiter."""
    return MagicMock()


async def test_await_mock_direct():
    """Test awaiting a mock directly."""
    mock_limiter = AsyncMock()
    mock_limiter.is_allowed = AsyncMock(return_value=True)

    # Test 1: Mock returns the object directly (not async)
    print("Test 1: Patching with non-async return_value")
    with patch("__main__.get_rate_limiter", return_value=mock_limiter):
        try:
            limiter = await get_rate_limiter()
            print(f"  Result: {limiter}")
            result = await limiter.is_allowed("test")
            print(f"  is_allowed result: {result}")
        except Exception as e:
            print(f"  Error: {e}")

    # Test 2: Mock returns async (correct way)
    print("\nTest 2: Patching with async return_value")

    async def mock_get_rate_limiter():
        return mock_limiter

    with patch("__main__.get_rate_limiter", new=mock_get_rate_limiter):
        try:
            limiter = await get_rate_limiter()
            print(f"  Result: {limiter}")
            result = await limiter.is_allowed("test")
            print(f"  is_allowed result: {result}")
            print(f"  is_allowed called: {mock_limiter.is_allowed.called}")
        except Exception as e:
            print(f"  Error: {e}")


asyncio.run(test_await_mock_direct())
