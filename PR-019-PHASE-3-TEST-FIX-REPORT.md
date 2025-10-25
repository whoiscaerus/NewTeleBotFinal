# PR-019 Phase 3 - Test Fixture Mismatch Report

## Issue Identified

**Test Execution Results**: 29 FAILED, 6 PASSED, 43 ERRORS (out of 78 tests)

**Root Cause**: Test fixtures and test code were written with incorrect assumptions about production code signatures.

### Production Code vs Test Expectations

#### TradingLoop Constructor

**Actual Production Code**:
```python
def __init__(
    self,
    mt5_client: Any,
    approvals_service: Any,
    order_service: Any,
    alert_service: Optional[Any] = None,
    retry_decorator: Optional[Any] = None,
    db_session: Optional[AsyncSession] = None,
    logger: Optional[logging.Logger] = None,
    loop_id: str = "trading_loop_main",
) -> None:
```

**What Tests Expected**:
```python
TradingLoop(
    account_id="test_account",
    drawdown_cap_percent=20.0,
    ...
)
```

**Issue**: Tests use `account_id` parameter which doesn't exist in production code. Production code requires `mt5_client`, `approvals_service`, `order_service` instead.

#### HeartbeatMetrics Dataclass

**Actual Production Code**:
```python
@dataclass
class HeartbeatMetrics:
    timestamp: datetime
    loop_id: str
    signals_processed: int
    trades_executed: int
    error_count: int
    loop_duration_ms: float
    positions_open: int
    account_equity: float
    total_signals_lifetime: int
    total_trades_lifetime: int
```

**What Tests Expected**:
```python
HeartbeatMetrics(
    timestamp=datetime.now(),
    loop_id="test",
    signals_processed=0,
    trades_executed=0,
    error_count=0,
    loop_duration_ms=100.0,
    positions_open=0
)
# Missing account_equity, total_signals_lifetime, total_trades_lifetime
```

**Issue**: Tests missing required parameters (account_equity, total_signals_lifetime, total_trades_lifetime).

#### DrawdownGuard Methods

**Actual Production Code**:
```python
def __init__(
    self,
    max_drawdown_percent: float = 20.0,
    alert_service: Optional[Any] = None,
    logger: Optional[logging.Logger] = None,
) -> None:

async def check_and_enforce(
    self,
    mt5_client: Any,
    order_service: Any,
    force_check: bool = False,
) -> DrawdownState:
```

**What Tests Expected**:
```python
drawdown_guard.calculate_drawdown(current, initial)
drawdown_guard.should_close_positions(current, initial)
drawdown_guard.close_all_positions(mock_order_service)
```

**Issue**: Tests call methods that don't exist. The actual method is `check_and_enforce()` that returns DrawdownState. Internal calculation happens inside this method, not as separate callable methods.

## Test Mismatch Categories

### Category 1: TradingLoop Initialization (21 errors)
- **Problem**: Fixture tries to create TradingLoop with `account_id` parameter
- **Affected Tests**: 21 tests (all tests use this fixture)
- **Fix**: Update fixture to pass `mt5_client`, `approvals_service`, `order_service` with mock objects

### Category 2: HeartbeatMetrics Creation (2 failures)
- **Problem**: Missing 3 required parameters
- **Affected Tests**: 2 tests
- **Fix**: Add `account_equity`, `total_signals_lifetime`, `total_trades_lifetime` parameters

### Category 3: DrawdownGuard Missing Methods (19 failures)
- **Problem**: Tests call non-existent methods (`calculate_drawdown()`, `should_close_positions()`, `close_all_positions()`)
- **Affected Tests**: 19 tests
- **Fix**: Refactor tests to use actual `check_and_enforce()` method

## Test Execution Summary

```
Tests by Status:
├─ PASSED: 6 (7.7%)
├─ FAILED: 29 (37.2%)
│  ├─ HeartbeatMetrics missing params: 2
│  ├─ DrawdownGuard method mismatches: 19
│  └─ Other parameter issues: 8
└─ ERROR: 43 (55.1%)
   └─ TradingLoop fixture creation: 43

Total: 78 tests
Passing Rate: 7.7% (CRITICAL)
```

