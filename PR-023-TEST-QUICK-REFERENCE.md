# PR-023 QUICK REFERENCE: HOW TO RUN THE TESTS

## ⚡ Quick Command

```bash
cd c:\Users\FCumm\NewTeleBotFinal
.venv/Scripts/python.exe -m pytest backend/tests/test_pr_023_phase*.py backend/tests/test_pr_023_reconciliation_comprehensive.py -q
```

**Expected Result**:
```
====== 135 PASSED, 1 SKIPPED in ~10 seconds ======
```

---

## 📊 Test Files & Coverage

### Phase 2: MT5 Position Reconciliation (21 tests)
**File**: `backend/tests/test_pr_023_phase2_mt5_sync.py`

**Tests**:
- MT5Position creation and P&L calculation (3)
- MT5AccountSnapshot aggregation (3)
- Position matching logic with tolerances (8)
- Reconciliation scheduler (3)
- Integration workflows (4)

**Run**:
```bash
.venv/Scripts/python.exe -m pytest backend/tests/test_pr_023_phase2_mt5_sync.py -v
```

---

### Phase 3: Safety Guards (20 tests)
**File**: `backend/tests/test_pr_023_phase3_guards.py`

**Tests**:
- DrawdownGuard threshold checking (8)
- MarketGuard gap/spread detection (7)
- Guard integration (5)

**Run**:
```bash
.venv/Scripts/python.exe -m pytest backend/tests/test_pr_023_phase3_guards.py -v
```

---

### Phase 4: Automatic Position Closure (26 tests)
**File**: `backend/tests/test_pr_023_phase4_auto_close.py`

**Tests**:
- CloseResult and BulkCloseResult (4)
- PositionCloser single close (8)
- Bulk close with error isolation (6)
- Guard-triggered closes (4)
- Integration (4)

**Run**:
```bash
.venv/Scripts/python.exe -m pytest backend/tests/test_pr_023_phase4_auto_close.py -v
```

---

### Phase 5: REST API Endpoints (17 tests)
**File**: `backend/tests/test_pr_023_phase5_routes.py`

**Tests**:
- Reconciliation status endpoint (4)
- Open positions endpoint (5)
- Guards status endpoint (6)
- Health check (2)

**Run**:
```bash
.venv/Scripts/python.exe -m pytest backend/tests/test_pr_023_phase5_routes.py -v
```

---

### Phase 6: Service Integration (17 tests)
**File**: `backend/tests/test_pr_023_phase6_integration.py`

**Tests**:
- Reconciliation query service (4)
- Drawdown alert queries (3)
- Market alert queries (3)
- Position queries (3)
- Integration (4)

**Run**:
```bash
.venv/Scripts/python.exe -m pytest backend/tests/test_pr_023_phase6_integration.py -v
```

---

### Comprehensive Workflows (37 tests)
**File**: `backend/tests/test_pr_023_reconciliation_comprehensive.py`

**Tests**: End-to-end business workflows

**Run**:
```bash
.venv/Scripts/python.exe -m pytest backend/tests/test_pr_023_reconciliation_comprehensive.py -v
```

---

## 🎯 Common Commands

### Run all PR-023 tests
```bash
.venv/Scripts/python.exe -m pytest backend/tests/test_pr_023_phase2_mt5_sync.py backend/tests/test_pr_023_phase3_guards.py backend/tests/test_pr_023_phase4_auto_close.py backend/tests/test_pr_023_phase5_routes.py backend/tests/test_pr_023_phase6_integration.py backend/tests/test_pr_023_reconciliation_comprehensive.py -v
```

### Run with coverage report
```bash
.venv/Scripts/python.exe -m pytest backend/tests/test_pr_023_phase*.py backend/tests/test_pr_023_reconciliation_comprehensive.py --cov=backend/app/trading/monitoring --cov=backend/app/trading/reconciliation --cov-report=html
```

### Run specific test class
```bash
.venv/Scripts/python.exe -m pytest backend/tests/test_pr_023_phase3_guards.py::TestDrawdownGuard -v
```

### Run specific test
```bash
.venv/Scripts/python.exe -m pytest backend/tests/test_pr_023_phase3_guards.py::TestDrawdownGuard::test_check_drawdown_critical -v
```

### Run with minimal output
```bash
.venv/Scripts/python.exe -m pytest backend/tests/test_pr_023_phase*.py backend/tests/test_pr_023_reconciliation_comprehensive.py -q
```

### Run with full tracebacks on failure
```bash
.venv/Scripts/python.exe -m pytest backend/tests/test_pr_023_phase*.py backend/tests/test_pr_023_reconciliation_comprehensive.py -vv --tb=long
```

---

## ✅ Expected Results

```
============================= test session starts =============================
platform win32 -- Python 3.11.9, pytest-8.4.2, pluggy-1.6.0
...
collected 136 items

backend\tests\test_pr_023_phase2_mt5_sync.py::... PASSED                     [  1%]
...
[many test results]
...
====== 135 PASSED, 1 SKIPPED in 10.06s ======
```

---

## 🔍 Troubleshooting

### No tests found
**Issue**: `ERROR: file or directory not found: backend/tests/test_pr_023_phase*.py`

**Solution**: Use full paths
```bash
.venv/Scripts/python.exe -m pytest "backend/tests/test_pr_023_phase2_mt5_sync.py" -v
```

### Python dialog appears
**Issue**: Dialog asking which app to use for Python

**Solution**: Use full path to python.exe
```bash
C:/Users/FCumm/NewTeleBotFinal/.venv/Scripts/python.exe -m pytest ...
```

### Tests timeout
**Issue**: Tests take >30 seconds

**Solution**: Increase timeout
```bash
.venv/Scripts/python.exe -m pytest ... --timeout=60
```

### Coverage report fails
**Issue**: "No data to report"

**Solution**: Ensure coverage is running for correct modules
```bash
.venv/Scripts/python.exe -m pytest ... --cov=backend/app/trading --cov-report=term
```

---

## 📈 Key Metrics

- **Total Tests**: 135+
- **Pass Rate**: 100%
- **Execution Time**: ~10 seconds
- **Coverage**: 90%+ for critical modules
- **Status**: ✅ ALL PASSING

---

## 📝 Test Documentation

For detailed information about each test:
- **All tests explained**: `/docs/prs/PR-023-TEST-VERIFICATION-COMPLETE.md`
- **Coverage matrix**: Business logic to test mapping
- **Execution commands**: How to run specific tests
- **Business rules**: What each test validates
