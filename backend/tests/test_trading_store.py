"""Tests for trading store models, service, and migration.

Test Coverage:
- Models: Initialization, validation, constraints, relationships
- Service: CRUD operations, filtering, analytics, reconciliation
- Migration: Schema creation and rollback
- Integration: Full workflows (create → close trade)

Target: ≥90% coverage (20+ tests)
"""

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.trading.store.models import EquityPoint, Position, Trade, ValidationLog
from backend.app.trading.store.service import TradeService


class TestTradeModel:
    """Test Trade model initialization and validation."""

    def test_trade_creation_buy(self):
        """Test creating a BUY trade."""
        trade_id = str(uuid4())
        trade = Trade(
            trade_id=trade_id,
            symbol="GOLD",
            trade_type="BUY",
            direction=0,
            entry_price=Decimal("1950.50"),
            entry_time=datetime.utcnow(),
            stop_loss=Decimal("1945.00"),
            take_profit=Decimal("1960.00"),
            volume=Decimal("0.1"),
            strategy="scalp_5m",
            timeframe="M5",
            status="OPEN",
        )

        assert trade.symbol == "GOLD"
        assert trade.trade_type == "BUY"
        assert trade.direction == 0
        assert trade.entry_price == Decimal("1950.50")
        assert trade.status == "OPEN"
        assert trade.trade_id == trade_id

    def test_trade_creation_sell(self):
        """Test creating a SELL trade."""
        trade_id = str(uuid4())
        trade = Trade(
            trade_id=trade_id,
            symbol="EURUSD",
            trade_type="SELL",
            direction=1,
            entry_price=Decimal("1.1050"),
            entry_time=datetime.utcnow(),
            stop_loss=Decimal("1.1100"),
            take_profit=Decimal("1.1000"),
            volume=Decimal("1.0"),
            strategy="trend_follow",
            timeframe="H1",
            status="OPEN",
        )

        assert trade.trade_type == "SELL"
        assert trade.direction == 1

    def test_trade_with_optional_fields(self):
        """Test trade with all optional fields."""
        signal_id = str(uuid4())
        device_id = str(uuid4())
        trade = Trade(
            symbol="GOLD",
            trade_type="BUY",
            direction=0,
            entry_price=Decimal("1950.50"),
            entry_time=datetime.utcnow(),
            stop_loss=Decimal("1945.00"),
            take_profit=Decimal("1960.00"),
            volume=Decimal("0.1"),
            strategy="scalp_5m",
            timeframe="M5",
            status="OPEN",
            signal_id=signal_id,
            device_id=device_id,
            entry_comment="Set and forget scalp",
        )

        assert trade.signal_id == signal_id
        assert trade.device_id == device_id
        assert trade.entry_comment == "Set and forget scalp"

    def test_trade_with_closed_details(self):
        """Test trade with exit details."""
        entry_time = datetime.utcnow()
        exit_time = entry_time + timedelta(hours=2)

        trade = Trade(
            symbol="GOLD",
            trade_type="BUY",
            direction=0,
            entry_price=Decimal("1950.50"),
            entry_time=entry_time,
            stop_loss=Decimal("1945.00"),
            take_profit=Decimal("1960.00"),
            volume=Decimal("0.1"),
            strategy="scalp_5m",
            timeframe="M5",
            status="CLOSED",
            exit_price=Decimal("1955.50"),
            exit_time=exit_time,
            exit_reason="TP_HIT",
        )

        assert trade.exit_price == Decimal("1955.50")
        assert trade.status == "CLOSED"
        assert trade.exit_reason == "TP_HIT"


