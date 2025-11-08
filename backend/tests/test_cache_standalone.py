"""
Standalone tests for persistent caching module.

This file does NOT use conftest to avoid settings initialization issues.
Tests only test the core CandleCache and SignalPublishCache classes directly.

Tests cover:
- CandleCache: In-memory cache without Redis
- SignalPublishCache: Signal deduplication
- Error handling and edge cases
"""

import asyncio
from datetime import datetime

import pytest


def test_candle_cache_import():
    """Test that CandleCache can be imported."""
    from backend.app.strategy.cache import CandleCache

    assert CandleCache is not None


def test_signal_publish_cache_import():
    """Test that SignalPublishCache can be imported."""
    from backend.app.strategy.cache import SignalPublishCache

    assert SignalPublishCache is not None


@pytest.mark.asyncio
async def test_candle_cache_set_and_get():
    """Test basic set and get operations."""
    from backend.app.strategy.cache import CandleCache

    cache = CandleCache()
    key = "candle:GOLD:15m:2025-01-01T10:15:00"
    value = {"price": 1950.50, "volume": 1000}

    # Set value
    result = await cache.set(key, value, ttl=3600)
    assert result is True

    # Get value
    retrieved = await cache.get(key)
    assert retrieved == value


@pytest.mark.asyncio
async def test_candle_cache_get_nonexistent_key():
    """Test getting non-existent key returns None."""
    from backend.app.strategy.cache import CandleCache

    cache = CandleCache()
    result = await cache.get("nonexistent:key")
    assert result is None


@pytest.mark.asyncio
async def test_candle_cache_exists():
    """Test exists check."""
    from backend.app.strategy.cache import CandleCache

    cache = CandleCache()
    key = "candle:TEST:15m:2025-01-01T10:15:00"

    # Initially doesn't exist
    assert await cache.exists(key) is False

    # After set, exists
    await cache.set(key, "data", ttl=3600)
    assert await cache.exists(key) is True


@pytest.mark.asyncio
async def test_candle_cache_delete():
    """Test deleting cache entries."""
    from backend.app.strategy.cache import CandleCache

    cache = CandleCache()
    key = "candle:GOLD:15m:2025-01-01T10:15:00"

    # Set and verify exists
    await cache.set(key, "value", ttl=3600)
    assert await cache.exists(key) is True

    # Delete and verify gone
    result = await cache.delete(key)
    assert result is True
    assert await cache.exists(key) is False


@pytest.mark.asyncio
async def test_candle_cache_clear():
    """Test clearing all cache entries."""
    from backend.app.strategy.cache import CandleCache

    cache = CandleCache()

    # Add multiple entries
    for i in range(5):
        key = f"candle:TEST:15m:2025-01-01T10:{i:02d}:00"
        await cache.set(key, {"index": i}, ttl=3600)

    # Verify all exist
    for i in range(5):
        key = f"candle:TEST:15m:2025-01-01T10:{i:02d}:00"
        assert await cache.exists(key) is True

    # Clear all
    result = await cache.clear()
    assert result is True

    # Verify all gone
    for i in range(5):
        key = f"candle:TEST:15m:2025-01-01T10:{i:02d}:00"
        assert await cache.exists(key) is False


@pytest.mark.asyncio
async def test_signal_publish_cache_mark_and_check():
    """Test marking and checking if signal published."""
    from backend.app.strategy.cache import SignalPublishCache

    cache = SignalPublishCache()
    instrument = "GOLD"
    candle_start = datetime(2025, 1, 1, 10, 15, 0)
    signal_id = "sig_12345"

    # Initially not published
    assert await cache.was_published(instrument, candle_start) is False

    # Mark as published
    result = await cache.mark_published(instrument, candle_start, signal_id, ttl=86400)
    assert result is True

    # Now published
    assert await cache.was_published(instrument, candle_start) is True


@pytest.mark.asyncio
async def test_signal_publish_cache_get_signal_id():
    """Test retrieving signal ID from cache."""
    from backend.app.strategy.cache import SignalPublishCache

    cache = SignalPublishCache()
    instrument = "EURUSD"
    candle_start = datetime(2025, 1, 1, 15, 0, 0)
    signal_id = "sig_67890"

    # Initially returns None
    assert await cache.get_signal_id(instrument, candle_start) is None

    # Mark published
    await cache.mark_published(instrument, candle_start, signal_id, ttl=86400)

    # Now returns signal ID
    retrieved_id = await cache.get_signal_id(instrument, candle_start)
    assert retrieved_id == signal_id


