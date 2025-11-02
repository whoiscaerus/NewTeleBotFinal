"""
PR-043: Positions Service Unit Tests

Tests for PositionsService methods:
- Position fetching from MT5
- Cache TTL behavior
- Portfolio aggregation and P&L calculations
- Error handling (connection failures, empty positions, etc.)
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from backend.app.core.errors import NotFoundError, ValidationError

# Fixtures imported from conftest_pr_043.py


# ============================================================================
# FETCHING POSITIONS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_positions_fresh_fetch(positions_service, linked_account):
    """Test fetching fresh positions from MT5."""
    # Mock MT5 positions
    positions_service.mt5.get_positions = AsyncMock(
        return_value=[
            {
                "ticket": "1001",
                "symbol": "EURUSD",
                "type": "buy",
                "volume": 1.0,
                "open_price": 1.0950,
                "current_price": 1.0980,
                "sl": 1.0900,
                "tp": 1.1050,
                "pnl_points": 30,
                "pnl": 300.00,
                "pnl_percent": 3.0,
                "open_time": datetime.utcnow(),
            },
            {
                "ticket": "1002",
                "symbol": "GBPUSD",
                "type": "sell",
                "volume": 0.5,
                "open_price": 1.2750,
                "current_price": 1.2700,
                "sl": 1.2800,
                "tp": 1.2600,
                "pnl_points": 50,
                "pnl": 250.00,
                "pnl_percent": 2.0,
                "open_time": datetime.utcnow(),
            },
        ]
    )

    # Fetch positions
    portfolio = await positions_service.get_positions(
        linked_account.id, force_refresh=True
    )

    assert portfolio.account_id == linked_account.id
    assert portfolio.open_positions_count == 2
    assert len(portfolio.positions) == 2
    assert portfolio.total_pnl_usd == pytest.approx(550.00)  # 300 + 250
    assert portfolio.total_pnl_percent == pytest.approx(5.5)  # 550 / 10000 * 100


@pytest.mark.asyncio
async def test_get_positions_no_positions(positions_service, linked_account):
    """Test fetching when no positions are open."""
    # Mock empty positions
    positions_service.mt5.get_positions = AsyncMock(return_value=[])

    # Fetch positions
    portfolio = await positions_service.get_positions(
        linked_account.id, force_refresh=True
    )

    assert portfolio.open_positions_count == 0
    assert len(portfolio.positions) == 0
    assert portfolio.total_pnl_usd == 0
    assert portfolio.total_pnl_percent == 0


@pytest.mark.asyncio
async def test_get_positions_cache_hit(positions_service, linked_account):
    """Test cached positions are returned if fresh."""
    # Mock MT5 positions
    positions_service.mt5.get_positions = AsyncMock(
        return_value=[
            {
                "ticket": "1001",
                "symbol": "EURUSD",
                "type": "buy",
                "volume": 1.0,
                "open_price": 1.0950,
                "current_price": 1.0980,
                "sl": 1.0900,
                "tp": 1.1050,
                "pnl_points": 30,
                "pnl": 300.00,
                "pnl_percent": 3.0,
                "open_time": datetime.utcnow(),
            }
        ]
    )

    # Fetch positions (fresh)
    portfolio1 = await positions_service.get_positions(
        linked_account.id, force_refresh=True
    )

    # Fetch again (should use cache)
    portfolio2 = await positions_service.get_positions(
        linked_account.id, force_refresh=False
    )

    # MT5 should only be called once
    assert positions_service.mt5.get_positions.call_count == 1

    assert portfolio1.total_pnl_usd == portfolio2.total_pnl_usd


@pytest.mark.asyncio
async def test_get_positions_cache_expired(
    positions_service, db_session, linked_account
):
    """Test cache TTL expiry triggers fresh fetch."""
    # Mock MT5 positions
    positions_service.mt5.get_positions = AsyncMock(
        return_value=[
            {
                "ticket": "1001",
                "symbol": "EURUSD",
                "type": "buy",
                "volume": 1.0,
                "open_price": 1.0950,
                "current_price": 1.0980,
                "sl": 1.0900,
                "tp": 1.1050,
                "pnl_points": 30,
                "pnl": 300.00,
                "pnl_percent": 3.0,
                "open_time": datetime.utcnow(),
            }
        ]
    )

    # Fetch positions (fresh)
    portfolio1 = await positions_service.get_positions(
        linked_account.id, force_refresh=True
    )

    # Manually expire cache by setting updated_at to past
    from sqlalchemy import select

    result = await db_session.execute(
        select(Position).where(Position.account_link_id == linked_account.id)
    )
    positions = result.scalars().all()

    for pos in positions:
        pos.updated_at = datetime.utcnow() - timedelta(seconds=60)
        db_session.add(pos)

    await db_session.commit()

    # Mock new prices
    positions_service.mt5.get_positions = AsyncMock(
        return_value=[
            {
                "ticket": "1001",
                "symbol": "EURUSD",
                "type": "buy",
                "volume": 1.0,
                "open_price": 1.0950,
                "current_price": 1.1000,  # Updated price
                "sl": 1.0900,
                "tp": 1.1050,
                "pnl_points": 50,
                "pnl": 500.00,  # Updated P&L
                "pnl_percent": 5.0,
                "open_time": datetime.utcnow(),
            }
        ]
    )

    # Fetch again (cache expired, should fetch fresh)
    portfolio2 = await positions_service.get_positions(
        linked_account.id, force_refresh=False
    )

    # Should fetch fresh from MT5
    assert positions_service.mt5.get_positions.call_count == 2


@pytest.mark.asyncio
async def test_get_positions_force_refresh(positions_service, linked_account):
    """Test force_refresh bypasses cache."""
    # Mock MT5 positions
    positions_service.mt5.get_positions = AsyncMock(
        return_value=[
            {
                "ticket": "1001",
                "symbol": "EURUSD",
                "type": "buy",
                "volume": 1.0,
                "open_price": 1.0950,
                "current_price": 1.0980,
                "sl": 1.0900,
                "tp": 1.1050,
                "pnl_points": 30,
                "pnl": 300.00,
                "pnl_percent": 3.0,
                "open_time": datetime.utcnow(),
            }
        ]
    )

    # Fetch positions (fresh)
    await positions_service.get_positions(linked_account.id, force_refresh=True)

    initial_calls = positions_service.mt5.get_positions.call_count

    # Fetch with force_refresh
    await positions_service.get_positions(linked_account.id, force_refresh=True)

    # Should fetch again, ignoring cache
    assert positions_service.mt5.get_positions.call_count == initial_calls + 1


@pytest.mark.asyncio
async def test_get_positions_mt5_failure(positions_service, linked_account):
    """Test MT5 connection failure handling."""
    # Mock MT5 to fail
    positions_service.mt5.get_positions = AsyncMock(
        side_effect=Exception("MT5 connection failed")
    )

    with pytest.raises(ValidationError, match="Failed to fetch"):
        await positions_service.get_positions(linked_account.id, force_refresh=True)


@pytest.mark.asyncio
async def test_get_positions_invalid_account(positions_service):
    """Test fetching positions for non-existent account fails."""
    fake_id = str(uuid4())

    with pytest.raises(NotFoundError):
        await positions_service.get_positions(fake_id, force_refresh=True)


# ============================================================================
# USER POSITIONS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_user_positions_with_primary_account(
    positions_service, linked_account, test_user
):
    """Test getting positions for user's primary account."""
    # Mock MT5 positions
    positions_service.mt5.get_positions = AsyncMock(
        return_value=[
            {
                "ticket": "1001",
                "symbol": "EURUSD",
                "type": "buy",
                "volume": 1.0,
                "open_price": 1.0950,
                "current_price": 1.0980,
                "sl": 1.0900,
                "tp": 1.1050,
                "pnl_points": 30,
                "pnl": 300.00,
                "pnl_percent": 3.0,
                "open_time": datetime.utcnow(),
            }
        ]
    )

    # Get user's positions
    portfolio = await positions_service.get_user_positions(test_user.id)

    assert portfolio.account_id == linked_account.id
    assert portfolio.open_positions_count == 1
    assert portfolio.total_pnl_usd == 300.00


