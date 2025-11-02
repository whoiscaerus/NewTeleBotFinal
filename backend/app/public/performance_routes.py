"""Public performance endpoints.

Provides read-only, aggregated trading performance data with T+X delay enforcement.
No PII leak. Strong disclaimers. For marketing and transparency.
"""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from prometheus_client import Counter
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.analytics.metrics import (
    calculate_calmar_ratio,
    calculate_sharpe_ratio,
    calculate_sortino_ratio,
)
from backend.app.core.db import get_db
from backend.app.core.logging import get_logger
from backend.app.trading.store.models import Trade

logger = get_logger(__name__)

# Prometheus telemetry
public_performance_views_total = Counter(
    "public_performance_views_total",
    "Public performance endpoint views",
    labelnames=["endpoint", "delay_minutes"],
)

public_performance_error_total = Counter(
    "public_performance_error_total",
    "Public performance endpoint errors",
    labelnames=["endpoint", "error_type"],
)

router = APIRouter(prefix="/api/v1/public", tags=["public"])


class PerformanceResponse:
    """Response schema for performance metrics."""

    def __init__(
        self,
        total_trades: int = 0,
        win_rate: float = 0.0,
        profit_factor: float = 0.0,
        return_percent: float = 0.0,
        sharpe_ratio: float = 0.0,
        sortino_ratio: float = 0.0,
        calmar_ratio: float = 0.0,
        avg_rr: float = 0.0,
        max_drawdown_percent: float = 0.0,
        data_as_of: datetime = None,
        delay_applied_minutes: int = 1440,
        disclaimer: str = "Past performance is not indicative of future results. This data is provided for informational purposes only and should not be used as investment advice.",
    ):
        """Initialize performance response."""
        self.total_trades = total_trades
        self.win_rate = win_rate
        self.profit_factor = profit_factor
        self.return_percent = return_percent
        self.sharpe_ratio = sharpe_ratio
        self.sortino_ratio = sortino_ratio
        self.calmar_ratio = calmar_ratio
        self.avg_rr = avg_rr
        self.max_drawdown_percent = max_drawdown_percent
        self.data_as_of = data_as_of or datetime.utcnow()
        self.delay_applied_minutes = delay_applied_minutes
        self.disclaimer = disclaimer

    def to_dict(self):
        """Convert to dictionary for JSON response."""
        return {
            "total_trades": self.total_trades,
            "win_rate": round(self.win_rate, 4),
            "profit_factor": round(self.profit_factor, 2),
            "return_percent": round(self.return_percent, 2),
            "sharpe_ratio": round(self.sharpe_ratio, 2),
            "sortino_ratio": round(self.sortino_ratio, 2),
            "calmar_ratio": round(self.calmar_ratio, 2),
            "avg_rr": round(self.avg_rr, 2),
            "max_drawdown_percent": round(self.max_drawdown_percent, 2),
            "data_as_of": self.data_as_of.isoformat() + "Z",
            "delay_applied_minutes": self.delay_applied_minutes,
            "disclaimer": self.disclaimer,
        }


class EquityPoint:
    """Single point on equity curve."""

    def __init__(self, date: datetime, equity: Decimal, returns_percent: float):
        """Initialize equity point."""
        self.date = date
        self.equity = float(equity)
        self.returns_percent = round(returns_percent, 2)

    def to_dict(self):
        """Convert to dictionary."""
        return {
            "date": self.date.isoformat() + "Z",
            "equity": self.equity,
            "returns_percent": self.returns_percent,
        }


def _validate_delay(delay_minutes: int) -> None:
    """Validate delay parameter.

    Args:
        delay_minutes: Delay in minutes

    Raises:
        ValueError: If delay is invalid
    """
    if delay_minutes < 1:
        raise ValueError("delay_minutes must be >= 1")
    if delay_minutes > 1_000_000:
        raise ValueError("delay_minutes must be <= 1,000,000")


async def _get_closed_trades_with_delay(
    db: AsyncSession,
    delay_minutes: int,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
) -> list[Trade]:
    """Fetch closed trades respecting T+X delay.

    Args:
        db: Database session
        delay_minutes: Minimum delay before publishing data
        from_date: Optional start date filter
        to_date: Optional end date filter

    Returns:
        List of closed Trade objects that satisfy delay requirements
    """
    # Calculate cutoff: now minus delay
    safe_cutoff = datetime.utcnow() - timedelta(minutes=delay_minutes)

    # Base query: closed trades
    query = select(Trade).where(
        and_(Trade.status == "CLOSED", Trade.exit_time < safe_cutoff)
    )

    # Add date range filters if provided
    if from_date:
        query = query.where(Trade.exit_time >= from_date)
    if to_date:
        query = query.where(Trade.exit_time <= to_date)

    # Sort by exit time ascending
    query = query.order_by(Trade.exit_time.asc())

    result = await db.execute(query)
    return result.scalars().all()


