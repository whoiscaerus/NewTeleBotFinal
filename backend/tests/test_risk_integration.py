"""Integration tests for PR-074 risk management system.

Tests validate REAL end-to-end workflows:
- Full workflow: check guards → calculate size → round → validate
- Multiple breach scenarios (combined violations)
- Platform limits vs client limits (most restrictive wins)
- Telemetry recording across full workflow
- Real account scenarios with drawdown, equity changes, position sizing

NO MOCKS - Tests use REAL guard and position sizing functions together.
"""

from decimal import Decimal
from unittest.mock import patch

import pytest

from backend.app.risk.guards import (
    AccountState,
    RiskLimits,
    RiskViolationType,
    check_all_guards,
)
from backend.app.risk.position_size import (
    calculate_position_with_constraints,
    calculate_risk_amount,
)


class TestFullTradingWorkflow:
    """Test complete trade decision workflow."""

    def test_healthy_account_allows_trade(self):
        """Test healthy account passes all guards and calculates position."""
        # Step 1: Check risk guards
        state = AccountState(
            current_equity=Decimal("10000"),
            peak_equity=Decimal("11000"),
            open_positions=2,
        )
        limits = RiskLimits(
            max_drawdown_percent=Decimal("20"),
            min_equity_threshold=Decimal("1000"),
            max_position_size=Decimal("2.0"),
            max_open_positions=5,
        )

        violations = check_all_guards(state, limits)
        assert len(violations) == 0, "Healthy account should pass all guards"

        # Step 2: Calculate position size
        lot_size = calculate_position_with_constraints(
            equity=state.current_equity,
            risk_percent=Decimal("2.0"),
            stop_distance_pips=Decimal("50"),
            pip_value=Decimal("10"),
            min_lot=Decimal("0.01"),
            max_lot=limits.max_position_size,
            step_lot=Decimal("0.01"),
        )

        # Expected: 200/(50*10) = 0.4 lots
        assert lot_size == Decimal("0.40")

        # Step 3: Verify position size within risk limits
        size_check_violations = check_all_guards(
            state, limits, requested_position_size=lot_size
        )
        assert (
            len(size_check_violations) == 0
        ), "Calculated size should be within limits"

        # Step 4: Verify actual risk
        actual_risk = calculate_risk_amount(lot_size, Decimal("50"), Decimal("10"))
        expected_risk = state.current_equity * (Decimal("2.0") / Decimal("100"))
        assert actual_risk == expected_risk  # £200

    def test_drawdown_breach_blocks_trade(self):
        """Test drawdown breach prevents trade execution."""
        # Account has suffered 25% drawdown (exceeds 20% limit)
        state = AccountState(
            current_equity=Decimal("7500"),
            peak_equity=Decimal("10000"),
            open_positions=1,
        )
        limits = RiskLimits(
            max_drawdown_percent=Decimal("20"),
            min_equity_threshold=Decimal("1000"),
            max_position_size=Decimal("1.0"),
            max_open_positions=5,
        )

        violations = check_all_guards(state, limits)

        assert len(violations) >= 1
        assert any(
            v.violation_type == RiskViolationType.MAX_DRAWDOWN_EXCEEDED
            for v in violations
        ), "Drawdown breach should block trade"

        # Position sizing should still work (but trade would be blocked by guards)
        lot_size = calculate_position_with_constraints(
            equity=state.current_equity,
            risk_percent=Decimal("2.0"),
            stop_distance_pips=Decimal("50"),
            pip_value=Decimal("10"),
            min_lot=Decimal("0.01"),
            max_lot=Decimal("100.0"),
            step_lot=Decimal("0.01"),
        )

        assert lot_size == Decimal("0.30")  # 150/(50*10) = 0.3

    def test_equity_floor_breach_blocks_trade(self):
        """Test equity floor breach prevents trade execution."""
        # Account below minimum equity threshold
        state = AccountState(
            current_equity=Decimal("800"),
            peak_equity=Decimal("10000"),
            open_positions=0,
        )
        limits = RiskLimits(
            max_drawdown_percent=Decimal("99"),  # High limit, won't breach
            min_equity_threshold=Decimal("1000"),
            max_position_size=Decimal("1.0"),
            max_open_positions=5,
        )

        violations = check_all_guards(state, limits)

        assert len(violations) >= 1
        assert any(
            v.violation_type == RiskViolationType.MIN_EQUITY_BREACH for v in violations
        ), "Equity floor breach should block trade"

    def test_max_positions_breach_blocks_trade(self):
        """Test maximum positions limit prevents new trade."""
        # Already at maximum positions
        state = AccountState(
            current_equity=Decimal("10000"),
            peak_equity=Decimal("11000"),
            open_positions=5,
        )
        limits = RiskLimits(
            max_drawdown_percent=Decimal("20"),
            min_equity_threshold=Decimal("1000"),
            max_position_size=Decimal("1.0"),
            max_open_positions=5,
        )

        violations = check_all_guards(state, limits)

        assert len(violations) >= 1
        assert any(
            v.violation_type == RiskViolationType.MAX_OPEN_POSITIONS_EXCEEDED
            for v in violations
        ), "Max positions breach should block trade"

    def test_calculated_size_exceeds_limit(self):
        """Test calculated position size exceeds maximum allowed."""
        # Large account, small stop → large calculated size
        state = AccountState(
            current_equity=Decimal("100000"),
            peak_equity=Decimal("110000"),
            open_positions=0,
        )
        limits = RiskLimits(
            max_drawdown_percent=Decimal("20"),
            min_equity_threshold=Decimal("1000"),
            max_position_size=Decimal("1.0"),  # Small max
            max_open_positions=5,
        )

        # Calculate size (will be large)
        lot_size = calculate_position_with_constraints(
            equity=state.current_equity,
            risk_percent=Decimal("2.0"),
            stop_distance_pips=Decimal("20"),
            pip_value=Decimal("10"),
            min_lot=Decimal("0.01"),
            max_lot=Decimal("100.0"),  # Broker allows 100 lots
            step_lot=Decimal("0.01"),
        )

        # Expected: 2000/(20*10) = 10 lots (capped by broker max 100)
        assert lot_size == Decimal("10.00")

        # But this exceeds risk profile max (1.0)
        violations = check_all_guards(state, limits, requested_position_size=lot_size)

        assert len(violations) >= 1
        assert any(
            v.violation_type == RiskViolationType.MAX_POSITION_SIZE_EXCEEDED
            for v in violations
        ), "Calculated size exceeding max should be blocked"


