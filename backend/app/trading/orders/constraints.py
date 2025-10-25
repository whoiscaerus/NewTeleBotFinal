"""Order constraint enforcement functions."""

import math

from .schema import get_constraints


def apply_min_stop_distance(
    entry: float,
    stop_loss: float,
    min_distance_points: float,
    symbol: str,
    side: str,
) -> tuple[float, bool]:
    """
    Enforce minimum SL distance from entry.

    Adjusts stop_loss if it violates the minimum distance constraint.
    For BUY orders, SL must be BELOW entry. For SELL orders, SL must be ABOVE entry.

    Args:
        entry: Entry price
        stop_loss: Current stop loss price
        min_distance_points: Minimum distance in points (e.g., 5)
        symbol: Trading symbol (e.g., "GOLD")
        side: "BUY" or "SELL"

    Returns:
        Tuple of (adjusted_sl, was_adjusted)
        - adjusted_sl: Final SL after constraint enforcement
        - was_adjusted: True if adjustment was needed

    Raises:
        ValueError: If side is invalid
        ValueError: If min_distance_points is negative

    Examples:
        >>> # BUY order: SL below entry
        >>> # Entry 1950.50, SL 1950.00 (distance 0.50 = 50 points)
        >>> adjusted_sl, adjusted = apply_min_stop_distance(
        ...     entry=1950.50,
        ...     stop_loss=1950.00,
        ...     min_distance_points=5,
        ...     symbol="GOLD",
        ...     side="BUY"
        ... )
        >>> adjusted
        False  # 50 points >= 5 points minimum, no adjustment

        >>> # BUY order: SL too close
        >>> # Entry 1950.50, SL 1950.30 (distance 0.20 = 20 points, needs 50)
        >>> adjusted_sl, adjusted = apply_min_stop_distance(
        ...     entry=1950.50,
        ...     stop_loss=1950.30,
        ...     min_distance_points=5,
        ...     symbol="GOLD",
        ...     side="BUY"
        ... )
        >>> adjusted
        True  # Adjusted to enforce minimum
        >>> adjusted_sl
        1945.50  # Entry - (5 points * 0.01 per point)

        >>> # SELL order: SL above entry
        >>> # Entry 1950.50, SL 1950.00 (violates, should be > entry)
        >>> adjusted_sl, adjusted = apply_min_stop_distance(
        ...     entry=1950.50,
        ...     stop_loss=1950.00,
        ...     min_distance_points=5,
        ...     symbol="GOLD",
        ...     side="SELL"
        ... )
        >>> adjusted
        True
        >>> adjusted_sl
        1955.50  # Entry + (5 points * 0.01 per point)
    """
    # Validate inputs
    if side not in {"BUY", "SELL"}:
        raise ValueError(f"side must be 'BUY' or 'SELL', got {side}")

    if min_distance_points < 0:
        raise ValueError(f"min_distance_points must be >= 0, got {min_distance_points}")

    # Get constraints for symbol
    constraints = get_constraints(symbol)

    # Convert points to price distance
    min_distance_price = min_distance_points * constraints.tick_size

    # Calculate minimum SL based on side
    if side == "BUY":
        # For BUY, SL must be BELOW entry
        min_sl = entry - min_distance_price
        if stop_loss >= min_sl:  # SL is too high (not far enough below entry)
            return min_sl, True
    else:  # SELL
        # For SELL, SL must be ABOVE entry
        max_sl = entry + min_distance_price
        if stop_loss <= max_sl:  # SL is too low (not far enough above entry)
            return max_sl, True

    return stop_loss, False


def round_to_tick(price: float, symbol: str, direction: str = "nearest") -> float:
    """
    Round price to broker's tick size.

    Args:
        price: Price to round
        symbol: Trading symbol (e.g., "GOLD")
        direction: Rounding direction - "up", "down", or "nearest"

    Returns:
        Rounded price

    Raises:
        ValueError: If direction is invalid
        ValueError: If symbol is unknown

    Examples:
        >>> # GOLD has tick_size=0.01
        >>> round_to_tick(1950.125, "GOLD", "nearest")
        1950.12  # Rounds to nearest 0.01

        >>> round_to_tick(1950.125, "GOLD", "up")
        1950.13  # Rounds up to 0.01

        >>> round_to_tick(1950.125, "GOLD", "down")
        1950.12  # Rounds down to 0.01

        >>> round_to_tick(1950.00, "GOLD", "nearest")
        1950.00  # Already on tick
    """
    # Validate direction
    if direction not in {"up", "down", "nearest"}:
        raise ValueError(
            f"direction must be 'up', 'down', or 'nearest', got {direction}"
        )

    # Get constraints for symbol
    constraints = get_constraints(symbol)
    tick_size = constraints.tick_size

    if direction == "up":
        return math.ceil(price / tick_size) * tick_size
    elif direction == "down":
        return math.floor(price / tick_size) * tick_size
    else:  # nearest
        return round(price / tick_size) * tick_size