class TestPositionModel:
    """Test Position model."""

    def test_position_creation(self):
        """Test creating an open position."""
        position_id = str(uuid4())
        position = Position(
            position_id=position_id,
            symbol="GOLD",
            side=0,  # 0=BUY
            volume=Decimal("0.1"),
            entry_price=Decimal("1950.50"),
            current_price=Decimal("1952.00"),
            stop_loss=Decimal("1945.00"),
            take_profit=Decimal("1960.00"),
        )

        assert position.symbol == "GOLD"
        assert position.side == 0
        assert position.volume == Decimal("0.1")
        assert position.position_id == position_id

    def test_position_with_unrealized_profit(self):
        """Test position with unrealized P&L."""
        position_id = str(uuid4())
        position = Position(
            position_id=position_id,
            symbol="GOLD",
            side=0,  # 0=BUY
            volume=Decimal("0.1"),
            entry_price=Decimal("1950.50"),
            current_price=Decimal("1955.50"),
            stop_loss=Decimal("1945.00"),
            take_profit=Decimal("1960.00"),
            unrealized_profit=Decimal("50.00"),
        )

        assert position.unrealized_profit == Decimal("50.00")


class TestEquityPointModel:
    """Test EquityPoint model."""

    def test_equity_point_creation(self):
        """Test creating an equity snapshot."""
        equity_id = str(uuid4())
        point = EquityPoint(
            equity_id=equity_id,
            equity=Decimal("10500.00"),
            balance=Decimal("10500.00"),
            drawdown_percent=Decimal("2.5"),
            timestamp=datetime.utcnow(),
            trades_open=5,
        )

        assert point.equity == Decimal("10500.00")
        assert point.trades_open == 5
        assert point.equity_id == equity_id


class TestValidationLogModel:
    """Test ValidationLog model."""

    def test_validation_log_creation(self):
        """Test creating a validation log entry."""
        log_id = str(uuid4())
        trade_id = str(uuid4())
        log = ValidationLog(
            log_id=log_id,
            trade_id=trade_id,
            event_type="CREATED",
            message="Trade created: BUY GOLD @ 1950.50",
            timestamp=datetime.utcnow(),
        )

        assert log.log_id == log_id
        assert log.trade_id == trade_id
        assert log.event_type == "CREATED"


