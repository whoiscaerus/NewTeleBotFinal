"""Tests for promotion pipeline.

Validates:
- Threshold enforcement (pass/fail gates)
- Status transitions (development → backtest → paper → live)
- Rejection paths (failed validation blocks promotion)
- Audit trail (promotion_history records)
"""

from datetime import datetime, timedelta

import pytest

from backend.app.research.models import StrategyMetadata, StrategyStatus
from backend.app.research.promotion import PromotionEngine
from backend.app.research.walkforward import WalkForwardValidationResult


@pytest.fixture
def promotion_engine():
    """PromotionEngine with default thresholds."""
    return PromotionEngine(
        min_sharpe=1.0,
        max_drawdown=15.0,
        min_win_rate=55.0,
        min_trades=30,
        min_paper_days=30,
        min_paper_trades=20,
    )


@pytest.fixture
def sample_validation_result():
    """Good validation result that passes thresholds."""
    return WalkForwardValidationResult(
        strategy_name="test_strategy",
        strategy_version="1.0",
        n_folds=5,
        fold_results=[],
        overall_sharpe=1.5,
        overall_max_dd=10.0,
        overall_win_rate=60.0,
        overall_total_trades=50,
        overall_total_pnl=1000.0,
        passed=False,
        run_date=datetime.utcnow(),
        run_id="test_run_123",
    )


@pytest.fixture
async def sample_strategy_metadata(db_session):
    """Strategy in development status."""
    strategy = StrategyMetadata(
        name="test_strategy",
        status=StrategyStatus.development,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        promotion_history=[],
    )
    db_session.add(strategy)
    await db_session.commit()
    await db_session.refresh(strategy)
    return strategy


class TestThresholdEvaluation:
    """Test threshold checking."""

    def test_check_thresholds_pass_all(self, promotion_engine):
        """Test good metrics → pass."""
        result = WalkForwardValidationResult(
            strategy_name="test",
            strategy_version="1.0",
            n_folds=5,
            fold_results=[],
            overall_sharpe=1.5,
            overall_max_dd=10.0,
            overall_win_rate=60.0,
            overall_total_trades=50,
            overall_total_pnl=1000.0,
            passed=False,
            run_date=datetime.utcnow(),
            run_id="test",
        )

        passed = promotion_engine._check_backtest_thresholds(result)
        assert passed is True

    def test_check_thresholds_fail_sharpe(self, promotion_engine):
        """Test Sharpe < min → fail."""
        result = WalkForwardValidationResult(
            strategy_name="test",
            strategy_version="1.0",
            n_folds=5,
            fold_results=[],
            overall_sharpe=0.8,  # Below 1.0
            overall_max_dd=10.0,
            overall_win_rate=60.0,
            overall_total_trades=50,
            overall_total_pnl=1000.0,
            passed=False,
            run_date=datetime.utcnow(),
            run_id="test",
        )

        passed = promotion_engine._check_backtest_thresholds(result)
        assert passed is False

    def test_check_thresholds_fail_drawdown(self, promotion_engine):
        """Test DD > max → fail."""
        result = WalkForwardValidationResult(
            strategy_name="test",
            strategy_version="1.0",
            n_folds=5,
            fold_results=[],
            overall_sharpe=1.5,
            overall_max_dd=20.0,  # Above 15.0
            overall_win_rate=60.0,
            overall_total_trades=50,
            overall_total_pnl=1000.0,
            passed=False,
            run_date=datetime.utcnow(),
            run_id="test",
        )

        passed = promotion_engine._check_backtest_thresholds(result)
        assert passed is False

    def test_check_thresholds_fail_win_rate(self, promotion_engine):
        """Test WR < min → fail."""
        result = WalkForwardValidationResult(
            strategy_name="test",
            strategy_version="1.0",
            n_folds=5,
            fold_results=[],
            overall_sharpe=1.5,
            overall_max_dd=10.0,
            overall_win_rate=50.0,  # Below 55.0
            overall_total_trades=50,
            overall_total_pnl=1000.0,
            passed=False,
            run_date=datetime.utcnow(),
            run_id="test",
        )

        passed = promotion_engine._check_backtest_thresholds(result)
        assert passed is False

    def test_check_thresholds_fail_trades(self, promotion_engine):
        """Test trades < min → fail."""
        result = WalkForwardValidationResult(
            strategy_name="test",
            strategy_version="1.0",
            n_folds=5,
            fold_results=[],
            overall_sharpe=1.5,
            overall_max_dd=10.0,
            overall_win_rate=60.0,
            overall_total_trades=20,  # Below 30
            overall_total_pnl=1000.0,
            passed=False,
            run_date=datetime.utcnow(),
            run_id="test",
        )

        passed = promotion_engine._check_backtest_thresholds(result)
        assert passed is False

    def test_get_rejection_reason_multiple(self, promotion_engine):
        """Test rejection reason includes all failures."""
        result = WalkForwardValidationResult(
            strategy_name="test",
            strategy_version="1.0",
            n_folds=5,
            fold_results=[],
            overall_sharpe=0.8,  # Fail
            overall_max_dd=20.0,  # Fail
            overall_win_rate=50.0,  # Fail
            overall_total_trades=20,  # Fail
            overall_total_pnl=1000.0,
            passed=False,
            run_date=datetime.utcnow(),
            run_id="test",
        )

        reason = promotion_engine._get_rejection_reason(result)

        assert "Sharpe" in reason
        assert "Max DD" in reason
        assert "Win rate" in reason
        assert "Trades" in reason


