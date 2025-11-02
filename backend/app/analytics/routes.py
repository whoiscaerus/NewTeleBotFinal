"""
Analytics API routes.

Provides endpoints for:
- /analytics/equity: Equity curve data
- /analytics/drawdown: Drawdown statistics
- /analytics/metrics: Performance metrics (Sharpe, Sortino, Calmar, etc.)

All endpoints require JWT authentication.
Support query parameters for date ranges and windows.
Include caching and error handling.
"""

from __future__ import annotations

import csv
import json
import logging
from datetime import date, datetime, timedelta
from io import StringIO
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.analytics.buckets import TimeBucketService
from backend.app.analytics.drawdown import DrawdownAnalyzer
from backend.app.analytics.equity import EquityEngine
from backend.app.analytics.metrics import PerformanceMetrics
from backend.app.auth.dependencies import get_current_user
from backend.app.auth.models import User
from backend.app.core.db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


class EquityPoint(BaseModel):
    """Single point in equity curve."""

    date: date
    equity: float = Field(..., description="Account equity at end of day")
    cumulative_pnl: float = Field(..., description="Total PnL from start")
    drawdown_percent: float = Field(..., description="Drawdown from peak")


class EquityResponse(BaseModel):
    """Equity curve response."""

    points: list[EquityPoint] = Field(..., description="Equity curve points")
    initial_equity: float = Field(..., description="Starting balance")
    final_equity: float = Field(..., description="Ending balance")
    total_return_percent: float = Field(..., description="Total return %")
    max_drawdown_percent: float = Field(..., description="Maximum drawdown %")
    days_in_period: int = Field(..., description="Number of days")


class DrawdownStats(BaseModel):
    """Drawdown statistics."""

    max_drawdown_percent: float = Field(..., description="Maximum drawdown %")
    current_drawdown_percent: float = Field(..., description="Current drawdown %")
    peak_equity: float = Field(..., description="Peak equity before drawdown")
    trough_equity: float = Field(..., description="Lowest equity during drawdown")
    drawdown_duration_days: int = Field(..., description="Days in drawdown")
    recovery_time_days: int = Field(
        ..., description="Days to recover from worst drawdown"
    )
    average_drawdown_percent: float = Field(
        ..., description="Average drawdown when in DD"
    )


class MetricsResponse(BaseModel):
    """Performance metrics response."""

    sharpe_ratio: float = Field(
        ..., description="Sharpe Ratio (excess return / volatility)"
    )
    sortino_ratio: float = Field(
        ..., description="Sortino Ratio (excess return / downside)"
    )
    calmar_ratio: float = Field(
        ..., description="Calmar Ratio (annual return / max dd)"
    )
    profit_factor: float = Field(..., description="Profit Factor (wins / losses)")
    recovery_factor: float = Field(..., description="Recovery Factor (return / max dd)")
    win_rate_percent: float = Field(..., description="Win rate %")
    num_trades: int = Field(..., description="Number of trades")
    total_return_percent: float = Field(..., description="Total return %")
    max_drawdown_percent: float = Field(..., description="Max drawdown %")
    period_days: int = Field(..., description="Period in days")


