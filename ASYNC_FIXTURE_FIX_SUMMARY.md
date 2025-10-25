# Async Fixture Fix Summary

## Issue Fixed
The `mock_market_calendar_async` fixture had incorrect initialization that caused async test failures.

## Root Cause
```python
# ❌ WRONG - Using MagicMock instead of AsyncMock
@pytest.fixture
def mock_market_calendar_async():
    calendar = MagicMock()  # Wrong: This creates sync mock
    calendar.is_market_open = AsyncMock(return_value=True)
    return calendar
```

The fixture was creating a sync `MagicMock` as the base object, then trying to attach an `AsyncMock` to it. This caused type mismatches and warnings.

## Solution Applied
```python
# ✅ CORRECT - Using AsyncMock directly
@pytest.fixture
def mock_market_calendar_async():
    calendar = AsyncMock()  # Correct: Creates async mock
    calendar.is_market_open = AsyncMock(return_value=True)
    return calendar
```

Changed the base object to `AsyncMock()` to properly support async operations.

## Files Modified
- `backend/tests/test_fib_rsi_strategy.py` (Line 50)

## Test Results
✅ **All 16 async tests in TestStrategyEngine now pass**
- `test_engine_initialization` - PASSED
- `test_generate_signal_with_valid_data` - PASSED
- `test_generate_signal_invalid_dataframe` - PASSED
- `test_generate_signal_insufficient_data` - PASSED
- `test_generate_signal_market_closed` - PASSED
- `test_validate_dataframe_missing_columns` - PASSED
- `test_validate_dataframe_with_nan` - PASSED
- `test_generate_buy_signal_with_indicators` - PASSED
- `test_generate_sell_signal_with_indicators` - PASSED
- `test_signal_entry_sl_tp_relationship_buy` - PASSED
- `test_signal_entry_sl_tp_relationship_sell` - PASSED
- `test_rate_limit_resets_over_time` - PASSED
- `test_signal_timestamp_set` - PASSED
- `test_signal_rr_ratio_configuration` - PASSED
- `test_engine_with_different_instruments` - PASSED
- `test_engine_confidence_varies_with_indicators` - PASSED

## Verification Commands
```bash
# Verify fixture collects correctly
.venv/Scripts/python.exe -m pytest backend/tests/test_fib_rsi_strategy.py --collect-only

# Run async tests
.venv/Scripts/python.exe -m pytest backend/tests/test_fib_rsi_strategy.py::TestStrategyEngine -v

# Run full test suite
.venv/Scripts/python.exe -m pytest backend/tests/test_fib_rsi_strategy.py -v
```

## Implementation Notes
- `AsyncMock()` is from `unittest.mock` and properly handles async/await patterns
- This fixture is used by all 16 async test methods in TestStrategyEngine class
- The change is backward compatible and doesn't affect any other fixtures
- Pre-existing test failures (4 in TestStrategyParams) are unrelated to this fix

## Key Learning
**Always use `AsyncMock()` for base objects in async fixtures, not `MagicMock()`.**

When you need async behavior:
- ❌ `calendar = MagicMock()` + `AsyncMock(return_value=...)` = Mismatch
- ✅ `calendar = AsyncMock()` + methods assigned = Correct async behavior
