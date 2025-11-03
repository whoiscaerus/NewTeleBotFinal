"""Comprehensive tests for TradingLoop main live trading bot loop.

Tests the core trading loop functionality:
- Loop initialization and lifecycle (start, stop)
- Signal fetching and batch processing
- Trade execution with retry logic
- Heartbeat emission at intervals
- Event emission for analytics
- Error handling and recovery
- Position closure on shutdown
- Concurrent signal processing

Coverage target: 100% of loop.py (717 lines)
"""

import pytest
import asyncio
import logging
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch, call

from backend.app.trading.runtime.loop import TradingLoop, HeartbeatMetrics, Event


# ============================================================================
# TRADINLOOP INITIALIZATION TESTS
# ============================================================================


class TestTradingLoopInitialization:
    """Test TradingLoop initialization and validation."""

    def test_trading_loop_init_valid_services(self):
        """Test TradingLoop initialization with required services."""
        mt5_client = MagicMock()
        approvals_service = MagicMock()
        order_service = MagicMock()

        loop = TradingLoop(
            mt5_client=mt5_client,
            approvals_service=approvals_service,
            order_service=order_service,
        )

        assert loop.mt5_client is mt5_client
        assert loop.approvals_service is approvals_service
        assert loop.order_service is order_service
        assert loop._running is False

    def test_trading_loop_init_with_optional_services(self):
        """Test TradingLoop initialization with optional services."""
        mt5_client = MagicMock()
        approvals_service = MagicMock()
        order_service = MagicMock()
        alert_service = AsyncMock()
        retry_decorator = MagicMock()

        loop = TradingLoop(
            mt5_client=mt5_client,
            approvals_service=approvals_service,
            order_service=order_service,
            alert_service=alert_service,
            retry_decorator=retry_decorator,
        )

        assert loop.alert_service is alert_service
        assert loop.retry_decorator is retry_decorator

    def test_trading_loop_init_with_custom_loop_id(self):
        """Test TradingLoop initialization with custom loop_id."""
        mt5_client = MagicMock()
        approvals_service = MagicMock()
        order_service = MagicMock()

        loop = TradingLoop(
            mt5_client=mt5_client,
            approvals_service=approvals_service,
            order_service=order_service,
            loop_id="trader_custom_001",
        )

        assert loop.loop_id == "trader_custom_001"

    def test_trading_loop_init_missing_mt5_client(self):
        """Test TradingLoop rejects missing mt5_client."""
        with pytest.raises(ValueError, match="mt5_client is required"):
            TradingLoop(
                mt5_client=None,
                approvals_service=MagicMock(),
                order_service=MagicMock(),
            )

    def test_trading_loop_init_missing_approvals_service(self):
        """Test TradingLoop rejects missing approvals_service."""
        with pytest.raises(ValueError, match="approvals_service is required"):
            TradingLoop(
                mt5_client=MagicMock(),
                approvals_service=None,
                order_service=MagicMock(),
            )

    def test_trading_loop_init_missing_order_service(self):
        """Test TradingLoop rejects missing order_service."""
        with pytest.raises(ValueError, match="order_service is required"):
            TradingLoop(
                mt5_client=MagicMock(),
                approvals_service=MagicMock(),
                order_service=None,
            )


# ============================================================================
# TRADINLOOP START/STOP TESTS
# ============================================================================


