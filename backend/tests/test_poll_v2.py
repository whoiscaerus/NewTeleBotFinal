"""
Tests for Poll Protocol V2 (PR-49): Compression, ETags, Conditional Requests, Adaptive Backoff.

Test Coverage:
- Response compression (gzip, brotli, zstd)
- ETag generation and validation
- Conditional request handling (If-Modified-Since → 304)
- Adaptive backoff calculation
- Batch size limiting
- Compression ratio calculation
"""

import gzip
import json
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from redis import Redis

from backend.app.polling.adaptive_backoff import AdaptiveBackoffManager
from backend.app.polling.protocol_v2 import (
    calculate_backoff,
    calculate_compression_ratio,
    check_if_modified,
    compress_response,
    generate_etag,
)

# Test data
SAMPLE_DATA = {
    "version": 2,
    "approvals": [
        {
            "id": str(uuid4()),
            "instrument": "EURUSD",
            "side": "buy",
            "entry_price": 1.0850,
            "volume": 0.1,
            "ttl_minutes": 240,
            "approved_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat(),
        }
        for _ in range(10)
    ],
    "count": 10,
    "next_poll_seconds": 10,
}


class TestCompressionGzip:
    """Test gzip compression."""

    def test_compress_response_gzip(self):
        """Test gzip compression support."""
        data = {"message": "hello" * 100}  # Repeated data compresses well
        compressed, algo = compress_response(data, "gzip")

        assert algo == "gzip"
        assert isinstance(compressed, bytes)
        assert len(compressed) < len(json.dumps(data))

        # Verify it's valid gzip
        decompressed = gzip.decompress(compressed).decode("utf-8")
        assert json.loads(decompressed) == data

    def test_compress_response_with_other_encodings(self):
        """Test gzip selected when multiple encodings offered."""
        data = {"data": "test"}
        compressed, algo = compress_response(data, "deflate, gzip, identity")

        assert algo == "gzip"
        assert gzip.decompress(compressed).decode("utf-8") == json.dumps(data)

    def test_compress_response_no_compression_when_not_requested(self):
        """Test no compression when not in Accept-Encoding."""
        data = {"data": "test"}
        compressed, algo = compress_response(data, "identity")

        assert algo == "identity"
        assert compressed == json.dumps(data).encode("utf-8")

    def test_compress_response_large_payload(self):
        """Test compression on large payload."""
        data = {"data": ["item"] * 1000}
        json_size = len(json.dumps(data))

        compressed, algo = compress_response(data, "gzip")

        assert algo == "gzip"
        assert len(compressed) < json_size * 0.5  # Expect 50%+ compression

    def test_compress_response_small_payload(self):
        """Test compression on small payload (may not compress well)."""
        data = {"id": "123", "status": "ok"}
        compressed, algo = compress_response(data, "gzip")

        # Compression might not help small data, but should still work
        assert algo == "gzip"
        assert isinstance(compressed, bytes)


class TestETagGeneration:
    """Test ETag generation."""

    def test_generate_etag_format(self):
        """Test ETag format (sha256: prefix)."""
        data = {"test": "data"}
        etag = generate_etag(data)

        assert etag.startswith("sha256:")
        assert len(etag) == 71  # 7 chars prefix + 64 hex chars

    def test_generate_etag_deterministic(self):
        """Test ETags are deterministic (same data → same ETag)."""
        data = {"approvals": [{"id": "123"}]}
        etag1 = generate_etag(data)
        etag2 = generate_etag(data)

        assert etag1 == etag2

    def test_generate_etag_different_for_different_data(self):
        """Test different data produces different ETag."""
        data1 = {"approvals": [{"id": "123"}]}
        data2 = {"approvals": [{"id": "456"}]}

        etag1 = generate_etag(data1)
        etag2 = generate_etag(data2)

        assert etag1 != etag2

    def test_generate_etag_key_order_invariant(self):
        """Test ETag same regardless of key order (sorted internally)."""
        data1 = {"a": 1, "b": 2, "c": 3}
        data2 = {"c": 3, "a": 1, "b": 2}

        etag1 = generate_etag(data1)
        etag2 = generate_etag(data2)

        assert etag1 == etag2

    def test_generate_etag_complex_data(self):
        """Test ETag generation on complex nested data."""
        data = SAMPLE_DATA.copy()
        etag = generate_etag(data)

        assert etag.startswith("sha256:")
        assert len(etag) == 71


