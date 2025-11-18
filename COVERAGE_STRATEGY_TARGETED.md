# 🎯 95% Coverage Strategy - Targeted Testing Approach

**Goal**: Reach 95% test coverage without wasting 1+ hour on full test suite runs.

## 📋 Current Status
- **Local tests**: 6,424 (takes 15-20 min to run locally)
- **CI tests**: 3,136 collected (takes 60+ min in GitHub Actions)
- **Current coverage**: ~85% backend
- **Target coverage**: 95% backend

## 🚀 New Strategy: Targeted Testing

Instead of running all 6,424 tests:

### Phase 1: Fix Schema Issues (DONE)
✅ Added missing model imports to `conftest.py`
- `SymbolPrice`, `OHLCCandle`, `DataPullLog` (data pipeline)
- `OpenPosition` (position monitoring)
- `Trade`, `Position`, `EquityPoint`, `ValidationLog` (trading store)
- 20+ additional models (telegram, KB, education, etc.)

**Validation**: Run targeted tests only
```bash
python test_quick.py data_pipeline      # ~30 sec
python test_quick.py position_monitor   # ~15 sec
python test_quick.py trade_store        # ~45 sec
# Total: ~90 seconds vs 60+ minutes
```

### Phase 2: Fix Test Logic Errors (IN PROGRESS)

From CI failure report, these need fixes:
- **test_poll_v2.py** (7 failures) - Redis/cache logic
- **test_pr_005_ratelimit.py** (11 failures) - Rate limiting algorithm
- **test_pr_017_018_integration.py** (7 failures) - Retry/resilience logic

**Validation**:
```bash
python test_quick.py poll              # Test polling
python test_quick.py ratelimit         # Test rate limiting
python test_quick.py integration       # Test resilience
```

### Phase 3: Add Missing Tests for 95% Coverage

**Gap Analysis**: Identify uncovered lines
```bash
python -m pytest backend/tests/test_data_pipeline.py \
  --cov=backend/app/trading/data \
  --cov-report=term-missing
```

**Coverage targets by module**:
| Module | Current | Target | Gap |
|--------|---------|--------|-----|
| data_pipeline | 82% | 95% | 13% |
| trading.store | 78% | 95% | 17% |
| trading.positions | 81% | 95% | 14% |
| polling | 75% | 95% | 20% |
| risk | 88% | 95% | 7% |

## 📊 Test Execution Time Breakdown

**Old approach** (run all 6,424 tests):
```
Collection:        15 min
Linting:          5 min
Type checking:     10 min
Tests:             60 min
Reports:           5 min
TOTAL:             95 minutes ❌ TOO SLOW
```

**New approach** (targeted):
```
Collection:        2 min
Specific module:   2-3 min
TOTAL:             5 minutes ✅ FAST
```

## 🛠️ Tools

### 1. Quick Test Script (Local)
```bash
# Test one module
python test_quick.py data_pipeline

# Test all targeted modules
python test_quick.py all

# Check timing
time python test_quick.py data_pipeline
```

### 2. Coverage Report (Local)
```bash
python -m pytest backend/tests/test_data_pipeline.py \
  --cov=backend/app/trading/data \
  --cov-report=html:coverage/data_pipeline

# Open coverage/data_pipeline/index.html in browser
```

### 3. Lightweight CI Workflow
- File: `.github/workflows/test-targeted.yml`
- Runs only schema-related tests
- Completes in ~5-10 minutes
- Still catches regressions in fixed code

## 📌 Workflow for Adding Tests

1. **Identify gap** (uncovered lines)
   ```bash
   python -m pytest backend/tests/test_xxx.py --cov=backend/app/xxx --cov-report=term-missing
   ```

2. **Write test** for uncovered line

3. **Run quick test** (5-30 seconds)
   ```bash
   python test_quick.py xxx
   ```

4. **Check coverage** increased
   ```bash
   python -m pytest backend/tests/test_xxx.py --cov=backend/app/xxx --cov-report=term
   ```

5. **Commit & push** (no waiting for 60+ min CI run)

6. **Monitor full CI** only for final validation (optional)

## 🎯 Coverage Targets by Phase

### Phase 1: Schema Fixes (CURRENT)
- ✅ Fix 929 schema errors
- Target: All data_pipeline, position_monitor, trade_store tests passing
- Time: ~2 min to validate

### Phase 2: Logic Fixes
- Fix 70 test failures
- Target: All poll_v2, ratelimit, integration tests passing
- Time: ~3 min to validate

### Phase 3: Coverage Gaps
- Add 100-200 new test cases
- Target: 95% coverage on all modules
- Time: 30 sec per new test

## 💡 Tips

1. **Don't run full suite locally** - use `test_quick.py`
2. **Check coverage with `--cov-report=term-missing`** to see exact uncovered lines
3. **Commit in smaller batches** - fixes schema first, then logic, then coverage
4. **Use `--maxfail=5`** to stop after 5 failures (faster iteration)

## ✅ Success Criteria

- [ ] All schema errors fixed (0/929)
- [ ] All test logic errors fixed (0/70)
- [ ] Backend coverage ≥95%
- [ ] Each module has dedicated test file with comprehensive coverage
- [ ] Full test suite can be validated in <10 minutes
