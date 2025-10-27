"""
Phase 3 Tests: Drawdown/Market Guards

Comprehensive test suite for DrawdownGuard and MarketGuard services.
Tests all guard checks, thresholds, alert generation, and edge cases.

Tests: 15 total (8 DrawdownGuard + 7 MarketGuard)
Coverage: Guard logic, alert generation, error handling
"""

from datetime import datetime

import pytest

from backend.app.trading.monitoring.drawdown_guard import (
    DrawdownAlertData,
    DrawdownGuard,
    get_drawdown_guard,
)
from backend.app.trading.monitoring.market_guard import (
    MarketGuard,
    get_market_guard,
)

# ============================================================================
# DRAWDOWN GUARD TESTS (8 tests)
# ============================================================================


class TestDrawdownGuard:
    """Test DrawdownGuard service."""

    @pytest.fixture
    def guard(self) -> DrawdownGuard:
        """Create DrawdownGuard instance."""
        return DrawdownGuard(
            max_drawdown_pct=20.0,
            warning_threshold_pct=15.0,
            min_equity_gbp=100.0,
            warning_seconds=10,
        )

    @pytest.mark.asyncio
    async def test_check_drawdown_within_threshold(self, guard: DrawdownGuard):
        """Test: Drawdown within safe threshold returns no alert."""
        # Arrange: 5% drawdown (below 15% warning threshold)
        current_equity = 9500.0
        peak_equity = 10000.0
        user_id = "user_123"

        # Act
        alert = await guard.check_drawdown(current_equity, peak_equity, user_id)

        # Assert
        assert alert is None, "No alert should be triggered for drawdown < threshold"

    @pytest.mark.asyncio
    async def test_check_drawdown_warning_threshold(self, guard: DrawdownGuard):
        """Test: Drawdown at warning threshold triggers warning alert."""
        # Arrange: 15% drawdown (at warning threshold)
        current_equity = 8500.0
        peak_equity = 10000.0
        user_id = "user_123"

        # Act
        alert = await guard.check_drawdown(current_equity, peak_equity, user_id)

        # Assert
        assert alert is not None, "Alert should be triggered"
        assert alert.alert_type == "warning", "Alert type should be warning"
        assert alert.drawdown_pct == 15.0, "Drawdown should be 15%"
        assert alert.user_id == user_id

    @pytest.mark.asyncio
    async def test_check_drawdown_critical(self, guard: DrawdownGuard):
        """Test: Drawdown exceeding max threshold triggers critical alert."""
        # Arrange: 25% drawdown (exceeds 20% critical threshold)
        current_equity = 7500.0
        peak_equity = 10000.0
        user_id = "user_123"

        # Act
        alert = await guard.check_drawdown(current_equity, peak_equity, user_id)

        # Assert
        assert alert is not None, "Alert should be triggered"
        assert alert.alert_type == "critical", "Alert type should be critical"
        assert alert.drawdown_pct == 25.0, "Drawdown should be 25%"

    @pytest.mark.asyncio
    async def test_check_drawdown_below_min_equity(self, guard: DrawdownGuard):
        """Test: Equity below minimum forces critical liquidation."""
        # Arrange: Equity £50 (below £100 minimum)
        current_equity = 50.0
        peak_equity = 10000.0
        user_id = "user_123"

        # Act
        alert = await guard.check_drawdown(current_equity, peak_equity, user_id)

        # Assert
        assert alert is not None
        assert alert.alert_type == "critical", "Force liquidation below min equity"
        assert alert.current_equity == 50.0

    @pytest.mark.asyncio
    async def test_check_drawdown_invalid_equity_negative(self, guard: DrawdownGuard):
        """Test: Negative equity raises ValueError."""
        # Arrange
        current_equity = -100.0
        peak_equity = 10000.0
        user_id = "user_123"

        # Act & Assert
        with pytest.raises(ValueError, match="Equity values must be non-negative"):
            await guard.check_drawdown(current_equity, peak_equity, user_id)

    @pytest.mark.asyncio
    async def test_check_drawdown_invalid_equity_zero(self, guard: DrawdownGuard):
        """Test: Zero peak equity raises ValueError."""
        # Arrange
        current_equity = 5000.0
        peak_equity = 0.0  # Zero peak (invalid)
        user_id = "user_123"

        # Act & Assert
        with pytest.raises(ValueError, match="Peak equity must be positive"):
            await guard.check_drawdown(current_equity, peak_equity, user_id)

    @pytest.mark.asyncio
    async def test_check_drawdown_new_peak(self, guard: DrawdownGuard):
        """Test: Current equity exceeding peak updates peak."""
        # Arrange: Current > Peak (new peak scenario)
        current_equity = 11000.0
        peak_equity = 10000.0
        user_id = "user_123"

        # Act
        alert = await guard.check_drawdown(current_equity, peak_equity, user_id)

        # Assert
        assert alert is None, "New peak should not trigger alert"

    @pytest.mark.asyncio
    async def test_alert_user_before_close(self, guard: DrawdownGuard):
        """Test: Alert message generation before liquidation."""
        # Arrange
        alert_data = DrawdownAlertData(
            user_id="user_123",
            alert_type="critical",
            drawdown_pct=25.0,
            current_equity=7500.0,
            peak_equity=10000.0,
            positions_count=3,
            timestamp=datetime.utcnow(),
        )

        # Act
        result = await guard.alert_user_before_close("user_123", alert_data)

        # Assert
        assert result is True, "Alert should be processed successfully"