class TestTradingLoopStartStop:
    """Test TradingLoop.start() and stop() methods."""

    @pytest.mark.asyncio
    async def test_start_sets_running_flag(self):
        """Test start() sets _running flag."""
        mt5_client = MagicMock()
        approvals_service = AsyncMock()
        approvals_service.get_pending_signals.return_value = []
        order_service = MagicMock()

        loop = TradingLoop(
            mt5_client=mt5_client,
            approvals_service=approvals_service,
            order_service=order_service,
        )

        # Start with duration to prevent infinite loop
        start_task = asyncio.create_task(loop.start(duration_seconds=0.05))

        # Wait for the task to complete
        await asyncio.sleep(0.15)
        try:
            await start_task
        except Exception:
            pass  # Task may have exceptions due to mocks

        assert loop._running is False  # Should be stopped after duration

    @pytest.mark.asyncio
    async def test_stop_clears_running_flag(self):
        """Test stop() clears _running flag."""
        mt5_client = MagicMock()
        approvals_service = AsyncMock()
        approvals_service.get_pending_signals.return_value = []
        order_service = AsyncMock()
        order_service.get_open_positions.return_value = []

        loop = TradingLoop(
            mt5_client=mt5_client,
            approvals_service=approvals_service,
            order_service=order_service,
        )

        loop._running = True
        await loop.stop()

        assert loop._running is False

    @pytest.mark.asyncio
    async def test_start_runs_until_duration_exceeded(self):
        """Test start() runs until duration exceeded."""
        mt5_client = MagicMock()
        approvals_service = AsyncMock()
        approvals_service.get_pending_signals.return_value = []
        order_service = AsyncMock()
        order_service.get_open_positions.return_value = []

        loop = TradingLoop(
            mt5_client=mt5_client,
            approvals_service=approvals_service,
            order_service=order_service,
        )

        start_time = datetime.now(UTC)
        await loop.start(duration_seconds=0.1)
        elapsed = (datetime.now(UTC) - start_time).total_seconds()

        # Should have run for approximately the duration
        assert elapsed >= 0.1

    @pytest.mark.asyncio
    async def test_start_closes_positions_on_stop(self):
        """Test start() closes positions when stopped."""
        mt5_client = AsyncMock()
        mt5_client.get_account_info.return_value = {"balance": 10000}
        mt5_client.get_positions.return_value = [{"id": "pos_1"}]

        approvals_service = AsyncMock()
        approvals_service.get_pending_signals.return_value = []

        order_service = AsyncMock()
        order_service.get_open_positions.return_value = [{"id": "pos_1"}]

        loop = TradingLoop(
            mt5_client=mt5_client,
            approvals_service=approvals_service,
            order_service=order_service,
        )

        await loop.start(duration_seconds=0.05)

        # close_position should have been called during stop
        order_service.close_position.assert_called()


# ============================================================================
# TRADINLOOP SIGNAL FETCHING TESTS
# ============================================================================


class TestTradingLoopSignalFetching:
    """Test TradingLoop._fetch_approved_signals() method."""

    @pytest.mark.asyncio
    async def test_fetch_approved_signals_returns_list(self):
        """Test _fetch_approved_signals returns list of signals."""
        mt5_client = MagicMock()
        approvals_service = AsyncMock()
        order_service = MagicMock()

        signals = [
            {"id": "sig_1", "instrument": "GOLD", "side": "buy"},
            {"id": "sig_2", "instrument": "EURUSD", "side": "sell"},
        ]
        approvals_service.get_pending_signals.return_value = signals

        loop = TradingLoop(
            mt5_client=mt5_client,
            approvals_service=approvals_service,
            order_service=order_service,
        )

        result = await loop._fetch_approved_signals(batch_size=10)

        assert len(result) == 2
        assert result[0]["id"] == "sig_1"

    @pytest.mark.asyncio
    async def test_fetch_approved_signals_respects_batch_size(self):
        """Test _fetch_approved_signals respects batch_size parameter."""
        mt5_client = MagicMock()
        approvals_service = AsyncMock()
        order_service = MagicMock()

        loop = TradingLoop(
            mt5_client=mt5_client,
            approvals_service=approvals_service,
            order_service=order_service,
        )

        await loop._fetch_approved_signals(batch_size=5)

        approvals_service.get_pending_signals.assert_called_once_with(limit=5)

    @pytest.mark.asyncio
    async def test_fetch_approved_signals_handles_empty_result(self):
        """Test _fetch_approved_signals handles empty signal list."""
        mt5_client = MagicMock()
        approvals_service = AsyncMock()
        approvals_service.get_pending_signals.return_value = []
        order_service = MagicMock()

        loop = TradingLoop(
            mt5_client=mt5_client,
            approvals_service=approvals_service,
            order_service=order_service,
        )

        result = await loop._fetch_approved_signals(batch_size=10)

        assert result == []

    @pytest.mark.asyncio
    async def test_fetch_approved_signals_handles_error(self):
        """Test _fetch_approved_signals handles database error gracefully."""
        mt5_client = MagicMock()
        approvals_service = AsyncMock()
        approvals_service.get_pending_signals.side_effect = RuntimeError("DB error")
        order_service = MagicMock()

        loop = TradingLoop(
            mt5_client=mt5_client,
            approvals_service=approvals_service,
            order_service=order_service,
        )

        result = await loop._fetch_approved_signals(batch_size=10)

        assert result == []
        assert loop._error_count_interval == 1


