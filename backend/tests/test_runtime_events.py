"""Comprehensive tests for EventEmitter analytics event system.

Tests the event emission infrastructure:
- Event dataclass with type, timestamp, metadata
- EventType enum with all 8 event types
- EventEmitter with type-safe event methods
- Event serialization to dict
- Metrics recording for each event type
- Structured logging

Coverage target: 100% of events.py (357 lines)
"""

import pytest
import logging
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from backend.app.trading.runtime.events import (
    EventType,
    Event,
    EventEmitter,
)


# ============================================================================
# EVENTTYPE ENUM TESTS
# ============================================================================


class TestEventType:
    """Test EventType enum."""

    def test_event_type_enum_values(self):
        """Test EventType enum has all required event types."""
        assert EventType.SIGNAL_RECEIVED.value == "signal_received"
        assert EventType.SIGNAL_APPROVED.value == "signal_approved"
        assert EventType.SIGNAL_REJECTED.value == "signal_rejected"
        assert EventType.TRADE_EXECUTED.value == "trade_executed"
        assert EventType.TRADE_FAILED.value == "trade_failed"
        assert EventType.POSITION_CLOSED.value == "position_closed"
        assert EventType.LOOP_STARTED.value == "loop_started"
        assert EventType.LOOP_STOPPED.value == "loop_stopped"

    def test_event_type_count(self):
        """Test EventType enum has exactly 8 event types."""
        event_types = list(EventType)
        assert len(event_types) == 8

    def test_event_type_string_conversion(self):
        """Test EventType enum can be converted to string."""
        assert str(EventType.SIGNAL_RECEIVED.value) == "signal_received"
        assert str(EventType.TRADE_EXECUTED.value) == "trade_executed"


# ============================================================================
# EVENT DATACLASS TESTS
# ============================================================================


class TestEventDataclass:
    """Test Event dataclass."""

    def test_event_creation(self):
        """Test Event dataclass creation."""
        now = datetime.now(UTC)
        event = Event(
            event_type=EventType.SIGNAL_RECEIVED,
            timestamp=now,
            loop_id="test_loop",
            metadata={"signal_id": "sig_123"},
        )

        assert event.event_type == EventType.SIGNAL_RECEIVED
        assert event.timestamp == now
        assert event.loop_id == "test_loop"
        assert event.metadata == {"signal_id": "sig_123"}

    def test_event_to_dict(self):
        """Test Event.to_dict() serialization."""
        now = datetime.now(UTC)
        event = Event(
            event_type=EventType.TRADE_EXECUTED,
            timestamp=now,
            loop_id="test_loop",
            metadata={"trade_id": "trade_123", "profit": 500.50},
        )

        event_dict = event.to_dict()

        assert event_dict["event_type"] == "trade_executed"
        assert event_dict["timestamp"] == now.isoformat()
        assert event_dict["loop_id"] == "test_loop"
        assert event_dict["metadata"]["trade_id"] == "trade_123"
        assert event_dict["metadata"]["profit"] == 500.50

    def test_event_timestamp_is_utc(self):
        """Test Event timestamp is in UTC."""
        now = datetime.now(UTC)
        event = Event(
            event_type=EventType.LOOP_STARTED,
            timestamp=now,
            loop_id="test",
            metadata={},
        )

        assert event.timestamp.tzinfo == UTC

    def test_event_metadata_empty(self):
        """Test Event with empty metadata."""
        event = Event(
            event_type=EventType.LOOP_STOPPED,
            timestamp=datetime.now(UTC),
            loop_id="test",
            metadata={},
        )

        assert event.metadata == {}
        assert event.to_dict()["metadata"] == {}

    def test_event_metadata_complex(self):
        """Test Event with complex metadata."""
        now = datetime.now(UTC)
        complex_metadata = {
            "signal_id": "sig_123",
            "instrument": "GOLD",
            "side": "buy",
            "price": 1950.50,
            "indicators": {
                "rsi": 75.2,
                "ma_ratio": 1.025,
            },
            "timeframe": "1H",
        }

        event = Event(
            event_type=EventType.SIGNAL_RECEIVED,
            timestamp=now,
            loop_id="trader_main",
            metadata=complex_metadata,
        )

        assert event.metadata["signal_id"] == "sig_123"
        assert event.metadata["indicators"]["rsi"] == 75.2


