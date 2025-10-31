"""Tests for Position Monitor Service (PR-104 Phase 4).

Tests the breach detection logic that monitors open positions and
creates close commands when hidden owner SL/TP levels are hit.
"""

from uuid import uuid4

import pytest

from backend.app.trading.positions.models import OpenPosition, PositionStatus
from backend.app.trading.positions.monitor import (
    check_position_breach,
    close_position,
    get_open_positions,
    get_position_by_id,
)


@pytest.mark.asyncio
async def test_buy_position_sl_breach():
    """Test SL breach detection for BUY position.

    BUY position: SL hit when price drops to or below owner_sl.
    """
    position = OpenPosition(
        id=str(uuid4()),
        execution_id=str(uuid4()),
        signal_id=str(uuid4()),
        approval_id=str(uuid4()),
        user_id=str(uuid4()),
        device_id=str(uuid4()),
        instrument="XAUUSD",
        side=0,  # BUY
        entry_price=2655.00,
        volume=0.1,
        owner_sl=2645.00,  # Hidden SL
        owner_tp=2670.00,  # Hidden TP
        status=PositionStatus.OPEN.value,
    )

    # Price drops below SL → breach detected
    result = await check_position_breach(position, 2643.00)
    assert result == "sl_hit"

    # Price exactly at SL → breach detected
    result = await check_position_breach(position, 2645.00)
    assert result == "sl_hit"

    # Price above SL but below TP → no breach
    result = await check_position_breach(position, 2660.00)
    assert result is None


@pytest.mark.asyncio
async def test_buy_position_tp_breach():
    """Test TP breach detection for BUY position.

    BUY position: TP hit when price rises to or above owner_tp.
    """
    position = OpenPosition(
        id=str(uuid4()),
        execution_id=str(uuid4()),
        signal_id=str(uuid4()),
        approval_id=str(uuid4()),
        user_id=str(uuid4()),
        device_id=str(uuid4()),
        instrument="XAUUSD",
        side=0,  # BUY
        entry_price=2655.00,
        volume=0.1,
        owner_sl=2645.00,
        owner_tp=2670.00,  # Hidden TP
        status=PositionStatus.OPEN.value,
    )

    # Price rises above TP → breach detected
    result = await check_position_breach(position, 2672.00)
    assert result == "tp_hit"

    # Price exactly at TP → breach detected
    result = await check_position_breach(position, 2670.00)
    assert result == "tp_hit"

    # Price below TP → no breach
    result = await check_position_breach(position, 2665.00)
    assert result is None


@pytest.mark.asyncio
async def test_sell_position_sl_breach():
    """Test SL breach detection for SELL position.

    SELL position: SL hit when price rises to or above owner_sl.
    """
    position = OpenPosition(
        id=str(uuid4()),
        execution_id=str(uuid4()),
        signal_id=str(uuid4()),
        approval_id=str(uuid4()),
        user_id=str(uuid4()),
        device_id=str(uuid4()),
        instrument="EURUSD",
        side=1,  # SELL
        entry_price=1.0850,
        volume=0.5,
        owner_sl=1.0870,  # Hidden SL (above entry for SELL)
        owner_tp=1.0820,  # Hidden TP (below entry for SELL)
        status=PositionStatus.OPEN.value,
    )

    # Price rises above SL → breach detected
    result = await check_position_breach(position, 1.0875)
    assert result == "sl_hit"

    # Price exactly at SL → breach detected
    result = await check_position_breach(position, 1.0870)
    assert result == "sl_hit"

    # Price below SL but above TP → no breach
    result = await check_position_breach(position, 1.0840)
    assert result is None


@pytest.mark.asyncio
async def test_sell_position_tp_breach():
    """Test TP breach detection for SELL position.

    SELL position: TP hit when price drops to or below owner_tp.
    """
    position = OpenPosition(
        id=str(uuid4()),
        execution_id=str(uuid4()),
        signal_id=str(uuid4()),
        approval_id=str(uuid4()),
        user_id=str(uuid4()),
        device_id=str(uuid4()),
        instrument="EURUSD",
        side=1,  # SELL
        entry_price=1.0850,
        volume=0.5,
        owner_sl=1.0870,
        owner_tp=1.0820,  # Hidden TP
        status=PositionStatus.OPEN.value,
    )

    # Price drops below TP → breach detected
    result = await check_position_breach(position, 1.0815)
    assert result == "tp_hit"

    # Price exactly at TP → breach detected
    result = await check_position_breach(position, 1.0820)
    assert result == "tp_hit"

    # Price above TP → no breach
    result = await check_position_breach(position, 1.0830)
    assert result is None


