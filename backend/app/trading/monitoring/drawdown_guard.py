"""
DrawdownGuard Service - Monitor account equity and trigger liquidation on extreme drawdown.

This service tracks account equity against peak equity and automatically closes
all positions if drawdown exceeds the configured threshold. It also sends user
alerts before liquidation.

Author: Trading System
Created: October 2024
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


class DrawdownAlertData:
    """Alert status for drawdown monitoring."""

    def __init__(
        self,
        user_id: str,
        alert_type: str,
        drawdown_pct: float,
        current_equity: float,
        peak_equity: float,
        positions_count: int,
        timestamp: datetime,
    ):
        """Initialize drawdown alert.

        Args:
            user_id: User identifier
            alert_type: Type of alert (warning, critical, liquidation)
            drawdown_pct: Current drawdown percentage
            current_equity: Current account equity in GBP
            peak_equity: Peak equity reached in GBP
            positions_count: Number of open positions
            timestamp: Alert timestamp (UTC)
        """
        self.user_id = user_id
        self.alert_type = alert_type
        self.drawdown_pct = drawdown_pct
        self.current_equity = current_equity
        self.peak_equity = peak_equity
        self.positions_count = positions_count
        self.timestamp = timestamp

    def __repr__(self) -> str:
        """String representation of alert."""
        return (
            f"<DrawdownAlert {self.alert_type}: {self.drawdown_pct:.1f}% "
            f"({self.current_equity:.2f}/{self.peak_equity:.2f})>"
        )


class DrawdownGuard:
    """Protects accounts from catastrophic losses via auto-close.

    When account drawdown exceeds threshold:
    - All open positions are closed immediately
    - Event logged for audit
    - User alerted via Telegram

    Responsibilities:
    1. Track peak equity over time
    2. Calculate current drawdown percentage
    3. Trigger alerts at warning and critical thresholds
    4. Force liquidation if drawdown exceeds maximum
    5. Send user notifications before liquidation

    Example:
        >>> guard = DrawdownGuard(
        ...     max_drawdown_pct=20.0,
        ...     warning_threshold_pct=15.0,
        ...     min_equity_gbp=100.0,
        ...     warning_seconds=10
        ... )
        >>> alert = await guard.check_drawdown(
        ...     current_equity=8000.0,
        ...     peak_equity=10000.0,
        ...     user_id="user_123"
        ... )
        >>> if alert:
        ...     await guard.alert_user_before_close(db, user_id, alert)
    """

    def __init__(
        self,
        max_drawdown_pct: float = 20.0,
        warning_threshold_pct: float = 15.0,
        min_equity_gbp: float = 100.0,
        warning_seconds: int = 10,
    ):
        """Initialize DrawdownGuard with thresholds.

        Args:
            max_drawdown_pct: Maximum allowed drawdown before liquidation (default 20%)
            warning_threshold_pct: Drawdown threshold for warning alert (default 15%)
            min_equity_gbp: Minimum account equity, force close if below (default £100)
            warning_seconds: Seconds before liquidation to send warning (default 10s)
        """
        self.max_drawdown_pct = max_drawdown_pct
        self.warning_threshold_pct = warning_threshold_pct
        self.min_equity_gbp = min_equity_gbp
        self.warning_seconds = warning_seconds
        self.triggered_at: Optional[datetime] = None

        logger.info(
            "DrawdownGuard initialized",
            extra={
                "max_drawdown_pct": max_drawdown_pct,
                "warning_threshold_pct": warning_threshold_pct,
                "min_equity_gbp": min_equity_gbp,
            },
        )

    async def check_drawdown(
        self, current_equity: float, peak_equity: float, user_id: str
    ) -> Optional[DrawdownAlertData]:
        """
        Check current drawdown and return alert if threshold exceeded.

        Args:
            current_equity: Current account equity in GBP
            peak_equity: Peak equity reached in GBP
            user_id: User identifier for logging

        Returns:
            DrawdownAlertData if any threshold exceeded, None otherwise

        Raises:
            ValueError: If equity values invalid (negative or zero)

        Example:
            >>> alert = await guard.check_drawdown(
            ...     current_equity=8000.0,
            ...     peak_equity=10000.0,
            ...     user_id="user_123"
            ... )
            >>> if alert and alert.alert_type == "critical":
            ...     print(f"Liquidation triggered: {alert.drawdown_pct:.1f}%")
        """
        if current_equity < 0 or peak_equity < 0:
            logger.error(
                "Invalid equity values in drawdown check",
                extra={
                    "user_id": user_id,
                    "current_equity": current_equity,
                    "peak_equity": peak_equity,
                },
            )
            raise ValueError("Equity values must be non-negative")

        if peak_equity == 0:
            logger.error(
                "Peak equity cannot be zero",
                extra={"user_id": user_id, "peak_equity": peak_equity},
            )
            raise ValueError("Peak equity must be positive")

        if current_equity > peak_equity:
            logger.warning(
                "Current equity exceeds peak equity (new peak detected)",
                extra={
                    "user_id": user_id,
                    "current_equity": current_equity,
                    "peak_equity": peak_equity,
                },
            )
            peak_equity = current_equity

        # Calculate drawdown percentage
        drawdown_pct = ((peak_equity - current_equity) / peak_equity) * 100

        now = datetime.utcnow()
        positions_count = 0  # Will be updated by caller

        # Check for minimum equity breach (force liquidation)
        if current_equity < self.min_equity_gbp:
            logger.warning(
                "Account equity below minimum threshold",
                extra={
                    "user_id": user_id,
                    "current_equity": current_equity,
                    "min_equity_gbp": self.min_equity_gbp,
                },
            )
            alert = DrawdownAlertData(
                user_id=user_id,
                alert_type="critical",
                drawdown_pct=drawdown_pct,
                current_equity=current_equity,
                peak_equity=peak_equity,
                positions_count=positions_count,
                timestamp=now,
            )
            logger.info(
                f"Drawdown alert (min equity): {alert}", extra={"user_id": user_id}
            )
            return alert

        # Check for critical drawdown (liquidation threshold)
        if drawdown_pct >= self.max_drawdown_pct:
            logger.warning(
                "Critical drawdown threshold exceeded",
                extra={
                    "user_id": user_id,
                    "drawdown_pct": drawdown_pct,
                    "max_drawdown_pct": self.max_drawdown_pct,
                },
            )
            alert = DrawdownAlertData(
                user_id=user_id,
                alert_type="critical",
                drawdown_pct=drawdown_pct,
                current_equity=current_equity,
                peak_equity=peak_equity,
                positions_count=positions_count,
                timestamp=now,
            )
            logger.info(
                f"Drawdown alert (critical): {alert}", extra={"user_id": user_id}
            )
            return alert

        # Check for warning threshold
        if drawdown_pct >= self.warning_threshold_pct:
            logger.info(
                "Drawdown warning threshold reached",
                extra={
                    "user_id": user_id,
                    "drawdown_pct": drawdown_pct,
                    "warning_threshold_pct": self.warning_threshold_pct,
                },
            )
            alert = DrawdownAlertData(
                user_id=user_id,
                alert_type="warning",
                drawdown_pct=drawdown_pct,
                current_equity=current_equity,
                peak_equity=peak_equity,
                positions_count=positions_count,
                timestamp=now,
            )
            return alert

        # No alert needed
        logger.debug(
            "Drawdown within normal range",
            extra={
                "user_id": user_id,
                "drawdown_pct": drawdown_pct,
                "threshold": self.warning_threshold_pct,
            },
        )
        return None

    async def alert_user_before_close(
        self, user_id: str, alert: DrawdownAlertData
    ) -> bool:
        """
        Send user alert before liquidation.

        Args:
            user_id: User identifier
            alert: DrawdownAlertData with details

        Returns:
            True if alert processed successfully

        Example:
            >>> alert_sent = await guard.alert_user_before_close(user_id, alert)
            >>> if alert_sent:
            ...     print(f"User alerted: liquidation in {guard.warning_seconds}s")
        """
        try:
            # Record triggered time
            if self.triggered_at is None:
                self.triggered_at = datetime.utcnow()

            # Prepare alert message
            alert_msg = (
                f"🚨 **DRAWDOWN ALERT** 🚨\n\n"
                f"Drawdown: {alert.drawdown_pct:.1f}%\n"
                f"Current: £{alert.current_equity:.2f}\n"
                f"Peak: £{alert.peak_equity:.2f}\n"
                f"Open Positions: {alert.positions_count}\n\n"
            )

            if alert.alert_type == "critical":
                close_time = datetime.utcnow() + timedelta(seconds=self.warning_seconds)
                alert_msg += (
                    f"⚠️ **LIQUIDATION IMMINENT**\n"
                    f"All positions will be closed in {self.warning_seconds} seconds\n"
                    f"Closing time: {close_time.isoformat()}Z"
                )
            else:
                alert_msg += "⚠️ **WARNING**: Continue with caution"

            logger.warning(
                "Drawdown alert message prepared",
                extra={
                    "user_id": user_id,
                    "alert_type": alert.alert_type,
                    "drawdown_pct": alert.drawdown_pct,
                    "alert_message": alert_msg,
                },
            )

            # TODO: Send Telegram alert to user
            # telegram_service.send_alert(user_id, alert_msg)

            return True

        except Exception as e:
            logger.error(
                f"Error preparing drawdown alert: {e}",
                exc_info=True,
                extra={"user_id": user_id},
            )
            return False


# Global instance (lazy-loaded)
_drawdown_guard: Optional[DrawdownGuard] = None


def get_drawdown_guard(
    max_drawdown_pct: float = 20.0,
    warning_threshold_pct: float = 15.0,
    min_equity_gbp: float = 100.0,
    warning_seconds: int = 10,
) -> DrawdownGuard:
    """Get or create global DrawdownGuard instance.

    Args:
        max_drawdown_pct: Maximum drawdown threshold (default 20%)
        warning_threshold_pct: Warning threshold (default 15%)
        min_equity_gbp: Minimum equity for liquidation (default £100)
        warning_seconds: Seconds before liquidation (default 10)

    Returns:
        DrawdownGuard instance
    """
    global _drawdown_guard

    if _drawdown_guard is None:
        _drawdown_guard = DrawdownGuard(
            max_drawdown_pct=max_drawdown_pct,
            warning_threshold_pct=warning_threshold_pct,
            min_equity_gbp=min_equity_gbp,
            warning_seconds=warning_seconds,
        )

    return _drawdown_guard
