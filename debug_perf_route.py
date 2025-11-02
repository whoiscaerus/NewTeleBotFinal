#!/usr/bin/env python3
"""Quick debug script to test performance route."""

import asyncio

from httpx import AsyncClient

from backend.app.orchestrator.main import app


async def main():
    """Test the performance endpoint."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/public/performance/summary?delay_minutes=0"
        )
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")


if __name__ == "__main__":
    asyncio.run(main())
