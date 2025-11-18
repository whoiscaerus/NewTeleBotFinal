# 🔧 Critical Model Fixes Required

Generated: 2025-11-18

## Models With Test Failures

### 1. OpenPosition (6 failures)

**Location**: `backend/app/data_pipeline/models.py` (or similar)

**Tests Failing**:
- test_buy_position_sl_breach
- test_buy_position_tp_breach
- test_sell_position_sl_breach
- test_sell_position_tp_breach
- test_position_with_no_owner_levels
- test_position_with_only_sl_set

**Test Constructor**:
```python
position = OpenPosition(
    approval_id='92d0c90b-7ad8-4ca6-9284-6876211174ad',
    device_id='2691f9d5-3820-4ec0-9af9-6d8e83b6358c',
    entry_price=2655.0,
    execution_id='80e27e57-733a-44d9-853b-a2d8dda1615a',
    id='5b352dd0-dbcb-4fef-9f42-e0f4ca8e0d70',
    instrument='XAUUSD',
    owner_sl=2645.0,
    owner_tp=2670.0,
    side=0,  # BUY
    signal_id='...'
)
```

**Diagnostics Needed**:
1. ✓ Does OpenPosition model exist?
2. ✓ Which fields are defined?
3. ✓ Are `owner_sl`, `owner_tp` nullable?
4. ✓ What is the `side` field type? (int, enum, str?)
5. ✓ Are there any field validators blocking construction?

**Command to Diagnose**:
```bash
cd backend
python -c "from backend.app.data_pipeline.models import OpenPosition; import inspect; print(inspect.signature(OpenPosition.__init__))"
python -c "from backend.app.data_pipeline.models import OpenPosition; print(OpenPosition.__table__.columns.keys())"
```

---

### 2. SymbolPrice (5+ failures from test_data_pipeline.py)

**Location**: `backend/app/data_pipeline/models.py`

**Tests Failing**:
- test_symbol_price_creation
- test_symbol_price_get_mid_price
- test_symbol_price_get_spread
- test_symbol_price_get_spread_percent
- test_symbol_price_repr

**Test Constructor**:
```python
price = SymbolPrice(
    ask=1950.75,
    bid=1950.5,
    id='b23ea4e5-8e19-41f8-87d3-a31ca55ef18f',
    symbol='GOLD',
    timestamp=datetime.datetime(2025, 11, 17, 20, 5, 54, 341878)
)
```

**Potential Issues**:
1. Timestamp might need timezone (UTC)
   ```python
   from datetime import datetime, timezone
   timestamp=datetime.now(timezone.utc)
   ```

2. Numeric fields might require `Decimal` type
   ```python
   from decimal import Decimal
   ask=Decimal('1950.75'),
   bid=Decimal('1950.5'),
   ```

3. Field validation might be too strict

**Commands to Check**:
```bash
python -c "from backend.app.data_pipeline.models import SymbolPrice; print(SymbolPrice.__table__.columns)"
python -c "from backend.app.data_pipeline.models import SymbolPrice; sp = SymbolPrice(ask=1950.75, bid=1950.5, symbol='GOLD', id='test'); print(sp)"
```

---

### 3. OHLCCandle (5+ failures from test_data_pipeline.py)

**Location**: `backend/app/data_pipeline/models.py`

**Tests Failing**:
- test_ohlc_candle_creation
- test_ohlc_candle_get_range
- (and others)

**Test Constructor**:
```python
candle = OHLCCandle(
    close=1.0865,
    high=1.0875,
    id='cd6ad57c-7bc2-467a-859f-ff6834ecbfd5',
    low=1.084,
    open=1.085,
    symbol='EURUSD',
    time_open=datetime.datetime(2025, 11, 17, 20, 5, 56, 42398),
    volume=1000000
)
```

**Likely Issues**:
- Same as SymbolPrice (Decimal types, timezone)
- Plus: volume might need int/Decimal clarification

---

### 4. Trade (21 failures from test_pr_016_trade_store.py)

