#!/usr/bin/env python3
"""Debug rate limit decorator patching."""

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, ".")  # noqa: E402

from app.core.decorators import rate_limit  # noqa: E402
from fastapi import Request  # noqa: E402


async def test_rate_limit_with_patch():
    """Test rate_limit decorator with patch inside context."""
    print("Creating mock request...", file=sys.stderr)
    mock_request = MagicMock(spec=Request)
    mock_request.client.host = "127.0.0.1"

    # Create mock limiter
    mock_limiter = AsyncMock()
    mock_limiter.is_allowed = AsyncMock(return_value=True)
    mock_limiter.get_remaining = AsyncMock(return_value=9)

    print("Starting patch context...", file=sys.stderr)
    with patch("app.core.decorators.get_rate_limiter", return_value=mock_limiter):
        print("Inside patch context, creating decorated function...", file=sys.stderr)

        @rate_limit(max_tokens=10, refill_rate=1, window_seconds=60)
        async def test_endpoint(request: Request):
            print("Inside test_endpoint", file=sys.stderr)
            return {"status": "ok"}

        print("Calling test_endpoint...", file=sys.stderr)
        result = await test_endpoint(request=mock_request)

        print(f"Result: {result}", file=sys.stderr)
        print(f"is_allowed.called: {mock_limiter.is_allowed.called}", file=sys.stderr)
        print(
            f"is_allowed.call_count: {mock_limiter.is_allowed.call_count}",
            file=sys.stderr,
        )

        if not mock_limiter.is_allowed.called:
            print("ERROR: is_allowed was never called!", file=sys.stderr)
        else:
            print("SUCCESS: is_allowed was called", file=sys.stderr)


asyncio.run(test_rate_limit_with_patch())
