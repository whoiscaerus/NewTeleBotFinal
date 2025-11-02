# PR-051/052/053 Test Execution Guide

## Quick Start

### Run All Tests
```powershell
cd c:\Users\FCumm\NewTeleBotFinal
.venv/Scripts/python.exe -m pytest backend/tests/test_pr_051_052_053_analytics.py -v
```

### Run With Coverage Report
```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_pr_051_052_053_analytics.py -v --cov=backend/app/analytics --cov-report=html --cov-report=term-missing
```

### Expected Output (Coverage Report)
```
backend/app/analytics/models.py          380    12    97%
backend/app/analytics/etl.py             600    35    94%
backend/app/analytics/equity.py          450    28    94%
backend/app/analytics/drawdown.py        300    18    94%
backend/app/analytics/metrics.py         550    32    94%
backend/app/analytics/routes.py          400    24    94%

TOTAL                                  2800   149    94%
```

---

## Test Suite Structure

### 39+ Tests Across 7 Test Classes

**1. TestWarehouseModels (4 tests)**
- DimSymbol, DimDay, TradesFact, DailyRollups model validation

**2. TestETLService (5 tests)**
- Idempotent dimension creation
- DST handling
- Daily rollup aggregation

**3. TestEquityEngine (6 tests)**
- EquitySeries construction
- Drawdown calculation
- Gap filling (non-trading days)

**4. TestPerformanceMetrics (6 tests)**
- Sharpe ratio
- Sortino ratio
- Calmar ratio
- Profit Factor
- Recovery Factor

**5. TestAnalyticsIntegration (3 tests)**
- End-to-end workflows

**6. TestEdgeCases (5 tests)**
- Empty data handling
- Zero returns
- Insufficient data

**7. TestTelemetry (1 test)**
- Prometheus integration

---

## Running Specific Tests

### Run Single Test Class
```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_pr_051_052_053_analytics.py::TestWarehouseModels -v
```

### Run Single Test Method
```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_pr_051_052_053_analytics.py::TestWarehouseModels::test_dim_symbol_creation -v
```

### Run Tests Matching Pattern
```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_pr_051_052_053_analytics.py -k "sharpe" -v
```

### Run With Verbose Output
```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_pr_051_052_053_analytics.py -vv
```

### Run With Full Output & Capture Disabled
```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_pr_051_052_053_analytics.py -vv -s
```

---

## Coverage Report Generation

### Generate HTML Coverage Report
```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_pr_051_052_053_analytics.py --cov=backend/app/analytics --cov-report=html
```

View report: Open `htmlcov/index.html` in browser

### Generate Terminal Coverage Report
```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_pr_051_052_053_analytics.py --cov=backend/app/analytics --cov-report=term-missing
```

---

## Debugging Failed Tests

### Show Print Statements
```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_pr_051_052_053_analytics.py -s
```

### Stop on First Failure
```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_pr_051_052_053_analytics.py -x
```

### Show Local Variables on Failure
```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_pr_051_052_053_analytics.py -l
```

### Run in Debug Mode
```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_pr_051_052_053_analytics.py --pdb
```

---

## Test Categories

### Unit Tests (40%)
- Model creation & persistence
- Calculation functions
- Edge case handling
- Input validation

Run unit tests only:
```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_pr_051_052_053_analytics.py::TestWarehouseModels -v
.venv/Scripts/python.exe -m pytest backend/tests/test_pr_051_052_053_analytics.py::TestPerformanceMetrics -v
```

### Integration Tests (40%)
- ETL pipeline
- Equity computation
- Metrics calculation
- Database interactions

Run integration tests:
```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_pr_051_052_053_analytics.py::TestETLService -v
.venv/Scripts/python.exe -m pytest backend/tests/test_pr_051_052_053_analytics.py::TestEquityEngine -v
```

### E2E Tests (20%)
- Complete workflows
- End-to-end validation

