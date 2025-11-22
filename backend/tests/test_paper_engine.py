"""
Tests for Paper Trading Engine

Validates fill math, slippage calculation, position tracking, and PnL accuracy.
"""

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.app.paper.engine import FillPriceMode, PaperTradingEngine, SlippageMode
from backend.app.paper.models import PaperAccount, TradeSide


@pytest.mark.asyncio
async def test_fill_order_mid_price(db_session, test_user):
    """Test order fill at mid price."""
    # Create paper account
    account = PaperAccount(
        user_id=test_user.id,
        balance=Decimal("10000"),
        equity=Decimal("10000"),
        enabled=True,
    )
    db_session.add(account)
    await db_session.commit()

    # Execute order with mid price
    engine = PaperTradingEngine(
        fill_mode=FillPriceMode.MID, slippage_mode=SlippageMode.NONE
    )
    trade = await engine.fill_order(
        db=db_session,
        account=account,
        symbol="GOLD",
        side=TradeSide.BUY,
        volume=Decimal("1.0"),
        bid=Decimal("1950.00"),
        ask=Decimal("1950.50"),
    )

    # Verify fill price is mid
    assert trade.entry_price == Decimal("1950.25")
    assert trade.slippage == Decimal("0.00")
    assert trade.symbol == "GOLD"
    assert trade.side == TradeSide.BUY
    assert trade.volume == Decimal("1.0")


@pytest.mark.asyncio
async def test_fill_order_bid_price(db_session, test_user):
    """Test order fill at bid price (sell side)."""
    account = PaperAccount(
        user_id=test_user.id,
        balance=Decimal("10000"),
        equity=Decimal("10000"),
        enabled=True,
    )
    db_session.add(account)
    await db_session.commit()

    engine = PaperTradingEngine(
        fill_mode=FillPriceMode.BID, slippage_mode=SlippageMode.NONE
    )
    trade = await engine.fill_order(
        db=db_session,
        account=account,
        symbol="GOLD",
        side=TradeSide.SELL,
        volume=Decimal("1.0"),
        bid=Decimal("1950.00"),
        ask=Decimal("1950.50"),
    )

    assert trade.entry_price == Decimal("1950.00")  # Bid price


@pytest.mark.asyncio
async def test_fill_order_ask_price(db_session, test_user):
    """Test order fill at ask price (buy side)."""
    account = PaperAccount(
        user_id=test_user.id,
        balance=Decimal("10000"),
        equity=Decimal("10000"),
        enabled=True,
    )
    db_session.add(account)
    await db_session.commit()

    engine = PaperTradingEngine(
        fill_mode=FillPriceMode.ASK, slippage_mode=SlippageMode.NONE
    )
    trade = await engine.fill_order(
        db=db_session,
        account=account,
        symbol="GOLD",
        side=TradeSide.BUY,
        volume=Decimal("1.0"),
        bid=Decimal("1950.00"),
        ask=Decimal("1950.50"),
    )

    assert trade.entry_price == Decimal("1950.50")  # Ask price


@pytest.mark.asyncio
async def test_fill_order_with_fixed_slippage(db_session, test_user):
    """Test order fill with fixed slippage."""
    account = PaperAccount(
        user_id=test_user.id,
        balance=Decimal("10000"),
        equity=Decimal("10000"),
        enabled=True,
    )
    db_session.add(account)
    await db_session.commit()

    engine = PaperTradingEngine(
        fill_mode=FillPriceMode.MID, slippage_mode=SlippageMode.FIXED, slippage_pips=2.0
    )
    trade = await engine.fill_order(
        db=db_session,
        account=account,
        symbol="GOLD",
        side=TradeSide.BUY,
        volume=Decimal("1.0"),
        bid=Decimal("1950.00"),
        ask=Decimal("1950.50"),
    )

    # Mid price + slippage (buy = positive slippage)
    # Mid = 1950.25, slippage = 2 pips * 0.01 = 0.02
    assert trade.entry_price == Decimal("1950.27")
    assert trade.slippage == Decimal("0.02")


