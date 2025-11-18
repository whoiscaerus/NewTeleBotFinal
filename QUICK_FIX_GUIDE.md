# 🎯 Quick Fix Guide - Model Schema Mismatches

**Goal**: Fix 70 test failures in ~2 hours
**Status**: Ready to debug
**Last Updated**: 2025-11-18

---

## 📍 Where Are The Models?

### Data Pipeline Models
**File**: `backend/app/data_pipeline/models.py`

**Models with Test Failures**:
1. ✗ `OpenPosition` - 6 test failures
2. ✗ `SymbolPrice` - 5+ test failures
3. ✗ `OHLCCandle` - 5+ test failures
4. ? `DataPullLog` - Possibly 2 failures
5. ? `ReconciliationLog` - Possibly 2 failures

### Trading Models
**File**: `backend/app/trading/models.py` (or similar)

**Models with Test Failures**:
1. ✗ `Trade` - 21 test failures
2. ? `Position` - Part of Trade failures

---

## 🔍 How to Find & Check Models

### Step 1: Locate the model file
```bash
find backend/app -name "models.py" -type f | sort
# Output will show:
# backend/app/data_pipeline/models.py
# backend/app/trading/models.py
# ... (other modules)
```

### Step 2: Check model definition
```bash
# For OpenPosition
grep -A 30 "class OpenPosition" backend/app/data_pipeline/models.py

# For SymbolPrice
grep -A 20 "class SymbolPrice" backend/app/data_pipeline/models.py

# For Trade
grep -A 40 "class Trade" backend/app/trading/models.py
```

### Step 3: Compare test usage vs model definition
```bash
# See how test uses model
grep -B 5 -A 10 "OpenPosition(" backend/tests/integration/test_position_monitor.py | head -20
```

---

## 🐛 Common Issues & Fixes

### Issue #1: Numeric Fields Need `Decimal` Type

**Symptom**:
```
TypeError: Unable to coerce value to Decimal instance
```

**Fix**:
```python
# Test BEFORE (wrong)
price = SymbolPrice(ask=1950.75, bid=1950.5, ...)

# Test AFTER (correct)
from decimal import Decimal
price = SymbolPrice(ask=Decimal('1950.75'), bid=Decimal('1950.5'), ...)
```

**Models Affected**:
- `SymbolPrice.ask`, `SymbolPrice.bid`
- `OHLCCandle.open`, `.high`, `.low`, `.close`
- `Trade.entry_price`, `Trade.exit_price`, `Trade.pnl`

**How to Fix Tests**:
```python
# In test file, add at top
from decimal import Decimal
from datetime import datetime, timezone

# Then in test
price = SymbolPrice(
    ask=Decimal('1950.75'),
    bid=Decimal('1950.5'),
    id='test',
    symbol='GOLD',
    timestamp=datetime.now(timezone.utc)
)
```

---

### Issue #2: DateTime Fields Must Be Timezone-Aware

**Symptom**:
```
ValueError: 'timestamp' must be timezone-aware
```

**Fix**:
```python
# BEFORE (wrong - naive datetime)
from datetime import datetime
timestamp=datetime(2025, 11, 17, 20, 5, 54)

# AFTER (correct - timezone-aware)
from datetime import datetime, timezone
timestamp=datetime(2025, 11, 17, 20, 5, 54, tzinfo=timezone.utc)

# OR (simpler)
timestamp=datetime.now(timezone.utc)
```

**Models Affected**:
- `SymbolPrice.timestamp`
- `OHLCCandle.time_open`
- `Trade.opened_at`, `Trade.closed_at`
- Any `*_at` fields

**How to Fix Tests**:
```python
# In test file, add at top
from datetime import datetime, timezone

# Then in test
timestamp=datetime.now(timezone.utc)
```

---

### Issue #3: Enum/Choice Fields Use Wrong Value Type

**Symptom**:
```
ValueError: 'BUY' is not a valid side. Valid values: [0, 1]
```