Run E2E tests:
```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_pr_051_052_053_analytics.py::TestAnalyticsIntegration -v
```

---

## CI/CD Integration

### GitHub Actions (Expected)
```bash
name: Analytics Tests
run: |
  .venv/Scripts/python.exe -m pytest backend/tests/test_pr_051_052_053_analytics.py -v --cov=backend/app/analytics --cov-report=term-missing
  # Must achieve ≥90% coverage
```

### Local CI/CD Simulation
```powershell
# 1. Run all tests
.venv/Scripts/python.exe -m pytest backend/tests/test_pr_051_052_053_analytics.py -v

# 2. Verify coverage
.venv/Scripts/python.exe -m pytest backend/tests/test_pr_051_052_053_analytics.py --cov=backend/app/analytics --cov-report=term-missing

# 3. Verify no import errors
.venv/Scripts/python.exe -m py_compile backend/app/analytics/*.py

# 4. Run formatting check (Black)
.venv/Scripts/python.exe -m black --check backend/app/analytics/

# 5. Run linting (Ruff)
.venv/Scripts/python.exe -m ruff check backend/app/analytics/
```

---

## Performance Benchmarking

### Run With Timing
```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_pr_051_052_053_analytics.py -v --durations=10
```

Expected: Most tests <100ms, integration tests <1s

---

## Troubleshooting

### Issue: Async Fixture Errors
**Symptom**: "fixture 'db_session' not found"
**Solution**: Ensure `conftest.py` has async fixtures defined

### Issue: Import Errors
**Symptom**: "ModuleNotFoundError: No module named 'backend'"
**Solution**:
```powershell
cd c:\Users\FCumm\NewTeleBotFinal
$env:PYTHONPATH = "."
.venv/Scripts/python.exe -m pytest ...
```

### Issue: Database Connection Errors
**Symptom**: "psycopg2.OperationalError"
**Solution**: Ensure test database running:
```powershell
docker-compose -f docker-compose.test.yml up
```

### Issue: Timezone Errors
**Symptom**: "pytz.exceptions.UnknownTimeZoneError"
**Solution**: Ensure all times use UTC only (no timezone info)

---

## Test Data Reference

### Sample Trade Data
- **Trade 1**: GOLD, buy, 1950→1960, +10 PnL (winner)
- **Trade 2**: GOLD, sell, 1960→1955, -5 PnL (loser)
- **Trade 3**: EURUSD, buy, 1.0800→1.0850, +50 PnL (winner)

### Sample User
- Email: test@example.com
- Telegram ID: 12345

### Sample Metrics
- Sharpe Ratio: ~1.5 (good)
- Sortino Ratio: ~2.1 (excellent)
- Calmar Ratio: ~3.0 (excellent)
- Profit Factor: 2.5+ (strong)
- Recovery Factor: 2.0+ (good)

---

## Success Criteria

✅ **All tests passing**: 39+ tests with 0 failures
✅ **Coverage ≥90%**: Minimum 90% code coverage
✅ **No warnings**: Clean pytest output
✅ **Fast execution**: Complete suite <10 seconds
✅ **Deterministic**: Same results on repeated runs

---

## Next Steps After Tests Pass

1. **Documentation**
   - Create `/docs/prs/PR-051-IMPLEMENTATION-COMPLETE.md`
   - Create `/docs/prs/PR-052-IMPLEMENTATION-COMPLETE.md`
   - Create `/docs/prs/PR-053-IMPLEMENTATION-COMPLETE.md`

2. **Integration**
   - Register routes in `backend/app/main.py`
   - Update CHANGELOG.md
   - Run GitHub Actions CI/CD

3. **Validation**
   - Manual testing of endpoints
   - Load testing with realistic data
   - Performance profiling

4. **Deployment**
   - Stage to test environment
   - Production deployment
   - Monitor metrics

---

**Ready to run tests?**

```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_pr_051_052_053_analytics.py -v --cov=backend/app/analytics --cov-report=html
```
