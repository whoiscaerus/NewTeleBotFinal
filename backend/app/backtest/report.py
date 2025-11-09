"""Backtest report generation with metrics parity to live analytics.

Generates comprehensive performance reports matching live metrics (PR-052/053):
    - PnL, equity curve, drawdown
    - Sharpe, Sortino, Calmar ratios
    - Win rate, profit factor, recovery factor
    - Export to HTML, CSV, JSON

Key Features:
    - Metrics parity: Identical calculations to live analytics
    - Multiple formats: HTML (visual), CSV (data), JSON (API)
    - Trade-level details: Entry/exit, PnL, reason
    - Summary statistics: Total trades, win rate, avg PnL
    - Risk metrics: Max DD, Sharpe, Sortino, Calmar

Example:
    >>> report = BacktestReport.from_trades(
    ...     strategy="fib_rsi",
    ...     symbol="GOLD",
    ...     start_date=datetime(2024, 1, 1),
    ...     end_date=datetime(2024, 12, 31),
    ...     initial_balance=10000.0,
    ...     trades=trades_list,
    ...     equity_curve=equity_data
    ... )
    >>> report.to_html("backtest_results.html")
    >>> report.to_csv("backtest_trades.csv")
    >>> report.to_json("backtest_summary.json")
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class Trade:
    """Individual trade record.

    Attributes:
        symbol: Trading symbol
        side: 0=buy, 1=sell
        entry_price: Entry price
        exit_price: Exit price
        entry_time: Entry datetime
        exit_time: Exit datetime
        size: Position size in lots
        pnl: Net PnL (after commission)
        reason: Exit reason (stop_loss, take_profit, end_of_backtest)
    """

    symbol: str
    side: int
    entry_price: float
    exit_price: float
    entry_time: datetime
    exit_time: datetime
    size: float
    pnl: float
    reason: str

    @property
    def duration_hours(self) -> float:
        """Trade duration in hours."""
        delta = self.exit_time - self.entry_time
        return delta.total_seconds() / 3600

    @property
    def pips(self) -> float:
        """Trade PnL in pips."""
        if self.side == 0:  # Long
            price_diff = self.exit_price - self.entry_price
        else:  # Short
            price_diff = self.entry_price - self.exit_price
        return price_diff * 10000  # Assuming 4-decimal pricing


@dataclass
class BacktestReport:
    """Comprehensive backtest performance report.

    Attributes:
        strategy: Strategy name
        symbol: Trading symbol
        start_date: Backtest start date
        end_date: Backtest end date
        initial_balance: Starting capital
        final_equity: Ending equity
        total_trades: Number of trades executed
        winning_trades: Number of profitable trades
        losing_trades: Number of losing trades
        win_rate: Win rate percentage (0-100)
        total_pnl: Total PnL
        gross_profit: Sum of winning trades
        gross_loss: Sum of losing trades (absolute value)
        profit_factor: Gross profit / gross loss
        avg_win: Average winning trade PnL
        avg_loss: Average losing trade PnL (absolute value)
        max_win: Largest winning trade
        max_loss: Largest losing trade (absolute value)
        max_drawdown: Maximum drawdown in currency
        max_drawdown_pct: Maximum drawdown as percentage
        sharpe_ratio: Sharpe ratio (annualized)
        sortino_ratio: Sortino ratio (annualized)
        calmar_ratio: Calmar ratio (return / max DD)
        recovery_factor: Net profit / max DD
        trades: List of individual trades
        equity_curve: List of (timestamp, equity) tuples
        duration_seconds: Backtest execution duration
    """

    strategy: str
    symbol: str
    start_date: datetime
    end_date: datetime
    initial_balance: float
    final_equity: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_pnl: float
    gross_profit: float
    gross_loss: float
    profit_factor: float
    avg_win: float
    avg_loss: float
    max_win: float
    max_loss: float
    max_drawdown: float
    max_drawdown_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    recovery_factor: float
    trades: list[Trade] = field(default_factory=list)
    equity_curve: list[tuple[datetime, float]] = field(default_factory=list)
    duration_seconds: float = 0.0

    @classmethod
    def from_trades(
        cls,
        strategy: str,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        initial_balance: float,
        trades: list[Trade],
        equity_curve: list[tuple[datetime, float]],
        duration_seconds: float = 0.0,
        risk_free_rate: float = 0.02,  # 2% annual risk-free rate
    ) -> "BacktestReport":
        """Generate report from trade list.

        Calculates all performance metrics matching live analytics (PR-052/053).

        Args:
            strategy: Strategy name
            symbol: Trading symbol
            start_date: Backtest start date
            end_date: Backtest end date
            initial_balance: Starting capital
            trades: List of closed trades
            equity_curve: List of (timestamp, equity) tuples
            duration_seconds: Backtest execution duration
            risk_free_rate: Annual risk-free rate for Sharpe calculation

        Returns:
            BacktestReport with computed metrics
        """
        # Calculate equity and drawdown (even if no trades)
        final_equity = equity_curve[-1][1] if equity_curve else initial_balance
        max_drawdown, max_drawdown_pct = cls._calculate_drawdown(equity_curve)

        if not trades:
            # No trades executed
            return cls(
                strategy=strategy,
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                initial_balance=initial_balance,
                final_equity=final_equity,
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate=0.0,
                total_pnl=0.0,
                gross_profit=0.0,
                gross_loss=0.0,
                profit_factor=0.0,
                avg_win=0.0,
                avg_loss=0.0,
                max_win=0.0,
                max_loss=0.0,
                max_drawdown=max_drawdown,
                max_drawdown_pct=max_drawdown_pct,
                sharpe_ratio=0.0,
                sortino_ratio=0.0,
                calmar_ratio=0.0,
                recovery_factor=0.0,
                trades=[],
                equity_curve=equity_curve,
                duration_seconds=duration_seconds,
            )

        # Basic counts
        total_trades = len(trades)
        winning_trades = sum(1 for t in trades if t.pnl > 0)
        losing_trades = sum(1 for t in trades if t.pnl < 0)
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0

        # PnL metrics
        total_pnl = sum(t.pnl for t in trades)
        gross_profit = sum(t.pnl for t in trades if t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in trades if t.pnl < 0))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 0.0

        # Average metrics
        wins = [t.pnl for t in trades if t.pnl > 0]
        losses = [abs(t.pnl) for t in trades if t.pnl < 0]
        avg_win = (sum(wins) / len(wins)) if wins else 0.0
        avg_loss = (sum(losses) / len(losses)) if losses else 0.0

        # Extremes
        max_win = max(wins) if wins else 0.0
        max_loss = max(losses) if losses else 0.0

        # Equity and drawdown (matches PR-052 equity.py)
        final_equity = equity_curve[-1][1] if equity_curve else initial_balance
        max_drawdown, max_drawdown_pct = cls._calculate_drawdown(equity_curve)

        # Risk-adjusted metrics (matches PR-053 metrics.py)
        sharpe_ratio = cls._calculate_sharpe(trades, initial_balance, risk_free_rate)
        sortino_ratio = cls._calculate_sortino(trades, initial_balance, risk_free_rate)
        calmar_ratio = cls._calculate_calmar(total_pnl, max_drawdown)
        recovery_factor = (total_pnl / max_drawdown) if max_drawdown > 0 else 0.0

        return cls(
            strategy=strategy,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            initial_balance=initial_balance,
            final_equity=final_equity,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            total_pnl=total_pnl,
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            profit_factor=profit_factor,
            avg_win=avg_win,
            avg_loss=avg_loss,
            max_win=max_win,
            max_loss=max_loss,
            max_drawdown=max_drawdown,
            max_drawdown_pct=max_drawdown_pct,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            calmar_ratio=calmar_ratio,
            recovery_factor=recovery_factor,
            trades=trades,
            equity_curve=equity_curve,
            duration_seconds=duration_seconds,
        )

    @staticmethod
    def _calculate_drawdown(
        equity_curve: list[tuple[datetime, float]],
    ) -> tuple[float, float]:
        """Calculate maximum drawdown.

        Matches PR-052 drawdown.py calculation.

        Args:
            equity_curve: List of (timestamp, equity) tuples

        Returns:
            (max_drawdown_currency, max_drawdown_pct) tuple
        """
        if not equity_curve:
            return (0.0, 0.0)

        equities = [e[1] for e in equity_curve]
        peak = equities[0]
        max_dd = 0.0
        max_dd_pct = 0.0

        for equity in equities:
            if equity > peak:
                peak = equity

            dd = peak - equity
            dd_pct = (dd / peak * 100) if peak > 0 else 0.0

            if dd > max_dd:
                max_dd = dd
                max_dd_pct = dd_pct

        return (max_dd, max_dd_pct)

    @staticmethod
    def _calculate_sharpe(
        trades: list[Trade],
        initial_balance: float,
        risk_free_rate: float,
    ) -> float:
        """Calculate Sharpe ratio (annualized).

        Matches PR-053 metrics.py calculation.

        Args:
            trades: List of trades
            initial_balance: Starting capital
            risk_free_rate: Annual risk-free rate

        Returns:
            Annualized Sharpe ratio
        """
        if not trades:
            return 0.0

        # Calculate daily returns
        returns = [t.pnl / initial_balance for t in trades]
        if not returns:
            return 0.0

        returns_array = np.array(returns)
        mean_return = np.mean(returns_array)
        std_return = np.std(returns_array)

        if std_return == 0:
            return 0.0

        # Annualize (assuming 252 trading days)
        excess_return = mean_return - (risk_free_rate / 252)
        sharpe = excess_return / std_return * np.sqrt(252)

        return float(sharpe)

    @staticmethod
    def _calculate_sortino(
        trades: list[Trade],
        initial_balance: float,
        risk_free_rate: float,
    ) -> float:
        """Calculate Sortino ratio (annualized).

        Matches PR-053 metrics.py calculation.

        Args:
            trades: List of trades
            initial_balance: Starting capital
            risk_free_rate: Annual risk-free rate

        Returns:
            Annualized Sortino ratio
        """
        if not trades:
            return 0.0

        # Calculate daily returns
        returns = [t.pnl / initial_balance for t in trades]
        if not returns:
            return 0.0

        returns_array = np.array(returns)
        mean_return = np.mean(returns_array)

        # Downside deviation (only negative returns)
        negative_returns = returns_array[returns_array < 0]
        if len(negative_returns) == 0:
            return 0.0

        downside_std = np.std(negative_returns)
        if downside_std == 0:
            return 0.0

        # Annualize
        excess_return = mean_return - (risk_free_rate / 252)
        sortino = excess_return / downside_std * np.sqrt(252)

        return float(sortino)

    @staticmethod
    def _calculate_calmar(total_pnl: float, max_drawdown: float) -> float:
        """Calculate Calmar ratio.

        Matches PR-053 metrics.py calculation.

        Args:
            total_pnl: Total PnL
            max_drawdown: Maximum drawdown in currency

        Returns:
            Calmar ratio (return / max DD)
        """
        if max_drawdown == 0:
            return 0.0
        return total_pnl / max_drawdown

    def to_html(self, filepath: str | Path) -> None:
        """Export report to HTML file.

        Generates visual report with:
            - Summary statistics table
            - Equity curve chart
            - Trade list table
            - Performance metrics

        Args:
            filepath: Output HTML file path
        """
        filepath = Path(filepath)
        logger.info(f"Exporting HTML report to: {filepath}")

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Backtest Report - {self.strategy} - {self.symbol}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        h1 {{ color: #333; }}
        table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #4CAF50; color: white; }}
        .positive {{ color: green; }}
        .negative {{ color: red; }}
        .metric-card {{ background: #f9f9f9; padding: 15px; margin: 10px 0; border-radius: 5px; }}
    </style>
</head>
<body>
    <h1>Backtest Report: {self.strategy} - {self.symbol}</h1>

    <div class="metric-card">
        <h2>Summary</h2>
        <table>
            <tr><th>Metric</th><th>Value</th></tr>
            <tr><td>Period</td><td>{self.start_date.date()} to {self.end_date.date()}</td></tr>
            <tr><td>Initial Balance</td><td>${self.initial_balance:,.2f}</td></tr>
            <tr><td>Final Equity</td><td class="{'positive' if self.final_equity > self.initial_balance else 'negative'}">${self.final_equity:,.2f}</td></tr>
            <tr><td>Total PnL</td><td class="{'positive' if self.total_pnl > 0 else 'negative'}">${self.total_pnl:,.2f}</td></tr>
            <tr><td>Return</td><td>{(self.total_pnl / self.initial_balance * 100):.2f}%</td></tr>
        </table>
    </div>

    <div class="metric-card">
        <h2>Trade Statistics</h2>
        <table>
            <tr><th>Metric</th><th>Value</th></tr>
            <tr><td>Total Trades</td><td>{self.total_trades}</td></tr>
            <tr><td>Winning Trades</td><td class="positive">{self.winning_trades}</td></tr>
            <tr><td>Losing Trades</td><td class="negative">{self.losing_trades}</td></tr>
            <tr><td>Win Rate</td><td>{self.win_rate:.2f}%</td></tr>
            <tr><td>Profit Factor</td><td>{self.profit_factor:.2f}</td></tr>
            <tr><td>Avg Win</td><td class="positive">${self.avg_win:,.2f}</td></tr>
            <tr><td>Avg Loss</td><td class="negative">${self.avg_loss:,.2f}</td></tr>
            <tr><td>Max Win</td><td class="positive">${self.max_win:,.2f}</td></tr>
            <tr><td>Max Loss</td><td class="negative">${self.max_loss:,.2f}</td></tr>
        </table>
    </div>

    <div class="metric-card">
        <h2>Risk Metrics</h2>
        <table>
            <tr><th>Metric</th><th>Value</th></tr>
            <tr><td>Max Drawdown</td><td class="negative">${self.max_drawdown:,.2f} ({self.max_drawdown_pct:.2f}%)</td></tr>
            <tr><td>Sharpe Ratio</td><td>{self.sharpe_ratio:.2f}</td></tr>
            <tr><td>Sortino Ratio</td><td>{self.sortino_ratio:.2f}</td></tr>
            <tr><td>Calmar Ratio</td><td>{self.calmar_ratio:.2f}</td></tr>
            <tr><td>Recovery Factor</td><td>{self.recovery_factor:.2f}</td></tr>
        </table>
    </div>

    <div class="metric-card">
        <h2>All Trades</h2>
        <table>
            <tr>
                <th>Entry Time</th>
                <th>Exit Time</th>
                <th>Side</th>
                <th>Entry Price</th>
                <th>Exit Price</th>
                <th>Size</th>
                <th>PnL</th>
                <th>Pips</th>
                <th>Duration (h)</th>
                <th>Reason</th>
            </tr>
            {''.join([
                f'''<tr>
                    <td>{t.entry_time}</td>
                    <td>{t.exit_time}</td>
                    <td>{'BUY' if t.side == 0 else 'SELL'}</td>
                    <td>{t.entry_price:.5f}</td>
                    <td>{t.exit_price:.5f}</td>
                    <td>{t.size:.2f}</td>
                    <td class="{'positive' if t.pnl > 0 else 'negative'}">${t.pnl:,.2f}</td>
                    <td class="{'positive' if t.pips > 0 else 'negative'}">{t.pips:.1f}</td>
                    <td>{t.duration_hours:.1f}</td>
                    <td>{t.reason}</td>
                </tr>'''
                for t in self.trades
            ])}
        </table>
    </div>

    <p><small>Generated: {datetime.utcnow()} UTC | Duration: {self.duration_seconds:.2f}s</small></p>
</body>
</html>
"""

        filepath.write_text(html, encoding="utf-8")
        logger.info(f"HTML report exported successfully: {filepath}")

    def to_csv(self, filepath: str | Path) -> None:
        """Export trades to CSV file.

        Args:
            filepath: Output CSV file path
        """
        filepath = Path(filepath)
        logger.info(f"Exporting CSV trades to: {filepath}")

        # Convert trades to DataFrame
        trades_data = [
            {
                "entry_time": t.entry_time,
                "exit_time": t.exit_time,
                "symbol": t.symbol,
                "side": "BUY" if t.side == 0 else "SELL",
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "size": t.size,
                "pnl": t.pnl,
                "pips": t.pips,
                "duration_hours": t.duration_hours,
                "reason": t.reason,
            }
            for t in self.trades
        ]

        df = pd.DataFrame(trades_data)
        df.to_csv(filepath, index=False)

        logger.info(f"CSV trades exported successfully: {filepath}")

    def to_json(self, filepath: str | Path) -> None:
        """Export report summary to JSON file.

        Args:
            filepath: Output JSON file path
        """
        filepath = Path(filepath)
        logger.info(f"Exporting JSON summary to: {filepath}")

        summary = {
            "strategy": self.strategy,
            "symbol": self.symbol,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "initial_balance": self.initial_balance,
            "final_equity": self.final_equity,
            "total_pnl": self.total_pnl,
            "return_pct": (self.total_pnl / self.initial_balance * 100),
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "avg_win": self.avg_win,
            "avg_loss": self.avg_loss,
            "max_win": self.max_win,
            "max_loss": self.max_loss,
            "max_drawdown": self.max_drawdown,
            "max_drawdown_pct": self.max_drawdown_pct,
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "calmar_ratio": self.calmar_ratio,
            "recovery_factor": self.recovery_factor,
            "duration_seconds": self.duration_seconds,
        }

        filepath.write_text(json.dumps(summary, indent=2), encoding="utf-8")

        logger.info(f"JSON summary exported successfully: {filepath}")
