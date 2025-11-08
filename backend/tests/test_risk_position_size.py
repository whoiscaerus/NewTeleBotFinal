"""Comprehensive tests for position sizing (PR-074).

Tests validate REAL business logic:
- Position size calculations based on risk parameters
- Tick rounding accuracy (down/up/nearest modes)
- Broker constraint validation (min/max/step lots)
- Edge cases: zero values, small accounts, large positions
- Real broker scenarios: FOREX (0.01), GOLD (0.01), Indices (0.1)

NO MOCKS - Tests use REAL calculation functions with Decimal precision.
"""

from decimal import Decimal

import pytest

from backend.app.risk.position_size import (
    RoundingMode,
    calculate_lot_size,
    calculate_position_with_constraints,
    calculate_risk_amount,
    round_to_tick,
    validate_broker_constraints,
)


class TestCalculateLotSize:
    """Test position size calculation based on risk."""

    def test_standard_eurusd_trade(self):
        """Test standard EURUSD position sizing."""
        # Account: £10,000, Risk: 2%, Stop: 50 pips, Pip value: £10/lot
        # Risk amount: £200
        # Lot size: £200 / (50 pips * £10/pip) = 0.4 lots
        size = calculate_lot_size(
            equity=Decimal("10000"),
            risk_percent=Decimal("2.0"),
            stop_distance_pips=Decimal("50"),
            pip_value=Decimal("10"),
        )

        assert size == Decimal("0.4")

    def test_tight_stop(self):
        """Test calculation with tight stop loss."""
        # Tighter stop → larger position size for same risk
        size = calculate_lot_size(
            equity=Decimal("10000"),
            risk_percent=Decimal("1.0"),
            stop_distance_pips=Decimal("20"),
            pip_value=Decimal("10"),
        )

        assert size == Decimal("0.5")

    def test_wide_stop(self):
        """Test calculation with wide stop loss."""
        # Wider stop → smaller position size for same risk
        size = calculate_lot_size(
            equity=Decimal("10000"),
            risk_percent=Decimal("2.0"),
            stop_distance_pips=Decimal("100"),
            pip_value=Decimal("10"),
        )

        assert size == Decimal("0.2")

    def test_gold_trade_higher_pip_value(self):
        """Test GOLD position sizing (higher pip value)."""
        # GOLD has higher pip value (£100/lot vs £10/lot for FOREX)
        size = calculate_lot_size(
            equity=Decimal("10000"),
            risk_percent=Decimal("2.0"),
            stop_distance_pips=Decimal("10"),
            pip_value=Decimal("100"),
        )

        assert size == Decimal("0.2")

    def test_small_account(self):
        """Test position sizing for small account."""
        # £1,000 account, 1% risk
        size = calculate_lot_size(
            equity=Decimal("1000"),
            risk_percent=Decimal("1.0"),
            stop_distance_pips=Decimal("50"),
            pip_value=Decimal("10"),
        )

        assert size == Decimal("0.02")

    def test_large_account(self):
        """Test position sizing for large account."""
        # £100,000 account, 2% risk
        size = calculate_lot_size(
            equity=Decimal("100000"),
            risk_percent=Decimal("2.0"),
            stop_distance_pips=Decimal("50"),
            pip_value=Decimal("10"),
        )

        assert size == Decimal("4.0")

    def test_conservative_risk(self):
        """Test conservative 0.5% risk."""
        size = calculate_lot_size(
            equity=Decimal("10000"),
            risk_percent=Decimal("0.5"),
            stop_distance_pips=Decimal("50"),
            pip_value=Decimal("10"),
        )

        assert size == Decimal("0.1")

    def test_aggressive_risk(self):
        """Test aggressive 5% risk."""
        size = calculate_lot_size(
            equity=Decimal("10000"),
            risk_percent=Decimal("5.0"),
            stop_distance_pips=Decimal("50"),
            pip_value=Decimal("10"),
        )

        assert size == Decimal("1.0")

    def test_zero_equity_raises_error(self):
        """Test zero equity raises ValueError."""
        with pytest.raises(ValueError, match="Equity must be positive"):
            calculate_lot_size(
                equity=Decimal("0"),
                risk_percent=Decimal("2.0"),
                stop_distance_pips=Decimal("50"),
                pip_value=Decimal("10"),
            )

    def test_negative_equity_raises_error(self):
        """Test negative equity raises ValueError."""
        with pytest.raises(ValueError, match="Equity must be positive"):
            calculate_lot_size(
                equity=Decimal("-1000"),
                risk_percent=Decimal("2.0"),
                stop_distance_pips=Decimal("50"),
                pip_value=Decimal("10"),
            )

    def test_zero_risk_percent_raises_error(self):
        """Test zero risk percent raises ValueError."""
        with pytest.raises(ValueError, match="Risk percent must be positive"):
            calculate_lot_size(
                equity=Decimal("10000"),
                risk_percent=Decimal("0"),
                stop_distance_pips=Decimal("50"),
                pip_value=Decimal("10"),
            )

    def test_zero_stop_distance_raises_error(self):
        """Test zero stop distance raises ValueError."""
        with pytest.raises(ValueError, match="Stop distance must be positive"):
            calculate_lot_size(
                equity=Decimal("10000"),
                risk_percent=Decimal("2.0"),
                stop_distance_pips=Decimal("0"),
                pip_value=Decimal("10"),
            )

    def test_zero_pip_value_raises_error(self):
        """Test zero pip value raises ValueError."""
        with pytest.raises(ValueError, match="Pip value must be positive"):
            calculate_lot_size(
                equity=Decimal("10000"),
                risk_percent=Decimal("2.0"),
                stop_distance_pips=Decimal("50"),
                pip_value=Decimal("0"),
            )

    def test_decimal_precision(self):
        """Test decimal precision in calculation."""
        size = calculate_lot_size(
            equity=Decimal("10000"),
            risk_percent=Decimal("2.0"),
            stop_distance_pips=Decimal("33"),
            pip_value=Decimal("10"),
        )

        # Risk: £200, Calculation: 200/(33*10) = 0.606060...
        expected = Decimal("200") / (Decimal("33") * Decimal("10"))
        assert size == expected

    def test_very_small_position(self):
        """Test very small position calculation."""
        # Small account, conservative risk, wide stop
        size = calculate_lot_size(
            equity=Decimal("500"),
            risk_percent=Decimal("0.5"),
            stop_distance_pips=Decimal("100"),
            pip_value=Decimal("10"),
        )

        # Risk: £2.50, Size: 2.5/(100*10) = 0.0025 lots
        assert size == Decimal("0.0025")