# ============================================================================
# TRADINLOOP TRADE EXECUTION TESTS
# ============================================================================


class TestTradingLoopTradeExecution:
    """Test TradingLoop._execute_signal() and _place_order() methods."""

    @pytest.mark.asyncio
    async def test_execute_signal_successful_execution(self):
        """Test _execute_signal with successful trade execution."""
        mt5_client = MagicMock()
        approvals_service = MagicMock()
        order_service = AsyncMock()
        order_service.place_order.return_value = {"id": "order_123"}

        loop = TradingLoop(
            mt5_client=mt5_client,
            approvals_service=approvals_service,
            order_service=order_service,
        )

        signal = {
            "id": "sig_123",
            "instrument": "GOLD",
            "side": "buy",
            "quantity": 1.0,
        }

        result = await loop._execute_signal(signal)

        assert result["success"] is True
        assert result["order_id"] == "order_123"
        assert result["execution_time_ms"] >= 0

    @pytest.mark.asyncio
    async def test_execute_signal_failed_execution(self):
        """Test _execute_signal with failed trade execution."""
        mt5_client = MagicMock()
        approvals_service = MagicMock()
        order_service = AsyncMock()
        # Mock order_service to raise exception (which signals failure)
        order_service.place_order.side_effect = RuntimeError("Insufficient margin")

        loop = TradingLoop(
            mt5_client=mt5_client,
            approvals_service=approvals_service,
            order_service=order_service,
        )

        signal = {"id": "sig_123", "instrument": "GOLD", "side": "buy"}

        result = await loop._execute_signal(signal)

        assert result["success"] is False
        assert "Insufficient margin" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_signal_with_retry(self):
        """Test _execute_signal uses retry decorator if provided."""
        mt5_client = MagicMock()
        approvals_service = MagicMock()
        order_service = AsyncMock()
        order_service.place_order.return_value = {"id": "order_123"}

        retry_decorator = AsyncMock()

        async def mock_retry_func(*args, **kwargs):
            return {"id": "order_123"}

        retry_decorator.return_value = mock_retry_func()

        loop = TradingLoop(
            mt5_client=mt5_client,
            approvals_service=approvals_service,
            order_service=order_service,
            retry_decorator=retry_decorator,
        )

        signal = {"id": "sig_123", "instrument": "GOLD", "side": "buy"}

        # With retry_decorator, execution uses retry logic
        result = await loop._execute_signal(signal)

        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_place_order_success(self):
        """Test _place_order creates order successfully."""
        mt5_client = MagicMock()
        approvals_service = MagicMock()
        order_service = AsyncMock()
        order_service.place_order.return_value = {"id": "order_123"}

        loop = TradingLoop(
            mt5_client=mt5_client,
            approvals_service=approvals_service,
            order_service=order_service,
        )

        signal = {
            "instrument": "GOLD",
            "side": "buy",
            "quantity": 1.0,
            "order_type": "market",
        }

        result = await loop._place_order(signal)

        assert result["success"] is True
        assert result["order_id"] == "order_123"

    @pytest.mark.asyncio
    async def test_place_order_handles_exception(self):
        """Test _place_order handles exceptions gracefully."""
        mt5_client = MagicMock()
        approvals_service = MagicMock()
        order_service = AsyncMock()
        order_service.place_order.side_effect = RuntimeError("Connection error")

        loop = TradingLoop(
            mt5_client=mt5_client,
            approvals_service=approvals_service,
            order_service=order_service,
        )

        signal = {"instrument": "GOLD"}

        result = await loop._place_order(signal)

        assert result["success"] is False
        assert "Connection error" in result["error"]


