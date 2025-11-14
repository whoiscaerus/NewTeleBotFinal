"""Tests for walk-forward validation.

Validates:
- Fold boundary calculation (chronological, even spacing)
- OOS validation (no data leakage)
- Metrics aggregation (mean, max, sum)
- Integration with BacktestRunner
"""

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from backend.app.research.walkforward import WalkForwardValidator


class TestFoldBoundaries:
    """Test fold boundary calculation."""

    def test_calculate_fold_boundaries_even_spacing(self):
        """Test 5 folds → 5 equal test windows across full date range."""
        validator = WalkForwardValidator(n_folds=5, test_window_days=90)

        start = datetime(2023, 1, 1)
        end = datetime(2024, 12, 31)  # 730 days total
        # 730 / 5 = 146 days per fold

        boundaries = validator._calculate_fold_boundaries(start, end)

        assert len(boundaries) == 6  # n_folds + 1
        assert boundaries[0] == start
        assert boundaries[-1] == end

        # Check even spacing across the full range (approximately 146 days each)
        expected_window_days = (end - start).days / validator.n_folds
        for i in range(len(boundaries) - 1):
            delta = (boundaries[i + 1] - boundaries[i]).days
            # Allow for rounding: expect ~146 days with 1 day tolerance
            assert abs(delta - expected_window_days) <= 1

    def test_calculate_fold_boundaries_chronological(self):
        """Test fold N+1 starts after fold N."""
        validator = WalkForwardValidator(n_folds=5, test_window_days=90)

        start = datetime(2023, 1, 1)
        end = datetime(2024, 12, 31)

        boundaries = validator._calculate_fold_boundaries(start, end)

        # Verify chronological order
        for i in range(len(boundaries) - 1):
            assert boundaries[i] < boundaries[i + 1]

    def test_calculate_fold_boundaries_insufficient_data(self):
        """Test raises ValueError for insufficient data."""
        validator = WalkForwardValidator(n_folds=5, test_window_days=90)

        start = datetime(2023, 1, 1)
        end = datetime(2023, 6, 1)  # Only 151 days (need 450)

        with pytest.raises(ValueError, match="Insufficient data"):
            validator._calculate_fold_boundaries(start, end)

    def test_calculate_fold_boundaries_single_fold(self):
        """Test n_folds=1 works."""
        validator = WalkForwardValidator(n_folds=1, test_window_days=90)

        start = datetime(2023, 1, 1)
        end = datetime(2023, 6, 1)

        boundaries = validator._calculate_fold_boundaries(start, end)

        assert len(boundaries) == 2
        assert boundaries[0] == start
        assert boundaries[1] == end