@pytest.mark.asyncio
async def test_fill_order_with_random_slippage(db_session, test_user):
    """Test order fill with random slippage."""
    account = PaperAccount(
        user_id=test_user.id,
        balance=Decimal("10000"),
        equity=Decimal("10000"),
        enabled=True,
    )
    db_session.add(account)
    await db_session.commit()

    engine = PaperTradingEngine(
        fill_mode=FillPriceMode.MID,
        slippage_mode=SlippageMode.RANDOM,
        slippage_pips=5.0,
    )
    trade = await engine.fill_order(
        db=db_session,
        account=account,
        symbol="GOLD",
        side=TradeSide.BUY,
        volume=Decimal("1.0"),
        bid=Decimal("1950.00"),
        ask=Decimal("1950.50"),
    )

    # Slippage should be between 0 and 5 pips (0 and 0.05)
    assert trade.entry_price >= Decimal("1950.25")
    assert trade.entry_price <= Decimal("1950.30")
    assert trade.slippage >= Decimal("0.00")
    assert trade.slippage <= Decimal("0.05")


@pytest.mark.asyncio
async def test_fill_order_insufficient_balance(db_session, test_user):
    """Test order rejection due to insufficient balance."""
    account = PaperAccount(
        user_id=test_user.id,
        balance=Decimal("100"),
        equity=Decimal("100"),
        enabled=True,
    )
    db_session.add(account)
    await db_session.commit()

    engine = PaperTradingEngine(
        fill_mode=FillPriceMode.MID, slippage_mode=SlippageMode.NONE
    )

    with pytest.raises(ValueError, match="Insufficient balance"):
        await engine.fill_order(
            db=db_session,
            account=account,
            symbol="GOLD",
            side=TradeSide.BUY,
            volume=Decimal("10.0"),  # Requires 19502.50, but only 100 available
            bid=Decimal("1950.00"),
            ask=Decimal("1950.50"),
        )


@pytest.mark.asyncio
async def test_position_tracking(db_session, test_user):
    """Test position is created and tracked."""
    account = PaperAccount(
        user_id=test_user.id,
        balance=Decimal("10000"),
        equity=Decimal("10000"),
        enabled=True,
    )
    db_session.add(account)
    await db_session.commit()

    engine = PaperTradingEngine(
        fill_mode=FillPriceMode.MID, slippage_mode=SlippageMode.NONE
    )
    await engine.fill_order(
        db=db_session,
        account=account,
        symbol="GOLD",
        side=TradeSide.BUY,
        volume=Decimal("1.0"),
        bid=Decimal("1950.00"),
        ask=Decimal("1950.50"),
    )

    # Reload account with positions
    result = await db_session.execute(
        select(PaperAccount)
        .where(PaperAccount.id == account.id)
        .options(selectinload(PaperAccount.positions))
    )
    account = result.scalar_one()

    # Check position was created
    assert len(account.positions) == 1
    position = account.positions[0]
    assert position.symbol == "GOLD"
    assert position.side == TradeSide.BUY
    assert position.volume == Decimal("1.0")
    assert position.entry_price == Decimal("1950.25")
    assert position.unrealized_pnl == Decimal("0")


@pytest.mark.asyncio
async def test_position_averaging(db_session, test_user):
    """Test position averaging when adding to existing position."""
    account = PaperAccount(
        user_id=test_user.id,
        balance=Decimal("10000"),
        equity=Decimal("10000"),
        enabled=True,
    )
    db_session.add(account)
    await db_session.commit()

    engine = PaperTradingEngine(
        fill_mode=FillPriceMode.MID, slippage_mode=SlippageMode.NONE
    )

    # First order at 1950.25
    await engine.fill_order(
        db=db_session,
        account=account,
        symbol="GOLD",
        side=TradeSide.BUY,
        volume=Decimal("1.0"),
        bid=Decimal("1950.00"),
        ask=Decimal("1950.50"),
    )

    # Second order at 1960.25 (higher price)
    await engine.fill_order(
        db=db_session,
        account=account,
        symbol="GOLD",
        side=TradeSide.BUY,
        volume=Decimal("1.0"),
        bid=Decimal("1960.00"),
        ask=Decimal("1960.50"),
    )

    # Reload account with positions
    result = await db_session.execute(
        select(PaperAccount)
        .where(PaperAccount.id == account.id)
        .options(selectinload(PaperAccount.positions))
    )
    account = result.scalar_one()

    # Position should be averaged
    assert len(account.positions) == 1
    position = account.positions[0]
    assert position.volume == Decimal("2.0")
    # Average: (1950.25 * 1.0 + 1960.25 * 1.0) / 2.0 = 1955.25
    assert position.entry_price == Decimal("1955.25")


