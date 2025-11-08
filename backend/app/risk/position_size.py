"""Position sizing calculations with broker tick rounding.

This module calculates position sizes based on risk parameters and rounds
to broker-compatible tick sizes. Handles:
- Risk-based position sizing (% of equity at risk)
- Tick rounding (down/up/nearest to broker step)
- Broker constraints (min lot, max lot, step lot)

All calculations use Decimal for precision in financial calculations.
"""

from decimal import ROUND_DOWN, ROUND_HALF_UP, ROUND_UP, Decimal
from enum import Enum


class RoundingMode(str, Enum):
    """Rounding modes for position size."""

    DOWN = "down"  # Always round down (conservative)
    UP = "up"  # Always round up
    NEAREST = "nearest"  # Round to nearest tick


def calculate_lot_size(
    equity: Decimal,
    risk_percent: Decimal,
    stop_distance_pips: Decimal,
    pip_value: Decimal,
) -> Decimal:
    """Calculate position size in lots based on risk parameters.

    Formula:
        Risk Amount (£) = Equity * (Risk % / 100)
        Lot Size = Risk Amount / (Stop Distance in Pips * Pip Value per Lot)

    Args:
        equity: Current account equity (e.g., £10,000)
        risk_percent: Risk as percentage of equity (e.g., 2.0 = 2%)
        stop_distance_pips: Distance to stop loss in pips (e.g., 50)
        pip_value: Value of 1 pip for 1 lot (e.g., £10 for EURUSD)

    Returns:
        Position size in lots (unrounded, may have many decimals)

    Raises:
        ValueError: If inputs are invalid (zero/negative values)

    Examples:
        >>> # Example 1: Standard EURUSD trade
        >>> size = calculate_lot_size(
        ...     equity=Decimal("10000"),
        ...     risk_percent=Decimal("2.0"),
        ...     stop_distance_pips=Decimal("50"),
        ...     pip_value=Decimal("10")
        ... )
        >>> assert size == Decimal("0.4")  # 0.4 lots

        >>> # Example 2: Tight stop
        >>> size = calculate_lot_size(
        ...     equity=Decimal("10000"),
        ...     risk_percent=Decimal("1.0"),
        ...     stop_distance_pips=Decimal("20"),
        ...     pip_value=Decimal("10")
        ... )
        >>> assert size == Decimal("0.5")  # 0.5 lots

        >>> # Example 3: GOLD trade (different pip value)
        >>> size = calculate_lot_size(
        ...     equity=Decimal("10000"),
        ...     risk_percent=Decimal("2.0"),
        ...     stop_distance_pips=Decimal("10"),
        ...     pip_value=Decimal("100")  # GOLD has higher pip value
        ... )
        >>> assert size == Decimal("0.2")  # 0.2 lots
    """
    # Validate inputs
    if equity <= 0:
        raise ValueError(f"Equity must be positive, got {equity}")

    if risk_percent <= 0:
        raise ValueError(f"Risk percent must be positive, got {risk_percent}")

    if stop_distance_pips <= 0:
        raise ValueError(f"Stop distance must be positive, got {stop_distance_pips}")

    if pip_value <= 0:
        raise ValueError(f"Pip value must be positive, got {pip_value}")

    # Calculate risk amount in account currency
    risk_amount = equity * (risk_percent / Decimal("100"))

    # Calculate position size
    # Lot Size = Risk Amount / (Stop Distance * Pip Value)
    lot_size = risk_amount / (stop_distance_pips * pip_value)

    return lot_size