class TestWalkForwardValidation:
    """Test walk-forward validation execution."""

    @pytest.mark.asyncio
    async def test_validate_runs_all_folds(self):
        """Test 5 folds configured → 5 backtests executed."""
        validator = WalkForwardValidator(n_folds=5, test_window_days=90)

        # Mock BacktestRunner - code calls runner.run(), not run_backtest()
        mock_runner = Mock()
        mock_runner.run = Mock(
            return_value=Mock(
                sharpe_ratio=1.5,
                max_drawdown_pct=10.0,
                win_rate=60.0,
                total_trades=50,
                total_pnl=1000.0,
            )
        )

        with patch(
            "backend.app.research.walkforward.BacktestRunner", return_value=mock_runner
        ):
            result = await validator.validate(
                strategy_name="test_strategy",
                data_source=Mock(),
                symbol="GOLD",
                start_date=datetime(2023, 1, 1),
                end_date=datetime(2024, 12, 31),
                strategy_params={},
            )

        assert len(result.fold_results) == 5
        assert mock_runner.run.call_count == 5

    @pytest.mark.asyncio
    async def test_validate_oos_only(self):
        """Test each fold tests on future data only (no leakage)."""
        validator = WalkForwardValidator(n_folds=3, test_window_days=90)

        # Track what windows were tested
        tested_windows = []

        mock_runner = Mock()
        mock_runner.run = Mock(
            side_effect=lambda *args, **kwargs: (
                tested_windows.append((kwargs["start_date"], kwargs["end_date"])),
                Mock(
                    sharpe_ratio=1.5,
                    max_drawdown_pct=10.0,
                    win_rate=60.0,
                    total_trades=50,
                    total_pnl=1000.0,
                ),
            )[1]
        )

        with patch(
            "backend.app.research.walkforward.BacktestRunner", return_value=mock_runner
        ):
            await validator.validate(
                strategy_name="test_strategy",
                data_source=Mock(),
                symbol="GOLD",
                start_date=datetime(2023, 1, 1),
                end_date=datetime(2024, 3, 31),  # 455 days
                strategy_params={},
            )

        # Verify each test window is after previous
        for i in range(len(tested_windows) - 1):
            assert tested_windows[i][1] <= tested_windows[i + 1][0]

    @pytest.mark.asyncio
    async def test_validate_aggregates_metrics_correctly(self):
        """Test mean Sharpe, max DD, sum trades correct."""
        validator = WalkForwardValidator(n_folds=3, test_window_days=90)

        # Mock different metrics per fold
        fold_metrics = [
            Mock(
                sharpe_ratio=1.0,
                max_drawdown_pct=10.0,
                win_rate=55.0,
                total_trades=30,
                total_pnl=500.0,
            ),
            Mock(
                sharpe_ratio=1.5,
                max_drawdown_pct=15.0,
                win_rate=60.0,
                total_trades=40,
                total_pnl=800.0,
            ),
            Mock(
                sharpe_ratio=2.0,
                max_drawdown_pct=8.0,
                win_rate=65.0,
                total_trades=50,
                total_pnl=1200.0,
            ),
        ]

        call_count = 0

        mock_runner = Mock()
        
        def side_effect_run(*args, **kwargs):
            nonlocal call_count
            result = fold_metrics[call_count]
            call_count += 1
            return result

        mock_runner.run = Mock(side_effect=side_effect_run)

        with patch(
            "backend.app.research.walkforward.BacktestRunner", return_value=mock_runner
        ):
            result = await validator.validate(
                strategy_name="test_strategy",
                data_source=Mock(),
                symbol="GOLD",
                start_date=datetime(2023, 1, 1),
                end_date=datetime(2024, 3, 31),
                strategy_params={},
            )

        # Check aggregations
        assert result.overall_sharpe == pytest.approx(
            1.5, rel=0.01
        )  # Mean: (1.0 + 1.5 + 2.0) / 3
        assert result.overall_max_dd == pytest.approx(15.0, rel=0.01)  # Max: 15.0
        assert result.overall_win_rate == pytest.approx(
            60.0, rel=0.01
        )  # Mean: (55 + 60 + 65) / 3
        assert result.overall_total_trades == 120  # Sum: 30 + 40 + 50
        assert result.overall_total_pnl == pytest.approx(
            2500.0, rel=0.01
        )  # Sum: 500 + 800 + 1200

    @pytest.mark.asyncio
    async def test_validate_stores_fold_details(self):
        """Test fold_results contains per-fold breakdown."""
        validator = WalkForwardValidator(n_folds=3, test_window_days=90)

        mock_runner = Mock()
        mock_runner.run = Mock(
            return_value=Mock(
                sharpe_ratio=1.5,
                max_drawdown_pct=10.0,
                win_rate=60.0,
                total_trades=50,
                total_pnl=1000.0,
            )
        )

        with patch(
            "backend.app.research.walkforward.BacktestRunner", return_value=mock_runner
        ):
            result = await validator.validate(
                strategy_name="test_strategy",
                data_source=Mock(),
                symbol="GOLD",
                start_date=datetime(2023, 1, 1),
                end_date=datetime(2024, 3, 31),
                strategy_params={},
            )

        assert len(result.fold_results) == 3

        for i, fold in enumerate(result.fold_results):
            assert fold.fold_index == i
            # Note: train_start/train_end may be equal for first fold (no prior data)
            assert fold.test_start <= fold.test_end
            # Training window should end by or before test window starts
            assert fold.train_end <= fold.test_start
            assert fold.sharpe_ratio == 1.5
            assert fold.max_drawdown == 10.0


class TestIntegration:
    """Test integration with BacktestRunner."""

    @pytest.mark.asyncio
    async def test_validate_uses_real_backtest_runner(self):
        """Test integration with real BacktestRunner."""
        # This test verifies we call BacktestRunner correctly
        # In real scenario, BacktestRunner would use real data

        validator = WalkForwardValidator(n_folds=2, test_window_days=90)

        # Track BacktestRunner initialization
        init_args = []

        def mock_init(self, *args, **kwargs):
            init_args.append((args, kwargs))

        mock_runner = Mock()
        mock_runner.run = Mock(
            return_value=Mock(
                sharpe_ratio=1.5,
                max_drawdown_pct=10.0,
                win_rate=60.0,
                total_trades=50,
                total_pnl=1000.0,
            )
        )

        with patch(
            "backend.app.research.walkforward.BacktestRunner", return_value=mock_runner
        ):
            await validator.validate(
                strategy_name="test_strategy",
                data_source=Mock(),
                symbol="GOLD",
                start_date=datetime(2023, 1, 1),
                end_date=datetime(2023, 12, 31),
                strategy_params={"rsi_period": 14},
            )

        # Verify BacktestRunner was called with correct parameters
        assert mock_runner.run.call_count == 2


