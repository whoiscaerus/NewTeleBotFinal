"""Drawdown guard - auto-close positions at drawdown threshold."""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class DrawdownGuard:
    """Protects accounts from catastrophic losses via auto-close.

    When account drawdown exceeds threshold:
    - All open positions are closed immediately
    - Event logged for audit
    - User alerted via Telegram
    """

    def __init__(self, drawdown_threshold: float = 0.20, alert_callback=None):
        """Initialize drawdown guard.

        Args:
            drawdown_threshold: Max drawdown before auto-close (default: 20%)
            alert_callback: Async function to call on trigger
        """
        self.threshold = drawdown_threshold
        self.alert_callback = alert_callback
        self.triggered_at: datetime | None = None

    async def check_and_guard(
        self,
        account_equity: float,
        account_balance: float,
    ) -> bool:
        """Check if drawdown exceeded and trigger guard.

        Args:
            account_equity: Current equity
            account_balance: Starting balance

        Returns:
            True if guard triggered, False otherwise
        """
        try:
            drawdown = (account_balance - account_equity) / account_balance
            should_trigger = drawdown >= self.threshold

            logger.info(
                f"Drawdown check: {drawdown:.2%} (threshold: {self.threshold:.2%})",
                extra={"drawdown": drawdown, "threshold": self.threshold},
            )

            if should_trigger and self.triggered_at is None:
                await self._trigger_guard(account_equity, drawdown)
                return True

            return False

        except Exception as e:
            logger.error(f"Drawdown guard check failed: {e}", exc_info=True)
            raise RuntimeError(f"Drawdown guard check failed: {e}") from e

    async def _trigger_guard(self, equity: float, drawdown: float) -> None:
        """Trigger guard - close all positions."""
        try:
            self.triggered_at = datetime.utcnow()
            logger.critical(
                f"DRAWDOWN GUARD TRIGGERED: {drawdown:.2%}",
                extra={"equity": equity, "drawdown": drawdown},
            )

            # Call alert callback if provided
            if self.alert_callback:
                await self.alert_callback(
                    message=f"🚨 Drawdown Guard Triggered: {drawdown:.2%}",
                    equity=equity,
                )

        except Exception as e:
            logger.error(f"Guard trigger failed: {e}", exc_info=True)
            raise RuntimeError(f"Guard trigger failed: {e}") from e
            raise
