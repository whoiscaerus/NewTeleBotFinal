"""Risk management guards for automated position closing.

This module implements guard functions to enforce maximum drawdown and minimum
equity thresholds. Automatically closes all positions when thresholds are
breached to prevent catastrophic losses.

Features:
- Max drawdown monitoring and enforcement
- Minimum equity threshold monitoring
- Automatic position closure on threshold breach
- Telegram alerts on guard triggers
- Guard state tracking and recovery

Example:
    >>> guards = Guards(
    ...     max_drawdown_percent=20.0,
    ...     min_equity_gbp=500.0,
    ...     alert_service=telegram_alerts
    ... )
    >>> state = await guards.check_and_enforce(mt5_client, order_service)
    >>> if state.cap_triggered:
    ...     print(f"Drawdown guard triggered: {state.current_drawdown}%")
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from backend.app.observability.metrics import get_metrics


@dataclass
class GuardState:
    """Current state of risk guards.

    Attributes:
        current_drawdown: Current drawdown percentage (0-100)
        entry_equity: Initial equity when guard started monitoring
        peak_equity: Highest equity reached so far
        current_equity: Current account equity
        cap_triggered: Whether drawdown cap has been exceeded
        min_equity_triggered: Whether minimum equity threshold breached
        last_check_time: When guards were last evaluated
        triggered_at: When guard was triggered (None if not triggered)
        reason: Why guard was triggered (if triggered)
    """

    current_drawdown: float = 0.0
    entry_equity: float | None = None
    peak_equity: float | None = None
    current_equity: float = 0.0
    cap_triggered: bool = False
    min_equity_triggered: bool = False
    last_check_time: datetime = field(default_factory=lambda: datetime.now(UTC))
    triggered_at: datetime | None = None
    reason: str = ""


class Guards:
    """Enforces maximum drawdown and minimum equity constraints.

    Monitors account equity and automatically closes all positions when
    either the maximum drawdown threshold or minimum equity threshold
    is breached. Non-negotiable safety mechanism.

    Attributes:
        max_drawdown_percent: Maximum allowed drawdown (e.g., 20.0 for 20%)
        min_equity_gbp: Minimum account balance in GBP
        alert_service: Optional Telegram alert service
        logger: Structured logger instance
        _peak_equity: Tracks peak equity since monitoring started
        _entry_equity: Initial equity at monitoring start
    """

    def __init__(
        self,
        max_drawdown_percent: float = 20.0,
        min_equity_gbp: float = 500.0,
        alert_service: Any = None,
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialize guards.

        Args:
            max_drawdown_percent: Max drawdown threshold (0-100)
            min_equity_gbp: Minimum equity threshold in GBP
            alert_service: Optional Telegram alerts service
            logger: Optional logger (creates default if not provided)

        Raises:
            ValueError: If thresholds invalid
        """
        if not (0 < max_drawdown_percent < 100):
            raise ValueError("max_drawdown_percent must be between 0 and 100")
        if min_equity_gbp <= 0:
            raise ValueError("min_equity_gbp must be > 0")

        self.max_drawdown_percent = max_drawdown_percent
        self.min_equity_gbp = min_equity_gbp
        self.alert_service = alert_service
        self._logger = logger or logging.getLogger(__name__)

        # Internal state tracking
        self._peak_equity: float | None = None
        self._entry_equity: float | None = None

    async def check_and_enforce(
        self,
        mt5_client: Any,
        order_service: Any,
        current_positions: list[dict] | None = None,
    ) -> GuardState:
        """Check guards and enforce constraints.

        Fetches current account equity from MT5, calculates drawdown,
        and closes all positions if thresholds breached.

        Args:
            mt5_client: MT5 client for account info and position closing
            order_service: Service for closing positions
            current_positions: Optional list of current positions

        Returns:
            GuardState: Current state of guards

        Raises:
            Exception: If MT5 account info retrieval fails
        """
        try:
            # Get account info from MT5
            account_info = await mt5_client.get_account_info()
            current_equity = account_info.get("equity", 0.0)

            state = GuardState(current_equity=current_equity)

            # Initialize entry equity on first check
            if self._entry_equity is None:
                self._entry_equity = current_equity
                self._peak_equity = current_equity
                state.entry_equity = current_equity
                state.peak_equity = current_equity
            else:
                state.entry_equity = self._entry_equity
                state.peak_equity = self._peak_equity

            # Update peak equity
            if current_equity > self._peak_equity:
                self._peak_equity = current_equity
                state.peak_equity = self._peak_equity

            # Calculate drawdown
            if state.peak_equity and state.peak_equity > 0:
                state.current_drawdown = (
                    (state.peak_equity - current_equity) / state.peak_equity * 100
                )
            else:
                state.current_drawdown = 0.0

            state.last_check_time = datetime.now(UTC)

            # Check max drawdown threshold
            if state.current_drawdown >= self.max_drawdown_percent:
                state.cap_triggered = True
                state.triggered_at = datetime.now(UTC)
                state.reason = (
                    f"Drawdown {state.current_drawdown:.1f}% "
                    f"exceeds cap {self.max_drawdown_percent:.1f}%"
                )

                self._logger.error(
                    "Drawdown guard triggered",
                    extra={
                        "current_drawdown": state.current_drawdown,
                        "max_drawdown": self.max_drawdown_percent,
                        "current_equity": current_equity,
                        "peak_equity": state.peak_equity,
                    },
                )

                # Close all positions
                await order_service.close_all_positions(reason=state.reason)

                # Record metric
                try:
                    metrics_registry = get_metrics()
                    metrics_registry.drawdown_block_total.inc()
                except Exception as e:
                    self._logger.warning(
                        "Failed to record drawdown metric",
                        extra={"error": str(e)},
                    )

                # Send alert
                if self.alert_service:
                    try:
                        await self.alert_service.send_owner_alert(
                            f"⚠️ DRAWDOWN GUARD TRIGGERED\n"
                            f"Drawdown: {state.current_drawdown:.1f}%\n"
                            f"Threshold: {self.max_drawdown_percent:.1f}%\n"
                            f"Equity: £{current_equity:.2f}\n"
                            f"Peak: £{state.peak_equity:.2f}\n\n"
                            f"All positions closed automatically."
                        )
                    except Exception as e:
                        self._logger.error(
                            "Failed to send drawdown alert",
                            extra={"error": str(e)},
                        )

            # Check minimum equity threshold
            if current_equity < self.min_equity_gbp:
                state.min_equity_triggered = True
                state.triggered_at = datetime.now(UTC)
                state.reason = (
                    f"Equity £{current_equity:.2f} "
                    f"below minimum £{self.min_equity_gbp:.2f}"
                )

                self._logger.error(
                    "Minimum equity guard triggered",
                    extra={
                        "current_equity": current_equity,
                        "min_equity": self.min_equity_gbp,
                    },
                )

                # Close all positions
                await order_service.close_all_positions(reason=state.reason)

                # Send alert
                if self.alert_service:
                    try:
                        await self.alert_service.send_owner_alert(
                            f"🛑 MINIMUM EQUITY GUARD TRIGGERED\n"
                            f"Current: £{current_equity:.2f}\n"
                            f"Minimum: £{self.min_equity_gbp:.2f}\n\n"
                            f"All positions closed automatically."
                        )
                    except Exception as e:
                        self._logger.error(
                            "Failed to send min equity alert",
                            extra={"error": str(e)},
                        )

            return state

        except Exception as e:
            self._logger.error(
                "Error checking guards",
                extra={"error": str(e)},
                exc_info=True,
            )
            raise


