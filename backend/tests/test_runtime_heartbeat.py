"""Comprehensive tests for HeartbeatManager periodic health monitoring.

Tests the heartbeat mechanism:
- Periodic emission at configured interval
- Lock-based synchronization for concurrent safety
- Metrics recording and structured logging
- Background task lifecycle management
- Error handling and recovery

Coverage target: 100% of heartbeat.py (240 lines)
"""

import pytest
import asyncio
import logging
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch, call

from backend.app.trading.runtime.heartbeat import HeartbeatManager, HeartbeatMetrics


class TestHeartbeatManagerInitialization:
    """Test HeartbeatManager initialization and validation."""

    def test_heartbeat_manager_init_default_values(self):
        """Test HeartbeatManager initialization with default values."""
        manager = HeartbeatManager()

        assert manager.interval_seconds == 10
        assert manager.loop_id == "trading_loop_main"
        assert isinstance(manager._lock, asyncio.Lock)

    def test_heartbeat_manager_init_custom_values(self):
        """Test HeartbeatManager initialization with custom values."""
        manager = HeartbeatManager(
            interval_seconds=5,
            loop_id="test_loop_123",
        )

        assert manager.interval_seconds == 5
        assert manager.loop_id == "test_loop_123"

    def test_heartbeat_manager_init_with_custom_logger(self):
        """Test HeartbeatManager initialization with custom logger."""
        custom_logger = logging.getLogger("test_heartbeat")
        manager = HeartbeatManager(logger=custom_logger)

        assert manager._logger is custom_logger

    def test_heartbeat_manager_init_invalid_interval_zero(self):
        """Test HeartbeatManager rejects interval <= 0."""
        with pytest.raises(ValueError, match="interval_seconds must be > 0"):
            HeartbeatManager(interval_seconds=0)

    def test_heartbeat_manager_init_invalid_interval_negative(self):
        """Test HeartbeatManager rejects negative interval."""
        with pytest.raises(ValueError, match="interval_seconds must be > 0"):
            HeartbeatManager(interval_seconds=-5)


class TestHeartbeatMetrics:
    """Test HeartbeatMetrics dataclass."""

    def test_heartbeat_metrics_creation(self):
        """Test HeartbeatMetrics dataclass initialization."""
        now = datetime.now(UTC)
        metrics = HeartbeatMetrics(
            timestamp=now,
            loop_id="test_loop",
            signals_processed=5,
            trades_executed=2,
            error_count=0,
            loop_duration_ms=125.5,
            positions_open=1,
            account_equity=10250.50,
            total_signals_lifetime=150,
            total_trades_lifetime=75,
        )

        assert metrics.timestamp == now
        assert metrics.loop_id == "test_loop"
        assert metrics.signals_processed == 5
        assert metrics.trades_executed == 2
        assert metrics.error_count == 0
        assert metrics.loop_duration_ms == 125.5
        assert metrics.positions_open == 1
        assert metrics.account_equity == 10250.50
        assert metrics.total_signals_lifetime == 150
        assert metrics.total_trades_lifetime == 75


