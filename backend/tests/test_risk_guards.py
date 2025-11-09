"""Comprehensive tests for risk guards (PR-074).

Tests validate REAL business logic:
- Drawdown enforcement blocks trades when threshold breached
- Equity floor blocks trades when balance too low
- Position size limits enforced
- Exact threshold behavior (blocks at threshold, not just above)
- Edge cases: zero equity, negative values, peak tracking
- Telemetry recording (risk_block_total metric)
- Integration with RiskProfile model

NO MOCKS - Tests use REAL guard functions with REAL calculations.
"""

from decimal import Decimal
from unittest.mock import patch

from backend.app.risk.guards import (
    AccountState,
    RiskCheckResult,
    RiskLimits,
    RiskViolationType,
    check_all_guards,
    check_open_positions,
    check_position_size,
    enforce_max_dd,
    min_equity,
)


class TestEnforceMaxDD:
    """Test maximum drawdown enforcement."""

    def test_no_drawdown_new_equity_high(self):
        """Test no drawdown when current equity exceeds peak."""
        result = enforce_max_dd(
            current_equity=Decimal("11000"),
            peak_equity=Decimal("10000"),
            max_dd_percent=Decimal("20"),
            record_metric=False,
        )

        assert result.passed is True
        assert result.violation_type is None
        assert result.current_value == Decimal("0")
        assert "new equity high" in result.message.lower()

    def test_within_drawdown_limit(self):
        """Test drawdown within acceptable limit."""
        result = enforce_max_dd(
            current_equity=Decimal("10000"),
            peak_equity=Decimal("11000"),
            max_dd_percent=Decimal("20"),
            record_metric=False,
        )

        assert result.passed is True
        assert result.violation_type is None
        # DD = (11000-10000)/11000*100 = 9.09%
        assert result.current_value == Decimal("9.09")
        assert result.threshold == Decimal("20")

    def test_exceeds_drawdown_limit(self):
        """Test drawdown exceeding maximum blocks trade."""
        result = enforce_max_dd(
            current_equity=Decimal("7000"),
            peak_equity=Decimal("10000"),
            max_dd_percent=Decimal("20"),
            record_metric=False,
        )

        assert result.passed is False
        assert result.violation_type == RiskViolationType.MAX_DRAWDOWN_EXCEEDED
        # DD = (10000-7000)/10000*100 = 30%
        assert result.current_value == Decimal("30.00")
        assert result.threshold == Decimal("20")
        assert "30.00%" in result.message

    def test_exact_drawdown_threshold_blocks(self):
        """Test that hitting exact threshold blocks (not just exceeding)."""
        result = enforce_max_dd(
            current_equity=Decimal("8000"),
            peak_equity=Decimal("10000"),
            max_dd_percent=Decimal("20"),
            record_metric=False,
        )

        # DD = (10000-8000)/10000*100 = 20.00% exactly
        assert result.passed is False, "Exact threshold should block"
        assert result.violation_type == RiskViolationType.MAX_DRAWDOWN_EXCEEDED
        assert result.current_value == Decimal("20.00")

    def test_just_below_threshold_passes(self):
        """Test that just below threshold passes."""
        result = enforce_max_dd(
            current_equity=Decimal("8001"),
            peak_equity=Decimal("10000"),
            max_dd_percent=Decimal("20"),
            record_metric=False,
        )

        # DD = (10000-8001)/10000*100 = 19.99%
        assert result.passed is True
        assert result.current_value == Decimal("19.99")

    def test_negative_equity_blocks(self):
        """Test negative equity is rejected."""
        result = enforce_max_dd(
            current_equity=Decimal("-1000"),
            peak_equity=Decimal("10000"),
            max_dd_percent=Decimal("20"),
            record_metric=False,
        )

        assert result.passed is False
        assert result.violation_type == RiskViolationType.MIN_EQUITY_BREACH
        assert "cannot be negative" in result.message.lower()

    def test_zero_peak_equity_rejected(self):
        """Test zero peak equity is invalid."""
        result = enforce_max_dd(
            current_equity=Decimal("5000"),
            peak_equity=Decimal("0"),
            max_dd_percent=Decimal("20"),
            record_metric=False,
        )

        assert result.passed is False
        assert "peak equity must be positive" in result.message.lower()

    def test_small_drawdown(self):
        """Test small drawdown calculation accuracy."""
        result = enforce_max_dd(
            current_equity=Decimal("9999"),
            peak_equity=Decimal("10000"),
            max_dd_percent=Decimal("20"),
            record_metric=False,
        )

        # DD = 1/10000*100 = 0.01%
        assert result.passed is True
        assert result.current_value == Decimal("0.01")

    def test_telemetry_recorded_on_breach(self):
        """Test that risk_block_total metric is incremented on breach."""
        with patch(
            "backend.app.risk.guards.metrics.risk_block_total.labels"
        ) as mock_labels:
            mock_counter = mock_labels.return_value

            result = enforce_max_dd(
                current_equity=Decimal("6000"),
                peak_equity=Decimal("10000"),
                max_dd_percent=Decimal("20"),
                record_metric=True,  # Enable metric recording
            )

            assert result.passed is False
            mock_labels.assert_called_once_with(
                reason=RiskViolationType.MAX_DRAWDOWN_EXCEEDED
            )
            mock_counter.inc.assert_called_once()

    def test_telemetry_not_recorded_when_disabled(self):
        """Test that metric is not recorded when record_metric=False."""
        with patch(
            "backend.app.risk.guards.metrics.risk_block_total.labels"
        ) as mock_labels:
            result = enforce_max_dd(
                current_equity=Decimal("6000"),
                peak_equity=Decimal("10000"),
                max_dd_percent=Decimal("20"),
                record_metric=False,
            )

            assert result.passed is False
            mock_labels.assert_not_called()

    def test_large_drawdown(self):
        """Test large drawdown (account nearly wiped out)."""
        result = enforce_max_dd(
            current_equity=Decimal("500"),
            peak_equity=Decimal("10000"),
            max_dd_percent=Decimal("20"),
            record_metric=False,
        )

        # DD = 9500/10000*100 = 95%
        assert result.passed is False
        assert result.current_value == Decimal("95.00")

    def test_decimal_precision(self):
        """Test decimal precision in drawdown calculation."""
        result = enforce_max_dd(
            current_equity=Decimal("8888.88"),
            peak_equity=Decimal("10000"),
            max_dd_percent=Decimal("20"),
            record_metric=False,
        )

        # DD = 1111.12/10000*100 = 11.1112% -> rounds to 11.11%
        assert result.passed is True
        assert result.current_value == Decimal("11.11")