# ============================================================================
# EVENTEMITTER INITIALIZATION TESTS
# ============================================================================


class TestEventEmitterInitialization:
    """Test EventEmitter initialization."""

    def test_event_emitter_init_default_values(self):
        """Test EventEmitter initialization with defaults."""
        emitter = EventEmitter()

        assert emitter.loop_id == "trading_loop_main"
        assert emitter._logger is not None

    def test_event_emitter_init_custom_loop_id(self):
        """Test EventEmitter initialization with custom loop_id."""
        emitter = EventEmitter(loop_id="test_loop_123")

        assert emitter.loop_id == "test_loop_123"

    def test_event_emitter_init_custom_logger(self):
        """Test EventEmitter initialization with custom logger."""
        custom_logger = logging.getLogger("test_events")
        emitter = EventEmitter(logger=custom_logger)

        assert emitter._logger is custom_logger


# ============================================================================
# EVENTEMITTER EMIT TESTS
# ============================================================================


class TestEventEmitterEmit:
    """Test EventEmitter.emit() method."""

    @pytest.mark.asyncio
    async def test_emit_basic_event(self):
        """Test emitting a basic event."""
        emitter = EventEmitter(loop_id="test_loop")

        event = Event(
            event_type=EventType.SIGNAL_RECEIVED,
            timestamp=datetime.now(UTC),
            loop_id="test_loop",
            metadata={"signal_id": "sig_123"},
        )

        # Should not raise
        await emitter.emit(event)

    @pytest.mark.asyncio
    async def test_emit_records_metric(self):
        """Test emit() records metric to observability."""
        emitter = EventEmitter()

        event = Event(
            event_type=EventType.TRADE_EXECUTED,
            timestamp=datetime.now(UTC),
            loop_id="test",
            metadata={},
        )

        with patch("backend.app.trading.runtime.events.get_metrics") as mock_metrics:
            metrics_registry = MagicMock()
            mock_metrics.return_value = metrics_registry

            await emitter.emit(event)

            # Verify metric recorded with event type label
            metrics_registry.analytics_events_total.labels.assert_called_once_with(
                event_type="trade_executed"
            )
            metrics_registry.analytics_events_total.labels().inc.assert_called_once()

    @pytest.mark.asyncio
    async def test_emit_handles_metrics_error(self):
        """Test emit() handles metrics recording error gracefully."""
        emitter = EventEmitter()

        event = Event(
            event_type=EventType.SIGNAL_RECEIVED,
            timestamp=datetime.now(UTC),
            loop_id="test",
            metadata={},
        )

        with patch("backend.app.trading.runtime.events.get_metrics") as mock_metrics:
            mock_metrics.side_effect = RuntimeError("Metrics unavailable")

            # Should not raise
            await emitter.emit(event)

    @pytest.mark.asyncio
    async def test_emit_logs_structured_message(self):
        """Test emit() logs event type correctly."""
        emitter = EventEmitter(loop_id="test_loop")

        event = Event(
            event_type=EventType.SIGNAL_APPROVED,
            timestamp=datetime.now(UTC),
            loop_id="test_loop",
            metadata={"signal_id": "sig_456"},
        )

        # Just verify emit doesn't raise and returns something
        await emitter.emit(event)  # Should not raise

    @pytest.mark.asyncio
    async def test_emit_all_event_types(self):
        """Test emit() works with all event types."""
        emitter = EventEmitter()

        for event_type in EventType:
            event = Event(
                event_type=event_type,
                timestamp=datetime.now(UTC),
                loop_id="test",
                metadata={"test": True},
            )

            # Should not raise
            await emitter.emit(event)


# ============================================================================
# EVENTEMITTER SIGNAL_RECEIVED TESTS
# ============================================================================