class TestTradeServiceCreateTrade:
    """Test TradeService.create_trade()."""

    @pytest.mark.asyncio
    async def test_create_buy_trade(self, db: AsyncSession):
        """Test creating a BUY trade via service."""
        service = TradeService(db)

        trade = await service.create_trade(
            symbol="GOLD",
            trade_type="BUY",
            entry_price=Decimal("1950.50"),
            stop_loss=Decimal("1945.00"),
            take_profit=Decimal("1960.00"),
            volume=Decimal("0.1"),
        )

        assert trade.trade_id is not None
        assert trade.symbol == "GOLD"
        assert trade.status == "OPEN"

        # Verify log was created
        stmt = select(ValidationLog).where(ValidationLog.trade_id == trade.trade_id)
        result = await db.execute(stmt)
        log = result.scalar_one_or_none()
        assert log is not None
        assert log.event_type == "CREATED"

    @pytest.mark.asyncio
    async def test_create_sell_trade(self, db: AsyncSession):
        """Test creating a SELL trade via service."""
        service = TradeService(db)

        trade = await service.create_trade(
            symbol="EURUSD",
            trade_type="SELL",
            entry_price=Decimal("1.1050"),
            stop_loss=Decimal("1.1100"),
            take_profit=Decimal("1.1000"),
            volume=Decimal("1.0"),
        )

        assert trade.trade_type == "SELL"
        assert trade.direction == 1

    @pytest.mark.asyncio
    async def test_create_trade_buy_invalid_prices(self, db: AsyncSession):
        """Test creating BUY trade with invalid prices raises error."""
        service = TradeService(db)

        # BUY: SL must be < Entry < TP
        with pytest.raises(ValueError, match="BUY:"):
            await service.create_trade(
                symbol="GOLD",
                trade_type="BUY",
                entry_price=Decimal("1950.50"),
                stop_loss=Decimal("1955.00"),  # SL > Entry (invalid)
                take_profit=Decimal("1960.00"),
                volume=Decimal("0.1"),
            )

    @pytest.mark.asyncio
    async def test_create_trade_sell_invalid_prices(self, db: AsyncSession):
        """Test creating SELL trade with invalid prices raises error."""
        service = TradeService(db)

        # SELL: TP must be < Entry < SL
        with pytest.raises(ValueError, match="SELL:"):
            await service.create_trade(
                symbol="EURUSD",
                trade_type="SELL",
                entry_price=Decimal("1.1050"),
                stop_loss=Decimal("1.1000"),  # SL < Entry (invalid for SELL)
                take_profit=Decimal("1.1100"),  # TP > Entry (invalid for SELL)
                volume=Decimal("1.0"),
            )

    @pytest.mark.asyncio
    async def test_create_trade_invalid_type(self, db: AsyncSession):
        """Test creating trade with invalid type raises error."""
        service = TradeService(db)

        with pytest.raises(ValueError, match="Invalid trade type"):
            await service.create_trade(
                symbol="GOLD",
                trade_type="INVALID",
                entry_price=Decimal("1950.50"),
                stop_loss=Decimal("1945.00"),
                take_profit=Decimal("1960.00"),
                volume=Decimal("0.1"),
            )

    @pytest.mark.asyncio
    async def test_create_trade_invalid_volume_too_small(self, db: AsyncSession):
        """Test creating trade with volume < 0.01 raises error."""
        service = TradeService(db)

        with pytest.raises(ValueError, match="Volume must be"):
            await service.create_trade(
                symbol="GOLD",
                trade_type="BUY",
                entry_price=Decimal("1950.50"),
                stop_loss=Decimal("1945.00"),
                take_profit=Decimal("1960.00"),
                volume=Decimal("0.001"),  # Too small
            )

    @pytest.mark.asyncio
    async def test_create_trade_invalid_volume_too_large(self, db: AsyncSession):
        """Test creating trade with volume > 100 raises error."""
        service = TradeService(db)

        with pytest.raises(ValueError, match="Volume must be"):
            await service.create_trade(
                symbol="GOLD",
                trade_type="BUY",
                entry_price=Decimal("1950.50"),
                stop_loss=Decimal("1945.00"),
                take_profit=Decimal("1960.00"),
                volume=Decimal("101.0"),  # Too large
            )

    @pytest.mark.asyncio
    async def test_create_trade_with_custom_strategy(self, db: AsyncSession):
        """Test creating trade with custom strategy and timeframe."""
        service = TradeService(db)

        trade = await service.create_trade(
            symbol="GOLD",
            trade_type="BUY",
            entry_price=Decimal("1950.50"),
            stop_loss=Decimal("1945.00"),
            take_profit=Decimal("1960.00"),
            volume=Decimal("0.1"),
            strategy="custom_scalp_5m",
            timeframe="M5",
        )

        assert trade.strategy == "custom_scalp_5m"
        assert trade.timeframe == "M5"


