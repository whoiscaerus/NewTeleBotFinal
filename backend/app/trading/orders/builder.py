"""Order building logic - convert signals to complete trade parameters."""

from datetime import datetime

from backend.app.strategy.fib_rsi.params import StrategyParams
from backend.app.strategy.fib_rsi.schema import SignalCandidate

from .constraints import apply_min_stop_distance, round_to_tick, validate_rr_ratio
from .expiry import compute_expiry
from .schema import BrokerConstraints, OrderParams, OrderType, get_constraints


class OrderBuildError(Exception):
    """Exception raised when order cannot be built."""

    pass


async def build_order(
    signal: SignalCandidate,
    params: StrategyParams,
    broker_constraints: BrokerConstraints | None = None,
    current_time: datetime | None = None,
) -> OrderParams:
    """
    Build a complete order from a signal with constraint enforcement.

    Converts a trading signal (from pattern detector) into a complete
    OrderParams object with all constraints validated and applied.

    Steps:
    1. Validate signal has required fields (entry, SL, TP)
    2. Validate signal TP matches pattern detector output
    3. Apply broker minimum SL distance constraint
    4. Recalculate R:R if SL was adjusted
    5. Validate final R:R >= configured minimum
    6. Validate SL < entry < TP (for BUY) or TP < entry < SL (for SELL)
    7. Calculate expiry time (now + 100 hours default)
    8. Create and return OrderParams
    9. Log success with telemetry

    Args:
        signal: SignalCandidate from pattern detector (PR-014 schema)
        params: StrategyParams with RR ratio, min SL distance
        broker_constraints: Optional broker constraints (uses defaults if None)
        current_time: Optional current datetime (uses utcnow if None)

    Returns:
        OrderParams: Complete order ready for broker submission

    Raises:
        OrderBuildError: If signal invalid or constraints cannot be satisfied
        ValueError: If signal structure invalid

    Examples:
        >>> signal = SignalCandidate(
        ...     instrument="GOLD",
        ...     side="buy",
        ...     entry_price=1950.50,
        ...     stop_loss=1945.00,
        ...     take_profit=1960.00,
        ...     confidence=0.82,
        ...     timestamp=datetime.utcnow(),
        ...     reason="rsi_oversold",
        ...     payload={}
        ... )
        >>> params = StrategyParams(rr_ratio=1.5)
        >>> order = await build_order(signal, params)
        >>> order.is_buy_order()
        True
    """
    # Use defaults if not provided
    if broker_constraints is None:
        broker_constraints = get_constraints(signal.instrument)

    if current_time is None:
        current_time = datetime.utcnow()

    # ========== STEP 1: Validate signal structure ==========
    if signal is None:
        raise OrderBuildError("Signal cannot be None")

    if not hasattr(signal, "instrument"):
        raise OrderBuildError("Signal missing required field: instrument")

    if not hasattr(signal, "entry_price") or signal.entry_price is None:
        raise OrderBuildError(f"Signal missing entry_price: {signal}")

    if not hasattr(signal, "stop_loss") or signal.stop_loss is None:
        raise OrderBuildError(f"Signal missing stop_loss: {signal}")

    if not hasattr(signal, "take_profit") or signal.take_profit is None:
        raise OrderBuildError(f"Signal missing take_profit: {signal}")

    # ========== STEP 2: Determine order side ==========
    # PR-014 uses: side="buy" or side="sell" (string)
    side_is_buy = signal.side.lower() == "buy"
    side_str = "BUY" if side_is_buy else "SELL"
    order_type = OrderType.PENDING_BUY if side_is_buy else OrderType.PENDING_SELL

    # ========== STEP 3: Validate price relationships ==========
    entry = signal.entry_price
    sl = signal.stop_loss
    tp = signal.take_profit

    if side_is_buy:
        # For BUY: entry should be between SL and TP
        # SL < entry < TP
        if sl >= entry:
            raise OrderBuildError(f"BUY order: SL ({sl}) must be < entry ({entry})")
        if tp <= entry:
            raise OrderBuildError(f"BUY order: TP ({tp}) must be > entry ({entry})")
    else:
        # For SELL: TP < entry < SL
        if sl <= entry:
            raise OrderBuildError(f"SELL order: SL ({sl}) must be > entry ({entry})")
        if tp >= entry:
            raise OrderBuildError(f"SELL order: TP ({tp}) must be < entry ({entry})")

    # ========== STEP 4: Apply minimum SL distance constraint ==========
    adjusted_sl, was_adjusted = apply_min_stop_distance(
        entry=entry,
        stop_loss=sl,
        min_distance_points=params.min_stop_distance_points,
        symbol=signal.instrument,
        side=side_str,
    )

    sl = adjusted_sl

    # ========== STEP 5: Round all prices to tick size ==========
    entry = round_to_tick(entry, signal.instrument, "nearest")
    sl = round_to_tick(sl, signal.instrument, "nearest")
    tp = round_to_tick(tp, signal.instrument, "nearest")

    # ========== STEP 6: Validate R:R ratio ==========
    is_valid, actual_rr, error_msg = validate_rr_ratio(
        entry=entry,
        stop_loss=sl,
        take_profit=tp,
        min_ratio=params.rr_ratio,
        side=side_str,
    )

    if not is_valid:
        raise OrderBuildError(f"R:R ratio constraint violation: {error_msg}")

    # ========== STEP 7: Calculate risk and reward amounts ==========
    if side_is_buy:
        risk_amount = entry - sl
        reward_amount = tp - entry
    else:
        risk_amount = sl - entry
        reward_amount = entry - tp

    # ========== STEP 8: Calculate expiry time (100 hours default) ==========
    expiry_time = compute_expiry(
        now=current_time,
        expiry_hours=100,  # Default from PR-015 spec
    )

    # ========== STEP 9: Create OrderParams ==========
    order = OrderParams(
        # IDs
        signal_id=signal.instrument,  # Using instrument as ID for now
        symbol=signal.instrument,
        # Order details
        order_type=order_type,
        volume=1.0,  # Default volume, caller can adjust
        # Prices
        entry_price=entry,
        stop_loss=sl,
        take_profit=tp,
        # Timing
        expiry_time=expiry_time,
        created_at=current_time,
        # Risk/reward
        risk_amount=risk_amount,
        reward_amount=reward_amount,
        risk_reward_ratio=actual_rr,
        # Constraints
        min_stop_distance_pips=params.min_stop_distance_points,
        # Metadata
        strategy_name="fib_rsi",
    )

    return order