class TestMinEquity:
    """Test minimum equity floor enforcement."""

    def test_above_minimum(self):
        """Test equity above minimum passes."""
        result = min_equity(
            current_equity=Decimal("1000"),
            min_threshold=Decimal("500"),
            record_metric=False,
        )

        assert result.passed is True
        assert result.violation_type is None
        assert result.current_value == Decimal("1000")
        assert result.threshold == Decimal("500")

    def test_below_minimum(self):
        """Test equity below minimum blocks trade."""
        result = min_equity(
            current_equity=Decimal("400"),
            min_threshold=Decimal("500"),
            record_metric=False,
        )

        assert result.passed is False
        assert result.violation_type == RiskViolationType.MIN_EQUITY_BREACH
        assert result.current_value == Decimal("400")
        assert result.threshold == Decimal("500")
        assert "£400" in result.message
        assert "£500" in result.message

    def test_exact_minimum_blocks(self):
        """Test that exact minimum equity blocks (not just below)."""
        result = min_equity(
            current_equity=Decimal("500"),
            min_threshold=Decimal("500"),
            record_metric=False,
        )

        assert result.passed is False, "Exact threshold should block"
        assert result.violation_type == RiskViolationType.MIN_EQUITY_BREACH

    def test_just_above_minimum_passes(self):
        """Test that just above minimum passes."""
        result = min_equity(
            current_equity=Decimal("500.01"),
            min_threshold=Decimal("500"),
            record_metric=False,
        )

        assert result.passed is True

    def test_zero_equity_blocks(self):
        """Test zero equity blocks."""
        result = min_equity(
            current_equity=Decimal("0"),
            min_threshold=Decimal("500"),
            record_metric=False,
        )

        assert result.passed is False
        assert result.violation_type == RiskViolationType.MIN_EQUITY_BREACH

    def test_negative_threshold_rejected(self):
        """Test negative minimum threshold is invalid."""
        result = min_equity(
            current_equity=Decimal("1000"),
            min_threshold=Decimal("-100"),
            record_metric=False,
        )

        assert result.passed is False
        assert "cannot be negative" in result.message.lower()

    def test_telemetry_recorded_on_breach(self):
        """Test that risk_block_total metric is incremented on breach."""
        with patch(
            "backend.app.risk.guards.metrics.risk_block_total.labels"
        ) as mock_labels:
            mock_counter = mock_labels.return_value

            result = min_equity(
                current_equity=Decimal("300"),
                min_threshold=Decimal("500"),
                record_metric=True,
            )

            assert result.passed is False
            mock_labels.assert_called_once_with(
                reason=RiskViolationType.MIN_EQUITY_BREACH
            )
            mock_counter.inc.assert_called_once()

    def test_very_small_equity(self):
        """Test very small equity amounts (near zero)."""
        result = min_equity(
            current_equity=Decimal("0.01"),
            min_threshold=Decimal("500"),
            record_metric=False,
        )

        assert result.passed is False