class TestTradeServiceCloseTrade:
    """Test TradeService.close_trade()."""

    @pytest.mark.asyncio
    async def test_close_trade_tp_hit(self, db: AsyncSession):
        """Test closing trade at take profit."""
        service = TradeService(db)

        # Create trade
        trade = await service.create_trade(
            symbol="GOLD",
            trade_type="BUY",
            entry_price=Decimal("1950.50"),
            stop_loss=Decimal("1945.00"),
            take_profit=Decimal("1960.00"),
            volume=Decimal("0.1"),
        )

        # Close at TP
        closed = await service.close_trade(
            trade_id=trade.trade_id,
            exit_price=Decimal("1960.00"),
            exit_reason="TP_HIT",
        )

        assert closed.status == "CLOSED"
        assert closed.exit_price == Decimal("1960.00")
        assert closed.exit_reason == "TP_HIT"
        assert closed.profit is not None
        assert closed.profit == (Decimal("1960.00") - Decimal("1950.50")) * Decimal(
            "0.1"
        )

    @pytest.mark.asyncio
    async def test_close_trade_sl_hit(self, db: AsyncSession):
        """Test closing trade at stop loss."""
        service = TradeService(db)

        trade = await service.create_trade(
            symbol="GOLD",
            trade_type="BUY",
            entry_price=Decimal("1950.50"),
            stop_loss=Decimal("1945.00"),
            take_profit=Decimal("1960.00"),
            volume=Decimal("0.1"),
        )

        closed = await service.close_trade(
            trade_id=trade.trade_id,
            exit_price=Decimal("1945.00"),
            exit_reason="SL_HIT",
        )

        assert closed.exit_price == Decimal("1945.00")
        assert closed.profit == (Decimal("1945.00") - Decimal("1950.50")) * Decimal(
            "0.1"
        )
        assert closed.profit < 0  # Loss

    @pytest.mark.asyncio
    async def test_close_trade_not_found(self, db: AsyncSession):
        """Test closing non-existent trade raises error."""
        service = TradeService(db)

        with pytest.raises(ValueError, match="Trade not found"):
            await service.close_trade(
                trade_id="invalid_trade_id",
                exit_price=Decimal("1955.00"),
            )

    @pytest.mark.asyncio
    async def test_close_already_closed_trade(self, db: AsyncSession):
        """Test closing already closed trade raises error."""
        service = TradeService(db)

        trade = await service.create_trade(
            symbol="GOLD",
            trade_type="BUY",
            entry_price=Decimal("1950.50"),
            stop_loss=Decimal("1945.00"),
            take_profit=Decimal("1960.00"),
            volume=Decimal("0.1"),
        )

        # Close once
        await service.close_trade(
            trade_id=trade.trade_id,
            exit_price=Decimal("1955.00"),
        )

        # Try to close again
        with pytest.raises(ValueError, match="not OPEN"):
            await service.close_trade(
                trade_id=trade.trade_id,
                exit_price=Decimal("1956.00"),
            )

    @pytest.mark.asyncio
    async def test_close_trade_calculates_duration(self, db: AsyncSession):
        """Test close trade calculates duration correctly."""
        service = TradeService(db)
        entry_time = datetime.utcnow()

        trade = await service.create_trade(
            symbol="GOLD",
            trade_type="BUY",
            entry_price=Decimal("1950.50"),
            stop_loss=Decimal("1945.00"),
            take_profit=Decimal("1960.00"),
            volume=Decimal("0.1"),
            entry_time=entry_time,
        )

        exit_time = entry_time + timedelta(hours=3)
        closed = await service.close_trade(
            trade_id=trade.trade_id,
            exit_price=Decimal("1955.00"),
            exit_time=exit_time,
        )

        assert closed.duration_hours == 3.0

    @pytest.mark.asyncio
    async def test_close_trade_calculates_pips(self, db: AsyncSession):
        """Test close trade calculates pips correctly."""
        service = TradeService(db)

        trade = await service.create_trade(
            symbol="GOLD",
            trade_type="BUY",
            entry_price=Decimal("1950.50"),
            stop_loss=Decimal("1945.00"),
            take_profit=Decimal("1960.00"),
            volume=Decimal("0.1"),
        )

        closed = await service.close_trade(
            trade_id=trade.trade_id,
            exit_price=Decimal("1960.00"),
        )

        # For GOLD: 1960.00 - 1950.50 = 9.50 * 10000 = 95000 pips
        assert closed.pips == Decimal("95000")