**Location**: `backend/app/trading/models.py` (or similar)

**Tests Failing**:
- test_trade_creation_valid
- test_trade_buy_price_relationships
- test_trade_sell_creation
- (and 18 more)

**Expected Constructor** (based on names):
```python
trade = Trade(
    id='...',
    user_id='...',
    instrument='EURUSD',
    side='BUY',  # or 0/1 ?
    entry_price=1.0850,
    exit_price=1.0880,
    quantity=100,
    status='closed',
    pnl=30.0,
    pnl_percent=0.28,
    opened_at=datetime.now(timezone.utc),
    closed_at=datetime.now(timezone.utc),
    # ... other fields
)
```

**Commands to Diagnose**:
```bash
python -c "from backend.app.trading.models import Trade; print(Trade.__table__.columns.keys())"
python -c "from backend.app.trading.models import Trade; t = Trade(side='BUY', instrument='EURUSD', entry_price=1.085, quantity=100); print(t)"
```

---

## Quick Diagnosis Script

Save as `scripts/diagnose_models.py`:

```python
#!/usr/bin/env python3
"""Diagnose model schema mismatches."""

from backend.app.data_pipeline.models import OpenPosition, SymbolPrice, OHLCCandle
from backend.app.trading.models import Trade
from sqlalchemy import inspect as sa_inspect
from datetime import datetime, timezone
from decimal import Decimal


def diagnose_model(model_class):
    """Print model schema and try instantiation."""
    print(f"\n{'='*60}")
    print(f"Model: {model_class.__name__}")
    print(f"{'='*60}")

    # Get columns
    inspector = sa_inspect(model_class)
    print("\nColumns:")
    for col in inspector.columns:
        nullable = "NULLABLE" if col.nullable else "NOT NULL"
        print(f"  - {col.name}: {col.type} [{nullable}]")

    # Try example instantiation
    print("\nTrying instantiation...")
    try:
        if model_class == OpenPosition:
            obj = OpenPosition(
                approval_id='test-id-1',
                device_id='test-id-2',
                entry_price=2655.0,
                execution_id='test-id-3',
                id='test-id-4',
                instrument='XAUUSD',
                owner_sl=2645.0,
                owner_tp=2670.0,
                side=0,
                signal_id='test-id-5'
            )
            print(f"  ✓ Success: {obj}")

        elif model_class == SymbolPrice:
            obj = SymbolPrice(
                ask=Decimal('1950.75'),
                bid=Decimal('1950.5'),
                id='test-id',
                symbol='GOLD',
                timestamp=datetime.now(timezone.utc)
            )
            print(f"  ✓ Success: {obj}")

        elif model_class == OHLCCandle:
            obj = OHLCCandle(
                close=Decimal('1.0865'),
                high=Decimal('1.0875'),
                id='test-id',
                low=Decimal('1.084'),
                open=Decimal('1.085'),
                symbol='EURUSD',
                time_open=datetime.now(timezone.utc),
                volume=1000000
            )
            print(f"  ✓ Success: {obj}")

        elif model_class == Trade:
            obj = Trade(
                id='test-id',
                entry_price=Decimal('1.085'),
                instrument='EURUSD',
                side=0,  # BUY
                quantity=100
            )
            print(f"  ✓ Success: {obj}")

    except Exception as e:
        print(f"  ✗ Error: {type(e).__name__}")
        print(f"    Message: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    diagnose_model(OpenPosition)
    diagnose_model(SymbolPrice)
    diagnose_model(OHLCCandle)
    diagnose_model(Trade)
```

**Run it**:
```bash
cd backend
python ../scripts/diagnose_models.py
```

---

## Check Rate Limiter Issues (11 failures)

**File**: `tests/test_pr_005_ratelimit.py`

**Tests Failing**:
- test_tokens_consumed_on_request
- test_rate_limit_enforced_when_tokens_exhausted
- test_different_users_have_separate_buckets
- (and 8 more)