class TestRoundToTick:
    """Test tick rounding functionality."""

    def test_round_down_forex_tick(self):
        """Test rounding down to 0.01 lot (FOREX standard)."""
        rounded = round_to_tick(
            lot_size=Decimal("0.437"),
            tick_size=Decimal("0.01"),
            mode=RoundingMode.DOWN,
        )

        assert rounded == Decimal("0.43")

    def test_round_up_forex_tick(self):
        """Test rounding up to 0.01 lot."""
        rounded = round_to_tick(
            lot_size=Decimal("0.437"),
            tick_size=Decimal("0.01"),
            mode=RoundingMode.UP,
        )

        assert rounded == Decimal("0.44")

    def test_round_nearest_forex_tick_up(self):
        """Test rounding to nearest tick (rounds up)."""
        rounded = round_to_tick(
            lot_size=Decimal("0.437"),
            tick_size=Decimal("0.01"),
            mode=RoundingMode.NEAREST,
        )

        # 0.437 is closer to 0.44 than 0.43
        assert rounded == Decimal("0.44")

    def test_round_nearest_forex_tick_down(self):
        """Test rounding to nearest tick (rounds down)."""
        rounded = round_to_tick(
            lot_size=Decimal("0.433"),
            tick_size=Decimal("0.01"),
            mode=RoundingMode.NEAREST,
        )

        # 0.433 is closer to 0.43 than 0.44
        assert rounded == Decimal("0.43")

    def test_round_exact_tick_boundary(self):
        """Test rounding when already on tick boundary."""
        for mode in [RoundingMode.DOWN, RoundingMode.UP, RoundingMode.NEAREST]:
            rounded = round_to_tick(
                lot_size=Decimal("0.50"),
                tick_size=Decimal("0.01"),
                mode=mode,
            )

            assert rounded == Decimal("0.50")

    def test_round_indices_tick_01(self):
        """Test rounding to 0.1 lot (indices)."""
        rounded = round_to_tick(
            lot_size=Decimal("1.76"),
            tick_size=Decimal("0.1"),
            mode=RoundingMode.DOWN,
        )

        assert rounded == Decimal("1.7")

    def test_round_whole_lots(self):
        """Test rounding to whole lots (1.0)."""
        rounded = round_to_tick(
            lot_size=Decimal("2.8"),
            tick_size=Decimal("1.0"),
            mode=RoundingMode.DOWN,
        )

        assert rounded == Decimal("2.0")

    def test_round_micro_lots(self):
        """Test rounding to micro lots (0.001)."""
        rounded = round_to_tick(
            lot_size=Decimal("0.5678"),
            tick_size=Decimal("0.001"),
            mode=RoundingMode.DOWN,
        )

        assert rounded == Decimal("0.567")

    def test_zero_lot_size(self):
        """Test zero lot size returns zero."""
        rounded = round_to_tick(
            lot_size=Decimal("0"),
            tick_size=Decimal("0.01"),
            mode=RoundingMode.DOWN,
        )

        assert rounded == Decimal("0")

    def test_zero_tick_size_raises_error(self):
        """Test zero tick size raises ValueError."""
        with pytest.raises(ValueError, match="Tick size must be positive"):
            round_to_tick(
                lot_size=Decimal("1.0"),
                tick_size=Decimal("0"),
                mode=RoundingMode.DOWN,
            )

    def test_negative_tick_size_raises_error(self):
        """Test negative tick size raises ValueError."""
        with pytest.raises(ValueError, match="Tick size must be positive"):
            round_to_tick(
                lot_size=Decimal("1.0"),
                tick_size=Decimal("-0.01"),
                mode=RoundingMode.DOWN,
            )

    def test_large_position_rounding(self):
        """Test rounding large position sizes."""
        rounded = round_to_tick(
            lot_size=Decimal("99.876"),
            tick_size=Decimal("0.01"),
            mode=RoundingMode.DOWN,
        )

        assert rounded == Decimal("99.87")

    def test_very_small_position_rounding(self):
        """Test rounding very small position sizes."""
        rounded = round_to_tick(
            lot_size=Decimal("0.0123"),
            tick_size=Decimal("0.01"),
            mode=RoundingMode.DOWN,
        )

        assert rounded == Decimal("0.01")

    def test_round_down_prevents_over_risk(self):
        """Test that DOWN mode is conservative (prevents over-risking)."""
        # If we have 0.437 lots calculated and round DOWN to 0.43,
        # we risk LESS than calculated (conservative)
        original = Decimal("0.437")
        rounded = round_to_tick(original, Decimal("0.01"), RoundingMode.DOWN)

        assert rounded < original