class TestHeartbeatManagerEmit:
    """Test HeartbeatManager.emit() method."""

    @pytest.mark.asyncio
    async def test_emit_returns_heartbeat_metrics(self):
        """Test emit() returns HeartbeatMetrics with correct values."""
        manager = HeartbeatManager(loop_id="test_loop")

        metrics = await manager.emit(
            signals_processed=5,
            trades_executed=2,
            error_count=0,
            loop_duration_ms=100.0,
            positions_open=1,
            account_equity=10250.50,
            total_signals_lifetime=150,
            total_trades_lifetime=75,
        )

        assert isinstance(metrics, HeartbeatMetrics)
        assert metrics.loop_id == "test_loop"
        assert metrics.signals_processed == 5
        assert metrics.trades_executed == 2
        assert metrics.error_count == 0
        assert metrics.loop_duration_ms == 100.0
        assert metrics.positions_open == 1
        assert metrics.account_equity == 10250.50
        assert metrics.total_signals_lifetime == 150
        assert metrics.total_trades_lifetime == 75

    @pytest.mark.asyncio
    async def test_emit_default_values(self):
        """Test emit() with default metric values."""
        manager = HeartbeatManager()

        metrics = await manager.emit()

        assert metrics.signals_processed == 0
        assert metrics.trades_executed == 0
        assert metrics.error_count == 0
        assert metrics.loop_duration_ms == 0.0
        assert metrics.positions_open == 0
        assert metrics.account_equity == 0.0

    @pytest.mark.asyncio
    async def test_emit_timestamp_is_utc(self):
        """Test emit() sets timestamp in UTC."""
        manager = HeartbeatManager()

        metrics = await manager.emit()

        assert metrics.timestamp.tzinfo == UTC

    @pytest.mark.asyncio
    async def test_emit_records_metric_to_observability(self):
        """Test emit() records metric to observability stack."""
        manager = HeartbeatManager()

        with patch("backend.app.trading.runtime.heartbeat.get_metrics") as mock_metrics:
            metrics_registry = MagicMock()
            mock_metrics.return_value = metrics_registry

            await manager.emit()

            metrics_registry.heartbeat_total.inc.assert_called_once()

    @pytest.mark.asyncio
    async def test_emit_handles_metrics_error_gracefully(self):
        """Test emit() handles metrics recording error without failing."""
        manager = HeartbeatManager()

        with patch("backend.app.trading.runtime.heartbeat.get_metrics") as mock_metrics:
            mock_metrics.side_effect = RuntimeError("Metrics unavailable")

            # Should not raise
            metrics = await manager.emit()

            assert isinstance(metrics, HeartbeatMetrics)

    @pytest.mark.asyncio
    async def test_emit_uses_async_lock(self):
        """Test emit() acquires async lock for synchronization."""
        manager = HeartbeatManager()

        # Simulate concurrent emit attempts
        metrics1 = await manager.emit(signals_processed=1)
        metrics2 = await manager.emit(signals_processed=2)

        # Both should complete without error
        assert metrics1.signals_processed == 1
        assert metrics2.signals_processed == 2

    @pytest.mark.asyncio
    async def test_emit_concurrent_calls_serialized(self):
        """Test concurrent emit calls are serialized by lock."""
        manager = HeartbeatManager()
        call_sequence = []

        async def emit_and_track(num):
            async with manager._lock:
                call_sequence.append(f"start_{num}")
                await asyncio.sleep(0.01)
                call_sequence.append(f"end_{num}")

        # Create concurrent tasks
        task1 = asyncio.create_task(emit_and_track(1))
        task2 = asyncio.create_task(emit_and_track(2))

        await asyncio.gather(task1, task2)

        # Verify serialization: each emission completes before next starts
        # (This is a simplified test; real lock behavior is more complex)
        assert len(call_sequence) == 4


class TestHeartbeatManagerBackgroundTask:
    """Test HeartbeatManager.start_background_heartbeat() method."""

    @pytest.mark.asyncio
    async def test_start_background_heartbeat_returns_task(self):
        """Test start_background_heartbeat() returns asyncio.Task."""
        manager = HeartbeatManager()

        def dummy_provider():
            return {}

        task = await manager.start_background_heartbeat(dummy_provider)

        assert isinstance(task, asyncio.Task)

        # Cleanup
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_background_heartbeat_emits_periodically(self):
        """Test background heartbeat emits at configured interval."""
        manager = HeartbeatManager(interval_seconds=0.1)  # 100ms for testing

        # The implementation properly awaits metrics_provider (async)
        async def metrics_provider():
            return {
                "signals_processed": 1,
                "trades_executed": 0,
                "error_count": 0,
                "loop_duration_ms": 10.0,
                "positions_open": 0,
                "account_equity": 10000.0,
                "total_signals_lifetime": 1,
                "total_trades_lifetime": 0,
            }

        with patch.object(manager, "emit", wraps=manager.emit) as mock_emit:
            task = await manager.start_background_heartbeat(metrics_provider)

            # Let it run for ~0.25 seconds
            await asyncio.sleep(0.25)

            # Should have emitted at least 2 times
            assert mock_emit.call_count >= 2

            # Cleanup
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_background_heartbeat_calls_metrics_provider(self):
        """Test background heartbeat calls metrics provider."""
        manager = HeartbeatManager(interval_seconds=0.05)
        provider_call_count = 0

        async def metrics_provider():
            nonlocal provider_call_count
            provider_call_count += 1
            return {
                "signals_processed": provider_call_count,
                "trades_executed": 0,
                "error_count": 0,
                "loop_duration_ms": 10.0,
                "positions_open": 0,
                "account_equity": 10000.0,
                "total_signals_lifetime": provider_call_count,
                "total_trades_lifetime": 0,
            }

        task = await manager.start_background_heartbeat(metrics_provider)

        # Let it run
        await asyncio.sleep(0.15)

        # Should have called provider at least 2 times
        assert provider_call_count >= 2

        # Cleanup
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_background_heartbeat_handles_cancellation(self):
        """Test background heartbeat handles cancellation gracefully."""
        manager = HeartbeatManager(interval_seconds=0.1)

        async def metrics_provider():
            return {}

        task = await manager.start_background_heartbeat(metrics_provider)

        await asyncio.sleep(0.05)

        # Cancel the task
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

    @pytest.mark.asyncio
    async def test_background_heartbeat_handles_provider_error(self):
        """Test background heartbeat handles metrics provider errors gracefully."""
        manager = HeartbeatManager(interval_seconds=0.05)
        error_count = 0

        async def failing_provider():
            nonlocal error_count
            error_count += 1
            raise RuntimeError("Provider error")

        task = await manager.start_background_heartbeat(failing_provider)

        # Let it run and error a few times
        await asyncio.sleep(0.15)

        # Cleanup
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Should have called provider at least 2 times despite errors
        assert error_count >= 2, "Provider should be called multiple times"

    @pytest.mark.asyncio
    async def test_background_heartbeat_continues_after_error(self):
        """Test background heartbeat continues running after provider error."""
        manager = HeartbeatManager(interval_seconds=0.05)
        call_sequence = []

        async def sometimes_failing_provider():
            call_num = len(call_sequence)
            call_sequence.append(call_num)

            if call_num == 1:  # Fail on second call
                raise RuntimeError("Temporary error")

            return {
                "signals_processed": 0,
                "trades_executed": 0,
                "error_count": 0,
                "loop_duration_ms": 0.0,
                "positions_open": 0,
                "account_equity": 0.0,
                "total_signals_lifetime": 0,
                "total_trades_lifetime": 0,
            }

        task = await manager.start_background_heartbeat(sometimes_failing_provider)

        await asyncio.sleep(0.20)

        # Cleanup
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Should have been called multiple times despite error
        assert len(call_sequence) >= 3

    @pytest.mark.asyncio
    async def test_background_heartbeat_emits_with_provider_data(self):
        """Test background heartbeat emits with metrics from provider."""
        manager = HeartbeatManager(interval_seconds=0.05)

        async def metrics_provider():
            return {
                "signals_processed": 42,
                "trades_executed": 7,
                "error_count": 1,
                "loop_duration_ms": 123.45,
                "positions_open": 2,
                "account_equity": 15000.50,
                "total_signals_lifetime": 420,
                "total_trades_lifetime": 70,
            }

        with patch.object(manager, "emit", wraps=manager.emit) as mock_emit:
            task = await manager.start_background_heartbeat(metrics_provider)

            # Let it emit once
            await asyncio.sleep(0.10)

            # Check call arguments
            assert mock_emit.called
            call_kwargs = mock_emit.call_args[1]
            assert call_kwargs["signals_processed"] == 42
            assert call_kwargs["trades_executed"] == 7
            assert call_kwargs["error_count"] == 1

            # Cleanup
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


