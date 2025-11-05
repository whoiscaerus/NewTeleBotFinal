"""Debug script for since parameter test."""

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / "backend"))


async def test_since_parsing():
    """Test since parameter parsing."""
    # Simulate what the test does
    checkpoint = datetime.now(UTC).isoformat()
    print(f"Checkpoint value: {checkpoint}")
    print(f"Checkpoint type: {type(checkpoint)}")

    # Simulate what happens when passed as query parameter
    since_str = checkpoint
    print(f"\nSince as string: {since_str}")
    print(f"Since type: {type(since_str)}")

    # Test parsing logic from routes.py
    try:
        since_dt = (
            since_str
            if isinstance(since_str, datetime)
            else datetime.fromisoformat(
                since_str.isoformat()
                if hasattr(since_str, "isoformat")
                else str(since_str)
            )
        )
        print(f"\nParsed datetime: {since_dt}")
        print(f"Parsed type: {type(since_dt)}")
    except Exception as e:
        print(f"\nError parsing: {e}")
        print(f"Error type: {type(e)}")
        import traceback

        traceback.print_exc()

    # Test what FastAPI does with since parameter
    print("\n" + "=" * 60)
    print("Testing FastAPI datetime parameter handling:")
    print("=" * 60)

    # When FastAPI gets ?since=2024-01-01T12:00:00+00:00
    # It should parse it as datetime object automatically

    # Simulate a query parameter that FastAPI would parse
    query_since_value = "2024-01-01T12:00:00+00:00"
    print(f"Query parameter value: {query_since_value}")

    # FastAPI's datetime parser
    try:
        parsed = datetime.fromisoformat(query_since_value)
        print(f"Parsed as datetime: {parsed}")
        print(f"Type: {type(parsed)}")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(test_since_parsing())
