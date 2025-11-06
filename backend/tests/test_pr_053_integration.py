"""
Integration tests for PR-053: Performance Metrics (Sharpe, Sortino, Calmar, Profit Factor).

Tests the full workflow with real database data and validates business logic.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from backend.app.analytics.metrics import PerformanceMetrics
from backend.app.analytics.models import DimDay, DimSymbol, EquityCurve, TradesFact


@pytest.mark.asyncio
class TestPerformanceMetricsIntegration:
    """Integration tests for metrics service with real database."""

    async def test_get_daily_returns_with_real_data(self, db_session, test_user):
        """Test get_daily_returns() with database equity curve data."""
        # Create dimension data
        symbol = DimSymbol(id=1, symbol="GOLD", description="Gold")
        db_session.add(symbol)

        # Create 10 days of equity data
        start_date = date(2025, 1, 1)
        equity_values = [
            Decimal("10000.00"),  # Day 0
            Decimal("10100.00"),  # Day 1: +1%
            Decimal("10050.00"),  # Day 2: -0.495%
            Decimal("10200.00"),  # Day 3: +1.493%
            Decimal("10150.00"),  # Day 4: -0.490%
            Decimal("10300.00"),  # Day 5: +1.478%
            Decimal("10250.00"),  # Day 6: -0.485%
            Decimal("10400.00"),  # Day 7: +1.463%
            Decimal("10350.00"),  # Day 8: -0.481%
            Decimal("10500.00"),  # Day 9: +1.449%
        ]

        for i, equity in enumerate(equity_values):
            day = DimDay(
                date=start_date + timedelta(days=i),
                year=2025,
                month=1,
                day_of_week=((start_date + timedelta(days=i)).weekday() + 1) % 7,
                week_of_year=1,
                is_trading_day=1,
                created_at=datetime.utcnow(),
            )
            db_session.add(day)
            await db_session.flush()  # Get the generated ID

            curve = EquityCurve(
                id=str(uuid4()),
                user_id=test_user.id,
                date=start_date + timedelta(days=i),
                equity=equity,
                peak_equity=max(equity_values[: i + 1]),  # Track peak
                daily_change=equity - equity_values[i - 1] if i > 0 else Decimal("0"),
                created_at=datetime.utcnow(),
            )
            db_session.add(curve)

        await db_session.commit()

        # Test get_daily_returns
        metrics = PerformanceMetrics(db_session)
        returns = await metrics.get_daily_returns(
            test_user.id, start_date, start_date + timedelta(days=9)
        )

        # Should have 9 returns (10 days = 9 daily changes)
        assert len(returns) == 9

        # Verify first return: (10100 - 10000) / 10000 = 0.01 (1%)
        assert abs(returns[0] - Decimal("0.01")) < Decimal("0.0001")

        # Verify second return: (10050 - 10100) / 10100 ≈ -0.00495 (-0.495%)
        assert abs(returns[1] - Decimal("-0.00495")) < Decimal("0.00001")

    async def test_sharpe_ratio_calculation_real_data(self, db_session, test_user):
        """Test Sharpe ratio with real database data."""
        # Create consistent upward trend (positive Sharpe)
        start_date = date(2025, 1, 1)
        equity_values = [
            Decimal("10000"),
            Decimal("10100"),  # +1%
            Decimal("10200"),  # +0.99%
            Decimal("10300"),  # +0.98%
            Decimal("10400"),  # +0.97%
        ]

        for i, equity in enumerate(equity_values):
            day = DimDay(
                id=i + 100,
                date=start_date + timedelta(days=i),
                year=2025,
                month=1,
                day=start_date.day + i,
                day_of_week=0,
                is_weekend=0,
            )
            db_session.add(day)

            curve = EquityCurve(
                id=str(uuid4()),
                user_id=test_user.id,
                date=start_date + timedelta(days=i),
                equity=equity,
                peak_equity=equity,  # Always increasing
                daily_change=equity - equity_values[i - 1] if i > 0 else Decimal("0"),
                created_at=datetime.utcnow(),
            )
            db_session.add(curve)

        await db_session.commit()

        # Calculate Sharpe ratio
        metrics = PerformanceMetrics(db_session)
        sharpe = await metrics.calculate_sharpe_ratio(
            test_user.id,
            start_date,
            start_date + timedelta(days=4),
            risk_free_rate=Decimal("0.02"),
        )

        # Sharpe should be positive (consistent gains)
        assert sharpe > 0
        # With consistent ~1% daily returns, Sharpe should be high
        assert sharpe > 5.0  # Very good Sharpe ratio

    async def test_sortino_ratio_vs_sharpe(self, db_session, test_user):
        """Test Sortino ratio focuses only on downside volatility."""
        # Create pattern: big gains, small losses (Sortino > Sharpe)
        start_date = date(2025, 2, 1)
        equity_values = [
            Decimal("10000"),
            Decimal("10500"),  # +5% (big gain)
            Decimal("10450"),  # -0.95% (small loss)
            Decimal("10900"),  # +4.31% (big gain)
            Decimal("10850"),  # -0.46% (small loss)
        ]

        for i, equity in enumerate(equity_values):
            day = DimDay(
                id=i + 200,
                date=start_date + timedelta(days=i),
                year=2025,
                month=2,
                day=start_date.day + i,
                day_of_week=0,
                is_weekend=0,
            )
            db_session.add(day)

            curve = EquityCurve(
                id=str(uuid4()),
                user_id=test_user.id,
                date=start_date + timedelta(days=i),
                equity=equity,
                peak_equity=max(equity_values[: i + 1]),
                daily_change=equity - equity_values[i - 1] if i > 0 else Decimal("0"),
                created_at=datetime.utcnow(),
            )
            db_session.add(curve)

        await db_session.commit()

        # Calculate both ratios
        metrics = PerformanceMetrics(db_session)
        sharpe = await metrics.calculate_sharpe_ratio(
            test_user.id, start_date, start_date + timedelta(days=4)
        )
        sortino = await metrics.calculate_sortino_ratio(
            test_user.id, start_date, start_date + timedelta(days=4)
        )

        # Both should be positive
        assert sharpe > 0
        assert sortino > 0
        # Sortino should be higher (only penalizes downside)
        assert sortino > sharpe

    async def test_calmar_ratio_calculation(self, db_session, test_user):
        """Test Calmar ratio (return / max drawdown)."""
        # Create pattern with significant drawdown
        start_date = date(2025, 3, 1)
        equity_values = [
            Decimal("10000"),
            Decimal("11000"),  # +10% (peak)
            Decimal("10000"),  # -9.09% (drawdown)
            Decimal("12000"),  # +20% (recovery + gain)
        ]

        for i, equity in enumerate(equity_values):
            day = DimDay(
                id=i + 300,
                date=start_date + timedelta(days=i),
                year=2025,
                month=3,
                day=start_date.day + i,
                day_of_week=0,
                is_weekend=0,
            )
            db_session.add(day)

            curve = EquityCurve(
                id=str(uuid4()),
                user_id=test_user.id,
                date=start_date + timedelta(days=i),
                equity=equity,
                peak_equity=max(equity_values[: i + 1]),
                daily_change=equity - equity_values[i - 1] if i > 0 else Decimal("0"),
                created_at=datetime.utcnow(),
            )
            db_session.add(curve)

        await db_session.commit()

        # Calculate Calmar ratio
        metrics = PerformanceMetrics(db_session)
        calmar = await metrics.calculate_calmar_ratio(
            test_user.id, start_date, start_date + timedelta(days=3)
        )

        # Total return: (12000 - 10000) / 10000 = 20%
        # Max drawdown: (11000 - 10000) / 11000 = 9.09%
        # Calmar = 20% / 9.09% ≈ 2.2
        assert calmar > 0
        assert abs(calmar - Decimal("2.2")) < Decimal("0.3")

    async def test_profit_factor_calculation(self, db_session, test_user):
        """Test profit factor (gross profit / gross loss)."""
        # Create trades with known profit/loss
        symbol = DimSymbol(id=2, symbol="EURUSD", description="EUR/USD")
        db_session.add(symbol)

        day1 = DimDay(
            id=401,
            date=date(2025, 4, 1),
            year=2025,
            month=4,
            day=1,
            day_of_week=0,
            is_weekend=0,
        )
        day2 = DimDay(
            id=402,
            date=date(2025, 4, 2),
            year=2025,
            month=4,
            day=2,
            day_of_week=1,
            is_weekend=0,
        )
        db_session.add_all([day1, day2])

        # Create trades: 2 winners, 1 loser
        trades = [
            # Winner: +100
            TradesFact(
                id=str(uuid4()),
                user_id=test_user.id,
                symbol_id=symbol.id,
                entry_date_id=day1.id,
                exit_date_id=day1.id,
                side=0,
                entry_price=Decimal("1.1000"),
                exit_price=Decimal("1.1100"),
                volume=Decimal("1.0"),
                gross_pnl=Decimal("100.00"),
                pnl_percent=Decimal("0.91"),
                commission=Decimal("5.00"),
                net_pnl=Decimal("95.00"),
                bars_held=10,
                winning_trade=1,
                risk_amount=Decimal("50.00"),
                max_run_up=Decimal("100.00"),
                max_drawdown=Decimal("0.00"),
                entry_time=datetime(2025, 4, 1, 10, 0),
                exit_time=datetime(2025, 4, 1, 14, 0),
                source="signal",
            ),
            # Winner: +200
            TradesFact(
                id=str(uuid4()),
                user_id=test_user.id,
                symbol_id=symbol.id,
                entry_date_id=day1.id,
                exit_date_id=day2.id,
                side=0,
                entry_price=Decimal("1.1000"),
                exit_price=Decimal("1.1200"),
                volume=Decimal("1.0"),
                gross_pnl=Decimal("200.00"),
                pnl_percent=Decimal("1.82"),
                commission=Decimal("5.00"),
                net_pnl=Decimal("195.00"),
                bars_held=20,
                winning_trade=1,
                risk_amount=Decimal("50.00"),
                max_run_up=Decimal("200.00"),
                max_drawdown=Decimal("0.00"),
                entry_time=datetime(2025, 4, 1, 10, 0),
                exit_time=datetime(2025, 4, 2, 10, 0),
                source="signal",
            ),
            # Loser: -50
            TradesFact(
                id=str(uuid4()),
                user_id=test_user.id,
                symbol_id=symbol.id,
                entry_date_id=day2.id,
                exit_date_id=day2.id,
                side=1,
                entry_price=Decimal("1.1000"),
                exit_price=Decimal("1.1050"),
                volume=Decimal("1.0"),
                gross_pnl=Decimal("-50.00"),
                pnl_percent=Decimal("-0.45"),
                commission=Decimal("5.00"),
                net_pnl=Decimal("-55.00"),
                bars_held=5,
                winning_trade=0,
                risk_amount=Decimal("50.00"),
                max_run_up=Decimal("0.00"),
                max_drawdown=Decimal("-50.00"),
                entry_time=datetime(2025, 4, 2, 11, 0),
                exit_time=datetime(2025, 4, 2, 12, 0),
                source="signal",
            ),
        ]
        db_session.add_all(trades)
        await db_session.commit()

        # Calculate profit factor
        metrics = PerformanceMetrics(db_session)
        profit_factor = await metrics.calculate_profit_factor(
            test_user.id, date(2025, 4, 1), date(2025, 4, 2)
        )

        # Gross profit = 100 + 200 = 300
        # Gross loss = 50
        # Profit factor = 300 / 50 = 6.0
        assert profit_factor is not None
        assert abs(profit_factor - Decimal("6.0")) < Decimal("0.1")

    async def test_recovery_factor_calculation(self, db_session, test_user):
        """Test recovery factor (total return / max drawdown)."""
        # Create equity curve with known return and drawdown
        start_date = date(2025, 5, 1)
        equity_values = [
            Decimal("10000"),  # Start
            Decimal("12000"),  # +20% (peak)
            Decimal("10800"),  # -10% drawdown from peak
            Decimal("13000"),  # Final: +30% total return
        ]

        for i, equity in enumerate(equity_values):
            day = DimDay(
                id=i + 500,
                date=start_date + timedelta(days=i),
                year=2025,
                month=5,
                day=start_date.day + i,
                day_of_week=0,
                is_weekend=0,
            )
            db_session.add(day)

            curve = EquityCurve(
                id=str(uuid4()),
                user_id=test_user.id,
                date=start_date + timedelta(days=i),
                equity=equity,
                peak_equity=max(equity_values[: i + 1]),
                daily_change=equity - equity_values[i - 1] if i > 0 else Decimal("0"),
                created_at=datetime.utcnow(),
            )
            db_session.add(curve)

        await db_session.commit()

        # Calculate recovery factor
        metrics = PerformanceMetrics(db_session)
        recovery = await metrics.calculate_recovery_factor(
            test_user.id, start_date, start_date + timedelta(days=3)
        )

        # Total return: (13000 - 10000) / 10000 = 30%
        # Max drawdown: (12000 - 10800) / 12000 = 10%
        # Recovery factor = 30% / 10% = 3.0
        assert recovery is not None
        assert abs(recovery - Decimal("3.0")) < Decimal("0.2")

    async def test_insufficient_data_handling(self, db_session, test_user):
        """Test metrics handle insufficient data gracefully."""
        # Create only 1 day of data (need 2+ for returns)
        start_date = date(2025, 6, 1)

        day = DimDay(
            id=600,
            date=start_date,
            year=2025,
            month=6,
            day=1,
            day_of_week=0,
            is_weekend=0,
        )
        db_session.add(day)

        curve = EquityCurve(
            id=str(uuid4()),
            user_id=test_user.id,
            date=start_date,
            equity=Decimal("10000"),
            peak_equity=Decimal("10000"),
            daily_change=Decimal("0"),
            created_at=datetime.utcnow(),
        )
        db_session.add(curve)
        await db_session.commit()

        # All metrics should handle insufficient data
        metrics = PerformanceMetrics(db_session)

        with pytest.raises(ValueError, match="insufficient data"):
            await metrics.get_daily_returns(test_user.id, start_date, start_date)

    async def test_zero_volatility_handling(self, db_session, test_user):
        """Test metrics handle zero volatility (flat equity)."""
        # Create flat equity curve (no volatility)
        start_date = date(2025, 7, 1)
        flat_equity = Decimal("10000")

        for i in range(5):
            day = DimDay(
                id=i + 700,
                date=start_date + timedelta(days=i),
                year=2025,
                month=7,
                day=start_date.day + i,
                day_of_week=0,
                is_weekend=0,
            )
            db_session.add(day)

            curve = EquityCurve(
                id=str(uuid4()),
                user_id=test_user.id,
                date=start_date + timedelta(days=i),
                equity=flat_equity,
                peak_equity=flat_equity,
                daily_change=Decimal("0"),
                created_at=datetime.utcnow(),
            )
            db_session.add(curve)

        await db_session.commit()

        # Sharpe/Sortino should handle zero volatility
        metrics = PerformanceMetrics(db_session)
        sharpe = await metrics.calculate_sharpe_ratio(
            test_user.id, start_date, start_date + timedelta(days=4)
        )
        sortino = await metrics.calculate_sortino_ratio(
            test_user.id, start_date, start_date + timedelta(days=4)
        )

        # Zero volatility + zero returns = 0 Sharpe/Sortino (not infinity or error)
        assert sharpe == 0
        assert sortino == 0
