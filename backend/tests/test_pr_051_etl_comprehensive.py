"""
Comprehensive ETL tests for PR-051 to achieve 90%+ coverage.

Tests specifically for load_trades() and build_equity_curve() methods
which were not covered in the main test suite.

Coverage gaps identified:
- etl.py lines 166-308: load_trades() method
- etl.py lines 525-611: build_equity_curve() method
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.analytics.etl import AnalyticsETL
from backend.app.analytics.models import DimDay, DimSymbol, EquityCurve, TradesFact
from backend.app.auth.models import User
from backend.app.trading.store.models import Trade


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create test user."""
    user = User(
        id=str(uuid4()),
        email="etl@example.com",
        password_hash="hashed",
        telegram_user_id="99999",
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.mark.asyncio
class TestLoadTradesComprehensive:
    """Comprehensive tests for load_trades() method."""

    async def test_load_trades_basic_functionality(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test basic load_trades functionality."""
        # Create source trades
        trade1 = Trade(
            trade_id=str(uuid4()),
            user_id=test_user.id,
            symbol="GOLD",
            strategy="test",
            timeframe="H1",
            trade_type="BUY",
            direction=0,
            entry_price=Decimal("1950.00"),
            exit_price=Decimal("1960.00"),
            entry_time=datetime(2025, 1, 1, 10, 0),
            exit_time=datetime(2025, 1, 1, 14, 0),
            stop_loss=Decimal("1940.00"),
            take_profit=Decimal("1970.00"),
            volume=Decimal("1.0"),
            profit=Decimal("10.00"),
            status="CLOSED",
        )
        db_session.add(trade1)
        await db_session.commit()

        # Load trades
        etl = AnalyticsETL(db_session)
        count = await etl.load_trades(test_user.id)

        assert count == 1

        # Verify trade was loaded into trades_fact
        result = await db_session.execute(
            select(TradesFact).where(TradesFact.user_id == test_user.id)
        )
        fact_trades = result.scalars().all()

        assert len(fact_trades) == 1
        fact_trade = fact_trades[0]
        assert fact_trade.side == 0
        assert fact_trade.entry_price == Decimal("1950.00")
        assert fact_trade.exit_price == Decimal("1960.00")
        assert fact_trade.gross_pnl == Decimal("10.00")

    async def test_load_trades_idempotence(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test that load_trades is idempotent (doesn't duplicate)."""
        # Create source trade
        trade_id = str(uuid4())
        trade = Trade(
            trade_id=trade_id,
            user_id=test_user.id,
            symbol="EURUSD",
            strategy="test",
            timeframe="H1",
            trade_type="BUY",
            direction=0,
            entry_price=Decimal("1.0800"),
            exit_price=Decimal("1.0850"),
            entry_time=datetime(2025, 1, 1),
            exit_time=datetime(2025, 1, 2),
            stop_loss=Decimal("1.0700"),
            take_profit=Decimal("1.0900"),
            volume=Decimal("1.0"),
            profit=Decimal("50.00"),
            status="CLOSED",
        )
        db_session.add(trade)
        await db_session.commit()

        etl = AnalyticsETL(db_session)

        # Load first time
        count1 = await etl.load_trades(test_user.id)
        assert count1 == 1

        # Load again (should skip duplicate)
        count2 = await etl.load_trades(test_user.id)
        assert count2 == 0

        # Verify only one record exists
        result = await db_session.execute(
            select(TradesFact).where(TradesFact.id == trade_id)
        )
        fact_trades = result.scalars().all()
        assert len(fact_trades) == 1

    async def test_load_trades_only_closed_status(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test that only closed trades are loaded."""
        # Create open trade
        trade_open = Trade(
            trade_id=str(uuid4()),
            user_id=test_user.id,
            symbol="GOLD",
            strategy="test",
            timeframe="H1",
            trade_type="BUY",
            direction=0,
            entry_price=Decimal("1950.00"),
            entry_time=datetime(2025, 1, 1),
            stop_loss=Decimal("1940.00"),
            take_profit=Decimal("1970.00"),
            volume=Decimal("1.0"),
            status="open",  # Not closed
        )
        db_session.add(trade_open)

        # Create closed trade
        trade_closed = Trade(
            trade_id=str(uuid4()),
            user_id=test_user.id,
            symbol="GOLD",
            strategy="test",
            timeframe="H1",
            trade_type="BUY",
            direction=0,
            entry_price=Decimal("1950.00"),
            exit_price=Decimal("1960.00"),
            entry_time=datetime(2025, 1, 1),
            exit_time=datetime(2025, 1, 2),
            stop_loss=Decimal("1940.00"),
            take_profit=Decimal("1970.00"),
            volume=Decimal("1.0"),
            profit=Decimal("10.00"),
            status="CLOSED",
        )
        db_session.add(trade_closed)
        await db_session.commit()

        etl = AnalyticsETL(db_session)
        count = await etl.load_trades(test_user.id)

        assert count == 1  # Only closed trade loaded

    async def test_load_trades_calculates_pnl_for_buy(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test PnL calculation for BUY trades."""
        trade = Trade(
            trade_id=str(uuid4()),
            user_id=test_user.id,
            symbol="GOLD",
            strategy="test",
            timeframe="H1",
            trade_type="BUY",
            direction=0,
            entry_price=Decimal("1950.00"),
            exit_price=Decimal("1960.00"),
            entry_time=datetime(2025, 1, 1),
            exit_time=datetime(2025, 1, 2),
            volume=Decimal("2.0"),
            profit=Decimal("20.00"),
            status="CLOSED",
        )
        db_session.add(trade)
        await db_session.commit()

        etl = AnalyticsETL(db_session)
        await etl.load_trades(test_user.id)

        result = await db_session.execute(
            select(TradesFact).where(TradesFact.user_id == test_user.id)
        )
        fact_trade = result.scalars().first()

        # PnL = (exit - entry) * volume = (1960 - 1950) * 2 = 20
        assert fact_trade.gross_pnl == Decimal("20.00")
        assert fact_trade.winning_trade == 1

    async def test_load_trades_calculates_pnl_for_sell(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test PnL calculation for SELL trades."""
        trade = Trade(
            trade_id=str(uuid4()),
            user_id=test_user.id,
            symbol="GOLD",
            strategy="test",
            timeframe="H1",
            trade_type="SELL",
            direction=1,
            entry_price=Decimal("1960.00"),
            exit_price=Decimal("1955.00"),
            entry_time=datetime(2025, 1, 1),
            exit_time=datetime(2025, 1, 2),
            volume=Decimal("1.0"),
            profit=Decimal("5.00"),
            status="CLOSED",
        )
        db_session.add(trade)
        await db_session.commit()

        etl = AnalyticsETL(db_session)
        await etl.load_trades(test_user.id)

        result = await db_session.execute(
            select(TradesFact).where(TradesFact.user_id == test_user.id)
        )
        fact_trade = result.scalars().first()

        # For SELL: price_diff negated
        # (1955 - 1960) = -5, negated = 5 * 1 = 5
        assert fact_trade.gross_pnl == Decimal("5.00")
        assert fact_trade.winning_trade == 1

    async def test_load_trades_calculates_r_multiple(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test R-multiple calculation."""
        trade = Trade(
            trade_id=str(uuid4()),
            user_id=test_user.id,
            symbol="GOLD",
            strategy="test",
            timeframe="H1",
            trade_type="BUY",
            direction=0,
            entry_price=Decimal("1950.00"),
            exit_price=Decimal("1970.00"),  # Reward: 20
            stop_loss=Decimal("1940.00"),  # Risk: 10
            entry_time=datetime(2025, 1, 1),
            exit_time=datetime(2025, 1, 2),
            volume=Decimal("1.0"),
            profit=Decimal("20.00"),
            status="CLOSED",
        )
        db_session.add(trade)
        await db_session.commit()

        etl = AnalyticsETL(db_session)
        await etl.load_trades(test_user.id)

        result = await db_session.execute(
            select(TradesFact).where(TradesFact.user_id == test_user.id)
        )
        fact_trade = result.scalars().first()

        # R = reward / risk = 20 / 10 = 2.0
        assert fact_trade.r_multiple == Decimal("2.0")

    async def test_load_trades_handles_missing_stop_loss(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test trade without stop loss (r_multiple should be None)."""
        trade = Trade(
            trade_id=str(uuid4()),
            user_id=test_user.id,
            symbol="GOLD",
            strategy="test",
            timeframe="H1",
            trade_type="BUY",
            direction=0,
            entry_price=Decimal("1950.00"),
            exit_price=Decimal("1960.00"),
            entry_time=datetime(2025, 1, 1),
            exit_time=datetime(2025, 1, 2),
            volume=Decimal("1.0"),
            profit=Decimal("10.00"),
            status="CLOSED",
            stop_loss=Decimal("1.0000"),  # No stop loss
        )
        db_session.add(trade)
        await db_session.commit()

        etl = AnalyticsETL(db_session)
        await etl.load_trades(test_user.id)

        result = await db_session.execute(
            select(TradesFact).where(TradesFact.user_id == test_user.id)
        )
        fact_trade = result.scalars().first()

        assert fact_trade.r_multiple is None

    async def test_load_trades_since_filter(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test loading trades with 'since' filter."""
        # Create old trade
        trade_old = Trade(
            trade_id=str(uuid4()),
            user_id=test_user.id,
            symbol="GOLD",
            strategy="test",
            timeframe="H1",
            trade_type="BUY",
            direction=0,
            entry_price=Decimal("1950.00"),
            exit_price=Decimal("1960.00"),
            entry_time=datetime(2025, 1, 1),
            exit_time=datetime(2025, 1, 2),
            volume=Decimal("1.0"),
            profit=Decimal("10.00"),
            status="CLOSED",
        )
        db_session.add(trade_old)

        # Create new trade
        trade_new = Trade(
            trade_id=str(uuid4()),
            user_id=test_user.id,
            symbol="GOLD",
            strategy="test",
            timeframe="H1",
            trade_type="BUY",
            direction=0,
            entry_price=Decimal("1960.00"),
            exit_price=Decimal("1970.00"),
            entry_time=datetime(2025, 1, 10),
            exit_time=datetime(2025, 1, 11),
            volume=Decimal("1.0"),
            profit=Decimal("10.00"),
            status="CLOSED",
        )
        db_session.add(trade_new)
        await db_session.commit()

        etl = AnalyticsETL(db_session)
        # Load only trades after Jan 5
        count = await etl.load_trades(test_user.id, since=datetime(2025, 1, 5))

        assert count == 1  # Only new trade loaded

    async def test_load_trades_creates_dimensions(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test that load_trades creates dimension records."""
        trade = Trade(
            trade_id=str(uuid4()),
            user_id=test_user.id,
            symbol="BTCUSD",
            strategy="test",
            timeframe="H1",
            trade_type="BUY",
            direction=0,
            entry_price=Decimal("50000.00"),
            exit_price=Decimal("51000.00"),
            entry_time=datetime(2025, 2, 15, 10, 0),
            exit_time=datetime(2025, 2, 16, 14, 0),
            volume=Decimal("0.1"),
            profit=Decimal("100.00"),
            status="CLOSED",
        )
        db_session.add(trade)
        await db_session.commit()

        etl = AnalyticsETL(db_session)
        await etl.load_trades(test_user.id)

        # Verify symbol dimension was created
        result = await db_session.execute(
            select(DimSymbol).where(DimSymbol.symbol == "BTCUSD")
        )
        symbol = result.scalars().first()
        assert symbol is not None
        assert symbol.symbol == "BTCUSD"

        # Verify day dimensions were created
        result = await db_session.execute(
            select(DimDay).where(DimDay.date == date(2025, 2, 15))
        )
        entry_day = result.scalars().first()
        assert entry_day is not None

        result = await db_session.execute(
            select(DimDay).where(DimDay.date == date(2025, 2, 16))
        )
        exit_day = result.scalars().first()
        assert exit_day is not None


@pytest.mark.asyncio
class TestBuildEquityCurveComprehensive:
    """Comprehensive tests for build_equity_curve() method."""

    async def test_build_equity_curve_basic(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test basic equity curve building."""
        # Create ETL and dimensions
        etl = AnalyticsETL(db_session)
        symbol = await etl.get_or_create_dim_symbol("GOLD")
        day1 = await etl.get_or_create_dim_day(date(2025, 1, 1))
        day2 = await etl.get_or_create_dim_day(date(2025, 1, 2))
        day3 = await etl.get_or_create_dim_day(date(2025, 1, 3))

        # Create trades
        trades_data = [
            (day1.id, day1.id, Decimal("100")),  # Day 1: +100
            (day2.id, day2.id, Decimal("-50")),  # Day 2: -50
            (day3.id, day3.id, Decimal("75")),  # Day 3: +75
        ]

        for entry_day_id, exit_day_id, pnl in trades_data:
            trade = TradesFact(
                id=str(uuid4()),
                user_id=test_user.id,
                symbol_id=symbol.id,
                entry_date_id=entry_day_id,
                exit_date_id=exit_day_id,
                side=0,
                entry_price=Decimal("1950"),
                exit_price=Decimal("1960"),
                volume=Decimal("1.0"),
                gross_pnl=pnl,
                pnl_percent=Decimal("0"),
                commission=Decimal("0"),
                net_pnl=pnl,
                winning_trade=1 if pnl > 0 else 0,
                bars_held=1,
                risk_amount=Decimal("10"),
                max_run_up=Decimal("0"),
                max_drawdown=Decimal("0"),
                entry_time=datetime(2025, 1, 1),
                exit_time=datetime(2025, 1, 1),
                source="signal",
            )
            db_session.add(trade)
        await db_session.commit()

        # Build equity curve
        count = await etl.build_equity_curve(
            test_user.id, initial_balance=Decimal("10000")
        )

        assert count == 3

        # Verify equity snapshots
        result = await db_session.execute(
            select(EquityCurve)
            .where(EquityCurve.user_id == test_user.id)
            .order_by(EquityCurve.date)
        )
        snapshots = result.scalars().all()

        assert len(snapshots) == 3

        # Day 1: 10000 + 100 = 10100
        assert snapshots[0].equity == Decimal("10100")
        assert snapshots[0].cumulative_pnl == Decimal("100")
        assert snapshots[0].daily_change == Decimal("100")

        # Day 2: 10100 - 50 = 10050
        assert snapshots[1].equity == Decimal("10050")
        assert snapshots[1].cumulative_pnl == Decimal("50")
        assert snapshots[1].daily_change == Decimal("-50")

        # Day 3: 10050 + 75 = 10125
        assert snapshots[2].equity == Decimal("10125")
        assert snapshots[2].cumulative_pnl == Decimal("125")
        assert snapshots[2].daily_change == Decimal("75")

    async def test_build_equity_curve_tracks_peak(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test that equity curve tracks peak equity correctly."""
        etl = AnalyticsETL(db_session)
        symbol = await etl.get_or_create_dim_symbol("GOLD")
        day1 = await etl.get_or_create_dim_day(date(2025, 1, 1))
        day2 = await etl.get_or_create_dim_day(date(2025, 1, 2))
        day3 = await etl.get_or_create_dim_day(date(2025, 1, 3))

        # Create trades: up, down, up again
        trades_data = [
            (day1.id, Decimal("500")),  # Peak
            (day2.id, Decimal("-200")),  # Drawdown
            (day3.id, Decimal("100")),  # Recovery (but below peak)
        ]

        for exit_day_id, pnl in trades_data:
            trade = TradesFact(
                id=str(uuid4()),
                user_id=test_user.id,
                symbol_id=symbol.id,
                entry_date_id=exit_day_id,
                exit_date_id=exit_day_id,
                side=0,
                entry_price=Decimal("1950"),
                exit_price=Decimal("1960"),
                volume=Decimal("1.0"),
                gross_pnl=pnl,
                pnl_percent=Decimal("0"),
                commission=Decimal("0"),
                net_pnl=pnl,
                winning_trade=1 if pnl > 0 else 0,
                bars_held=1,
                risk_amount=Decimal("10"),
                max_run_up=Decimal("0"),
                max_drawdown=Decimal("0"),
                entry_time=datetime(2025, 1, 1),
                exit_time=datetime(2025, 1, 1),
                source="signal",
            )
            db_session.add(trade)
        await db_session.commit()

        await etl.build_equity_curve(test_user.id, initial_balance=Decimal("10000"))

        result = await db_session.execute(
            select(EquityCurve)
            .where(EquityCurve.user_id == test_user.id)
            .order_by(EquityCurve.date)
        )
        snapshots = result.scalars().all()

        # Peak should be set at day 1 and maintained
        assert snapshots[0].peak_equity == Decimal("10500")  # Initial peak
        assert snapshots[1].peak_equity == Decimal("10500")  # Peak maintained
        assert snapshots[2].peak_equity == Decimal("10500")  # Peak still maintained

    async def test_build_equity_curve_calculates_drawdown(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test that drawdown is calculated correctly."""
        etl = AnalyticsETL(db_session)
        symbol = await etl.get_or_create_dim_symbol("GOLD")
        day1 = await etl.get_or_create_dim_day(date(2025, 1, 1))
        day2 = await etl.get_or_create_dim_day(date(2025, 1, 2))

        # Create trades: up then down
        for exit_day_id, pnl in [
            (day1.id, Decimal("1000")),
            (day2.id, Decimal("-500")),
        ]:
            trade = TradesFact(
                id=str(uuid4()),
                user_id=test_user.id,
                symbol_id=symbol.id,
                entry_date_id=exit_day_id,
                exit_date_id=exit_day_id,
                side=0,
                entry_price=Decimal("1950"),
                exit_price=Decimal("1960"),
                volume=Decimal("1.0"),
                gross_pnl=pnl,
                pnl_percent=Decimal("0"),
                commission=Decimal("0"),
                net_pnl=pnl,
                winning_trade=1 if pnl > 0 else 0,
                bars_held=1,
                risk_amount=Decimal("10"),
                max_run_up=Decimal("0"),
                max_drawdown=Decimal("0"),
                entry_time=datetime(2025, 1, 1),
                exit_time=datetime(2025, 1, 1),
                source="signal",
            )
            db_session.add(trade)
        await db_session.commit()

        await etl.build_equity_curve(test_user.id, initial_balance=Decimal("10000"))

        result = await db_session.execute(
            select(EquityCurve)
            .where(EquityCurve.user_id == test_user.id)
            .order_by(EquityCurve.date)
        )
        snapshots = result.scalars().all()

        # Day 1: No drawdown (at peak)
        assert snapshots[0].drawdown == Decimal("0")

        # Day 2: Drawdown = (11000 - 10500) / 11000 * 100 = 4.545%
        expected_dd = (
            (Decimal("11000") - Decimal("10500")) / Decimal("11000") * Decimal("100")
        )
        assert abs(snapshots[1].drawdown - expected_dd) < Decimal("0.01")

    async def test_build_equity_curve_idempotence(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test that build_equity_curve is idempotent."""
        etl = AnalyticsETL(db_session)
        symbol = await etl.get_or_create_dim_symbol("GOLD")
        day1 = await etl.get_or_create_dim_day(date(2025, 1, 1))

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
            gross_pnl=Decimal("100"),
            pnl_percent=Decimal("0"),
            commission=Decimal("0"),
            net_pnl=Decimal("100"),
            winning_trade=1,
            bars_held=1,
            risk_amount=Decimal("10"),
            max_run_up=Decimal("0"),
            max_drawdown=Decimal("0"),
            entry_time=datetime(2025, 1, 1),
            exit_time=datetime(2025, 1, 1),
            source="signal",
        )
        db_session.add(trade)
        await db_session.commit()

        # Build first time
        count1 = await etl.build_equity_curve(test_user.id)
        assert count1 == 1

        # Build again (should skip existing)
        count2 = await etl.build_equity_curve(test_user.id)
        assert count2 == 0

        # Verify only one snapshot
        result = await db_session.execute(
            select(EquityCurve).where(EquityCurve.user_id == test_user.id)
        )
        snapshots = result.scalars().all()
        assert len(snapshots) == 1

    async def test_build_equity_curve_no_trades(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test equity curve with no trades."""
        etl = AnalyticsETL(db_session)
        count = await etl.build_equity_curve(test_user.id)

        assert count == 0

    async def test_build_equity_curve_custom_initial_balance(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test equity curve with custom initial balance."""
        etl = AnalyticsETL(db_session)
        symbol = await etl.get_or_create_dim_symbol("GOLD")
        day1 = await etl.get_or_create_dim_day(date(2025, 1, 1))

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
            gross_pnl=Decimal("250"),
            pnl_percent=Decimal("0"),
            commission=Decimal("0"),
            net_pnl=Decimal("250"),
            winning_trade=1,
            bars_held=1,
            risk_amount=Decimal("10"),
            max_run_up=Decimal("0"),
            max_drawdown=Decimal("0"),
            entry_time=datetime(2025, 1, 1),
            exit_time=datetime(2025, 1, 1),
            source="signal",
        )
        db_session.add(trade)
        await db_session.commit()

        # Use custom initial balance
        await etl.build_equity_curve(test_user.id, initial_balance=Decimal("5000"))

        result = await db_session.execute(
            select(EquityCurve).where(EquityCurve.user_id == test_user.id)
        )
        snapshot = result.scalars().first()

        # Equity = 5000 + 250 = 5250
        assert snapshot.equity == Decimal("5250")
        assert snapshot.cumulative_pnl == Decimal("250")
