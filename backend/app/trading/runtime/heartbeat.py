"""Periodic heartbeat mechanism for trading loop monitoring.

This module implements the heartbeat system that emits health metrics at
regular intervals to track trading loop health and performance.

Features:
- Periodic emission (configurable interval, default 10s)
- Lock-based synchronization to prevent concurrent emissions
- Metrics collection and reporting
- Integration with observability stack

Example:
    >>> heartbeat = HeartbeatManager(
    ...     interval_seconds=10,
    ...     loop_id="trader_main"
    ... )
    >>> await heartbeat.emit(
    ...     signals_processed=5,
    ...     trades_executed=2,
    ...     error_count=0,
    ...     loop_duration_ms=245.5
    ... )
"""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from backend.app.observability.metrics import get_metrics


@dataclass
class HeartbeatMetrics:
    """Metrics emitted with each heartbeat.

    Attributes:
        timestamp: When heartbeat was emitted (UTC)
        loop_id: Unique identifier for this loop instance
        signals_processed: Count of signals processed this interval
        trades_executed: Count of successful trades this interval
        error_count: Count of errors encountered
        loop_duration_ms: How long the loop iteration took (milliseconds)
        positions_open: Current number of open positions
        account_equity: Current account equity in account currency
        total_signals_lifetime: Total signals processed since loop started
        total_trades_lifetime: Total trades executed since loop started
    """

    timestamp: datetime
    loop_id: str
    signals_processed: int
    trades_executed: int
    error_count: int
    loop_duration_ms: float
    positions_open: int
    account_equity: float
    total_signals_lifetime: int
    total_trades_lifetime: int


class HeartbeatManager:
    """Manages periodic heartbeat emission for loop health monitoring.

    Implements a thread-safe heartbeat mechanism with configurable intervals.
    Ensures only one heartbeat is emitted at a time via async lock.

    Attributes:
        interval_seconds: How often to emit heartbeat (default: 10)
        loop_id: Unique identifier for this loop
        _lock: Async lock to prevent concurrent heartbeat emissions
        _logger: Structured logger instance
    """

    def __init__(
        self,
        interval_seconds: int = 10,
        loop_id: str = "trading_loop_main",
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialize heartbeat manager.

        Args:
            interval_seconds: Heartbeat interval in seconds (default: 10)
            loop_id: Unique identifier for loop instance
            logger: Optional logger (creates default if not provided)

        Raises:
            ValueError: If interval_seconds <= 0
        """
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be > 0")

        self.interval_seconds = interval_seconds
        self.loop_id = loop_id
        self._lock = asyncio.Lock()
        self._logger = logger or logging.getLogger(__name__)

    async def emit(
        self,
        signals_processed: int = 0,
        trades_executed: int = 0,
        error_count: int = 0,
        loop_duration_ms: float = 0.0,
        positions_open: int = 0,
        account_equity: float = 0.0,
        total_signals_lifetime: int = 0,
        total_trades_lifetime: int = 0,
    ) -> HeartbeatMetrics:
        """Emit a heartbeat with current metrics.

        Uses async lock to ensure only one heartbeat emits concurrently.
        Records metrics to observability stack and logs structured message.

        Args:
            signals_processed: Signals processed in current interval
            trades_executed: Successful trades in current interval
            error_count: Errors encountered in current interval
            loop_duration_ms: How long current iteration took
            positions_open: Current number of open positions
            account_equity: Current account equity
            total_signals_lifetime: Total signals since loop start
            total_trades_lifetime: Total trades since loop start

        Returns:
            HeartbeatMetrics: The emitted metrics

        Example:
            >>> metrics = await heartbeat.emit(
            ...     signals_processed=3,
            ...     trades_executed=1,
            ...     positions_open=1,
            ...     account_equity=10250.50
            ... )
            >>> assert metrics.timestamp is not None
        """
        async with self._lock:
            now = datetime.now(UTC)

            metrics = HeartbeatMetrics(
                timestamp=now,
                loop_id=self.loop_id,
                signals_processed=signals_processed,
                trades_executed=trades_executed,
                error_count=error_count,
                loop_duration_ms=loop_duration_ms,
                positions_open=positions_open,
                account_equity=account_equity,
                total_signals_lifetime=total_signals_lifetime,
                total_trades_lifetime=total_trades_lifetime,
            )

            # Record metrics to observability stack
            try:
                metrics_registry = get_metrics()
                metrics_registry.heartbeat_total.inc()
            except Exception as e:
                self._logger.warning(
                    "Failed to record heartbeat metric",
                    extra={"error": str(e)},
                )

            # Log structured heartbeat
            self._logger.info(
                "heartbeat_emitted",
                extra={
                    "loop_id": self.loop_id,
                    "timestamp": now.isoformat(),
                    "signals_processed": signals_processed,
                    "trades_executed": trades_executed,
                    "error_count": error_count,
                    "loop_duration_ms": loop_duration_ms,
                    "positions_open": positions_open,
                    "account_equity": account_equity,
                    "total_signals_lifetime": total_signals_lifetime,
                    "total_trades_lifetime": total_trades_lifetime,
                },
            )

            return metrics

    async def start_background_heartbeat(
        self,
        metrics_provider: Callable[[], dict[str, Any]],
    ) -> asyncio.Task[None]:
        """Start background heartbeat task.

        Periodically calls metrics_provider and emits heartbeat at configured
        interval. Logs errors but continues running.

        Args:
            metrics_provider: Async callable that returns metrics dict with
                keys: signals_processed, trades_executed, error_count,
                loop_duration_ms, positions_open, account_equity,
                total_signals_lifetime, total_trades_lifetime

        Returns:
            asyncio.Task: Background task that can be awaited or cancelled

        Example:
            >>> async def get_stats():
            ...     return {
            ...         "signals_processed": 5,
            ...         "trades_executed": 2,
            ...         "error_count": 0,
            ...         "loop_duration_ms": 100.0,
            ...         "positions_open": 1,
            ...         "account_equity": 10250.50,
            ...         "total_signals_lifetime": 150,
            ...         "total_trades_lifetime": 75,
            ...     }
            >>> task = await heartbeat.start_background_heartbeat(get_stats)
            >>> # Task now runs in background
            >>> task.cancel()  # Stop heartbeat
        """

        async def _heartbeat_loop() -> None:
            """Background loop that emits heartbeat at interval."""
            while True:
                try:
                    await asyncio.sleep(self.interval_seconds)

                    metrics = metrics_provider()
                    await self.emit(**metrics)
                except asyncio.CancelledError:
                    self._logger.info(
                        "Heartbeat background task cancelled",
                        extra={"loop_id": self.loop_id},
                    )
                    raise
                except Exception as e:
                    self._logger.error(
                        "Error in heartbeat background task",
                        extra={"loop_id": self.loop_id, "error": str(e)},
                    )

        return asyncio.create_task(_heartbeat_loop())
