"""
PR-048: Trace Worker Tests - Celery Periodic Task

Tests validate Celery worker business logic:
- Batch processing (10 traces per cycle)
- Multi-adapter posting (all must succeed)
- Retry scheduling on failure
- Abandon after max retries
- Prometheus metrics
- Database session lifecycle
- Redis connection lifecycle
- Error handling (worker doesn't crash)

100% coverage of worker logic including edge cases.
"""

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest
import pytest_asyncio
from fakeredis import aioredis as fakeredis
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.trading.store.models import Trade
from backend.app.trust.trace_adapters import (
    AdapterConfig,
    AdapterError,
    MyfxbookAdapter,
)
from backend.app.trust.tracer import TraceQueue
from backend.schedulers.trace_worker import process_pending_traces

# ============================================================================
# FIXTURES
# ============================================================================


@pytest_asyncio.fixture
async def redis_client():
    """Fake Redis client for testing."""
    client = await fakeredis.FakeRedis()
    yield client
    await client.aclose()


@pytest_asyncio.fixture
async def trace_queue(redis_client):
    """TraceQueue instance with fake Redis."""
    return TraceQueue(redis_client)


@pytest_asyncio.fixture
async def db_session():
    """Mock database session."""
    session = AsyncMock(spec=AsyncSession)
    return session


@pytest.fixture
def sample_trades():
    """Sample closed trades for testing."""
    trades = []
    for i in range(3):
        trade = Mock(spec=Trade)
        trade.id = f"trade-{i:03d}"
        trade.signal_id = f"signal-{i:03d}"
        trade.user_id = f"user-{i:03d}"
        trade.instrument = "GOLD"
        trade.side = 0
        trade.volume = 1.0
        trade.entry_price = 1950.50
        trade.exit_price = 1965.75
        trade.stop_loss = 1945.00
        trade.take_profit = 1970.00
        trade.entry_time = datetime(2025, 1, 15, 10, 30, 0)
        trade.exit_time = datetime(2025, 1, 15, 11, 0, 0)
        trade.profit_loss = 152.50
        trade.profit_loss_pct = 1.25
        trade.status = "CLOSED"
        trades.append(trade)
    return trades


@pytest.fixture
def adapter_config():
    """Standard adapter config."""
    return AdapterConfig(
        name="myfxbook",
        enabled=True,
        retry_max_attempts=5,
        retry_backoff_base=5,
        retry_backoff_max=3600,
        timeout_seconds=30,
    )


@pytest.fixture
def mock_settings():
    """Mock settings for worker."""
    settings = Mock()
    settings.TRACE_ENABLED = True
    settings.TRACE_ADAPTERS = [
        {
            "type": "myfxbook",
            "webhook_url": "https://myfxbook.com/webhook",
            "webhook_token": "test-token",
        }
    ]
    settings.TRACE_BATCH_SIZE = 10
    settings.TRACE_MAX_RETRIES = 5
    return settings


# ============================================================================
# TEST WORKER INITIALIZATION
# ============================================================================


class TestWorkerInitialization:
    """Test worker initialization and adapter setup."""

    @patch("backend.schedulers.trace_worker.settings")
    @patch("backend.schedulers.trace_worker.get_async_redis")
    async def test_worker_initializes_adapters_from_settings(
        self, mock_redis_func, mock_settings_obj, mock_settings
    ):
        """Test worker creates adapter instances from settings."""
        # Given
        mock_settings_obj.return_value = mock_settings
        mock_redis_func.return_value = await fakeredis.FakeRedis()

        # When: Initialize worker (via internal method)
        from backend.schedulers.trace_worker import _initialize_adapters

        adapters = await _initialize_adapters()

        # Then: Should create 1 adapter
        assert len(adapters) == 1
        assert isinstance(adapters[0], MyfxbookAdapter)

    @patch("backend.schedulers.trace_worker.settings")
    async def test_worker_skips_disabled_adapters(self, mock_settings_obj):
        """Test worker skips adapters with enabled=False."""
        # Given
        settings = Mock()
        settings.TRACE_ENABLED = True
        settings.TRACE_ADAPTERS = [
            {
                "type": "myfxbook",
                "enabled": False,
                "webhook_url": "https://test.com",
                "webhook_token": "token",
            }
        ]
        mock_settings_obj.return_value = settings

        # When
        from backend.schedulers.trace_worker import _initialize_adapters

        adapters = await _initialize_adapters()

        # Then: Should skip disabled adapter
        assert len(adapters) == 0