## Remediation Plan

### Step 1: Fix TradingLoop Fixture (1 fixture)
Update `/backend/tests/conftest.py` or fixture in test files:
```python
@pytest.fixture
def trading_loop():
    """Create TradingLoop with mocked dependencies."""
    mock_mt5 = AsyncMock()
    mock_mt5.get_account.return_value = {"equity": 10000.0, "balance": 10000.0}

    mock_approvals = AsyncMock()
    mock_approvals.get_pending.return_value = []

    mock_orders = AsyncMock()
    mock_orders.get_open_positions.return_value = []

    loop = TradingLoop(
        mt5_client=mock_mt5,
        approvals_service=mock_approvals,
        order_service=mock_orders,
        loop_id="test_loop"
    )
    return loop
```

### Step 2: Fix HeartbeatMetrics Tests (2 tests)
Add missing parameters:
```python
metrics = HeartbeatMetrics(
    timestamp=datetime.now(timezone.utc),
    loop_id="test",
    signals_processed=0,
    trades_executed=0,
    error_count=0,
    loop_duration_ms=100.0,
    positions_open=0,
    account_equity=10000.0,  # ADD
    total_signals_lifetime=0,  # ADD
    total_trades_lifetime=0,  # ADD
)
```

### Step 3: Fix DrawdownGuard Tests (19 tests)
Refactor to use `check_and_enforce()` instead of non-existent methods:
```python
# OLD: drawdown_guard.calculate_drawdown(current, initial)
# NEW: Call check_and_enforce() and check returned state
state = await drawdown_guard.check_and_enforce(mock_mt5, mock_orders)
assert state.drawdown_percent == expected_drawdown
```

## Test Files Requiring Fixes

1. **backend/tests/test_trading_loop.py** (550 lines)
   - Fixture: Update `trading_loop` fixture (lines ~40-50)
   - HeartbeatMetrics tests: Add 3 missing parameters (lines ~140-145)
   - Signal processing tests: May need adjustments

2. **backend/tests/test_drawdown_guard.py** (550 lines)
   - All DrawdownCalculation tests: Use `check_and_enforce()` instead
   - All ThresholdChecking tests: Use `check_and_enforce()` instead
   - All PositionClosing tests: Use `check_and_enforce()` instead
   - All AlertTriggering tests: Use `check_and_enforce()` instead
   - All RecoveryTracking tests: Use `check_and_enforce()` instead

3. **backend/tests/test_runtime_integration.py** (750 lines)
   - All tests using `trading_loop` fixture: Will be fixed by Step 1

## Estimated Fix Time

- Fix TradingLoop fixture: 20 minutes
- Fix HeartbeatMetrics tests: 5 minutes
- Fix DrawdownGuard tests: 45 minutes
- Re-run tests: 5 minutes
- **Total: 75 minutes (~1.25 hours)**

## Next Steps

1. Review and understand actual method signatures (DONE)
2. Update test fixtures to create proper mock objects
3. Refactor test methods to call correct production code methods
4. Re-run tests and achieve ≥80% coverage
5. Continue to Phase 4 verification

## Quality Gate Status

- ✅ Production code verified (1,271 lines)
- ❌ Test code verified (fixture mismatch identified)
- ❌ All tests passing (7.7% passing - critical failure)
- ❌ Coverage ≥80% (cannot measure due to test failures)
- ❌ Ready to merge (blocked by test failures)

**Blocker**: Cannot proceed to Phase 4 verification until all tests pass.

---

**Status**: 🔴 CRITICAL - Test fixtures must be rewritten to match production code signatures

**Priority**: HIGH - This must be completed before PR-019 can be merged

**Complexity**: MODERATE - Clear root cause, straightforward fixes, no production code changes needed