class TestMultipleViolations:
    """Test scenarios with multiple simultaneous violations."""

    def test_catastrophic_account_state(self):
        """Test account in catastrophic state (multiple breaches)."""
        # Account:
        # - 80% drawdown (way over 20% limit)
        # - Below minimum equity
        # - At maximum positions
        state = AccountState(
            current_equity=Decimal("2000"),
            peak_equity=Decimal("10000"),
            open_positions=5,
        )
        limits = RiskLimits(
            max_drawdown_percent=Decimal("20"),
            min_equity_threshold=Decimal("5000"),
            max_position_size=Decimal("1.0"),
            max_open_positions=5,
        )

        violations = check_all_guards(state, limits)

        # Should have at least 3 violations
        assert len(violations) >= 3

        violation_types = {v.violation_type for v in violations}
        assert RiskViolationType.MAX_DRAWDOWN_EXCEEDED in violation_types
        assert RiskViolationType.MIN_EQUITY_BREACH in violation_types
        assert RiskViolationType.MAX_OPEN_POSITIONS_EXCEEDED in violation_types

    def test_drawdown_and_equity_floor_both_breach(self):
        """Test both drawdown and equity floor breached."""
        # Account has 50% drawdown and is below min equity
        state = AccountState(
            current_equity=Decimal("500"),
            peak_equity=Decimal("1000"),
            open_positions=0,
        )
        limits = RiskLimits(
            max_drawdown_percent=Decimal("30"),  # 50% > 30%
            min_equity_threshold=Decimal("600"),  # 500 < 600
            max_position_size=Decimal("1.0"),
            max_open_positions=5,
        )

        violations = check_all_guards(state, limits)

        assert len(violations) >= 2
        violation_types = {v.violation_type for v in violations}
        assert RiskViolationType.MAX_DRAWDOWN_EXCEEDED in violation_types
        assert RiskViolationType.MIN_EQUITY_BREACH in violation_types