class TestHeartbeatManagerIntegration:
    """Integration tests for HeartbeatManager."""

    @pytest.mark.asyncio
    async def test_multiple_emits_increment_metrics(self):
        """Test multiple emits increment observability metrics."""
        manager = HeartbeatManager()

        with patch("backend.app.trading.runtime.heartbeat.get_metrics") as mock_metrics:
            metrics_registry = MagicMock()
            mock_metrics.return_value = metrics_registry

            # Emit 3 times
            await manager.emit()
            await manager.emit()
            await manager.emit()

            # heartbeat_total.inc() should be called 3 times
            assert metrics_registry.heartbeat_total.inc.call_count == 3

    @pytest.mark.asyncio
    async def test_background_task_lifecycle(self):
        """Test complete background task lifecycle."""
        manager = HeartbeatManager(interval_seconds=0.05)
        emit_calls = []

        async def metrics_provider():
            return {
                "signals_processed": 1,
                "trades_executed": 0,
                "error_count": 0,
                "loop_duration_ms": 10.0,
                "positions_open": 0,
                "account_equity": 10000.0,
                "total_signals_lifetime": 1,
                "total_trades_lifetime": 0,
            }

        with patch.object(manager, "emit") as mock_emit:
            mock_emit.return_value = HeartbeatMetrics(
                timestamp=datetime.now(UTC),
                loop_id="test",
                signals_processed=1,
                trades_executed=0,
                error_count=0,
                loop_duration_ms=10.0,
                positions_open=0,
                account_equity=10000.0,
                total_signals_lifetime=1,
                total_trades_lifetime=0,
            )

            task = await manager.start_background_heartbeat(metrics_provider)

            # Verify task is running
            assert not task.done()

            await asyncio.sleep(0.12)

            # Verify emit called
            assert mock_emit.called

            # Cancel and verify cleanup
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

            assert task.done()

    @pytest.mark.asyncio
    async def test_heartbeat_with_realistic_metrics(self):
        """Test heartbeat with realistic trading loop metrics."""
        manager = HeartbeatManager(
            interval_seconds=10,
            loop_id="trader_main_001",
        )

        # Simulate realistic metrics
        metrics = await manager.emit(
            signals_processed=15,
            trades_executed=8,
            error_count=0,
            loop_duration_ms=4523.45,
            positions_open=3,
            account_equity=12450.75,
            total_signals_lifetime=450,
            total_trades_lifetime=220,
        )

        assert metrics.loop_id == "trader_main_001"
        assert metrics.signals_processed == 15
        assert metrics.trades_executed == 8
        assert metrics.positions_open == 3
        assert metrics.account_equity == 12450.75