class TestValidateBrokerConstraints:
    """Test broker constraint validation."""

    def test_within_all_constraints(self):
        """Test position size within all constraints."""
        adjusted = validate_broker_constraints(
            lot_size=Decimal("0.5"),
            min_lot=Decimal("0.01"),
            max_lot=Decimal("100.0"),
            step_lot=Decimal("0.01"),
        )

        assert adjusted == Decimal("0.5")

    def test_exceeds_maximum_capped(self):
        """Test position size exceeding maximum is capped."""
        adjusted = validate_broker_constraints(
            lot_size=Decimal("150.0"),
            min_lot=Decimal("0.01"),
            max_lot=Decimal("100.0"),
            step_lot=Decimal("0.01"),
        )

        assert adjusted == Decimal("100.0")

    def test_below_minimum_raises_error(self):
        """Test position size below minimum raises ValueError."""
        with pytest.raises(ValueError, match="below minimum"):
            validate_broker_constraints(
                lot_size=Decimal("0.005"),
                min_lot=Decimal("0.01"),
                max_lot=Decimal("100.0"),
                step_lot=Decimal("0.01"),
            )

    def test_not_on_step_boundary_rounded_down(self):
        """Test position not on step boundary is rounded down."""
        adjusted = validate_broker_constraints(
            lot_size=Decimal("0.437"),
            min_lot=Decimal("0.01"),
            max_lot=Decimal("100.0"),
            step_lot=Decimal("0.01"),
        )

        assert adjusted == Decimal("0.43")

    def test_rounding_results_in_below_minimum(self):
        """Test rounding down results in below minimum raises error."""
        # 0.014 rounds down to 0.01 (on boundary), but if min is 0.02, should fail
        with pytest.raises(ValueError, match="below minimum"):
            validate_broker_constraints(
                lot_size=Decimal("0.014"),
                min_lot=Decimal("0.02"),
                max_lot=Decimal("100.0"),
                step_lot=Decimal("0.01"),
            )

    def test_exact_minimum_allowed(self):
        """Test exact minimum is allowed."""
        adjusted = validate_broker_constraints(
            lot_size=Decimal("0.01"),
            min_lot=Decimal("0.01"),
            max_lot=Decimal("100.0"),
            step_lot=Decimal("0.01"),
        )

        assert adjusted == Decimal("0.01")

    def test_exact_maximum_allowed(self):
        """Test exact maximum is allowed."""
        adjusted = validate_broker_constraints(
            lot_size=Decimal("100.0"),
            min_lot=Decimal("0.01"),
            max_lot=Decimal("100.0"),
            step_lot=Decimal("0.01"),
        )

        assert adjusted == Decimal("100.0")

    def test_step_lot_01_for_indices(self):
        """Test step lot 0.1 for indices."""
        adjusted = validate_broker_constraints(
            lot_size=Decimal("1.76"),
            min_lot=Decimal("0.1"),
            max_lot=Decimal("100.0"),
            step_lot=Decimal("0.1"),
        )

        assert adjusted == Decimal("1.7")

    def test_step_lot_10_whole_lots_only(self):
        """Test step lot 1.0 (whole lots only)."""
        adjusted = validate_broker_constraints(
            lot_size=Decimal("2.8"),
            min_lot=Decimal("1.0"),
            max_lot=Decimal("100.0"),
            step_lot=Decimal("1.0"),
        )

        assert adjusted == Decimal("2.0")

    def test_zero_min_lot_raises_error(self):
        """Test zero min lot raises ValueError."""
        with pytest.raises(ValueError, match="Min lot must be positive"):
            validate_broker_constraints(
                lot_size=Decimal("1.0"),
                min_lot=Decimal("0"),
                max_lot=Decimal("100.0"),
                step_lot=Decimal("0.01"),
            )

    def test_zero_max_lot_raises_error(self):
        """Test zero max lot raises ValueError."""
        with pytest.raises(ValueError, match="Max lot must be positive"):
            validate_broker_constraints(
                lot_size=Decimal("1.0"),
                min_lot=Decimal("0.01"),
                max_lot=Decimal("0"),
                step_lot=Decimal("0.01"),
            )

    def test_zero_step_lot_raises_error(self):
        """Test zero step lot raises ValueError."""
        with pytest.raises(ValueError, match="Step lot must be positive"):
            validate_broker_constraints(
                lot_size=Decimal("1.0"),
                min_lot=Decimal("0.01"),
                max_lot=Decimal("100.0"),
                step_lot=Decimal("0"),
            )

    def test_min_exceeds_max_raises_error(self):
        """Test min lot exceeding max lot raises ValueError."""
        with pytest.raises(ValueError, match="Min lot .* exceeds max lot"):
            validate_broker_constraints(
                lot_size=Decimal("1.0"),
                min_lot=Decimal("10.0"),
                max_lot=Decimal("5.0"),
                step_lot=Decimal("0.01"),
            )