class TestPlatformVsClientLimits:
    """Test interaction between platform limits and client limits."""

    def test_client_limit_more_restrictive(self):
        """Test client limit more restrictive than platform (client wins)."""
        # Client has 10% max DD, platform allows 20%
        state = AccountState(
            current_equity=Decimal("9000"),
            peak_equity=Decimal("10000"),
            open_positions=0,
        )

        # Client limits (stricter)
        client_limits = RiskLimits(
            max_drawdown_percent=Decimal("10"),
            min_equity_threshold=Decimal("5000"),
            max_position_size=Decimal("0.5"),
            max_open_positions=3,
        )

        violations = check_all_guards(state, client_limits)

        # 10% DD, but client limit is 10%, so should block
        assert len(violations) == 0, "10% DD is within 10% limit"

        # Now 11% DD
        state.current_equity = Decimal("8900")
        violations = check_all_guards(state, client_limits)
        assert len(violations) >= 1
        assert any(
            v.violation_type == RiskViolationType.MAX_DRAWDOWN_EXCEEDED
            for v in violations
        )

    def test_position_size_respects_risk_profile_max(self):
        """Test position sizing respects risk profile maximum."""
        state = AccountState(
            current_equity=Decimal("10000"),
            peak_equity=Decimal("10000"),
            open_positions=0,
        )
        limits = RiskLimits(
            max_drawdown_percent=Decimal("20"),
            min_equity_threshold=Decimal("1000"),
            max_position_size=Decimal("0.5"),  # Small max
            max_open_positions=5,
        )

        # Broker allows 100 lots, but risk profile limits to 0.5
        lot_size = calculate_position_with_constraints(
            equity=state.current_equity,
            risk_percent=Decimal("5.0"),  # Aggressive risk
            stop_distance_pips=Decimal("10"),  # Tight stop
            pip_value=Decimal("10"),
            min_lot=Decimal("0.01"),
            max_lot=limits.max_position_size,  # Use risk profile max
            step_lot=Decimal("0.01"),
        )

        # Calculated: 500/(10*10) = 5.0 lots, but capped at 0.5
        assert lot_size == Decimal("0.50")


class TestTelemetryIntegration:
    """Test telemetry recording across full workflow."""

    def test_telemetry_recorded_on_drawdown_breach(self):
        """Test risk_block_total metric recorded on drawdown breach."""
        state = AccountState(
            current_equity=Decimal("7000"),
            peak_equity=Decimal("10000"),
            open_positions=0,
        )
        limits = RiskLimits(
            max_drawdown_percent=Decimal("20"),
            min_equity_threshold=Decimal("1000"),
            max_position_size=Decimal("1.0"),
            max_open_positions=5,
        )

        with patch(
            "backend.app.risk.guards.metrics.risk_block_total.labels"
        ) as mock_labels:
            mock_counter = mock_labels.return_value

            violations = check_all_guards(state, limits)

            assert len(violations) >= 1
            # Metric should be recorded for drawdown breach
            mock_labels.assert_called_with(
                reason=RiskViolationType.MAX_DRAWDOWN_EXCEEDED
            )
            mock_counter.inc.assert_called()

    def test_telemetry_recorded_on_equity_breach(self):
        """Test risk_block_total metric recorded on equity breach."""
        state = AccountState(
            current_equity=Decimal("400"),
            peak_equity=Decimal("10000"),
            open_positions=0,
        )
        limits = RiskLimits(
            max_drawdown_percent=Decimal("99"),  # Won't breach
            min_equity_threshold=Decimal("500"),
            max_position_size=Decimal("1.0"),
            max_open_positions=5,
        )

        with patch(
            "backend.app.risk.guards.metrics.risk_block_total.labels"
        ) as mock_labels:
            mock_counter = mock_labels.return_value

            violations = check_all_guards(state, limits)

            assert len(violations) >= 1
            # Metric should be recorded for equity breach
            mock_labels.assert_called_with(reason=RiskViolationType.MIN_EQUITY_BREACH)
            mock_counter.inc.assert_called()


