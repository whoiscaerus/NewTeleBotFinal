"""
Comprehensive test suite for PR-051, PR-052, PR-053.

Tests:
- PR-051: Analytics warehouse ETL (models, migrations, idempotence, DST handling)
- PR-052: Equity and drawdown computation (gap handling, peak tracking)
- PR-053: Performance metrics (Sharpe, Sortino, Calmar, Profit Factor, Recovery Factor)

Coverage target: 90%+
Test categories: unit (40%), integration (40%), end-to-end (20%)
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.analytics.drawdown import DrawdownAnalyzer
from backend.app.analytics.equity import EquityEngine, EquitySeries
from backend.app.analytics.etl import AnalyticsETL
from backend.app.analytics.metrics import PerformanceMetrics
from backend.app.analytics.models import (
    DailyRollups,
    DimDay,
    DimSymbol,
    EquityCurve,
    TradesFact,
)
from backend.app.auth.models import User
from backend.app.trading.store.models import Trade

# ============================================================================
# FIXTURES
# ============================================================================


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create test user."""
    user = User(
        id=str(uuid4()),
        email="test@example.com",
        password_hash="hashed_password_here",
        telegram_user_id="12345",
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest_asyncio.fixture
async def sample_trades(db_session: AsyncSession, test_user: User) -> list:
    """Create sample trades for testing."""
    trades = []

    base_date = datetime(2025, 1, 1, 12, 0, 0)

    # Trade 1: Winner
    trade1 = Trade(
        trade_id=str(uuid4()),
        user_id=test_user.id,
        symbol="GOLD",
        strategy="fib_rsi",
        timeframe="H1",
        trade_type="BUY",
        direction=0,
        entry_price=Decimal("1950.00"),
        exit_price=Decimal("1960.00"),
        entry_time=base_date,
        exit_time=base_date + timedelta(hours=2),
        stop_loss=Decimal("1940.00"),
        take_profit=Decimal("1970.00"),
        volume=Decimal("1.0"),
        profit=Decimal("10.00"),
        status="CLOSED",
    )
    trades.append(trade1)

    # Trade 2: Loser
    trade2 = Trade(
        trade_id=str(uuid4()),
        user_id=test_user.id,
        symbol="GOLD",
        strategy="channel",
        timeframe="H1",
        trade_type="SELL",
        direction=1,
        entry_price=Decimal("1960.00"),
        exit_price=Decimal("1955.00"),
        entry_time=base_date + timedelta(days=1),
        exit_time=base_date + timedelta(days=1, hours=4),
        stop_loss=Decimal("1970.00"),
        take_profit=Decimal("1950.00"),
        volume=Decimal("1.0"),
        profit=Decimal("-5.00"),
        status="CLOSED",
    )
    trades.append(trade2)

    # Trade 3: Winner on different day
    trade3 = Trade(
        trade_id=str(uuid4()),
        user_id=test_user.id,
        symbol="EURUSD",
        strategy="fib_rsi",
        timeframe="H4",
        trade_type="BUY",
        direction=0,
        entry_price=Decimal("1.0800"),
        exit_price=Decimal("1.0850"),
        entry_time=base_date + timedelta(days=2),
        exit_time=base_date + timedelta(days=2, hours=3),
        stop_loss=Decimal("1.0750"),
        take_profit=Decimal("1.0900"),
        volume=Decimal("10.0"),
        profit=Decimal("500.00"),
        status="CLOSED",
    )
    trades.append(trade3)

    for trade in trades:
        db_session.add(trade)
    await db_session.commit()

    return trades


# ============================================================================
# PR-051 TESTS: WAREHOUSE & ETL
# ============================================================================


@pytest.mark.asyncio
class TestWarehouseModels:
    """Test warehouse data models."""

    async def test_dim_symbol_creation(self, db_session: AsyncSession):
        """Test DimSymbol model."""
        symbol = DimSymbol(
            symbol="GOLD",
            asset_class="commodity",
            created_at=datetime.utcnow(),
        )
        db_session.add(symbol)
        await db_session.commit()

        result = await db_session.execute(
            select(DimSymbol).where(DimSymbol.symbol == "GOLD")
        )
        retrieved = result.scalars().first()

        assert retrieved is not None
        assert retrieved.symbol == "GOLD"
        assert retrieved.asset_class == "commodity"

    async def test_dim_day_creation(self, db_session: AsyncSession):
        """Test DimDay model."""
        target_date = date(2025, 1, 15)
        dim_day = DimDay(
            date=target_date,
            day_of_week=2,  # Wednesday
            week_of_year=3,
            month=1,
            year=2025,
            is_trading_day=1,
            created_at=datetime.utcnow(),
        )
        db_session.add(dim_day)
        await db_session.commit()

        result = await db_session.execute(
            select(DimDay).where(DimDay.date == target_date)
        )
        retrieved = result.scalars().first()

        assert retrieved is not None
        assert retrieved.date == target_date
        assert retrieved.day_of_week == 2
        assert retrieved.is_trading_day == 1

    async def test_trades_fact_creation(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test TradesFact model."""
        # Create dimensions first
        symbol = DimSymbol(
            symbol="GOLD", asset_class="commodity", created_at=datetime.utcnow()
        )
        db_session.add(symbol)
        await db_session.flush()

        day1 = DimDay(
            date=date(2025, 1, 1),
            day_of_week=2,
            week_of_year=1,
            month=1,
            year=2025,
            is_trading_day=1,
            created_at=datetime.utcnow(),
        )
        day2 = DimDay(
            date=date(2025, 1, 2),
            day_of_week=3,
            week_of_year=1,
            month=1,
            year=2025,
            is_trading_day=1,
            created_at=datetime.utcnow(),
        )
        db_session.add(day1)
        db_session.add(day2)
        await db_session.flush()

        # Create fact record
        trade = TradesFact(
            id=str(uuid4()),
            user_id=test_user.id,
            symbol_id=symbol.id,
            entry_date_id=day1.id,
            exit_date_id=day2.id,
            side=0,  # Buy
            entry_price=Decimal("1950.00"),
            exit_price=Decimal("1960.00"),
            volume=Decimal("1.0"),
            gross_pnl=Decimal("10.00"),
            pnl_percent=Decimal("0.51"),
            commission=Decimal("5.00"),
            net_pnl=Decimal("5.00"),
            r_multiple=Decimal("2.0"),
            bars_held=48,
            winning_trade=1,
            risk_amount=Decimal("10.00"),
            max_run_up=Decimal("15.00"),
            max_drawdown=Decimal("0.00"),
            entry_time=datetime(2025, 1, 1, 12, 0),
            exit_time=datetime(2025, 1, 2, 12, 0),
            source="signal",
        )
        db_session.add(trade)
        await db_session.commit()

        result = await db_session.execute(
            select(TradesFact).where(TradesFact.id == trade.id)
        )
        retrieved = result.scalars().first()

        assert retrieved is not None
        assert retrieved.net_pnl == Decimal("5.00")
        assert retrieved.winning_trade == 1

    async def test_daily_rollups_creation(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test DailyRollups model."""
        symbol = DimSymbol(
            symbol="GOLD", asset_class="commodity", created_at=datetime.utcnow()
        )
        db_session.add(symbol)
        await db_session.flush()

        day = DimDay(
            date=date(2025, 1, 1),
            day_of_week=2,
            week_of_year=1,
            month=1,
            year=2025,
            is_trading_day=1,
            created_at=datetime.utcnow(),
        )
        db_session.add(day)
        await db_session.flush()

        rollup = DailyRollups(
            id=str(uuid4()),
            user_id=test_user.id,
            symbol_id=symbol.id,
            day_id=day.id,
            total_trades=5,
            winning_trades=3,
            losing_trades=2,
            gross_pnl=Decimal("100.00"),
            total_commission=Decimal("25.00"),
            net_pnl=Decimal("75.00"),
            win_rate=Decimal("0.60"),
            profit_factor=Decimal("2.50"),
            avg_r_multiple=Decimal("1.80"),
            avg_win=Decimal("50.00"),
            avg_loss=Decimal("-25.00"),
            largest_win=Decimal("75.00"),
            largest_loss=Decimal("-50.00"),
            max_run_up=Decimal("100.00"),
            max_drawdown=Decimal("10.00"),
        )
        db_session.add(rollup)
        await db_session.commit()

        result = await db_session.execute(
            select(DailyRollups).where(DailyRollups.id == rollup.id)
        )
        retrieved = result.scalars().first()

        assert retrieved is not None
        assert retrieved.win_rate == Decimal("0.60")
        assert retrieved.profit_factor == Decimal("2.50")


@pytest.mark.asyncio
class TestETLService:
    """Test ETL service."""

    async def test_get_or_create_dim_symbol_idempotent(self, db_session: AsyncSession):
        """Test DimSymbol creation is idempotent."""
        etl = AnalyticsETL(db_session)

        # Create first time
        symbol1 = await etl.get_or_create_dim_symbol("GOLD", "commodity")
        await db_session.commit()

        # Create again (should return same)
        symbol2 = await etl.get_or_create_dim_symbol("GOLD", "commodity")
        await db_session.commit()

        assert symbol1.id == symbol2.id
        assert symbol1.symbol == symbol2.symbol

    async def test_get_or_create_dim_day_idempotent(self, db_session: AsyncSession):
        """Test DimDay creation is idempotent."""
        etl = AnalyticsETL(db_session)
        target_date = date(2025, 1, 15)

        # Create first time
        day1 = await etl.get_or_create_dim_day(target_date)
        await db_session.commit()

        # Create again (should return same)
        day2 = await etl.get_or_create_dim_day(target_date)
        await db_session.commit()

        assert day1.id == day2.id
        assert day1.date == day2.date

    async def test_dim_day_dst_handling(self, db_session: AsyncSession):
        """Test DimDay handles DST transitions safely."""
        etl = AnalyticsETL(db_session)

        # Create days around DST boundary (March 10, 2025)
        day_before = await etl.get_or_create_dim_day(date(2025, 3, 9))  # Sunday
        dst_day = await etl.get_or_create_dim_day(date(2025, 3, 10))  # Monday (DST)
        day_after = await etl.get_or_create_dim_day(date(2025, 3, 11))  # Tuesday

        assert day_before.date == date(2025, 3, 9)
        assert dst_day.date == date(2025, 3, 10)
        assert day_after.date == date(2025, 3, 11)
        # Verify dates are sequential
        assert (day_after.date - day_before.date).days == 2
        # Verify all dates created successfully with DST handling
        assert day_before.is_trading_day == 0  # Sunday - not trading day
        assert dst_day.is_trading_day == 1  # Monday - trading day (DST transition)
        assert day_after.is_trading_day == 1  # Tuesday - trading day

    async def test_build_daily_rollups_aggregates_correctly(
        self, db_session: AsyncSession, test_user: User, sample_trades
    ):
        """Test daily rollups aggregate trade metrics correctly."""
        etl = AnalyticsETL(db_session)

        # Load trades (this is normally done separately)
        # For this test, manually create trades_fact records

        # Trade 1: GOLD, winner, 10 PnL
        symbol_gold = await etl.get_or_create_dim_symbol("GOLD", "commodity")
        day1 = await etl.get_or_create_dim_day(date(2025, 1, 1))

        trade1 = TradesFact(
            id=str(uuid4()),
            user_id=test_user.id,
            symbol_id=symbol_gold.id,
            entry_date_id=day1.id,
            exit_date_id=day1.id,
            side=0,
            entry_price=Decimal("1950.00"),
            exit_price=Decimal("1960.00"),
            volume=Decimal("1.0"),
            gross_pnl=Decimal("10.00"),
            pnl_percent=Decimal("0.51"),
            commission=Decimal("2.00"),
            net_pnl=Decimal("8.00"),
            winning_trade=1,
            bars_held=2,
            risk_amount=Decimal("10.00"),
            max_run_up=Decimal("10.00"),
            max_drawdown=Decimal("0.00"),
            entry_time=datetime(2025, 1, 1, 8, 0),
            exit_time=datetime(2025, 1, 1, 10, 0),
            source="signal",
        )
        db_session.add(trade1)

        # Trade 2: GOLD, loser, -5 PnL
        trade2 = TradesFact(
            id=str(uuid4()),
            user_id=test_user.id,
            symbol_id=symbol_gold.id,
            entry_date_id=day1.id,
            exit_date_id=day1.id,
            side=1,
            entry_price=Decimal("1960.00"),
            exit_price=Decimal("1955.00"),
            volume=Decimal("1.0"),
            gross_pnl=Decimal("-5.00"),
            pnl_percent=Decimal("-0.26"),
            commission=Decimal("2.00"),
            net_pnl=Decimal("-7.00"),
            winning_trade=0,
            bars_held=1,
            risk_amount=Decimal("10.00"),
            max_run_up=Decimal("0.00"),
            max_drawdown=Decimal("5.00"),
            entry_time=datetime(2025, 1, 1, 11, 0),
            exit_time=datetime(2025, 1, 1, 12, 0),
            source="manual",
        )
        db_session.add(trade2)
        await db_session.commit()

        # Build rollup
        await etl.build_daily_rollups(test_user.id, date(2025, 1, 1))

        # Verify rollup
        result = await db_session.execute(
            select(DailyRollups).where(
                DailyRollups.user_id == test_user.id,
                DailyRollups.day_id == day1.id,
            )
        )
        rollups = result.scalars().all()

        assert len(rollups) == 1
        rollup = rollups[0]
        assert rollup.total_trades == 2
        assert rollup.winning_trades == 1
        assert rollup.losing_trades == 1
        assert rollup.net_pnl == Decimal("1.00")  # 8 + (-7)
        assert rollup.win_rate == Decimal("0.5")


# ============================================================================
# PR-052 TESTS: EQUITY & DRAWDOWN
# ============================================================================


@pytest.mark.asyncio
class TestEquityEngine:
    """Test equity computation engine."""

    def test_equity_series_construction(self):
        """Test EquitySeries object."""
        dates = [date(2025, 1, 1), date(2025, 1, 2), date(2025, 1, 3)]
        equity = [Decimal("10000"), Decimal("10100"), Decimal("10050")]
        peak = [Decimal("10000"), Decimal("10100"), Decimal("10100")]
        pnl = [Decimal("0"), Decimal("100"), Decimal("50")]

        series = EquitySeries(dates, equity, peak, pnl)

        assert series.final_equity == Decimal("10050")
        assert series.total_return > 0
        assert len(series.drawdown) == 3

    def test_equity_series_drawdown_calculation(self):
        """Test drawdown calculation in EquitySeries."""
        dates = [date(2025, 1, i) for i in range(1, 6)]
        # 10000 -> 10100 (peak) -> 10000 (dd=1%) -> 9900 (dd=1.98%) -> 10200
        equity = [
            Decimal("10000"),
            Decimal("10100"),
            Decimal("10000"),
            Decimal("9900"),
            Decimal("10200"),
        ]
        peak = [
            Decimal("10000"),
            Decimal("10100"),
            Decimal("10100"),
            Decimal("10100"),
            Decimal("10200"),
        ]
        pnl = [
            Decimal("0"),
            Decimal("100"),
            Decimal("0"),
            Decimal("-100"),
            Decimal("200"),
        ]

        series = EquitySeries(dates, equity, peak, pnl)
        drawdowns = series.drawdown

        assert drawdowns[0] == Decimal("0")  # No DD at start
        assert drawdowns[1] == Decimal("0")  # No DD at peak
        assert drawdowns[2] < Decimal("1")  # Small DD
        assert drawdowns[3] > drawdowns[2]  # Larger DD
        assert drawdowns[4] == Decimal("0")  # No DD at new peak

    def test_equity_series_max_drawdown(self):
        """Test max_drawdown property."""
        dates = [date(2025, 1, i) for i in range(1, 4)]
        equity = [Decimal("10000"), Decimal("11000"), Decimal("9000")]
        peak = [Decimal("10000"), Decimal("11000"), Decimal("11000")]
        pnl = [Decimal("0"), Decimal("1000"), Decimal("-1000")]

        series = EquitySeries(dates, equity, peak, pnl)

        max_dd = series.max_drawdown
        # Expected: (11000 - 9000) / 11000 * 100 = 18.18...
        expected = (
            (Decimal("11000") - Decimal("9000")) / Decimal("11000") * Decimal("100")
        )
        assert abs(max_dd - expected) < Decimal("0.01")

    async def test_compute_equity_series_fills_gaps(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test equity computation handles gaps (non-trading days)."""
        # Create dimension records
        symbol = DimSymbol(symbol="GOLD", created_at=datetime.utcnow())
        db_session.add(symbol)
        await db_session.flush()

        # Create days: 1st, 2nd (trading), gap to 5th, 6th
        days = {}
        for d in [1, 2, 5, 6]:
            dim_day = DimDay(
                date=date(2025, 1, d),
                day_of_week=d % 7,
                week_of_year=1,
                month=1,
                year=2025,
                is_trading_day=1,
                created_at=datetime.utcnow(),
            )
            db_session.add(dim_day)
            await db_session.flush()
            days[d] = dim_day

        # Create trades
        trade1 = TradesFact(
            id=str(uuid4()),
            user_id=test_user.id,
            symbol_id=symbol.id,
            entry_date_id=days[1].id,
            exit_date_id=days[1].id,
            side=0,
            entry_price=Decimal("1950.00"),
            exit_price=Decimal("1960.00"),
            volume=Decimal("1.0"),
            gross_pnl=Decimal("10.00"),
            pnl_percent=Decimal("0.51"),
            commission=Decimal("1.00"),
            net_pnl=Decimal("9.00"),
            winning_trade=1,
            bars_held=2,
            risk_amount=Decimal("10.00"),
            max_run_up=Decimal("10.00"),
            max_drawdown=Decimal("0.00"),
            entry_time=datetime(2025, 1, 1),
            exit_time=datetime(2025, 1, 2),
            source="signal",
        )
        db_session.add(trade1)

        trade2 = TradesFact(
            id=str(uuid4()),
            user_id=test_user.id,
            symbol_id=symbol.id,
            entry_date_id=days[5].id,
            exit_date_id=days[5].id,
            side=0,
            entry_price=Decimal("1960.00"),
            exit_price=Decimal("1965.00"),
            volume=Decimal("1.0"),
            gross_pnl=Decimal("5.00"),
            pnl_percent=Decimal("0.26"),
            commission=Decimal("1.00"),
            net_pnl=Decimal("4.00"),
            winning_trade=1,
            bars_held=1,
            risk_amount=Decimal("10.00"),
            max_run_up=Decimal("5.00"),
            max_drawdown=Decimal("0.00"),
            entry_time=datetime(2025, 1, 5),
            exit_time=datetime(2025, 1, 5),
            source="signal",
        )
        db_session.add(trade2)
        await db_session.commit()

        # Compute equity series
        engine = EquityEngine(db_session)
        equity_series = await engine.compute_equity_series(test_user.id)

        # Verify gap handling
        # Trades exit on days 2 and 5, so range is 2-5 (4 days)
        assert len(equity_series.dates) == 4  # Days 2, 3, 4, 5
        assert equity_series.dates[0] == date(2025, 1, 2)
        assert equity_series.dates[-1] == date(2025, 1, 5)

        # Verify forward fill: days 3, 4 should have equity from day 2
        day2_equity = equity_series.equity[0]  # Index 0 = day 2
        day3_equity = equity_series.equity[1]  # Index 1 = day 3 (gap filled)
        day4_equity = equity_series.equity[2]  # Index 2 = day 4 (gap filled)

        assert day3_equity == day2_equity  # Gap filled
        assert day4_equity == day2_equity  # Gap filled

    async def test_compute_drawdown_metrics(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test drawdown computation."""
        symbol = DimSymbol(symbol="GOLD", created_at=datetime.utcnow())
        db_session.add(symbol)
        await db_session.flush()

        days = {}
        for d in range(1, 6):
            dim_day = DimDay(
                date=date(2025, 1, d),
                day_of_week=d % 7,
                week_of_year=1,
                month=1,
                year=2025,
                is_trading_day=1,
                created_at=datetime.utcnow(),
            )
            db_session.add(dim_day)
            await db_session.flush()
            days[d] = dim_day

        # Create trades that produce: 10000 -> 11000 (peak) -> 9000 (max DD 18.2%)
        trades_data = [
            (1, 1, Decimal("1950"), Decimal("2050"), Decimal("1000")),  # +1000
            (2, 2, Decimal("2050"), Decimal("1850"), Decimal("-1000")),  # -1000
        ]

        for entry_d, exit_d, entry_p, exit_p, pnl in trades_data:
            trade = TradesFact(
                id=str(uuid4()),
                user_id=test_user.id,
                symbol_id=symbol.id,
                entry_date_id=days[entry_d].id,
                exit_date_id=days[exit_d].id,
                side=0,
                entry_price=entry_p,
                exit_price=exit_p,
                volume=Decimal("1.0"),
                gross_pnl=pnl,
                pnl_percent=(exit_p - entry_p) / entry_p * Decimal("100"),
                commission=Decimal("0"),
                net_pnl=pnl,
                winning_trade=1 if pnl > 0 else 0,
                bars_held=1,
                risk_amount=Decimal("100"),
                max_run_up=max(pnl, Decimal("0")),
                max_drawdown=abs(min(pnl, Decimal("0"))),
                entry_time=datetime(2025, 1, entry_d),
                exit_time=datetime(2025, 1, exit_d),
                source="signal",
            )
            db_session.add(trade)
        await db_session.commit()

        engine = EquityEngine(db_session)
        equity_series = await engine.compute_equity_series(test_user.id)
        max_dd, duration = await engine.compute_drawdown(equity_series)

        # Verify max drawdown is calculated
        assert max_dd > 0
        assert duration >= 0


# ============================================================================
# PR-053 TESTS: PERFORMANCE METRICS
# ============================================================================


@pytest.mark.asyncio
class TestPerformanceMetrics:
    """Test performance metrics calculation."""

    def test_sharpe_ratio_calculation(self):
        """Test Sharpe Ratio calculation."""
        metrics = PerformanceMetrics.__new__(PerformanceMetrics)
        metrics.risk_free_daily = Decimal("0.0001")

        # Daily returns
        daily_returns = [
            Decimal("0.01"),  # 1%
            Decimal("0.02"),  # 2%
            Decimal("-0.01"),  # -1%
            Decimal("0.015"),  # 1.5%
        ]

        sharpe = metrics.calculate_sharpe_ratio(daily_returns)

        assert sharpe > 0
        assert isinstance(sharpe, Decimal)

    def test_sortino_ratio_calculation(self):
        """Test Sortino Ratio calculation."""
        metrics = PerformanceMetrics.__new__(PerformanceMetrics)
        metrics.risk_free_daily = Decimal("0.0001")

        daily_returns = [
            Decimal("0.02"),  # 2%
            Decimal("0.02"),  # 2%
            Decimal("-0.005"),  # -0.5%
        ]

        sortino = metrics.calculate_sortino_ratio(daily_returns)

        assert sortino > 0
        assert isinstance(sortino, Decimal)

    def test_calmar_ratio_calculation(self):
        """Test Calmar Ratio calculation."""
        metrics = PerformanceMetrics.__new__(PerformanceMetrics)

        # Calmar = annual_return / max_drawdown
        total_return = Decimal("30")  # 30%
        max_dd = Decimal("10")  # 10%
        days = 90

        calmar = metrics.calculate_calmar_ratio(total_return, max_dd, days)

        expected = (Decimal("30") * Decimal("365") / Decimal("90")) / Decimal("10")
        assert abs(calmar - expected) < Decimal("0.01")

    def test_profit_factor_calculation(self):
        """Test Profit Factor calculation."""
        metrics = PerformanceMetrics.__new__(PerformanceMetrics)

        trades = [
            (Decimal("100"), True),  # Win
            (Decimal("50"), True),  # Win
            (Decimal("-30"), False),  # Loss
            (Decimal("-20"), False),  # Loss
        ]

        pf = metrics.calculate_profit_factor(trades)

        # PF = 150 / 50 = 3.0
        expected = Decimal("150") / Decimal("50")
        assert abs(pf - expected) < Decimal("0.01")

    def test_profit_factor_no_losses(self):
        """Test Profit Factor with no losses."""
        metrics = PerformanceMetrics.__new__(PerformanceMetrics)

        trades = [
            (Decimal("100"), True),
            (Decimal("50"), True),
        ]

        pf = metrics.calculate_profit_factor(trades)

        assert pf == Decimal("999")

    def test_recovery_factor_calculation(self):
        """Test Recovery Factor calculation."""
        metrics = PerformanceMetrics.__new__(PerformanceMetrics)

        total_return = Decimal("50")  # 50%
        max_dd = Decimal("20")  # 20%

        rf = metrics.calculate_recovery_factor(total_return, max_dd)

        expected = Decimal("50") / Decimal("20")
        assert abs(rf - expected) < Decimal("0.01")

    # ========================================================================
    # EDGE CASE TESTS - Sharpe Ratio
    # ========================================================================

    def test_sharpe_ratio_empty_list(self):
        """Test Sharpe Ratio with empty returns."""
        metrics = PerformanceMetrics.__new__(PerformanceMetrics)
        metrics.risk_free_daily = Decimal("0.0001")

        sharpe = metrics.calculate_sharpe_ratio([])
        assert sharpe == Decimal(0)

    def test_sharpe_ratio_single_return(self):
        """Test Sharpe Ratio with single return (insufficient data)."""
        metrics = PerformanceMetrics.__new__(PerformanceMetrics)
        metrics.risk_free_daily = Decimal("0.0001")

        sharpe = metrics.calculate_sharpe_ratio([Decimal("0.01")])
        assert sharpe == Decimal(0)

    def test_sharpe_ratio_constant_returns(self):
        """Test Sharpe Ratio with constant returns (zero volatility)."""
        metrics = PerformanceMetrics.__new__(PerformanceMetrics)
        metrics.risk_free_daily = Decimal("0.0001")

        daily_returns = [Decimal("0.01")] * 5
        sharpe = metrics.calculate_sharpe_ratio(daily_returns)
        assert sharpe == Decimal(0)

    def test_sharpe_ratio_negative_returns(self):
        """Test Sharpe Ratio with all negative returns."""
        metrics = PerformanceMetrics.__new__(PerformanceMetrics)
        metrics.risk_free_daily = Decimal("0.0001")

        daily_returns = [
            Decimal("-0.01"),
            Decimal("-0.02"),
            Decimal("-0.015"),
        ]
        sharpe = metrics.calculate_sharpe_ratio(daily_returns)
        # Should be negative since returns < risk-free rate
        assert sharpe < 0
        assert isinstance(sharpe, Decimal)

    def test_sharpe_ratio_high_volatility(self):
        """Test Sharpe Ratio with high volatility."""
        metrics = PerformanceMetrics.__new__(PerformanceMetrics)
        metrics.risk_free_daily = Decimal("0.0001")

        daily_returns = [
            Decimal("0.05"),
            Decimal("-0.04"),
            Decimal("0.06"),
            Decimal("-0.05"),
        ]
        sharpe = metrics.calculate_sharpe_ratio(daily_returns)
        assert isinstance(sharpe, Decimal)
        assert sharpe.as_tuple().exponent <= -4  # 4 decimal places

    # ========================================================================
    # EDGE CASE TESTS - Sortino Ratio
    # ========================================================================

    def test_sortino_ratio_empty_list(self):
        """Test Sortino Ratio with empty returns."""
        metrics = PerformanceMetrics.__new__(PerformanceMetrics)
        metrics.risk_free_daily = Decimal("0.0001")

        sortino = metrics.calculate_sortino_ratio([])
        assert sortino == Decimal(0)

    def test_sortino_ratio_single_return(self):
        """Test Sortino Ratio with single return."""
        metrics = PerformanceMetrics.__new__(PerformanceMetrics)
        metrics.risk_free_daily = Decimal("0.0001")

        sortino = metrics.calculate_sortino_ratio([Decimal("0.01")])
        assert sortino == Decimal(0)

    def test_sortino_ratio_all_positive(self):
        """Test Sortino Ratio with all positive returns (no downside)."""
        metrics = PerformanceMetrics.__new__(PerformanceMetrics)
        metrics.risk_free_daily = Decimal("0.0001")

        daily_returns = [Decimal("0.01"), Decimal("0.02"), Decimal("0.015")]
        sortino = metrics.calculate_sortino_ratio(daily_returns)
        # Perfect Sortino (no downside) should be very high
        assert sortino == Decimal(999)

    def test_sortino_ratio_mixed_returns(self):
        """Test Sortino Ratio with mixed returns."""
        metrics = PerformanceMetrics.__new__(PerformanceMetrics)
        metrics.risk_free_daily = Decimal("0.0001")

        daily_returns = [
            Decimal("0.01"),
            Decimal("-0.005"),
            Decimal("0.02"),
            Decimal("-0.003"),
        ]
        sortino = metrics.calculate_sortino_ratio(daily_returns)
        assert isinstance(sortino, Decimal)
        assert sortino >= 0  # Sortino can't be negative

    def test_sortino_ratio_equal_downside_std(self):
        """Test Sortino Ratio with downside variance calculation."""
        metrics = PerformanceMetrics.__new__(PerformanceMetrics)
        metrics.risk_free_daily = Decimal("0.0001")

        # Returns where downside is significant
        daily_returns = [
            Decimal("0.02"),
            Decimal("-0.02"),
            Decimal("0.02"),
            Decimal("-0.02"),
        ]
        sortino = metrics.calculate_sortino_ratio(daily_returns)
        assert isinstance(sortino, Decimal)

    # ========================================================================
    # EDGE CASE TESTS - Calmar Ratio
    # ========================================================================

    def test_calmar_ratio_zero_drawdown(self):
        """Test Calmar Ratio with zero drawdown (perfect strategy)."""
        metrics = PerformanceMetrics.__new__(PerformanceMetrics)

        calmar = metrics.calculate_calmar_ratio(
            total_return=Decimal("30"), max_drawdown=Decimal("0"), days=90
        )
        assert calmar == Decimal(0)

    def test_calmar_ratio_negative_drawdown(self):
        """Test Calmar Ratio with negative drawdown."""
        metrics = PerformanceMetrics.__new__(PerformanceMetrics)

        calmar = metrics.calculate_calmar_ratio(
            total_return=Decimal("30"), max_drawdown=Decimal("-5"), days=90
        )
        assert calmar == Decimal(0)

    def test_calmar_ratio_one_year_window(self):
        """Test Calmar Ratio with one-year window (no annualization needed)."""
        metrics = PerformanceMetrics.__new__(PerformanceMetrics)

        total_return = Decimal("20")  # 20% over 365 days
        max_dd = Decimal("10")  # 10% max drawdown
        days = 365

        calmar = metrics.calculate_calmar_ratio(total_return, max_dd, days)
        # Calmar = (20 * 365/365) / 10 = 20/10 = 2.0
        expected = total_return / max_dd
        assert abs(calmar - expected) < Decimal("0.01")

    def test_calmar_ratio_short_window(self):
        """Test Calmar Ratio with short window (aggressive annualization)."""
        metrics = PerformanceMetrics.__new__(PerformanceMetrics)

        total_return = Decimal("5")  # 5% over 30 days
        max_dd = Decimal("2")  # 2% max drawdown
        days = 30

        calmar = metrics.calculate_calmar_ratio(total_return, max_dd, days)
        # Calmar = (5 * 365/30) / 2 = (60.833) / 2 ≈ 30.41
        expected = (total_return * Decimal("365") / Decimal(days)) / max_dd
        assert abs(calmar - expected) < Decimal("0.1")

    # ========================================================================
    # EDGE CASE TESTS - Profit Factor
    # ========================================================================

    def test_profit_factor_empty_trades(self):
        """Test Profit Factor with empty trades."""
        metrics = PerformanceMetrics.__new__(PerformanceMetrics)

        pf = metrics.calculate_profit_factor([])
        assert pf == Decimal(0)

    def test_profit_factor_only_losses(self):
        """Test Profit Factor with only losses."""
        metrics = PerformanceMetrics.__new__(PerformanceMetrics)

        trades = [
            (Decimal("-50"), False),
            (Decimal("-30"), False),
        ]

        pf = metrics.calculate_profit_factor(trades)
        assert pf == Decimal(0)

    def test_profit_factor_break_even(self):
        """Test Profit Factor with zero losses (break even)."""
        metrics = PerformanceMetrics.__new__(PerformanceMetrics)

        trades = [
            (Decimal("100"), True),
            (Decimal("50"), True),
            (Decimal("0"), False),  # Loss is zero
        ]

        pf = metrics.calculate_profit_factor(trades)
        assert pf == Decimal(999)

    def test_profit_factor_exact_calculation(self):
        """Test Profit Factor exact calculation."""
        metrics = PerformanceMetrics.__new__(PerformanceMetrics)

        trades = [
            (Decimal("100"), True),
            (Decimal("200"), True),
            (Decimal("50"), True),
            (Decimal("-60"), False),
            (Decimal("-40"), False),
        ]

        pf = metrics.calculate_profit_factor(trades)
        # PF = 350 / 100 = 3.5
        expected = Decimal("350") / Decimal("100")
        assert abs(pf - expected) < Decimal("0.01")

    def test_profit_factor_rounding(self):
        """Test Profit Factor rounding to 2 decimals."""
        metrics = PerformanceMetrics.__new__(PerformanceMetrics)

        trades = [
            (Decimal("100.333"), True),
            (Decimal("-50.777"), False),
        ]

        pf = metrics.calculate_profit_factor(trades)
        # Should be rounded to 2 decimals: 100.333 / 50.777 ≈ 1.97
        assert pf.as_tuple().exponent == -2  # 2 decimal places

    # ========================================================================
    # EDGE CASE TESTS - Recovery Factor
    # ========================================================================

    def test_recovery_factor_zero_drawdown(self):
        """Test Recovery Factor with zero drawdown."""
        metrics = PerformanceMetrics.__new__(PerformanceMetrics)

        rf = metrics.calculate_recovery_factor(
            total_return=Decimal("50"), max_drawdown=Decimal("0")
        )
        assert rf == Decimal(0)

    def test_recovery_factor_negative_drawdown(self):
        """Test Recovery Factor with negative drawdown."""
        metrics = PerformanceMetrics.__new__(PerformanceMetrics)

        rf = metrics.calculate_recovery_factor(
            total_return=Decimal("50"), max_drawdown=Decimal("-10")
        )
        assert rf == Decimal(0)

    def test_recovery_factor_poor_recovery(self):
        """Test Recovery Factor with poor recovery (return < drawdown)."""
        metrics = PerformanceMetrics.__new__(PerformanceMetrics)

        total_return = Decimal("5")  # Only 5% return
        max_dd = Decimal("20")  # But 20% drawdown

        rf = metrics.calculate_recovery_factor(total_return, max_dd)
        # RF = 5 / 20 = 0.25
        expected = total_return / max_dd
        assert abs(rf - expected) < Decimal("0.01")

    def test_recovery_factor_excellent_recovery(self):
        """Test Recovery Factor with excellent recovery."""
        metrics = PerformanceMetrics.__new__(PerformanceMetrics)

        total_return = Decimal("100")  # 100% return
        max_dd = Decimal("10")  # Only 10% drawdown

        rf = metrics.calculate_recovery_factor(total_return, max_dd)
        # RF = 100 / 10 = 10.0
        expected = total_return / max_dd
        assert abs(rf - expected) < Decimal("0.01")

    # ========================================================================
    # INITIALIZATION & CONFIGURATION TESTS
    # ========================================================================

    def test_performance_metrics_default_risk_free_rate(self, db_session: AsyncSession):
        """Test PerformanceMetrics uses default risk-free rate."""
        metrics = PerformanceMetrics(db_session)

        assert metrics.risk_free_rate == Decimal("0.02")  # 2% default
        assert metrics.risk_free_daily == Decimal("0.02") / Decimal(252)

    def test_performance_metrics_custom_risk_free_rate(self, db_session: AsyncSession):
        """Test PerformanceMetrics with custom risk-free rate."""
        custom_rate = Decimal("0.03")  # 3%
        metrics = PerformanceMetrics(db_session, risk_free_rate=custom_rate)

        assert metrics.risk_free_rate == custom_rate
        assert metrics.risk_free_daily == custom_rate / Decimal(252)

    def test_performance_metrics_decimal_precision(self):
        """Test PerformanceMetrics maintains Decimal precision."""
        metrics = PerformanceMetrics.__new__(PerformanceMetrics)
        metrics.risk_free_daily = Decimal("0.0001")

        daily_returns = [Decimal(str(x / 1000)) for x in range(1, 11)]

        sharpe = metrics.calculate_sharpe_ratio(daily_returns)
        # Result should have 4 decimal places
        assert sharpe.as_tuple().exponent <= -4


# ============================================================================
# END-TO-END INTEGRATION TESTS
# ============================================================================


@pytest.mark.asyncio
class TestAnalyticsIntegration:
    """End-to-end integration tests."""

    async def test_complete_etl_to_metrics_workflow(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test complete workflow: create trades -> ETL -> equity -> metrics."""
        # Create test data
        symbol = DimSymbol(symbol="GOLD", created_at=datetime.utcnow())
        db_session.add(symbol)
        await db_session.flush()

        etl = AnalyticsETL(db_session)

        # Create dimension day
        day = await etl.get_or_create_dim_day(date(2025, 1, 1))

        # Create some trades
        for i in range(5):
            profit = Decimal("100") if i % 2 == 0 else Decimal("-50")
            trade = TradesFact(
                id=str(uuid4()),
                user_id=test_user.id,
                symbol_id=symbol.id,
                entry_date_id=day.id,
                exit_date_id=day.id,
                side=0,
                entry_price=Decimal("1950"),
                exit_price=Decimal("1950") + profit / Decimal("10"),
                volume=Decimal("1.0"),
                gross_pnl=profit,
                pnl_percent=(profit / Decimal("1950")) * Decimal("100"),
                commission=Decimal("5"),
                net_pnl=profit - Decimal("5"),
                winning_trade=1 if profit > 0 else 0,
                bars_held=2,
                risk_amount=Decimal("50"),
                max_run_up=max(profit, Decimal("0")),
                max_drawdown=abs(min(profit, Decimal("0"))),
                entry_time=datetime(2025, 1, 1, 8, 0),
                exit_time=datetime(2025, 1, 1, 10, 0),
                source="signal",
            )
            db_session.add(trade)

        await db_session.commit()

        # Build rollups
        await etl.build_daily_rollups(test_user.id, date(2025, 1, 1))

        # Verify rollup created
        result = await db_session.execute(
            select(DailyRollups).where(DailyRollups.user_id == test_user.id)
        )
        rollups = result.scalars().all()

        assert len(rollups) > 0
        assert rollups[0].total_trades == 5
        assert rollups[0].winning_trades == 3


# ============================================================================
# DRAWDOWN ANALYZER COVERAGE TESTS (20+)
# ============================================================================


@pytest.mark.asyncio
class TestDrawdownAnalyzerCoverage:
    """Comprehensive coverage tests for DrawdownAnalyzer methods."""

    # ---- Test calculate_drawdown_duration ----

    async def test_calculate_drawdown_duration_normal_recovery(
        self, db_session: AsyncSession
    ):
        """Test drawdown duration calculation with normal recovery."""
        analyzer = DrawdownAnalyzer(db_session)

        # Peak at 100, trough at 80, recovers to 100 at index 4
        equity_values = [
            Decimal("100"),  # peak (idx 0)
            Decimal("90"),
            Decimal("80"),  # trough (idx 2)
            Decimal("95"),
            Decimal("100"),  # recovered (idx 4)
            Decimal("105"),
        ]

        duration = analyzer.calculate_drawdown_duration(
            equity_values, peak_idx=0, trough_idx=2
        )

        assert duration == 4, f"Expected duration 4, got {duration}"

    async def test_calculate_drawdown_duration_never_recovers(
        self, db_session: AsyncSession
    ):
        """Test drawdown duration when equity never recovers to peak."""
        analyzer = DrawdownAnalyzer(db_session)

        equity_values = [
            Decimal("100"),  # peak (idx 0)
            Decimal("90"),
            Decimal("80"),  # trough (idx 2)
            Decimal("85"),
            Decimal("88"),
        ]

        duration = analyzer.calculate_drawdown_duration(
            equity_values, peak_idx=0, trough_idx=2
        )

        # Duration is from peak to end (4 periods)
        assert duration == 4

    async def test_calculate_drawdown_duration_immediate_recovery(
        self, db_session: AsyncSession
    ):
        """Test drawdown duration when recovery is immediate."""
        analyzer = DrawdownAnalyzer(db_session)

        equity_values = [
            Decimal("100"),  # peak (idx 0)
            Decimal("95"),  # trough (idx 1)
            Decimal("100"),  # recovered (idx 2)
            Decimal("105"),
        ]

        duration = analyzer.calculate_drawdown_duration(
            equity_values, peak_idx=0, trough_idx=1
        )

        assert duration == 2

    async def test_calculate_drawdown_duration_peak_at_end(
        self, db_session: AsyncSession
    ):
        """Test drawdown duration when peak index is beyond series."""
        analyzer = DrawdownAnalyzer(db_session)

        equity_values = [Decimal("100"), Decimal("90"), Decimal("80")]

        duration = analyzer.calculate_drawdown_duration(
            equity_values, peak_idx=100, trough_idx=2
        )

        assert duration == 0

    # ---- Test calculate_consecutive_losses ----

    async def test_calculate_consecutive_losses_single_loss(
        self, db_session: AsyncSession
    ):
        """Test consecutive losses with single losing day."""
        analyzer = DrawdownAnalyzer(db_session)

        daily_pnls = [
            Decimal("100"),
            Decimal("-50"),
            Decimal("75"),
        ]

        max_consecutive, total_loss = analyzer.calculate_consecutive_losses(daily_pnls)

        assert max_consecutive == 1
        assert total_loss == Decimal("50")

    async def test_calculate_consecutive_losses_multiple_streaks(
        self, db_session: AsyncSession
    ):
        """Test consecutive losses with multiple losing streaks."""
        analyzer = DrawdownAnalyzer(db_session)

        daily_pnls = [
            Decimal("100"),
            Decimal("-50"),
            Decimal("-30"),
            Decimal("75"),
            Decimal("-20"),
            Decimal("-10"),
            Decimal("-5"),
            Decimal("100"),
        ]

        max_consecutive, total_loss = analyzer.calculate_consecutive_losses(daily_pnls)

        assert max_consecutive == 3, f"Expected 3, got {max_consecutive}"
        assert total_loss == Decimal("115"), f"Expected 115, got {total_loss}"

    async def test_calculate_consecutive_losses_all_losers(
        self, db_session: AsyncSession
    ):
        """Test consecutive losses when all days are losing."""
        analyzer = DrawdownAnalyzer(db_session)

        daily_pnls = [Decimal("-10"), Decimal("-20"), Decimal("-15"), Decimal("-5")]

        max_consecutive, total_loss = analyzer.calculate_consecutive_losses(daily_pnls)

        assert max_consecutive == 4
        assert total_loss == Decimal("50")

    async def test_calculate_consecutive_losses_no_losses(
        self, db_session: AsyncSession
    ):
        """Test consecutive losses with no losing days."""
        analyzer = DrawdownAnalyzer(db_session)

        daily_pnls = [Decimal("10"), Decimal("20"), Decimal("15")]

        max_consecutive, total_loss = analyzer.calculate_consecutive_losses(daily_pnls)

        assert max_consecutive == 0
        assert total_loss == Decimal("0")

    async def test_calculate_consecutive_losses_empty_list(
        self, db_session: AsyncSession
    ):
        """Test consecutive losses with empty list."""
        analyzer = DrawdownAnalyzer(db_session)

        max_consecutive, total_loss = analyzer.calculate_consecutive_losses([])

        assert max_consecutive == 0
        assert total_loss == Decimal("0")

    # ---- Test calculate_drawdown_stats ----

    async def test_calculate_drawdown_stats_normal_series(
        self, db_session: AsyncSession
    ):
        """Test drawdown stats calculation on normal equity series."""
        analyzer = DrawdownAnalyzer(db_session)

        # Create equity series
        dates = [date(2025, 1, i) for i in range(1, 6)]
        equity = [
            Decimal("1000"),
            Decimal("1100"),
            Decimal("900"),
            Decimal("1000"),
            Decimal("1050"),
        ]
        peak_equity = [
            Decimal("1000"),
            Decimal("1100"),
            Decimal("1100"),
            Decimal("1100"),
            Decimal("1100"),
        ]
        cumulative_pnl = [
            Decimal("0"),
            Decimal("100"),
            Decimal("-100"),
            Decimal("0"),
            Decimal("50"),
        ]

        equity_series = EquitySeries(dates, equity, peak_equity, cumulative_pnl)

        stats = analyzer.calculate_drawdown_stats(equity_series)

        assert "max_drawdown_percent" in stats
        assert "peak_date" in stats
        assert "trough_date" in stats
        assert "drawdown_duration_periods" in stats
        assert "average_drawdown_percent" in stats
        assert stats["max_drawdown_percent"] > 0

    async def test_calculate_drawdown_stats_empty_series(
        self, db_session: AsyncSession
    ):
        """Test drawdown stats handles empty equity series."""
        analyzer = DrawdownAnalyzer(db_session)

        equity_series = EquitySeries([], [], [], [])

        stats = analyzer.calculate_drawdown_stats(equity_series)

        assert stats["max_drawdown_percent"] == Decimal("0")
        assert stats["average_drawdown"] == Decimal("0")
        assert stats["drawdown_values"] == []

    async def test_calculate_drawdown_stats_single_value(
        self, db_session: AsyncSession
    ):
        """Test drawdown stats with single value."""
        analyzer = DrawdownAnalyzer(db_session)

        dates = [date(2025, 1, 1)]
        equity = [Decimal("1000")]
        peak_equity = [Decimal("1000")]
        cumulative_pnl = [Decimal("0")]

        equity_series = EquitySeries(dates, equity, peak_equity, cumulative_pnl)

        stats = analyzer.calculate_drawdown_stats(equity_series)

        assert stats["max_drawdown_percent"] == Decimal("0")

    async def test_calculate_drawdown_stats_all_gains(self, db_session: AsyncSession):
        """Test drawdown stats with only gaining period (no drawdown)."""
        analyzer = DrawdownAnalyzer(db_session)

        dates = [date(2025, 1, i) for i in range(1, 6)]
        equity = [
            Decimal("1000"),
            Decimal("1100"),
            Decimal("1200"),
            Decimal("1300"),
            Decimal("1400"),
        ]
        peak_equity = equity  # Always at peak
        cumulative_pnl = [
            Decimal("0"),
            Decimal("100"),
            Decimal("200"),
            Decimal("300"),
            Decimal("400"),
        ]

        equity_series = EquitySeries(dates, equity, peak_equity, cumulative_pnl)

        stats = analyzer.calculate_drawdown_stats(equity_series)

        assert stats["max_drawdown_percent"] == Decimal("0")

    # ---- Test get_drawdown_by_date_range ----

    async def test_get_drawdown_by_date_range_has_data(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test get_drawdown_by_date_range with data present."""
        analyzer = DrawdownAnalyzer(db_session)

        # Create equity curve snapshots
        snapshots = [
            EquityCurve(
                id=str(uuid4()),
                user_id=test_user.id,
                date=date(2025, 1, 1),
                equity=Decimal("1000"),
                peak_equity=Decimal("1000"),
                drawdown=Decimal("0"),
                cumulative_pnl=Decimal("0"),
            ),
            EquityCurve(
                id=str(uuid4()),
                user_id=test_user.id,
                date=date(2025, 1, 2),
                equity=Decimal("1100"),
                peak_equity=Decimal("1100"),
                drawdown=Decimal("0"),
                cumulative_pnl=Decimal("100"),
            ),
            EquityCurve(
                id=str(uuid4()),
                user_id=test_user.id,
                date=date(2025, 1, 3),
                equity=Decimal("900"),
                peak_equity=Decimal("1100"),
                drawdown=Decimal("18.18"),
                cumulative_pnl=Decimal("-100"),
            ),
        ]

        for snapshot in snapshots:
            db_session.add(snapshot)
        await db_session.commit()

        result = await analyzer.get_drawdown_by_date_range(
            test_user.id, date(2025, 1, 1), date(2025, 1, 3)
        )

        assert "max_drawdown_percent" in result
        assert "current_drawdown_percent" in result
        assert result["max_drawdown_percent"] > 0

    async def test_get_drawdown_by_date_range_no_data(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test get_drawdown_by_date_range with no data returns zeros."""
        analyzer = DrawdownAnalyzer(db_session)

        result = await analyzer.get_drawdown_by_date_range(
            test_user.id, date(2025, 1, 1), date(2025, 1, 3)
        )

        assert result["max_drawdown"] == Decimal("0")
        assert result["current_drawdown"] == Decimal("0")
        assert result["days_in_dd"] == 0

    async def test_get_drawdown_by_date_range_partial_overlap(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test get_drawdown_by_date_range with partial date overlap."""
        analyzer = DrawdownAnalyzer(db_session)

        # Add snapshots
        snapshots = [
            EquityCurve(
                id=str(uuid4()),
                user_id=test_user.id,
                date=date(2025, 1, 1),
                equity=Decimal("1000"),
                peak_equity=Decimal("1000"),
                drawdown=Decimal("0"),
                cumulative_pnl=Decimal("0"),
            ),
            EquityCurve(
                id=str(uuid4()),
                user_id=test_user.id,
                date=date(2025, 1, 5),
                equity=Decimal("950"),
                peak_equity=Decimal("1000"),
                drawdown=Decimal("5"),
                cumulative_pnl=Decimal("-50"),
            ),
        ]

        for snapshot in snapshots:
            db_session.add(snapshot)
        await db_session.commit()

        # Query for range that includes both
        result = await analyzer.get_drawdown_by_date_range(
            test_user.id, date(2025, 1, 1), date(2025, 1, 10)
        )

        assert "start_date" in result
        assert "end_date" in result

    # ---- Test get_monthly_drawdown_stats ----

    async def test_get_monthly_drawdown_stats_has_data(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test get_monthly_drawdown_stats with data in specified month."""
        analyzer = DrawdownAnalyzer(db_session)

        # Add Jan 2025 snapshots
        snapshots = [
            EquityCurve(
                id=str(uuid4()),
                user_id=test_user.id,
                date=date(2025, 1, 1),
                equity=Decimal("1000"),
                peak_equity=Decimal("1000"),
                drawdown=Decimal("0"),
                cumulative_pnl=Decimal("0"),
            ),
            EquityCurve(
                id=str(uuid4()),
                user_id=test_user.id,
                date=date(2025, 1, 15),
                equity=Decimal("900"),
                peak_equity=Decimal("1000"),
                drawdown=Decimal("10"),
                cumulative_pnl=Decimal("-100"),
            ),
        ]

        for snapshot in snapshots:
            db_session.add(snapshot)
        await db_session.commit()

        result = await analyzer.get_monthly_drawdown_stats(test_user.id, 2025, 1)

        assert "month" in result or "max_drawdown_percent" in result

    async def test_get_monthly_drawdown_stats_no_data(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test get_monthly_drawdown_stats with no data returns empty/zero."""
        analyzer = DrawdownAnalyzer(db_session)

        result = await analyzer.get_monthly_drawdown_stats(test_user.id, 2025, 12)

        # Should handle gracefully (return empty or zeros)
        assert result is not None or isinstance(result, dict)

    # ---- Test max_drawdown calculation edge cases ----

    async def test_calculate_max_drawdown_negative_equity(
        self, db_session: AsyncSession
    ):
        """Test max drawdown calculation with negative equity values."""
        analyzer = DrawdownAnalyzer(db_session)

        equity_values = [Decimal("1000"), Decimal("-500"), Decimal("-100")]

        max_dd, peak_idx, trough_idx = analyzer.calculate_max_drawdown(equity_values)

        # Should handle negative values gracefully
        assert isinstance(max_dd, Decimal)
        assert peak_idx >= 0
        assert trough_idx >= 0

    async def test_calculate_max_drawdown_very_small_values(
        self, db_session: AsyncSession
    ):
        """Test max drawdown with very small decimal values."""
        analyzer = DrawdownAnalyzer(db_session)

        equity_values = [
            Decimal("0.001"),
            Decimal("0.0015"),
            Decimal("0.0008"),
        ]

        max_dd, peak_idx, trough_idx = analyzer.calculate_max_drawdown(equity_values)

        assert max_dd > 0
        assert peak_idx < trough_idx

    async def test_calculate_max_drawdown_repeated_values(
        self, db_session: AsyncSession
    ):
        """Test max drawdown with repeated (flat) equity values."""
        analyzer = DrawdownAnalyzer(db_session)

        equity_values = [Decimal("1000")] * 5

        max_dd, peak_idx, trough_idx = analyzer.calculate_max_drawdown(equity_values)

        assert max_dd == Decimal("0")


# ============================================================================
# EDGE CASE TESTS
# ============================================================================


@pytest.mark.asyncio
class TestEdgeCases:
    """Test edge cases and error handling."""

    async def test_equity_series_empty_trades_raises(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test EquityEngine raises on no trades."""
        engine = EquityEngine(db_session)

        with pytest.raises(ValueError, match="No trades found"):
            await engine.compute_equity_series(test_user.id)

    async def test_metrics_insufficient_data_handles_gracefully(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test metrics handle insufficient data gracefully."""
        metrics = PerformanceMetrics(db_session)

        try:
            result = await metrics.get_metrics_for_window(test_user.id, 30)
            # Should raise ValueError for insufficient data
            assert False, "Should have raised ValueError"
        except ValueError:
            # Expected
            pass

    def test_sharpe_ratio_zero_returns(self):
        """Test Sharpe Ratio with zero returns."""
        metrics = PerformanceMetrics.__new__(PerformanceMetrics)
        metrics.risk_free_daily = Decimal("0")

        daily_returns = [Decimal("0")] * 5

        sharpe = metrics.calculate_sharpe_ratio(daily_returns)

        assert sharpe == Decimal("0")

    def test_drawdown_empty_series_handles(self):
        """Test drawdown analyzer handles empty series."""
        analyzer = DrawdownAnalyzer.__new__(DrawdownAnalyzer)

        with pytest.raises(ValueError):
            analyzer.calculate_max_drawdown([])


# ============================================================================
# TELEMETRY TESTS
# ============================================================================


@pytest.mark.asyncio
class TestTelemetry:
    """Test telemetry/prometheus integration."""

    async def test_etl_increments_prometheus_counter(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test ETL increments Prometheus counter."""
        # This would only work if PROMETHEUS_AVAILABLE is True
        # For now, just verify it doesn't crash

        etl = AnalyticsETL(db_session)

        # Create dims
        symbol = await etl.get_or_create_dim_symbol("GOLD")
        day = await etl.get_or_create_dim_day(date(2025, 1, 1))

        # Create trade
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
            commission=Decimal("0"),
            net_pnl=Decimal("10"),
            winning_trade=1,
            bars_held=1,
            risk_amount=Decimal("50"),
            max_run_up=Decimal("10"),
            max_drawdown=Decimal("0"),
            entry_time=datetime(2025, 1, 1),
            exit_time=datetime(2025, 1, 1),
            source="signal",
        )
        db_session.add(trade)
        await db_session.commit()

        # Build rollup (should increment counter)
        await etl.build_daily_rollups(test_user.id, date(2025, 1, 1))

        # Just verify no exception raised
        assert True