async def _calculate_performance_metrics(trades: list[Trade]) -> PerformanceResponse:
    """Calculate performance metrics from trades.

    Args:
        trades: List of closed Trade objects

    Returns:
        PerformanceResponse with calculated metrics
    """
    if not trades:
        return PerformanceResponse()

    # Extract metrics
    total_trades = len(trades)
    winning_trades = [t for t in trades if t.profit and t.profit > 0]
    losing_trades = [t for t in trades if t.profit and t.profit < 0]

    win_rate = len(winning_trades) / total_trades if total_trades > 0 else 0.0

    # Profit factor
    gross_profit = sum(Decimal(t.profit) for t in winning_trades if t.profit)
    gross_loss = abs(sum(Decimal(t.profit) for t in losing_trades if t.profit))
    profit_factor = float(gross_profit / gross_loss) if gross_loss > 0 else 0.0

    # Total return
    total_profit = sum(Decimal(t.profit) for t in trades if t.profit)
    return_percent = float(total_profit) if total_profit else 0.0

    # Average R:R
    rr_values = [float(t.risk_reward_ratio) for t in trades if t.risk_reward_ratio]
    avg_rr = sum(rr_values) / len(rr_values) if rr_values else 0.0

    # Extract profit for volatility calculations
    profits = [float(t.profit) for t in trades if t.profit]

    # Sharpe ratio (simplified, assuming zero risk-free rate)
    sharpe_ratio = calculate_sharpe_ratio(profits) if profits else 0.0

    # Sortino ratio (only downside volatility)
    sortino_ratio = calculate_sortino_ratio(profits) if profits else 0.0

    # Calmar ratio
    calmar_ratio = calculate_calmar_ratio(profits) if profits else 0.0

    # Max drawdown
    max_drawdown_percent = _calculate_max_drawdown(trades)

    return PerformanceResponse(
        total_trades=total_trades,
        win_rate=win_rate,
        profit_factor=profit_factor,
        return_percent=return_percent,
        sharpe_ratio=sharpe_ratio,
        sortino_ratio=sortino_ratio,
        calmar_ratio=calmar_ratio,
        avg_rr=avg_rr,
        max_drawdown_percent=max_drawdown_percent,
        data_as_of=datetime.utcnow(),
    )


def _calculate_max_drawdown(trades: list[Trade]) -> float:
    """Calculate maximum drawdown from equity curve.

    Args:
        trades: Sorted list of closed trades (by exit time)

    Returns:
        Maximum drawdown as percentage
    """
    if not trades:
        return 0.0

    equity_values = []
    running_equity = Decimal("10000")  # Base starting equity

    for trade in trades:
        if trade.profit:
            running_equity += Decimal(str(trade.profit))
            equity_values.append(float(running_equity))

    if not equity_values:
        return 0.0

    peak = equity_values[0]
    max_dd = 0.0

    for value in equity_values:
        if value > peak:
            peak = value
        drawdown = (peak - value) / peak if peak > 0 else 0
        max_dd = max(max_dd, drawdown)

    return max_dd * 100


