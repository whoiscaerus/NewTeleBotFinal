# PR-015: Order Construction - Implementation Plan

**Status**: Phase 1 - PLANNING
**Estimated Duration**: 4 hours (1 planning + 1.5 implementation + 1.5 testing)
**Target Coverage**: ≥90%
**Target Tests**: 50+

---

## 📋 PR-015 SPECIFICATION SUMMARY

### Goal
Centralize trade parameter building with RR enforcement and broker constraints.

### Deliverables
```
backend/app/trading/orders/
  __init__.py          # Package initialization
  builder.py           # build_order(signal) -> OrderParams
  constraints.py       # apply_min_stop_distance, round_to_tick
  expiry.py            # compute_expiry(now, hours)
  schema.py            # OrderParams (Pydantic model)
```

### Core Requirements
1. **Validate R:R >= configured ratio** (from StrategyParams)
2. **Enforce min SL distance** (from broker constraints)
3. **Adjust entry/TP if needed** (constraint satisfaction)
4. **TTL/expiry embedded** for EA consumption
5. **Telemetry**: orders_built_total, orders_rejected_total{reason}

### Source Alignment
From DemoNoStochRSI:
- `rr_ratio = 3.25` (from StrategyParams)
- `min_stop_distance_points = 5` (from CONFIG)
- `order_expiry_hours = 100` (from CONFIG)
- Point value calculations for different symbols

---

## 📐 DATA MODEL

### Input: SignalCandidate (from PR-014)
```python
{
    "id": str,                      # UUID
    "signal_id": str,               # UUID
    "symbol": str,                  # "GOLD" or "XAUUSD"
    "side": int,                    # 0=BUY, 1=SELL
    "entry_price": float,           # Entry level
    "stop_loss": float,             # SL level
    "take_profit": float,           # TP level (optional, calculated)
    "risk_reward_ratio": float,     # R:R ratio
    "payload": dict,                # Metadata
    "created_at": datetime,
    "expires_at": datetime,
}
```

### Output: OrderParams (New Schema)
```python
{
    "order_id": str,                # UUID (new)
    "signal_id": str,               # From signal
    "symbol": str,                  # "GOLD"
    "order_type": str,              # "PENDING_SELL" (SHORT) / "PENDING_BUY" (LONG)
    "volume": float,                # Position size (from position_size calc)
    "entry_price": float,           # Final entry (may be adjusted)
    "stop_loss": float,             # Final SL (may be adjusted)
    "take_profit": float,           # Final TP (may be adjusted)
    "expiry_time": datetime,        # NOW + order_expiry_hours
    "risk_amount": float,           # SL - Entry (for SHORT), Entry - SL (for LONG)
    "reward_amount": float,         # TP - Entry magnitude
    "risk_reward_ratio": float,     # reward_amount / risk_amount
    "min_stop_distance_pips": int,  # Broker constraint (e.g., 5)
    "strategy_name": str,           # "fib_rsi"
    "created_at": datetime,
}
```

---

## 🔧 CORE FUNCTIONS

### 1. builder.py: build_order()

```python
async def build_order(
    signal: SignalCandidate,
    params: StrategyParams,
    broker_constraints: BrokerConstraints,
    current_time: datetime
) -> OrderParams:
    """
    Build a complete order from a signal with constraint enforcement.

    Steps:
    1. Validate signal (has entry, SL, TP)
    2. Apply min SL distance constraint
    3. Recalculate R:R if SL adjusted
    4. Validate final R:R >= configured ratio
    5. Calculate expiry time (now + order_expiry_hours)
    6. Calculate position size (if needed)
    7. Create and return OrderParams

    Raises:
    - ValueError: If constraint violations (R:R too low, SL too close, etc.)
    - OrderRejectedError: If cannot satisfy constraints
    """
    pass
```

### 2. constraints.py: Enforcement Functions

