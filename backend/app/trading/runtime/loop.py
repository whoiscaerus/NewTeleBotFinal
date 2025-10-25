"""Live trading bot main loop with heartbeat and event emission.

This module implements the core trading loop that processes approved signals,
executes trades via MT5, monitors health, and emits events for analytics.

Features:
- Heartbeat mechanism: Emits health checks every 10 seconds
- Event emission: Signal received, approved, executed events
- Error recovery: Graceful handling with retry logic
- Async operations: Non-blocking signal processing and execution
- Metrics collection: Signal/trade/error counts tracked

Example:
    >>> loop = TradingLoop(mt5_client=mt5, approvals_service=approvals)
    >>> await loop.start(duration_seconds=300)  # Run for 5 minutes
    >>> loop.stop()
"""

import asyncio
import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

# Import from existing modules (assuming they exist from previous PRs)
# from backend.app.core.mt5 import MT5Client  # PR-011
# from backend.app.approvals import ApprovalsService  # PR-014
# from backend.app.trading.orders import OrderService  # PR-015
# from backend.app.core.retry import with_retry  # PR-018
# from backend.app.ops.alerts import OpsAlertService  # PR-018


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


@dataclass
class Event:
    """Base event class for trading loop events.

    Attributes:
        event_type: Type of event (e.g., 'signal_received', 'trade_executed')
        timestamp: When event occurred (UTC)
        loop_id: Which loop instance emitted this event
        metadata: Additional event-specific data
    """

    event_type: str
    timestamp: datetime
    loop_id: str
    metadata: dict[str, Any]


