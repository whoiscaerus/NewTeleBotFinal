"""MT5 health check probes."""

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .session import MT5SessionManager


@dataclass
class MT5HealthStatus:
    """Health status of MT5 connection."""

    is_healthy: bool
    is_connected: bool
    failure_count: int
    circuit_breaker_open: bool
    last_check_time: float
    uptime_seconds: float | None = None
    message: str = ""


async def probe(session_manager: "MT5SessionManager") -> MT5HealthStatus:
    """Probe MT5 session health.

    Args:
        session_manager: MT5SessionManager instance to probe

    Returns:
        MT5HealthStatus with current health information
    """
    current_time = time.time()

    # Calculate uptime
    uptime = None
    if hasattr(session_manager, "_connect_time") and session_manager._connect_time:
        uptime = current_time - session_manager._connect_time

    # Determine status
    is_connected = getattr(session_manager, "_is_connected", False)
    failure_count = getattr(session_manager, "_failure_count", 0)
    circuit_breaker_open = getattr(session_manager, "_circuit_breaker_open", False)
    max_failures = getattr(session_manager, "_max_failures", 5)

    # Build message
    message_parts = []
    if circuit_breaker_open:
        message_parts.append(
            f"Circuit breaker open ({failure_count}/{max_failures} failures)"
        )
    elif is_connected:
        message_parts.append("Connected and healthy")
    else:
        message_parts.append("Disconnected or initializing")

    if uptime is not None:
        message_parts.append(f"uptime: {uptime:.1f}s")

    message = " | ".join(message_parts)

    return MT5HealthStatus(
        is_healthy=is_connected and not circuit_breaker_open,
        is_connected=is_connected,
        failure_count=failure_count,
        circuit_breaker_open=circuit_breaker_open,
        last_check_time=current_time,
        uptime_seconds=uptime,
        message=message,
    )