@pytest.mark.asyncio
async def test_position_with_no_owner_levels():
    """Test position with NULL owner_sl and owner_tp.

    If no hidden levels are set, no breach can be detected.
    Monitor should skip these positions.
    """
    position = OpenPosition(
        id=str(uuid4()),
        execution_id=str(uuid4()),
        signal_id=str(uuid4()),
        approval_id=str(uuid4()),
        user_id=str(uuid4()),
        device_id=str(uuid4()),
        instrument="XAUUSD",
        side=0,
        entry_price=2655.00,
        volume=0.1,
        owner_sl=None,  # No hidden SL
        owner_tp=None,  # No hidden TP
        status=PositionStatus.OPEN.value,
    )

    # No breach possible without levels
    result = await check_position_breach(position, 2600.00)
    assert result is None

    result = await check_position_breach(position, 2700.00)
    assert result is None


@pytest.mark.asyncio
async def test_position_with_only_sl_set():
    """Test position with only owner_sl (no TP).

    Should detect SL breach but not TP breach.
    """
    position = OpenPosition(
        id=str(uuid4()),
        execution_id=str(uuid4()),
        signal_id=str(uuid4()),
        approval_id=str(uuid4()),
        user_id=str(uuid4()),
        device_id=str(uuid4()),
        instrument="XAUUSD",
        side=0,  # BUY
        entry_price=2655.00,
        volume=0.1,
        owner_sl=2645.00,  # Only SL set
        owner_tp=None,  # No TP
        status=PositionStatus.OPEN.value,
    )

    # SL breach detected
    result = await check_position_breach(position, 2643.00)
    assert result == "sl_hit"

    # No TP breach (no TP set)
    result = await check_position_breach(position, 2700.00)
    assert result is None


@pytest.mark.asyncio
async def test_get_open_positions(db_session):
    """Test retrieving all open positions for monitoring."""
    user_id = str(uuid4())

    # Create 3 open positions
    positions = []
    for i in range(3):
        position = OpenPosition(
            id=str(uuid4()),
            execution_id=str(uuid4()),
            signal_id=str(uuid4()),
            approval_id=str(uuid4()),
            user_id=user_id,
            device_id=str(uuid4()),
            instrument="XAUUSD",
            side=0,
            entry_price=2655.00 + i,
            volume=0.1,
            owner_sl=2645.00,
            owner_tp=2670.00,
            status=PositionStatus.OPEN.value,
        )
        db_session.add(position)
        positions.append(position)

    # Create 1 closed position (should not be returned)
    closed_position = OpenPosition(
        id=str(uuid4()),
        execution_id=str(uuid4()),
        signal_id=str(uuid4()),
        approval_id=str(uuid4()),
        user_id=user_id,
        device_id=str(uuid4()),
        instrument="EURUSD",
        side=1,
        entry_price=1.0850,
        volume=0.5,
        status=PositionStatus.CLOSED_SL.value,  # CLOSED
    )
    db_session.add(closed_position)

    await db_session.commit()

    # Get all open positions
    open_positions = await get_open_positions(db_session)

    assert len(open_positions) == 3
    assert all(p.status == PositionStatus.OPEN.value for p in open_positions)
    assert closed_position.id not in [p.id for p in open_positions]


@pytest.mark.asyncio
async def test_get_position_by_id(db_session):
    """Test retrieving a single position by ID."""
    user_id = str(uuid4())

    position = OpenPosition(
        id=str(uuid4()),
        execution_id=str(uuid4()),
        signal_id=str(uuid4()),
        approval_id=str(uuid4()),
        user_id=user_id,
        device_id=str(uuid4()),
        instrument="XAUUSD",
        side=0,
        entry_price=2655.00,
        volume=0.1,
        owner_sl=2645.00,
        owner_tp=2670.00,
        status=PositionStatus.OPEN.value,
    )
    db_session.add(position)
    await db_session.commit()

    # Get position by ID
    retrieved = await get_position_by_id(db_session, position.id)

    assert retrieved is not None
    assert retrieved.id == position.id
    assert retrieved.instrument == "XAUUSD"
    assert retrieved.owner_sl == 2645.00
    assert retrieved.owner_tp == 2670.00


@pytest.mark.asyncio
async def test_close_position(db_session):
    """Test closing a position after breach detected."""
    user_id = str(uuid4())

    position = OpenPosition(
        id=str(uuid4()),
        execution_id=str(uuid4()),
        signal_id=str(uuid4()),
        approval_id=str(uuid4()),
        user_id=user_id,
        device_id=str(uuid4()),
        instrument="XAUUSD",
        side=0,
        entry_price=2655.00,
        volume=0.1,
        owner_sl=2645.00,
        owner_tp=2670.00,
        status=PositionStatus.OPEN.value,
    )
    db_session.add(position)
    await db_session.commit()

    # Close position due to SL hit
    closed = await close_position(
        db_session,
        position,
        close_price=2643.50,
        reason="sl_hit",
    )

    assert closed.status == PositionStatus.CLOSED_SL.value
    assert closed.close_price == 2643.50
    assert closed.close_reason == "sl_hit"
    assert closed.closed_at is not None
    assert not closed.is_open()
    assert closed.is_closed()