**Diagnostics**:
```bash
# Try importing rate limiter
python -c "from backend.app.core.ratelimit import RateLimiter; print('✓ Import OK')" 2>&1

# Check if Redis is available
python -c "from redis import Redis; r = Redis(); r.ping(); print('✓ Redis OK')" 2>&1

# Try running just rate limit tests
pytest tests/test_pr_005_ratelimit.py::test_tokens_consumed_on_request -vv 2>&1 | tail -50
```

---

## Check Poll Issues (7 failures)

**File**: `tests/test_poll_v2.py`

**Tests Failing**:
- test_record_poll_no_approvals
- test_record_poll_with_approvals
- test_record_multiple_polls
- (and 4 more)

**Diagnostics**:
```bash
# Try importing polling module
python -c "from backend.app.polling.service import PollService; print('✓ Import OK')" 2>&1

# Run specific test
pytest tests/test_poll_v2.py::test_record_poll_no_approvals -vv 2>&1 | tail -50
```

---

## Check Async/Retry Issues (7 failures)

**File**: `tests/test_pr_017_018_integration.py`

**Tests Failing**:
- test_retry_decorator_retries_on_transient_failure
- test_retry_stops_on_success_without_extra_retries
- test_retry_on_timeout_error
- (and 4 more)

**Diagnostics**:
```bash
# Check retry module
python -c "from backend.app.core.retry import retry, RetryExhaustedError; print('✓ Import OK')" 2>&1

# Run specific test with verbose output
pytest tests/test_pr_017_018_integration.py::test_retry_decorator_retries_on_transient_failure -vv 2>&1 | tail -50

# Check if pytest-asyncio is configured correctly
grep -i "asyncio" pyproject.toml backend/pytest.ini
```

---

## Summary of Fixes Needed

| Model | Issue | Fix | Priority |
|-------|-------|-----|----------|
| OpenPosition | Constructor fails | Check schema match | 🔴 CRITICAL |
| SymbolPrice | Constructor fails | Add Decimal types | 🔴 CRITICAL |
| OHLCCandle | Constructor fails | Add Decimal types | 🔴 CRITICAL |
| Trade | Constructor fails | Check schema match | 🔴 CRITICAL |
| RateLimiter | Import/fixture error | Check dependencies | 🟠 HIGH |
| PollService | Import/fixture error | Check dependencies | 🟠 HIGH |
| RetryDecorator | Async event loop | Check pytest-asyncio | 🟠 HIGH |

---

## Next Command to Run

```bash
cd c:\Users\FCumm\NewTeleBotFinal\backend

# 1. Run diagnostics script (once created)
python ../scripts/diagnose_models.py

# 2. Test individual failing models
python -m pytest tests/integration/test_position_monitor.py::test_buy_position_sl_breach -vv

# 3. Check all model instantiations
python -c "
from backend.app.data_pipeline.models import OpenPosition, SymbolPrice, OHLCCandle
from backend.app.trading.models import Trade
from datetime import datetime, timezone
from decimal import Decimal

# Test each model
try:
    print('Testing OpenPosition...')
    op = OpenPosition(approval_id='a', device_id='b', entry_price=2655.0, execution_id='c', id='d', instrument='XAUUSD', owner_sl=2645.0, owner_tp=2670.0, side=0, signal_id='e')
    print('  ✓ OK')
except Exception as e:
    print(f'  ✗ {e}')

try:
    print('Testing SymbolPrice...')
    sp = SymbolPrice(ask=Decimal('1950.75'), bid=Decimal('1950.5'), id='id', symbol='GOLD', timestamp=datetime.now(timezone.utc))
    print('  ✓ OK')
except Exception as e:
    print(f'  ✗ {e}')

try:
    print('Testing OHLCCandle...')
    oc = OHLCCandle(close=Decimal('1.0865'), high=Decimal('1.0875'), id='id', low=Decimal('1.084'), open=Decimal('1.085'), symbol='EURUSD', time_open=datetime.now(timezone.utc), volume=1000000)
    print('  ✓ OK')
except Exception as e:
    print(f'  ✗ {e}')
"
```
