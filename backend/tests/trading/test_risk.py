from unittest.mock import AsyncMock

import pytest

from backend.app.trading.risk import RiskCheckException, RiskEngine


@pytest.mark.asyncio
async def test_risk_kill_switch():
    """Test kill switch functionality."""
    redis = AsyncMock()
    engine = RiskEngine(redis)

    # 1. Global Kill Switch Active
    redis.get.side_effect = lambda k: b"1" if k == "risk:kill_switch:global" else None

    with pytest.raises(RiskCheckException, match="Kill Switch active"):
        await engine.check_risk("u1", "a1", "EURUSD", "buy", 1.0, 1.1, 1000.0, None)

    # 2. User Kill Switch Active
    redis.get.side_effect = lambda k: b"1" if k == "risk:kill_switch:user:u1" else None

    with pytest.raises(RiskCheckException, match="Kill Switch active"):
        await engine.check_risk("u1", "a1", "EURUSD", "buy", 1.0, 1.1, 1000.0, None)


@pytest.mark.asyncio
async def test_daily_loss_limit():
    """Test daily loss limit logic."""
    redis = AsyncMock()
    engine = RiskEngine(redis)

    # Setup: Start equity = 1000, Current = 900 (-10%)
    # Limit = -5%

    async def mock_get(key):
        if "start" in key:
            return b"1000.0"
        if "daily_loss" in key:
            return b"-5.0"
        return None

    redis.get.side_effect = mock_get

    with pytest.raises(RiskCheckException, match="Daily loss limit reached"):
        await engine.check_risk("u1", "a1", "EURUSD", "buy", 1.0, 1.1, 900.0, None)

    # Safe case: Current = 960 (-4%)
    # Should pass
    await engine.check_risk("u1", "a1", "EURUSD", "buy", 1.0, 1.1, 960.0, None)


@pytest.mark.asyncio
async def test_position_size_limit():
    """Test max position size check."""
    redis = AsyncMock()
    engine = RiskEngine(redis)

    # Mock get to handle different keys
    async def mock_get(key):
        if "max_lots" in key:
            return b"10.0"
        return None  # Kill switch and others return None

    redis.get.side_effect = mock_get

    # Fail: 11 lots
    with pytest.raises(RiskCheckException, match="Position size exceeds limit"):
        await engine.check_risk("u1", "a1", "EURUSD", "buy", 11.0, 1.1, 1000.0, None)

    # Pass: 5 lots
    await engine.check_risk("u1", "a1", "EURUSD", "buy", 5.0, 1.1, 1000.0, None)