def round_to_tick(
    lot_size: Decimal,
    tick_size: Decimal,
    mode: RoundingMode = RoundingMode.DOWN,
) -> Decimal:
    """Round position size to broker tick size.

    Brokers require position sizes in specific increments (tick sizes):
    - FOREX: 0.01 lots (micro lots)
    - GOLD/SILVER: 0.01 lots
    - Indices: 0.1 lots
    - Some brokers: 0.1 or 1.0 lot minimum

    Args:
        lot_size: Calculated lot size (may have many decimals)
        tick_size: Broker tick size (e.g., 0.01, 0.1, 1.0)
        mode: Rounding mode (DOWN=conservative, UP=aggressive, NEAREST=closest)

    Returns:
        Lot size rounded to nearest tick

    Raises:
        ValueError: If tick_size is invalid

    Examples:
        >>> # Round down (conservative)
        >>> rounded = round_to_tick(
        ...     lot_size=Decimal("0.437"),
        ...     tick_size=Decimal("0.01"),
        ...     mode=RoundingMode.DOWN
        ... )
        >>> assert rounded == Decimal("0.43")

        >>> # Round up
        >>> rounded = round_to_tick(
        ...     lot_size=Decimal("0.437"),
        ...     tick_size=Decimal("0.01"),
        ...     mode=RoundingMode.UP
        ... )
        >>> assert rounded == Decimal("0.44")

        >>> # Round to nearest
        >>> rounded = round_to_tick(
        ...     lot_size=Decimal("0.437"),
        ...     tick_size=Decimal("0.01"),
        ...     mode=RoundingMode.NEAREST
        ... )
        >>> assert rounded == Decimal("0.44")  # Closer to 0.44

        >>> # Tick size 0.1 (indices)
        >>> rounded = round_to_tick(
        ...     lot_size=Decimal("1.76"),
        ...     tick_size=Decimal("0.1"),
        ...     mode=RoundingMode.DOWN
        ... )
        >>> assert rounded == Decimal("1.7")

        >>> # Tick size 1.0 (whole lots)
        >>> rounded = round_to_tick(
        ...     lot_size=Decimal("2.8"),
        ...     tick_size=Decimal("1.0"),
        ...     mode=RoundingMode.DOWN
        ... )
        >>> assert rounded == Decimal("2.0")
    """
    # Validate tick size
    if tick_size <= 0:
        raise ValueError(f"Tick size must be positive, got {tick_size}")

    # Handle zero lot size
    if lot_size == 0:
        return Decimal("0")

    # Calculate number of ticks
    num_ticks = lot_size / tick_size

    # Apply rounding mode
    if mode == RoundingMode.DOWN:
        rounded_ticks = num_ticks.quantize(Decimal("1"), rounding=ROUND_DOWN)
    elif mode == RoundingMode.UP:
        rounded_ticks = num_ticks.quantize(Decimal("1"), rounding=ROUND_UP)
    elif mode == RoundingMode.NEAREST:
        rounded_ticks = num_ticks.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    else:
        raise ValueError(f"Invalid rounding mode: {mode}")

    # Convert back to lot size
    rounded_lot_size = rounded_ticks * tick_size

    return rounded_lot_size


def validate_broker_constraints(
    lot_size: Decimal,
    min_lot: Decimal,
    max_lot: Decimal,
    step_lot: Decimal,
) -> Decimal:
    """Validate and adjust position size to broker constraints.

    Ensures position size:
    1. Is at or above minimum lot size
    2. Does not exceed maximum lot size
    3. Is rounded to valid step size

    Args:
        lot_size: Requested position size
        min_lot: Broker minimum lot size (e.g., 0.01)
        max_lot: Broker maximum lot size (e.g., 100.0)
        step_lot: Broker step size/tick size (e.g., 0.01)

    Returns:
        Adjusted lot size within broker constraints

    Raises:
        ValueError: If lot_size is below minimum or constraints invalid

    Examples:
        >>> # Within constraints
        >>> adjusted = validate_broker_constraints(
        ...     lot_size=Decimal("0.5"),
        ...     min_lot=Decimal("0.01"),
        ...     max_lot=Decimal("100.0"),
        ...     step_lot=Decimal("0.01")
        ... )
        >>> assert adjusted == Decimal("0.5")

        >>> # Exceeds maximum
        >>> adjusted = validate_broker_constraints(
        ...     lot_size=Decimal("150.0"),
        ...     min_lot=Decimal("0.01"),
        ...     max_lot=Decimal("100.0"),
        ...     step_lot=Decimal("0.01")
        ... )
        >>> assert adjusted == Decimal("100.0")  # Capped at max

        >>> # Below minimum
        >>> try:
        ...     adjusted = validate_broker_constraints(
        ...         lot_size=Decimal("0.005"),
        ...         min_lot=Decimal("0.01"),
        ...         max_lot=Decimal("100.0"),
        ...         step_lot=Decimal("0.01")
        ...     )
        ...     assert False, "Should raise ValueError"
        ... except ValueError as e:
        ...     assert "below minimum" in str(e)

        >>> # Not on step boundary (rounds down)
        >>> adjusted = validate_broker_constraints(
        ...     lot_size=Decimal("0.437"),
        ...     min_lot=Decimal("0.01"),
        ...     max_lot=Decimal("100.0"),
        ...     step_lot=Decimal("0.01")
        ... )
        >>> assert adjusted == Decimal("0.43")
    """
    # Validate constraints
    if min_lot <= 0:
        raise ValueError(f"Min lot must be positive, got {min_lot}")

    if max_lot <= 0:
        raise ValueError(f"Max lot must be positive, got {max_lot}")

    if step_lot <= 0:
        raise ValueError(f"Step lot must be positive, got {step_lot}")

    if min_lot > max_lot:
        raise ValueError(f"Min lot {min_lot} exceeds max lot {max_lot}")

    # Round to step size (conservative - round down)
    adjusted_size = round_to_tick(lot_size, step_lot, mode=RoundingMode.DOWN)

    # Check minimum
    if adjusted_size < min_lot:
        raise ValueError(
            f"Position size {adjusted_size} below minimum {min_lot} "
            f"(original: {lot_size}, step: {step_lot})"
        )

    # Cap at maximum
    if adjusted_size > max_lot:
        adjusted_size = max_lot

    return adjusted_size