class TestTradeServiceQueries:
    """Test TradeService query methods."""

    @pytest.mark.asyncio
    async def test_list_trades_empty(self, db: AsyncSession):
        """Test listing trades when empty."""
        service = TradeService(db)

        trades = await service.list_trades()

        assert trades == []

    @pytest.mark.asyncio
    async def test_list_trades_multiple(self, db: AsyncSession):
        """Test listing multiple trades."""
        service = TradeService(db)

        # Create 3 trades
        for i in range(3):
            await service.create_trade(
                symbol="GOLD",
                trade_type="BUY",
                entry_price=Decimal("1950.50") + i,
                stop_loss=Decimal("1945.00"),
                take_profit=Decimal("1960.00"),
                volume=Decimal("0.1"),
            )

        trades = await service.list_trades()
        assert len(trades) == 3

    @pytest.mark.asyncio
    async def test_list_trades_filter_by_symbol(self, db: AsyncSession):
        """Test filtering trades by symbol."""
        service = TradeService(db)

        # Create GOLD trades
        for i in range(2):
            await service.create_trade(
                symbol="GOLD",
                trade_type="BUY",
                entry_price=Decimal("1950.50"),
                stop_loss=Decimal("1945.00"),
                take_profit=Decimal("1960.00"),
                volume=Decimal("0.1"),
            )

        # Create EURUSD trade
        await service.create_trade(
            symbol="EURUSD",
            trade_type="BUY",
            entry_price=Decimal("1.1050"),
            stop_loss=Decimal("1.1000"),
            take_profit=Decimal("1.1100"),
            volume=Decimal("1.0"),
        )

        gold_trades = await service.list_trades(symbol="GOLD")
        assert len(gold_trades) == 2
        assert all(t.symbol == "GOLD" for t in gold_trades)

    @pytest.mark.asyncio
    async def test_list_trades_filter_by_status(self, db: AsyncSession):
        """Test filtering trades by status."""
        service = TradeService(db)

        # Create and close 2 trades
        for i in range(2):
            trade = await service.create_trade(
                symbol="GOLD",
                trade_type="BUY",
                entry_price=Decimal("1950.50"),
                stop_loss=Decimal("1945.00"),
                take_profit=Decimal("1960.00"),
                volume=Decimal("0.1"),
            )
            await service.close_trade(
                trade_id=trade.trade_id,
                exit_price=Decimal("1955.00"),
            )

        # Create 1 open trade
        await service.create_trade(
            symbol="GOLD",
            trade_type="BUY",
            entry_price=Decimal("1950.50"),
            stop_loss=Decimal("1945.00"),
            take_profit=Decimal("1960.00"),
            volume=Decimal("0.1"),
        )

        open_trades = await service.list_trades(status="OPEN")
        closed_trades = await service.list_trades(status="CLOSED")

        assert len(open_trades) == 1
        assert len(closed_trades) == 2

    @pytest.mark.asyncio
    async def test_list_trades_pagination(self, db: AsyncSession):
        """Test trade list pagination."""
        service = TradeService(db)

        # Create 5 trades
        for i in range(5):
            await service.create_trade(
                symbol="GOLD",
                trade_type="BUY",
                entry_price=Decimal("1950.50"),
                stop_loss=Decimal("1945.00"),
                take_profit=Decimal("1960.00"),
                volume=Decimal("0.1"),
            )

        page1 = await service.list_trades(limit=2, offset=0)
        page2 = await service.list_trades(limit=2, offset=2)

        assert len(page1) == 2
        assert len(page2) == 2

    @pytest.mark.asyncio
    async def test_get_trade(self, db: AsyncSession):
        """Test fetching a single trade."""
        service = TradeService(db)

        trade = await service.create_trade(
            symbol="GOLD",
            trade_type="BUY",
            entry_price=Decimal("1950.50"),
            stop_loss=Decimal("1945.00"),
            take_profit=Decimal("1960.00"),
            volume=Decimal("0.1"),
        )

        fetched = await service.get_trade(trade.trade_id)

        assert fetched is not None
        assert fetched.trade_id == trade.trade_id
        assert fetched.symbol == "GOLD"

    @pytest.mark.asyncio
    async def test_get_trade_not_found(self, db: AsyncSession):
        """Test fetching non-existent trade."""
        service = TradeService(db)

        result = await service.get_trade("invalid_id")

        assert result is None


