"""Celery background tasks for risk management.

Scheduled and async tasks:
- calculate_exposure_snapshots: Periodic exposure snapshot (runs every 1 hour)
- check_drawdown_breakers: Check for breach of drawdown limits (runs every 15 min)
"""

import logging
from datetime import datetime
from decimal import Decimal

from celery import shared_task
from sqlalchemy import distinct, select

from backend.app.core.db import get_async_session
from backend.app.risk.models import ExposureSnapshot, RiskProfile
from backend.app.risk.service import RiskService
from backend.app.trading.store.models import Trade

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def calculate_exposure_snapshots_task(self):
    """
    Periodic task: Calculate exposure snapshots for all active clients.

    Runs every 1 hour to record historical exposure data.
    Used for analytics, reporting, and drawdown tracking.

    Success: Log count of clients processed
    Failure: Retry with exponential backoff (max 3 retries)

    Returns:
        dict: Execution summary
    """
    import asyncio

    async def _run():
        async with await get_async_session() as db:
            try:
                # Get all unique clients with open trades
                stmt = select(distinct(Trade.user_id)).where(Trade.status == "OPEN")
                result = await db.execute(stmt)
                client_ids = result.scalars().all()

                logger.info(
                    f"Calculating exposure snapshots for {len(client_ids)} clients"
                )

                # Calculate exposure for each client
                successful = 0
                failed = 0

                for client_id in client_ids:
                    try:
                        await RiskService.calculate_current_exposure(client_id, db)
                        successful += 1
                    except Exception as e:
                        logger.warning(
                            f"Failed to calculate exposure for {client_id}: {e}"
                        )
                        failed += 1

                logger.info(
                    f"Exposure snapshot calculation complete: "
                    f"{successful} successful, {failed} failed"
                )

                return {
                    "status": "success",
                    "clients_processed": successful,
                    "failures": failed,
                }

            except Exception as e:
                logger.error(f"Exposure snapshot task failed: {e}", exc_info=True)
                # Retry with exponential backoff
                raise self.retry(exc=e, countdown=60 * (2**self.request.retries))

    return asyncio.run(_run())


@shared_task(bind=True, max_retries=3)
def check_drawdown_breakers_task(self):
    """
    Periodic task: Check for drawdown limit breaches.

    Runs every 15 minutes to identify clients who have exceeded
    their max drawdown limits. Issues warnings and alerts.

    Issues:
    - WARNING: Client at 80%+ of drawdown limit
    - CRITICAL: Client exceeded drawdown limit
    - ACTION: May trigger automatic position closure or alerts

    Success: Log count of breaches detected
    Failure: Retry with exponential backoff

    Returns:
        dict: Breach summary
    """
    import asyncio

    async def _run():
        async with await get_async_session() as db:
            try:
                # Get all active risk profiles
                stmt = select(RiskProfile)
                result = await db.execute(stmt)
                profiles = result.scalars().all()

                logger.info(f"Checking drawdown limits for {len(profiles)} clients")

                warnings = []
                critical = []

                for profile in profiles:
                    try:
                        # Calculate current drawdown
                        drawdown = await RiskService.calculate_current_drawdown(
                            profile.client_id, db
                        )

                        # Check against limit
                        if drawdown >= profile.max_drawdown_percent:
                            critical.append(
                                {
                                    "client_id": profile.client_id,
                                    "drawdown": str(drawdown),
                                    "limit": str(profile.max_drawdown_percent),
                                }
                            )
                            logger.critical(
                                f"DRAWDOWN BREACH: Client {profile.client_id} "
                                f"at {drawdown}% (limit: {profile.max_drawdown_percent}%)"
                            )

                        elif drawdown >= profile.max_drawdown_percent * Decimal("0.80"):
                            warnings.append(
                                {
                                    "client_id": profile.client_id,
                                    "drawdown": str(drawdown),
                                    "limit": str(profile.max_drawdown_percent),
                                }
                            )
                            logger.warning(
                                f"DRAWDOWN WARNING: Client {profile.client_id} "
                                f"at {drawdown}% (80% of limit {profile.max_drawdown_percent}%)"
                            )

                    except Exception as e:
                        logger.warning(
                            f"Failed to check drawdown for {profile.client_id}: {e}"
                        )

                logger.info(
                    f"Drawdown check complete: "
                    f"{len(warnings)} warnings, {len(critical)} critical"
                )

                return {
                    "status": "success",
                    "warnings": len(warnings),
                    "critical_breaches": len(critical),
                    "warning_details": warnings,
                    "critical_details": critical,
                }

            except Exception as e:
                logger.error(f"Drawdown breaker task failed: {e}", exc_info=True)
                # Retry
                raise self.retry(exc=e, countdown=60 * (2**self.request.retries))

    return asyncio.run(_run())


@shared_task(bind=True, max_retries=2)
def cleanup_old_exposure_snapshots_task(self):
    """
    Periodic task: Clean up old exposure snapshots.

    Runs weekly to delete exposure snapshots older than 90 days.
    Keeps recent data for analytics while managing database size.

    Retention: 90 days of exposure history

    Returns:
        dict: Cleanup summary
    """
    import asyncio
    from datetime import timedelta

    async def _run():
        async with await get_async_session() as db:
            try:
                # Calculate cutoff date (90 days ago)
                cutoff = datetime.utcnow() - timedelta(days=90)

                # Delete old snapshots
                stmt = select(ExposureSnapshot).where(
                    ExposureSnapshot.timestamp < cutoff
                )
                result = await db.execute(stmt)
                old_snapshots = result.scalars().all()

                count = len(old_snapshots)

                for snapshot in old_snapshots:
                    await db.delete(snapshot)

                await db.commit()

                logger.info(
                    f"Cleaned up {count} exposure snapshots older than {cutoff}"
                )

                return {"status": "success", "snapshots_deleted": count}

            except Exception as e:
                logger.error(f"Snapshot cleanup task failed: {e}", exc_info=True)
                raise self.retry(exc=e, countdown=60 * (2**self.request.retries))

    return asyncio.run(_run())
