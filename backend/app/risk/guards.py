"""Risk guard functions for trade blocking and safety enforcement.

This module provides centralized risk checks that ALL strategies must pass
before executing trades. Guards enforce:
- Maximum drawdown limits (prevent further losses when equity drops below threshold)
- Minimum equity floor (block trades if account balance too low)
- Position size limits (prevent over-leveraging)

All guards return structured results indicating pass/fail with reasons for telemetry.
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from backend.app.observability.metrics import metrics


class RiskViolationType(str, Enum):
    """Types of risk violations that block trades."""

    MAX_DRAWDOWN_EXCEEDED = "max_drawdown_exceeded"
    MIN_EQUITY_BREACH = "min_equity_breach"
    MAX_POSITION_SIZE_EXCEEDED = "max_position_size_exceeded"
    MAX_OPEN_POSITIONS_EXCEEDED = "max_open_positions_exceeded"
    CORRELATION_LIMIT_EXCEEDED = "correlation_limit_exceeded"


@dataclass
class RiskCheckResult:
    """Result of a risk guard check.

    Attributes:
        passed: True if guard passed (trade allowed), False if blocked
        violation_type: Type of violation if blocked, None if passed
        message: Human-readable explanation
        current_value: Current value being checked (e.g., current DD%)
        threshold: Threshold that was breached (if applicable)
    """

    passed: bool
    violation_type: RiskViolationType | None
    message: str
    current_value: Decimal | None = None
    threshold: Decimal | None = None


def enforce_max_dd(
    current_equity: Decimal,
    peak_equity: Decimal,
    max_dd_percent: Decimal,
    record_metric: bool = True,
) -> RiskCheckResult:
    """Enforce maximum drawdown limit.

    Blocks trades if current drawdown exceeds maximum allowed percentage.

    Drawdown calculation:
        DD% = ((peak_equity - current_equity) / peak_equity) * 100

    Args:
        current_equity: Current account equity (e.g., £10,000)
        peak_equity: Historical peak equity (e.g., £12,000)
        max_dd_percent: Maximum allowed drawdown percentage (e.g., 20.0 = 20%)
        record_metric: Whether to record telemetry (default True)

    Returns:
        RiskCheckResult with pass/fail status and violation details

    Examples:
        >>> # Case 1: Within limits
        >>> result = enforce_max_dd(
        ...     current_equity=Decimal("10000"),
        ...     peak_equity=Decimal("11000"),
        ...     max_dd_percent=Decimal("20")
        ... )
        >>> assert result.passed is True
        >>> assert result.current_value == Decimal("9.09")  # 9.09% DD

        >>> # Case 2: Drawdown breach
        >>> result = enforce_max_dd(
        ...     current_equity=Decimal("7000"),
        ...     peak_equity=Decimal("10000"),
        ...     max_dd_percent=Decimal("20")
        ... )
        >>> assert result.passed is False
        >>> assert result.violation_type == RiskViolationType.MAX_DRAWDOWN_EXCEEDED
        >>> assert result.current_value == Decimal("30.00")  # 30% DD

        >>> # Case 3: Exact threshold (blocks)
        >>> result = enforce_max_dd(
        ...     current_equity=Decimal("8000"),
        ...     peak_equity=Decimal("10000"),
        ...     max_dd_percent=Decimal("20")
        ... )
        >>> assert result.passed is False  # 20% DD exactly
    """
    # Validate inputs
    if current_equity < 0:
        return RiskCheckResult(
            passed=False,
            violation_type=RiskViolationType.MIN_EQUITY_BREACH,
            message="Current equity cannot be negative",
            current_value=current_equity,
            threshold=Decimal("0"),
        )

    if peak_equity <= 0:
        return RiskCheckResult(
            passed=False,
            violation_type=None,
            message="Peak equity must be positive",
            current_value=peak_equity,
            threshold=Decimal("0"),
        )

    if current_equity > peak_equity:
        # Current equity exceeds peak (new high) - no drawdown
        return RiskCheckResult(
            passed=True,
            violation_type=None,
            message="Account at new equity high, no drawdown",
            current_value=Decimal("0"),
            threshold=max_dd_percent,
        )

    # Calculate current drawdown percentage
    drawdown_amount = peak_equity - current_equity
    current_dd_percent = (drawdown_amount / peak_equity) * Decimal("100")

    # Round to 2 decimal places for comparison
    current_dd_percent = current_dd_percent.quantize(Decimal("0.01"))

    # Check if drawdown exceeds maximum (>=, not >, to block at exact threshold)
    if current_dd_percent >= max_dd_percent:
        if record_metric:
            metrics.risk_block_total.labels(
                reason=RiskViolationType.MAX_DRAWDOWN_EXCEEDED
            ).inc()

        return RiskCheckResult(
            passed=False,
            violation_type=RiskViolationType.MAX_DRAWDOWN_EXCEEDED,
            message=f"Drawdown {current_dd_percent}% exceeds maximum {max_dd_percent}%",
            current_value=current_dd_percent,
            threshold=max_dd_percent,
        )

    # Drawdown within limits
    return RiskCheckResult(
        passed=True,
        violation_type=None,
        message=f"Drawdown {current_dd_percent}% within limit {max_dd_percent}%",
        current_value=current_dd_percent,
        threshold=max_dd_percent,
    )


def min_equity(
    current_equity: Decimal,
    min_threshold: Decimal,
    record_metric: bool = True,
) -> RiskCheckResult:
    """Enforce minimum equity floor.

    Blocks trades if account equity falls below minimum required balance.

    Args:
        current_equity: Current account equity (e.g., £1,000)
        min_threshold: Minimum required equity (e.g., £500)
        record_metric: Whether to record telemetry (default True)

    Returns:
        RiskCheckResult with pass/fail status and violation details

    Examples:
        >>> # Case 1: Above minimum
        >>> result = min_equity(
        ...     current_equity=Decimal("1000"),
        ...     min_threshold=Decimal("500")
        ... )
        >>> assert result.passed is True

        >>> # Case 2: Below minimum
        >>> result = min_equity(
        ...     current_equity=Decimal("400"),
        ...     min_threshold=Decimal("500")
        ... )
        >>> assert result.passed is False
        >>> assert result.violation_type == RiskViolationType.MIN_EQUITY_BREACH

        >>> # Case 3: Exact threshold (blocks)
        >>> result = min_equity(
        ...     current_equity=Decimal("500"),
        ...     min_threshold=Decimal("500")
        ... )
        >>> assert result.passed is False  # Blocks at exact threshold
    """
    # Validate inputs
    if min_threshold < 0:
        return RiskCheckResult(
            passed=False,
            violation_type=None,
            message="Minimum threshold cannot be negative",
            current_value=current_equity,
            threshold=min_threshold,
        )

    # Check if equity is below or equal to minimum (<=, not <, to block at exact threshold)
    if current_equity <= min_threshold:
        if record_metric:
            metrics.risk_block_total.labels(
                reason=RiskViolationType.MIN_EQUITY_BREACH
            ).inc()

        return RiskCheckResult(
            passed=False,
            violation_type=RiskViolationType.MIN_EQUITY_BREACH,
            message=f"Equity £{current_equity} at or below minimum £{min_threshold}",
            current_value=current_equity,
            threshold=min_threshold,
        )

    # Equity above minimum
    return RiskCheckResult(
        passed=True,
        violation_type=None,
        message=f"Equity £{current_equity} above minimum £{min_threshold}",
        current_value=current_equity,
        threshold=min_threshold,
    )


def check_position_size(
    requested_size: Decimal,
    max_size: Decimal,
    record_metric: bool = True,
) -> RiskCheckResult:
    """Check if requested position size exceeds maximum.

    Args:
        requested_size: Requested position size in lots (e.g., 2.5)
        max_size: Maximum allowed position size (e.g., 1.0)
        record_metric: Whether to record telemetry (default True)

    Returns:
        RiskCheckResult with pass/fail status

    Examples:
        >>> result = check_position_size(
        ...     requested_size=Decimal("0.5"),
        ...     max_size=Decimal("1.0")
        ... )
        >>> assert result.passed is True

        >>> result = check_position_size(
        ...     requested_size=Decimal("1.5"),
        ...     max_size=Decimal("1.0")
        ... )
        >>> assert result.passed is False
    """
    if requested_size > max_size:
        if record_metric:
            metrics.risk_block_total.labels(
                reason=RiskViolationType.MAX_POSITION_SIZE_EXCEEDED
            ).inc()

        return RiskCheckResult(
            passed=False,
            violation_type=RiskViolationType.MAX_POSITION_SIZE_EXCEEDED,
            message=f"Position size {requested_size} lots exceeds maximum {max_size} lots",
            current_value=requested_size,
            threshold=max_size,
        )

    return RiskCheckResult(
        passed=True,
        violation_type=None,
        message=f"Position size {requested_size} lots within limit {max_size} lots",
        current_value=requested_size,
        threshold=max_size,
    )


def check_open_positions(
    current_open: int,
    max_open: int,
    record_metric: bool = True,
) -> RiskCheckResult:
    """Check if opening new position would exceed maximum concurrent trades.

    Args:
        current_open: Current number of open positions
        max_open: Maximum allowed concurrent positions
        record_metric: Whether to record telemetry (default True)

    Returns:
        RiskCheckResult with pass/fail status

    Examples:
        >>> result = check_open_positions(current_open=3, max_open=5)
        >>> assert result.passed is True

        >>> result = check_open_positions(current_open=5, max_open=5)
        >>> assert result.passed is False  # Already at max
    """
    # Block if already at maximum (>=, not >, prevents opening when at limit)
    if current_open >= max_open:
        if record_metric:
            metrics.risk_block_total.labels(
                reason=RiskViolationType.MAX_OPEN_POSITIONS_EXCEEDED
            ).inc()

        return RiskCheckResult(
            passed=False,
            violation_type=RiskViolationType.MAX_OPEN_POSITIONS_EXCEEDED,
            message=f"Already at maximum {max_open} open positions",
            current_value=Decimal(str(current_open)),
            threshold=Decimal(str(max_open)),
        )

    return RiskCheckResult(
        passed=True,
        violation_type=None,
        message=f"{current_open} open positions, can open more (max {max_open})",
        current_value=Decimal(str(current_open)),
        threshold=Decimal(str(max_open)),
    )


@dataclass
class AccountState:
    """Current account state for risk checks.

    Attributes:
        current_equity: Current account equity
        peak_equity: Historical peak equity (for drawdown calculation)
        open_positions: Number of currently open positions
    """

    current_equity: Decimal
    peak_equity: Decimal
    open_positions: int


@dataclass
class RiskLimits:
    """Risk limits to enforce.

    Attributes:
        max_drawdown_percent: Maximum allowed drawdown (e.g., 20.0 = 20%)
        min_equity_threshold: Minimum required equity (e.g., 500.00)
        max_position_size: Maximum position size in lots (e.g., 1.0)
        max_open_positions: Maximum concurrent open positions (e.g., 5)
    """

    max_drawdown_percent: Decimal
    min_equity_threshold: Decimal
    max_position_size: Decimal
    max_open_positions: int


def check_all_guards(
    account_state: AccountState,
    risk_limits: RiskLimits,
    requested_position_size: Decimal | None = None,
) -> list[RiskCheckResult]:
    """Run all risk guards and return any violations.

    This is the main entry point for risk checks. It runs all applicable
    guards and returns a list of violations. If list is empty, all checks passed.

    Args:
        account_state: Current account state (equity, positions, etc.)
        risk_limits: Risk limits to enforce
        requested_position_size: If provided, also check position size limit

    Returns:
        List of RiskCheckResult for failed checks (empty if all passed)

    Examples:
        >>> # All guards pass
        >>> state = AccountState(
        ...     current_equity=Decimal("10000"),
        ...     peak_equity=Decimal("11000"),
        ...     open_positions=2
        ... )
        >>> limits = RiskLimits(
        ...     max_drawdown_percent=Decimal("20"),
        ...     min_equity_threshold=Decimal("500"),
        ...     max_position_size=Decimal("1.0"),
        ...     max_open_positions=5
        ... )
        >>> violations = check_all_guards(state, limits)
        >>> assert len(violations) == 0  # All passed

        >>> # Drawdown breach
        >>> state = AccountState(
        ...     current_equity=Decimal("7000"),
        ...     peak_equity=Decimal("10000"),
        ...     open_positions=2
        ... )
        >>> violations = check_all_guards(state, limits)
        >>> assert len(violations) == 1
        >>> assert violations[0].violation_type == RiskViolationType.MAX_DRAWDOWN_EXCEEDED

        >>> # Multiple breaches
        >>> state = AccountState(
        ...     current_equity=Decimal("400"),  # Below min equity
        ...     peak_equity=Decimal("10000"),
        ...     open_positions=5  # At max positions
        ... )
        >>> violations = check_all_guards(state, limits)
        >>> assert len(violations) >= 2  # Multiple violations
    """
    violations = []

    # Guard 1: Maximum drawdown
    dd_result = enforce_max_dd(
        current_equity=account_state.current_equity,
        peak_equity=account_state.peak_equity,
        max_dd_percent=risk_limits.max_drawdown_percent,
    )
    if not dd_result.passed:
        violations.append(dd_result)

    # Guard 2: Minimum equity floor
    equity_result = min_equity(
        current_equity=account_state.current_equity,
        min_threshold=risk_limits.min_equity_threshold,
    )
    if not equity_result.passed:
        violations.append(equity_result)

    # Guard 3: Maximum open positions
    positions_result = check_open_positions(
        current_open=account_state.open_positions,
        max_open=risk_limits.max_open_positions,
    )
    if not positions_result.passed:
        violations.append(positions_result)

    # Guard 4: Position size (if requested size provided)
    if requested_position_size is not None:
        size_result = check_position_size(
            requested_size=requested_position_size,
            max_size=risk_limits.max_position_size,
        )
        if not size_result.passed:
            violations.append(size_result)

    return violations