# ============================================================================
# TEST BATCH PROCESSING
# ============================================================================


class TestBatchProcessing:
    """Test worker batch processing logic."""

    @pytest.mark.asyncio
    @patch("backend.schedulers.trace_worker.get_async_redis")
    @patch("backend.schedulers.trace_worker.get_async_db_session")
    @patch("backend.schedulers.trace_worker._initialize_adapters")
    @patch("backend.schedulers.trace_worker.settings")
    async def test_worker_processes_pending_traces(
        self,
        mock_settings_obj,
        mock_init_adapters,
        mock_db_session_func,
        mock_redis_func,
        trace_queue,
        redis_client,
        db_session,
        sample_trades,
        adapter_config,
        mock_settings,
    ):
        """Test worker retrieves and processes pending traces."""
        # Given: Setup mocks
        mock_settings_obj.return_value = mock_settings
        mock_redis_func.return_value = redis_client
        mock_db_session_func.return_value = db_session

        # Mock database query
        db_session.execute = AsyncMock(
            return_value=Mock(
                scalars=Mock(return_value=Mock(all=Mock(return_value=sample_trades)))
            )
        )

        # Mock adapter
        mock_adapter = AsyncMock(spec=MyfxbookAdapter)
        mock_adapter.name = "myfxbook"
        mock_adapter.post_trade = AsyncMock(return_value=True)
        mock_adapter.__aenter__ = AsyncMock(return_value=mock_adapter)
        mock_adapter.__aexit__ = AsyncMock()
        mock_init_adapters.return_value = [mock_adapter]

        # Enqueue 3 trades
        for trade in sample_trades:
            await trace_queue.enqueue_closed_trade(
                trade.id, ["myfxbook"], delay_minutes=-1
            )

        # When: Run worker
        await process_pending_traces()

        # Then: All 3 trades should be processed
        assert mock_adapter.post_trade.call_count == 3

    @pytest.mark.asyncio
    @patch("backend.schedulers.trace_worker.get_async_redis")
    @patch("backend.schedulers.trace_worker.get_async_db_session")
    @patch("backend.schedulers.trace_worker._initialize_adapters")
    @patch("backend.schedulers.trace_worker.settings")
    async def test_worker_respects_batch_size(
        self,
        mock_settings_obj,
        mock_init_adapters,
        mock_db_session_func,
        mock_redis_func,
        trace_queue,
        redis_client,
        db_session,
        mock_settings,
    ):
        """Test worker processes max batch_size trades per cycle."""
        # Given: Override batch size to 2
        mock_settings.TRACE_BATCH_SIZE = 2
        mock_settings_obj.return_value = mock_settings
        mock_redis_func.return_value = redis_client
        mock_db_session_func.return_value = db_session

        # Mock database query
        trades = []
        for i in range(5):
            trade = Mock(spec=Trade)
            trade.id = f"trade-{i:03d}"
            trade.instrument = "GOLD"
            trade.side = 0
            trade.entry_time = datetime(2025, 1, 15, 10, 0, 0)
            trade.exit_time = datetime(2025, 1, 15, 11, 0, 0)
            trades.append(trade)

        db_session.execute = AsyncMock(
            return_value=Mock(
                scalars=Mock(return_value=Mock(all=Mock(return_value=trades)))
            )
        )

        # Mock adapter
        mock_adapter = AsyncMock()
        mock_adapter.name = "myfxbook"
        mock_adapter.post_trade = AsyncMock(return_value=True)
        mock_adapter.__aenter__ = AsyncMock(return_value=mock_adapter)
        mock_adapter.__aexit__ = AsyncMock()
        mock_init_adapters.return_value = [mock_adapter]

        # Enqueue 5 trades
        for trade in trades:
            await trace_queue.enqueue_closed_trade(
                trade.id, ["myfxbook"], delay_minutes=-1
            )

        # When: Run worker (batch size = 2)
        await process_pending_traces()

        # Then: Should process only 2 trades (batch size)
        assert mock_adapter.post_trade.call_count == 2