class TestPromotionToBacktest:
    """Test development → backtest promotion."""

    @pytest.mark.asyncio
    async def test_promote_pass_updates_status(
        self,
        promotion_engine,
        sample_strategy_metadata,
        sample_validation_result,
        db_session,
    ):
        """Test validation pass → status=backtest."""
        success = await promotion_engine.promote_to_backtest(
            strategy_name="test_strategy",
            validation_result=sample_validation_result,
            db_session=db_session,
        )

        assert success is True

        # Reload strategy
        await db_session.refresh(sample_strategy_metadata)

        assert sample_strategy_metadata.status == StrategyStatus.backtest

    @pytest.mark.asyncio
    async def test_promote_updates_metrics(
        self,
        promotion_engine,
        sample_strategy_metadata,
        sample_validation_result,
        db_session,
    ):
        """Test backtest_sharpe, backtest_max_dd updated."""
        await promotion_engine.promote_to_backtest(
            strategy_name="test_strategy",
            validation_result=sample_validation_result,
            db_session=db_session,
        )

        await db_session.refresh(sample_strategy_metadata)

        assert sample_strategy_metadata.backtest_sharpe == 1.5
        assert sample_strategy_metadata.backtest_max_dd == 10.0
        assert sample_strategy_metadata.backtest_win_rate == 60.0
        assert sample_strategy_metadata.backtest_total_trades == 50

    @pytest.mark.asyncio
    async def test_promote_records_audit(
        self,
        promotion_engine,
        sample_strategy_metadata,
        sample_validation_result,
        db_session,
    ):
        """Test promotion_history appended."""
        await promotion_engine.promote_to_backtest(
            strategy_name="test_strategy",
            validation_result=sample_validation_result,
            db_session=db_session,
        )

        await db_session.refresh(sample_strategy_metadata)

        assert len(sample_strategy_metadata.promotion_history) == 1

        record = sample_strategy_metadata.promotion_history[0]
        assert record["from_status"] == "development"
        assert record["to_status"] == "backtest"
        assert record["result"] == "approved"
        assert record["metrics"]["sharpe"] == 1.5
        assert record["run_id"] == "test_run_123"

    @pytest.mark.asyncio
    async def test_reject_does_not_change_status(
        self, promotion_engine, sample_strategy_metadata, db_session
    ):
        """Test failed validation → status unchanged."""
        bad_result = WalkForwardValidationResult(
            strategy_name="test_strategy",
            strategy_version="1.0",
            n_folds=5,
            fold_results=[],
            overall_sharpe=0.5,  # Too low
            overall_max_dd=10.0,
            overall_win_rate=60.0,
            overall_total_trades=50,
            overall_total_pnl=1000.0,
            passed=False,
            run_date=datetime.utcnow(),
            run_id="test_run_123",
        )

        success = await promotion_engine.promote_to_backtest(
            strategy_name="test_strategy",
            validation_result=bad_result,
            db_session=db_session,
        )

        assert success is False

        await db_session.refresh(sample_strategy_metadata)

        assert sample_strategy_metadata.status == StrategyStatus.development

    @pytest.mark.asyncio
    async def test_reject_records_reasons(
        self, promotion_engine, sample_strategy_metadata, db_session
    ):
        """Test failure reasons in promotion_history."""
        bad_result = WalkForwardValidationResult(
            strategy_name="test_strategy",
            strategy_version="1.0",
            n_folds=5,
            fold_results=[],
            overall_sharpe=0.5,
            overall_max_dd=20.0,
            overall_win_rate=50.0,
            overall_total_trades=20,
            overall_total_pnl=1000.0,
            passed=False,
            run_date=datetime.utcnow(),
            run_id="test_run_123",
        )

        await promotion_engine.promote_to_backtest(
            strategy_name="test_strategy",
            validation_result=bad_result,
            db_session=db_session,
        )

        await db_session.refresh(sample_strategy_metadata)

        assert len(sample_strategy_metadata.promotion_history) == 1

        record = sample_strategy_metadata.promotion_history[0]
        assert record["result"] == "rejected"
        assert "Sharpe" in record["reason"]
        assert "Max DD" in record["reason"]


