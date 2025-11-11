"""
Performance metrics calculation engine.

Computes professional-grade KPIs:
- Sharpe Ratio: excess return / volatility
- Sortino Ratio: excess return / downside volatility
- Calmar Ratio: annual return / max drawdown
- Profit Factor: gross wins / gross losses
- Recovery Factor: total return / max drawdown

Supports rolling windows: 30/90/365 days.
Risk-free rate configurable via environment.
"""

import math
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.analytics.models import EquityCurve, TradesFact
from backend.app.core.logging import get_logger

logger = get_logger(__name__)

try:
    from prometheus_client import Histogram

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

if PROMETHEUS_AVAILABLE:
    metrics_compute_histogram = Histogram(
        "metrics_compute_seconds",
        "Metrics computation duration in seconds",
        labelnames=["metric_type", "window"],
    )


class PerformanceMetrics:
    """Service for computing performance metrics.

    Provides methods to calculate:
    - Sharpe Ratio (excess return vs risk-free rate)
    - Sortino Ratio (excess return vs downside risk)
    - Calmar Ratio (annual return / max drawdown)
    - Profit Factor (gross wins / gross losses)
    - Recovery Factor (total return / max drawdown)

    With support for rolling windows and configurable risk-free rate.
    """

    # Default assumptions
    DEFAULT_RISK_FREE_RATE = Decimal("0.02")  # 2% annual
    RISK_FREE_DAILY = DEFAULT_RISK_FREE_RATE / Decimal(252)  # 252 trading days/year

    def __init__(
        self, db_session: AsyncSession, risk_free_rate: Optional[Decimal] = None
    ):
        """Initialize metrics calculator.

        Args:
            db_session: Async database session
            risk_free_rate: Annual risk-free rate (default 2%)
        """
        self.db = db_session
        self.logger = logger
        self.risk_free_rate = risk_free_rate or self.DEFAULT_RISK_FREE_RATE
        self.risk_free_daily = self.risk_free_rate / Decimal(252)

    def calculate_sharpe_ratio(
        self,
        daily_returns: list[Decimal],
    ) -> Decimal:
        """Calculate Sharpe Ratio.

        Sharpe = (mean_return - risk_free_rate) / std_dev
        Measures excess return per unit of risk.

        Args:
            daily_returns: List of daily returns (as decimals, e.g., 0.01 for 1%)

        Returns:
            Decimal: Sharpe Ratio

        Raises:
            ValueError: If insufficient data
        """
        if not daily_returns or len(daily_returns) < 2:
            return Decimal(0)

        # Calculate mean return
        mean_return = sum(daily_returns) / Decimal(len(daily_returns))

        # Calculate standard deviation
        variance = sum((r - mean_return) ** 2 for r in daily_returns) / Decimal(
            len(daily_returns)
        )
        std_dev = Decimal(str(math.sqrt(float(variance))))

        # Avoid division by zero
        if std_dev == 0:
            return Decimal(0)

        # Sharpe = (mean - rf) / std
        sharpe = (mean_return - self.risk_free_daily) / std_dev

        return sharpe.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    def calculate_sortino_ratio(
        self,
        daily_returns: list[Decimal],
    ) -> Decimal:
        """Calculate Sortino Ratio.

        Sortino = (mean_return - risk_free_rate) / downside_std_dev
        Similar to Sharpe but only penalizes downside volatility.

        Args:
            daily_returns: List of daily returns (as decimals)

        Returns:
            Decimal: Sortino Ratio
        """
        if not daily_returns or len(daily_returns) < 2:
            return Decimal(0)

        # Calculate mean return
        mean_return = sum(daily_returns) / Decimal(len(daily_returns))

        # Calculate downside standard deviation (only negative returns)
        negative_returns = [r for r in daily_returns if r < 0]
        if not negative_returns:
            # No negative returns = perfect (very high sortino)
            return Decimal(999)

        downside_variance = sum(
            min(r - mean_return, Decimal(0)) ** 2 for r in daily_returns
        ) / Decimal(len(daily_returns))
        downside_std = Decimal(str(math.sqrt(float(downside_variance))))

        # Avoid division by zero
        if downside_std == 0:
            return Decimal(0)

        # Sortino = (mean - rf) / downside_std
        sortino = (mean_return - self.risk_free_daily) / downside_std

        return sortino.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    def calculate_calmar_ratio(
        self,
        total_return: Decimal,
        max_drawdown: Decimal,
        days: int,
    ) -> Decimal:
        """Calculate Calmar Ratio.

        Calmar = annual_return / max_drawdown
        Measures return relative to risk (drawdown).

        Args:
            total_return: Total return over period (as %, e.g., 15 for 15%)
            max_drawdown: Maximum drawdown (as %, e.g., 10 for 10%)
            days: Number of days in period

        Returns:
            Decimal: Calmar Ratio

        Raises:
            ValueError: If max_drawdown is 0 or negative
        """
        if max_drawdown <= 0:
            return Decimal(0)

        # Annualize return
        annual_return = total_return * Decimal(365) / Decimal(days)

        # Calmar = annual_return / max_drawdown
        calmar = annual_return / max_drawdown

        return calmar.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    def calculate_profit_factor(
        self,
        trades: list[tuple[Decimal, bool]],
    ) -> Decimal:
        """Calculate Profit Factor.

        Profit Factor = sum(winning_pnls) / abs(sum(losing_pnls))
        Higher is better. >1 = profitable, <1 = losing.

        Args:
            trades: List of (pnl, is_winning) tuples

        Returns:
            Decimal: Profit Factor
        """
        if not trades:
            return Decimal(0)

        winning_pnl = sum((pnl for pnl, is_win in trades if is_win), Decimal(0))
        losing_pnl = sum((pnl for pnl, is_win in trades if not is_win), Decimal(0))

        if losing_pnl >= 0:
            # No losses
            return Decimal(999) if winning_pnl > 0 else Decimal(0)

        profit_factor = Decimal(winning_pnl) / abs(Decimal(losing_pnl))

        return profit_factor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def calculate_recovery_factor(
        self,
        total_return: Decimal,
        max_drawdown: Decimal,
    ) -> Decimal:
        """Calculate Recovery Factor.

        Recovery Factor = total_return / max_drawdown
        Measures how quickly account recovered from worst loss.

        Args:
            total_return: Total return (as %, e.g., 50 for 50%)
            max_drawdown: Maximum drawdown (as %, e.g., 20 for 20%)

        Returns:
            Decimal: Recovery Factor
        """
        if max_drawdown <= 0:
            return Decimal(0)

        recovery = total_return / max_drawdown

        return recovery.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    async def get_daily_returns(
        self,
        user_id: str,
        start_date: date,
        end_date: date,
    ) -> list[Decimal]:
        """Get daily returns for date range.

        Args:
            user_id: User ID
            start_date: Start date
            end_date: End date

        Returns:
            List[Decimal]: Daily returns (as decimals, e.g., 0.01 for 1%)
        """
        query = (
            select(EquityCurve)
            .where(
                and_(
                    EquityCurve.user_id == user_id,
                    EquityCurve.date >= start_date,
                    EquityCurve.date <= end_date,
                )
            )
            .order_by(EquityCurve.date)
        )

        result = await self.db.execute(query)
        snapshots = result.scalars().all()

        if len(snapshots) < 2:
            return []

        daily_returns = []
        for i in range(1, len(snapshots)):
            prev_equity = snapshots[i - 1].equity
            curr_equity = snapshots[i].equity

            if prev_equity > 0:
                return_pct = (curr_equity - prev_equity) / prev_equity
                daily_returns.append(return_pct)

        return daily_returns

    async def get_metrics_for_window(
        self,
        user_id: str,
        window_days: int = 90,
    ) -> dict[str, Decimal | int]:
        """Get all metrics for a rolling window.

        Args:
            user_id: User ID
            window_days: Window size (30, 90, 365)

        Returns:
            Dict: Metrics dict with sharpe, sortino, calmar, profit_factor, recovery_factor

        Raises:
            ValueError: If insufficient data
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=window_days)

        # Get daily returns
        daily_returns = await self.get_daily_returns(user_id, start_date, end_date)
        if not daily_returns:
            raise ValueError(f"Insufficient data for window_days={window_days}")

        # Get equity curve
        query = (
            select(EquityCurve)
            .where(
                and_(
                    EquityCurve.user_id == user_id,
                    EquityCurve.date >= start_date,
                    EquityCurve.date <= end_date,
                )
            )
            .order_by(EquityCurve.date)
        )

        result = await self.db.execute(query)
        snapshots = result.scalars().all()

        if not snapshots:
            raise ValueError("No equity snapshots found")

        # Calculate metrics
        first_equity = snapshots[0].equity
        last_equity = snapshots[-1].equity
        total_return = (
            ((last_equity - first_equity) / first_equity * Decimal(100))
            if first_equity > 0
            else Decimal(0)
        )

        # Get trades for profit factor
        trades_query = select(TradesFact).where(
            and_(
                TradesFact.user_id == user_id,
                TradesFact.exit_time
                >= datetime.combine(start_date, datetime.min.time()),
                TradesFact.exit_time <= datetime.combine(end_date, datetime.max.time()),
            )
        )
        result = await self.db.execute(trades_query)
        trades_list = result.scalars().all()

        # Max drawdown from snapshots
        max_dd = max((s.drawdown for s in snapshots), default=Decimal(0))

        # Build trade tuples for profit factor
        trade_tuples = [
            (Decimal(str(t.net_pnl)), bool(t.winning_trade)) for t in trades_list
        ]

        return {
            "sharpe_ratio": self.calculate_sharpe_ratio(daily_returns),
            "sortino_ratio": self.calculate_sortino_ratio(daily_returns),
            "calmar_ratio": self.calculate_calmar_ratio(
                total_return, max_dd, window_days
            ),
            "profit_factor": self.calculate_profit_factor(trade_tuples),
            "recovery_factor": self.calculate_recovery_factor(total_return, max_dd),
            "total_return_percent": total_return,
            "max_drawdown_percent": max_dd,
            "win_rate": (
                Decimal(
                    sum(1 for t in trades_list if t.winning_trade)
                    / len(trades_list)
                    * 100
                )
                if trades_list
                else Decimal(0)
            ),
            "num_trades": len(trades_list),
            "period_days": window_days,
        }

    async def get_all_window_metrics(
        self,
        user_id: str,
    ) -> dict[int, dict[str, Decimal | int]]:
        """Get metrics for all standard windows (30, 90, 365 days).

        Args:
            user_id: User ID

        Returns:
            Dict mapping window_days -> metrics dict
        """
        results = {}

        for window in [30, 90, 365]:
            try:
                results[window] = await self.get_metrics_for_window(user_id, window)
            except ValueError as e:
                self.logger.warning(
                    f"Could not compute metrics for {window}d window: {e}"
                )
                results[window] = {}

        return results


# Module-level wrapper functions for backward compatibility with public routes
def calculate_sharpe_ratio(profits: list[float]) -> float:
    """Calculate Sharpe ratio from profit list.

    Args:
        profits: List of daily profit/loss values

    Returns:
        Sharpe ratio
    """
    if not profits or len(profits) < 2:
        return 0.0

    # Convert to numpy-like operations without numpy
    mean = sum(profits) / len(profits)
    variance = sum((x - mean) ** 2 for x in profits) / len(profits)
    std_dev = math.sqrt(variance)

    if std_dev == 0:
        return 0.0

    return mean / std_dev


def calculate_sortino_ratio(profits: list[float]) -> float:
    """Calculate Sortino ratio from profit list.

    Only considers downside volatility.

    Args:
        profits: List of daily profit/loss values

    Returns:
        Sortino ratio
    """
    if not profits or len(profits) < 2:
        return 0.0

    mean = sum(profits) / len(profits)

    # Only downside deviations (negative returns)
    downside_returns = [max(0, -x) for x in profits]
    downside_var = sum(x**2 for x in downside_returns) / len(downside_returns)
    downside_std = math.sqrt(downside_var)

    if downside_std == 0:
        return 0.0

    return mean / downside_std


def calculate_calmar_ratio(profits: list[float]) -> float:
    """Calculate Calmar ratio from profit list.

    Annual return / max drawdown.

    Args:
        profits: List of daily profit/loss values

    Returns:
        Calmar ratio
    """
    if not profits:
        return 0.0

    total_return = sum(profits)

    # Calculate max drawdown from running sum (equity curve)
    running_equity = 0.0
    peak = 0.0
    max_dd = 0.0

    for profit in profits:
        running_equity += profit
        if running_equity > peak:
            peak = running_equity
        drawdown = peak - running_equity
        if drawdown > max_dd:
            max_dd = drawdown

    if max_dd <= 0:
        return 0.0

    # Annualize return (assume 252 trading days)
    annual_return = total_return * 252 / max(len(profits), 1)

    return annual_return / max_dd


def calculate_profit_factor(trades: list[Any]) -> float:
    """Calculate profit factor from trade list.

    Gross wins / gross losses.

    Args:
        trades: List of Trade objects with profit attribute

    Returns:
        Profit factor
    """
    if not trades:
        return 0.0

    gross_wins = sum(float(t.profit) for t in trades if t.profit and t.profit > 0)
    gross_losses = sum(
        abs(float(t.profit)) for t in trades if t.profit and t.profit < 0
    )

    if gross_losses == 0:
        return 0.0

    return float(gross_wins / gross_losses)
