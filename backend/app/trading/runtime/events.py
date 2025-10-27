"""Event emission system for trading loop analytics hooks.

This module implements the event emission infrastructure for tracking trading
loop lifecycle events: signal received, approved, rejected, executed, failed.

Features:
- Event dataclass with type, timestamp, loop_id, metadata
- Event emission with observability integration
- Analytics event hooks for tracking
- Type-safe event handling

Event types:
- signal_received: New signal ingested into loop
- signal_approved: Signal approved by user/system
- signal_rejected: Signal rejected/ignored
- trade_executed: Trade successfully placed
- trade_failed: Trade placement failed
- position_closed: Position manually/automatically closed
- loop_started: Trading loop started
- loop_stopped: Trading loop stopped

Example:
    >>> emitter = EventEmitter(loop_id="trader_main")
    >>> await emitter.emit_signal_received(
    ...     signal_id="sig-123",
    ...     instrument="GOLD",
    ...     side="buy",
    ...     metadata={"rsi": 75, "ma_ratio": 1.02}
    ... )
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from backend.app.observability.metrics import get_metrics


class EventType(str, Enum):
    """Valid event types for trading loop."""

    SIGNAL_RECEIVED = "signal_received"
    SIGNAL_APPROVED = "signal_approved"
    SIGNAL_REJECTED = "signal_rejected"
    TRADE_EXECUTED = "trade_executed"
    TRADE_FAILED = "trade_failed"
    POSITION_CLOSED = "position_closed"
    LOOP_STARTED = "loop_started"
    LOOP_STOPPED = "loop_stopped"


@dataclass
class Event:
    """Base event class for trading loop events.

    Attributes:
        event_type: Type of event (e.g., 'signal_received', 'trade_executed')
        timestamp: When event occurred (UTC)
        loop_id: Which loop instance emitted this event
        metadata: Additional event-specific data (dict)
    """

    event_type: EventType
    timestamp: datetime
    loop_id: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Convert event to dictionary for serialization.

        Returns:
            dict: Event as dictionary with ISO timestamp
        """
        return {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "loop_id": self.loop_id,
            "metadata": self.metadata,
        }


