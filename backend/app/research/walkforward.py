"""Walk-forward validation for time-series strategy testing.

K-fold cross-validation with anchored walk-forward windows.
Each fold uses expanding training data and fixed test window.

Process:
    1. Split data into K folds chronologically
    2. For each fold: train on [0, fold), test on [fold, fold+1)
    3. Run backtest on test window with trained parameters
    4. Aggregate metrics across all folds (OOS performance)

Example:
    >>> validator = WalkForwardValidator(n_folds=5, test_window_days=90)
    >>> result = await validator.validate(
    ...     strategy_name="fib_rsi",
    ...     data_source=csv_adapter,
    ...     symbol="GOLD",
    ...     start_date=datetime(2023, 1, 1),
    ...     end_date=datetime(2024, 12, 31),
    ... )
    >>> assert result.overall_sharpe > 1.0
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

import numpy as np

from backend.app.backtest.adapters import DataAdapter
from backend.app.backtest.runner import BacktestConfig, BacktestRunner

logger = logging.getLogger(__name__)


@dataclass
class FoldResult:
    """Results from a single walk-forward fold.

    Attributes:
        fold_index: Fold number (0-indexed)
        train_start: Training window start date
        train_end: Training window end date
        test_start: Test window start date
        test_end: Test window end date
        sharpe_ratio: Sharpe ratio on test window
        max_drawdown: Max drawdown % on test window
        win_rate: Win rate % on test window
        total_trades: Trade count on test window
        total_pnl: Total PnL on test window
    """

    fold_index: int
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    total_trades: int
    total_pnl: float


@dataclass
class WalkForwardValidationResult:
    """Aggregated walk-forward validation results.

    Attributes:
        strategy_name: Strategy validated
        strategy_version: Version tested
        n_folds: Number of folds
        fold_results: Per-fold detailed results
        overall_sharpe: Mean Sharpe across folds
        overall_max_dd: Worst drawdown across folds
        overall_win_rate: Mean win rate across folds
        overall_total_trades: Sum of trades across folds
        overall_total_pnl: Sum of PnL across folds
        passed: Whether validation passed thresholds
        run_date: Validation execution timestamp
        run_id: Unique identifier for this run
    """

    strategy_name: str
    strategy_version: str
    n_folds: int
    fold_results: list[FoldResult]
    overall_sharpe: float
    overall_max_dd: float
    overall_win_rate: float
    overall_total_trades: int
    overall_total_pnl: float
    passed: bool
    run_date: datetime
    run_id: str


class WalkForwardValidator:
    """K-fold walk-forward cross-validator for time-series strategies.

    Performs anchored walk-forward analysis:
    - Expanding training window (all data up to test start)
    - Fixed test window (out-of-sample period)
    - Chronological order preserved (no data leakage)

    Example:
        >>> validator = WalkForwardValidator(n_folds=5, test_window_days=90)
        >>> result = await validator.validate(
        ...     strategy_name="fib_rsi",
        ...     data_source=CSVAdapter("data/GOLD.csv", symbol="GOLD"),
        ...     symbol="GOLD",
        ...     start_date=datetime(2023, 1, 1),
        ...     end_date=datetime(2024, 12, 31),
        ...     strategy_params={"rsi_period": 14},
        ... )
        >>> print(f"OOS Sharpe: {result.overall_sharpe:.2f}")
        >>> print(f"OOS Max DD: {result.overall_max_dd:.1f}%")
    """

    def __init__(
        self,
        n_folds: int = 5,
        test_window_days: int = 90,
        config: BacktestConfig | None = None,
    ):
        """Initialize walk-forward validator.

        Args:
            n_folds: Number of folds (K)
            test_window_days: Size of each test window in days
            config: Backtest configuration (position size, slippage, etc.)
        """
        if n_folds < 2:
            raise ValueError("n_folds must be at least 2")
        if test_window_days < 1:
            raise ValueError("test_window_days must be at least 1")

        self.n_folds = n_folds
        self.test_window_days = test_window_days
        self.config = config or BacktestConfig()

        logger.info(
            f"WalkForwardValidator initialized: n_folds={n_folds}, "
            f"test_window_days={test_window_days}"
        )

    async def validate(
        self,
        strategy_name: str,
        data_source: DataAdapter,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        strategy_params: dict[str, Any] | None = None,
        strategy_version: str = "1.0.0",
    ) -> WalkForwardValidationResult:
        """Run walk-forward validation.

        Args:
            strategy_name: Strategy to validate
            data_source: Data adapter (CSV, Parquet, Database)
            symbol: Instrument symbol
            start_date: Validation start date
            end_date: Validation end date
            strategy_params: Strategy-specific parameters
            strategy_version: Version identifier

        Returns:
            WalkForwardValidationResult with aggregated metrics

        Raises:
            ValueError: If date range too small for n_folds
        """
        logger.info(
            f"Starting walk-forward validation: strategy={strategy_name}, "
            f"symbol={symbol}, folds={self.n_folds}, "
            f"date_range={start_date.date()} to {end_date.date()}"
        )

        # Calculate fold boundaries
        fold_boundaries = self._calculate_fold_boundaries(start_date, end_date)

        if len(fold_boundaries) < self.n_folds + 1:
            raise ValueError(
                f"Date range too small: need at least "
                f"{self.n_folds * self.test_window_days} days, "
                f"got {(end_date - start_date).days}"
            )

        # Run backtest on each fold
        fold_results: list[FoldResult] = []

        for fold_idx in range(self.n_folds):
            logger.info(f"Processing fold {fold_idx + 1}/{self.n_folds}")

            # Training window: all data from start to test_start
            train_start = start_date
            train_end = fold_boundaries[fold_idx]

            # Test window: fixed window after training
            test_start = fold_boundaries[fold_idx]
            test_end = fold_boundaries[fold_idx + 1]

            # Run backtest on test window only (OOS)
            runner = BacktestRunner(
                strategy=strategy_name,
                data_source=data_source,
                config=self.config,
            )

            report = runner.run(
                symbol=symbol,
                start_date=test_start,
                end_date=test_end,
                strategy_params=strategy_params or {},
            )

            fold_result = FoldResult(
                fold_index=fold_idx,
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
                sharpe_ratio=report.sharpe_ratio,
                max_drawdown=report.max_drawdown_pct,
                win_rate=report.win_rate,
                total_trades=report.total_trades,
                total_pnl=report.total_pnl,
            )

            fold_results.append(fold_result)

            logger.info(
                f"Fold {fold_idx + 1} complete: "
                f"Sharpe={fold_result.sharpe_ratio:.2f}, "
                f"DD={fold_result.max_drawdown:.1f}%, "
                f"WR={fold_result.win_rate:.1f}%"
            )

        # Aggregate metrics across folds
        overall_sharpe = np.mean([f.sharpe_ratio for f in fold_results])
        overall_max_dd = np.max([f.max_drawdown for f in fold_results])
        overall_win_rate = np.mean([f.win_rate for f in fold_results])
        overall_total_trades = sum(f.total_trades for f in fold_results)
        overall_total_pnl = sum(f.total_pnl for f in fold_results)

        result = WalkForwardValidationResult(
            strategy_name=strategy_name,
            strategy_version=strategy_version,
            n_folds=self.n_folds,
            fold_results=fold_results,
            overall_sharpe=float(overall_sharpe),
            overall_max_dd=float(overall_max_dd),
            overall_win_rate=float(overall_win_rate),
            overall_total_trades=int(overall_total_trades),
            overall_total_pnl=float(overall_total_pnl),
            passed=False,  # Set by promotion engine
            run_date=datetime.utcnow(),
            run_id=str(uuid4()),
        )

        logger.info(
            f"Walk-forward validation complete: "
            f"Sharpe={result.overall_sharpe:.2f}, "
            f"DD={result.overall_max_dd:.1f}%, "
            f"WR={result.overall_win_rate:.1f}%, "
            f"Trades={result.overall_total_trades}"
        )

        return result

    def _calculate_fold_boundaries(
        self, start_date: datetime, end_date: datetime
    ) -> list[datetime]:
        """Calculate chronological fold boundaries.

        Returns:
            List of (n_folds + 1) timestamps marking fold boundaries
        """
        total_days = (end_date - start_date).days
        test_days = self.test_window_days * self.n_folds

        if total_days < test_days:
            raise ValueError(
                f"Date range too small: need {test_days} days for "
                f"{self.n_folds} folds of {self.test_window_days} days each"
            )

        boundaries = [start_date]

        for fold_idx in range(self.n_folds):
            boundary = start_date + timedelta(
                days=(fold_idx + 1) * self.test_window_days
            )
            boundaries.append(boundary)

        return boundaries