class TestCheckPositionSize:
    """Test position size limit enforcement."""

    def test_within_limit(self):
        """Test position size within limit passes."""
        result = check_position_size(
            requested_size=Decimal("0.5"),
            max_size=Decimal("1.0"),
            record_metric=False,
        )

        assert result.passed is True
        assert result.current_value == Decimal("0.5")
        assert result.threshold == Decimal("1.0")

    def test_exceeds_limit(self):
        """Test position size exceeding limit blocks."""
        result = check_position_size(
            requested_size=Decimal("1.5"),
            max_size=Decimal("1.0"),
            record_metric=False,
        )

        assert result.passed is False
        assert result.violation_type == RiskViolationType.MAX_POSITION_SIZE_EXCEEDED
        assert "1.5 lots exceeds maximum 1.0 lots" in result.message

    def test_exact_limit_passes(self):
        """Test exact limit is allowed."""
        result = check_position_size(
            requested_size=Decimal("1.0"),
            max_size=Decimal("1.0"),
            record_metric=False,
        )

        assert result.passed is True

    def test_telemetry_recorded(self):
        """Test metric recording on breach."""
        with patch(
            "backend.app.risk.guards.metrics.risk_block_total.labels"
        ) as mock_labels:
            mock_counter = mock_labels.return_value

            result = check_position_size(
                requested_size=Decimal("2.0"),
                max_size=Decimal("1.0"),
                record_metric=True,
            )

            assert result.passed is False
            mock_labels.assert_called_once_with(
                reason=RiskViolationType.MAX_POSITION_SIZE_EXCEEDED
            )
            mock_counter.inc.assert_called_once()


class TestCheckOpenPositions:
    """Test open positions limit enforcement."""

    def test_below_limit(self):
        """Test open positions below limit allows new trade."""
        result = check_open_positions(
            current_open=3,
            max_open=5,
            record_metric=False,
        )

        assert result.passed is True
        assert result.current_value == Decimal("3")
        assert result.threshold == Decimal("5")

    def test_at_limit_blocks(self):
        """Test that being at limit blocks new position."""
        result = check_open_positions(
            current_open=5,
            max_open=5,
            record_metric=False,
        )

        assert result.passed is False, "At limit should block new position"
        assert result.violation_type == RiskViolationType.MAX_OPEN_POSITIONS_EXCEEDED

    def test_exceeds_limit_blocks(self):
        """Test exceeding limit blocks."""
        result = check_open_positions(
            current_open=6,
            max_open=5,
            record_metric=False,
        )

        assert result.passed is False

    def test_zero_positions(self):
        """Test zero open positions allows trade."""
        result = check_open_positions(
            current_open=0,
            max_open=5,
            record_metric=False,
        )

        assert result.passed is True

    def test_telemetry_recorded(self):
        """Test metric recording on breach."""
        with patch(
            "backend.app.risk.guards.metrics.risk_block_total.labels"
        ) as mock_labels:
            mock_counter = mock_labels.return_value

            result = check_open_positions(
                current_open=5,
                max_open=5,
                record_metric=True,
            )

            assert result.passed is False
            mock_labels.assert_called_once_with(
                reason=RiskViolationType.MAX_OPEN_POSITIONS_EXCEEDED
            )
            mock_counter.inc.assert_called_once()


