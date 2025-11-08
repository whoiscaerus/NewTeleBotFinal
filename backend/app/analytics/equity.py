"""
Equity and drawdown calculation engine.

Provides services to compute equity curves and drawdown from warehouse data.
Handles gaps, partial days, and peak tracking robustly.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.analytics.models import TradesFact
from backend.app.core.logging import get_logger

logger = get_logger(__name__)

try:
    from prometheus_client import Histogram

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

if PROMETHEUS_AVAILABLE:
    equity_compute_histogram = Histogram(
        "equity_compute_seconds",
        "Equity computation duration in seconds",
    )


class EquitySeries:
    """Represents an equity curve time series.

    Attributes:
        dates: List of dates
        equity: List of equity values (parallel to dates)
        peak_equity: Peak equity to each point
        cumulative_pnl: Cumulative PnL to each point
    """

    def __init__(
        self,
        dates: list[date],
        equity: list[Decimal],
        peak_equity: list[Decimal],
        cumulative_pnl: list[Decimal],
    ):
        """Initialize equity series.

        Args:
            dates: List of dates (sorted)
            equity: Equity balance at each date
            peak_equity: Peak equity up to each date
            cumulative_pnl: Cumulative PnL at each date
        """
        if not (len(dates) == len(equity) == len(peak_equity) == len(cumulative_pnl)):
            raise ValueError("All lists must have same length")

        self.dates = dates
        self.equity = equity
        self.peak_equity = peak_equity
        self.cumulative_pnl = cumulative_pnl

    @property
    def drawdown(self) -> list[Decimal]:
        """Get drawdown at each point.

        Drawdown = (peak_equity - current_equity) / peak_equity * 100

        Returns:
            List[Decimal]: Drawdown percentage at each point
        """
        return [
            ((p - e) / p * Decimal(100)) if p > 0 else Decimal(0)
            for e, p in zip(self.equity, self.peak_equity, strict=True)
        ]

    @property
    def max_drawdown(self) -> Decimal:
        """Get maximum drawdown over entire series.

        Returns:
            Decimal: Maximum drawdown percentage
        """
        return max(self.drawdown) if self.drawdown else Decimal(0)

    @property
    def points(self) -> list[dict]:
        """Get equity points as list of dictionaries.

        Returns:
            List[dict]: List of point dicts with date, equity, cumulative_pnl, drawdown_percent
        """
        return [
            {
                "date": d,
                "equity": float(e),
                "cumulative_pnl": float(c),
                "drawdown_percent": float(dd),
            }
            for d, e, c, dd in zip(
                self.dates, self.equity, self.cumulative_pnl, self.drawdown, strict=True
            )
        ]

    @property
    def final_equity(self) -> Decimal:
        """Get final equity value.

        Returns:
            Decimal: Last equity value
        """
        return self.equity[-1] if self.equity else Decimal(0)

    @property
    def total_return(self) -> Decimal:
        """Get total return percentage.

        Returns:
            Decimal: Return from first to last equity
        """
        if not self.equity:
            return Decimal(0)
        first = self.equity[0]
        last = self.equity[-1]
        return ((last - first) / first * Decimal(100)) if first > 0 else Decimal(0)

    @property
    def total_return_percent(self) -> float:
        """Get total return percentage as float.

        Returns:
            float: Return percentage
        """
        return float(self.total_return)

    @property
    def initial_equity(self) -> float:
        """Get initial equity value.

        Returns:
            float: First equity value
        """
        return float(self.equity[0]) if self.equity else 0.0

    @property
    def max_drawdown_percent(self) -> float:
        """Get maximum drawdown percentage as float.

        Returns:
            float: Maximum drawdown percentage
        """
        return float(self.max_drawdown)

    @property
    def days_in_period(self) -> int:
        """Get number of trading days in period.

        Returns:
            int: Number of days
        """
        return len(self.dates)

    def __repr__(self):
        return (
            f"<EquitySeries points={len(self.dates)} "
            f"final_equity={self.final_equity} "
            f"max_dd={self.max_drawdown}%>"
        )


class EquityEngine:
    """Service for computing equity curves and drawdown.

    Provides methods to:
    - Compute equity series from trades or snapshots
    - Calculate maximum drawdown
    - Handle gaps and partial days
    - Account for peak tracking
    """

    def __init__(self, db_session: AsyncSession):
        """Initialize equity engine.

        Args:
            db_session: Async database session
        """
        self.db = db_session
        self.logger = logger

    async def compute_equity_series(
        self,
        user_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        initial_balance: Decimal = Decimal("10000"),
    ) -> EquitySeries:
        """Compute equity curve from trades.

        Handles gaps (non-trading days) by forward-filling previous equity.
        Robust to partial days and missing data.

        Args:
            user_id: User ID
            start_date: Start date (defaults to earliest trade)
            end_date: End date (defaults to latest trade)
            initial_balance: Starting account balance

        Returns:
            EquitySeries: Computed equity series

        Raises:
            ValueError: If no trades found or invalid date range
        """
        if start_date and end_date and start_date > end_date:
            raise ValueError("start_date must be <= end_date")

        # Get all trades for user, sorted by exit date
        trades_query = (
            select(TradesFact)
            .where(TradesFact.user_id == user_id)
            .order_by(TradesFact.exit_time)
        )
        result = await self.db.execute(trades_query)
        trades = result.scalars().all()

        if not trades:
            self.logger.warning(f"No trades found for user {user_id}")
            raise ValueError(f"No trades found for user {user_id}")

        # Determine date range
        min_date = trades[0].exit_time.date()
        max_date = trades[-1].exit_time.date()

        if start_date:
            min_date = max(min_date, start_date)
        if end_date:
            max_date = min(max_date, end_date)

        # Group trades by date
        trades_by_date: dict[date, list[Any]] = {}
        for trade in trades:
            trade_date = trade.exit_time.date()
            if min_date <= trade_date <= max_date:
                if trade_date not in trades_by_date:
                    trades_by_date[trade_date] = []
                trades_by_date[trade_date].append(trade)

        if not trades_by_date:
            raise ValueError("No trades in specified date range")

        # Build equity series
        dates = []
        equity_values = []
        peak_equity_values = []
        cumulative_pnl_values = []

        cumulative_pnl = Decimal(0)
        peak_equity = initial_balance

        # Iterate through all days in range (filling gaps)
        current_date = min_date
        last_equity = initial_balance

        while current_date <= max_date:
            if current_date in trades_by_date:
                # Sum PnL for trades on this date
                daily_pnl = sum(
                    (Decimal(str(t.net_pnl)) for t in trades_by_date[current_date]),
                    Decimal(0)
                )
                cumulative_pnl += daily_pnl
                last_equity = initial_balance + cumulative_pnl
                peak_equity = max(peak_equity, last_equity)
            # else: forward-fill from previous day (gap handling)

            dates.append(current_date)
            equity_values.append(last_equity)
            peak_equity_values.append(peak_equity)
            cumulative_pnl_values.append(cumulative_pnl)

            current_date += timedelta(days=1)

        self.logger.info(
            f"Computed equity series for user {user_id}: {len(dates)} points",
            extra={"user_id": user_id, "points": len(dates)},
        )

        return EquitySeries(
            dates=dates,
            equity=equity_values,
            peak_equity=peak_equity_values,
            cumulative_pnl=cumulative_pnl_values,
        )

    async def compute_drawdown(
        self, equity_series: EquitySeries
    ) -> tuple[Decimal, int]:
        """Compute maximum drawdown and duration.

        Calculates peak-to-trough drawdown and how long it persisted.

        Args:
            equity_series: EquitySeries object

        Returns:
            Tuple[Decimal, int]: (max_drawdown_percent, duration_days)
        """
        if not equity_series.equity:
            return Decimal(0), 0

        max_dd = Decimal(0)
        max_dd_duration = 0
        current_dd_start = None

        for i, equity in enumerate(equity_series.equity):
            peak = equity_series.peak_equity[i]
            current_dd = (
                ((peak - equity) / peak * Decimal(100)) if peak > 0 else Decimal(0)
            )

            if current_dd > 0:
                if current_dd_start is None:
                    current_dd_start = i
                    current_dd_duration = 1
                else:
                    current_dd_duration += 1

                if current_dd > max_dd:
                    max_dd = current_dd
                    max_dd_duration = current_dd_duration
            else:
                current_dd_start = None
                current_dd_duration = 0

        return max_dd, max_dd_duration

    async def get_recovery_factor(self, equity_series: EquitySeries) -> Decimal:
        """Get recovery factor: total return / max drawdown.

        Measures efficiency of drawdown recovery.
        Higher = better (recovered faster and went higher).

        Args:
            equity_series: EquitySeries object

        Returns:
            Decimal: Recovery factor (total_return / max_drawdown)
        """
        if not equity_series.drawdown:
            return Decimal(0)

        max_dd = max(equity_series.drawdown)
        total_return = equity_series.total_return

        if max_dd == 0:
            return total_return if total_return > 0 else Decimal(0)

        return total_return / max_dd

    async def get_summary_stats(
        self,
        user_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> dict:
        """Get comprehensive equity/drawdown statistics.

        Args:
            user_id: User ID
            start_date: Optional start date
            end_date: Optional end date

        Returns:
            dict: Summary statistics

        Raises:
            ValueError: If no trades found
        """
        equity_series = await self.compute_equity_series(user_id, start_date, end_date)
        max_dd, max_dd_duration = await self.compute_drawdown(equity_series)
        recovery_factor = await self.get_recovery_factor(equity_series)

        return {
            "initial_equity": (
                equity_series.equity[0] if equity_series.equity else Decimal(0)
            ),
            "final_equity": equity_series.final_equity,
            "total_return_percent": equity_series.total_return,
            "max_drawdown_percent": max_dd,
            "max_drawdown_duration_days": max_dd_duration,
            "recovery_factor": recovery_factor,
            "peak_equity": (
                max(equity_series.peak_equity)
                if equity_series.peak_equity
                else Decimal(0)
            ),
            "days_in_series": len(equity_series.dates),
        }