class TestCalculatePositionWithConstraints:
    """Test full position sizing with all validations."""

    def test_standard_eurusd_full_pipeline(self):
        """Test standard EURUSD trade through full pipeline."""
        size = calculate_position_with_constraints(
            equity=Decimal("10000"),
            risk_percent=Decimal("2.0"),
            stop_distance_pips=Decimal("50"),
            pip_value=Decimal("10"),
            min_lot=Decimal("0.01"),
            max_lot=Decimal("100.0"),
            step_lot=Decimal("0.01"),
        )

        # Calculated: 0.4 lots, no rounding needed, within constraints
        assert size == Decimal("0.40")

    def test_small_account_below_minimum(self):
        """Test small account resulting in below minimum size raises error."""
        with pytest.raises(ValueError, match="below minimum"):
            calculate_position_with_constraints(
                equity=Decimal("100"),
                risk_percent=Decimal("1.0"),
                stop_distance_pips=Decimal("50"),
                pip_value=Decimal("10"),
                min_lot=Decimal("0.01"),
                max_lot=Decimal("100.0"),
                step_lot=Decimal("0.01"),
            )
            # Calculated: 0.002 lots → rounds to 0.00 → below min 0.01

    def test_large_position_exceeds_maximum(self):
        """Test large position exceeding maximum is capped."""
        size = calculate_position_with_constraints(
            equity=Decimal("1000000"),
            risk_percent=Decimal("5.0"),
            stop_distance_pips=Decimal("10"),
            pip_value=Decimal("10"),
            min_lot=Decimal("0.01"),
            max_lot=Decimal("10.0"),
            step_lot=Decimal("0.01"),
        )

        # Calculated: 500 lots → capped at max 10.0
        assert size == Decimal("10.0")

    def test_rounding_required(self):
        """Test position requiring rounding."""
        size = calculate_position_with_constraints(
            equity=Decimal("10000"),
            risk_percent=Decimal("2.0"),
            stop_distance_pips=Decimal("46"),  # Creates odd decimal
            pip_value=Decimal("10"),
            min_lot=Decimal("0.01"),
            max_lot=Decimal("100.0"),
            step_lot=Decimal("0.01"),
        )

        # Calculated: 200/(46*10) = 0.434782... → rounds to 0.43
        assert size == Decimal("0.43")

    def test_gold_trade_full_pipeline(self):
        """Test GOLD trade through full pipeline."""
        size = calculate_position_with_constraints(
            equity=Decimal("10000"),
            risk_percent=Decimal("2.0"),
            stop_distance_pips=Decimal("10"),
            pip_value=Decimal("100"),  # GOLD has higher pip value
            min_lot=Decimal("0.01"),
            max_lot=Decimal("100.0"),
            step_lot=Decimal("0.01"),
        )

        # Calculated: 0.2 lots
        assert size == Decimal("0.20")

    def test_indices_step_01(self):
        """Test indices with 0.1 step lot."""
        size = calculate_position_with_constraints(
            equity=Decimal("10000"),
            risk_percent=Decimal("2.0"),
            stop_distance_pips=Decimal("47"),  # Creates odd decimal
            pip_value=Decimal("10"),
            min_lot=Decimal("0.1"),
            max_lot=Decimal("100.0"),
            step_lot=Decimal("0.1"),
        )

        # Calculated: 200/(47*10) = 0.4255... → rounds to 0.4
        assert size == Decimal("0.4")