class TestPromotionToPaper:
    """Test backtest → paper promotion."""

    @pytest.mark.asyncio
    async def test_promote_to_paper_updates_status(self, promotion_engine, db_session):
        """Test manual approval → status=paper."""
        strategy = StrategyMetadata(
            name="test_strategy",
            status=StrategyStatus.backtest,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            promotion_history=[],
        )
        db_session.add(strategy)
        await db_session.commit()

        success = await promotion_engine.promote_to_paper(
            strategy_name="test_strategy",
            db_session=db_session,
        )

        assert success is True

        await db_session.refresh(strategy)

        assert strategy.status == StrategyStatus.paper
        assert strategy.paper_start_date is not None

    @pytest.mark.asyncio
    async def test_promote_to_paper_wrong_status(
        self, promotion_engine, sample_strategy_metadata, db_session
    ):
        """Test raises ValueError if not in backtest status."""
        with pytest.raises(ValueError, match="expected backtest"):
            await promotion_engine.promote_to_paper(
                strategy_name="test_strategy",
                db_session=db_session,
            )


class TestPromotionToLive:
    """Test paper → live promotion."""

    @pytest.mark.asyncio
    async def test_promote_to_live_pass_requirements(
        self, promotion_engine, db_session
    ):
        """Test paper days/trades met → status=live."""
        strategy = StrategyMetadata(
            name="test_strategy",
            status=StrategyStatus.paper,
            paper_start_date=datetime.utcnow() - timedelta(days=35),
            paper_trade_count=25,
            paper_pnl=500.0,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            promotion_history=[],
        )
        db_session.add(strategy)
        await db_session.commit()

        success = await promotion_engine.promote_to_live(
            strategy_name="test_strategy",
            db_session=db_session,
        )

        assert success is True

        await db_session.refresh(strategy)

        assert strategy.status == StrategyStatus.live
        assert strategy.paper_end_date is not None
        assert strategy.live_start_date is not None

    @pytest.mark.asyncio
    async def test_promote_to_live_insufficient_days(
        self, promotion_engine, db_session
    ):
        """Test paper days < min → rejected."""
        strategy = StrategyMetadata(
            name="test_strategy",
            status=StrategyStatus.paper,
            paper_start_date=datetime.utcnow() - timedelta(days=15),  # Too short
            paper_trade_count=25,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            promotion_history=[],
        )
        db_session.add(strategy)
        await db_session.commit()

        success = await promotion_engine.promote_to_live(
            strategy_name="test_strategy",
            db_session=db_session,
        )

        assert success is False

        await db_session.refresh(strategy)

        assert strategy.status == StrategyStatus.paper  # Unchanged

    @pytest.mark.asyncio
    async def test_promote_to_live_insufficient_trades(
        self, promotion_engine, db_session
    ):
        """Test paper trades < min → rejected."""
        strategy = StrategyMetadata(
            name="test_strategy",
            status=StrategyStatus.paper,
            paper_start_date=datetime.utcnow() - timedelta(days=35),
            paper_trade_count=10,  # Too few
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            promotion_history=[],
        )
        db_session.add(strategy)
        await db_session.commit()

        success = await promotion_engine.promote_to_live(
            strategy_name="test_strategy",
            db_session=db_session,
        )

        assert success is False