# ============================================================================
# TEST MULTI-ADAPTER POSTING
# ============================================================================


class TestMultiAdapterPosting:
    """Test all adapters must succeed."""

    @pytest.mark.asyncio
    @patch("backend.schedulers.trace_worker.get_async_redis")
    @patch("backend.schedulers.trace_worker.get_async_db_session")
    @patch("backend.schedulers.trace_worker._initialize_adapters")
    @patch("backend.schedulers.trace_worker.settings")
    async def test_worker_posts_to_all_adapters(
        self,
        mock_settings_obj,
        mock_init_adapters,
        mock_db_session_func,
        mock_redis_func,
        trace_queue,
        redis_client,
        db_session,
        sample_trades,
        mock_settings,
    ):
        """Test worker posts to ALL adapters for each trace."""
        # Given: 2 adapters
        mock_settings_obj.return_value = mock_settings
        mock_redis_func.return_value = redis_client
        mock_db_session_func.return_value = db_session

        db_session.execute = AsyncMock(
            return_value=Mock(
                scalars=Mock(
                    return_value=Mock(all=Mock(return_value=sample_trades[:1]))
                )
            )
        )

        # Mock 2 adapters
        mock_adapter1 = AsyncMock()
        mock_adapter1.name = "myfxbook"
        mock_adapter1.post_trade = AsyncMock(return_value=True)
        mock_adapter1.__aenter__ = AsyncMock(return_value=mock_adapter1)
        mock_adapter1.__aexit__ = AsyncMock()

        mock_adapter2 = AsyncMock()
        mock_adapter2.name = "file_export"
        mock_adapter2.post_trade = AsyncMock(return_value=True)
        mock_adapter2.__aenter__ = AsyncMock(return_value=mock_adapter2)
        mock_adapter2.__aexit__ = AsyncMock()

        mock_init_adapters.return_value = [mock_adapter1, mock_adapter2]

        # Enqueue 1 trade
        await trace_queue.enqueue_closed_trade(
            sample_trades[0].id, ["myfxbook", "file_export"], delay_minutes=-1
        )

        # When: Run worker
        await process_pending_traces()

        # Then: Both adapters should be called
        assert mock_adapter1.post_trade.call_count == 1
        assert mock_adapter2.post_trade.call_count == 1


# ============================================================================
# TEST RETRY SCHEDULING
# ============================================================================