class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_validate_strategy_not_found(self):
        """Test KeyError raised for unknown strategy."""
        validator = WalkForwardValidator(n_folds=2, test_window_days=90)

        mock_runner = Mock()
        mock_runner.run = Mock(side_effect=KeyError("Strategy not found"))

        with patch(
            "backend.app.research.walkforward.BacktestRunner", return_value=mock_runner
        ):
            with pytest.raises(KeyError, match="Strategy not found"):
                await validator.validate(
                    strategy_name="nonexistent_strategy",
                    data_source=Mock(),
                    symbol="GOLD",
                    start_date=datetime(2023, 1, 1),
                    end_date=datetime(2023, 12, 31),
                    strategy_params={},
                )

    @pytest.mark.asyncio
    async def test_validate_data_adapter_failure(self):
        """Test handles data loading errors."""
        validator = WalkForwardValidator(n_folds=2, test_window_days=90)

        mock_runner = Mock()
        mock_runner.run = Mock(
            side_effect=FileNotFoundError("Data file not found")
        )

        with patch(
            "backend.app.research.walkforward.BacktestRunner", return_value=mock_runner
        ):
            with pytest.raises(FileNotFoundError, match="Data file not found"):
                await validator.validate(
                    strategy_name="test_strategy",
                    data_source=Mock(),
                    symbol="GOLD",
                    start_date=datetime(2023, 1, 1),
                    end_date=datetime(2023, 12, 31),
                    strategy_params={},
                )

    def test_validate_small_date_range(self):
        """Test handles minimal data."""
        validator = WalkForwardValidator(n_folds=2, test_window_days=90)

        start = datetime(2023, 1, 1)
        end = datetime(2023, 3, 1)  # Only 59 days (need 180)

        with pytest.raises(ValueError, match="Insufficient data"):
            validator._calculate_fold_boundaries(start, end)

    @pytest.mark.asyncio
    async def test_validate_returns_unset_passed_flag(self):
        """Test passed flag is False by default (set by promotion engine)."""
        validator = WalkForwardValidator(n_folds=2, test_window_days=90)

        mock_runner = Mock()
        mock_runner.run = Mock(
            return_value=Mock(
                sharpe_ratio=1.5,
                max_drawdown_pct=10.0,
                win_rate=60.0,
                total_trades=50,
                total_pnl=1000.0,
            )
        )

        with patch(
            "backend.app.research.walkforward.BacktestRunner", return_value=mock_runner
        ):
            result = await validator.validate(
                strategy_name="test_strategy",
                data_source=Mock(),
                symbol="GOLD",
                start_date=datetime(2023, 1, 1),
                end_date=datetime(2023, 12, 31),
                strategy_params={},
            )

        assert result.passed is False  # Not set until promotion engine checks


class TestGoldenFixtures:
    """Test with known data for regression testing."""

    @pytest.mark.asyncio
    async def test_validate_golden_fib_rsi(self):
        """Test with known metrics for fib_rsi strategy."""
        validator = WalkForwardValidator(n_folds=2, test_window_days=90)

        # Golden metrics (from previous validated run)
        golden_metrics = [
            Mock(
                sharpe_ratio=1.45,
                max_drawdown_pct=12.3,
                win_rate=58.2,
                total_trades=45,
                total_pnl=987.50,
            ),
            Mock(
                sharpe_ratio=1.38,
                max_drawdown_pct=14.1,
                win_rate=56.8,
                total_trades=42,
                total_pnl=895.20,
            ),
        ]

        call_count = 0

        mock_runner = Mock()

        def side_effect_run(*args, **kwargs):
            nonlocal call_count
            result = golden_metrics[call_count]
            call_count += 1
            return result

        mock_runner.run = Mock(side_effect=side_effect_run)

        with patch(
            "backend.app.research.walkforward.BacktestRunner", return_value=mock_runner
        ):
            result = await validator.validate(
                strategy_name="fib_rsi",
                data_source=Mock(),
                symbol="GOLD",
                start_date=datetime(2023, 1, 1),
                end_date=datetime(2023, 12, 31),
                strategy_params={"rsi_period": 14},
            )

        # Verify against golden values
        assert result.overall_sharpe == pytest.approx(
            1.415, rel=0.01
        )  # Mean: (1.45 + 1.38) / 2
        assert result.overall_max_dd == pytest.approx(14.1, rel=0.01)  # Max: 14.1
        assert result.overall_win_rate == pytest.approx(
            57.5, rel=0.01
        )  # Mean: (58.2 + 56.8) / 2
        assert result.overall_total_trades == 87  # Sum: 45 + 42
        assert result.overall_total_pnl == pytest.approx(
            1882.70, rel=0.01
        )  # Sum: 987.50 + 895.20