class EventEmitter:
    """Emits analytics events for trading loop lifecycle.

    Provides type-safe methods to emit events at key points in trading loop:
    signal ingestion, approval, execution, etc. Integrates with observability
    stack for metrics collection.

    Attributes:
        loop_id: Unique identifier for loop instance
        _logger: Structured logger instance
    """

    def __init__(
        self,
        loop_id: str = "trading_loop_main",
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialize event emitter.

        Args:
            loop_id: Unique identifier for loop instance
            logger: Optional logger (creates default if not provided)
        """
        self.loop_id = loop_id
        self._logger = logger or logging.getLogger(__name__)

    async def emit(self, event: Event) -> None:
        """Emit an event.

        Records event to observability stack and logs structured message.

        Args:
            event: Event to emit

        Example:
            >>> event = Event(
            ...     event_type=EventType.SIGNAL_RECEIVED,
            ...     timestamp=datetime.now(UTC),
            ...     loop_id="trader_main",
            ...     metadata={"signal_id": "sig-123", "instrument": "GOLD"}
            ... )
            >>> await emitter.emit(event)
        """
        try:
            metrics_registry = get_metrics()
            metrics_registry.analytics_events_total.labels(
                event_type=event.event_type.value
            ).inc()
        except Exception as e:
            self._logger.warning(
                "Failed to record event metric",
                extra={"event_type": event.event_type.value, "error": str(e)},
            )

        self._logger.info(
            f"event_emitted: {event.event_type.value}",
            extra={
                "loop_id": event.loop_id,
                "event_type": event.event_type.value,
                "timestamp": event.timestamp.isoformat(),
                **event.metadata,
            },
        )

    async def emit_signal_received(
        self,
        signal_id: str,
        instrument: str,
        side: str,
        metadata: dict[str, Any] | None = None,
    ) -> Event:
        """Emit signal_received event.

        Args:
            signal_id: Unique signal identifier
            instrument: Trading instrument (e.g., GOLD, EURUSD)
            side: Trade direction (buy/sell)
            metadata: Additional event data

        Returns:
            Event: Emitted event
        """
        event = Event(
            event_type=EventType.SIGNAL_RECEIVED,
            timestamp=datetime.now(UTC),
            loop_id=self.loop_id,
            metadata={
                "signal_id": signal_id,
                "instrument": instrument,
                "side": side,
                **(metadata or {}),
            },
        )
        await self.emit(event)
        return event

    async def emit_signal_approved(
        self,
        signal_id: str,
        approved_by: str,
        metadata: dict[str, Any] | None = None,
    ) -> Event:
        """Emit signal_approved event.

        Args:
            signal_id: Unique signal identifier
            approved_by: User/system that approved signal
            metadata: Additional event data

        Returns:
            Event: Emitted event
        """
        event = Event(
            event_type=EventType.SIGNAL_APPROVED,
            timestamp=datetime.now(UTC),
            loop_id=self.loop_id,
            metadata={
                "signal_id": signal_id,
                "approved_by": approved_by,
                **(metadata or {}),
            },
        )
        await self.emit(event)
        return event

    async def emit_trade_executed(
        self,
        signal_id: str,
        trade_id: str,
        instrument: str,
        volume: float,
        entry_price: float,
        metadata: dict[str, Any] | None = None,
    ) -> Event:
        """Emit trade_executed event.

        Args:
            signal_id: Associated signal identifier
            trade_id: Unique trade identifier
            instrument: Trading instrument
            volume: Trade volume/size
            entry_price: Entry price
            metadata: Additional event data

        Returns:
            Event: Emitted event
        """
        event = Event(
            event_type=EventType.TRADE_EXECUTED,
            timestamp=datetime.now(UTC),
            loop_id=self.loop_id,
            metadata={
                "signal_id": signal_id,
                "trade_id": trade_id,
                "instrument": instrument,
                "volume": volume,
                "entry_price": entry_price,
                **(metadata or {}),
            },
        )
        await self.emit(event)
        return event

    async def emit_trade_failed(
        self,
        signal_id: str,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> Event:
        """Emit trade_failed event.

        Args:
            signal_id: Associated signal identifier
            reason: Why trade failed
            metadata: Additional event data

        Returns:
            Event: Emitted event
        """
        event = Event(
            event_type=EventType.TRADE_FAILED,
            timestamp=datetime.now(UTC),
            loop_id=self.loop_id,
            metadata={
                "signal_id": signal_id,
                "reason": reason,
                **(metadata or {}),
            },
        )
        await self.emit(event)
        return event

    async def emit_position_closed(
        self,
        trade_id: str,
        close_price: float,
        profit_loss: float,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> Event:
        """Emit position_closed event.

        Args:
            trade_id: Unique trade identifier
            close_price: Exit price
            profit_loss: PnL amount
            reason: Why position closed (e.g., "take_profit", "stop_loss", "drawdown_guard")
            metadata: Additional event data

        Returns:
            Event: Emitted event
        """
        event = Event(
            event_type=EventType.POSITION_CLOSED,
            timestamp=datetime.now(UTC),
            loop_id=self.loop_id,
            metadata={
                "trade_id": trade_id,
                "close_price": close_price,
                "profit_loss": profit_loss,
                "reason": reason,
                **(metadata or {}),
            },
        )
        await self.emit(event)
        return event

    async def emit_loop_started(
        self,
        metadata: dict[str, Any] | None = None,
    ) -> Event:
        """Emit loop_started event.

        Args:
            metadata: Additional event data (symbols, etc.)

        Returns:
            Event: Emitted event
        """
        event = Event(
            event_type=EventType.LOOP_STARTED,
            timestamp=datetime.now(UTC),
            loop_id=self.loop_id,
            metadata=metadata or {},
        )
        await self.emit(event)
        return event

    async def emit_loop_stopped(
        self,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> Event:
        """Emit loop_stopped event.

        Args:
            reason: Why loop stopped (normal, error, user_request)
            metadata: Additional event data

        Returns:
            Event: Emitted event
        """
        event = Event(
            event_type=EventType.LOOP_STOPPED,
            timestamp=datetime.now(UTC),
            loop_id=self.loop_id,
            metadata={
                "reason": reason,
                **(metadata or {}),
            },
        )
        await self.emit(event)
        return event