class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_promote_missing_strategy(
        self, promotion_engine, sample_validation_result, db_session
    ):
        """Test ValueError on unknown strategy."""
        with pytest.raises(ValueError, match="not found"):
            await promotion_engine.promote_to_backtest(
                strategy_name="nonexistent",
                validation_result=sample_validation_result,
                db_session=db_session,
            )

    @pytest.mark.asyncio
    async def test_promote_already_promoted(
        self, promotion_engine, sample_validation_result, db_session
    ):
        """Test cannot promote strategy already in backtest."""
        strategy = StrategyMetadata(
            name="test_strategy",
            status=StrategyStatus.backtest,  # Already promoted
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            promotion_history=[],
        )
        db_session.add(strategy)
        await db_session.commit()

        with pytest.raises(ValueError, match="expected development"):
            await promotion_engine.promote_to_backtest(
                strategy_name="test_strategy",
                validation_result=sample_validation_result,
                db_session=db_session,
            )

    @pytest.mark.asyncio
    async def test_multiple_promotion_attempts(
        self, promotion_engine, sample_strategy_metadata, db_session
    ):
        """Test multiple promotion attempts recorded."""
        # First attempt (fail)
        bad_result = WalkForwardValidationResult(
            strategy_name="test_strategy",
            strategy_version="1.0",
            n_folds=5,
            fold_results=[],
            overall_sharpe=0.5,
            overall_max_dd=10.0,
            overall_win_rate=60.0,
            overall_total_trades=50,
            overall_total_pnl=1000.0,
            passed=False,
            run_date=datetime.utcnow(),
            run_id="run1",
        )

        await promotion_engine.promote_to_backtest(
            strategy_name="test_strategy",
            validation_result=bad_result,
            db_session=db_session,
        )

        # Second attempt (pass)
        good_result = WalkForwardValidationResult(
            strategy_name="test_strategy",
            strategy_version="1.0",
            n_folds=5,
            fold_results=[],
            overall_sharpe=1.5,
            overall_max_dd=10.0,
            overall_win_rate=60.0,
            overall_total_trades=50,
            overall_total_pnl=1000.0,
            passed=False,
            run_date=datetime.utcnow(),
            run_id="run2",
        )

        await promotion_engine.promote_to_backtest(
            strategy_name="test_strategy",
            validation_result=good_result,
            db_session=db_session,
        )

        await db_session.refresh(sample_strategy_metadata)

        assert len(sample_strategy_metadata.promotion_history) == 2
        assert sample_strategy_metadata.promotion_history[0]["result"] == "rejected"
        assert sample_strategy_metadata.promotion_history[1]["result"] == "approved"