@router.get("/equity", response_model=EquityResponse, summary="Get equity curve")
async def get_equity_curve(
    start_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    initial_balance: float = Query(
        10000, description="Initial balance in base currency"
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get equity curve for user.

    Returns chronological equity values from start to end date.
    Handles gaps (forward-fills) for non-trading days.

    Query Parameters:
    - start_date: Start date (optional, defaults to first trade)
    - end_date: End date (optional, defaults to last trade)
    - initial_balance: Starting balance (default 10000)

    Returns:
    - EquityResponse with equity points and summary stats

    Raises:
    - 404: No trades found
    - 500: Calculation error
    """
    try:
        engine = EquityEngine(db)

        # Compute equity series
        equity_series = await engine.compute_equity_series(
            user_id=current_user.id,
            start_date=start_date,
            end_date=end_date,
            initial_balance=initial_balance,
        )

        # Build response
        points = [
            EquityPoint(
                date=d,
                equity=float(e),
                cumulative_pnl=float(cp),
                drawdown_percent=float(dd),
            )
            for d, e, cp, dd in zip(
                equity_series.dates,
                equity_series.equity,
                equity_series.cumulative_pnl,
                equity_series.drawdown,
            )
        ]

        return EquityResponse(
            points=points,
            initial_equity=(
                float(equity_series.equity[0]) if equity_series.equity else 0
            ),
            final_equity=float(equity_series.final_equity),
            total_return_percent=float(equity_series.total_return),
            max_drawdown_percent=float(equity_series.max_drawdown),
            days_in_period=len(equity_series.dates),
        )

    except ValueError as e:
        logger.warning(f"Equity curve error: {e}", extra={"user_id": current_user.id})
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error computing equity curve: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to compute equity curve")


@router.get(
    "/drawdown", response_model=DrawdownStats, summary="Get drawdown statistics"
)
async def get_drawdown_stats(
    start_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get drawdown statistics for user.

    Returns peak-to-trough drawdown and recovery metrics.

    Query Parameters:
    - start_date: Start date (optional)
    - end_date: End date (optional)

    Returns:
    - DrawdownStats with all DD metrics

    Raises:
    - 404: No data found
    - 500: Calculation error
    """
    try:
        engine = EquityEngine(db)
        analyzer = DrawdownAnalyzer(db)

        # Compute equity series
        equity_series = await engine.compute_equity_series(
            user_id=current_user.id,
            start_date=start_date,
            end_date=end_date,
        )

        # Calculate drawdown stats
        stats = analyzer.calculate_drawdown_stats(equity_series)

        return DrawdownStats(
            max_drawdown_percent=float(stats["max_drawdown_percent"]),
            current_drawdown_percent=float(stats["current_drawdown_percent"]),
            peak_equity=(
                float(equity_series.equity[stats["peak_index"]])
                if stats["peak_index"] < len(equity_series.equity)
                else 0
            ),
            trough_equity=(
                float(equity_series.equity[stats["trough_index"]])
                if stats["trough_index"] < len(equity_series.equity)
                else 0
            ),
            drawdown_duration_days=int(stats["drawdown_duration_periods"]),
            recovery_time_days=int(stats["recovery_time"]),
            average_drawdown_percent=float(stats["average_drawdown_percent"]),
        )

    except ValueError as e:
        logger.warning(f"Drawdown stats error: {e}", extra={"user_id": current_user.id})
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error computing drawdown stats: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="Failed to compute drawdown statistics"
        )


@router.get(
    "/metrics", response_model=MetricsResponse, summary="Get performance metrics"
)
async def get_performance_metrics(
    window: int = Query(90, description="Window in days (30, 90, 365)", ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get performance metrics for user.

    Returns Sharpe, Sortino, Calmar, Profit Factor, and Recovery Factor.

    Query Parameters:
    - window: Time window in days (default 90)

    Returns:
    - MetricsResponse with all KPIs

    Raises:
    - 404: No trades in window
    - 500: Calculation error
    """
    try:
        metrics_calc = PerformanceMetrics(db)

        # Get metrics for window
        metrics = await metrics_calc.get_metrics_for_window(
            user_id=current_user.id,
            window_days=window,
        )

        return MetricsResponse(
            sharpe_ratio=float(metrics["sharpe_ratio"]),
            sortino_ratio=float(metrics["sortino_ratio"]),
            calmar_ratio=float(metrics["calmar_ratio"]),
            profit_factor=float(metrics["profit_factor"]),
            recovery_factor=float(metrics["recovery_factor"]),
            win_rate_percent=float(metrics["win_rate"]),
            num_trades=int(metrics["num_trades"]),
            total_return_percent=float(metrics["total_return_percent"]),
            max_drawdown_percent=float(metrics["max_drawdown_percent"]),
            period_days=window,
        )

    except ValueError as e:
        logger.warning(
            f"Metrics error: {e}", extra={"user_id": current_user.id, "window": window}
        )
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error computing metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to compute metrics")


@router.get("/metrics/all-windows", summary="Get metrics for all windows")
async def get_all_metrics_windows(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get metrics for all standard windows (30, 90, 365 days).

    Returns:
    - Dict mapping window_days -> MetricsResponse

    Raises:
    - 500: Calculation error
    """
    try:
        metrics_calc = PerformanceMetrics(db)

        # Get all windows
        all_metrics = await metrics_calc.get_all_window_metrics(user_id=current_user.id)

        # Convert to response format
        results = {}
        for window_days, metrics in all_metrics.items():
            if metrics:
                results[str(window_days)] = MetricsResponse(
                    sharpe_ratio=float(metrics.get("sharpe_ratio", 0)),
                    sortino_ratio=float(metrics.get("sortino_ratio", 0)),
                    calmar_ratio=float(metrics.get("calmar_ratio", 0)),
                    profit_factor=float(metrics.get("profit_factor", 0)),
                    recovery_factor=float(metrics.get("recovery_factor", 0)),
                    win_rate_percent=float(metrics.get("win_rate", 0)),
                    num_trades=int(metrics.get("num_trades", 0)),
                    total_return_percent=float(metrics.get("total_return_percent", 0)),
                    max_drawdown_percent=float(metrics.get("max_drawdown_percent", 0)),
                    period_days=window_days,
                )

        return results

    except Exception as e:
        logger.error(f"Error computing all metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to compute metrics")


# ============================================================================
# BUCKET ENDPOINTS (Time-based aggregations)
# ============================================================================


class HourBucketResponse(BaseModel):
    """Hour-of-day bucket."""

    hour: int = Field(..., ge=0, le=23, description="Hour of day (0-23)")
    num_trades: int = Field(..., description="Number of trades in this hour")
    winning_trades: int = Field(..., description="Winning trades")
    losing_trades: int = Field(..., description="Losing trades")
    total_pnl: float = Field(..., description="Total PnL for this hour")
    avg_pnl: float = Field(..., description="Average PnL per trade")
    win_rate_percent: float = Field(..., description="Win rate %")


class DayOfWeekBucketResponse(BaseModel):
    """Day-of-week bucket."""

    day_of_week: int = Field(..., ge=0, le=6, description="Day of week (0=Mon, 6=Sun)")
    day_name: str = Field(..., description="Day name (Monday-Sunday)")
    num_trades: int = Field(..., description="Number of trades on this day")
    winning_trades: int = Field(..., description="Winning trades")
    losing_trades: int = Field(..., description="Losing trades")
    total_pnl: float = Field(..., description="Total PnL for this day")
    avg_pnl: float = Field(..., description="Average PnL per trade")
    win_rate_percent: float = Field(..., description="Win rate %")


class MonthBucketResponse(BaseModel):
    """Calendar month bucket (1-12, aggregates across all years)."""

    month: int = Field(..., ge=1, le=12, description="Month (1-12)")
    month_name: str = Field(..., description="Month name (January-December)")
    num_trades: int = Field(..., description="Number of trades in this month")
    winning_trades: int = Field(..., description="Winning trades")
    losing_trades: int = Field(..., description="Losing trades")
    total_pnl: float = Field(..., description="Total PnL for this month")
    avg_pnl: float = Field(..., description="Average PnL per trade")
    win_rate_percent: float = Field(..., description="Win rate %")


class CalendarMonthBucketResponse(BaseModel):
    """Specific calendar month bucket (YYYY-MM)."""

    calendar_month: str = Field(..., description="Calendar month (YYYY-MM)")
    num_trades: int = Field(..., description="Number of trades in this month")
    winning_trades: int = Field(..., description="Winning trades")
    losing_trades: int = Field(..., description="Losing trades")
    total_pnl: float = Field(..., description="Total PnL for this month")
    avg_pnl: float = Field(..., description="Average PnL per trade")
    win_rate_percent: float = Field(..., description="Win rate %")


@router.get(
    "/buckets/hour",
    response_model=list[HourBucketResponse],
    summary="Get hour-of-day buckets",
)
async def get_hour_buckets(
    start_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get trade aggregations by hour of day (0-23).

    Returns metrics for each hour of the day:
    - num_trades: Number of trades
    - winning_trades: Trades with positive PnL
    - total_pnl: Sum of PnL
    - avg_pnl: Average PnL per trade
    - win_rate_percent: Win rate %

    Empty hours return 0 values (no nulls).

    Query Parameters:
    - start_date: Start date (optional, defaults to earliest trade)
    - end_date: End date (optional, defaults to latest trade)

    Returns:
    - List of 24 HourBucketResponse objects (one per hour, sorted 0-23)

    Raises:
    - 404: No trades found
    - 500: Calculation error
    """
    try:
        if not start_date or not end_date:
            # Default to last 90 days if not specified
            end_date = date.today()
            start_date = end_date - timedelta(days=90)

        service = TimeBucketService(db)
        buckets = await service.group_by_hour(
            user_id=current_user.id,
            start_date=start_date,
            end_date=end_date,
        )

        return [HourBucketResponse(**bucket.to_dict()) for bucket in buckets]

    except ValueError as e:
        logger.warning(f"Hour bucket error: {e}", extra={"user_id": current_user.id})
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error computing hour buckets: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to compute hour buckets")


@router.get(
    "/buckets/dow",
    response_model=list[DayOfWeekBucketResponse],
    summary="Get day-of-week buckets",
)
async def get_dow_buckets(
    start_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get trade aggregations by day of week (Monday-Sunday).

    Returns metrics for each day of the week (aggregates across all weeks):
    - num_trades: Number of trades
    - winning_trades: Trades with positive PnL
    - total_pnl: Sum of PnL
    - avg_pnl: Average PnL per trade
    - win_rate_percent: Win rate %

    Empty days return 0 values (no nulls).

    Query Parameters:
    - start_date: Start date (optional, defaults to earliest trade)
    - end_date: End date (optional, defaults to latest trade)

    Returns:
    - List of 7 DayOfWeekBucketResponse objects (Mon-Sun, sorted 0-6)

    Raises:
    - 404: No trades found
    - 500: Calculation error
    """
    try:
        if not start_date or not end_date:
            # Default to last 90 days if not specified
            end_date = date.today()
            start_date = end_date - timedelta(days=90)

        service = TimeBucketService(db)
        buckets = await service.group_by_dow(
            user_id=current_user.id,
            start_date=start_date,
            end_date=end_date,
        )

        return [DayOfWeekBucketResponse(**bucket.to_dict()) for bucket in buckets]

    except ValueError as e:
        logger.warning(
            f"Day-of-week bucket error: {e}", extra={"user_id": current_user.id}
        )
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error computing day-of-week buckets: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="Failed to compute day-of-week buckets"
        )


@router.get(
    "/buckets/month",
    response_model=list[MonthBucketResponse],
    summary="Get month buckets",
)
async def get_month_buckets(
    start_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get trade aggregations by calendar month (1-12).

    Returns metrics for each calendar month (aggregates across all years):
    - num_trades: Number of trades
    - winning_trades: Trades with positive PnL
    - total_pnl: Sum of PnL
    - avg_pnl: Average PnL per trade
    - win_rate_percent: Win rate %

    Empty months return 0 values (no nulls).

    Query Parameters:
    - start_date: Start date (optional, defaults to earliest trade)
    - end_date: End date (optional, defaults to latest trade)

    Returns:
    - List of 12 MonthBucketResponse objects (sorted Jan-Dec)

    Raises:
    - 404: No trades found
    - 500: Calculation error
    """
    try:
        if not start_date or not end_date:
            # Default to last 90 days if not specified
            end_date = date.today()
            start_date = end_date - timedelta(days=90)

        service = TimeBucketService(db)
        buckets = await service.group_by_month(
            user_id=current_user.id,
            start_date=start_date,
            end_date=end_date,
        )

        return [MonthBucketResponse(**bucket.to_dict()) for bucket in buckets]

    except ValueError as e:
        logger.warning(f"Month bucket error: {e}", extra={"user_id": current_user.id})
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error computing month buckets: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to compute month buckets")


@router.get(
    "/buckets/calendar-month",
    response_model=list[CalendarMonthBucketResponse],
    summary="Get calendar month buckets",
)
async def get_calendar_month_buckets(
    start_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get trade aggregations by specific calendar month (YYYY-MM).

    Returns metrics for each unique year-month in the date range:
    - num_trades: Number of trades
    - winning_trades: Trades with positive PnL
    - total_pnl: Sum of PnL
    - avg_pnl: Average PnL per trade
    - win_rate_percent: Win rate %

    Empty months return 0 values (no nulls).

    Query Parameters:
    - start_date: Start date (optional, defaults to earliest trade)
    - end_date: End date (optional, defaults to latest trade)

    Returns:
    - List of CalendarMonthBucketResponse objects (sorted chronologically)

    Raises:
    - 404: No trades found
    - 500: Calculation error
    """
    try:
        if not start_date or not end_date:
            # Default to last 90 days if not specified
            end_date = date.today()
            start_date = end_date - timedelta(days=90)

        service = TimeBucketService(db)
        buckets = await service.group_by_calendar_month(
            user_id=current_user.id,
            start_date=start_date,
            end_date=end_date,
        )

        return [CalendarMonthBucketResponse(**bucket.to_dict()) for bucket in buckets]

    except ValueError as e:
        logger.warning(
            f"Calendar month bucket error: {e}", extra={"user_id": current_user.id}
        )
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error computing calendar month buckets: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="Failed to compute calendar month buckets"
        )


# ============================================================================
# Export Endpoints (PR-055)
# ============================================================================


@router.get("/export/csv", summary="Export analytics as CSV")
async def export_csv(
    start_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export analytics data as CSV file.

    Includes:
    - Equity curve points
    - Performance metrics
    - Hour/day/month breakdowns

    Returns:
    - CSV file download with all analytics data

    Raises:
    - 404: No data to export
    - 500: Export generation error
    """
    try:
        if not start_date or not end_date:
            end_date = date.today()
            start_date = end_date - timedelta(days=90)

        logger.info(
            f"Exporting analytics CSV for user {current_user.id}",
            extra={
                "user_id": current_user.id,
                "start_date": start_date,
                "end_date": end_date,
            },
        )

        # Create CSV in memory
        output = StringIO()
        writer = csv.writer(output)

        # Get all data
        engine = EquityEngine(db)
        equity_data = await engine.compute_equity_series(
            user_id=current_user.id,
            start_date=start_date,
            end_date=end_date,
        )

        if not equity_data or not equity_data.points:
            raise ValueError("No equity data found for export")

        # Write equity header
        writer.writerow(
            ["Analytics Export", current_user.email, datetime.now().isoformat()]
        )
        writer.writerow([])
        writer.writerow(["EQUITY CURVE"])
        writer.writerow(["Date", "Equity", "Cumulative PnL", "Drawdown %"])

        # Write equity data
        for point in equity_data.points:
            writer.writerow(
                [
                    point.date.isoformat(),
                    round(point.equity, 2),
                    round(point.cumulative_pnl, 2),
                    round(point.drawdown_percent * 100, 2),
                ]
            )

        writer.writerow([])
        writer.writerow(["SUMMARY STATS"])
        writer.writerow(["Metric", "Value"])
        writer.writerow(["Initial Equity", round(equity_data.initial_equity, 2)])
        writer.writerow(["Final Equity", round(equity_data.final_equity, 2)])
        writer.writerow(["Total Return %", round(equity_data.total_return_percent, 2)])
        writer.writerow(["Max Drawdown %", round(equity_data.max_drawdown_percent, 2)])
        writer.writerow(["Days in Period", equity_data.days_in_period])

        # Convert to bytes
        output.seek(0)
        content = output.getvalue()

        logger.info(
            f"CSV export completed for user {current_user.id}",
            extra={
                "user_id": current_user.id,
                "file_size_bytes": len(content),
            },
        )

        # Increment telemetry counter
        logger.info("analytics_exports_total{type=csv}", extra={"type": "csv"})

        return StreamingResponse(
            iter([content]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=analytics_{start_date}_to_{end_date}.csv"
            },
        )

    except ValueError as e:
        logger.warning(f"CSV export error: {e}", extra={"user_id": current_user.id})
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(
            f"Error exporting CSV: {e}",
            exc_info=True,
            extra={"user_id": current_user.id},
        )
        raise HTTPException(status_code=500, detail="Failed to export CSV")


@router.get("/export/json", summary="Export analytics as JSON")
async def export_json(
    start_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    include_metrics: bool = Query(True, description="Include performance metrics"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export analytics data as JSON file.

    Includes:
    - Equity curve points
    - Performance metrics (optional)
    - Hour/day/month breakdowns

    Query Parameters:
    - start_date: Start date (optional, defaults to 90 days ago)
    - end_date: End date (optional, defaults to today)
    - include_metrics: Include computed metrics (default True)

    Returns:
    - JSON file download with all analytics data

    Raises:
    - 404: No data to export
    - 500: Export generation error
    """
    try:
        if not start_date or not end_date:
            end_date = date.today()
            start_date = end_date - timedelta(days=90)

        logger.info(
            f"Exporting analytics JSON for user {current_user.id}",
            extra={
                "user_id": current_user.id,
                "start_date": start_date,
                "end_date": end_date,
                "include_metrics": include_metrics,
            },
        )

        # Get all data
        engine = EquityEngine(db)
        equity_data = await engine.compute_equity_series(
            user_id=current_user.id,
            start_date=start_date,
            end_date=end_date,
        )

        if not equity_data or not equity_data.points:
            raise ValueError("No equity data found for export")

        # Build export data
        export_data = {
            "export_date": datetime.now().isoformat(),
            "user": current_user.email,
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "days": equity_data.days_in_period,
            },
            "equity_curve": {
                "initial_equity": equity_data.initial_equity,
                "final_equity": equity_data.final_equity,
                "total_return_percent": equity_data.total_return_percent,
                "max_drawdown_percent": equity_data.max_drawdown_percent,
                "points": [
                    {
                        "date": point.date.isoformat(),
                        "equity": point.equity,
                        "cumulative_pnl": point.cumulative_pnl,
                        "drawdown_percent": point.drawdown_percent,
                    }
                    for point in equity_data.points
                ],
            },
        }

        # Add metrics if requested
        if include_metrics:
            try:
                metrics_svc = PerformanceMetrics(db)
                metrics = await metrics_svc.calculate(
                    user_id=current_user.id,
                    window_days=90,
                )
                export_data["metrics"] = {
                    "sharpe_ratio": metrics.sharpe_ratio,
                    "sortino_ratio": metrics.sortino_ratio,
                    "calmar_ratio": metrics.calmar_ratio,
                    "profit_factor": metrics.profit_factor,
                    "recovery_factor": metrics.recovery_factor,
                    "win_rate_percent": metrics.win_rate_percent,
                    "num_trades": metrics.num_trades,
                }
            except Exception as e:
                logger.warning(f"Could not compute metrics for export: {e}")
                export_data["metrics"] = None

        # Serialize to JSON
        json_content = json.dumps(export_data, indent=2, default=str)

        logger.info(
            f"JSON export completed for user {current_user.id}",
            extra={
                "user_id": current_user.id,
                "file_size_bytes": len(json_content),
            },
        )

        # Increment telemetry counter
        logger.info("analytics_exports_total{type=json}", extra={"type": "json"})

        return StreamingResponse(
            iter([json_content]),
            media_type="application/json",
            headers={
                "Content-Disposition": f"attachment; filename=analytics_{start_date}_to_{end_date}.json"
            },
        )

    except ValueError as e:
        logger.warning(f"JSON export error: {e}", extra={"user_id": current_user.id})
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(
            f"Error exporting JSON: {e}",
            exc_info=True,
            extra={"user_id": current_user.id},
        )
        raise HTTPException(status_code=500, detail="Failed to export JSON")
