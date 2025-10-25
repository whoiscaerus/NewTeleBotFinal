"""MT5 session management and trading interface.

This module provides:
- MT5SessionManager: Lifecycle management with resilience
- Exceptions: MT5InitError, MT5AuthError, MT5Disconnected, MT5CircuitBreakerOpen
- Health probes: Monitor connection status
"""

from backend.app.trading.mt5.errors import (
    MT5AuthError,
    MT5CircuitBreakerOpen,
    MT5Disconnected,
    MT5Error,
    MT5InitError,
)
from backend.app.trading.mt5.health import MT5HealthStatus, probe
from backend.app.trading.mt5.session import MT5SessionManager

__all__ = [
    "MT5SessionManager",
    "MT5Error",
    "MT5InitError",
    "MT5AuthError",
    "MT5Disconnected",
    "MT5CircuitBreakerOpen",
    "MT5HealthStatus",
    "probe",
]
