"""
PR-056: Revenue Service

Implements business logic for:
- MRR (Monthly Recurring Revenue) calculation
- ARR (Annual Recurring Revenue) calculation
- Churn rate analysis
- ARPU (Average Revenue Per User) computation
- Cohort retention analysis
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.billing.models import Plan, Subscription
from backend.app.revenue.models import RevenueSnapshot, SubscriptionCohort

logger = logging.getLogger(__name__)


class RevenueService:
    """Service for revenue calculations and reporting."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def calculate_mrr(self, as_of: Optional[date] = None) -> float:
        """Calculate Monthly Recurring Revenue.

        MRR = sum of all active subscription prices per month

        Args:
            as_of: Calculate as of specific date (default: today)

        Returns:
            MRR in GBP
        """
        if not as_of:
            as_of = date.today()

        try:
            # Query active subscriptions as of date
            stmt = select(func.sum(Subscription.price_gbp)).where(
                Subscription.started_at <= datetime.combine(as_of, datetime.min.time()),
                (Subscription.ended_at.is_(None))
                | (
                    Subscription.ended_at > datetime.combine(as_of, datetime.min.time())
                ),
                Subscription.status == "active",
            )

            result = await self.db.execute(stmt)
            mrr = result.scalar() or 0.0

            logger.info(f"Calculated MRR as of {as_of}: £{mrr:.2f}")
            return float(mrr)

        except Exception as e:
            logger.error(f"Error calculating MRR: {e}", exc_info=True)
            return 0.0

    async def calculate_arr(self, as_of: Optional[date] = None) -> float:
        """Calculate Annual Recurring Revenue.

        ARR = MRR * 12

        Args:
            as_of: Calculate as of specific date (default: today)

        Returns:
            ARR in GBP
        """
        mrr = await self.calculate_mrr(as_of)
        arr = mrr * 12
        logger.info(f"Calculated ARR: £{arr:.2f}")
        return arr

    async def calculate_churn_rate(self, month: Optional[str] = None) -> float:
        """Calculate monthly churn rate.

        Churn Rate = (Churned Users / Starting Active Users) * 100

        Args:
            month: Calculate for specific month (YYYY-MM format, default: current month)

        Returns:
            Churn rate as percentage (0-100)
        """
        if not month:
            today = date.today()
            month = today.strftime("%Y-%m")

        try:
            # Parse month
            year, month_num = month.split("-")
            month_start = date(int(year), int(month_num), 1)
            if int(month_num) == 12:
                month_end = date(int(year) + 1, 1, 1) - timedelta(days=1)
            else:
                month_end = date(int(year), int(month_num) + 1, 1) - timedelta(days=1)

            # Count subscriptions active at start of month
            stmt_starting = (
                select(func.count())
                .select_from(Subscription)
                .where(
                    Subscription.started_at
                    <= datetime.combine(month_start, datetime.min.time()),
                    (Subscription.ended_at.is_(None))
                    | (
                        Subscription.ended_at
                        > datetime.combine(month_start, datetime.min.time())
                    ),
                )
            )
            result_starting = await self.db.execute(stmt_starting)
            starting_count = result_starting.scalar() or 1

            # Count churned subscriptions during month
            stmt_churned = (
                select(func.count())
                .select_from(Subscription)
                .where(
                    Subscription.ended_at
                    >= datetime.combine(month_start, datetime.min.time()),
                    Subscription.ended_at
                    <= datetime.combine(month_end, datetime.max.time()),
                )
            )
            result_churned = await self.db.execute(stmt_churned)
            churned_count = result_churned.scalar() or 0

            churn_rate = (
                (churned_count / starting_count * 100) if starting_count > 0 else 0.0
            )

            logger.info(f"Calculated churn rate for {month}: {churn_rate:.2f}%")
            return churn_rate

        except Exception as e:
            logger.error(f"Error calculating churn rate: {e}", exc_info=True)
            return 0.0

    async def calculate_arpu(self, as_of: Optional[date] = None) -> float:
        """Calculate Average Revenue Per User.

        ARPU = MRR / Active Subscribers

        Args:
            as_of: Calculate as of specific date (default: today)

        Returns:
            ARPU in GBP
        """
        if not as_of:
            as_of = date.today()

        try:
            mrr = await self.calculate_mrr(as_of)

            # Count active subscriptions
            stmt = select(func.count(Subscription.id)).where(
                Subscription.started_at <= datetime.combine(as_of, datetime.min.time()),
                (Subscription.ended_at.is_(None))
                | (
                    Subscription.ended_at > datetime.combine(as_of, datetime.min.time())
                ),
                Subscription.status == "active",
            )

            result = await self.db.execute(stmt)
            active_count = result.scalar() or 1

            arpu = mrr / active_count if active_count > 0 else 0.0

            logger.info(f"Calculated ARPU as of {as_of}: £{arpu:.2f}")
            return arpu

        except Exception as e:
            logger.error(f"Error calculating ARPU: {e}", exc_info=True)
            return 0.0

    async def get_cohort_analysis(self, months_back: int = 12) -> list[dict]:
        """Get cohort retention analysis.

        Returns:
            List of cohort data including retention rates and metrics
        """
        try:
            # Query all cohorts from past N months
            today = date.today()
            start_date = date(
                today.year - (today.month - months_back - 1) // 12,
                (today.month - months_back - 1) % 12 + 1,
                1,
            )

            stmt = (
                select(SubscriptionCohort)
                .where(
                    SubscriptionCohort.cohort_month >= start_date.strftime("%Y-%m"),
                )
                .order_by(SubscriptionCohort.cohort_month.desc())
            )

            result = await self.db.execute(stmt)
            cohorts = result.scalars().all()

            cohort_data = [
                {
                    "cohort_month": cohort.cohort_month,
                    "initial_subscribers": cohort.initial_subscribers,
                    "retention_data": cohort.retention_data or {},
                    "churn_rates": cohort.churn_rate_by_month or {},
                    "total_revenue_gbp": cohort.total_revenue_gbp,
                    "average_lifetime_value_gbp": cohort.average_lifetime_value_gbp,
                }
                for cohort in cohorts
            ]

            logger.info(f"Retrieved cohort analysis for {len(cohort_data)} cohorts")
            return cohort_data

        except Exception as e:
            logger.error(f"Error getting cohort analysis: {e}", exc_info=True)
            return []

    async def create_daily_snapshot(self) -> RevenueSnapshot:
        """Create daily revenue snapshot.

        Aggregates all revenue metrics and stores as snapshot for trend analysis.

        Returns:
            Created RevenueSnapshot object
        """
        try:
            today = date.today()
            as_of = today

            # Check if snapshot already exists
            stmt = select(RevenueSnapshot).where(RevenueSnapshot.snapshot_date == today)
            result = await self.db.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing:
                logger.info(f"Snapshot already exists for {today}")
                return existing

            # Calculate metrics
            mrr = await self.calculate_mrr(as_of)
            arr = await self.calculate_arr(as_of)
            churn_rate = await self.calculate_churn_rate()
            arpu = await self.calculate_arpu(as_of)

            # Count subscribers
            stmt_count = select(func.count(Subscription.id)).where(
                Subscription.started_at <= datetime.combine(as_of, datetime.min.time()),
                (Subscription.ended_at.is_(None))
                | (
                    Subscription.ended_at > datetime.combine(as_of, datetime.min.time())
                ),
                Subscription.status == "active",
            )
            result_count = await self.db.execute(stmt_count)
            active_subscribers = result_count.scalar() or 0

            # Count by plan type
            stmt_annual = (
                select(func.count())
                .select_from(Subscription)
                .where(
                    Subscription.plan_id.in_(
                        select(Plan.id).where(Plan.billing_period == "annual")
                    ),
                    Subscription.started_at
                    <= datetime.combine(as_of, datetime.min.time()),
                    (Subscription.ended_at.is_(None))
                    | (
                        Subscription.ended_at
                        > datetime.combine(as_of, datetime.min.time())
                    ),
                )
            )
            result_annual = await self.db.execute(stmt_annual)
            annual_plan_count = result_annual.scalar() or 0

            stmt_monthly = (
                select(func.count())
                .select_from(Subscription)
                .where(
                    Subscription.plan_id.in_(
                        select(Plan.id).where(Plan.billing_period == "monthly")
                    ),
                    Subscription.started_at
                    <= datetime.combine(as_of, datetime.min.time()),
                    (Subscription.ended_at.is_(None))
                    | (
                        Subscription.ended_at
                        > datetime.combine(as_of, datetime.min.time())
                    ),
                )
            )
            result_monthly = await self.db.execute(stmt_monthly)
            monthly_plan_count = result_monthly.scalar() or 0

            # Create snapshot
            snapshot = RevenueSnapshot(
                snapshot_date=today,
                mrr_gbp=mrr,
                arr_gbp=arr,
                active_subscribers=active_subscribers,
                annual_plan_subscribers=annual_plan_count,
                monthly_plan_subscribers=monthly_plan_count,
                churned_this_month=0,  # Would be calculated separately
                churn_rate_percent=churn_rate,
                arpu_gbp=arpu,
            )

            self.db.add(snapshot)
            await self.db.commit()
            await self.db.refresh(snapshot)

            logger.info(
                f"Created revenue snapshot for {today}: MRR £{mrr:.2f}, ARR £{arr:.2f}"
            )
            return snapshot

        except Exception as e:
            logger.error(f"Error creating daily snapshot: {e}", exc_info=True)
            raise
