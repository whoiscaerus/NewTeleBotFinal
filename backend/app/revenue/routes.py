"""
PR-056: Revenue Routes

API endpoints for revenue reporting:
- GET /revenue/summary: MRR, ARR, churn, ARPU
- GET /revenue/cohorts: Cohort retention analysis
- GET /revenue/snapshots: Historical revenue data
"""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.dependencies import get_current_user
from backend.app.core.db import get_db
from backend.app.core.observability import logger
from backend.app.revenue.models import RevenueSnapshot
from backend.app.revenue.service import RevenueService
from backend.app.users.models import User

router = APIRouter(prefix="/api/v1/revenue", tags=["revenue"])


# ============================================================================
# Response Schemas
# ============================================================================


class RevenueSummaryResponse(BaseModel):
    """Revenue summary for owner dashboard."""

    date: date
    mrr_gbp: float = Field(..., description="Monthly Recurring Revenue")
    arr_gbp: float = Field(..., description="Annual Recurring Revenue")
    active_subscribers: int = Field(..., description="Total active subscriptions")
    annual_plan_subscribers: int = Field(..., description="Annual plan count")
    monthly_plan_subscribers: int = Field(..., description="Monthly plan count")
    churn_rate_percent: float = Field(..., description="Monthly churn rate %")
    arpu_gbp: float = Field(..., description="Average Revenue Per User")


class CohortMetricsResponse(BaseModel):
    """Cohort metrics for retention analysis."""

    cohort_month: str = Field(..., description="Month in YYYY-MM format")
    initial_subscribers: int = Field(..., description="Users who subscribed that month")
    retention_data: dict = Field(
        ..., description="Monthly retention counts {month_offset: count}"
    )
    churn_rates: dict = Field(..., description="Churn rates by month {month_offset: %}")
    total_revenue_gbp: float = Field(..., description="All-time revenue from cohort")
    average_lifetime_value_gbp: float = Field(..., description="Average LTV per user")


class RevenueSnapshotResponse(BaseModel):
    """Historical revenue snapshot."""

    snapshot_date: date
    mrr_gbp: float
    arr_gbp: float
    active_subscribers: int
    churn_rate_percent: float
    arpu_gbp: float


# ============================================================================
# Endpoints
# ============================================================================


@router.get(
    "/summary", response_model=RevenueSummaryResponse, summary="Get revenue summary"
)
async def get_revenue_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current revenue summary (MRR, ARR, churn, ARPU).

    Requires: Owner/admin role

    Returns:
    - Current revenue metrics and subscriber counts

    Raises:
    - 403: User is not owner/admin
    - 500: Calculation error
    """
    try:
        # Verify owner/admin
        if not (current_user.is_admin or current_user.is_owner):
            logger.warning(f"Unauthorized revenue access by {current_user.id}")
            raise HTTPException(status_code=403, detail="Insufficient permissions")

        service = RevenueService(db)

        # Calculate metrics
        mrr = await service.calculate_mrr()
        arr = await service.calculate_arr()
        churn = await service.calculate_churn_rate()
        arpu = await service.calculate_arpu()

        # Get latest snapshot for subscriber counts
        from sqlalchemy import select

        stmt = (
            select(RevenueSnapshot)
            .order_by(RevenueSnapshot.snapshot_date.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        latest_snapshot = result.scalar_one_or_none()

        return RevenueSummaryResponse(
            date=date.today(),
            mrr_gbp=mrr,
            arr_gbp=arr,
            active_subscribers=(
                latest_snapshot.active_subscribers if latest_snapshot else 0
            ),
            annual_plan_subscribers=(
                latest_snapshot.annual_plan_subscribers if latest_snapshot else 0
            ),
            monthly_plan_subscribers=(
                latest_snapshot.monthly_plan_subscribers if latest_snapshot else 0
            ),
            churn_rate_percent=churn,
            arpu_gbp=arpu,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting revenue summary: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="Failed to calculate revenue summary"
        )


@router.get(
    "/cohorts",
    response_model=list[CohortMetricsResponse],
    summary="Get cohort analysis",
)
async def get_cohort_analysis(
    months_back: int = Query(
        12, description="Number of months to analyze (default 12)"
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get cohort retention and revenue analysis.

    Shows retention rates and ARPU for each monthly cohort of subscribers.
    Useful for understanding user lifetime value trends.

    Requires: Owner/admin role

    Query Parameters:
    - months_back: Analyze past N months (default 12)

    Returns:
    - List of cohort metrics including retention rates

    Raises:
    - 403: User is not owner/admin
    - 500: Analysis error
    """
    try:
        # Verify owner/admin
        if not (current_user.is_admin or current_user.is_owner):
            logger.warning(f"Unauthorized cohort analysis by {current_user.id}")
            raise HTTPException(status_code=403, detail="Insufficient permissions")

        if months_back < 1 or months_back > 60:
            raise HTTPException(status_code=400, detail="months_back must be 1-60")

        service = RevenueService(db)
        cohorts = await service.get_cohort_analysis(months_back)

        logger.info(
            f"Retrieved cohort analysis: {len(cohorts)} cohorts, {months_back} months"
        )

        return [
            CohortMetricsResponse(
                cohort_month=c["cohort_month"],
                initial_subscribers=c["initial_subscribers"],
                retention_data=c["retention_data"],
                churn_rates=c["churn_rates"],
                total_revenue_gbp=c["total_revenue_gbp"],
                average_lifetime_value_gbp=c["average_lifetime_value_gbp"],
            )
            for c in cohorts
        ]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting cohort analysis: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get cohort analysis")


@router.get(
    "/snapshots",
    response_model=list[RevenueSnapshotResponse],
    summary="Get revenue history",
)
async def get_revenue_snapshots(
    days_back: int = Query(90, description="Days of history (default 90)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get historical revenue snapshots.

    Returns daily snapshots of MRR, ARR, churn, and ARPU for trend analysis.

    Requires: Owner/admin role

    Query Parameters:
    - days_back: Number of days to retrieve (default 90, max 365)

    Returns:
    - List of daily revenue snapshots in chronological order

    Raises:
    - 403: User is not owner/admin
    - 400: Invalid days_back
    - 500: Query error
    """
    try:
        # Verify owner/admin
        if not (current_user.is_admin or current_user.is_owner):
            logger.warning(f"Unauthorized snapshots access by {current_user.id}")
            raise HTTPException(status_code=403, detail="Insufficient permissions")

        if days_back < 1 or days_back > 365:
            raise HTTPException(status_code=400, detail="days_back must be 1-365")

        # Query snapshots
        from sqlalchemy import select

        start_date = date.today() - timedelta(days=days_back)

        stmt = (
            select(RevenueSnapshot)
            .where(RevenueSnapshot.snapshot_date >= start_date)
            .order_by(RevenueSnapshot.snapshot_date.asc())
        )

        result = await db.execute(stmt)
        snapshots = result.scalars().all()

        logger.info(f"Retrieved {len(snapshots)} revenue snapshots")

        return [
            RevenueSnapshotResponse(
                snapshot_date=s.snapshot_date,
                mrr_gbp=s.mrr_gbp,
                arr_gbp=s.arr_gbp,
                active_subscribers=s.active_subscribers,
                churn_rate_percent=s.churn_rate_percent,
                arpu_gbp=s.arpu_gbp,
            )
            for s in snapshots
        ]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting snapshots: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve snapshots")