@pytest.mark.asyncio
async def test_get_user_positions_no_primary_account(positions_service, test_user):
    """Test getting positions fails when user has no primary account."""
    with pytest.raises(NotFoundError, match="No primary account"):
        await positions_service.get_user_positions(test_user.id)


# ============================================================================
# PORTFOLIO AGGREGATION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_portfolio_pnl_calculations(positions_service, linked_account):
    """Test portfolio P&L aggregation is accurate."""
    # Mock MT5 positions with various P&L
    positions_service.mt5.get_positions = AsyncMock(
        return_value=[
            {
                "ticket": "1001",
                "symbol": "EURUSD",
                "type": "buy",
                "volume": 1.0,
                "open_price": 1.0950,
                "current_price": 1.0980,
                "sl": 1.0900,
                "tp": 1.1050,
                "pnl_points": 30,
                "pnl": 300.00,  # +300
                "pnl_percent": 3.0,
                "open_time": datetime.utcnow(),
            },
            {
                "ticket": "1002",
                "symbol": "GBPUSD",
                "type": "sell",
                "volume": 0.5,
                "open_price": 1.2750,
                "current_price": 1.2700,
                "sl": 1.2800,
                "tp": 1.2600,
                "pnl_points": 50,
                "pnl": 250.00,  # +250
                "pnl_percent": 2.0,
                "open_time": datetime.utcnow(),
            },
            {
                "ticket": "1003",
                "symbol": "USDJPY",
                "type": "buy",
                "volume": 2.0,
                "open_price": 110.50,
                "current_price": 110.30,
                "sl": 110.00,
                "tp": 111.00,
                "pnl_points": -20,
                "pnl": -400.00,  # -400
                "pnl_percent": -4.0,
                "open_time": datetime.utcnow(),
            },
        ]
    )

    # Fetch positions
    portfolio = await positions_service.get_positions(
        linked_account.id, force_refresh=True
    )

    # Total P&L = 300 + 250 - 400 = 150
    assert portfolio.total_pnl_usd == pytest.approx(150.00)
    # P&L % = 150 / 10000 * 100 = 1.5%
    assert portfolio.total_pnl_percent == pytest.approx(1.5)