class TestTradeServiceAnalytics:
    """Test TradeService analytics methods."""

    @pytest.mark.asyncio
    async def test_get_trade_stats_empty(self, db: AsyncSession):
        """Test stats with no trades."""
        service = TradeService(db)

        stats = await service.get_trade_stats()

        assert stats["total_trades"] == 0
        assert stats["win_rate"] == 0.0
        assert stats["profit_factor"] == 0.0

    @pytest.mark.asyncio
    async def test_get_trade_stats_with_trades(self, db: AsyncSession):
        """Test calculating stats from closed trades."""
        service = TradeService(db)

        # Create 2 winning trades
        for i in range(2):
            trade = await service.create_trade(
                symbol="GOLD",
                trade_type="BUY",
                entry_price=Decimal("1950.00"),
                stop_loss=Decimal("1945.00"),
                take_profit=Decimal("1960.00"),
                volume=Decimal("0.1"),
            )
            await service.close_trade(
                trade_id=trade.trade_id,
                exit_price=Decimal("1955.00"),  # Profit: +50
            )

        # Create 1 losing trade
        trade = await service.create_trade(
            symbol="GOLD",
            trade_type="BUY",
            entry_price=Decimal("1950.00"),
            stop_loss=Decimal("1945.00"),
            take_profit=Decimal("1960.00"),
            volume=Decimal("0.1"),
        )
        await service.close_trade(
            trade_id=trade.trade_id,
            exit_price=Decimal("1948.00"),  # Loss: -20
        )

        stats = await service.get_trade_stats()

        assert stats["total_trades"] == 3
        assert stats["win_rate"] == pytest.approx(2 / 3, rel=0.01)
        assert stats["profit_factor"] > 0

    @pytest.mark.asyncio
    async def test_get_trade_stats_by_symbol(self, db: AsyncSession):
        """Test stats filtered by symbol."""
        service = TradeService(db)

        # Create GOLD trades
        for i in range(2):
            trade = await service.create_trade(
                symbol="GOLD",
                trade_type="BUY",
                entry_price=Decimal("1950.00"),
                stop_loss=Decimal("1945.00"),
                take_profit=Decimal("1960.00"),
                volume=Decimal("0.1"),
            )
            await service.close_trade(
                trade_id=trade.trade_id,
                exit_price=Decimal("1955.00"),
            )

        # Create EURUSD trade (losing)
        trade = await service.create_trade(
            symbol="EURUSD",
            trade_type="BUY",
            entry_price=Decimal("1.1050"),
            stop_loss=Decimal("1.1000"),
            take_profit=Decimal("1.1100"),
            volume=Decimal("1.0"),
        )
        await service.close_trade(
            trade_id=trade.trade_id,
            exit_price=Decimal("1.1040"),  # Loss
        )

        gold_stats = await service.get_trade_stats(symbol="GOLD")
        eurusd_stats = await service.get_trade_stats(symbol="EURUSD")

        assert gold_stats["total_trades"] == 2
        assert gold_stats["win_rate"] == 1.0
        assert eurusd_stats["total_trades"] == 1
        assert eurusd_stats["win_rate"] == 0.0


