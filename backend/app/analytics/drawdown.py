"""
Drawdown calculation specialized service.

Focuses specifically on drawdown metrics, analysis, and edge case handling.
Used by equity engine and directly by routes.
"""

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.analytics.equity import EquitySeries
from backend.app.analytics.models import EquityCurve
from backend.app.core.logging import get_logger

logger = get_logger(__name__)


class DrawdownAnalyzer:
    """Specialized analyzer for drawdown metrics.

    Provides:
    - Peak-to-trough calculation
    - Drawdown duration analysis
    - Recovery metrics
    - Comparative analysis
    """

    def __init__(self, db_session: AsyncSession):
        """Initialize drawdown analyzer.

        Args:
            db_session: Async database session
        """
        self.db = db_session
        self.logger = logger

    def calculate_max_drawdown(
        self, equity_values: list[Decimal]
    ) -> tuple[Decimal, int, int]:
        """Calculate maximum drawdown from equity values.

        Finds peak-to-trough drawdown in series.

        Args:
            equity_values: List of equity values (chronological)

        Returns:
            Tuple[Decimal, int, int]: (max_dd_percent, peak_index, trough_index)

        Raises:
            ValueError: If list is empty or invalid
        """
        if not equity_values:
            raise ValueError("equity_values cannot be empty")

        if len(equity_values) == 1:
            return Decimal(0), 0, 0

        max_dd = Decimal(0)
        peak_idx = 0
        trough_idx = 0
        peak_value = equity_values[0]
        peak_at_idx = 0

        for i, equity in enumerate(equity_values):
            if equity > peak_value:
                peak_value = equity
                peak_at_idx = i

            dd = (
                ((peak_value - equity) / peak_value * Decimal(100))
                if peak_value > 0
                else Decimal(0)
            )

            if dd > max_dd:
                max_dd = dd
                peak_idx = peak_at_idx
                trough_idx = i

        return max_dd, peak_idx, trough_idx

    def calculate_drawdown_duration(
        self,
        equity_values: list[Decimal],
        peak_idx: int,
        trough_idx: int,
    ) -> int:
        """Calculate drawdown duration in periods.

        Duration = number of periods from peak to recovery (or end of series).

        Args:
            equity_values: List of equity values
            peak_idx: Index of peak
            trough_idx: Index of trough

        Returns:
            int: Duration in periods (starting from peak)
        """
        if peak_idx >= len(equity_values):
            return 0

        peak_value = equity_values[peak_idx]

        # Find when equity recovers to peak (or end of series)
        for i in range(trough_idx, len(equity_values)):
            if equity_values[i] >= peak_value:
                return i - peak_idx

        # Never recovered
        return len(equity_values) - 1 - peak_idx

    def calculate_consecutive_losses(
        self, daily_pnls: list[Decimal]
    ) -> tuple[int, Decimal]:
        """Calculate consecutive losing days and total loss.

        Args:
            daily_pnls: List of daily PnL values

        Returns:
            Tuple[int, Decimal]: (max_consecutive_loss_days, total_loss_amount)
        """
        max_consecutive = 0
        current_consecutive = 0
        total_loss = Decimal(0)

        for pnl in daily_pnls:
            if pnl < 0:
                current_consecutive += 1
                max_consecutive = max(max_consecutive, current_consecutive)
                total_loss += abs(pnl)
            else:
                current_consecutive = 0

        return max_consecutive, total_loss

    def calculate_drawdown_stats(
        self,
        equity_series: EquitySeries,
    ) -> dict:
        """Calculate comprehensive drawdown statistics.

        Args:
            equity_series: EquitySeries object

        Returns:
            dict: Comprehensive drawdown stats
        """
        if not equity_series.equity:
            return {
                "max_drawdown_percent": Decimal(0),
                "peak_index": 0,
                "trough_index": 0,
                "drawdown_duration": 0,
                "recovery_time": 0,
                "drawdown_values": [],
                "average_drawdown": Decimal(0),
            }

        # Calculate max drawdown
        max_dd, peak_idx, trough_idx = self.calculate_max_drawdown(equity_series.equity)

        # Calculate duration
        duration = self.calculate_drawdown_duration(
            equity_series.equity, peak_idx, trough_idx
        )

        # All drawdown values
        drawdown_values = equity_series.drawdown

        # Average drawdown (excluding zero drawdowns)
        non_zero_dds = [dd for dd in drawdown_values if dd > 0]
        avg_dd = sum(non_zero_dds) / len(non_zero_dds) if non_zero_dds else Decimal(0)

        return {
            "max_drawdown_percent": max_dd,
            "peak_index": peak_idx,
            "peak_date": (
                equity_series.dates[peak_idx]
                if peak_idx < len(equity_series.dates)
                else None
            ),
            "trough_index": trough_idx,
            "trough_date": (
                equity_series.dates[trough_idx]
                if trough_idx < len(equity_series.dates)
                else None
            ),
            "drawdown_duration_periods": duration,
            "recovery_time": duration,  # Same as duration (time to recover)
            "current_drawdown_percent": (
                drawdown_values[-1] if drawdown_values else Decimal(0)
            ),
            "average_drawdown_percent": avg_dd,
            "max_drawdown_depth": max_dd,
            "all_drawdown_values": drawdown_values,
        }

    async def get_drawdown_by_date_range(
        self,
        user_id: str,
        start_date: date,
        end_date: date,
    ) -> dict:
        """Get drawdown stats for specific date range.

        Args:
            user_id: User ID
            start_date: Start date
            end_date: End date

        Returns:
            dict: Drawdown stats for range
        """
        # Query equity snapshots for date range
        query = select(EquityCurve).where(
            and_(
                EquityCurve.user_id == user_id,
                EquityCurve.date >= start_date,
                EquityCurve.date <= end_date,
            )
        )
        result = await self.db.execute(query)
        snapshots = list(result.scalars().all())

        if not snapshots:
            self.logger.warning(
                f"No equity snapshots found for user {user_id} between {start_date} and {end_date}"
            )
            return {
                "max_drawdown": Decimal(0),
                "current_drawdown": Decimal(0),
                "days_in_dd": 0,
            }

        # Sort by date
        snapshots.sort(key=lambda s: s.date)

        # Extract equity and dates
        dates = [s.date for s in snapshots]
        equity_values = [s.equity for s in snapshots]

        # Calculate
        max_dd, peak_idx, trough_idx = self.calculate_max_drawdown(equity_values)
        duration = self.calculate_drawdown_duration(equity_values, peak_idx, trough_idx)

        return {
            "max_drawdown_percent": float(max_dd),
            "current_drawdown_percent": float(snapshots[-1].drawdown),
            "drawdown_duration_days": duration,
            "peak_equity": (
                float(equity_values[peak_idx]) if peak_idx < len(equity_values) else 0
            ),
            "trough_equity": (
                float(equity_values[trough_idx])
                if trough_idx < len(equity_values)
                else 0
            ),
            "start_date": dates[0],
            "end_date": dates[-1],
        }

    async def get_monthly_drawdown_stats(
        self,
        user_id: str,
        year: int,
        month: int,
    ) -> dict:
        """Get drawdown stats for a specific month.

        Args:
            user_id: User ID
            year: Year
            month: Month (1-12)

        Returns:
            dict: Monthly drawdown stats
        """
        # Find first and last day of month
        if month == 12:
            first_day = date(year, month, 1)
            last_day = date(year + 1, 1, 1) - timedelta(days=1)
        else:

            first_day = date(year, month, 1)
            last_day = date(year, month + 1, 1) - timedelta(days=1)

        return await self.get_drawdown_by_date_range(user_id, first_day, last_day)


# Helper function for import