@pytest.mark.asyncio
async def test_close_position_profitable(db_session, test_user):
    """Test closing position with profit."""
    account = PaperAccount(
        user_id=test_user.id,
        balance=Decimal("10000"),
        equity=Decimal("10000"),
        enabled=True,
    )
    db_session.add(account)
    await db_session.commit()

    engine = PaperTradingEngine(
        fill_mode=FillPriceMode.MID, slippage_mode=SlippageMode.NONE
    )

    # Open position at 1950.25
    await engine.fill_order(
        db=db_session,
        account=account,
        symbol="GOLD",
        side=TradeSide.BUY,
        volume=Decimal("1.0"),
        bid=Decimal("1950.00"),
        ask=Decimal("1950.50"),
    )

    # Reload account with positions
    result = await db_session.execute(
        select(PaperAccount)
        .where(PaperAccount.id == account.id)
        .options(selectinload(PaperAccount.positions))
    )
    account = result.scalar_one()
    position = account.positions[0]
    # initial_balance = account.balance  # Removed - unused variable

    # Close position at 1960.25 (profit of 10.00 per unit)
    trade = await engine.close_position(
        db=db_session,
        account=account,
        position=position,
        bid=Decimal("1960.00"),
        ask=Decimal("1960.50"),
    )

    # Expire account to force reload of relationships
    db_session.expunge(account)

    # Reload account with positions
    result = await db_session.execute(
        select(PaperAccount)
        .where(PaperAccount.id == account.id)
        .options(selectinload(PaperAccount.positions))
    )
    account = result.scalar_one()

    # Verify PnL
    assert trade.realized_pnl == Decimal("10.00")  # (1960.25 - 1950.25) * 1.0
    assert trade.closed_at is not None

    # Verify balance updated (return margin + profit)
    # Initial balance after buy: 10000 - 1950.25 = 8049.75
    # After close: 8049.75 + 1950.25 (margin) + 10.00 (profit) = 10010.00
    assert account.balance == Decimal("10010.00")

    # Verify position removed
    assert len(account.positions) == 0


@pytest.mark.asyncio
async def test_close_position_loss(db_session, test_user):
    """Test closing position with loss."""
    account = PaperAccount(
        user_id=test_user.id,
        balance=Decimal("10000"),
        equity=Decimal("10000"),
        enabled=True,
    )
    db_session.add(account)
    await db_session.commit()

    engine = PaperTradingEngine(
        fill_mode=FillPriceMode.MID, slippage_mode=SlippageMode.NONE
    )

    # Open position at 1950.25
    await engine.fill_order(
        db=db_session,
        account=account,
        symbol="GOLD",
        side=TradeSide.BUY,
        volume=Decimal("1.0"),
        bid=Decimal("1950.00"),
        ask=Decimal("1950.50"),
    )

    # Reload account with positions
    result = await db_session.execute(
        select(PaperAccount)
        .where(PaperAccount.id == account.id)
        .options(selectinload(PaperAccount.positions))
    )
    account = result.scalar_one()
    position = account.positions[0]

    # Close position at 1940.25 (loss of 10.00 per unit)
    trade = await engine.close_position(
        db=db_session,
        account=account,
        position=position,
        bid=Decimal("1940.00"),
        ask=Decimal("1940.50"),
    )

    # Reload account with positions
    result = await db_session.execute(
        select(PaperAccount)
        .where(PaperAccount.id == account.id)
        .options(selectinload(PaperAccount.positions))
    )
    account = result.scalar_one()

    # Verify PnL
    assert trade.realized_pnl == Decimal("-10.00")  # (1940.25 - 1950.25) * 1.0

    # Verify balance updated (return margin + loss)
    # After close: 8049.75 + 1950.25 - 10.00 = 9990.00
    assert account.balance == Decimal("9990.00")