**Fix**:
```python
# BEFORE (wrong - using string)
trade = Trade(side='BUY', ...)

# AFTER (correct - using int)
trade = Trade(side=0, ...)  # 0=BUY, 1=SELL
```

**Models Affected**:
- `OpenPosition.side` (0=BUY, 1=SELL)
- `Trade.side` (0=BUY, 1=SELL)
- Any status/enum fields

**Check model to verify**:
```bash
grep -A 5 "side.*Column" backend/app/data_pipeline/models.py
```

---

### Issue #4: Required Fields Missing from Constructor

**Symptom**:
```
TypeError: __init__() missing required positional argument: 'status'
```

**Fix**:
```python
# BEFORE (incomplete)
position = OpenPosition(
    approval_id='...',
    device_id='...',
    entry_price=2655.0,
    # Missing other required fields
)

# AFTER (complete)
position = OpenPosition(
    approval_id='...',
    device_id='...',
    entry_price=2655.0,
    execution_id='...',  # Added
    id='...',            # Added
    instrument='XAUUSD', # Added
    owner_sl=2645.0,
    owner_tp=2670.0,
    side=0,
    signal_id='...',     # Added
    status='open',       # Added if required
    # ... etc
)
```

**How to Find Required Fields**:
```bash
python -c "from backend.app.data_pipeline.models import OpenPosition; import inspect; print(inspect.signature(OpenPosition.__init__))"
```

---

## 🛠️ Step-by-Step Fix Process

### Fix Step 1: Identify the Issue
```bash
cd backend

# Run ONE failing test with full output
python -m pytest tests/integration/test_position_monitor.py::test_buy_position_sl_breach -vvv 2>&1 | tail -100
```

### Fix Step 2: Examine the Model Definition
```bash
# Look at actual model
vi backend/app/data_pipeline/models.py
# Search for: class OpenPosition
# Note all Column() definitions
```

### Fix Step 3: Update Test Fixture
```bash
# Open test file
vi backend/tests/integration/test_position_monitor.py
# Line 26: Update OpenPosition(...) constructor call
# Match all fields from model definition
```

### Fix Step 4: Verify Fix
```bash
# Run test again
python -m pytest tests/integration/test_position_monitor.py::test_buy_position_sl_breach -v
```

### Fix Step 5: Apply to Similar Tests
```bash
# If test above passes, apply same fix to other 5 tests in that file
python -m pytest tests/integration/test_position_monitor.py -v
```

---

## 📋 Test Groups & Fixes Needed

### Group 1: Position Tests (6 failures)
**File**: `backend/tests/integration/test_position_monitor.py`
**Model**: `OpenPosition` in `backend/app/data_pipeline/models.py`
**Issue**: Likely missing fields or wrong field types

```bash
# Test
python -m pytest backend/tests/integration/test_position_monitor.py -v

# Expected after fix: 6 PASS ✓
```

### Group 2: Data Pipeline Tests (17 failures)
**File**: `backend/tests/test_data_pipeline.py`
**Models**: `SymbolPrice`, `OHLCCandle`, `DataPullLog`, `ReconciliationLog`
**Issue**: Numeric fields need `Decimal`, datetime fields need timezone

```bash
# Quick fix:
# 1. Add to test file:
from decimal import Decimal
from datetime import datetime, timezone

# 2. Update SymbolPrice(...) calls to use Decimal and timezone-aware datetime
# 3. Same for OHLCCandle, etc.

# Test
python -m pytest backend/tests/test_data_pipeline.py -v

# Expected after fix: 17 PASS ✓
```

### Group 3: Trade Store Tests (21 failures)
**File**: `backend/tests/test_pr_016_trade_store.py`
**Model**: `Trade` in `backend/app/trading/models.py`
**Issue**: Schema mismatch in Trade model

```bash
# Identify required Trade fields first
python -c "from backend.app.trading.models import Trade; print(Trade.__table__.columns.keys())"

# Update all Trade(...) constructors in test file
# Apply Decimal and timezone fixes

# Test
python -m pytest backend/tests/test_pr_016_trade_store.py -v

# Expected after fix: 21 PASS ✓
```