# ============================================================================
# MARKET GUARD TESTS (7 tests)
# ============================================================================


class TestMarketGuard:
    """Test MarketGuard service."""

    @pytest.fixture
    def guard(self) -> MarketGuard:
        """Create MarketGuard instance."""
        return MarketGuard(
            price_gap_alert_pct=5.0,
            bid_ask_spread_max_pct=0.5,
            min_liquidity_volume_lots=10.0,
            liquidity_check_enabled=True,
        )

    @pytest.mark.asyncio
    async def test_check_price_gap_normal(self, guard: MarketGuard):
        """Test: Normal price movement no alert."""
        # Arrange: 2% gap (below 5% threshold)
        symbol = "XAUUSD"
        last_close = 1950.00
        current_open = 1989.00  # 2% higher

        # Act
        alert = await guard.check_price_gap(symbol, last_close, current_open)

        # Assert
        assert alert is None, "No alert for gap < threshold"

    @pytest.mark.asyncio
    async def test_check_price_gap_large_up(self, guard: MarketGuard):
        """Test: Large gap up triggers alert."""
        # Arrange: 5.1% gap up
        symbol = "XAUUSD"
        last_close = 1950.00
        current_open = 2049.50  # 5.1% higher

        # Act
        alert = await guard.check_price_gap(symbol, last_close, current_open)

        # Assert
        assert alert is not None
        assert alert.alert_type == "gap"
        assert alert.condition_value > 5.0
        assert "up" in alert.message.lower()

    @pytest.mark.asyncio
    async def test_check_price_gap_large_down(self, guard: MarketGuard):
        """Test: Large gap down triggers alert."""
        # Arrange: 5.5% gap down
        symbol = "XAUUSD"
        last_close = 2000.00
        current_open = 1890.00  # 5.5% lower

        # Act
        alert = await guard.check_price_gap(symbol, last_close, current_open)

        # Assert
        assert alert is not None
        assert alert.alert_type == "gap"
        assert alert.condition_value > 5.0
        assert "down" in alert.message.lower()

    @pytest.mark.asyncio
    async def test_check_liquidity_sufficient(self, guard: MarketGuard):
        """Test: Normal spread returns no alert."""
        # Arrange: 0.1% spread (below 0.5% max)
        symbol = "XAUUSD"
        bid = 1950.00
        ask = 1950.20  # 0.1% spread
        position_volume = 1.0

        # Act
        alert = await guard.check_liquidity(symbol, bid, ask, position_volume)

        # Assert
        assert alert is None, "No alert for spread < max"

    @pytest.mark.asyncio
    async def test_check_liquidity_wide_spread(self, guard: MarketGuard):
        """Test: Wide spread triggers liquidity alert."""
        # Arrange: 1.0% spread (exceeds 0.5% max)
        symbol = "XAUUSD"
        bid = 1950.00
        ask = 1969.50  # 1.0% spread
        position_volume = 1.0

        # Act
        alert = await guard.check_liquidity(symbol, bid, ask, position_volume)

        # Assert
        assert alert is not None
        assert alert.alert_type == "spread"
        assert alert.condition_value > 0.5

    @pytest.mark.asyncio
    async def test_check_liquidity_invalid_prices(self, guard: MarketGuard):
        """Test: Invalid prices raise ValueError."""
        # Arrange
        symbol = "XAUUSD"
        bid = 1950.00
        ask = 1940.00  # Ask < Bid (invalid)
        position_volume = 1.0

        # Act & Assert
        with pytest.raises(ValueError, match="Ask price must be >= bid"):
            await guard.check_liquidity(symbol, bid, ask, position_volume)

    @pytest.mark.asyncio
    async def test_mark_position_for_close(self, guard: MarketGuard):
        """Test: Position marked for close."""
        # Arrange
        position_id = "pos_123"
        reason = "gap"
        condition_details = {"gap_pct": 5.5, "symbol": "XAUUSD"}

        # Act
        result = await guard.mark_position_for_close(
            position_id, reason, condition_details
        )

        # Assert
        assert result is True, "Position should be marked for close"


