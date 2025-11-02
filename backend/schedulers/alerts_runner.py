"""
PR-044: Price Alerts Scheduler - Background alert evaluation

Runs periodically (every 1 minute) to:
1. Fetch all active price alerts
2. Get current market prices
3. Evaluate which alerts should trigger
4. Send Telegram + Mini App notifications
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, Protocol


from backend.app.alerts.service import PriceAlertService
from backend.app.core.db import SessionLocal

logger = logging.getLogger(__name__)


class PricingService(Protocol):
    """Protocol for pricing service interface."""

    async def get_current_prices(self, symbols: list[str]) -> dict[str, float]:
        """Get current prices for symbols."""
        ...


class AlertsRunner:
    """
    Background scheduler for price alert evaluation.
    Runs every 60 seconds.
    """

    def __init__(
        self,
        alert_service: PriceAlertService,
        pricing_service: PricingService,
        check_interval_seconds: int = 60,
    ):
        """
        Initialize alerts runner.

        Args:
            alert_service: Price alert service instance
            pricing_service: Pricing service for current prices
            check_interval_seconds: How often to check (default 60s = 1 minute)
        """
        self.alert_service = alert_service
        self.pricing_service = pricing_service
        self.check_interval = check_interval_seconds
        self.is_running = False
        self.last_check: Optional[datetime] = None
        self.alerts_evaluated = 0
        self.alerts_triggered = 0

    async def start(self) -> None:
        """
        Start the background scheduler.
        Runs indefinitely until stopped.
        """
        self.is_running = True
        logger.info(f"Starting alerts scheduler (check every {self.check_interval}s)")

        try:
            while self.is_running:
                try:
                    await self._run_check()
                    await asyncio.sleep(self.check_interval)

                except asyncio.CancelledError:
                    logger.info("Alerts scheduler cancelled")
                    break

                except Exception as e:
                    logger.error(f"Error in alerts scheduler: {e}", exc_info=True)
                    # Continue despite error
                    await asyncio.sleep(self.check_interval)

        finally:
            self.is_running = False
            logger.info("Alerts scheduler stopped")

    async def stop(self) -> None:
        """Stop the background scheduler."""
        self.is_running = False
        logger.info("Stopping alerts scheduler")

    async def _run_check(self) -> None:
        """
        Run one evaluation cycle:
        1. Get current prices for all symbols
        2. Evaluate all active alerts
        3. Send notifications for triggered alerts
        """
        start_time = datetime.utcnow()
        self.last_check = start_time

        async with SessionLocal() as db:
            try:
                # Get all symbols we have alerts for
                all_alerts = await db.execute(
                    "SELECT DISTINCT symbol FROM price_alerts WHERE is_active = true"
                )
                symbols = [row[0] for row in all_alerts.fetchall()]

                if not symbols:
                    logger.debug("No active alerts, skipping check")
                    return

                logger.debug(f"Evaluating alerts for {len(symbols)} symbols")

                # Fetch current prices
                current_prices = await self.pricing_service.get_current_prices(symbols)

                if not current_prices:
                    logger.warning("Failed to fetch current prices")
                    return

                logger.debug(f"Got prices for {len(current_prices)} symbols")

                # Evaluate which alerts should trigger
                triggered = await self.alert_service.evaluate_alerts(
                    db=db, current_prices=current_prices
                )

                self.alerts_evaluated += len(symbols)
                self.alerts_triggered += len(triggered)

                # Send notifications
                if triggered:
                    logger.info(
                        f"Sending notifications for {len(triggered)} triggered alerts"
                    )
                    await self.alert_service.send_notifications(
                        db=db, triggered_alerts=triggered
                    )

                # Log metrics
                elapsed = (datetime.utcnow() - start_time).total_seconds()
                logger.info(
                    f"Alerts check complete: {len(symbols)} symbols, "
                    f"{len(triggered)} triggered, {elapsed:.2f}s",
                    extra={
                        "symbols_checked": len(symbols),
                        "alerts_triggered": len(triggered),
                        "elapsed_ms": int(elapsed * 1000),
                    },
                )

            except Exception as e:
                logger.error(f"Error during alert evaluation: {e}", exc_info=True)

    def get_stats(self) -> dict:
        """
        Get scheduler statistics.

        Returns:
            Dict with running, last_check, alerts_evaluated, alerts_triggered
        """
        return {
            "is_running": self.is_running,
            "last_check": self.last_check.isoformat() if self.last_check else None,
            "check_interval_seconds": self.check_interval,
            "total_alerts_evaluated": self.alerts_evaluated,
            "total_alerts_triggered": self.alerts_triggered,
        }


# Global runner instance
_runner: Optional[AlertsRunner] = None


async def initialize_alerts_scheduler(
    alert_service: PriceAlertService,
    pricing_service: PricingService,
) -> None:
    """
    Initialize and start the alerts scheduler.

    Args:
        alert_service: Price alert service
        pricing_service: Pricing service
    """
    global _runner

    if _runner is not None:
        logger.warning("Alerts scheduler already initialized")
        return

    _runner = AlertsRunner(alert_service, pricing_service)
    asyncio.create_task(_runner.start())
    logger.info("Alerts scheduler initialized")


async def get_alerts_runner() -> Optional[AlertsRunner]:
    """Get the global alerts runner instance."""
    return _runner


async def stop_alerts_scheduler() -> None:
    """Stop the alerts scheduler."""
    global _runner
    if _runner:
        await _runner.stop()
        _runner = None
        logger.info("Alerts scheduler stopped")
