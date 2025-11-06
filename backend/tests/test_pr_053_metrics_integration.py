"""
Comprehensive integration tests for PR-053: Performance Metrics.

Tests the full workflow:
1. get_daily_returns() - Query EquityCurve snapshots
2. get_metrics_for_window() - Compute all metrics for a time window
3. get_all_window_metrics() - Compute metrics for multiple windows
4. API endpoints - /analytics/metrics and /analytics/metrics/all-windows

Validates business logic with real database integration (not mocks).
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.analytics.metrics import PerformanceMetrics
from backend.app.analytics.models import DimDay, DimSymbol, EquityCurve, TradesFact
from backend.app.auth.models import User

# ============================================================================
# INTEGRATION TESTS: get_daily_returns()
# ============================================================================


@pytest.mark.asyncio
class TestGetDailyReturnsIntegration:
    """Test get_daily_returns() with real database."""

    async def test_get_daily_returns_with_equity_snapshots(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test get_daily_returns extracts daily returns from EquityCurve."""
        # Create equity snapshots for 5 consecutive days
        snapshots = []
        base_date = date(2025, 1, 1)
        equity_values = [
            Decimal("10000"),  # Day 0: start
            Decimal("10100"),  # Day 1: +1%
            Decimal("10200"),  # Day 2: +0.99%
            Decimal("10000"),  # Day 3: -1.96%
            Decimal("10150"),  # Day 4: +1.5%
        ]

        peak_so_far = Decimal("10000")
        for i, equity in enumerate(equity_values):
            # Track peak equity
            if equity > peak_so_far:
                peak_so_far = equity

            snapshot = EquityCurve(
                id=str(uuid4()),
                user_id=test_user.id,
                date=base_date + timedelta(days=i),
                equity=equity,
                cumulative_pnl=equity - Decimal("10000"),
                peak_equity=peak_so_far,
                drawdown=Decimal("0"),
                daily_change=Decimal("0"),
            )
            snapshots.append(snapshot)
            db_session.add(snapshot)

        await db_session.commit()

        # Get daily returns
        metrics = PerformanceMetrics(db_session)
        returns = await metrics.get_daily_returns(
            user_id=test_user.id,
            start_date=base_date,
            end_date=base_date + timedelta(days=4),
        )

        # Validate: should have 4 returns (5 snapshots = 4 transitions)
        assert len(returns) == 4

        # Validate each return calculation
        # Day 0→1: (10100 - 10000) / 10000 = 0.01 (1%)
        assert abs(returns[0] - Decimal("0.01")) < Decimal("0.0001")

        # Day 1→2: (10200 - 10100) / 10100 ≈ 0.0099 (0.99%)
        assert abs(returns[1] - Decimal("0.0099")) < Decimal("0.0001")

        # Day 2→3: (10000 - 10200) / 10200 ≈ -0.0196 (-1.96%)
        assert abs(returns[2] - Decimal("-0.0196")) < Decimal("0.001")

        # Day 3→4: (10150 - 10000) / 10000 = 0.015 (1.5%)
        assert abs(returns[3] - Decimal("0.015")) < Decimal("0.0001")

    async def test_get_daily_returns_empty_data(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test get_daily_returns with no equity snapshots."""
        metrics = PerformanceMetrics(db_session)

        returns = await metrics.get_daily_returns(
            user_id=test_user.id,
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
        )

        assert returns == []

    async def test_get_daily_returns_single_snapshot(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test get_daily_returns with single snapshot (insufficient)."""
        snapshot = EquityCurve(
            id=str(uuid4()),
            user_id=test_user.id,
            date=date(2025, 1, 1),
            equity=Decimal("10000"),
            cumulative_pnl=Decimal("0"),
            drawdown=Decimal("0"),
        )
        db_session.add(snapshot)
        await db_session.commit()

        metrics = PerformanceMetrics(db_session)
        returns = await metrics.get_daily_returns(
            user_id=test_user.id,
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 1),
        )

        # Should return empty (need at least 2 snapshots)
        assert returns == []

    async def test_get_daily_returns_handles_zero_equity(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test get_daily_returns skips calculations when prev_equity is zero."""
        # Day 1: equity = 0 (edge case)
        snapshot1 = EquityCurve(
            id=str(uuid4()),
            user_id=test_user.id,
            date=date(2025, 1, 1),
            equity=Decimal("0"),
            cumulative_pnl=Decimal("-10000"),
            drawdown=Decimal("100"),
        )
        # Day 2: equity = 100
        snapshot2 = EquityCurve(
            id=str(uuid4()),
            user_id=test_user.id,
            date=date(2025, 1, 2),
            equity=Decimal("100"),
            cumulative_pnl=Decimal("-9900"),
            drawdown=Decimal("0"),
        )
        db_session.add_all([snapshot1, snapshot2])
        await db_session.commit()

        metrics = PerformanceMetrics(db_session)
        returns = await metrics.get_daily_returns(
            user_id=test_user.id,
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 2),
        )

        # Should skip return calculation (prev_equity = 0)
        assert returns == []


# ============================================================================
# INTEGRATION TESTS: get_metrics_for_window()
# ============================================================================


@pytest.mark.asyncio
class TestGetMetricsForWindowIntegration:
    """Test get_metrics_for_window() with real database."""

    async def test_get_metrics_for_window_complete_workflow(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test full metrics calculation workflow with trades and equity snapshots."""
        # Setup: Create dimensions
        symbol = DimSymbol(id=1, symbol="GOLD", asset_class="commodity")
        day1 = DimDay(id=1, date=date(2025, 1, 1), day_of_week=3, month=1, year=2025)
        day2 = DimDay(id=2, date=date(2025, 1, 2), day_of_week=4, month=1, year=2025)
        day3 = DimDay(id=3, date=date(2025, 1, 3), day_of_week=5, month=1, year=2025)
        db_session.add_all([symbol, day1, day2, day3])
        await db_session.commit()

        # Create 3 trades (2 wins, 1 loss)
        trades = [
            TradesFact(
                id=str(uuid4()),
                user_id=test_user.id,
                symbol_id=symbol.id,
                entry_date_id=day1.id,
                exit_date_id=day1.id,
                side=0,
                entry_price=Decimal("1950"),
                exit_price=Decimal("1960"),
                volume=Decimal("1.0"),
                gross_pnl=Decimal("10"),
                pnl_percent=Decimal("0.51"),
                commission=Decimal("1"),
                net_pnl=Decimal("9"),
                winning_trade=1,
                bars_held=1,
                risk_amount=Decimal("10"),
                max_run_up=Decimal("10"),
                max_drawdown=Decimal("0"),
                entry_time=datetime(2025, 1, 1, 10, 0),
                exit_time=datetime(2025, 1, 1, 14, 0),
                source="signal",
            ),
            TradesFact(
                id=str(uuid4()),
                user_id=test_user.id,
                symbol_id=symbol.id,
                entry_date_id=day2.id,
                exit_date_id=day2.id,
                side=0,
                entry_price=Decimal("1960"),
                exit_price=Decimal("1980"),
                volume=Decimal("1.0"),
                gross_pnl=Decimal("20"),
                pnl_percent=Decimal("1.02"),
                commission=Decimal("1"),
                net_pnl=Decimal("19"),
                winning_trade=1,
                bars_held=1,
                risk_amount=Decimal("10"),
                max_run_up=Decimal("20"),
                max_drawdown=Decimal("0"),
                entry_time=datetime(2025, 1, 2, 10, 0),
                exit_time=datetime(2025, 1, 2, 14, 0),
                source="signal",
            ),
            TradesFact(
                id=str(uuid4()),
                user_id=test_user.id,
                symbol_id=symbol.id,
                entry_date_id=day3.id,
                exit_date_id=day3.id,
                side=1,  # sell
                entry_price=Decimal("1980"),
                exit_price=Decimal("1990"),
                volume=Decimal("1.0"),
                gross_pnl=Decimal("-10"),
                pnl_percent=Decimal("-0.51"),
                commission=Decimal("1"),
                net_pnl=Decimal("-11"),
                winning_trade=0,
                bars_held=1,
                risk_amount=Decimal("10"),
                max_run_up=Decimal("0"),
                max_drawdown=Decimal("11"),
                entry_time=datetime(2025, 1, 3, 10, 0),
                exit_time=datetime(2025, 1, 3, 14, 0),
                source="signal",
            ),
        ]
        db_session.add_all(trades)

        # Create equity snapshots
        snapshots = [
            EquityCurve(
                id=str(uuid4()),
                user_id=test_user.id,
                date=date(2025, 1, 1),
                equity=Decimal("10009"),
                cumulative_pnl=Decimal("9"),
                drawdown=Decimal("0"),
            ),
            EquityCurve(
                id=str(uuid4()),
                user_id=test_user.id,
                date=date(2025, 1, 2),
                equity=Decimal("10028"),
                cumulative_pnl=Decimal("28"),
                drawdown=Decimal("0"),
            ),
            EquityCurve(
                id=str(uuid4()),
                user_id=test_user.id,
                date=date(2025, 1, 3),
                equity=Decimal("10017"),
                cumulative_pnl=Decimal("17"),
                drawdown=Decimal("1.10"),  # Drawdown from peak
            ),
        ]
        db_session.add_all(snapshots)
        await db_session.commit()

        # Test: Get metrics for 3-day window
        metrics_calc = PerformanceMetrics(db_session)
        result = await metrics_calc.get_metrics_for_window(
            user_id=test_user.id,
            window_days=3,
        )

        # Validate results
        assert "sharpe_ratio" in result
        assert "sortino_ratio" in result
        assert "calmar_ratio" in result
        assert "profit_factor" in result
        assert "recovery_factor" in result
        assert "total_return_percent" in result
        assert "max_drawdown_percent" in result
        assert "win_rate" in result
        assert "num_trades" in result

        # Business logic validation
        assert result["num_trades"] == 3
        assert result["win_rate"] == Decimal("66.67")  # 2 wins / 3 trades ≈ 66.67%

        # Total return: (10017 - 10009) / 10009 * 100 ≈ 0.08%
        expected_return = (
            (Decimal("10017") - Decimal("10009")) / Decimal("10009") * Decimal("100")
        )
        assert abs(result["total_return_percent"] - expected_return) < Decimal("0.01")

        # Max drawdown: 1.10%
        assert result["max_drawdown_percent"] == Decimal("1.10")

        # Profit factor: (9 + 19) / 11 ≈ 2.55
        expected_pf = Decimal("28") / Decimal("11")
        assert abs(result["profit_factor"] - expected_pf) < Decimal("0.01")

        # Sharpe/Sortino should be calculated
        assert isinstance(result["sharpe_ratio"], Decimal)
        assert isinstance(result["sortino_ratio"], Decimal)

    async def test_get_metrics_for_window_insufficient_data(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test get_metrics_for_window raises ValueError on insufficient data."""
        metrics = PerformanceMetrics(db_session)

        with pytest.raises(ValueError, match="Insufficient data"):
            await metrics.get_metrics_for_window(test_user.id, window_days=30)

    async def test_get_metrics_for_window_custom_risk_free_rate(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test get_metrics_for_window uses custom risk-free rate."""
        # Create minimal data
        symbol = DimSymbol(id=1, symbol="GOLD", asset_class="commodity")
        day1 = DimDay(id=1, date=date.today(), day_of_week=3, month=1, year=2025)
        db_session.add_all([symbol, day1])

        trade = TradesFact(
            id=str(uuid4()),
            user_id=test_user.id,
            symbol_id=symbol.id,
            entry_date_id=day1.id,
            exit_date_id=day1.id,
            side=0,
            entry_price=Decimal("1950"),
            exit_price=Decimal("1960"),
            volume=Decimal("1.0"),
            gross_pnl=Decimal("10"),
            pnl_percent=Decimal("0.51"),
            commission=Decimal("1"),
            net_pnl=Decimal("9"),
            winning_trade=1,
            bars_held=1,
            risk_amount=Decimal("10"),
            max_run_up=Decimal("10"),
            max_drawdown=Decimal("0"),
            entry_time=datetime.now(),
            exit_time=datetime.now(),
            source="signal",
        )
        db_session.add(trade)

        snapshots = [
            EquityCurve(
                id=str(uuid4()),
                user_id=test_user.id,
                date=date.today() - timedelta(days=1),
                equity=Decimal("10000"),
                cumulative_pnl=Decimal("0"),
                drawdown=Decimal("0"),
            ),
            EquityCurve(
                id=str(uuid4()),
                user_id=test_user.id,
                date=date.today(),
                equity=Decimal("10009"),
                cumulative_pnl=Decimal("9"),
                drawdown=Decimal("0"),
            ),
        ]
        db_session.add_all(snapshots)
        await db_session.commit()

        # Test with custom risk-free rate (5% annual)
        custom_rate = Decimal("0.05")
        metrics = PerformanceMetrics(db_session, risk_free_rate=custom_rate)

        result = await metrics.get_metrics_for_window(test_user.id, window_days=1)

        # Verify metrics calculated
        assert result is not None
        assert "sharpe_ratio" in result
        assert metrics.risk_free_rate == custom_rate


# ============================================================================
# INTEGRATION TESTS: get_all_window_metrics()
# ============================================================================


@pytest.mark.asyncio
class TestGetAllWindowMetricsIntegration:
    """Test get_all_window_metrics() with real database."""

    async def test_get_all_window_metrics_multiple_windows(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test get_all_window_metrics returns metrics for 30/90/365 days."""
        # Create equity snapshots for 400 days (covers all windows)
        base_date = date.today() - timedelta(days=400)
        equity = Decimal("10000")

        for i in range(400):
            equity += Decimal("10")  # Steady growth
            snapshot = EquityCurve(
                id=str(uuid4()),
                user_id=test_user.id,
                date=base_date + timedelta(days=i),
                equity=equity,
                cumulative_pnl=equity - Decimal("10000"),
                drawdown=Decimal("0"),
            )
            db_session.add(snapshot)

        await db_session.commit()

        # Create at least one trade per window
        symbol = DimSymbol(id=1, symbol="GOLD", asset_class="commodity")
        day1 = DimDay(id=1, date=base_date, day_of_week=1, month=1, year=2024)
        day2 = DimDay(
            id=2,
            date=base_date + timedelta(days=100),
            day_of_week=1,
            month=4,
            year=2024,
        )
        day3 = DimDay(
            id=3,
            date=base_date + timedelta(days=300),
            day_of_week=1,
            month=10,
            year=2024,
        )
        db_session.add_all([symbol, day1, day2, day3])

        trades = []
        for day in [day1, day2, day3]:
            trade = TradesFact(
                id=str(uuid4()),
                user_id=test_user.id,
                symbol_id=symbol.id,
                entry_date_id=day.id,
                exit_date_id=day.id,
                side=0,
                entry_price=Decimal("1950"),
                exit_price=Decimal("1960"),
                volume=Decimal("1.0"),
                gross_pnl=Decimal("10"),
                pnl_percent=Decimal("0.51"),
                commission=Decimal("1"),
                net_pnl=Decimal("9"),
                winning_trade=1,
                bars_held=1,
                risk_amount=Decimal("10"),
                max_run_up=Decimal("10"),
                max_drawdown=Decimal("0"),
                entry_time=datetime.combine(day.date, datetime.min.time()),
                exit_time=datetime.combine(day.date, datetime.max.time()),
                source="signal",
            )
            trades.append(trade)
        db_session.add_all(trades)
        await db_session.commit()

        # Test: Get all window metrics
        metrics = PerformanceMetrics(db_session)
        result = await metrics.get_all_window_metrics(user_id=test_user.id)

        # Validate structure
        assert 30 in result
        assert 90 in result
        assert 365 in result

        # Validate all windows have metrics
        for window_days, metrics_dict in result.items():
            if metrics_dict:  # May be empty if insufficient data
                assert "sharpe_ratio" in metrics_dict
                assert "total_return_percent" in metrics_dict
                assert "num_trades" in metrics_dict

    async def test_get_all_window_metrics_handles_partial_data(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test get_all_window_metrics handles partial data gracefully."""
        # Create data only for 40 days (enough for 30d, not 90d/365d)
        base_date = date.today() - timedelta(days=40)
        equity = Decimal("10000")

        for i in range(40):
            equity += Decimal("5")
            snapshot = EquityCurve(
                id=str(uuid4()),
                user_id=test_user.id,
                date=base_date + timedelta(days=i),
                equity=equity,
                cumulative_pnl=equity - Decimal("10000"),
                drawdown=Decimal("0"),
            )
            db_session.add(snapshot)

        await db_session.commit()

        # Create minimal trade
        symbol = DimSymbol(id=1, symbol="GOLD", asset_class="commodity")
        day1 = DimDay(id=1, date=base_date, day_of_week=1, month=1, year=2025)
        db_session.add_all([symbol, day1])

        trade = TradesFact(
            id=str(uuid4()),
            user_id=test_user.id,
            symbol_id=symbol.id,
            entry_date_id=day1.id,
            exit_date_id=day1.id,
            side=0,
            entry_price=Decimal("1950"),
            exit_price=Decimal("1960"),
            volume=Decimal("1.0"),
            gross_pnl=Decimal("10"),
            pnl_percent=Decimal("0.51"),
            commission=Decimal("1"),
            net_pnl=Decimal("9"),
            winning_trade=1,
            bars_held=1,
            risk_amount=Decimal("10"),
            max_run_up=Decimal("10"),
            max_drawdown=Decimal("0"),
            entry_time=datetime.combine(day1.date, datetime.min.time()),
            exit_time=datetime.combine(day1.date, datetime.max.time()),
            source="signal",
        )
        db_session.add(trade)
        await db_session.commit()

        # Test
        metrics = PerformanceMetrics(db_session)
        result = await metrics.get_all_window_metrics(user_id=test_user.id)

        # 30d window should have data
        assert 30 in result
        if result[30]:
            assert "sharpe_ratio" in result[30]

        # 90d and 365d windows may be empty
        assert 90 in result
        assert 365 in result
        # They should be empty dicts (not errors)
        if not result[90]:
            assert result[90] == {}


# ============================================================================
# API ROUTE TESTS: /analytics/metrics
# ============================================================================


@pytest.mark.asyncio
class TestMetricsAPIRoutes:
    """Test /analytics/metrics API endpoints."""

    async def test_metrics_endpoint_requires_auth(self, client: AsyncClient):
        """Test /analytics/metrics requires authentication."""
        response = await client.get("/api/v1/analytics/metrics?window=90")

        assert response.status_code == 401
        assert "detail" in response.json()

    async def test_metrics_endpoint_returns_metrics(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_user: User,
        db_session: AsyncSession,
    ):
        """Test /analytics/metrics returns complete metrics."""
        # Setup: Create complete data
        symbol = DimSymbol(id=1, symbol="GOLD", asset_class="commodity")
        day1 = DimDay(
            id=1,
            date=date.today() - timedelta(days=5),
            day_of_week=1,
            month=1,
            year=2025,
        )
        day2 = DimDay(
            id=2,
            date=date.today() - timedelta(days=4),
            day_of_week=2,
            month=1,
            year=2025,
        )
        db_session.add_all([symbol, day1, day2])

        # Create trade
        trade = TradesFact(
            id=str(uuid4()),
            user_id=test_user.id,
            symbol_id=symbol.id,
            entry_date_id=day1.id,
            exit_date_id=day1.id,
            side=0,
            entry_price=Decimal("1950"),
            exit_price=Decimal("1960"),
            volume=Decimal("1.0"),
            gross_pnl=Decimal("10"),
            pnl_percent=Decimal("0.51"),
            commission=Decimal("1"),
            net_pnl=Decimal("9"),
            winning_trade=1,
            bars_held=1,
            risk_amount=Decimal("10"),
            max_run_up=Decimal("10"),
            max_drawdown=Decimal("0"),
            entry_time=datetime.combine(day1.date, datetime.min.time()),
            exit_time=datetime.combine(day1.date, datetime.max.time()),
            source="signal",
        )
        db_session.add(trade)

        # Create equity snapshots
        for i in range(7):
            snapshot = EquityCurve(
                id=str(uuid4()),
                user_id=test_user.id,
                date=date.today() - timedelta(days=6 - i),
                equity=Decimal("10000") + Decimal(str(i * 10)),
                cumulative_pnl=Decimal(str(i * 10)),
                drawdown=Decimal("0"),
            )
            db_session.add(snapshot)

        await db_session.commit()

        # Test
        response = await client.get(
            "/api/v1/analytics/metrics?window=7", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        # Validate response structure
        assert "sharpe_ratio" in data
        assert "sortino_ratio" in data
        assert "calmar_ratio" in data
        assert "profit_factor" in data
        assert "recovery_factor" in data
        assert "win_rate_percent" in data
        assert "num_trades" in data
        assert "total_return_percent" in data
        assert "max_drawdown_percent" in data
        assert "period_days" in data

        # Validate types
        assert isinstance(data["sharpe_ratio"], (int, float))
        assert isinstance(data["profit_factor"], (int, float))
        assert isinstance(data["num_trades"], int)
        assert data["period_days"] == 7

    async def test_metrics_endpoint_handles_no_trades(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test /analytics/metrics returns 404 when no trades exist."""
        response = await client.get(
            "/api/v1/analytics/metrics?window=30", headers=auth_headers
        )

        assert response.status_code == 404
        assert "detail" in response.json()

    async def test_metrics_endpoint_respects_window_param(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_user: User,
        db_session: AsyncSession,
    ):
        """Test /analytics/metrics respects window parameter."""
        # Setup minimal data
        symbol = DimSymbol(id=1, symbol="GOLD", asset_class="commodity")
        day1 = DimDay(
            id=1,
            date=date.today() - timedelta(days=10),
            day_of_week=1,
            month=1,
            year=2025,
        )
        db_session.add_all([symbol, day1])

        trade = TradesFact(
            id=str(uuid4()),
            user_id=test_user.id,
            symbol_id=symbol.id,
            entry_date_id=day1.id,
            exit_date_id=day1.id,
            side=0,
            entry_price=Decimal("1950"),
            exit_price=Decimal("1960"),
            volume=Decimal("1.0"),
            gross_pnl=Decimal("10"),
            pnl_percent=Decimal("0.51"),
            commission=Decimal("1"),
            net_pnl=Decimal("9"),
            winning_trade=1,
            bars_held=1,
            risk_amount=Decimal("10"),
            max_run_up=Decimal("10"),
            max_drawdown=Decimal("0"),
            entry_time=datetime.combine(day1.date, datetime.min.time()),
            exit_time=datetime.combine(day1.date, datetime.max.time()),
            source="signal",
        )
        db_session.add(trade)

        # Create equity for 15 days
        for i in range(15):
            snapshot = EquityCurve(
                id=str(uuid4()),
                user_id=test_user.id,
                date=date.today() - timedelta(days=14 - i),
                equity=Decimal("10000") + Decimal(str(i * 5)),
                cumulative_pnl=Decimal(str(i * 5)),
                drawdown=Decimal("0"),
            )
            db_session.add(snapshot)

        await db_session.commit()

        # Test with custom window
        response = await client.get(
            "/api/v1/analytics/metrics?window=10", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["period_days"] == 10

    async def test_metrics_all_windows_endpoint(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_user: User,
        db_session: AsyncSession,
    ):
        """Test /analytics/metrics/all-windows returns multiple windows."""
        # Setup: Create enough data for at least 30d window
        symbol = DimSymbol(id=1, symbol="GOLD", asset_class="commodity")
        day1 = DimDay(
            id=1,
            date=date.today() - timedelta(days=35),
            day_of_week=1,
            month=1,
            year=2025,
        )
        db_session.add_all([symbol, day1])

        trade = TradesFact(
            id=str(uuid4()),
            user_id=test_user.id,
            symbol_id=symbol.id,
            entry_date_id=day1.id,
            exit_date_id=day1.id,
            side=0,
            entry_price=Decimal("1950"),
            exit_price=Decimal("1960"),
            volume=Decimal("1.0"),
            gross_pnl=Decimal("10"),
            pnl_percent=Decimal("0.51"),
            commission=Decimal("1"),
            net_pnl=Decimal("9"),
            winning_trade=1,
            bars_held=1,
            risk_amount=Decimal("10"),
            max_run_up=Decimal("10"),
            max_drawdown=Decimal("0"),
            entry_time=datetime.combine(day1.date, datetime.min.time()),
            exit_time=datetime.combine(day1.date, datetime.max.time()),
            source="signal",
        )
        db_session.add(trade)

        # Create equity for 40 days
        for i in range(40):
            snapshot = EquityCurve(
                id=str(uuid4()),
                user_id=test_user.id,
                date=date.today() - timedelta(days=39 - i),
                equity=Decimal("10000") + Decimal(str(i * 5)),
                cumulative_pnl=Decimal(str(i * 5)),
                drawdown=Decimal("0"),
            )
            db_session.add(snapshot)

        await db_session.commit()

        # Test
        response = await client.get(
            "/api/v1/analytics/metrics/all-windows", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        # Validate structure (returns dict with string keys)
        assert "30" in data or "90" in data or "365" in data

        # At least one window should have data
        has_data = False
        for window_data in data.values():
            if window_data:
                has_data = True
                assert "sharpe_ratio" in window_data
                assert "profit_factor" in window_data
                break

        assert has_data, "At least one window should have metrics"