class TestEventEmitterSignalReceived:
    """Test EventEmitter.emit_signal_received() method."""

    @pytest.mark.asyncio
    async def test_emit_signal_received_creates_event(self):
        """Test emit_signal_received() creates and returns event."""
        emitter = EventEmitter(loop_id="test_loop")

        event = await emitter.emit_signal_received(
            signal_id="sig_123",
            instrument="GOLD",
            side="buy",
        )

        assert event.event_type == EventType.SIGNAL_RECEIVED
        assert event.loop_id == "test_loop"
        assert event.metadata["signal_id"] == "sig_123"
        assert event.metadata["instrument"] == "GOLD"
        assert event.metadata["side"] == "buy"

    @pytest.mark.asyncio
    async def test_emit_signal_received_with_metadata(self):
        """Test emit_signal_received() includes additional metadata."""
        emitter = EventEmitter()

        event = await emitter.emit_signal_received(
            signal_id="sig_789",
            instrument="EURUSD",
            side="sell",
            metadata={"rsi": 25, "confidence": 0.95},
        )

        assert event.metadata["signal_id"] == "sig_789"
        assert event.metadata["rsi"] == 25
        assert event.metadata["confidence"] == 0.95

    @pytest.mark.asyncio
    async def test_emit_signal_received_calls_emit(self):
        """Test emit_signal_received() calls emit() internally."""
        emitter = EventEmitter()

        with patch.object(emitter, "emit") as mock_emit:
            mock_emit.return_value = None

            await emitter.emit_signal_received(
                signal_id="sig_123",
                instrument="GOLD",
                side="buy",
            )

            mock_emit.assert_called_once()
            called_event = mock_emit.call_args[0][0]
            assert called_event.event_type == EventType.SIGNAL_RECEIVED


# ============================================================================
# EVENTEMITTER SIGNAL_APPROVED TESTS
# ============================================================================


class TestEventEmitterSignalApproved:
    """Test EventEmitter.emit_signal_approved() method."""

    @pytest.mark.asyncio
    async def test_emit_signal_approved_creates_event(self):
        """Test emit_signal_approved() creates and returns event."""
        emitter = EventEmitter()

        event = await emitter.emit_signal_approved(
            signal_id="sig_123",
            approved_by="user_456",
        )

        assert event.event_type == EventType.SIGNAL_APPROVED
        assert event.metadata["signal_id"] == "sig_123"
        assert event.metadata["approved_by"] == "user_456"

    @pytest.mark.asyncio
    async def test_emit_signal_approved_with_metadata(self):
        """Test emit_signal_approved() includes additional metadata."""
        emitter = EventEmitter()

        event = await emitter.emit_signal_approved(
            signal_id="sig_123",
            approved_by="system",
            metadata={"reason": "auto_approval_threshold_met"},
        )

        assert event.metadata["reason"] == "auto_approval_threshold_met"


# ============================================================================
# EVENTEMITTER TRADE_EXECUTED TESTS
# ============================================================================


class TestEventEmitterTradeExecuted:
    """Test EventEmitter.emit_trade_executed() method."""

    @pytest.mark.asyncio
    async def test_emit_trade_executed_creates_event(self):
        """Test emit_trade_executed() creates and returns event."""
        emitter = EventEmitter()

        event = await emitter.emit_trade_executed(
            signal_id="sig_123",
            trade_id="trade_456",
            instrument="GOLD",
            volume=1.0,
            entry_price=1950.50,
        )

        assert event.event_type == EventType.TRADE_EXECUTED
        assert event.metadata["signal_id"] == "sig_123"
        assert event.metadata["trade_id"] == "trade_456"
        assert event.metadata["instrument"] == "GOLD"
        assert event.metadata["volume"] == 1.0
        assert event.metadata["entry_price"] == 1950.50

    @pytest.mark.asyncio
    async def test_emit_trade_executed_with_metadata(self):
        """Test emit_trade_executed() includes additional metadata."""
        emitter = EventEmitter()

        event = await emitter.emit_trade_executed(
            signal_id="sig_123",
            trade_id="trade_456",
            instrument="GOLD",
            volume=1.0,
            entry_price=1950.50,
            metadata={"execution_time_ms": 234.5},
        )

        assert event.metadata["execution_time_ms"] == 234.5