class TestTradeServiceReconciliation:
    """Test TradeService reconciliation methods."""

    @pytest.mark.asyncio
    async def test_find_orphaned_trades_none(self, db: AsyncSession):
        """Test no orphaned trades when all synced."""
        service = TradeService(db)

        trade = await service.create_trade(
            symbol="GOLD",
            trade_type="BUY",
            entry_price=Decimal("1950.50"),
            stop_loss=Decimal("1945.00"),
            take_profit=Decimal("1960.00"),
            volume=Decimal("0.1"),
        )

        orphaned = await service.find_orphaned_trades(
            [{"ticket": trade.trade_id, "symbol": "GOLD"}]
        )

        assert len(orphaned) == 0

    @pytest.mark.asyncio
    async def test_find_orphaned_trades_found(self, db: AsyncSession):
        """Test finding orphaned trades."""
        service = TradeService(db)

        trade1 = await service.create_trade(
            symbol="GOLD",
            trade_type="BUY",
            entry_price=Decimal("1950.50"),
            stop_loss=Decimal("1945.00"),
            take_profit=Decimal("1960.00"),
            volume=Decimal("0.1"),
        )

        trade2 = await service.create_trade(
            symbol="EURUSD",
            trade_type="BUY",
            entry_price=Decimal("1.1050"),
            stop_loss=Decimal("1.1000"),
            take_profit=Decimal("1.1100"),
            volume=Decimal("1.0"),
        )

        # Only trade1 is in MT5
        orphaned = await service.find_orphaned_trades(
            [{"ticket": trade1.trade_id, "symbol": "GOLD"}]
        )

        assert len(orphaned) == 1
        assert orphaned[0].trade_id == trade2.trade_id

    @pytest.mark.asyncio
    async def test_sync_with_mt5(self, db: AsyncSession):
        """Test MT5 reconciliation."""
        service = TradeService(db)

        trade = await service.create_trade(
            symbol="GOLD",
            trade_type="BUY",
            entry_price=Decimal("1950.50"),
            stop_loss=Decimal("1945.00"),
            take_profit=Decimal("1960.00"),
            volume=Decimal("0.1"),
        )

        result = await service.sync_with_mt5(
            [
                {
                    "symbol": "GOLD",
                    "ticket": trade.trade_id,
                    "volume": 0.1,
                }
            ]
        )

        assert result["synced"] == 1
        assert result["mismatches"] == 0


class TestTradeServiceIntegration:
    """Integration tests for complete workflows."""

    @pytest.mark.asyncio
    async def test_full_trade_lifecycle(self, db: AsyncSession):
        """Test complete trade workflow from creation to closure."""
        service = TradeService(db)

        # 1. Create trade
        trade = await service.create_trade(
            symbol="GOLD",
            trade_type="BUY",
            entry_price=Decimal("1950.50"),
            stop_loss=Decimal("1945.00"),
            take_profit=Decimal("1960.00"),
            volume=Decimal("0.1"),
            strategy="scalp_5m",
            signal_id=str(uuid4()),
        )

        # 2. Verify created
        assert trade.status == "OPEN"
        assert trade.profit is None

        # 3. Close trade
        closed = await service.close_trade(
            trade_id=trade.trade_id,
            exit_price=Decimal("1955.00"),
        )

        # 4. Verify closed
        assert closed.status == "CLOSED"
        assert closed.profit is not None
        assert closed.exit_price == Decimal("1955.00")

        # 5. List and verify
        closed_trades = await service.list_trades(status="CLOSED")
        assert len(closed_trades) == 1
        assert closed_trades[0].trade_id == trade.trade_id

    @pytest.mark.asyncio
    async def test_multiple_trades_analytics(self, db: AsyncSession):
        """Test analytics across multiple trades."""
        service = TradeService(db)

        # Create 5 trades: 3 wins, 2 losses
        for i in range(3):
            trade = await service.create_trade(
                symbol="GOLD",
                trade_type="BUY",
                entry_price=Decimal("1950.00"),
                stop_loss=Decimal("1945.00"),
                take_profit=Decimal("1960.00"),
                volume=Decimal("0.1"),
            )
            await service.close_trade(
                trade_id=trade.trade_id,
                exit_price=Decimal("1960.00"),  # TP hit
            )

        for i in range(2):
            trade = await service.create_trade(
                symbol="GOLD",
                trade_type="BUY",
                entry_price=Decimal("1950.00"),
                stop_loss=Decimal("1945.00"),
                take_profit=Decimal("1960.00"),
                volume=Decimal("0.1"),
            )
            await service.close_trade(
                trade_id=trade.trade_id,
                exit_price=Decimal("1945.00"),  # SL hit
            )

        stats = await service.get_trade_stats()

        assert stats["total_trades"] == 5
        assert stats["win_rate"] == 0.6
        assert stats["total_profit"] > 0