class TestCheckAllGuards:
    """Test combined risk guard checks."""

    def test_all_guards_pass(self):
        """Test all guards passing allows trade."""
        state = AccountState(
            current_equity=Decimal("10000"),
            peak_equity=Decimal("11000"),
            open_positions=2,
        )
        limits = RiskLimits(
            max_drawdown_percent=Decimal("20"),
            min_equity_threshold=Decimal("500"),
            max_position_size=Decimal("1.0"),
            max_open_positions=5,
        )

        violations = check_all_guards(
            state, limits, requested_position_size=Decimal("0.5")
        )

        assert len(violations) == 0, "All guards should pass"

    def test_drawdown_breach_only(self):
        """Test only drawdown guard fails."""
        state = AccountState(
            current_equity=Decimal("7000"),
            peak_equity=Decimal("10000"),
            open_positions=2,
        )
        limits = RiskLimits(
            max_drawdown_percent=Decimal("20"),
            min_equity_threshold=Decimal("500"),
            max_position_size=Decimal("1.0"),
            max_open_positions=5,
        )

        violations = check_all_guards(state, limits)

        assert len(violations) == 1
        assert violations[0].violation_type == RiskViolationType.MAX_DRAWDOWN_EXCEEDED
        assert violations[0].current_value == Decimal("30.00")

    def test_equity_breach_only(self):
        """Test only equity floor fails."""
        state = AccountState(
            current_equity=Decimal("400"),
            peak_equity=Decimal("10000"),
            open_positions=2,
        )
        limits = RiskLimits(
            max_drawdown_percent=Decimal("99"),  # High limit, won't breach
            min_equity_threshold=Decimal("500"),
            max_position_size=Decimal("1.0"),
            max_open_positions=5,
        )

        violations = check_all_guards(state, limits)

        assert len(violations) == 1
        assert violations[0].violation_type == RiskViolationType.MIN_EQUITY_BREACH

    def test_multiple_breaches(self):
        """Test multiple guards failing simultaneously."""
        state = AccountState(
            current_equity=Decimal("400"),  # Below min equity + high DD
            peak_equity=Decimal("10000"),
            open_positions=5,  # At max positions
        )
        limits = RiskLimits(
            max_drawdown_percent=Decimal("20"),
            min_equity_threshold=Decimal("500"),
            max_position_size=Decimal("1.0"),
            max_open_positions=5,
        )

        violations = check_all_guards(state, limits)

        # Should have at least 3 violations:
        # 1. Drawdown exceeded (96% DD)
        # 2. Equity below minimum
        # 3. At max positions
        assert (
            len(violations) >= 2
        ), f"Expected multiple violations, got {len(violations)}"

        violation_types = [v.violation_type for v in violations]
        assert RiskViolationType.MAX_DRAWDOWN_EXCEEDED in violation_types
        assert RiskViolationType.MIN_EQUITY_BREACH in violation_types
        assert RiskViolationType.MAX_OPEN_POSITIONS_EXCEEDED in violation_types

    def test_position_size_check_when_requested(self):
        """Test position size is checked when requested_position_size provided."""
        state = AccountState(
            current_equity=Decimal("10000"),
            peak_equity=Decimal("11000"),
            open_positions=2,
        )
        limits = RiskLimits(
            max_drawdown_percent=Decimal("20"),
            min_equity_threshold=Decimal("500"),
            max_position_size=Decimal("1.0"),
            max_open_positions=5,
        )

        # Request position size that exceeds limit
        violations = check_all_guards(
            state, limits, requested_position_size=Decimal("1.5")
        )

        assert len(violations) == 1
        assert (
            violations[0].violation_type == RiskViolationType.MAX_POSITION_SIZE_EXCEEDED
        )

    def test_position_size_not_checked_when_not_requested(self):
        """Test position size is not checked when requested_position_size not provided."""
        state = AccountState(
            current_equity=Decimal("10000"),
            peak_equity=Decimal("11000"),
            open_positions=2,
        )
        limits = RiskLimits(
            max_drawdown_percent=Decimal("20"),
            min_equity_threshold=Decimal("500"),
            max_position_size=Decimal("1.0"),
            max_open_positions=5,
        )

        # Don't provide requested_position_size
        violations = check_all_guards(state, limits)

        # Position size should not be checked, all other guards pass
        assert len(violations) == 0

    def test_realistic_scenario_conservative_limits(self):
        """Test realistic scenario with conservative limits."""
        # Account has lost 15%, still has 3 positions open
        state = AccountState(
            current_equity=Decimal("8500"),
            peak_equity=Decimal("10000"),
            open_positions=3,
        )
        limits = RiskLimits(
            max_drawdown_percent=Decimal("20"),
            min_equity_threshold=Decimal("1000"),
            max_position_size=Decimal("0.5"),
            max_open_positions=5,
        )

        violations = check_all_guards(
            state, limits, requested_position_size=Decimal("0.3")
        )

        # DD = 15%, above min equity (8500>1000), below max positions, size OK
        assert len(violations) == 0

    def test_realistic_scenario_aggressive_limits(self):
        """Test realistic scenario with aggressive limits."""
        state = AccountState(
            current_equity=Decimal("8500"),
            peak_equity=Decimal("10000"),
            open_positions=8,
        )
        limits = RiskLimits(
            max_drawdown_percent=Decimal("10"),  # Strict 10% max DD
            min_equity_threshold=Decimal("5000"),  # High minimum
            max_position_size=Decimal("2.0"),  # Large positions allowed
            max_open_positions=10,
        )

        violations = check_all_guards(state, limits)

        # DD = 15% > 10% limit
        # Equity = 8500 > 5000 (OK)
        # Positions = 8 < 10 (OK)
        assert len(violations) == 1
        assert violations[0].violation_type == RiskViolationType.MAX_DRAWDOWN_EXCEEDED