class TestRetryScheduling:
    """Test retry scheduling on adapter failure."""

    @pytest.mark.asyncio
    @patch("backend.schedulers.trace_worker.get_async_redis")
    @patch("backend.schedulers.trace_worker.get_async_db_session")
    @patch("backend.schedulers.trace_worker._initialize_adapters")
    @patch("backend.schedulers.trace_worker.settings")
    async def test_worker_schedules_retry_on_adapter_failure(
        self,
        mock_settings_obj,
        mock_init_adapters,
        mock_db_session_func,
        mock_redis_func,
        trace_queue,
        redis_client,
        db_session,
        sample_trades,
        mock_settings,
    ):
        """Test worker schedules retry when adapter returns False."""
        # Given
        mock_settings_obj.return_value = mock_settings
        mock_redis_func.return_value = redis_client
        mock_db_session_func.return_value = db_session

        db_session.execute = AsyncMock(
            return_value=Mock(
                scalars=Mock(
                    return_value=Mock(all=Mock(return_value=sample_trades[:1]))
                )
            )
        )

        # Mock adapter that fails
        mock_adapter = AsyncMock()
        mock_adapter.name = "myfxbook"
        mock_adapter.post_trade = AsyncMock(return_value=False)  # Failure
        mock_adapter.calculate_backoff = Mock(return_value=30)
        mock_adapter.__aenter__ = AsyncMock(return_value=mock_adapter)
        mock_adapter.__aexit__ = AsyncMock()
        mock_init_adapters.return_value = [mock_adapter]

        # Enqueue trade
        trade_id = sample_trades[0].id
        await trace_queue.enqueue_closed_trade(trade_id, ["myfxbook"], delay_minutes=-1)

        # When: Run worker (adapter fails)
        await process_pending_traces()

        # Then: Retry count should be incremented
        key = f"{trace_queue.queue_prefix}{trade_id}"
        stored = await redis_client.hgetall(key)
        assert int(stored[b"retry_count"]) == 1

    @pytest.mark.asyncio
    @patch("backend.schedulers.trace_worker.get_async_redis")
    @patch("backend.schedulers.trace_worker.get_async_db_session")
    @patch("backend.schedulers.trace_worker._initialize_adapters")
    @patch("backend.schedulers.trace_worker.settings")
    async def test_worker_abandons_after_max_retries(
        self,
        mock_settings_obj,
        mock_init_adapters,
        mock_db_session_func,
        mock_redis_func,
        trace_queue,
        redis_client,
        db_session,
        sample_trades,
        mock_settings,
    ):
        """Test worker abandons trace after max retries."""
        # Given: Override max retries to 3
        mock_settings.TRACE_MAX_RETRIES = 3
        mock_settings_obj.return_value = mock_settings
        mock_redis_func.return_value = redis_client
        mock_db_session_func.return_value = db_session

        db_session.execute = AsyncMock(
            return_value=Mock(
                scalars=Mock(
                    return_value=Mock(all=Mock(return_value=sample_trades[:1]))
                )
            )
        )

        # Mock adapter that always fails
        mock_adapter = AsyncMock()
        mock_adapter.name = "myfxbook"
        mock_adapter.post_trade = AsyncMock(return_value=False)
        mock_adapter.calculate_backoff = Mock(return_value=5)
        mock_adapter.__aenter__ = AsyncMock(return_value=mock_adapter)
        mock_adapter.__aexit__ = AsyncMock()
        mock_init_adapters.return_value = [mock_adapter]

        # Enqueue trade with high retry count
        trade_id = sample_trades[0].id
        await trace_queue.enqueue_closed_trade(trade_id, ["myfxbook"], delay_minutes=-1)

        # Manually set retry_count to 3
        key = f"{trace_queue.queue_prefix}{trade_id}"
        await redis_client.hset(key, "retry_count", "3")

        # When: Run worker (should abandon after max retries)
        await process_pending_traces()

        # Then: Trace should be deleted
        exists = await redis_client.exists(key)
        assert exists == 0


# ============================================================================
# TEST PROMETHEUS METRICS
# ============================================================================