```python
def apply_min_stop_distance(
    entry: float,
    stop_loss: float,
    min_distance_points: float,
    symbol: str,
    side: str  # "BUY" or "SELL"
) -> Tuple[float, bool]:
    """
    Enforce minimum SL distance from entry.

    Returns: (adjusted_sl, was_adjusted)

    SHORT: SL must be ≥ entry + min_distance (SL above entry)
    LONG: SL must be ≤ entry - min_distance (SL below entry)
    """
    pass

def round_to_tick(
    price: float,
    symbol: str,
    round_direction: str = "nearest"  # "up", "down", "nearest"
) -> float:
    """
    Round price to broker's tick size.
    GOLD tick = 0.01
    """
    pass

def validate_rr_ratio(
    entry: float,
    stop_loss: float,
    take_profit: float,
    min_ratio: float,
    side: str
) -> Tuple[bool, float, str]:
    """
    Validate R:R ratio >= minimum.

    Returns: (is_valid, actual_ratio, error_message)
    """
    pass
```

### 3. expiry.py: TTL Calculation

```python
def compute_expiry(
    now: datetime,
    expiry_hours: int = 100
) -> datetime:
    """
    Calculate expiry time: now + expiry_hours.

    Returns: datetime in UTC
    """
    pass
```

### 4. schema.py: Pydantic Models

```python
class OrderParams(BaseModel):
    """Complete order parameters for broker submission."""
    order_id: str
    signal_id: str
    symbol: str
    order_type: str  # "PENDING_BUY", "PENDING_SELL"
    volume: float
    entry_price: float
    stop_loss: float
    take_profit: float
    expiry_time: datetime
    risk_amount: float
    reward_amount: float
    risk_reward_ratio: float
    min_stop_distance_pips: int
    strategy_name: str = "fib_rsi"
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Validation
    @validator("symbol")
    def validate_symbol(cls, v):
        if v not in ["GOLD", "XAUUSD"]:
            raise ValueError(f"Unknown symbol: {v}")
        return v

    @validator("order_type")
    def validate_order_type(cls, v):
        if v not in ["PENDING_BUY", "PENDING_SELL"]:
            raise ValueError(f"Invalid order type: {v}")
        return v

    @validator("risk_reward_ratio")
    def validate_rr_ratio(cls, v):
        if v < 1.0:
            raise ValueError(f"R:R ratio too low: {v} (minimum 1.0)")
        return v
```

---

## 🧪 TEST PLAN (50+ Tests)

### Test Classes and Cases

1. **TestOrderBuilder** (12 tests)
   - test_build_order_short_signal
   - test_build_order_long_signal
   - test_build_order_missing_tp
   - test_build_order_invalid_signal
   - test_build_order_calculation_accuracy
   - test_build_order_expiry_calculation
   - test_build_order_volume_calculation
   - test_build_order_strategy_params_applied
   - test_build_order_custom_rr_ratio
   - test_build_order_custom_expiry_hours
   - test_build_order_idempotent
   - test_build_order_timezone_handling

2. **TestConstraintEnforcement** (15 tests)
   - test_min_sl_distance_short_violation
   - test_min_sl_distance_short_ok
   - test_min_sl_distance_long_violation
   - test_min_sl_distance_long_ok
   - test_min_sl_distance_adjustment
   - test_min_sl_distance_multiple_adjustments
   - test_tick_rounding_nearest
   - test_tick_rounding_up
   - test_tick_rounding_down
   - test_tick_rounding_multiple_values
   - test_rr_ratio_validation_sufficient
   - test_rr_ratio_validation_insufficient
   - test_rr_ratio_validation_boundary
   - test_rr_ratio_validation_edge_cases
   - test_constraint_interaction_rr_after_adjustment

3. **TestExpiryCalculation** (8 tests)
   - test_compute_expiry_default_hours
   - test_compute_expiry_custom_hours
   - test_compute_expiry_zero_hours
   - test_compute_expiry_timezone_utc
   - test_compute_expiry_timezone_conversion
   - test_compute_expiry_dst_handling
   - test_compute_expiry_rounding
   - test_compute_expiry_multiple_days

