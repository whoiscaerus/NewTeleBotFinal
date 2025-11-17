# ⚡ Quick Testing Reference Guide

**Goal**: Run specific tests quickly (< 5 min) instead of full suite (1+ hour)

## 🚀 Quick Commands

### Run ALL tests (use when ready for final validation)
```bash
.\.venv\Scripts\python.exe -m pytest backend/tests -v
```
**Time**: ~1 hour | **Tests**: 6,400+

### Run FOCUSED suite (skip slow tests)
```bash
.\.venv\Scripts\python.exe -m pytest backend/tests -c pytest-focused.ini -v
```
**Time**: ~5-10 min | **Tests**: ~2,000 (fastest tests only)

---

## 📋 Test by Category

### Data Pipeline Tests (fixes schema errors)
```bash
.\.venv\Scripts\python.exe -m pytest backend/tests/test_data_pipeline.py -v --tb=short
```
**Time**: 1-2 min | **Tests**: 66

### Position Monitor Tests (fixes OpenPosition model)
```bash
.\.venv\Scripts\python.exe -m pytest backend/tests/integration/test_position_monitor.py -v --tb=short
```
**Time**: 15 sec | **Tests**: 9

### Trade Store Tests (fixes Trade/Position/EquityPoint models)
```bash
.\.venv\Scripts\python.exe -m pytest backend/tests/test_pr_016_trade_store.py -v --tb=short
```
**Time**: 1-2 min | **Tests**: 34

### Decision Logs Tests
```bash
.\.venv\Scripts\python.exe -m pytest backend/tests/test_decision_logs.py -v --tb=short
```
**Time**: 30 sec | **Tests**: ~20

### Rate Limit Tests
```bash
.\.venv\Scripts\python.exe -m pytest backend/tests/test_pr_005_ratelimit.py -v --tb=short
```
**Time**: 2 min | **Tests**: 11+

### Poll Tests
```bash
.\.venv\Scripts\python.exe -m pytest backend/tests/test_poll_v2.py -v --tb=short
```
**Time**: 1 min | **Tests**: 7+

### Integration Tests
```bash
.\.venv\Scripts\python.exe -m pytest backend/tests/test_pr_017_018_integration.py -v --tb=short
```
**Time**: 30 sec | **Tests**: 7+

---

## 🎯 Run Tests by Feature

### Schema-Related (70 tests, 2-3 min)
```bash
.\.venv\Scripts\python.exe -m pytest \
  backend/tests/test_data_pipeline.py \
  backend/tests/integration/test_position_monitor.py \
  backend/tests/test_pr_016_trade_store.py \
  backend/tests/test_decision_logs.py \
  -v --tb=short
```

### API Routes (test each file)
```bash
.\.venv\Scripts\python.exe -m pytest backend/tests/test_*_routes.py -v --tb=short -m route
```
**Time**: 5-10 min | **Tests**: ~500

### Integration (business logic)
```bash
.\.venv\Scripts\python.exe -m pytest backend/tests/integration/ -v --tb=short
```
**Time**: 3-5 min | **Tests**: ~100

---

## 📊 With Coverage Report

### Schema tests with coverage
```bash
.\.venv\Scripts\python.exe -m pytest \
  backend/tests/test_data_pipeline.py \
  backend/tests/integration/test_position_monitor.py \
  backend/tests/test_pr_016_trade_store.py \
  --cov=backend/app/trading/data \
  --cov=backend/app/trading/positions \
  --cov=backend/app/trading/store \
  --cov-report=term-missing \
  -v
```

### Full coverage (takes longer)
```bash
.\.venv\Scripts\python.exe -m pytest backend/tests \
  --cov=backend/app \
  --cov-report=html \
  --cov-report=term-missing \
  -v
```

---

## 🔍 Run Specific Test

### Single test
```bash
.\.venv\Scripts\python.exe -m pytest \
  backend/tests/test_data_pipeline.py::TestSymbolPriceModel::test_symbol_price_creation \
  -xvs
```

