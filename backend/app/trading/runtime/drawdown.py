"""Drawdown guard for automated risk management.

This module implements a drawdown guard that monitors account equity and
automatically closes all positions when drawdown exceeds a configurable
threshold. Prevents catastrophic losses during adverse market conditions.

Features:
- Real-time equity monitoring
- Configurable drawdown threshold (e.g., 20%)
- Automatic position closure on threshold breach
- Telegram alerts on drawdown events
- Drawdown recovery tracking
- Graceful error handling

Example:
    >>> guard = DrawdownGuard(
    ...     max_drawdown_percent=20.0,
    ...     alert_service=telegram_alerts
    ... )
    >>> await guard.check_and_enforce(
    ...     mt5_client=mt5,
    ...     order_service=orders
    ... )
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


class DrawdownCapExceededError(Exception):
    """Raised when account drawdown exceeds configured cap.

    Attributes:
        current_drawdown: Current drawdown percentage
        max_drawdown: Maximum allowed drawdown percentage
        message: Human-readable error message
    """

    def __init__(
        self,
        current_drawdown: float,
        max_drawdown: float,
        positions_closed: int = 0,
    ) -> None:
        """Initialize DrawdownCapExceededError.

        Args:
            current_drawdown: Current drawdown percentage
            max_drawdown: Maximum allowed drawdown percentage
            positions_closed: How many positions were closed
        """
        self.current_drawdown = current_drawdown
        self.max_drawdown = max_drawdown
        self.positions_closed = positions_closed

        message = (
            f"Drawdown {current_drawdown:.1f}% exceeds cap {max_drawdown:.1f}%; "
            f"closed {positions_closed} positions"
        )
        super().__init__(message)


@dataclass
class DrawdownState:
    """Current drawdown state tracking.

    Attributes:
        entry_equity: Account equity at start of monitoring
        current_equity: Current account equity
        drawdown_percent: Current drawdown as percentage (0-100)
        drawdown_amount: Current drawdown in account currency
        positions_open: Number of currently open positions
        last_checked: When state was last updated
        positions_closed: Count of positions closed due to cap
        cap_triggered: Whether drawdown cap was triggered
    """

    entry_equity: float
    current_equity: float
    drawdown_percent: float
    drawdown_amount: float
    positions_open: int
    last_checked: datetime
    positions_closed: int = 0
    cap_triggered: bool = False


class DrawdownGuard:
    """Automated drawdown cap enforcement.

    Monitors account equity and closes all positions when drawdown
    exceeds threshold. Implements hard risk limits for live trading.

    Attributes:
        max_drawdown_percent: Maximum allowed drawdown (e.g., 20.0 for 20%)
        alert_service: Optional Telegram alert service
        logger: Structured logger instance

    Example:
        >>> guard = DrawdownGuard(max_drawdown_percent=20.0)
        >>> state = await guard.check_and_enforce(mt5, orders)
        >>> print(f"Current drawdown: {state.drawdown_percent:.1f}%")
    """

    # Class constants
    MIN_DRAWDOWN_THRESHOLD = 1.0  # Minimum 1%
    MAX_DRAWDOWN_THRESHOLD = 99.0  # Maximum 99%
    DRAWDOWN_CHECK_INTERVAL_SECONDS = 5

    def __init__(
        self,
        max_drawdown_percent: float = 20.0,
        alert_service: Any | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialize drawdown guard.

        Args:
            max_drawdown_percent: Maximum allowed drawdown percentage (1-99)
            alert_service: Optional Telegram alert service for notifications
            logger: Optional logger instance (creates default if not provided)

        Raises:
            ValueError: If max_drawdown_percent out of valid range
        """
        # Validate drawdown threshold
        if (
            not self.MIN_DRAWDOWN_THRESHOLD
            <= max_drawdown_percent
            <= self.MAX_DRAWDOWN_THRESHOLD
        ):
            raise ValueError(
                f"max_drawdown_percent must be between {self.MIN_DRAWDOWN_THRESHOLD} "
                f"and {self.MAX_DRAWDOWN_THRESHOLD}, got {max_drawdown_percent}"
            )

        self.max_drawdown_percent = max_drawdown_percent
        self.alert_service = alert_service
        self.logger = logger or logging.getLogger(__name__)

        # Runtime state
        self._entry_equity: float | None = None
        self._cap_triggered = False
        self._positions_closed_count = 0

    async def check_and_enforce(
        self,
        mt5_client: Any,
        order_service: Any,
        force_check: bool = False,
    ) -> DrawdownState:
        """Check drawdown and enforce cap if exceeded.

        Steps:
        1. Get current account equity
        2. Calculate drawdown percentage
        3. If exceeds cap: close all positions and alert
        4. Return current state

        Args:
            mt5_client: MT5 connection client
            order_service: Order management service
            force_check: If True, check even if interval not exceeded

        Returns:
            DrawdownState with current equity/drawdown info

        Raises:
            DrawdownCapExceededError: If cap enforced (positions closed)

        Example:
            >>> try:
            ...     state = await guard.check_and_enforce(mt5, orders)
            ...     print(f"Drawdown: {state.drawdown_percent:.1f}%")
            ... except DrawdownCapExceededError as e:
            ...     print(f"Cap triggered: {e}")
        """
        try:
            # Get current account info
            account_info = await self._get_account_info(mt5_client)

            if not account_info:
                return self._create_empty_state()

            current_equity = account_info.get("equity", 0.0)
            balance = account_info.get("balance", 0.0)

            # Initialize entry equity on first check
            if self._entry_equity is None:
                self._entry_equity = balance
                self.logger.info(
                    f"Drawdown guard initialized with entry equity: £{balance:.2f}",
                    extra={
                        "entry_equity": balance,
                        "max_drawdown_percent": self.max_drawdown_percent,
                    },
                )

            # Calculate current drawdown
            drawdown_state = self._calculate_drawdown(
                entry_equity=self._entry_equity,
                current_equity=current_equity,
                mt5_client=mt5_client,
            )

            # Check if cap exceeded
            if drawdown_state.drawdown_percent > self.max_drawdown_percent:
                if not self._cap_triggered:
                    # Cap triggered for first time
                    await self._enforce_cap(
                        drawdown_state=drawdown_state,
                        order_service=order_service,
                        mt5_client=mt5_client,
                    )

                drawdown_state.cap_triggered = True

            return drawdown_state

        except Exception as e:
            self.logger.error(
                f"Error in drawdown check: {e}",
                extra={"error": str(e), "error_type": type(e).__name__},
                exc_info=True,
            )
            return self._create_empty_state()

    def _calculate_drawdown(
        self,
        entry_equity: float,
        current_equity: float,
        mt5_client: Any,
    ) -> DrawdownState:
        """Calculate current drawdown percentage.

        Formula: drawdown_percent = ((entry - current) / entry) * 100

        Args:
            entry_equity: Starting equity
            current_equity: Current equity
            mt5_client: MT5 client for getting position count

        Returns:
            DrawdownState with calculated drawdown

        Examples:
            >>> # £10,000 → £8,000 = 20% drawdown
            >>> state = guard._calculate_drawdown(10000, 8000, mt5)
            >>> assert state.drawdown_percent == 20.0

            >>> # £10,000 → £0 = 100% drawdown
            >>> state = guard._calculate_drawdown(10000, 0, mt5)
            >>> assert state.drawdown_percent == 100.0
        """
        # Handle edge case: entry equity is zero
        if entry_equity <= 0:
            drawdown_percent = 0.0
            drawdown_amount = 0.0
        else:
            # Calculate drawdown: how much lost from peak
            loss = entry_equity - current_equity
            drawdown_percent = (loss / entry_equity) * 100.0
            drawdown_amount = loss

            # Cap at 100%
            if drawdown_percent > 100.0:
                drawdown_percent = 100.0

        # Get position count
        positions_open = 0
        try:
            positions = mt5_client.get_positions() if mt5_client else []
            positions_open = len(positions) if positions else 0
        except Exception as e:
            self.logger.warning(
                f"Could not get position count: {e}",
                extra={"error": str(e)},
            )

        return DrawdownState(
            entry_equity=entry_equity,
            current_equity=current_equity,
            drawdown_percent=drawdown_percent,
            drawdown_amount=drawdown_amount,
            positions_open=positions_open,
            last_checked=datetime.now(UTC),
            positions_closed=self._positions_closed_count,
            cap_triggered=False,
        )

    async def _enforce_cap(
        self,
        drawdown_state: DrawdownState,
        order_service: Any,
        mt5_client: Any,
    ) -> None:
        """Enforce drawdown cap by closing all positions.

        Called when drawdown exceeds threshold. Closes all open positions
        and sends Telegram alert.

        Args:
            drawdown_state: Current drawdown state
            order_service: Order management service
            mt5_client: MT5 client for getting positions

        Raises:
            DrawdownCapExceededError: Always raised after closing positions
        """
        self._cap_triggered = True

        self.logger.error(
            f"DRAWDOWN CAP TRIGGERED: {drawdown_state.drawdown_percent:.1f}% "
            f"exceeds {self.max_drawdown_percent:.1f}%",
            extra={
                "drawdown_percent": drawdown_state.drawdown_percent,
                "max_drawdown_percent": self.max_drawdown_percent,
                "positions_open": drawdown_state.positions_open,
            },
        )

        # Close all positions
        positions_closed = await self._close_all_positions(
            order_service=order_service,
            mt5_client=mt5_client,
        )

        self._positions_closed_count = positions_closed

        # Send Telegram alert
        if self.alert_service:
            await self._send_alert(drawdown_state, positions_closed)

        # Raise exception for calling code
        raise DrawdownCapExceededError(
            current_drawdown=drawdown_state.drawdown_percent,
            max_drawdown=self.max_drawdown_percent,
            positions_closed=positions_closed,
        )

    async def _close_all_positions(
        self,
        order_service: Any,
        mt5_client: Any,
    ) -> int:
        """Close all open positions.

        Args:
            order_service: Order management service
            mt5_client: MT5 client for getting positions

        Returns:
            Number of positions successfully closed
        """
        positions_closed = 0

        try:
            # Get all open positions
            positions = await mt5_client.get_positions() if mt5_client else []

            if not positions:
                self.logger.info("No open positions to close")
                return 0

            self.logger.info(
                f"Closing {len(positions)} open positions",
                extra={"position_count": len(positions)},
            )

            # Close each position
            for position in positions:
                try:
                    position_id = position.get("id")
                    await order_service.close_position(position_id=position_id)

                    positions_closed += 1

                    self.logger.info(
                        f"Position closed due to drawdown cap: {position_id}",
                        extra={"position_id": position_id},
                    )

                except Exception as e:
                    self.logger.error(
                        f"Error closing position {position.get('id')}: {e}",
                        extra={
                            "position_id": position.get("id"),
                            "error": str(e),
                        },
                        exc_info=True,
                    )

        except Exception as e:
            self.logger.error(
                f"Error closing positions: {e}",
                extra={"error": str(e)},
                exc_info=True,
            )

        return positions_closed

    async def _send_alert(
        self, drawdown_state: DrawdownState, positions_closed: int
    ) -> None:
        """Send Telegram alert about drawdown cap trigger.

        Args:
            drawdown_state: Current drawdown state
            positions_closed: Number of positions that were closed
        """
        try:
            message = (
                f"🚨 DRAWDOWN CAP TRIGGERED\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"Drawdown: {drawdown_state.drawdown_percent:.1f}%\n"
                f"Cap Threshold: {self.max_drawdown_percent:.1f}%\n"
                f"Entry Equity: £{drawdown_state.entry_equity:.2f}\n"
                f"Current Equity: £{drawdown_state.current_equity:.2f}\n"
                f"Loss: £{drawdown_state.drawdown_amount:.2f}\n"
                f"Positions Closed: {positions_closed}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"⚠️ Trading paused. Manual intervention required."
            )

            if self.alert_service:
                await self.alert_service.send_owner_alert(
                    message=message,
                    severity="CRITICAL",
                )

            self.logger.info("Drawdown alert sent to Telegram")

        except Exception as e:
            self.logger.error(
                f"Error sending drawdown alert: {e}",
                extra={"error": str(e)},
                exc_info=True,
            )

    async def _get_account_info(self, mt5_client: Any) -> dict[str, Any] | None:
        """Get account information from MT5.

        Args:
            mt5_client: MT5 connection client

        Returns:
            Dictionary with account info (balance, equity, etc.)
            Returns None if unable to fetch

        Example:
            >>> info = await guard._get_account_info(mt5)
            >>> print(info["balance"])  # £10,000.00
        """
        try:
            if not mt5_client:
                return None

            account_info: dict[str, Any] | None = await mt5_client.get_account_info()
            return account_info

        except Exception as e:
            self.logger.warning(
                f"Could not get account info: {e}",
                extra={"error": str(e)},
            )
            return None

    def _create_empty_state(self) -> DrawdownState:
        """Create empty drawdown state (for error cases).

        Returns:
            DrawdownState with zero values
        """
        return DrawdownState(
            entry_equity=0.0,
            current_equity=0.0,
            drawdown_percent=0.0,
            drawdown_amount=0.0,
            positions_open=0,
            last_checked=datetime.now(UTC),
            positions_closed=0,
            cap_triggered=False,
        )

    def reset(self) -> None:
        """Reset drawdown tracking.

        Clears entry equity and cap triggered flag.
        Used when restarting trading after drawdown recovery.
        """
        self._entry_equity = None
        self._cap_triggered = False
        self._positions_closed_count = 0

        self.logger.info("Drawdown guard reset")

    def get_state_summary(self) -> dict[str, Any]:
        """Get current guard state for monitoring.

        Returns:
            Dictionary with current state information
        """
        return {
            "entry_equity": self._entry_equity,
            "cap_triggered": self._cap_triggered,
            "positions_closed": self._positions_closed_count,
            "max_drawdown_percent": self.max_drawdown_percent,
        }