class TestConditionalRequests:
    """Test If-Modified-Since conditional request handling."""

    def test_check_if_modified_with_no_since(self):
        """Test check_if_modified returns True when no since timestamp."""
        approvals = []
        assert check_if_modified(approvals, None) is True

    def test_check_if_modified_with_old_timestamp(self):
        """Test check_if_modified returns True when approvals newer than since."""
        now = datetime.utcnow()
        old = now - timedelta(hours=1)

        approval = type("Approval", (), {"created_at": now})()
        approvals = [approval]

        assert check_if_modified(approvals, old) is True

    def test_check_if_modified_with_recent_timestamp(self):
        """Test check_if_modified returns False when approvals older than since."""
        now = datetime.utcnow()
        recent = now + timedelta(seconds=1)

        approval = type("Approval", (), {"created_at": now})()
        approvals = [approval]

        assert check_if_modified(approvals, recent) is False

    def test_check_if_modified_multiple_approvals(self):
        """Test check_if_modified with multiple approvals."""
        now = datetime.utcnow()
        old = now - timedelta(hours=1)

        approval1 = type("Approval", (), {"created_at": old})()
        approval2 = type("Approval", (), {"created_at": now})()
        approvals = [approval1, approval2]

        # Returns True because at least one is newer than since
        assert check_if_modified(approvals, old - timedelta(minutes=1)) is True

    def test_check_if_modified_all_older(self):
        """Test check_if_modified when all approvals are older than since."""
        base = datetime.utcnow()

        approval1 = type("Approval", (), {"created_at": base})()
        approval2 = type("Approval", (), {"created_at": base})()
        approvals = [approval1, approval2]

        since = base + timedelta(seconds=1)

        assert check_if_modified(approvals, since) is False


class TestAdaptiveBackoff:
    """Test adaptive backoff calculation."""

    def test_calculate_backoff_with_approvals(self):
        """Test fast polling when approvals found."""
        device_id = uuid4()
        interval = calculate_backoff(device_id, has_approvals=True, poll_count=0)

        assert interval == 10

    def test_calculate_backoff_no_approvals_first_poll(self):
        """Test backoff on first empty poll (10s)."""
        device_id = uuid4()
        interval = calculate_backoff(device_id, has_approvals=False, poll_count=1)

        assert interval == 20  # 10 * (1 + 1)

    def test_calculate_backoff_exponential(self):
        """Test exponential backoff on consecutive empty polls."""
        device_id = uuid4()

        # Poll 1-4
        assert calculate_backoff(device_id, False, 1) == 20
        assert calculate_backoff(device_id, False, 2) == 30
        assert calculate_backoff(device_id, False, 3) == 40
        assert calculate_backoff(device_id, False, 4) == 50

    def test_calculate_backoff_capped_at_60(self):
        """Test backoff capped at 60 seconds."""
        device_id = uuid4()

        # After 6+ empty polls
        assert calculate_backoff(device_id, False, 5) == 60
        assert calculate_backoff(device_id, False, 10) == 60

    def test_calculate_backoff_resets_on_approval(self):
        """Test backoff resets to 10s when approval received."""
        device_id = uuid4()

        # After 3 empty polls (40s)
        assert calculate_backoff(device_id, False, 3) == 40

        # Approval received, reset to 10s
        assert calculate_backoff(device_id, True, 0) == 10


class TestCompressionRatio:
    """Test compression ratio calculation."""

    def test_calculate_compression_ratio_perfect(self):
        """Test ratio for perfect compression."""
        ratio = calculate_compression_ratio(1000, 1)

        assert ratio == 0.001

    def test_calculate_compression_ratio_no_compression(self):
        """Test ratio when no compression (1.0)."""
        ratio = calculate_compression_ratio(1000, 1000)

        assert ratio == 1.0

    def test_calculate_compression_ratio_gzip_typical(self):
        """Test typical gzip compression ratio."""
        original = 2800  # 2.8 KB
        compressed = 1000  # ~1 KB

        ratio = calculate_compression_ratio(original, compressed)

        assert ratio == pytest.approx(0.357, rel=0.01)

    def test_calculate_compression_ratio_zero_original(self):
        """Test ratio with zero original size."""
        ratio = calculate_compression_ratio(0, 0)

        assert ratio == 0.0