@pytest.mark.asyncio
async def test_portfolio_account_info(positions_service, linked_account):
    """Test portfolio includes correct account info."""
    # Mock MT5 positions
    positions_service.mt5.get_positions = AsyncMock(return_value=[])

    # Mock account info has equity info
    positions_service.accounts.mt5.get_account_info = AsyncMock(
        return_value={
            "account": "12345678",
            "balance": 10000.00,
            "equity": 9500.00,
            "free_margin": 4500.00,
            "margin_used": 5000.00,
            "margin_level": 190.0,
            "open_positions": 0,
        }
    )

    # Fetch positions
    portfolio = await positions_service.get_positions(
        linked_account.id, force_refresh=True
    )

    assert portfolio.balance == 10000.00
    assert portfolio.equity == 9500.00
    assert portfolio.free_margin == 4500.00
    assert portfolio.margin_level == 190.0


# ============================================================================
# POSITION DATA STORAGE TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_positions_stored_in_database(
    positions_service, db_session, linked_account
):
    """Test positions are stored in database after fetching."""
    # Mock MT5 positions
    positions_service.mt5.get_positions = AsyncMock(
        return_value=[
            {
                "ticket": "1001",
                "symbol": "EURUSD",
                "type": "buy",
                "volume": 1.0,
                "open_price": 1.0950,
                "current_price": 1.0980,
                "sl": 1.0900,
                "tp": 1.1050,
                "pnl_points": 30,
                "pnl": 300.00,
                "pnl_percent": 3.0,
                "open_time": datetime.utcnow(),
            }
        ]
    )

    # Fetch positions
    await positions_service.get_positions(linked_account.id, force_refresh=True)

    # Query database
    from sqlalchemy import select

    result = await db_session.execute(
        select(Position).where(Position.account_link_id == linked_account.id)
    )
    stored_positions = result.scalars().all()

    assert len(stored_positions) == 1
    assert stored_positions[0].ticket == "1001"
    assert stored_positions[0].instrument == "EURUSD"
    assert stored_positions[0].pnl_usd == 300.00