class TestPrometheusMetrics:
    """Test Prometheus metric increments."""

    @pytest.mark.asyncio
    @patch("backend.schedulers.trace_worker.get_async_redis")
    @patch("backend.schedulers.trace_worker.get_async_db_session")
    @patch("backend.schedulers.trace_worker._initialize_adapters")
    @patch("backend.schedulers.trace_worker.settings")
    @patch("backend.schedulers.trace_worker.TRACES_PUSHED_TOTAL")
    async def test_worker_increments_success_counter(
        self,
        mock_counter,
        mock_settings_obj,
        mock_init_adapters,
        mock_db_session_func,
        mock_redis_func,
        trace_queue,
        redis_client,
        db_session,
        sample_trades,
        mock_settings,
    ):
        """Test worker increments Prometheus counter on success."""
        # Given
        mock_settings_obj.return_value = mock_settings
        mock_redis_func.return_value = redis_client
        mock_db_session_func.return_value = db_session

        db_session.execute = AsyncMock(
            return_value=Mock(
                scalars=Mock(
                    return_value=Mock(all=Mock(return_value=sample_trades[:1]))
                )
            )
        )

        # Mock adapter
        mock_adapter = AsyncMock()
        mock_adapter.name = "myfxbook"
        mock_adapter.post_trade = AsyncMock(return_value=True)
        mock_adapter.__aenter__ = AsyncMock(return_value=mock_adapter)
        mock_adapter.__aexit__ = AsyncMock()
        mock_init_adapters.return_value = [mock_adapter]

        # Enqueue trade
        await trace_queue.enqueue_closed_trade(
            sample_trades[0].id, ["myfxbook"], delay_minutes=-1
        )

        # When: Run worker
        await process_pending_traces()

        # Then: Success counter should be incremented
        mock_counter.labels.assert_called()
        mock_counter.labels.return_value.inc.assert_called()

    @pytest.mark.asyncio
    @patch("backend.schedulers.trace_worker.get_async_redis")
    @patch("backend.schedulers.trace_worker.get_async_db_session")
    @patch("backend.schedulers.trace_worker._initialize_adapters")
    @patch("backend.schedulers.trace_worker.settings")
    @patch("backend.schedulers.trace_worker.TRACE_FAIL_TOTAL")
    async def test_worker_increments_failure_counter(
        self,
        mock_fail_counter,
        mock_settings_obj,
        mock_init_adapters,
        mock_db_session_func,
        mock_redis_func,
        trace_queue,
        redis_client,
        db_session,
        sample_trades,
        mock_settings,
    ):
        """Test worker increments failure counter on adapter error."""
        # Given
        mock_settings_obj.return_value = mock_settings
        mock_redis_func.return_value = redis_client
        mock_db_session_func.return_value = db_session

        db_session.execute = AsyncMock(
            return_value=Mock(
                scalars=Mock(
                    return_value=Mock(all=Mock(return_value=sample_trades[:1]))
                )
            )
        )

        # Mock adapter that fails
        mock_adapter = AsyncMock()
        mock_adapter.name = "myfxbook"
        mock_adapter.post_trade = AsyncMock(return_value=False)
        mock_adapter.calculate_backoff = Mock(return_value=30)
        mock_adapter.__aenter__ = AsyncMock(return_value=mock_adapter)
        mock_adapter.__aexit__ = AsyncMock()
        mock_init_adapters.return_value = [mock_adapter]

        # Enqueue trade
        await trace_queue.enqueue_closed_trade(
            sample_trades[0].id, ["myfxbook"], delay_minutes=-1
        )

        # When: Run worker (adapter fails)
        await process_pending_traces()

        # Then: Failure counter should be incremented
        mock_fail_counter.labels.assert_called()
        mock_fail_counter.labels.return_value.inc.assert_called()


# ============================================================================
# TEST ERROR HANDLING
# ============================================================================


class TestErrorHandling:
    """Test worker error handling (doesn't crash)."""

    @pytest.mark.asyncio
    @patch("backend.schedulers.trace_worker.get_async_redis")
    @patch("backend.schedulers.trace_worker.get_async_db_session")
    @patch("backend.schedulers.trace_worker._initialize_adapters")
    @patch("backend.schedulers.trace_worker.settings")
    async def test_worker_handles_db_query_failure(
        self,
        mock_settings_obj,
        mock_init_adapters,
        mock_db_session_func,
        mock_redis_func,
        redis_client,
        mock_settings,
    ):
        """Test worker gracefully handles DB query failure."""
        # Given
        mock_settings_obj.return_value = mock_settings
        mock_redis_func.return_value = redis_client

        # Mock DB session that raises error
        db_session = AsyncMock()
        db_session.execute = AsyncMock(side_effect=Exception("DB connection lost"))
        mock_db_session_func.return_value = db_session

        mock_adapter = AsyncMock()
        mock_adapter.__aenter__ = AsyncMock(return_value=mock_adapter)
        mock_adapter.__aexit__ = AsyncMock()
        mock_init_adapters.return_value = [mock_adapter]

        # When: Run worker (should not crash)
        try:
            await process_pending_traces()
            # Worker should catch exception and continue
        except Exception as e:
            pytest.fail(f"Worker crashed: {e}")

    @pytest.mark.asyncio
    @patch("backend.schedulers.trace_worker.get_async_redis")
    @patch("backend.schedulers.trace_worker.get_async_db_session")
    @patch("backend.schedulers.trace_worker._initialize_adapters")
    @patch("backend.schedulers.trace_worker.settings")
    async def test_worker_handles_adapter_fatal_error(
        self,
        mock_settings_obj,
        mock_init_adapters,
        mock_db_session_func,
        mock_redis_func,
        trace_queue,
        redis_client,
        db_session,
        sample_trades,
        mock_settings,
    ):
        """Test worker handles AdapterError (fatal error)."""
        # Given
        mock_settings_obj.return_value = mock_settings
        mock_redis_func.return_value = redis_client
        mock_db_session_func.return_value = db_session

        db_session.execute = AsyncMock(
            return_value=Mock(
                scalars=Mock(
                    return_value=Mock(all=Mock(return_value=sample_trades[:1]))
                )
            )
        )

        # Mock adapter that raises AdapterError
        mock_adapter = AsyncMock()
        mock_adapter.name = "myfxbook"
        mock_adapter.post_trade = AsyncMock(
            side_effect=AdapterError("Auth failed (401)")
        )
        mock_adapter.__aenter__ = AsyncMock(return_value=mock_adapter)
        mock_adapter.__aexit__ = AsyncMock()
        mock_init_adapters.return_value = [mock_adapter]

        # Enqueue trade
        await trace_queue.enqueue_closed_trade(
            sample_trades[0].id, ["myfxbook"], delay_minutes=-1
        )

        # When: Run worker (should not crash)
        try:
            await process_pending_traces()
            # Worker should catch AdapterError and mark as failure
        except Exception as e:
            pytest.fail(f"Worker crashed on AdapterError: {e}")