def calculate_position_with_constraints(
    equity: Decimal,
    risk_percent: Decimal,
    stop_distance_pips: Decimal,
    pip_value: Decimal,
    min_lot: Decimal = Decimal("0.01"),
    max_lot: Decimal = Decimal("100.0"),
    step_lot: Decimal = Decimal("0.01"),
) -> Decimal:
    """Calculate position size with all validations and broker constraints.

    This is the main entry point for position sizing. It:
    1. Calculates raw lot size based on risk
    2. Rounds to broker tick size
    3. Validates against broker min/max constraints

    Args:
        equity: Current account equity
        risk_percent: Risk as percentage of equity
        stop_distance_pips: Distance to stop loss in pips
        pip_value: Value of 1 pip for 1 lot
        min_lot: Broker minimum lot size (default 0.01)
        max_lot: Broker maximum lot size (default 100.0)
        step_lot: Broker step size (default 0.01)

    Returns:
        Final position size ready for broker order

    Raises:
        ValueError: If inputs invalid or size below broker minimum

    Examples:
        >>> # Standard EURUSD trade
        >>> size = calculate_position_with_constraints(
        ...     equity=Decimal("10000"),
        ...     risk_percent=Decimal("2.0"),
        ...     stop_distance_pips=Decimal("50"),
        ...     pip_value=Decimal("10"),
        ...     min_lot=Decimal("0.01"),
        ...     max_lot=Decimal("100.0"),
        ...     step_lot=Decimal("0.01")
        ... )
        >>> assert size == Decimal("0.40")  # 0.4 lots rounded

        >>> # Small account - below minimum
        >>> try:
        ...     size = calculate_position_with_constraints(
        ...         equity=Decimal("100"),
        ...         risk_percent=Decimal("1.0"),
        ...         stop_distance_pips=Decimal("50"),
        ...         pip_value=Decimal("10"),
        ...         min_lot=Decimal("0.01"),
        ...         max_lot=Decimal("100.0"),
        ...         step_lot=Decimal("0.01")
        ...     )
        ...     assert False, "Should raise ValueError"
        ... except ValueError as e:
        ...     assert "below minimum" in str(e)

        >>> # Large position - exceeds maximum
        >>> size = calculate_position_with_constraints(
        ...     equity=Decimal("1000000"),
        ...     risk_percent=Decimal("5.0"),
        ...     stop_distance_pips=Decimal("10"),
        ...     pip_value=Decimal("10"),
        ...     min_lot=Decimal("0.01"),
        ...     max_lot=Decimal("10.0"),  # Small max
        ...     step_lot=Decimal("0.01")
        ... )
        >>> assert size == Decimal("10.0")  # Capped at max
    """
    # Step 1: Calculate raw lot size
    raw_size = calculate_lot_size(equity, risk_percent, stop_distance_pips, pip_value)

    # Step 2: Validate and adjust to broker constraints
    final_size = validate_broker_constraints(raw_size, min_lot, max_lot, step_lot)

    return final_size


def calculate_risk_amount(
    lot_size: Decimal,
    stop_distance_pips: Decimal,
    pip_value: Decimal,
) -> Decimal:
    """Calculate risk amount (potential loss) for a given position.

    This is the inverse of calculate_lot_size. Use it to verify that
    the final rounded lot size results in acceptable risk.

    Args:
        lot_size: Position size in lots
        stop_distance_pips: Distance to stop loss in pips
        pip_value: Value of 1 pip for 1 lot

    Returns:
        Risk amount in account currency

    Examples:
        >>> # 0.5 lot EURUSD with 50 pip stop
        >>> risk = calculate_risk_amount(
        ...     lot_size=Decimal("0.5"),
        ...     stop_distance_pips=Decimal("50"),
        ...     pip_value=Decimal("10")
        ... )
        >>> assert risk == Decimal("250")  # £250 at risk

        >>> # Verify round-trip calculation
        >>> equity = Decimal("10000")
        >>> risk_pct = Decimal("2.0")
        >>> stop_pips = Decimal("50")
        >>> pip_val = Decimal("10")
        >>>
        >>> # Calculate lot size
        >>> lot = calculate_lot_size(equity, risk_pct, stop_pips, pip_val)
        >>> # Round to tick
        >>> lot_rounded = round_to_tick(lot, Decimal("0.01"), RoundingMode.DOWN)
        >>> # Calculate actual risk
        >>> actual_risk = calculate_risk_amount(lot_rounded, stop_pips, pip_val)
        >>> expected_risk = equity * (risk_pct / Decimal("100"))
        >>> # Actual risk should be <= expected (due to rounding down)
        >>> assert actual_risk <= expected_risk
    """
    if lot_size < 0:
        raise ValueError(f"Lot size must be non-negative, got {lot_size}")

    if stop_distance_pips < 0:
        raise ValueError(
            f"Stop distance must be non-negative, got {stop_distance_pips}"
        )

    if pip_value < 0:
        raise ValueError(f"Pip value must be non-negative, got {pip_value}")

    risk_amount = lot_size * stop_distance_pips * pip_value

    return risk_amount
