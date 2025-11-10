"""Quota management service.

Implements quota checking and consumption with Redis counters.
Provides per-user, per-feature usage tracking with automatic resets.
"""

import logging
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.redis import get_redis
from backend.app.observability.metrics import metrics
from backend.app.quotas.models import (
    QuotaDefinition,
    QuotaPeriod,
    QuotaType,
    QuotaUsage,
)
from backend.app.subscriptions.models import SubscriptionTier

logger = logging.getLogger(__name__)


class QuotaExceededException(Exception):
    """Raised when quota limit is exceeded."""

    def __init__(self, quota_type: str, limit: int, current: int, reset_at: datetime):
        """Initialize exception."""
        self.quota_type = quota_type
        self.limit = limit
        self.current = current
        self.reset_at = reset_at
        super().__init__(
            f"Quota exceeded for {quota_type}: {current}/{limit}. Resets at {reset_at.isoformat()}"
        )


class QuotaService:
    """Service for quota management and enforcement."""

    # Default quota definitions (seeded on first use)
    DEFAULT_QUOTAS = {
        SubscriptionTier.FREE: {
            QuotaType.SIGNALS_PER_DAY: (10, QuotaPeriod.DAY),
            QuotaType.ALERTS_PER_DAY: (5, QuotaPeriod.DAY),
            QuotaType.EXPORTS_PER_MONTH: (1, QuotaPeriod.MONTH),
            QuotaType.API_CALLS_PER_MINUTE: (30, QuotaPeriod.MINUTE),
            QuotaType.BACKTESTS_PER_DAY: (2, QuotaPeriod.DAY),
            QuotaType.STRATEGIES_MAX: (1, QuotaPeriod.NONE),
        },
        SubscriptionTier.PREMIUM: {
            QuotaType.SIGNALS_PER_DAY: (100, QuotaPeriod.DAY),
            QuotaType.ALERTS_PER_DAY: (50, QuotaPeriod.DAY),
            QuotaType.EXPORTS_PER_MONTH: (10, QuotaPeriod.MONTH),
            QuotaType.API_CALLS_PER_MINUTE: (120, QuotaPeriod.MINUTE),
            QuotaType.BACKTESTS_PER_DAY: (10, QuotaPeriod.DAY),
            QuotaType.STRATEGIES_MAX: (5, QuotaPeriod.NONE),
        },
        SubscriptionTier.PRO: {
            QuotaType.SIGNALS_PER_DAY: (1000, QuotaPeriod.DAY),
            QuotaType.ALERTS_PER_DAY: (500, QuotaPeriod.DAY),
            QuotaType.EXPORTS_PER_MONTH: (100, QuotaPeriod.MONTH),
            QuotaType.API_CALLS_PER_MINUTE: (300, QuotaPeriod.MINUTE),
            QuotaType.BACKTESTS_PER_DAY: (50, QuotaPeriod.DAY),
            QuotaType.STRATEGIES_MAX: (20, QuotaPeriod.NONE),
        },
    }

    def __init__(self, db: AsyncSession):
        """Initialize service."""
        self.db = db

    async def _ensure_quota_definitions(self) -> None:
        """Ensure default quota definitions exist in database."""
        for tier, quotas in self.DEFAULT_QUOTAS.items():
            for quota_type, (limit, period) in quotas.items():
                # Check if definition exists
                stmt = select(QuotaDefinition).where(
                    QuotaDefinition.tier == tier.value,
                    QuotaDefinition.quota_type == quota_type.value,
                )
                result = await self.db.execute(stmt)
                existing = result.scalar_one_or_none()

                if not existing:
                    # Create new definition
                    definition = QuotaDefinition(
                        id=str(uuid4()),
                        tier=tier.value,
                        quota_type=quota_type.value,
                        limit=limit,
                        period=period.value,
                    )
                    self.db.add(definition)
                    logger.info(
                        f"Created quota definition: {tier.value}:{quota_type.value} = {limit}/{period.value}"
                    )

        await self.db.commit()

    async def _get_quota_definition(
        self, tier: str, quota_type: str
    ) -> QuotaDefinition | None:
        """Get quota definition for tier and type."""
        stmt = select(QuotaDefinition).where(
            QuotaDefinition.tier == tier,
            QuotaDefinition.quota_type == quota_type,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    def _get_redis_key(
        self, user_id: str, quota_type: str, period_start: datetime
    ) -> str:
        """Generate Redis key for quota counter."""
        period_str = period_start.strftime("%Y%m%d%H%M")
        return f"quota:{user_id}:{quota_type}:{period_str}"

    def _calculate_period_boundaries(
        self, period: str, now: datetime | None = None
    ) -> tuple[datetime, datetime]:
        """Calculate period start and end times."""
        if now is None:
            now = datetime.utcnow()

        if period == QuotaPeriod.MINUTE.value:
            start = now.replace(second=0, microsecond=0)
            end = start + timedelta(minutes=1)
        elif period == QuotaPeriod.HOUR.value:
            start = now.replace(minute=0, second=0, microsecond=0)
            end = start + timedelta(hours=1)
        elif period == QuotaPeriod.DAY.value:
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=1)
        elif period == QuotaPeriod.MONTH.value:
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            # Next month (handle year rollover)
            if now.month == 12:
                end = start.replace(year=now.year + 1, month=1)
            else:
                end = start.replace(month=now.month + 1)
        else:  # NONE - lifetime limit
            start = datetime(2000, 1, 1)  # Arbitrary past date
            end = datetime(2099, 12, 31)  # Far future

        return start, end

    def _calculate_ttl(self, period: str, period_end: datetime) -> int:
        """Calculate Redis TTL in seconds until period end."""
        now = datetime.utcnow()
        seconds = int((period_end - now).total_seconds())
        return max(1, seconds)  # At least 1 second

    async def check_and_consume(
        self,
        user_id: str,
        tier: str,
        quota_type: str,
        amount: int = 1,
    ) -> dict[str, Any]:
        """Check quota and consume if available.

        Args:
            user_id: User ID
            tier: Subscription tier (free, premium, pro)
            quota_type: Type of quota (signals_per_day, etc.)
            amount: Amount to consume (default 1)

        Returns:
            Dict with usage info: {
                "allowed": bool,
                "current": int,
                "limit": int,
                "remaining": int,
                "reset_at": datetime
            }

        Raises:
            QuotaExceededException: If quota would be exceeded
        """
        # Ensure quota definitions exist
        await self._ensure_quota_definitions()

        # Get quota definition
        definition = await self._get_quota_definition(tier, quota_type)
        if not definition:
            logger.warning(
                f"No quota definition found for {tier}:{quota_type}, allowing by default"
            )
            return {
                "allowed": True,
                "current": 0,
                "limit": 999999,
                "remaining": 999999,
                "reset_at": datetime.utcnow() + timedelta(days=365),
            }

        # Calculate period boundaries
        now = datetime.utcnow()
        period_start, period_end = self._calculate_period_boundaries(
            definition.period, now
        )

        # Get Redis client
        redis_client = await get_redis()

        # Generate Redis key
        redis_key = self._get_redis_key(user_id, quota_type, period_start)

        try:
            # Get current count from Redis
            current_str = await redis_client.get(redis_key)
            current = int(current_str) if current_str else 0

            # Check if quota would be exceeded
            new_count = current + amount
            if new_count > definition.limit:
                # Increment block metric
                metrics.quota_block_total.labels(key=quota_type).inc()

                logger.warning(
                    f"Quota exceeded for user {user_id}: {quota_type} {new_count}/{definition.limit}"
                )

                raise QuotaExceededException(
                    quota_type=quota_type,
                    limit=definition.limit,
                    current=current,
                    reset_at=period_end,
                )

            # Consume quota (increment Redis counter)
            await redis_client.incrby(redis_key, amount)

            # Set TTL if this is first usage in period
            if current == 0:
                ttl_seconds = self._calculate_ttl(definition.period, period_end)
                await redis_client.expire(redis_key, ttl_seconds)

            # Update database usage record (async, for audit trail)
            await self._update_usage_record(
                user_id, quota_type, new_count, period_start, period_end
            )

            logger.info(
                f"Quota consumed for user {user_id}: {quota_type} {new_count}/{definition.limit}"
            )

            return {
                "allowed": True,
                "current": new_count,
                "limit": definition.limit,
                "remaining": definition.limit - new_count,
                "reset_at": period_end,
            }

        except QuotaExceededException:
            # Re-raise quota exceptions
            raise
        except Exception as e:
            logger.error(f"Error checking quota: {e}", exc_info=True)
            # On error, allow by default (fail open)
            return {
                "allowed": True,
                "current": 0,
                "limit": definition.limit,
                "remaining": definition.limit,
                "reset_at": period_end,
            }

    async def _update_usage_record(
        self,
        user_id: str,
        quota_type: str,
        count: int,
        period_start: datetime,
        period_end: datetime,
    ) -> None:
        """Update usage record in database (audit trail)."""
        try:
            # Find existing record
            stmt = select(QuotaUsage).where(
                QuotaUsage.user_id == user_id,
                QuotaUsage.quota_type == quota_type,
                QuotaUsage.period_start == period_start,
            )
            result = await self.db.execute(stmt)
            usage = result.scalar_one_or_none()

            if usage:
                # Update existing
                usage.count = count
                usage.updated_at = datetime.utcnow()
            else:
                # Create new
                usage = QuotaUsage(
                    id=str(uuid4()),
                    user_id=user_id,
                    quota_type=quota_type,
                    count=count,
                    period_start=period_start,
                    period_end=period_end,
                )
                self.db.add(usage)

            await self.db.commit()
        except Exception as e:
            logger.error(f"Error updating usage record: {e}", exc_info=True)
            # Don't fail the request if audit logging fails
            await self.db.rollback()

    async def get_quota_status(
        self, user_id: str, tier: str, quota_type: str
    ) -> dict[str, Any]:
        """Get current quota status without consuming.

        Args:
            user_id: User ID
            tier: Subscription tier
            quota_type: Type of quota

        Returns:
            Dict with usage info (same format as check_and_consume)
        """
        # Ensure quota definitions exist
        await self._ensure_quota_definitions()

        # Get quota definition
        definition = await self._get_quota_definition(tier, quota_type)
        if not definition:
            return {
                "current": 0,
                "limit": 999999,
                "remaining": 999999,
                "reset_at": datetime.utcnow() + timedelta(days=365),
            }

        # Calculate period boundaries
        now = datetime.utcnow()
        period_start, period_end = self._calculate_period_boundaries(
            definition.period, now
        )

        # Get Redis client
        redis_client = await get_redis()

        # Generate Redis key
        redis_key = self._get_redis_key(user_id, quota_type, period_start)

        try:
            # Get current count from Redis
            current_str = await redis_client.get(redis_key)
            current = int(current_str) if current_str else 0

            return {
                "current": current,
                "limit": definition.limit,
                "remaining": max(0, definition.limit - current),
                "reset_at": period_end,
            }
        except Exception as e:
            logger.error(f"Error getting quota status: {e}", exc_info=True)
            return {
                "current": 0,
                "limit": definition.limit,
                "remaining": definition.limit,
                "reset_at": period_end,
            }

    async def get_all_quotas(
        self, user_id: str, tier: str
    ) -> dict[str, dict[str, Any]]:
        """Get status for all quotas for a user.

        Args:
            user_id: User ID
            tier: Subscription tier

        Returns:
            Dict mapping quota_type to status dict
        """
        result = {}
        for quota_type in QuotaType:
            status = await self.get_quota_status(user_id, tier, quota_type.value)
            result[quota_type.value] = status

        return result

    async def reset_quota(self, user_id: str, quota_type: str) -> None:
        """Reset quota counter for a user (admin operation).

        Args:
            user_id: User ID
            quota_type: Type of quota to reset
        """
        # Get quota definition to determine period
        definition = await self._get_quota_definition("free", quota_type)
        if not definition:
            logger.warning(f"Cannot reset quota - no definition for {quota_type}")
            return

        # Calculate current period
        now = datetime.utcnow()
        period_start, _ = self._calculate_period_boundaries(definition.period, now)

        # Get Redis client
        redis_client = await get_redis()

        # Generate Redis key
        redis_key = self._get_redis_key(user_id, quota_type, period_start)

        try:
            # Delete Redis key
            await redis_client.delete(redis_key)

            logger.info(f"Reset quota for user {user_id}: {quota_type}")
        except Exception as e:
            logger.error(f"Error resetting quota: {e}", exc_info=True)
