"""Trading runtime module - main loop and risk management.

This module provides the core trading loop execution engine with:
- Continuous signal processing
- MT5 trade execution
- Health monitoring via heartbeats (PR-019)
- Risk management via drawdown caps and guards (PR-019)
- Event emission for analytics hooks (PR-019)

Components:
- TradingLoop: Main loop orchestrating signal execution
- HeartbeatManager: Periodic health check emission
- EventEmitter: Analytics event tracking
- Guards: Risk enforcement (max drawdown, min equity)
- DrawdownGuard: Legacy drawdown monitoring (use Guards instead)

Example:
    >>> from backend.app.trading.runtime import TradingLoop, HeartbeatManager, EventEmitter, Guards
    >>> loop = TradingLoop(mt5_client=mt5, approvals_service=approvals, ...)
    >>> heartbeat = HeartbeatManager(interval_seconds=10)
    >>> events = EventEmitter(loop_id="trader_main")
    >>> guards = Guards(max_drawdown_percent=20.0, min_equity_gbp=500.0)
    >>> await loop.start(duration_seconds=3600)
"""

from backend.app.trading.runtime.drawdown import (
    DrawdownCapExceededError,
    DrawdownGuard,
    DrawdownState,
)
from backend.app.trading.runtime.events import Event, EventEmitter, EventType
from backend.app.trading.runtime.guards import (
    Guards,
    GuardState,
    enforce_max_drawdown,
    min_equity_guard,
)
from backend.app.trading.runtime.heartbeat import HeartbeatManager, HeartbeatMetrics
from backend.app.trading.runtime.loop import TradingLoop

__all__ = [
    # Loop
    "TradingLoop",
    # Heartbeat (PR-019)
    "HeartbeatManager",
    "HeartbeatMetrics",
    # Events (PR-019)
    "Event",
    "EventEmitter",
    "EventType",
    # Guards (PR-019)
    "Guards",
    "GuardState",
    "enforce_max_drawdown",
    "min_equity_guard",
    # Legacy (keep for backwards compatibility)
    "DrawdownGuard",
    "DrawdownCapExceededError",
    "DrawdownState",
]
