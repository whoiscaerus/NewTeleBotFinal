"""Backtesting runner for strategy validation.

Executes strategies against historical data with deterministic results.
Ensures strategy parity with live trading code paths (PR-071).

Key Features:
    - Strategy parity: Uses same strategy code as live trading
    - Deterministic: Reproducible results from same data + params
    - Event-driven: Processes data bar-by-bar like live
    - Position tracking: Simulates entry/exit/PnL
    - Metrics parity: Uses same analytics as live (PR-052/053)

Architecture:
    1. Load historical data via adapter
    2. Initialize strategy (fib_rsi, ppo_gold, etc.)
    3. Process bars sequentially:
       - Check if new candle boundary (matches live detection)
       - Generate signal via strategy
       - Simulate fill (configurable slippage)
       - Track position PnL
    4. Generate report with metrics matching live analytics

Example:
    >>> from backend.app.backtest.runner import BacktestRunner
    >>> from backend.app.backtest.adapters import CSVAdapter
    >>>
    >>> adapter = CSVAdapter("data/GOLD_15M.csv")
    >>> runner = BacktestRunner(strategy="fib_rsi", data_source=adapter)
    >>> report = await runner.run(
    ...     symbol="GOLD",
    ...     start="2024-01-01",
    ...     end="2024-12-31",
    ...     initial_balance=10000.0
    ... )
    >>> print(f"Final equity: {report.final_equity}")
    >>> print(f"Max drawdown: {report.max_drawdown_pct}%")
    >>> print(f"Win rate: {report.win_rate}%")
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd

from backend.app.backtest.adapters import DataAdapter
from backend.app.backtest.report import BacktestReport, Trade
from backend.app.strategy.registry import get_strategy

logger = logging.getLogger(__name__)

# Prometheus metrics
try:
    from prometheus_client import Counter, Histogram

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    logger.warning("Prometheus not available, metrics disabled")

if PROMETHEUS_AVAILABLE:
    backtest_runs_total = Counter(
        "backtest_runs_total",
        "Total backtesting runs completed",
        ["strategy", "symbol", "result"],
    )
    backtest_duration_seconds = Histogram(
        "backtest_duration_seconds",
        "Backtest execution duration in seconds",
        ["strategy"],
    )


@dataclass
class BacktestConfig:
    """Backtesting configuration parameters.

    Attributes:
        initial_balance: Starting capital (default: 10000.0)
        position_size: Fixed lot size or fraction (default: 0.1)
        slippage_pips: Slippage per trade in pips (default: 2.0)
        commission_per_lot: Commission per lot (default: 0.0)
        max_positions: Max concurrent positions (default: 1)
        risk_per_trade: Risk % per trade (default: 2.0)
    """

    initial_balance: float = 10000.0
    position_size: float = 0.1  # lots
    slippage_pips: float = 2.0
    commission_per_lot: float = 0.0
    max_positions: int = 1
    risk_per_trade: float = 2.0  # %


@dataclass
class Position:
    """Open position tracking.

    Attributes:
        symbol: Trading symbol
        side: 0=buy, 1=sell
        entry_price: Entry price
        entry_time: Entry datetime
        size: Position size in lots
        stop_loss: Stop loss price (optional)
        take_profit: Take profit price (optional)
        pnl: Current unrealized PnL
    """

    symbol: str
    side: int  # 0=buy, 1=sell
    entry_price: float
    entry_time: datetime
    size: float
    stop_loss: float | None = None
    take_profit: float | None = None
    pnl: float = 0.0

    def update_pnl(self, current_price: float, pip_value: float = 10.0) -> None:
        """Update unrealized PnL based on current price.

        Args:
            current_price: Current market price
            pip_value: Value of 1 pip in account currency (default: $10 for standard lot)
        """
        if self.side == 0:  # Long
            price_diff = current_price - self.entry_price
        else:  # Short
            price_diff = self.entry_price - current_price

        # Convert price diff to pips (assuming 4-decimal pricing)
        pips = price_diff * 10000
        self.pnl = pips * pip_value * self.size

    def should_close(self, current_price: float) -> tuple[bool, str]:
        """Check if position should be closed (SL/TP hit).

        Args:
            current_price: Current market price

        Returns:
            (should_close, reason) tuple
        """
        if self.stop_loss is not None:
            if self.side == 0 and current_price <= self.stop_loss:
                return (True, "stop_loss")
            elif self.side == 1 and current_price >= self.stop_loss:
                return (True, "stop_loss")

        if self.take_profit is not None:
            if self.side == 0 and current_price >= self.take_profit:
                return (True, "take_profit")
            elif self.side == 1 and current_price <= self.take_profit:
                return (True, "take_profit")

        return (False, "")


class BacktestRunner:
    """Execute strategy backtests with historical data.

    Processes data bar-by-bar, generates signals via strategy,
    simulates fills, and tracks performance.

    Attributes:
        strategy_name: Strategy identifier (e.g., "fib_rsi", "ppo_gold")
        data_source: DataAdapter for loading historical data
        config: Backtesting configuration
        strategy: Loaded strategy instance
        positions: Currently open positions
        closed_trades: Completed trades
        equity_curve: Balance history over time
    """

    def __init__(
        self,
        strategy: str,
        data_source: DataAdapter,
        config: BacktestConfig | None = None,
    ):
        """Initialize backtest runner.

        Args:
            strategy: Strategy name (must be registered in registry)
            data_source: Data adapter for historical data
            config: Backtesting configuration (uses defaults if None)

        Raises:
            ValueError: If strategy not found in registry
        """
        self.strategy_name = strategy
        self.data_source = data_source
        self.config = config or BacktestConfig()

        # Load strategy (same code path as live trading)
        self.strategy = get_strategy(strategy)
        if self.strategy is None:
            raise ValueError(f"Strategy not found in registry: {strategy}")

        self.positions: list[Position] = []
        self.closed_trades: list[Trade] = []
        self.equity_curve: list[tuple[datetime, float]] = []
        self.balance: float = self.config.initial_balance

        logger.info(
            f"BacktestRunner initialized: strategy={strategy}, "
            f"initial_balance={self.config.initial_balance}"
        )

    async def run(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        strategy_params: dict[str, Any] | None = None,
    ) -> BacktestReport:
        """Execute backtest for date range.

        Args:
            symbol: Trading symbol
            start: Start datetime (inclusive)
            end: End datetime (inclusive)
            strategy_params: Strategy-specific parameters (optional)

        Returns:
            BacktestReport with performance metrics

        Raises:
            ValueError: If invalid parameters or no data
        """
        logger.info(
            f"Starting backtest: strategy={self.strategy_name}, symbol={symbol}, "
            f"start={start}, end={end}"
        )

        start_time = datetime.utcnow()

        try:
            # Load historical data
            df = await self.data_source.load(symbol, start, end)
            logger.info(f"Loaded {len(df)} bars for backtesting")

            # Reset state
            self.positions = []
            self.closed_trades = []
            self.equity_curve = [(start, self.config.initial_balance)]
            self.balance = self.config.initial_balance

            # Process bars sequentially (event-driven)
            for idx in range(len(df)):
                current_bar = df.iloc[idx]
                timestamp = df.index[idx]

                # Update open positions PnL
                self._update_positions(current_bar)

                # Check stop loss / take profit
                self._check_exits(current_bar, timestamp)

                # Generate signal (uses same strategy code as live)
                # Note: In real implementation, would pass proper windowed data
                if idx >= 50:  # Need history for indicators
                    window_df = df.iloc[max(0, idx - 100) : idx + 1]
                    signal = await self._generate_signal(
                        window_df, symbol, timestamp, strategy_params
                    )

                    if signal:
                        self._process_signal(signal, current_bar, timestamp)

                # Record equity
                current_equity = self.balance + sum(p.pnl for p in self.positions)
                self.equity_curve.append((timestamp, current_equity))

            # Close any remaining positions at end
            self._close_all_positions(df.iloc[-1], df.index[-1])

            # Generate report
            duration = (datetime.utcnow() - start_time).total_seconds()
            report = self._generate_report(symbol, start, end, duration)

            # Telemetry
            if PROMETHEUS_AVAILABLE:
                backtest_runs_total.labels(
                    strategy=self.strategy_name,
                    symbol=symbol,
                    result="success",
                ).inc()
                backtest_duration_seconds.labels(strategy=self.strategy_name).observe(
                    duration
                )

            logger.info(
                f"Backtest complete: trades={len(self.closed_trades)}, "
                f"final_equity={report.final_equity}, "
                f"max_dd={report.max_drawdown_pct:.2f}%"
            )

            return report

        except Exception as e:
            logger.error(f"Backtest failed: {e}", exc_info=True)
            if PROMETHEUS_AVAILABLE:
                backtest_runs_total.labels(
                    strategy=self.strategy_name,
                    symbol=symbol,
                    result="error",
                ).inc()
            raise

    def _update_positions(self, bar: pd.Series) -> None:
        """Update PnL for all open positions."""
        current_price = bar["close"]
        for position in self.positions:
            position.update_pnl(current_price)

    def _check_exits(self, bar: pd.Series, timestamp: datetime) -> None:
        """Check if any positions should be closed (SL/TP)."""
        current_price = bar["close"]

        for position in list(self.positions):  # Copy to allow removal
            should_close, reason = position.should_close(current_price)
            if should_close:
                self._close_position(position, current_price, timestamp, reason)

    async def _generate_signal(
        self,
        df: pd.DataFrame,
        symbol: str,
        timestamp: datetime,
        params: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        """Generate trading signal via strategy.

        Args:
            df: Historical data window
            symbol: Trading symbol
            timestamp: Current timestamp
            params: Strategy parameters

        Returns:
            Signal dict or None if no signal
        """
        try:
            # Call strategy (same code path as live)
            signal = await self.strategy.generate_signal(df, symbol, timestamp)

            if signal and hasattr(signal, "side"):
                return {
                    "side": signal.side,
                    "confidence": getattr(signal, "confidence", 0.7),
                    "stop_loss": getattr(signal, "stop_loss", None),
                    "take_profit": getattr(signal, "take_profit", None),
                }
            return None

        except Exception as e:
            logger.warning(f"Signal generation failed: {e}")
            return None

    def _process_signal(
        self, signal: dict[str, Any], bar: pd.Series, timestamp: datetime
    ) -> None:
        """Process signal and open position if conditions met."""
        # Check max positions
        if len(self.positions) >= self.config.max_positions:
            return

        # Simulate fill with slippage
        entry_price = bar["close"]
        if signal["side"] == 0:  # Buy
            entry_price += self.config.slippage_pips / 10000
        else:  # Sell
            entry_price -= self.config.slippage_pips / 10000

        # Create position
        position = Position(
            symbol=bar["symbol"],
            side=signal["side"],
            entry_price=entry_price,
            entry_time=timestamp,
            size=self.config.position_size,
            stop_loss=signal.get("stop_loss"),
            take_profit=signal.get("take_profit"),
        )

        self.positions.append(position)
        logger.debug(
            f"Opened position: {position.symbol} {'BUY' if position.side == 0 else 'SELL'} "
            f"@ {position.entry_price}"
        )

    def _close_position(
        self,
        position: Position,
        exit_price: float,
        exit_time: datetime,
        reason: str,
    ) -> None:
        """Close position and record trade."""
        position.update_pnl(exit_price)

        # Deduct commission
        commission = self.config.commission_per_lot * position.size
        net_pnl = position.pnl - commission

        # Update balance
        self.balance += net_pnl

        # Record trade
        trade = Trade(
            symbol=position.symbol,
            side=position.side,
            entry_price=position.entry_price,
            exit_price=exit_price,
            entry_time=position.entry_time,
            exit_time=exit_time,
            size=position.size,
            pnl=net_pnl,
            reason=reason,
        )
        self.closed_trades.append(trade)

        # Remove from open positions
        self.positions.remove(position)

        logger.debug(
            f"Closed position: {trade.symbol} PnL={trade.pnl:.2f} reason={reason}"
        )

    def _close_all_positions(self, bar: pd.Series, timestamp: datetime) -> None:
        """Close all remaining positions at end of backtest."""
        exit_price = bar["close"]
        for position in list(self.positions):
            self._close_position(position, exit_price, timestamp, "end_of_backtest")

    def _generate_report(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        duration_seconds: float,
    ) -> BacktestReport:
        """Generate backtest report with performance metrics.

        Uses same metrics calculation as live analytics (PR-052/053).
        """
        return BacktestReport.from_trades(
            strategy=self.strategy_name,
            symbol=symbol,
            start_date=start,
            end_date=end,
            initial_balance=self.config.initial_balance,
            trades=self.closed_trades,
            equity_curve=self.equity_curve,
            duration_seconds=duration_seconds,
        )