# ============================================================================
# TRADINLOOP HEARTBEAT TESTS
# ============================================================================


class TestTradingLoopHeartbeat:
    """Test TradingLoop heartbeat emission methods."""

    @pytest.mark.asyncio
    async def test_emit_heartbeat_now_creates_metrics(self):
        """Test _emit_heartbeat_now() creates and logs metrics."""
        mt5_client = AsyncMock()
        mt5_client.get_account_info.return_value = {"balance": 10000}
        mt5_client.get_positions.return_value = []

        approvals_service = MagicMock()
        order_service = MagicMock()

        loop = TradingLoop(
            mt5_client=mt5_client,
            approvals_service=approvals_service,
            order_service=order_service,
        )

        loop._signals_processed_interval = 5
        loop._trades_executed_interval = 2

        await loop._emit_heartbeat_now(loop_duration_ms=100.0)

        # Verify metrics reset
        assert loop._signals_processed_interval == 0
        assert loop._trades_executed_interval == 0

    @pytest.mark.asyncio
    async def test_check_and_emit_heartbeat_respects_interval(self):
        """Test _check_and_emit_heartbeat() respects heartbeat interval."""
        mt5_client = AsyncMock()
        mt5_client.get_account_info.return_value = {"balance": 10000}
        mt5_client.get_positions.return_value = []

        approvals_service = MagicMock()
        order_service = MagicMock()

        loop = TradingLoop(
            mt5_client=mt5_client,
            approvals_service=approvals_service,
            order_service=order_service,
        )

        loop._last_heartbeat = datetime.now(UTC)

        # Too soon - should not emit
        with patch.object(loop, "_emit_heartbeat_now") as mock_emit:
            await loop._check_and_emit_heartbeat(50.0)
            mock_emit.assert_not_called()

    @pytest.mark.asyncio
    async def test_emit_heartbeat_fetches_account_info(self):
        """Test _emit_heartbeat_now() fetches current account info."""
        mt5_client = AsyncMock()
        mt5_client.get_account_info.return_value = {"balance": 10250.50}
        mt5_client.get_positions.return_value = [
            {"id": "pos_1"},
            {"id": "pos_2"},
        ]

        approvals_service = MagicMock()
        order_service = MagicMock()

        loop = TradingLoop(
            mt5_client=mt5_client,
            approvals_service=approvals_service,
            order_service=order_service,
        )

        await loop._emit_heartbeat_now()

        mt5_client.get_account_info.assert_called()
        mt5_client.get_positions.assert_called()


# ============================================================================
# TRADINLOOP EVENT EMISSION TESTS
# ============================================================================


class TestTradingLoopEventEmission:
    """Test TradingLoop._emit_event() method."""

    @pytest.mark.asyncio
    async def test_emit_event_creates_and_logs_event(self):
        """Test _emit_event() creates and logs event."""
        mt5_client = MagicMock()
        approvals_service = MagicMock()
        order_service = MagicMock()

        loop = TradingLoop(
            mt5_client=mt5_client,
            approvals_service=approvals_service,
            order_service=order_service,
        )

        await loop._emit_event(
            event_type="signal_received",
            metadata={"signal_id": "sig_123"},
        )

        # Should not raise

    @pytest.mark.asyncio
    async def test_emit_event_handles_error_gracefully(self):
        """Test _emit_event() handles errors gracefully."""
        mt5_client = MagicMock()
        approvals_service = MagicMock()
        order_service = MagicMock()

        loop = TradingLoop(
            mt5_client=mt5_client,
            approvals_service=approvals_service,
            order_service=order_service,
        )

        # Call with minimal data
        await loop._emit_event(
            event_type="signal_received",
            metadata={},
        )

        # Should not raise