### Multiple specific tests
```bash
.\.venv\Scripts\python.exe -m pytest \
  backend/tests/test_data_pipeline.py::TestSymbolPriceModel::test_symbol_price_creation \
  backend/tests/test_data_pipeline.py::TestSymbolPriceModel::test_symbol_price_repr \
  -xvs
```

### Tests matching pattern
```bash
.\.venv\Scripts\python.exe -m pytest backend/tests -k "symbol_price" -v
```

---

## 🚀 Smart Test Strategy by Phase

### PHASE 1: Quick Validation (2 min)
When making a fix, run just the affected test:
```bash
.\.venv\Scripts\python.exe test_quick.py <module_name>
```

### PHASE 2: Related Tests (5-10 min)
Make sure you didn't break related functionality:
```bash
.\.venv\Scripts\python.exe -m pytest backend/tests/<module>/ -v
```

### PHASE 3: Full Suite (1 hour)
Before committing, run everything:
```bash
.\.venv\Scripts\python.exe -m pytest backend/tests -v --tb=short
```

### PHASE 4: Coverage Check (optional)
Ensure coverage targets met:
```bash
.\.venv\Scripts\python.exe -m pytest backend/tests \
  --cov=backend/app \
  --cov-report=term-missing:skip-covered
```

---

## 📌 Flags Reference

| Flag | Purpose |
|------|---------|
| `-v` | Verbose output |
| `-vv` | More verbose (show all details) |
| `-x` | Stop on first failure |
| `-k "pattern"` | Run tests matching pattern |
| `-m marker` | Run tests with marker (e.g., `integration`) |
| `--tb=short` | Short traceback format |
| `--tb=line` | One-liner traceback |
| `--cov=module` | Coverage for module |
| `--cov-report=html` | Generate HTML coverage report |
| `--maxfail=N` | Stop after N failures |
| `--durations=N` | Show N slowest tests |

---

## ⚙️ Environment Variables

Set before running tests:
```bash
$env:CI = "true"                    # Run in CI mode
$env:APP_ENV = "test"              # Test environment
$env:DATABASE_URL = "..."          # Override DB URL
$env:REDIS_URL = "redis://..."     # Override Redis URL
```

Example:
```bash
$env:CI = "true"; .\.venv\Scripts\python.exe -m pytest backend/tests/test_data_pipeline.py -v
```

---

## 💡 Pro Tips

1. **Run data pipeline tests first** - they're the foundation (2 min)
2. **Then run integration tests** - they catch cross-module issues (5 min)
3. **Finally run full suite** - only when confident (60 min)

2. **Use `-x` flag** to stop on first failure and debug faster:
   ```bash
   .\.venv\Scripts\python.exe -m pytest backend/tests/test_data_pipeline.py -xvs
   ```

3. **Check what changed** before deciding which tests to run:
   ```bash
   git diff --name-only HEAD~1
   ```
   If `backend/app/trading/data/` changed → run `test_data_pipeline.py`

4. **Mark tests as slow**:
   ```python
   @pytest.mark.slow
   def test_very_slow_operation():
       ...
   ```
   Then skip slow tests:
   ```bash
   .\.venv\Scripts\python.exe -m pytest backend/tests -m "not slow"
   ```

---

## 🐛 Common Issues & Fixes

### Issue: Import errors in conftest
**Fix**: Clear pytest cache
```bash
Remove-Item -Path backend/.pytest_cache -Recurse -Force
```

### Issue: Tests hanging/timing out
**Fix**: Use `-x` flag to stop on first timeout:
```bash
.\.venv\Scripts\python.exe -m pytest backend/tests -x --tb=short
```

### Issue: Database errors
**Fix**: Make sure PostgreSQL and Redis are not running:
```bash
docker-compose down
```
Tests use in-memory SQLite instead.

---

**Last Updated**: 2025-11-17
**Target**: ✅ 95% coverage (6,000+ tests, all passing)