class TradingLoop:
    """Main live trading bot loop.

    Processes approved signals, executes trades via MT5, monitors health,
    and emits events for analytics and monitoring.

    Attributes:
        mt5_client: MT5 integration client (from PR-011)
        approvals_service: Signal approvals service (from PR-014)
        order_service: Order management service (from PR-015)
        retry_decorator: Retry logic for resilient operations (from PR-018)
        alert_service: Telegram alerts service (from PR-018)
        logger: Structured logger instance
        db_session: Database session for persistence

    Example:
        >>> mt5 = MT5Client(...)
        >>> approvals = ApprovalsService(db_session)
        >>> orders = OrderService(db_session)
        >>> loop = TradingLoop(
        ...     mt5_client=mt5,
        ...     approvals_service=approvals,
        ...     order_service=orders
        ... )
        >>> await loop.start(duration_seconds=3600)
    """

    # Class constants
    HEARTBEAT_INTERVAL_SECONDS = 10
    SIGNAL_BATCH_SIZE = 10
    ERROR_LOG_LEVEL = logging.ERROR
    INFO_LOG_LEVEL = logging.INFO

    def __init__(
        self,
        mt5_client: Any,
        approvals_service: Any,
        order_service: Any,
        alert_service: Any | None = None,
        retry_decorator: Any | None = None,
        db_session: AsyncSession | None = None,
        logger: logging.Logger | None = None,
        loop_id: str = "trading_loop_main",
    ) -> None:
        """Initialize trading loop.

        Args:
            mt5_client: MT5 connection and API client
            approvals_service: Service for fetching approved signals
            order_service: Service for placing/closing orders
            alert_service: Optional Telegram alert service
            retry_decorator: Optional retry decorator for resilient calls
            db_session: Optional database session
            logger: Optional logger instance (creates default if not provided)
            loop_id: Unique identifier for this loop instance

        Raises:
            ValueError: If critical services are None
        """
        if not mt5_client:
            raise ValueError("mt5_client is required")
        if not approvals_service:
            raise ValueError("approvals_service is required")
        if not order_service:
            raise ValueError("order_service is required")

        self.mt5_client = mt5_client
        self.approvals_service = approvals_service
        self.order_service = order_service
        self.alert_service = alert_service
        self.retry_decorator = retry_decorator
        self.db_session = db_session
        self.logger = logger or logging.getLogger(__name__)
        self.loop_id = loop_id

        # Runtime state
        self._running = False
        self._last_heartbeat = datetime.now(UTC)
        self._signals_processed_interval = 0
        self._trades_executed_interval = 0
        self._error_count_interval = 0
        self._total_signals_lifetime = 0
        self._total_trades_lifetime = 0
        self._processed_signal_ids: set[str] = set()

    async def start(
        self,
        duration_seconds: float | None = None,
    ) -> None:
        """Start the trading loop.

        Runs continuously (or for specified duration) processing signals,
        executing trades, emitting heartbeats and events.

        Args:
            duration_seconds: If specified, run for this many seconds
                           If None, run indefinitely until stop() called

        Example:
            >>> await loop.start(duration_seconds=3600)  # Run for 1 hour
            >>> await loop.start()  # Run indefinitely
        """
        self._running = True
        start_time = datetime.now(UTC)

        self.logger.info(
            "Trading loop started",
            extra={
                "loop_id": self.loop_id,
                "duration_seconds": duration_seconds,
            },
        )

        try:
            while self._running:
                iteration_start = datetime.now(UTC)

                # Check if duration exceeded
                if duration_seconds:
                    elapsed = (datetime.now(UTC) - start_time).total_seconds()
                    if elapsed >= duration_seconds:
                        self.logger.info(
                            f"Trading loop duration exceeded ({elapsed}s >= {duration_seconds}s)",
                            extra={"loop_id": self.loop_id},
                        )
                        break

                # Main loop iteration
                try:
                    await self._loop_iteration()
                except Exception as e:
                    self._error_count_interval += 1
                    await self._handle_error(e, "loop_iteration")

                # Emit heartbeat if interval exceeded
                iteration_duration = (
                    datetime.now(UTC) - iteration_start
                ).total_seconds()
                await self._check_and_emit_heartbeat(iteration_duration * 1000)

                # Small delay to prevent CPU spinning
                await asyncio.sleep(0.1)

        except KeyboardInterrupt:
            self.logger.info(
                "Trading loop interrupted by user",
                extra={"loop_id": self.loop_id},
            )
        except Exception as e:
            self.logger.error(
                f"Unexpected error in trading loop: {e}",
                extra={"loop_id": self.loop_id, "error": str(e)},
                exc_info=True,
            )
        finally:
            await self.stop()

    async def stop(self) -> None:
        """Stop the trading loop gracefully.

        Closes all open positions, flushes logs, and cleans up resources.
        """
        if not self._running:
            return

        self._running = False
        self.logger.info(
            "Trading loop stopping",
            extra={"loop_id": self.loop_id},
        )

        try:
            # Close all open positions
            await self._close_all_positions()

            # Final heartbeat
            await self._emit_heartbeat_now()

            self.logger.info(
                "Trading loop stopped cleanly",
                extra={
                    "loop_id": self.loop_id,
                    "total_signals": self._total_signals_lifetime,
                    "total_trades": self._total_trades_lifetime,
                },
            )
        except Exception as e:
            self.logger.error(
                f"Error during loop shutdown: {e}",
                extra={"loop_id": self.loop_id},
                exc_info=True,
            )

    async def _loop_iteration(self) -> None:
        """Single iteration of the trading loop.

        Steps:
        1. Fetch approved signals (batch)
        2. For each signal:
           a. Emit signal_received event
           b. Execute trade
           c. Emit signal_executed event
        3. Update metrics
        """
        # Fetch batch of approved signals
        approved_signals = await self._fetch_approved_signals(
            batch_size=self.SIGNAL_BATCH_SIZE
        )

        if not approved_signals:
            # No signals to process
            return

        self.logger.info(
            f"Processing {len(approved_signals)} approved signals",
            extra={
                "loop_id": self.loop_id,
                "signal_count": len(approved_signals),
            },
        )

        # Process each signal
        for signal in approved_signals:
            signal_id = signal.get("id", "unknown")

            # Skip if already processed (idempotency)
            if signal_id in self._processed_signal_ids:
                continue

            try:
                # Emit signal received event
                await self._emit_event(
                    event_type="signal_received",
                    metadata={
                        "signal_id": signal_id,
                        "instrument": signal.get("instrument"),
                        "side": signal.get("side"),
                    },
                )

                # Execute the trade
                execution_result = await self._execute_signal(signal)

                if execution_result.get("success"):
                    self._trades_executed_interval += 1
                    self._total_trades_lifetime += 1

                    # Emit signal executed event
                    await self._emit_event(
                        event_type="signal_executed",
                        metadata={
                            "signal_id": signal_id,
                            "order_id": execution_result.get("order_id"),
                            "execution_time_ms": execution_result.get(
                                "execution_time_ms"
                            ),
                        },
                    )

                # Mark as processed
                self._processed_signal_ids.add(signal_id)
                self._signals_processed_interval += 1
                self._total_signals_lifetime += 1

            except Exception as e:
                self._error_count_interval += 1
                self.logger.error(
                    f"Error processing signal {signal_id}: {e}",
                    extra={
                        "loop_id": self.loop_id,
                        "signal_id": signal_id,
                        "error": str(e),
                    },
                    exc_info=True,
                )

    async def _fetch_approved_signals(self, batch_size: int) -> list[dict[str, Any]]:
        """Fetch batch of approved signals waiting for execution.

        Args:
            batch_size: Maximum number of signals to fetch

        Returns:
            List of approved signal dictionaries

        Raises:
            Exception: If database query fails
        """
        try:
            if not self.approvals_service:
                return []

            signals = await self.approvals_service.get_pending_signals(limit=batch_size)
            return signals or []

        except Exception as e:
            self.logger.error(
                f"Error fetching approved signals: {e}",
                extra={"loop_id": self.loop_id, "error": str(e)},
                exc_info=True,
            )
            self._error_count_interval += 1
            return []

    async def _execute_signal(self, signal: dict[str, Any]) -> dict[str, Any]:
        """Execute a signal by placing trade via MT5.

        Args:
            signal: Signal dictionary with instrument, side, quantity, etc.

        Returns:
            Dictionary with execution result:
                {
                    "success": bool,
                    "order_id": str,
                    "execution_time_ms": float,
                    "error": str (if failed)
                }

        Raises:
            Exception: If order placement fails after retries
        """
        signal_id = signal.get("id", "unknown")
        execution_start = datetime.now(UTC)

        try:
            # Retry logic for resilient execution
            if self.retry_decorator:
                result = await self.retry_decorator(
                    self._place_order,
                    signal=signal,
                    max_retries=3,
                    base_delay=2.0,
                )
            else:
                result = await self._place_order(signal)

            execution_time_ms = (
                datetime.now(UTC) - execution_start
            ).total_seconds() * 1000

            if result.get("success"):
                self.logger.info(
                    f"Signal executed successfully: {signal_id}",
                    extra={
                        "loop_id": self.loop_id,
                        "signal_id": signal_id,
                        "order_id": result.get("order_id"),
                        "execution_time_ms": execution_time_ms,
                    },
                )

                return {
                    "success": True,
                    "order_id": result.get("order_id"),
                    "execution_time_ms": execution_time_ms,
                }
            else:
                error_msg = result.get("error", "Unknown error")
                self.logger.warning(
                    f"Signal execution failed: {signal_id} - {error_msg}",
                    extra={
                        "loop_id": self.loop_id,
                        "signal_id": signal_id,
                        "error": error_msg,
                    },
                )

                return {
                    "success": False,
                    "error": error_msg,
                    "execution_time_ms": execution_time_ms,
                }

        except Exception as e:
            execution_time_ms = (
                datetime.now(UTC) - execution_start
            ).total_seconds() * 1000

            self.logger.error(
                f"Error executing signal: {e}",
                extra={
                    "loop_id": self.loop_id,
                    "signal_id": signal_id,
                    "error": str(e),
                    "execution_time_ms": execution_time_ms,
                },
                exc_info=True,
            )

            return {
                "success": False,
                "error": str(e),
                "execution_time_ms": execution_time_ms,
            }

    async def _place_order(self, signal: dict[str, Any]) -> dict[str, Any]:
        """Place order via MT5 (called by _execute_signal).

        Args:
            signal: Signal with instrument, side, quantity

        Returns:
            Dictionary with success status and order_id
        """
        try:
            if not self.order_service:
                return {"success": False, "error": "Order service not available"}

            order = await self.order_service.place_order(
                instrument=signal.get("instrument"),
                side=signal.get("side"),
                quantity=signal.get("quantity", 1.0),
                order_type=signal.get("order_type", "market"),
                price=signal.get("price"),
            )

            return {
                "success": True,
                "order_id": order.get("id"),
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    async def _check_and_emit_heartbeat(self, loop_duration_ms: float) -> None:
        """Check if heartbeat interval exceeded, emit if needed.

        Args:
            loop_duration_ms: Duration of last loop iteration in milliseconds
        """
        now = datetime.now(UTC)
        time_since_heartbeat = (now - self._last_heartbeat).total_seconds()

        if time_since_heartbeat >= self.HEARTBEAT_INTERVAL_SECONDS:
            await self._emit_heartbeat_now(loop_duration_ms)

    async def _emit_heartbeat_now(self, loop_duration_ms: float = 0.0) -> None:
        """Emit heartbeat with current metrics immediately.

        Args:
            loop_duration_ms: Duration of last loop iteration
        """
        try:
            # Get current account equity
            account_equity = 0.0
            positions_open = 0

            if self.mt5_client:
                try:
                    account_info = await self.mt5_client.get_account_info()
                    account_equity = account_info.get("balance", 0.0)
                except Exception as e:
                    self.logger.warning(
                        f"Could not get account info: {e}",
                        extra={"loop_id": self.loop_id},
                    )

                try:
                    positions = await self.mt5_client.get_positions()
                    positions_open = len(positions) if positions else 0
                except Exception as e:
                    self.logger.warning(
                        f"Could not get positions: {e}",
                        extra={"loop_id": self.loop_id},
                    )

            # Create heartbeat metrics
            metrics = HeartbeatMetrics(
                timestamp=datetime.now(UTC),
                loop_id=self.loop_id,
                signals_processed=self._signals_processed_interval,
                trades_executed=self._trades_executed_interval,
                error_count=self._error_count_interval,
                loop_duration_ms=loop_duration_ms,
                positions_open=positions_open,
                account_equity=account_equity,
                total_signals_lifetime=self._total_signals_lifetime,
                total_trades_lifetime=self._total_trades_lifetime,
            )

            # Log heartbeat as JSON
            heartbeat_dict = asdict(metrics)
            heartbeat_dict["timestamp"] = metrics.timestamp.isoformat()

            self.logger.info(
                "heartbeat",
                extra={
                    "heartbeat": True,
                    **heartbeat_dict,
                },
            )

            # Reset interval counters
            self._signals_processed_interval = 0
            self._trades_executed_interval = 0
            self._error_count_interval = 0
            self._last_heartbeat = datetime.now(UTC)

        except Exception as e:
            self.logger.error(
                f"Error emitting heartbeat: {e}",
                extra={"loop_id": self.loop_id, "error": str(e)},
                exc_info=True,
            )

    async def _emit_event(self, event_type: str, metadata: dict[str, Any]) -> None:
        """Emit an event for analytics tracking.

        Args:
            event_type: Type of event (e.g., 'signal_received', 'trade_executed')
            metadata: Event-specific metadata

        Example:
            >>> await loop._emit_event(
            ...     event_type="signal_executed",
            ...     metadata={"signal_id": "sig_123", "order_id": "ord_456"}
            ... )
        """
        try:
            event = Event(
                event_type=event_type,
                timestamp=datetime.now(UTC),
                loop_id=self.loop_id,
                metadata=metadata,
            )

            # Log event as JSON for analytics
            event_dict = asdict(event)
            event_dict["timestamp"] = event.timestamp.isoformat()

            self.logger.info(
                f"event: {event_type}",
                extra={
                    "event_type": event_type,
                    **event_dict,
                },
            )

        except Exception as e:
            self.logger.error(
                f"Error emitting event: {e}",
                extra={
                    "loop_id": self.loop_id,
                    "event_type": event_type,
                    "error": str(e),
                },
                exc_info=True,
            )

    async def _close_all_positions(self) -> None:
        """Close all open positions gracefully on shutdown.

        Called during loop shutdown to ensure no positions left open.
        """
        if not self.order_service:
            return

        try:
            self.logger.info(
                "Closing all positions",
                extra={"loop_id": self.loop_id},
            )

            positions = await self.order_service.get_open_positions()

            if not positions:
                return

            for position in positions:
                try:
                    await self.order_service.close_position(
                        position_id=position.get("id")
                    )

                    self.logger.info(
                        f"Position closed: {position.get('id')}",
                        extra={
                            "loop_id": self.loop_id,
                            "position_id": position.get("id"),
                        },
                    )

                except Exception as e:
                    self.logger.error(
                        f"Error closing position {position.get('id')}: {e}",
                        extra={
                            "loop_id": self.loop_id,
                            "position_id": position.get("id"),
                            "error": str(e),
                        },
                        exc_info=True,
                    )

        except Exception as e:
            self.logger.error(
                f"Error during position cleanup: {e}",
                extra={"loop_id": self.loop_id, "error": str(e)},
                exc_info=True,
            )

    async def _handle_error(self, error: Exception, context: str) -> None:
        """Handle errors in trading loop gracefully.

        Args:
            error: The exception that occurred
            context: Context where error occurred (for logging)
        """
        self._error_count_interval += 1

        self.logger.error(
            f"Error in {context}: {error}",
            extra={
                "loop_id": self.loop_id,
                "context": context,
                "error": str(error),
                "error_type": type(error).__name__,
            },
            exc_info=True,
        )

        # Send alert if available
        if self.alert_service:
            try:
                await self.alert_service.send_owner_alert(
                    message=f"Trading loop error in {context}: {error}",
                    severity="ERROR",
                )
            except Exception as alert_error:
                self.logger.error(
                    f"Could not send alert: {alert_error}",
                    extra={"loop_id": self.loop_id},
                )