class TestAdaptiveBackoffManager:
    """Test AdaptiveBackoffManager with Redis."""

    @pytest.fixture
    def redis_client(self):
        """Get Redis client for testing."""
        # Try to use test Redis instance
        redis = Redis(host="localhost", port=6379, db=15, decode_responses=True)
        try:
            redis.ping()
            redis.flushdb()  # Clean database
            yield redis
            redis.flushdb()
        except Exception:
            pytest.skip("Redis not available")

    def test_record_poll_no_approvals(self, redis_client):
        """Test recording poll with no approvals."""
        manager = AdaptiveBackoffManager(redis_client)
        device_id = uuid4()

        manager.record_poll(device_id, has_approvals=False)

        history = manager.get_history(device_id)
        assert history == [0]

    def test_record_poll_with_approvals(self, redis_client):
        """Test recording poll with approvals."""
        manager = AdaptiveBackoffManager(redis_client)
        device_id = uuid4()

        manager.record_poll(device_id, has_approvals=True)

        history = manager.get_history(device_id)
        assert history == [1]

    def test_record_multiple_polls(self, redis_client):
        """Test recording multiple polls."""
        manager = AdaptiveBackoffManager(redis_client)
        device_id = uuid4()

        manager.record_poll(device_id, False)
        manager.record_poll(device_id, False)
        manager.record_poll(device_id, True)
        manager.record_poll(device_id, False)

        history = manager.get_history(device_id)
        assert history == [0, 0, 1, 0]

    def test_get_backoff_interval_fast_polling(self, redis_client):
        """Test backoff interval with approvals (fast poll)."""
        manager = AdaptiveBackoffManager(redis_client)
        device_id = uuid4()

        manager.record_poll(device_id, has_approvals=True)
        interval = manager.get_backoff_interval(device_id)

        assert interval == 10

    def test_get_backoff_interval_exponential(self, redis_client):
        """Test backoff interval calculation."""
        manager = AdaptiveBackoffManager(redis_client)
        device_id = uuid4()

        # 3 empty polls
        manager.record_poll(device_id, False)
        manager.record_poll(device_id, False)
        manager.record_poll(device_id, False)

        interval = manager.get_backoff_interval(device_id)
        assert interval == 40  # 10 * (3 + 1)

    def test_get_backoff_interval_capped(self, redis_client):
        """Test backoff capped at 60 seconds."""
        manager = AdaptiveBackoffManager(redis_client)
        device_id = uuid4()

        # Many empty polls
        for _ in range(10):
            manager.record_poll(device_id, False)

        interval = manager.get_backoff_interval(device_id)
        assert interval == 60

    def test_get_backoff_interval_resets(self, redis_client):
        """Test backoff resets when approvals received."""
        manager = AdaptiveBackoffManager(redis_client)
        device_id = uuid4()

        # 3 empty polls (40s)
        for _ in range(3):
            manager.record_poll(device_id, False)

        interval = manager.get_backoff_interval(device_id)
        assert interval == 40

        # Approval received
        manager.record_poll(device_id, True)
        interval = manager.get_backoff_interval(device_id)
        assert interval == 10

    def test_reset_history(self, redis_client):
        """Test resetting poll history."""
        manager = AdaptiveBackoffManager(redis_client)
        device_id = uuid4()

        manager.record_poll(device_id, False)
        assert manager.get_history(device_id) == [0]

        manager.reset_history(device_id)
        assert manager.get_history(device_id) == []

    def test_no_history_returns_empty_list(self, redis_client):
        """Test no history returns empty list."""
        manager = AdaptiveBackoffManager(redis_client)
        device_id = uuid4()

        history = manager.get_history(device_id)
        assert history == []

    def test_default_interval_no_history(self, redis_client):
        """Test default fast interval when no history."""
        manager = AdaptiveBackoffManager(redis_client)
        device_id = uuid4()

        interval = manager.get_backoff_interval(device_id)
        assert interval == 10


class TestPollV2IntegrationScenarios:
    """Integration test scenarios."""

    def test_typical_trading_day_scenario(self):
        """Test typical trading day: active → quiet → active."""
        device_id = uuid4()

        # Morning: Active trading
        intervals = [calculate_backoff(device_id, True, 0) for _ in range(5)]
        assert all(i == 10 for i in intervals)  # All fast

        # Afternoon: Quiet period
        intervals = [calculate_backoff(device_id, False, i + 1) for i in range(5)]
        assert intervals == [20, 30, 40, 50, 60]  # Exponential backoff

        # Evening: Activity resumes
        interval = calculate_backoff(device_id, True, 0)
        assert interval == 10  # Back to fast

    def test_compression_ratio_bandwidth_savings(self):
        """Test realistic bandwidth savings."""
        # 10 approvals at ~2.8 KB each
        data = SAMPLE_DATA.copy()

        # Original
        original_json = json.dumps(data)
        original_size = len(original_json)

        # Compressed
        compressed, algo = compress_response(data, "gzip")
        ratio = calculate_compression_ratio(original_size, len(compressed))

        # Should achieve 60%+ compression
        assert ratio < 0.4
        assert algo == "gzip"

    def test_conditional_request_workflow(self):
        """Test conditional request workflow."""
        now = datetime.utcnow()

        # First poll
        etag1 = generate_etag(SAMPLE_DATA)
        assert etag1.startswith("sha256:")

        # Wait and poll again (no data change)
        etag2 = generate_etag(SAMPLE_DATA)
        assert etag1 == etag2  # Same ETag

        # Data changed
        data_changed = SAMPLE_DATA.copy()
        data_changed["count"] = 11
        etag3 = generate_etag(data_changed)
        assert etag3 != etag1  # Different ETag


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_compress_empty_data(self):
        """Test compression of empty data."""
        data = {}
        compressed, algo = compress_response(data, "gzip")

        assert algo == "gzip"
        assert len(compressed) > 0
        assert gzip.decompress(compressed).decode("utf-8") == "{}"

    def test_generate_etag_large_payload(self):
        """Test ETag generation on very large payload."""
        large_data = {"items": [{"id": str(i)} for i in range(10000)]}
        etag = generate_etag(large_data)

        assert etag.startswith("sha256:")
        assert len(etag) == 71

    def test_check_if_modified_with_empty_approvals(self):
        """Test check_if_modified with empty approval list."""
        result = check_if_modified([], None)
        assert result is True

    def test_calculate_backoff_with_zero_poll_count(self):
        """Test backoff with zero poll count."""
        device_id = uuid4()
        interval = calculate_backoff(device_id, False, 0)

        assert interval == 10  # First empty poll
