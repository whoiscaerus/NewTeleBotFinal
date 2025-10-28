"""MT5 Position Sync Scheduler.

Periodically syncs all active users' MT5 positions with bot trades.
Runs every 10 seconds with circuit breaker and error tracking.
"""

import asyncio
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.models import User
from backend.app.core.logging import get_logger
from backend.app.trading.reconciliation.mt5_sync import run_reconciliation_sync

logger = get_logger(__name__)


class ReconciliationScheduler:
    """Orchestrates periodic position reconciliation for all users."""

    def __init__(
        self,
        db_session_factory,
        mt5_session,
        sync_interval_seconds: int = 10,
        max_concurrent_syncs: int = 5,
    ):
        """Initialize reconciliation scheduler.

        Args:
            db_session_factory: Async session factory
            mt5_session: MT5SessionManager instance
            sync_interval_seconds: How often to run full sync (default 10s)
            max_concurrent_syncs: Max concurrent user syncs (default 5)
        """
        self.db_factory = db_session_factory
        self.mt5 = mt5_session
        self.sync_interval = sync_interval_seconds
        self.max_concurrent = max_concurrent_syncs
        self.is_running = False
        self.last_sync_time: datetime | None = None
        self.sync_count = 0
        self.error_count = 0

    async def start(self) -> None:
        """Start the reconciliation scheduler.

        Runs in background indefinitely, syncing positions every N seconds.
        """
        self.is_running = True
        logger.info(
            "Reconciliation scheduler started",
            extra={
                "sync_interval_seconds": self.sync_interval,
                "max_concurrent_syncs": self.max_concurrent,
            },
        )

        while self.is_running:
            try:
                await self._run_sync_cycle()
                await asyncio.sleep(self.sync_interval)
            except Exception as e:
                logger.error(
                    f"Reconciliation cycle error: {e}",
                    exc_info=True,
                )
                self.error_count += 1
                await asyncio.sleep(self.sync_interval)

    async def stop(self) -> None:
        """Stop the reconciliation scheduler gracefully."""
        logger.info("Reconciliation scheduler stopping...")
        self.is_running = False

    async def _run_sync_cycle(self) -> None:
        """Run a single reconciliation cycle for all active users."""
        start_time = datetime.now(UTC)

        try:
            # Get list of all active users
            async with self.db_factory() as db:
                users = await self._get_active_users(db)

            if not users:
                logger.debug("No active users to sync")
                return

            logger.info(
                f"Starting sync cycle for {len(users)} users",
                extra={"user_count": len(users)},
            )

            # Sync users concurrently with limit
            tasks = [self._sync_user_with_error_handling(user) for user in users]

            # Run in batches to avoid overwhelming MT5
            for i in range(0, len(tasks), self.max_concurrent):
                batch = tasks[i : i + self.max_concurrent]
                results = await asyncio.gather(*batch, return_exceptions=True)

                # Log batch results
                successful = sum(
                    1 for r in results if isinstance(r, dict) and not r.get("errors")
                )
                logger.info(
                    f"Sync batch completed: {successful}/{len(batch)} successful"
                )

            # Calculate cycle duration
            duration = (datetime.now(UTC) - start_time).total_seconds()
            self.sync_count += 1
            self.last_sync_time = start_time

            logger.info(
                "Sync cycle completed",
                extra={
                    "duration_seconds": duration,
                    "total_cycles": self.sync_count,
                    "users_synced": len(users),
                },
            )

        except Exception as e:
            logger.error(
                f"Failed to run sync cycle: {e}",
                exc_info=True,
            )
            self.error_count += 1

    async def _get_active_users(self, db: AsyncSession) -> list[User]:
        """Get all active users who should be synced.

        A user is active if:
        - They have at least one open position
        - They've logged in within the last 30 days
        - Their account is not suspended

        Args:
            db: AsyncSession

        Returns:
            List of User objects
        """
        try:
            # Query users with recent activity
            stmt = select(User).where(
                and_(
                    User.is_active,
                    User.last_login_at.isnot(None),
                )
            )
            result = await db.execute(stmt)
            users = list(result.scalars().all())

            return users

        except Exception as e:
            logger.error(f"Failed to get active users: {e}", exc_info=True)
            return []

    async def _sync_user_with_error_handling(self, user: User) -> dict[str, Any]:
        """Sync positions for a single user with error handling.

        Args:
            user: User to sync

        Returns:
            Sync result dict
        """
        async with self.db_factory() as db:
            try:
                result = await run_reconciliation_sync(db, self.mt5, user)

                if not isinstance(result, dict):
                    result = {}

                if result.get("errors"):
                    logger.warning(
                        f"Sync for user {user.id} had errors",
                        extra={
                            "user_id": str(user.id),
                            "errors": result["errors"],
                        },
                    )
                else:
                    logger.debug(
                        f"Sync for user {user.id} successful",
                        extra={
                            "user_id": str(user.id),
                            "matched_count": result.get("matched_count", 0),
                        },
                    )

                return cast(dict[str, Any], result)

            except Exception as e:
                logger.error(
                    f"Exception syncing user {user.id}: {e}",
                    exc_info=True,
                    extra={"user_id": str(user.id)},
                )
                return {
                    "matched_count": 0,
                    "divergences_count": 0,
                    "new_positions_count": 0,
                    "closed_positions_count": 0,
                    "errors": [str(e)],
                }

    async def get_status(self) -> dict:
        """Get current scheduler status.

        Returns:
            Dict with scheduler metrics
        """
        return {
            "is_running": self.is_running,
            "sync_count": self.sync_count,
            "error_count": self.error_count,
            "last_sync_time": (
                self.last_sync_time.isoformat() if self.last_sync_time else None
            ),
            "sync_interval_seconds": self.sync_interval,
            "max_concurrent_syncs": self.max_concurrent,
        }


# Global scheduler instance (initialized at app startup)
_scheduler: ReconciliationScheduler | None = None


async def initialize_reconciliation_scheduler(
    db_factory, mt5_session, **kwargs
) -> ReconciliationScheduler:
    """Initialize and start the reconciliation scheduler.

    Args:
        db_factory: Async session factory
        mt5_session: MT5SessionManager instance
        **kwargs: Additional options (sync_interval_seconds, max_concurrent_syncs)

    Returns:
        Initialized ReconciliationScheduler instance
    """
    global _scheduler

    _scheduler = ReconciliationScheduler(
        db_factory,
        mt5_session,
        sync_interval_seconds=kwargs.get("sync_interval_seconds", 10),
        max_concurrent_syncs=kwargs.get("max_concurrent_syncs", 5),
    )

    # Start scheduler in background
    asyncio.create_task(_scheduler.start())

    logger.info("Reconciliation scheduler initialized and started")
    return _scheduler


def get_scheduler() -> ReconciliationScheduler | None:
    """Get the global reconciliation scheduler instance.

    Returns:
        ReconciliationScheduler or None if not initialized
    """
    return _scheduler