@pytest.mark.asyncio
async def test_multiple_instruments():
    """Test caching signals for multiple instruments."""
    from backend.app.strategy.cache import SignalPublishCache

    cache = SignalPublishCache()
    candle_start = datetime(2025, 1, 1, 10, 15, 0)

    instruments = ["GOLD", "EURUSD", "GBPUSD", "USDJPY"]
    signal_ids = ["sig_1", "sig_2", "sig_3", "sig_4"]

    # Mark all as published
    for inst, sig_id in zip(instruments, signal_ids, strict=True):
        await cache.mark_published(inst, candle_start, sig_id, ttl=86400)

    # Verify all are published
    for inst in instruments:
        assert await cache.was_published(inst, candle_start) is True

    # Verify each has correct signal ID
    for inst, sig_id in zip(instruments, signal_ids, strict=True):
        retrieved_id = await cache.get_signal_id(inst, candle_start)
        assert retrieved_id == sig_id


@pytest.mark.asyncio
async def test_multiple_candles():
    """Test caching signals for multiple candles of same instrument."""
    from backend.app.strategy.cache import SignalPublishCache

    cache = SignalPublishCache()
    instrument = "GOLD"
    signal_ids = ["sig_1", "sig_2", "sig_3"]

    candle_times = [
        datetime(2025, 1, 1, 10, 15, 0),
        datetime(2025, 1, 1, 10, 30, 0),
        datetime(2025, 1, 1, 10, 45, 0),
    ]

    # Mark all as published
    for i, candle_start in enumerate(candle_times):
        await cache.mark_published(instrument, candle_start, signal_ids[i], ttl=86400)

    # Verify all are published
    for candle_start in candle_times:
        assert await cache.was_published(instrument, candle_start) is True

    # Verify each has correct signal ID
    for i, candle_start in enumerate(candle_times):
        retrieved_id = await cache.get_signal_id(instrument, candle_start)
        assert retrieved_id == signal_ids[i]


@pytest.mark.asyncio
async def test_concurrent_operations():
    """Test concurrent cache operations."""
    from backend.app.strategy.cache import CandleCache

    cache = CandleCache()

    async def set_and_get(index):
        key = f"concurrent:test:{index}"
        await cache.set(key, f"value_{index}", ttl=3600)
        result = await cache.get(key)
        return result == f"value_{index}"

    # Run multiple concurrent operations
    results = await asyncio.gather(*[set_and_get(i) for i in range(10)])
    assert all(results)


@pytest.mark.asyncio
async def test_large_values():
    """Test caching large values."""
    from backend.app.strategy.cache import CandleCache

    cache = CandleCache()
    key = "large:value"

    # Large dictionary
    large_value = {f"key_{i}": f"value_{i}" * 100 for i in range(100)}

    # Should handle large values
    await cache.set(key, large_value, ttl=3600)
    result = await cache.get(key)
    assert result == large_value


@pytest.mark.asyncio
async def test_cache_multiple_types():
    """Test caching different data types."""
    from backend.app.strategy.cache import CandleCache

    cache = CandleCache()

    test_data = {
        "string": "test_value",
        "int": 42,
        "float": 3.14159,
        "dict": {"nested": "data"},
        "list": [1, 2, 3],
        "bool": True,
    }

    for key_suffix, value in test_data.items():
        key = f"test:{key_suffix}"
        await cache.set(key, value, ttl=3600)
        retrieved = await cache.get(key)
        assert retrieved == value


@pytest.mark.asyncio
async def test_candle_detector_integration_pattern():
    """Test pattern used by CandleDetector."""
    from backend.app.strategy.cache import CandleCache

    cache = CandleCache()

    instrument = "GOLD"
    timeframe = "15m"
    candle_start = datetime(2025, 1, 1, 10, 15, 0)

    # Pattern: candle:{instrument}:{timeframe}:{candle_start}
    cache_key = f"candle:{instrument}:{timeframe}:{candle_start.isoformat()}"

    # First call: not in cache
    exists = await cache.exists(cache_key)
    assert exists is False

    # Process candle, then cache it
    await cache.set(cache_key, True, ttl=3600)

    # Second call: in cache
    exists = await cache.exists(cache_key)
    assert exists is True


@pytest.mark.asyncio
async def test_signal_publisher_integration_pattern():
    """Test pattern used by SignalPublisher."""
    from backend.app.strategy.cache import SignalPublishCache

    cache = SignalPublishCache()

    instrument = "GOLD"
    candle_start = datetime(2025, 1, 1, 10, 15, 0)
    signal_id = "sig_abc123"

    # Pattern: signal:publish:{instrument}:{candle_start}
    # Mark signal as published
    await cache.mark_published(instrument, candle_start, signal_id, ttl=86400)

    # Check if already published
    already_published = await cache.was_published(instrument, candle_start)
    assert already_published is True

    # Retrieve signal ID
    retrieved_id = await cache.get_signal_id(instrument, candle_start)
    assert retrieved_id == signal_id