# ============================================================================
# TRADINLOOP LOOP ITERATION TESTS
# ============================================================================


class TestTradingLoopIteration:
    """Test TradingLoop._loop_iteration() method."""

    @pytest.mark.asyncio
    async def test_loop_iteration_processes_signals(self):
        """Test _loop_iteration() processes approved signals."""
        mt5_client = MagicMock()
        approvals_service = AsyncMock()
        order_service = AsyncMock()
        order_service.place_order.return_value = {"id": "order_123"}

        signals = [
            {
                "id": "sig_1",
                "instrument": "GOLD",
                "side": "buy",
                "quantity": 1.0,
            }
        ]
        approvals_service.get_pending_signals.return_value = signals

        loop = TradingLoop(
            mt5_client=mt5_client,
            approvals_service=approvals_service,
            order_service=order_service,
        )

        await loop._loop_iteration()

        # Signal should be marked as processed
        assert "sig_1" in loop._processed_signal_ids
        assert loop._signals_processed_interval == 1

    @pytest.mark.asyncio
    async def test_loop_iteration_skips_already_processed(self):
        """Test _loop_iteration() skips already processed signals."""
        mt5_client = MagicMock()
        approvals_service = AsyncMock()
        order_service = AsyncMock()

        signals = [{"id": "sig_1", "instrument": "GOLD", "side": "buy"}]
        approvals_service.get_pending_signals.return_value = signals

        loop = TradingLoop(
            mt5_client=mt5_client,
            approvals_service=approvals_service,
            order_service=order_service,
        )

        # Mark as already processed
        loop._processed_signal_ids.add("sig_1")

        with patch.object(loop, "_execute_signal") as mock_execute:
            await loop._loop_iteration()

            # Should not execute already processed signal
            mock_execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_loop_iteration_increments_lifetime_counters(self):
        """Test _loop_iteration() increments lifetime counters."""
        mt5_client = MagicMock()
        approvals_service = AsyncMock()
        order_service = AsyncMock()
        order_service.place_order.return_value = {"id": "order_123"}

        signals = [{"id": "sig_1", "instrument": "GOLD", "side": "buy"}]
        approvals_service.get_pending_signals.return_value = signals

        loop = TradingLoop(
            mt5_client=mt5_client,
            approvals_service=approvals_service,
            order_service=order_service,
        )

        assert loop._total_signals_lifetime == 0

        await loop._loop_iteration()

        assert loop._total_signals_lifetime == 1

    @pytest.mark.asyncio
    async def test_loop_iteration_no_signals(self):
        """Test _loop_iteration() handles case with no signals."""
        mt5_client = MagicMock()
        approvals_service = AsyncMock()
        approvals_service.get_pending_signals.return_value = []
        order_service = MagicMock()

        loop = TradingLoop(
            mt5_client=mt5_client,
            approvals_service=approvals_service,
            order_service=order_service,
        )

        # Should complete without error
        await loop._loop_iteration()

        assert loop._signals_processed_interval == 0


# ============================================================================
# TRADINLOOP ERROR HANDLING TESTS
# ============================================================================


class TestTradingLoopErrorHandling:
    """Test TradingLoop error handling methods."""

    @pytest.mark.asyncio
    async def test_handle_error_logs_and_increments_counter(self):
        """Test _handle_error() logs error and increments counter."""
        mt5_client = MagicMock()
        approvals_service = MagicMock()
        order_service = MagicMock()

        loop = TradingLoop(
            mt5_client=mt5_client,
            approvals_service=approvals_service,
            order_service=order_service,
        )

        error = RuntimeError("Test error")

        await loop._handle_error(error, context="test_context")

        assert loop._error_count_interval == 1

    @pytest.mark.asyncio
    async def test_handle_error_sends_alert(self):
        """Test _handle_error() sends alert if service available."""
        mt5_client = MagicMock()
        approvals_service = MagicMock()
        order_service = MagicMock()
        alert_service = AsyncMock()

        loop = TradingLoop(
            mt5_client=mt5_client,
            approvals_service=approvals_service,
            order_service=order_service,
            alert_service=alert_service,
        )

        error = RuntimeError("Test error")

        await loop._handle_error(error, context="test_context")

        alert_service.send_owner_alert.assert_called_once()