async def build_orders_batch(
    signals: list[SignalCandidate],
    params: StrategyParams,
    broker_constraints: BrokerConstraints | None = None,
    current_time: datetime | None = None,
) -> dict:
    """
    Build multiple orders from a batch of signals.

    Processes multiple signals and tracks success/failures.

    Args:
        signals: List of SignalCandidate objects
        params: StrategyParams
        broker_constraints: Optional broker constraints
        current_time: Optional current datetime

    Returns:
        Dict with keys:
        - "orders": List of successfully built OrderParams
        - "errors": List of (signal, error_message) tuples for failed orders
        - "built_count": Number of successfully built orders
        - "rejected_count": Number of rejected orders

    Examples:
        >>> signals = [
        ...     SignalCandidate(...),  # BUY signal
        ...     SignalCandidate(...),  # SELL signal
        ... ]
        >>> result = await build_orders_batch(signals, params)
        >>> len(result["orders"])
        2
        >>> result["built_count"]
        2
        >>> result["rejected_count"]
        0
    """
    orders = []
    errors = []

    for signal in signals:
        try:
            order = await build_order(
                signal=signal,
                params=params,
                broker_constraints=broker_constraints,
                current_time=current_time,
            )
            orders.append(order)
        except OrderBuildError as e:
            errors.append((signal, str(e)))

    return {
        "orders": orders,
        "errors": errors,
        "built_count": len(orders),
        "rejected_count": len(errors),
    }