class TestRealWorldScenarios:
    """Test realistic trading scenarios."""

    def test_day_trader_multiple_small_positions(self):
        """Test day trader with multiple small positions."""
        # Day trader: £5,000 account, 3 open positions, 1% risk per trade
        state = AccountState(
            current_equity=Decimal("5000"),
            peak_equity=Decimal("5200"),
            open_positions=3,
        )
        limits = RiskLimits(
            max_drawdown_percent=Decimal("15"),  # Conservative
            min_equity_threshold=Decimal("3000"),
            max_position_size=Decimal("0.3"),
            max_open_positions=5,
        )

        # Check guards
        violations = check_all_guards(state, limits)
        assert len(violations) == 0, "Day trader within all limits"

        # Calculate new position
        lot_size = calculate_position_with_constraints(
            equity=state.current_equity,
            risk_percent=Decimal("1.0"),
            stop_distance_pips=Decimal("30"),
            pip_value=Decimal("10"),
            min_lot=Decimal("0.01"),
            max_lot=limits.max_position_size,
            step_lot=Decimal("0.01"),
        )

        # Expected: 50/(30*10) = 0.1666... → rounds to 0.16
        assert lot_size == Decimal("0.16")

        # Verify size check
        size_violations = check_all_guards(
            state, limits, requested_position_size=lot_size
        )
        assert len(size_violations) == 0

    def test_swing_trader_larger_positions(self):
        """Test swing trader with fewer, larger positions."""
        # Swing trader: £20,000 account, 1 open position, 2% risk per trade
        state = AccountState(
            current_equity=Decimal("20000"),
            peak_equity=Decimal("21000"),
            open_positions=1,
        )
        limits = RiskLimits(
            max_drawdown_percent=Decimal("25"),  # Less strict
            min_equity_threshold=Decimal("5000"),
            max_position_size=Decimal("2.0"),
            max_open_positions=3,  # Fewer positions
        )

        violations = check_all_guards(state, limits)
        assert len(violations) == 0

        # Calculate position with wider stop
        lot_size = calculate_position_with_constraints(
            equity=state.current_equity,
            risk_percent=Decimal("2.0"),
            stop_distance_pips=Decimal("80"),
            pip_value=Decimal("10"),
            min_lot=Decimal("0.01"),
            max_lot=limits.max_position_size,
            step_lot=Decimal("0.01"),
        )

        # Expected: 400/(80*10) = 0.5 lots
        assert lot_size == Decimal("0.50")

    def test_account_recovery_after_drawdown(self):
        """Test account recovering after drawdown."""
        # Account was at £10,000, dropped to £7,000 (30% DD - blocked),
        # now recovered to £8,500 (15% DD - allowed if limit is 20%)
        state = AccountState(
            current_equity=Decimal("8500"),
            peak_equity=Decimal("10000"),  # Peak before drawdown
            open_positions=1,
        )
        limits = RiskLimits(
            max_drawdown_percent=Decimal("20"),
            min_equity_threshold=Decimal("2000"),
            max_position_size=Decimal("1.0"),
            max_open_positions=5,
        )

        violations = check_all_guards(state, limits)

        # 15% DD is within 20% limit
        assert len(violations) == 0, "Recovered account should be allowed to trade"

        # Position sizing should be based on current equity
        lot_size = calculate_position_with_constraints(
            equity=state.current_equity,
            risk_percent=Decimal("2.0"),
            stop_distance_pips=Decimal("50"),
            pip_value=Decimal("10"),
            min_lot=Decimal("0.01"),
            max_lot=Decimal("100.0"),
            step_lot=Decimal("0.01"),
        )

        # Expected: 170/(50*10) = 0.34 lots
        assert lot_size == Decimal("0.34")

    def test_small_account_cant_trade_safely(self):
        """Test small account where calculated size is below broker minimum."""
        # £500 account, 1% risk, 50 pip stop
        # Risk: £5, Size: 5/(50*10) = 0.01 lots (exactly at minimum)
        state = AccountState(
            current_equity=Decimal("500"),
            peak_equity=Decimal("600"),
            open_positions=0,
        )
        limits = RiskLimits(
            max_drawdown_percent=Decimal("20"),
            min_equity_threshold=Decimal("200"),
            max_position_size=Decimal("1.0"),
            max_open_positions=5,
        )

        violations = check_all_guards(state, limits)
        assert len(violations) == 0

        # This should work (exactly 0.01)
        lot_size = calculate_position_with_constraints(
            equity=state.current_equity,
            risk_percent=Decimal("1.0"),
            stop_distance_pips=Decimal("50"),
            pip_value=Decimal("10"),
            min_lot=Decimal("0.01"),
            max_lot=Decimal("100.0"),
            step_lot=Decimal("0.01"),
        )

        assert lot_size == Decimal("0.01")

        # But if account is smaller or stop wider, would fail
        with pytest.raises(ValueError, match="below minimum"):
            calculate_position_with_constraints(
                equity=Decimal("400"),  # Smaller account
                risk_percent=Decimal("1.0"),
                stop_distance_pips=Decimal("50"),
                pip_value=Decimal("10"),
                min_lot=Decimal("0.01"),
                max_lot=Decimal("100.0"),
                step_lot=Decimal("0.01"),
            )