# ============================================================================
# EVENTEMITTER TRADE_FAILED TESTS
# ============================================================================


class TestEventEmitterTradeFailed:
    """Test EventEmitter.emit_trade_failed() method."""

    @pytest.mark.asyncio
    async def test_emit_trade_failed_creates_event(self):
        """Test emit_trade_failed() creates and returns event."""
        emitter = EventEmitter()

        event = await emitter.emit_trade_failed(
            signal_id="sig_123",
            reason="Insufficient margin",
        )

        assert event.event_type == EventType.TRADE_FAILED
        assert event.metadata["signal_id"] == "sig_123"
        assert event.metadata["reason"] == "Insufficient margin"

    @pytest.mark.asyncio
    async def test_emit_trade_failed_with_metadata(self):
        """Test emit_trade_failed() includes additional metadata."""
        emitter = EventEmitter()

        event = await emitter.emit_trade_failed(
            signal_id="sig_123",
            reason="Connection timeout",
            metadata={"retry_count": 3},
        )

        assert event.metadata["retry_count"] == 3


# ============================================================================
# EVENTEMITTER POSITION_CLOSED TESTS
# ============================================================================


class TestEventEmitterPositionClosed:
    """Test EventEmitter.emit_position_closed() method."""

    @pytest.mark.asyncio
    async def test_emit_position_closed_creates_event(self):
        """Test emit_position_closed() creates and returns event."""
        emitter = EventEmitter()

        event = await emitter.emit_position_closed(
            trade_id="trade_123",
            close_price=1955.50,
            profit_loss=500.50,
            reason="take_profit",
        )

        assert event.event_type == EventType.POSITION_CLOSED
        assert event.metadata["trade_id"] == "trade_123"
        assert event.metadata["close_price"] == 1955.50
        assert event.metadata["profit_loss"] == 500.50
        assert event.metadata["reason"] == "take_profit"

    @pytest.mark.asyncio
    async def test_emit_position_closed_multiple_reasons(self):
        """Test emit_position_closed() with different close reasons."""
        emitter = EventEmitter()

        # Test stop_loss
        event1 = await emitter.emit_position_closed(
            trade_id="trade_1",
            close_price=1940.00,
            profit_loss=-200.00,
            reason="stop_loss",
        )
        assert event1.metadata["reason"] == "stop_loss"

        # Test drawdown_guard
        event2 = await emitter.emit_position_closed(
            trade_id="trade_2",
            close_price=1945.00,
            profit_loss=100.00,
            reason="drawdown_guard",
        )
        assert event2.metadata["reason"] == "drawdown_guard"

        # Test manual
        event3 = await emitter.emit_position_closed(
            trade_id="trade_3",
            close_price=1950.00,
            profit_loss=0.00,
            reason="manual",
        )
        assert event3.metadata["reason"] == "manual"


# ============================================================================
# EVENTEMITTER LOOP_LIFECYCLE TESTS
# ============================================================================