@pytest.mark.asyncio
async def test_equity_calculation(db_session, test_user):
    """Test equity calculation with unrealized PnL."""
    account = PaperAccount(
        user_id=test_user.id,
        balance=Decimal("10000"),
        equity=Decimal("10000"),
        enabled=True,
    )
    db_session.add(account)
    await db_session.commit()

    engine = PaperTradingEngine(
        fill_mode=FillPriceMode.MID, slippage_mode=SlippageMode.NONE
    )

    # Open position at 1950.25
    await engine.fill_order(
        db=db_session,
        account=account,
        symbol="GOLD",
        side=TradeSide.BUY,
        volume=Decimal("1.0"),
        bid=Decimal("1950.00"),
        ask=Decimal("1950.50"),
    )

    # Reload account with positions
    result = await db_session.execute(
        select(PaperAccount)
        .where(PaperAccount.id == account.id)
        .options(selectinload(PaperAccount.positions))
    )
    account = result.scalar_one()
    position = account.positions[0]

    # Update position price to simulate market movement
    position.current_price = Decimal("1960.25")

    # Recalculate equity
    await engine._update_account_equity(db_session, account)

    # Verify unrealized PnL
    assert position.unrealized_pnl == Decimal("10.00")  # (1960.25 - 1950.25) * 1.0

    # Verify equity = balance + unrealized PnL
    # Balance after buy: 8049.75
    # Equity: 8049.75 + 10.00 = 8059.75
    assert account.equity == Decimal("8059.75")


@pytest.mark.asyncio
async def test_sell_position_pnl(db_session, test_user):
    """Test SELL position PnL calculation (opposite of BUY)."""
    account = PaperAccount(
        user_id=test_user.id,
        balance=Decimal("10000"),
        equity=Decimal("10000"),
        enabled=True,
    )
    db_session.add(account)
    await db_session.commit()

    engine = PaperTradingEngine(
        fill_mode=FillPriceMode.MID, slippage_mode=SlippageMode.NONE
    )

    # Open SELL position at 1950.25
    await engine.fill_order(
        db=db_session,
        account=account,
        symbol="GOLD",
        side=TradeSide.SELL,
        volume=Decimal("1.0"),
        bid=Decimal("1950.00"),
        ask=Decimal("1950.50"),
    )

    # Reload account with positions
    result = await db_session.execute(
        select(PaperAccount)
        .where(PaperAccount.id == account.id)
        .options(selectinload(PaperAccount.positions))
    )
    account = result.scalar_one()
    position = account.positions[0]

    # Close position at 1940.25 (profit of 10.00 per unit for SELL)
    trade = await engine.close_position(
        db=db_session,
        account=account,
        position=position,
        bid=Decimal("1940.00"),
        ask=Decimal("1940.50"),
    )

    # Reload account with positions
    result = await db_session.execute(
        select(PaperAccount)
        .where(PaperAccount.id == account.id)
        .options(selectinload(PaperAccount.positions))
    )
    account = result.scalar_one()

    # Verify PnL
    # Entry: 1950.25, Exit: 1940.25
    # Profit = (Entry - Exit) * Volume = (1950.25 - 1940.25) * 1.0 = 10.00
    assert trade.realized_pnl == Decimal("10.00")

    # Verify balance updated
    # Initial balance after sell: 10000 - 1950.25 = 8049.75
    # After close: 8049.75 + 1950.25 (margin) + 10.00 (profit) = 10010.00
    assert account.balance == Decimal("10010.00")
