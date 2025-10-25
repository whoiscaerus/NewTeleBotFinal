"""Trading runtime module - main loop and risk management.

This module provides the core trading loop execution engine with:
- Continuous signal processing
- MT5 trade execution
- Health monitoring via heartbeats
- Risk management via drawdown caps
- Event emission for analytics

Components:
- TradingLoop: Main loop orchestrating signal execution
- DrawdownGuard: Automated drawdown cap enforcement

Example:
    >>> from backend.app.trading.runtime import TradingLoop, DrawdownGuard
    >>> loop = TradingLoop(mt5_client=mt5, approvals_service=approvals, ...)
    >>> await loop.start(duration_seconds=3600)
"""

from backend.app.trading.runtime.drawdown import (
    DrawdownCapExceededError,
    DrawdownGuard,
    DrawdownState,
)
from backend.app.trading.runtime.loop import Event, HeartbeatMetrics, TradingLoop

__all__ = [
    "TradingLoop",
    "DrawdownGuard",
    "DrawdownCapExceededError",
    "DrawdownState",
    "Event",
    "HeartbeatMetrics",
]