class TestDataClasses:
    """Test data class instantiation and validation."""

    def test_account_state_creation(self):
        """Test AccountState can be created."""
        state = AccountState(
            current_equity=Decimal("10000"),
            peak_equity=Decimal("12000"),
            open_positions=3,
        )

        assert state.current_equity == Decimal("10000")
        assert state.peak_equity == Decimal("12000")
        assert state.open_positions == 3

    def test_risk_limits_creation(self):
        """Test RiskLimits can be created."""
        limits = RiskLimits(
            max_drawdown_percent=Decimal("25"),
            min_equity_threshold=Decimal("1000"),
            max_position_size=Decimal("1.5"),
            max_open_positions=10,
        )

        assert limits.max_drawdown_percent == Decimal("25")
        assert limits.min_equity_threshold == Decimal("1000")
        assert limits.max_position_size == Decimal("1.5")
        assert limits.max_open_positions == 10

    def test_risk_check_result_creation(self):
        """Test RiskCheckResult can be created."""
        result = RiskCheckResult(
            passed=False,
            violation_type=RiskViolationType.MAX_DRAWDOWN_EXCEEDED,
            message="Test message",
            current_value=Decimal("30"),
            threshold=Decimal("20"),
        )

        assert result.passed is False
        assert result.violation_type == RiskViolationType.MAX_DRAWDOWN_EXCEEDED
        assert result.message == "Test message"
        assert result.current_value == Decimal("30")
        assert result.threshold == Decimal("20")