async def enforce_max_drawdown(
    max_drawdown_percent: float,
    mt5_client: Any,
    order_service: Any,
    current_positions: list[dict] | None = None,
    alert_service: Any = None,
    logger: logging.Logger | None = None,
) -> GuardState:
    """Enforce maximum drawdown constraint.

    Convenience function to check and enforce max drawdown using Guards class.

    Args:
        max_drawdown_percent: Maximum allowed drawdown percentage
        mt5_client: MT5 client
        order_service: Order service for closing positions
        current_positions: Optional list of current positions
        alert_service: Optional alert service
        logger: Optional logger

    Returns:
        GuardState: Current guard state

    Example:
        >>> state = await enforce_max_drawdown(
        ...     max_drawdown_percent=20.0,
        ...     mt5_client=mt5,
        ...     order_service=orders,
        ...     alert_service=alerts
        ... )
        >>> if state.cap_triggered:
        ...     print("Drawdown guard triggered")
    """
    guards = Guards(
        max_drawdown_percent=max_drawdown_percent,
        alert_service=alert_service,
        logger=logger,
    )
    return await guards.check_and_enforce(
        mt5_client,
        order_service,
        current_positions,
    )


async def min_equity_guard(
    min_equity_gbp: float,
    mt5_client: Any,
    order_service: Any,
    current_positions: list[dict] | None = None,
    alert_service: Any = None,
    logger: logging.Logger | None = None,
) -> GuardState:
    """Enforce minimum equity constraint.

    Convenience function to check and enforce min equity using Guards class.

    Args:
        min_equity_gbp: Minimum allowed equity in GBP
        mt5_client: MT5 client
        order_service: Order service for closing positions
        current_positions: Optional list of current positions
        alert_service: Optional alert service
        logger: Optional logger

    Returns:
        GuardState: Current guard state

    Example:
        >>> state = await min_equity_guard(
        ...     min_equity_gbp=500.0,
        ...     mt5_client=mt5,
        ...     order_service=orders,
        ...     alert_service=alerts
        ... )
        >>> if state.min_equity_triggered:
        ...     print("Minimum equity guard triggered")
    """
    guards = Guards(
        min_equity_gbp=min_equity_gbp,
        alert_service=alert_service,
        logger=logger,
    )
    return await guards.check_and_enforce(
        mt5_client,
        order_service,
        current_positions,
    )