class TestCalculateRiskAmount:
    """Test risk amount calculation (inverse of calculate_lot_size)."""

    def test_standard_risk_calculation(self):
        """Test standard risk amount calculation."""
        risk = calculate_risk_amount(
            lot_size=Decimal("0.5"),
            stop_distance_pips=Decimal("50"),
            pip_value=Decimal("10"),
        )

        # 0.5 lots * 50 pips * £10/pip = £250
        assert risk == Decimal("250")

    def test_zero_lot_size(self):
        """Test zero lot size results in zero risk."""
        risk = calculate_risk_amount(
            lot_size=Decimal("0"),
            stop_distance_pips=Decimal("50"),
            pip_value=Decimal("10"),
        )

        assert risk == Decimal("0")

    def test_round_trip_calculation(self):
        """Test calculating lot size then verifying risk amount."""
        equity = Decimal("10000")
        risk_pct = Decimal("2.0")
        stop_pips = Decimal("50")
        pip_val = Decimal("10")

        # Calculate lot size
        lot = calculate_lot_size(equity, risk_pct, stop_pips, pip_val)

        # Round to tick (conservative)
        lot_rounded = round_to_tick(lot, Decimal("0.01"), RoundingMode.DOWN)

        # Calculate actual risk
        actual_risk = calculate_risk_amount(lot_rounded, stop_pips, pip_val)

        # Expected risk
        expected_risk = equity * (risk_pct / Decimal("100"))

        # Actual risk should be <= expected (due to rounding down)
        assert actual_risk <= expected_risk

    def test_gold_risk_calculation(self):
        """Test risk calculation for GOLD (higher pip value)."""
        risk = calculate_risk_amount(
            lot_size=Decimal("0.2"),
            stop_distance_pips=Decimal("10"),
            pip_value=Decimal("100"),
        )

        # 0.2 lots * 10 pips * £100/pip = £200
        assert risk == Decimal("200")

    def test_large_position_risk(self):
        """Test risk calculation for large position."""
        risk = calculate_risk_amount(
            lot_size=Decimal("10.0"),
            stop_distance_pips=Decimal("100"),
            pip_value=Decimal("10"),
        )

        # 10 lots * 100 pips * £10/pip = £10,000
        assert risk == Decimal("10000")

    def test_negative_lot_size_raises_error(self):
        """Test negative lot size raises ValueError."""
        with pytest.raises(ValueError, match="Lot size must be non-negative"):
            calculate_risk_amount(
                lot_size=Decimal("-1.0"),
                stop_distance_pips=Decimal("50"),
                pip_value=Decimal("10"),
            )

    def test_negative_stop_distance_raises_error(self):
        """Test negative stop distance raises ValueError."""
        with pytest.raises(ValueError, match="Stop distance must be non-negative"):
            calculate_risk_amount(
                lot_size=Decimal("1.0"),
                stop_distance_pips=Decimal("-50"),
                pip_value=Decimal("10"),
            )

    def test_negative_pip_value_raises_error(self):
        """Test negative pip value raises ValueError."""
        with pytest.raises(ValueError, match="Pip value must be non-negative"):
            calculate_risk_amount(
                lot_size=Decimal("1.0"),
                stop_distance_pips=Decimal("50"),
                pip_value=Decimal("-10"),
            )


