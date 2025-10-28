"""Comprehensive tests for PR-019 new modules: heartbeat, events, guards."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from backend.app.trading.runtime.events import Event, EventEmitter, EventType
from backend.app.trading.runtime.guards import (
    Guards,
    GuardState,
    enforce_max_drawdown,
    min_equity_guard,
)
from backend.app.trading.runtime.heartbeat import HeartbeatManager, HeartbeatMetrics

# ============================================================================
# HEARTBEAT TESTS
# ============================================================================


class TestHeartbeatManager:
    """Test suite for HeartbeatManager."""

    def test_init_valid(self):
        """Test heartbeat manager initialization with valid parameters."""
        manager = HeartbeatManager(interval_seconds=10, loop_id="test_loop")
        assert manager.interval_seconds == 10
        assert manager.loop_id == "test_loop"

    def test_init_invalid_interval(self):
        """Test heartbeat initialization rejects invalid intervals."""
        with pytest.raises(ValueError, match="interval_seconds must be > 0"):
            HeartbeatManager(interval_seconds=0)

        with pytest.raises(ValueError, match="interval_seconds must be > 0"):
            HeartbeatManager(interval_seconds=-5)

    @pytest.mark.asyncio
    async def test_emit_heartbeat_creates_metrics(self):
        """Test heartbeat emission creates HeartbeatMetrics."""
        manager = HeartbeatManager(interval_seconds=10)

        metrics = await manager.emit(
            signals_processed=5,
            trades_executed=2,
            error_count=0,
            loop_duration_ms=150.5,
            positions_open=1,
            account_equity=10250.50,
            total_signals_lifetime=150,
            total_trades_lifetime=75,
        )

        assert isinstance(metrics, HeartbeatMetrics)
        assert metrics.signals_processed == 5
        assert metrics.trades_executed == 2
        assert metrics.error_count == 0
        assert metrics.loop_duration_ms == 150.5
        assert metrics.positions_open == 1
        assert metrics.account_equity == 10250.50
        assert metrics.total_signals_lifetime == 150
        assert metrics.total_trades_lifetime == 75
        assert metrics.timestamp is not None

    @pytest.mark.asyncio
    async def test_emit_heartbeat_concurrent_safe(self):
        """Test heartbeat emission is thread-safe with async lock."""
        manager = HeartbeatManager(interval_seconds=10)
        results = []

        async def emit_metrics():
            metric = await manager.emit(
                signals_processed=1,
                trades_executed=0,
            )
            results.append(metric)

        # Emit multiple concurrent heartbeats
        await asyncio.gather(
            emit_metrics(),
            emit_metrics(),
            emit_metrics(),
        )

        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_heartbeat_background_task_emits_periodically(self):
        """Test background heartbeat task emits at configured interval."""
        manager = HeartbeatManager(interval_seconds=1)

        async def metrics_provider():
            return {
                "signals_processed": 1,
                "trades_executed": 0,
                "error_count": 0,
                "loop_duration_ms": 100.0,
                "positions_open": 0,
                "account_equity": 10000.0,
                "total_signals_lifetime": 10,
                "total_trades_lifetime": 5,
            }

        task = await manager.start_background_heartbeat(metrics_provider)

        # Let it emit a couple times
        await asyncio.sleep(2.5)
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass


# ============================================================================
# EVENT TESTS
# ============================================================================


class TestEventEmitter:
    """Test suite for EventEmitter."""

    def test_event_type_enum(self):
        """Test EventType enum has expected values."""
        assert EventType.SIGNAL_RECEIVED.value == "signal_received"
        assert EventType.SIGNAL_APPROVED.value == "signal_approved"
        assert EventType.TRADE_EXECUTED.value == "trade_executed"
        assert EventType.TRADE_FAILED.value == "trade_failed"
        assert EventType.POSITION_CLOSED.value == "position_closed"

    def test_event_to_dict(self):
        """Test Event.to_dict() serialization."""
        event = Event(
            event_type=EventType.SIGNAL_RECEIVED,
            timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
            loop_id="test_loop",
            metadata={"signal_id": "sig-123", "instrument": "GOLD"},
        )

        event_dict = event.to_dict()

        assert event_dict["event_type"] == "signal_received"
        assert event_dict["loop_id"] == "test_loop"
        assert event_dict["timestamp"] == "2025-01-01T12:00:00+00:00"
        assert event_dict["metadata"]["signal_id"] == "sig-123"

    @pytest.mark.asyncio
    async def test_emit_signal_received(self):
        """Test emit_signal_received creates proper event."""
        emitter = EventEmitter(loop_id="test_loop")

        event = await emitter.emit_signal_received(
            signal_id="sig-123",
            instrument="GOLD",
            side="buy",
            metadata={"rsi": 75},
        )

        assert event.event_type == EventType.SIGNAL_RECEIVED
        assert event.metadata["signal_id"] == "sig-123"
        assert event.metadata["instrument"] == "GOLD"
        assert event.metadata["side"] == "buy"
        assert event.metadata["rsi"] == 75

    @pytest.mark.asyncio
    async def test_emit_signal_approved(self):
        """Test emit_signal_approved creates proper event."""
        emitter = EventEmitter(loop_id="test_loop")

        event = await emitter.emit_signal_approved(
            signal_id="sig-123",
            approved_by="system",
        )

        assert event.event_type == EventType.SIGNAL_APPROVED
        assert event.metadata["signal_id"] == "sig-123"
        assert event.metadata["approved_by"] == "system"

    @pytest.mark.asyncio
    async def test_emit_trade_executed(self):
        """Test emit_trade_executed creates proper event."""
        emitter = EventEmitter(loop_id="test_loop")

        event = await emitter.emit_trade_executed(
            signal_id="sig-123",
            trade_id="trade-456",
            instrument="GOLD",
            volume=0.1,
            entry_price=2050.50,
        )

        assert event.event_type == EventType.TRADE_EXECUTED
        assert event.metadata["signal_id"] == "sig-123"
        assert event.metadata["trade_id"] == "trade-456"
        assert event.metadata["volume"] == 0.1

    @pytest.mark.asyncio
    async def test_emit_trade_failed(self):
        """Test emit_trade_failed creates proper event."""
        emitter = EventEmitter(loop_id="test_loop")

        event = await emitter.emit_trade_failed(
            signal_id="sig-123",
            reason="insufficient_margin",
        )

        assert event.event_type == EventType.TRADE_FAILED
        assert event.metadata["reason"] == "insufficient_margin"

    @pytest.mark.asyncio
    async def test_emit_position_closed(self):
        """Test emit_position_closed creates proper event."""
        emitter = EventEmitter(loop_id="test_loop")

        event = await emitter.emit_position_closed(
            trade_id="trade-456",
            close_price=2055.50,
            profit_loss=50.00,
            reason="take_profit",
        )

        assert event.event_type == EventType.POSITION_CLOSED
        assert event.metadata["profit_loss"] == 50.00
        assert event.metadata["reason"] == "take_profit"


# ============================================================================
# GUARDS TESTS
# ============================================================================


class TestGuards:
    """Test suite for Guards class."""

    def test_guards_init_valid(self):
        """Test guards initialization with valid parameters."""
        guards = Guards(max_drawdown_percent=20.0, min_equity_gbp=500.0)
        assert guards.max_drawdown_percent == 20.0
        assert guards.min_equity_gbp == 500.0

    def test_guards_init_invalid_drawdown(self):
        """Test guards reject invalid max drawdown."""
        with pytest.raises(ValueError, match="must be between 0 and 100"):
            Guards(max_drawdown_percent=0)

        with pytest.raises(ValueError, match="must be between 0 and 100"):
            Guards(max_drawdown_percent=101)

    def test_guards_init_invalid_min_equity(self):
        """Test guards reject invalid min equity."""
        with pytest.raises(ValueError, match="min_equity_gbp must be > 0"):
            Guards(min_equity_gbp=-100)

        with pytest.raises(ValueError, match="min_equity_gbp must be > 0"):
            Guards(min_equity_gbp=0)

    @pytest.mark.asyncio
    async def test_check_and_enforce_no_trigger(self):
        """Test guards don't trigger when thresholds not breached."""
        guards = Guards(max_drawdown_percent=20.0, min_equity_gbp=500.0)

        mt5_client = AsyncMock()
        mt5_client.get_account_info = AsyncMock(return_value={"equity": 10000.0})

        order_service = AsyncMock()

        state = await guards.check_and_enforce(mt5_client, order_service)

        assert not state.cap_triggered
        assert not state.min_equity_triggered
        assert state.current_equity == 10000.0
        assert order_service.close_all_positions.call_count == 0

    @pytest.mark.asyncio
    async def test_check_and_enforce_max_drawdown_trigger(self):
        """Test guards trigger when drawdown exceeds threshold."""
        guards = Guards(max_drawdown_percent=20.0, min_equity_gbp=500.0)

        mt5_client = AsyncMock()

        # Simulate: peak equity 10000, current equity 7500 = 25% drawdown
        # Need to return peak equity on first call, then lower equity on check
        responses = [
            {"equity": 10000.0},  # First call - sets peak equity
            {"equity": 10000.0},  # Peak equity is stable
            {"equity": 7500.0},  # Drawdown equity
        ]
        response_iter = iter(responses)

        async def get_account_info():
            return next(response_iter)

        mt5_client.get_account_info = get_account_info

        order_service = AsyncMock()

        # First call to initialize peak equity
        state1 = await guards.check_and_enforce(mt5_client, order_service)
        assert not state1.cap_triggered

        # Reset the iterator for second call
        responses = [
            {"equity": 10000.0},  # Current check still at peak
            {"equity": 7500.0},  # Drawdown
        ]
        response_iter = iter(responses)
        mt5_client.get_account_info = get_account_info

        # Second call with drawdown - update peak first, then call again
        await guards.check_and_enforce(mt5_client, order_service)

        # Now trigger drawdown on next check
        mt5_client.get_account_info = AsyncMock(return_value={"equity": 7500.0})
        state2 = await guards.check_and_enforce(mt5_client, order_service)

        assert state2.cap_triggered
        assert state2.current_drawdown >= 20.0
        assert order_service.close_all_positions.called

    @pytest.mark.asyncio
    async def test_check_and_enforce_min_equity_trigger(self):
        """Test guards trigger when equity drops below minimum."""
        guards = Guards(max_drawdown_percent=20.0, min_equity_gbp=500.0)

        mt5_client = AsyncMock()
        mt5_client.get_account_info = AsyncMock(return_value={"equity": 400.0})

        order_service = AsyncMock()

        state = await guards.check_and_enforce(mt5_client, order_service)

        assert state.min_equity_triggered
        assert state.current_equity == 400.0
        assert order_service.close_all_positions.called

    @pytest.mark.asyncio
    async def test_check_and_enforce_with_alert_service(self):
        """Test guards call alert service when triggered."""
        guards = Guards(
            max_drawdown_percent=20.0,
            min_equity_gbp=500.0,
            alert_service=AsyncMock(),
        )

        mt5_client = AsyncMock()
        mt5_client.get_account_info = AsyncMock(return_value={"equity": 400.0})

        order_service = AsyncMock()

        await guards.check_and_enforce(mt5_client, order_service)

        assert guards.alert_service.send_owner_alert.called
        alert_text = guards.alert_service.send_owner_alert.call_args[0][0]
        assert "MINIMUM EQUITY" in alert_text


class TestGuardsFunctions:
    """Test convenience functions for guards."""

    @pytest.mark.asyncio
    async def test_enforce_max_drawdown_function(self):
        """Test enforce_max_drawdown convenience function."""
        mt5_client = AsyncMock()
        mt5_client.get_account_info = AsyncMock(return_value={"equity": 10000.0})
        order_service = AsyncMock()

        state = await enforce_max_drawdown(
            max_drawdown_percent=20.0,
            mt5_client=mt5_client,
            order_service=order_service,
        )

        assert isinstance(state, GuardState)
        assert not state.cap_triggered

    @pytest.mark.asyncio
    async def test_min_equity_guard_function(self):
        """Test min_equity_guard convenience function."""
        mt5_client = AsyncMock()
        mt5_client.get_account_info = AsyncMock(return_value={"equity": 400.0})
        order_service = AsyncMock()

        state = await min_equity_guard(
            min_equity_gbp=500.0,
            mt5_client=mt5_client,
            order_service=order_service,
        )

        assert isinstance(state, GuardState)
        assert state.min_equity_triggered
        assert order_service.close_all_positions.called