@pytest.mark.asyncio
async def test_position_fields_populated_correctly(
    positions_service, db_session, linked_account
):
    """Test all position fields are populated correctly."""
    now = datetime.utcnow()

    # Mock MT5 position
    positions_service.mt5.get_positions = AsyncMock(
        return_value=[
            {
                "ticket": "1001",
                "symbol": "EURUSD",
                "type": "buy",
                "volume": 1.5,
                "open_price": 1.0950,
                "current_price": 1.0980,
                "sl": 1.0900,
                "tp": 1.1050,
                "pnl_points": 30,
                "pnl": 450.00,
                "pnl_percent": 4.5,
                "open_time": now,
            }
        ]
    )

    # Fetch positions
    await positions_service.get_positions(linked_account.id, force_refresh=True)

    # Query database
    from sqlalchemy import select

    result = await db_session.execute(
        select(Position).where(Position.account_link_id == linked_account.id)
    )
    position = result.scalar()

    assert position.ticket == "1001"
    assert position.instrument == "EURUSD"
    assert position.side == 0  # buy
    assert position.volume == 1.5
    assert position.entry_price == 1.0950
    assert position.current_price == 1.0980
    assert position.stop_loss == 1.0900
    assert position.take_profit == 1.1050
    assert position.pnl_points == 30
    assert position.pnl_usd == 450.00
    assert position.pnl_percent == pytest.approx(4.5)


# ============================================================================
# EDGE CASES TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_position_with_no_sl_tp(positions_service, linked_account):
    """Test position without stop loss/take profit."""
    # Mock position with no SL/TP
    positions_service.mt5.get_positions = AsyncMock(
        return_value=[
            {
                "ticket": "1001",
                "symbol": "EURUSD",
                "type": "buy",
                "volume": 1.0,
                "open_price": 1.0950,
                "current_price": 1.0980,
                "sl": None,
                "tp": None,
                "pnl_points": 30,
                "pnl": 300.00,
                "pnl_percent": 3.0,
                "open_time": datetime.utcnow(),
            }
        ]
    )

    # Fetch positions
    portfolio = await positions_service.get_positions(
        linked_account.id, force_refresh=True
    )

    position = portfolio.positions[0]
    assert position.stop_loss is None
    assert position.take_profit is None


@pytest.mark.asyncio
async def test_position_with_sell_side(positions_service, linked_account):
    """Test sell position (side = 1)."""
    # Mock sell position
    positions_service.mt5.get_positions = AsyncMock(
        return_value=[
            {
                "ticket": "1001",
                "symbol": "EURUSD",
                "type": "sell",
                "volume": 1.0,
                "open_price": 1.1000,
                "current_price": 1.0950,
                "sl": 1.1100,
                "tp": 1.0850,
                "pnl_points": 50,
                "pnl": 500.00,
                "pnl_percent": 5.0,
                "open_time": datetime.utcnow(),
            }
        ]
    )

    # Fetch positions
    portfolio = await positions_service.get_positions(
        linked_account.id, force_refresh=True
    )

    position = portfolio.positions[0]
    assert position.side == 1  # sell
    assert position.pnl_usd == 500.00


@pytest.mark.asyncio
async def test_portfolio_with_negative_pnl(positions_service, linked_account):
    """Test portfolio with all losing positions."""
    # Mock losing positions
    positions_service.mt5.get_positions = AsyncMock(
        return_value=[
            {
                "ticket": "1001",
                "symbol": "EURUSD",
                "type": "buy",
                "volume": 1.0,
                "open_price": 1.0950,
                "current_price": 1.0900,
                "sl": 1.1000,
                "tp": 1.1000,
                "pnl_points": -50,
                "pnl": -500.00,
                "pnl_percent": -5.0,
                "open_time": datetime.utcnow(),
            },
            {
                "ticket": "1002",
                "symbol": "GBPUSD",
                "type": "sell",
                "volume": 1.0,
                "open_price": 1.2700,
                "current_price": 1.2800,
                "sl": 1.2600,
                "tp": 1.2600,
                "pnl_points": -100,
                "pnl": -1000.00,
                "pnl_percent": -10.0,
                "open_time": datetime.utcnow(),
            },
        ]
    )

    # Fetch positions
    portfolio = await positions_service.get_positions(
        linked_account.id, force_refresh=True
    )

    assert portfolio.total_pnl_usd == pytest.approx(-1500.00)
    assert portfolio.total_pnl_percent == pytest.approx(-15.0)