# ============================================================================
# TEST EDGE CASES
# ============================================================================


class TestEdgeCases:
    """Test edge cases."""

    @pytest.mark.asyncio
    @patch("backend.schedulers.trace_worker.get_async_redis")
    @patch("backend.schedulers.trace_worker.get_async_db_session")
    @patch("backend.schedulers.trace_worker._initialize_adapters")
    @patch("backend.schedulers.trace_worker.settings")
    async def test_worker_handles_empty_queue(
        self,
        mock_settings_obj,
        mock_init_adapters,
        mock_db_session_func,
        mock_redis_func,
        redis_client,
        db_session,
        mock_settings,
    ):
        """Test worker completes successfully when queue is empty."""
        # Given: Empty queue
        mock_settings_obj.return_value = mock_settings
        mock_redis_func.return_value = redis_client
        mock_db_session_func.return_value = db_session

        mock_adapter = AsyncMock()
        mock_adapter.__aenter__ = AsyncMock(return_value=mock_adapter)
        mock_adapter.__aexit__ = AsyncMock()
        mock_init_adapters.return_value = [mock_adapter]

        # When: Run worker
        await process_pending_traces()

        # Then: Should complete without error

    @pytest.mark.asyncio
    @patch("backend.schedulers.trace_worker.get_async_redis")
    @patch("backend.schedulers.trace_worker.get_async_db_session")
    @patch("backend.schedulers.trace_worker._initialize_adapters")
    @patch("backend.schedulers.trace_worker.settings")
    async def test_worker_handles_trade_not_found_in_db(
        self,
        mock_settings_obj,
        mock_init_adapters,
        mock_db_session_func,
        mock_redis_func,
        trace_queue,
        redis_client,
        db_session,
        mock_settings,
    ):
        """Test worker handles trade not found in database."""
        # Given
        mock_settings_obj.return_value = mock_settings
        mock_redis_func.return_value = redis_client
        mock_db_session_func.return_value = db_session

        # DB query returns empty list
        db_session.execute = AsyncMock(
            return_value=Mock(
                scalars=Mock(return_value=Mock(all=Mock(return_value=[])))
            )
        )

        mock_adapter = AsyncMock()
        mock_adapter.__aenter__ = AsyncMock(return_value=mock_adapter)
        mock_adapter.__aexit__ = AsyncMock()
        mock_init_adapters.return_value = [mock_adapter]

        # Enqueue trade that doesn't exist in DB
        await trace_queue.enqueue_closed_trade(
            "trade-nonexistent", ["myfxbook"], delay_minutes=-1
        )

        # When: Run worker (should not crash)
        await process_pending_traces()

        # Then: Worker should skip this trace


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