### Group 4: Rate Limit Tests (11 failures)
**File**: `backend/tests/test_pr_005_ratelimit.py`
**Issue**: Likely import or fixture initialization

```bash
# First check import
python -c "from backend.app.core.ratelimit import RateLimiter; print('✓')" 2>&1

# Then run test to see actual error
python -m pytest backend/tests/test_pr_005_ratelimit.py::test_tokens_consumed_on_request -vvv 2>&1 | tail -50

# Fix based on error message
# Then test
python -m pytest backend/tests/test_pr_005_ratelimit.py -v

# Expected after fix: 11 PASS ✓
```

### Group 5: Poll Tests (7 failures)
**File**: `backend/tests/test_poll_v2.py`
**Issue**: Similar to rate limit - fixture or import issue

```bash
# Check import
python -c "from backend.app.polling.service import PollService; print('✓')" 2>&1

# Run test
python -m pytest backend/tests/test_poll_v2.py::test_record_poll_no_approvals -vvv 2>&1 | tail -50

# Fix and verify
python -m pytest backend/tests/test_poll_v2.py -v
```

### Group 6: Retry/Integration Tests (7 failures)
**File**: `backend/tests/test_pr_017_018_integration.py`
**Issue**: Async event loop or mock issues

```bash
# Run specific test
python -m pytest backend/tests/test_pr_017_018_integration.py::test_retry_decorator_retries_on_transient_failure -vvv 2>&1 | tail -50

# Fix based on error
# Likely needs: @pytest.mark.asyncio on async tests
# Or: proper async mock setup

python -m pytest backend/tests/test_pr_017_018_integration.py -v
```

---

## 💡 Universal Fix Template

For **every model-based test failure**, apply this template:

```python
# BEFORE (failing test)
def test_something():
    model = SomeModel(
        field1=value1,
        field2=value2,
    )
    assert model.field1 == value1

# AFTER (fixed test)
from decimal import Decimal
from datetime import datetime, timezone

def test_something():
    model = SomeModel(
        field1=Decimal('value1') if numeric else value1,  # Fix numeric
        field2=datetime.now(timezone.utc) if datetime_field else value2,  # Fix datetime
        # Add any missing required fields
        # Use enum values (int) not string names
    )
    assert model.field1 == Decimal('value1') if numeric else value1
```

---

## ✅ Verification Checklist

After each fix, verify:

- [ ] Individual test passes: `python -m pytest tests/test_file.py::test_name -v`
- [ ] All tests in module pass: `python -m pytest tests/test_file.py -v`
- [ ] No import errors: `python -c "from backend.app.module import Model; print('✓')"`
- [ ] Model instantiation works: `python -c "from backend.app.module import Model; m = Model(...); print(m)"`
- [ ] Field values correct: `python -c "from backend.app.module import Model; m = Model(...); print(m.field)"`

---

## 🚀 Expected Timeline

| Fix Group | Models | Tests | Time | Expected Result |
|-----------|--------|-------|------|-----------------|
| 1 | OpenPosition | 6 | 15 min | ✓ PASS |
| 2 | SymbolPrice, OHLCCandle | 17 | 20 min | ✓ PASS |
| 3 | Trade | 21 | 25 min | ✓ PASS |
| 4 | RateLimiter | 11 | 15 min | ✓ PASS |
| 5 | Poll | 7 | 10 min | ✓ PASS |
| 6 | Retry | 7 | 10 min | ✓ PASS |
| **TOTAL** | **6** | **69** | **~95 min** | **95%+ pass rate** |

---

## 🎯 Next Action

1. **RIGHT NOW**: Run diagnostic command
```bash
cd backend
python -m pytest tests/integration/test_position_monitor.py::test_buy_position_sl_breach -vvv 2>&1 | tail -80
```

2. **GET FULL ERROR**: Copy the last 80 lines and analyze

3. **IDENTIFY PATTERN**: Does it match Issue #1, #2, #3, or #4?

4. **APPLY FIX**: Use template above

5. **VERIFY**: Run test again

**You should have full fix within 2 hours.**