# ============================================================================
# INTEGRATION TESTS (3 tests)
# ============================================================================


class TestGuardIntegration:
    """Integration tests for guards working together."""

    @pytest.mark.asyncio
    async def test_should_close_position_on_gap(self):
        """Test: Position closed when price gap detected."""
        # Arrange
        guard = get_market_guard()
        position_id = "pos_123"
        symbol = "XAUUSD"
        bid = 2050.00
        ask = 2050.50
        last_close = 1950.00
        current_open = 2050.00  # 5.1% gap
        position_volume = 1.0

        # Act
        should_close, reason = await guard.should_close_position(
            position_id, symbol, bid, ask, last_close, current_open, position_volume
        )

        # Assert
        assert should_close is True, "Position should close on gap"
        assert "gap" in reason.lower()

    @pytest.mark.asyncio
    async def test_should_close_position_on_spread(self):
        """Test: Position closed when spread too wide."""
        # Arrange
        guard = get_market_guard()
        position_id = "pos_123"
        symbol = "XAUUSD"
        bid = 1950.00
        ask = 1970.00  # 1.0% spread (exceeds 0.5% max)
        last_close = 1950.00
        current_open = 1955.00  # 0.26% gap (no gap alert)
        position_volume = 1.0

        # Act
        should_close, reason = await guard.should_close_position(
            position_id, symbol, bid, ask, last_close, current_open, position_volume
        )

        # Assert
        assert should_close is True, "Position should close on wide spread"
        assert "liquidity" in reason.lower()

    @pytest.mark.asyncio
    async def test_should_not_close_position_normal(self):
        """Test: Position not closed under normal conditions."""
        # Arrange
        guard = get_market_guard()
        position_id = "pos_123"
        symbol = "XAUUSD"
        bid = 1950.00
        ask = 1950.10  # 0.005% spread (normal)
        last_close = 1950.00
        current_open = 1955.00  # 0.26% gap (normal)
        position_volume = 1.0

        # Act
        should_close, reason = await guard.should_close_position(
            position_id, symbol, bid, ask, last_close, current_open, position_volume
        )

        # Assert
        assert (
            should_close is False
        ), "Position should not close under normal conditions"
        assert reason is None, "No reason provided"


# ============================================================================
# GUARD INSTANTIATION TESTS (2 tests)
# ============================================================================


class TestGuardInstances:
    """Test guard singleton instances."""

    def test_get_drawdown_guard_singleton(self):
        """Test: DrawdownGuard is singleton."""
        # Act
        guard1 = get_drawdown_guard()
        guard2 = get_drawdown_guard()

        # Assert
        assert guard1 is guard2, "Should return same instance"

    def test_get_market_guard_singleton(self):
        """Test: MarketGuard is singleton."""
        # Act
        guard1 = get_market_guard()
        guard2 = get_market_guard()

        # Assert
        assert guard1 is guard2, "Should return same instance"