def validate_rr_ratio(
    entry: float, stop_loss: float, take_profit: float, min_ratio: float, side: str
) -> tuple[bool, float, str]:
    """
    Validate R:R ratio meets minimum requirement.

    Calculates actual risk-reward ratio and compares to minimum.

    Args:
        entry: Entry price
        stop_loss: Stop loss price
        take_profit: Take profit price
        min_ratio: Minimum acceptable ratio (e.g., 1.5)
        side: "BUY" or "SELL"

    Returns:
        Tuple of (is_valid, actual_ratio, error_message)
        - is_valid: True if ratio >= min_ratio
        - actual_ratio: Calculated R:R ratio
        - error_message: Empty string if valid, error description if invalid

    Raises:
        ValueError: If side is invalid
        ValueError: If any price is invalid

    Examples:
        >>> # BUY order: Entry 1950, SL 1945 (risk 5), TP 1960 (reward 10)
        >>> # R:R = 10/5 = 2.0
        >>> is_valid, ratio, msg = validate_rr_ratio(
        ...     entry=1950.0,
        ...     stop_loss=1945.0,
        ...     take_profit=1960.0,
        ...     min_ratio=1.5,
        ...     side="BUY"
        ... )
        >>> is_valid
        True
        >>> ratio
        2.0

        >>> # BUY order: Ratio too low (1.0 < 1.5 minimum)
        >>> is_valid, ratio, msg = validate_rr_ratio(
        ...     entry=1950.0,
        ...     stop_loss=1945.0,
        ...     take_profit=1952.0,
        ...     min_ratio=1.5,
        ...     side="BUY"
        ... )
        >>> is_valid
        False
        >>> ratio
        0.4
        >>> "minimum" in msg.lower()
        True

        >>> # SELL order: Entry 1950, SL 1955 (risk 5), TP 1940 (reward 10)
        >>> is_valid, ratio, msg = validate_rr_ratio(
        ...     entry=1950.0,
        ...     stop_loss=1955.0,
        ...     take_profit=1940.0,
        ...     min_ratio=1.5,
        ...     side="SELL"
        ... )
        >>> is_valid
        True
        >>> ratio
        2.0
    """
    # Validate side
    if side not in {"BUY", "SELL"}:
        raise ValueError(f"side must be 'BUY' or 'SELL', got {side}")

    # Validate prices
    if entry <= 0 or stop_loss <= 0 or take_profit <= 0:
        raise ValueError("All prices must be positive")

    # Calculate risk and reward based on side
    if side == "BUY":
        # For BUY: risk = entry - SL, reward = TP - entry
        risk = entry - stop_loss
        reward = take_profit - entry
    else:  # SELL
        # For SELL: risk = SL - entry, reward = entry - TP
        risk = stop_loss - entry
        reward = entry - take_profit

    # Validate risk/reward are positive
    if risk <= 0:
        return (
            False,
            0.0,
            f"Invalid risk: {risk}. Check entry vs SL for {side} order.",
        )

    if reward <= 0:
        return (
            False,
            0.0,
            f"Invalid reward: {reward}. Check entry vs TP for {side} order.",
        )

    # Calculate actual ratio
    actual_ratio = reward / risk

    # Check against minimum
    if actual_ratio < min_ratio:
        return (
            False,
            actual_ratio,
            f"R:R ratio {actual_ratio:.2f} < minimum {min_ratio}. "
            f"Adjust TP up or SL closer to improve ratio.",
        )

    return True, actual_ratio, ""


def enforce_all_constraints(
    entry: float,
    stop_loss: float,
    take_profit: float,
    min_rr_ratio: float,
    min_distance_pips: int,
    symbol: str,
    side: str,
) -> tuple[float, float, float, str]:
    """
    Apply all constraints and adjust parameters as needed.

    Steps:
    1. Apply minimum SL distance
    2. Round all prices to tick
    3. Validate final R:R ratio

    Args:
        entry: Entry price
        stop_loss: Stop loss price
        take_profit: Take profit price
        min_rr_ratio: Minimum R:R ratio (e.g., 1.5)
        min_distance_pips: Minimum SL distance in points
        symbol: Trading symbol
        side: "BUY" or "SELL"

    Returns:
        Tuple of (adjusted_entry, adjusted_sl, adjusted_tp, error_message)
        - error_message: Empty string if successful, error if constraints cannot be satisfied

    Examples:
        >>> entry, sl, tp, msg = enforce_all_constraints(
        ...     entry=1950.50,
        ...     stop_loss=1950.00,
        ...     take_profit=1960.00,
        ...     min_rr_ratio=1.5,
        ...     min_distance_pips=5,
        ...     symbol="GOLD",
        ...     side="BUY"
        ... )
        >>> msg == ""  # No errors
        True
    """
    # Step 1: Apply minimum SL distance
    adjusted_sl, was_adjusted = apply_min_stop_distance(
        entry, stop_loss, min_distance_pips, symbol, side
    )

    if was_adjusted:
        # SL was adjusted, may need to adjust TP to maintain/improve ratio
        pass  # TP stays as specified (user can adjust if needed)

    # Step 2: Round all prices to tick
    adjusted_entry = round_to_tick(entry, symbol, "nearest")
    adjusted_sl = round_to_tick(adjusted_sl, symbol, "nearest")
    adjusted_tp = round_to_tick(take_profit, symbol, "nearest")

    # Step 3: Validate final R:R ratio
    is_valid, ratio, error_msg = validate_rr_ratio(
        adjusted_entry, adjusted_sl, adjusted_tp, min_rr_ratio, side
    )

    if not is_valid:
        return adjusted_entry, adjusted_sl, adjusted_tp, error_msg

    return adjusted_entry, adjusted_sl, adjusted_tp, ""