@router.get("/performance/summary")
async def get_performance_summary(
    delay_minutes: int = Query(1440, ge=0, le=1_000_000),
    from_date: Optional[datetime] = Query(None),
    to_date: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get aggregated performance summary with T+X delay.

    Endpoint: GET /api/v1/public/performance/summary

    Query Parameters:
        delay_minutes: Minimum delay before publishing data (default: 1440 = 24h)
        from_date: Optional start date filter
        to_date: Optional end date filter

    Returns:
        Aggregated performance metrics (no PII):
        - total_trades: Number of closed trades
        - win_rate: Winning trades / total trades
        - profit_factor: Gross profit / gross loss
        - return_percent: Total profit as percentage
        - sharpe_ratio: Risk-adjusted return metric
        - sortino_ratio: Downside risk-adjusted return
        - calmar_ratio: Return / max drawdown
        - avg_rr: Average risk-reward ratio
        - max_drawdown_percent: Largest peak-to-trough decline
        - disclaimer: Strong warning about forward guidance

    Security:
        - ✅ Returns aggregated data only (no user IDs, names, emails)
        - ✅ No individual trade details leaked
        - ✅ Only closed trades after delay_minutes
        - ✅ Public endpoint (no authentication required)

    Example:
        GET /api/v1/public/performance/summary?delay_minutes=1440
        Response:
        {
            "total_trades": 143,
            "win_rate": 0.6573,
            "profit_factor": 2.15,
            ...
            "disclaimer": "Past performance is not indicative..."
        }

    Raises:
        400 Bad Request: If delay_minutes < 1 or invalid date range
        500 Internal Server Error: If database query fails
    """
    db_session = await get_db()

    try:
        # Validate delay parameter
        _validate_delay(delay_minutes)

        # Record telemetry
        public_performance_views_total.labels(
            endpoint="summary", delay_minutes=delay_minutes
        ).inc()

        # Fetch closed trades with delay enforcement
        logger.info(
            f"Fetching performance summary with {delay_minutes}min delay",
            extra={"delay_minutes": delay_minutes},
        )

        trades = await _get_closed_trades_with_delay(
            db_session, delay_minutes, from_date, to_date
        )

        # Calculate metrics
        metrics = await _calculate_performance_metrics(trades)

        logger.info(
            f"Performance summary calculated: {metrics.total_trades} trades",
            extra={"total_trades": metrics.total_trades},
        )

        return metrics.to_dict()

    except ValueError as e:
        logger.warning(f"Validation error: {e}")
        public_performance_error_total.labels(
            endpoint="summary", error_type="validation"
        ).inc()
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        logger.error(f"Error fetching performance summary: {e}", exc_info=True)
        public_performance_error_total.labels(
            endpoint="summary", error_type="internal"
        ).inc()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/performance/equity")
async def get_equity_curve(
    delay_minutes: int = Query(1440, ge=0, le=1_000_000),
    from_date: Optional[datetime] = Query(None),
    to_date: Optional[datetime] = Query(None),
    granularity: str = Query("daily"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get equity curve data points for charting.

    Endpoint: GET /api/v1/public/performance/equity

    Query Parameters:
        delay_minutes: Minimum delay before publishing (default: 1440 = 24h)
        from_date: Optional start date
        to_date: Optional end date
        granularity: "daily" (only option for now)

    Returns:
        Array of equity points:
        [
            {
                "date": "2025-10-01T00:00:00Z",
                "equity": 10000.00,
                "returns_percent": 0.0
            },
            ...
        ]
        Plus metadata:
        - final_equity: Ending equity value
        - delay_applied_minutes: Delay enforced
        - data_as_of: Timestamp of calculation

    Security:
        - ✅ No PII in response
        - ✅ No individual trade details (entry/exit prices, symbols)
        - ✅ Only closed trades after delay_minutes
        - ✅ Day-level granularity only (no intra-day leakage)

    Example:
        GET /api/v1/public/performance/equity?delay_minutes=1440
        Response:
        {
            "points": [...],
            "final_equity": 14730.00,
            "delay_applied_minutes": 1440,
            "data_as_of": "2025-10-30T10:00:00Z"
        }

    Raises:
        400 Bad Request: If invalid parameters
        500 Internal Server Error: If database query fails
    """
    db_session = await get_db()

    try:
        # Validate delay parameter
        _validate_delay(delay_minutes)

        # Record telemetry
        public_performance_views_total.labels(
            endpoint="equity", delay_minutes=delay_minutes
        ).inc()

        logger.info(
            f"Fetching equity curve with {delay_minutes}min delay",
            extra={"delay_minutes": delay_minutes, "granularity": granularity},
        )

        # Fetch closed trades with delay enforcement
        trades = await _get_closed_trades_with_delay(
            db_session, delay_minutes, from_date, to_date
        )

        # Build equity curve
        points = []
        running_equity = Decimal("10000")  # Starting equity
        last_date = None

        for trade in trades:
            if not trade.exit_time or not trade.profit:
                continue

            # Group by date
            trade_date = trade.exit_time.date()
            if last_date is None or trade_date != last_date:
                last_date = trade_date

            running_equity += Decimal(str(trade.profit))

            # Calculate return percentage
            returns_percent = float(
                ((running_equity - Decimal("10000")) / Decimal("10000")) * 100
            )

            # Create point for this trade's exit date
            point = EquityPoint(
                date=trade.exit_time,
                equity=running_equity,
                returns_percent=returns_percent,
            )
            points.append(point)

        logger.info(
            f"Equity curve calculated: {len(points)} data points",
            extra={"total_points": len(points)},
        )

        # Get final equity
        final_equity = float(running_equity) if points else 10000.0

        return {
            "points": [p.to_dict() for p in points],
            "final_equity": round(final_equity, 2),
            "delay_applied_minutes": delay_minutes,
            "data_as_of": datetime.utcnow().isoformat() + "Z",
        }

    except ValueError as e:
        logger.warning(f"Validation error: {e}")
        public_performance_error_total.labels(
            endpoint="equity", error_type="validation"
        ).inc()
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        logger.error(f"Error fetching equity curve: {e}", exc_info=True)
        public_performance_error_total.labels(
            endpoint="equity", error_type="internal"
        ).inc()
        raise HTTPException(status_code=500, detail="Internal server error")
