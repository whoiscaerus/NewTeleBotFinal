# 🚀 Testing Strategy - Quick Summary

## The Problem
- Full test suite: 6,400+ tests, **1+ hour** to run
- CI was running same 1-hour test on every push
- Needed faster feedback loop for fixing issues

## The Solution
Created **quick testing tools** to run focused test suites in **2-10 minutes**:

### ⚡ Quick Test Runner
```bash
python test_quick.py <suite_name>
```

**Available suites:**
- `data_pipeline` → 66 tests, 1-2 min (SymbolPrice, OHLCCandle, DataPullLog)
- `position` → 9 tests, 15 sec (OpenPosition model)
- `trade_store` → 34 tests, 1-2 min (Trade, Position, EquityPoint)
- `decision_logs` → 20 tests, 30 sec (DecisionLog model)
- `rate_limit` → 11 tests, 2 min (Rate limiting logic)
- `poll` → 7 tests, 1 min (Poll functionality)
- `integration` → 7 tests, 30 sec (Integration workflows)
- `schema` → 129 tests, 2-3 min (ALL schema-related fixes)
- `all` → 188 tests, 5-10 min (All critical tests)
- `full` → 6,400+ tests, 1+ hour (FULL suite before final commit)

### 📋 Example Usage

**Testing a quick fix locally:**
```bash
python test_quick.py data_pipeline    # 1-2 min to verify fix works
```

**Before committing:**
```bash
python test_quick.py schema           # 2-3 min to ensure no regressions
```

**Final validation:**
```bash
python test_quick.py full             # 1 hour - run before merge to main
```

## 📚 Documentation

### QUICK_TEST_GUIDE.md
Complete reference guide with:
- All available test commands
- Test timing estimates
- Coverage reporting examples
- Environment variables
- Troubleshooting tips

### pytest-focused.ini
pytest configuration that skips slow tests:
```bash
pytest backend/tests -c pytest-focused.ini
```

## 🎯 Testing Workflow (New!)

### Step 1: Fix Code (5-30 min)
```bash
# Edit code in backend/app/
```

### Step 2: Quick Validate (2 min)
```bash
python test_quick.py <affected_suite>
```
Example: If you fixed data_pipeline models:
```bash
python test_quick.py data_pipeline
```

### Step 3: Check Related (3-5 min)
```bash
python test_quick.py schema
```

### Step 4: Final Validation (1 hour)
```bash
python test_quick.py full
```

### Step 5: Commit & Push
```bash
git add .
git commit -m "fix: ..."
git push whoiscaerus main
```

## ✅ Benefits

| Before | After |
|--------|-------|
| Run full suite (~1 hour) to test one module | Run targeted test (~2 min) |
| Slow feedback loop discourages testing | Fast feedback loop enables rapid iteration |
| Wasted hour on unrelated tests | Focus only on affected code |
| Hard to debug with 1000s of tests | Easy to debug with 10-50 tests |

## 🔧 CI/CD Changes Made

1. **Fixed `test-changed-only.yml` workflow**
   - Now runs automatically (was being skipped)
   - Triggers on any push to main
   - Completes in ~5-10 minutes

2. **Main `tests.yml` still runs full suite**
   - Ensures nothing breaks
   - Runs ~1 hour (acceptable for main branch validation)
   - Provides comprehensive coverage report

## 🎓 When to Use Which

| Scenario | Command | Time |
|----------|---------|------|
| Quick local test after fix | `python test_quick.py <module>` | 30 sec - 2 min |
| Before commit to local branch | `python test_quick.py schema` | 2-3 min |
| Before push to GitHub | `python test_quick.py all` | 5-10 min |
| Final validation before merge | `python test_quick.py full` | 1 hour |
| Specific test debugging | `.venv/Scripts/python.exe -m pytest backend/tests/test_file.py::test_name -xvs` | 10-30 sec |

## 📌 Key Files

1. **test_quick.py** - Main quick test runner script
2. **QUICK_TEST_GUIDE.md** - Comprehensive testing reference
3. **pytest-focused.ini** - pytest config for focused testing
4. **.github/workflows/test-changed-only.yml** - Quick CI workflow (fixed)
5. **.github/workflows/tests.yml** - Full test suite CI workflow

## 💡 Pro Tips

1. **Always run quick test first** before pushing
2. **Run schema tests** if you touched any models
3. **Run full suite** only before final merge
4. **Check what changed** to decide which tests to run:
   ```bash
   git diff --name-only HEAD~1
   ```

---

**Updated**: 2025-11-17
**Status**: ✅ Ready to use - Run `python test_quick.py all` to test now!