class TestRealBrokerScenarios:
    """Test real broker configurations and scenarios."""

    def test_forex_broker_standard(self):
        """Test standard FOREX broker: min 0.01, step 0.01, max 100."""
        size = calculate_position_with_constraints(
            equity=Decimal("5000"),
            risk_percent=Decimal("1.5"),
            stop_distance_pips=Decimal("30"),
            pip_value=Decimal("10"),
            min_lot=Decimal("0.01"),
            max_lot=Decimal("100.0"),
            step_lot=Decimal("0.01"),
        )

        # Calculated: 75/(30*10) = 0.25 lots
        assert size == Decimal("0.25")

    def test_gold_broker_config(self):
        """Test GOLD broker: min 0.01, step 0.01, max 50."""
        size = calculate_position_with_constraints(
            equity=Decimal("10000"),
            risk_percent=Decimal("2.0"),
            stop_distance_pips=Decimal("15"),
            pip_value=Decimal("100"),
            min_lot=Decimal("0.01"),
            max_lot=Decimal("50.0"),
            step_lot=Decimal("0.01"),
        )

        # Calculated: 200/(15*100) = 0.133... → rounds to 0.13
        assert size == Decimal("0.13")

    def test_indices_broker_config(self):
        """Test indices broker: min 0.1, step 0.1, max 50."""
        size = calculate_position_with_constraints(
            equity=Decimal("10000"),
            risk_percent=Decimal("2.0"),
            stop_distance_pips=Decimal("40"),
            pip_value=Decimal("10"),
            min_lot=Decimal("0.1"),
            max_lot=Decimal("50.0"),
            step_lot=Decimal("0.1"),
        )

        # Calculated: 200/(40*10) = 0.5 lots
        assert size == Decimal("0.5")

    def test_restrictive_broker(self):
        """Test restrictive broker: min 0.1, step 1.0, max 10 (whole lots only)."""
        # Calculated: 0.4 lots → rounds DOWN to 0.0 (but min is 0.1)
        # This should raise error since rounded size (0.0) < min (0.1)
        # 0.4 lots with step 1.0 → rounds down to 0 lots
        # 0 lots < 0.1 min → error
        with pytest.raises(ValueError, match="below minimum"):
            calculate_position_with_constraints(
                equity=Decimal("10000"),
                risk_percent=Decimal("2.0"),
                stop_distance_pips=Decimal("50"),
                pip_value=Decimal("10"),
                min_lot=Decimal("0.1"),
                max_lot=Decimal("10.0"),
                step_lot=Decimal("1.0"),  # Whole lots only
            )