4. **TestOrderSchema** (10 tests)
   - test_order_params_creation
   - test_order_params_validation_symbol
   - test_order_params_validation_order_type
   - test_order_params_validation_rr_ratio
   - test_order_params_calculation_fields
   - test_order_params_datetime_defaults
   - test_order_params_serialization
   - test_order_params_deserialization
   - test_order_params_edge_values
   - test_order_params_field_validation

5. **TestIntegration** (5+ tests)
   - test_complete_signal_to_order_workflow_short
   - test_complete_signal_to_order_workflow_long
   - test_constraint_violation_rejection
   - test_multi_signal_batch_processing
   - test_order_consistency_across_runs

### Coverage Targets
- builder.py: ≥90%
- constraints.py: ≥92%
- expiry.py: ≥95%
- schema.py: ≥88%
- Overall: ≥90%

---

## 🎯 IMPLEMENTATION PHASES

### Phase 1: Planning & Schema (30 minutes)
- [x] Understand PR-015 spec
- [ ] Create OrderParams schema
- [ ] Create BrokerConstraints schema
- [ ] Plan function signatures
- [ ] Create implementation plan

### Phase 2: Core Implementation (90 minutes)
- [ ] Implement schema.py (OrderParams)
- [ ] Implement expiry.py (compute_expiry)
- [ ] Implement constraints.py (all functions)
- [ ] Implement builder.py (build_order)
- [ ] Add telemetry/logging

### Phase 3: Testing (90 minutes)
- [ ] Test schema validation
- [ ] Test constraint enforcement
- [ ] Test expiry calculation
- [ ] Test integration workflows
- [ ] Achieve ≥90% coverage

### Phase 4: Verification (30 minutes)
- [ ] End-to-end signal→order test
- [ ] Create verification script
- [ ] Document results

---

## 📊 BROKER CONSTRAINTS (From DemoNoStochRSI)

### GOLD / XAUUSD
- **Tick Size**: 0.01 (precision: 2 decimals)
- **Min SL Distance**: 5 points (0.05 in price)
- **Min TP Distance**: 5 points (0.05 in price)
- **Max Stop Distance**: 200 points (2.00 in price)
- **Point Value**: 10 (1 pip × 10)
- **Order Expiry**: 100 hours

### Position Sizing
```python
risk_percent = 0.02  # 2% per trade
risk_amount = account_balance * risk_percent
pip_distance = abs(entry - sl) / 0.0001  # Points in pips
volume = risk_amount / (pip_distance * point_value)
```

---

## ✅ ACCEPTANCE CRITERIA

1. **Schema**: OrderParams with all required fields ✅
2. **Builder**: build_order() creates valid OrderParams ✅
3. **Constraints**: Min SL distance enforced ✅
4. **R:R Validation**: Rejects orders with R:R < configured ✅
5. **Expiry**: TTL correctly calculated ✅
6. **Tests**: 50+ tests, ≥90% coverage ✅
7. **Telemetry**: Track built/rejected orders ✅
8. **Integration**: Signal→Order workflow complete ✅

---

## 📚 DEPENDENCIES

**Requires (Already Complete)**:
- PR-014: SignalCandidate schema ✅
- PR-014: StrategyParams ✅
- PR-012: Market calendar (for timezone handling)

**No Database Changes** (uses in-memory schemas)

---

## 🚀 NEXT STEPS

1. **Review this plan** - Verify alignment with spec
2. **Create schema files** - Start with OrderParams
3. **Implement functions** - One file at a time
4. **Write tests incrementally** - Test-driven approach
5. **Verify E2E** - Signal to complete OrderParams

---

*Created: October 24, 2025*
*PR: PR-015 - Order Construction*
*Phase: 1/4 - PLANNING*