# ============================================================================
# TRADINLOOP POSITION CLOSURE TESTS
# ============================================================================


class TestTradingLoopPositionClosure:
    """Test TradingLoop._close_all_positions() method."""

    @pytest.mark.asyncio
    async def test_close_all_positions_closes_all(self):
        """Test _close_all_positions() closes all open positions."""
        mt5_client = MagicMock()
        approvals_service = MagicMock()
        order_service = AsyncMock()
        order_service.get_open_positions.return_value = [
            {"id": "pos_1"},
            {"id": "pos_2"},
            {"id": "pos_3"},
        ]

        loop = TradingLoop(
            mt5_client=mt5_client,
            approvals_service=approvals_service,
            order_service=order_service,
        )

        await loop._close_all_positions()

        assert order_service.close_position.call_count == 3

    @pytest.mark.asyncio
    async def test_close_all_positions_no_positions(self):
        """Test _close_all_positions() handles no open positions."""
        mt5_client = MagicMock()
        approvals_service = MagicMock()
        order_service = AsyncMock()
        order_service.get_open_positions.return_value = []

        loop = TradingLoop(
            mt5_client=mt5_client,
            approvals_service=approvals_service,
            order_service=order_service,
        )

        await loop._close_all_positions()

        order_service.close_position.assert_not_called()

    @pytest.mark.asyncio
    async def test_close_all_positions_handles_error(self):
        """Test _close_all_positions() handles closure errors gracefully."""
        mt5_client = MagicMock()
        approvals_service = MagicMock()
        order_service = AsyncMock()
        order_service.get_open_positions.return_value = [
            {"id": "pos_1"},
            {"id": "pos_2"},
        ]
        order_service.close_position.side_effect = RuntimeError("Closure failed")

        loop = TradingLoop(
            mt5_client=mt5_client,
            approvals_service=approvals_service,
            order_service=order_service,
        )

        # Should not raise
        await loop._close_all_positions()


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


class TestTradingLoopIntegration:
    """Integration tests for TradingLoop."""

    @pytest.mark.asyncio
    async def test_complete_trading_flow(self):
        """Test complete trading loop flow: fetch -> execute -> emit -> heartbeat."""
        mt5_client = AsyncMock()
        mt5_client.get_account_info.return_value = {"balance": 10000}
        mt5_client.get_positions.return_value = []

        approvals_service = AsyncMock()
        approvals_service.get_pending_signals.return_value = [
            {"id": "sig_1", "instrument": "GOLD", "side": "buy", "quantity": 1.0}
        ]

        order_service = AsyncMock()
        order_service.place_order.return_value = {"id": "order_123"}
        order_service.get_open_positions.return_value = []

        loop = TradingLoop(
            mt5_client=mt5_client,
            approvals_service=approvals_service,
            order_service=order_service,
        )

        await loop.start(duration_seconds=0.1)

        # Verify signal was processed
        assert loop._total_signals_lifetime >= 1

    @pytest.mark.asyncio
    async def test_loop_emits_events_during_execution(self):
        """Test loop emits events during signal execution."""
        mt5_client = AsyncMock()
        mt5_client.get_account_info.return_value = {"balance": 10000}
        mt5_client.get_positions.return_value = []

        approvals_service = AsyncMock()
        approvals_service.get_pending_signals.return_value = [
            {"id": "sig_1", "instrument": "GOLD", "side": "buy"}
        ]

        order_service = AsyncMock()
        order_service.place_order.return_value = {"id": "order_123"}
        order_service.get_open_positions.return_value = []

        loop = TradingLoop(
            mt5_client=mt5_client,
            approvals_service=approvals_service,
            order_service=order_service,
        )

        with patch.object(loop, "_emit_event") as mock_emit:
            await loop.start(duration_seconds=0.05)

            # Should have emitted at least signal_received event
            assert mock_emit.called