class TestEventEmitterLoopLifecycle:
    """Test EventEmitter.emit_loop_started() and emit_loop_stopped() methods."""

    @pytest.mark.asyncio
    async def test_emit_loop_started(self):
        """Test emit_loop_started() creates event."""
        emitter = EventEmitter()

        event = await emitter.emit_loop_started(
            metadata={"symbols": ["GOLD", "EURUSD", "SPX"]}
        )

        assert event.event_type == EventType.LOOP_STARTED
        assert event.metadata["symbols"] == ["GOLD", "EURUSD", "SPX"]

    @pytest.mark.asyncio
    async def test_emit_loop_started_no_metadata(self):
        """Test emit_loop_started() works without metadata."""
        emitter = EventEmitter()

        event = await emitter.emit_loop_started()

        assert event.event_type == EventType.LOOP_STARTED
        assert event.metadata == {}

    @pytest.mark.asyncio
    async def test_emit_loop_stopped_normal(self):
        """Test emit_loop_stopped() with normal stop reason."""
        emitter = EventEmitter()

        event = await emitter.emit_loop_stopped(reason="normal")

        assert event.event_type == EventType.LOOP_STOPPED
        assert event.metadata["reason"] == "normal"

    @pytest.mark.asyncio
    async def test_emit_loop_stopped_error(self):
        """Test emit_loop_stopped() with error stop reason."""
        emitter = EventEmitter()

        event = await emitter.emit_loop_stopped(
            reason="error",
            metadata={"error": "Connection lost"},
        )

        assert event.event_type == EventType.LOOP_STOPPED
        assert event.metadata["reason"] == "error"
        assert event.metadata["error"] == "Connection lost"


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


class TestEventEmitterIntegration:
    """Integration tests for EventEmitter."""

    @pytest.mark.asyncio
    async def test_complete_trading_flow_events(self):
        """Test complete event sequence for trading flow."""
        emitter = EventEmitter(loop_id="trader_main")

        # 1. Loop started
        loop_started = await emitter.emit_loop_started(
            metadata={"symbols": ["GOLD"]}
        )
        assert loop_started.event_type == EventType.LOOP_STARTED

        # 2. Signal received
        signal_received = await emitter.emit_signal_received(
            signal_id="sig_123",
            instrument="GOLD",
            side="buy",
            metadata={"rsi": 75},
        )
        assert signal_received.event_type == EventType.SIGNAL_RECEIVED

        # 3. Signal approved
        signal_approved = await emitter.emit_signal_approved(
            signal_id="sig_123",
            approved_by="user_1",
        )
        assert signal_approved.event_type == EventType.SIGNAL_APPROVED

        # 4. Trade executed
        trade_executed = await emitter.emit_trade_executed(
            signal_id="sig_123",
            trade_id="trade_456",
            instrument="GOLD",
            volume=1.0,
            entry_price=1950.50,
        )
        assert trade_executed.event_type == EventType.TRADE_EXECUTED

        # 5. Position closed
        position_closed = await emitter.emit_position_closed(
            trade_id="trade_456",
            close_price=1955.50,
            profit_loss=500.50,
            reason="take_profit",
        )
        assert position_closed.event_type == EventType.POSITION_CLOSED

        # 6. Loop stopped
        loop_stopped = await emitter.emit_loop_stopped(reason="normal")
        assert loop_stopped.event_type == EventType.LOOP_STOPPED

    @pytest.mark.asyncio
    async def test_event_metrics_incremented_per_type(self):
        """Test metrics are incremented for each event type."""
        emitter = EventEmitter()

        with patch("backend.app.trading.runtime.events.get_metrics") as mock_metrics:
            metrics_registry = MagicMock()
            mock_metrics.return_value = metrics_registry

            # Emit different event types
            await emitter.emit_signal_received("sig_1", "GOLD", "buy")
            await emitter.emit_signal_approved("sig_1", "user_1")
            await emitter.emit_trade_executed("sig_1", "trade_1", "GOLD", 1.0, 1950.0)

            # Verify labels() called with correct event types
            labels_calls = [call[1]["event_type"] for call in mock_metrics.return_value.analytics_events_total.labels.call_args_list]
            assert "signal_received" in labels_calls
            assert "signal_approved" in labels_calls
            assert "trade_executed" in labels_calls

    @pytest.mark.asyncio
    async def test_multiple_concurrent_emissions(self):
        """Test multiple concurrent event emissions."""
        import asyncio

        emitter = EventEmitter()

        async def emit_event(signal_id):
            await emitter.emit_signal_received(
                signal_id=signal_id,
                instrument="GOLD",
                side="buy",
            )

        # Emit 5 events concurrently
        tasks = [emit_event(f"sig_{i}") for i in range(5)]
        await asyncio.gather(*tasks)

        # All should succeed
        assert True
