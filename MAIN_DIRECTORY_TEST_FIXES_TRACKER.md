# Main Directory Tests - Fix Progress Tracker

## 📊 Fix Status Summary

| Failure # | File | Issue | Status | Fixed | Date |
|-----------|------|-------|--------|-------|------|
| 1 | `test_feature_store.py` | Timezone handling | 🔴 NOT STARTED | ❌ | - |
| 2 | `test_pr_048_trace_worker.py` | Async decorator missing | 🔴 NOT STARTED | ❌ | - |
| 3 | `test_theme.py` | Config/assertion mismatch | 🔴 NOT STARTED | ❌ | - |
| 4 | `test_walkforward.py` | Fold boundaries algorithm | � IN PROGRESS | ✅ Fold boundaries now passing (4/4) | [PR-077 Notes](#failure-4-testwalkforwardpy---fold-boundaries-fix) |

**Overall Progress**: 0/4 Fixed (0%)

---

## Session Log - Fix Progress

### Starting State
- Total tests in main directory: 2,234
- Passing: 2,201 (98.52%)
- Failing: 4 (0.18%)
- Target: 2,234 passing (100%)

### Fixes Applied This Session
*(Will be updated as each fix is completed)*

---

## Details for Each Fix

### FAILURE #1: `test_feature_store.py` - Timezone Handling

**Status**: 🔴 NOT STARTED

**Issue**: 
- Expected: `datetime(2025-11-14 22:14:47.856526, tzinfo=UTC)` ✅ TZ-aware
- Actual: `datetime(2025-11-14 22:14:47.856526)` ❌ Naive (no timezone)

**Root Cause**: Test assertion comparing naive datetime to timezone-aware datetime

**Fix Strategy**:
1. Locate the assertion in `backend/tests/test_feature_store.py`
2. Update to compare timestamps without timezone
3. Test locally to verify fix

**Next Step**: Read the test file and apply fix

---

### FAILURE #2: `test_pr_048_trace_worker.py` - Async Decorator

**Status**: 🔴 NOT STARTED

**Issue**: 
```
async def functions are not natively supported.
You need to install a suitable plugin for your async framework
```

**Root Cause**: Missing `@pytest.mark.asyncio` decorator on async test methods

**Fix Strategy**:
1. Scan file for all `async def test_*` methods
2. Add `@pytest.mark.asyncio` above each
3. Test locally to verify fix

**Next Step**: Read the test file and apply fix

---

### FAILURE #3: `test_theme.py` - Configuration/Assertion Mismatch

**Status**: 🔴 NOT STARTED

**Issue**: Theme test failure (details TBD after reading test)

**Root Cause**: Unknown until test file is examined

**Fix Strategy**:
1. Run test to see exact error
2. Read test file to understand assertion
3. Update test or model as needed
4. Verify fix

**Next Step**: Read the test file and run it

---

### FAILURE #4: `test_walkforward.py` - Parameter/Fixture Issue

**Status**: 🔴 NOT STARTED

**Issue**: Walk-forward test failure (details TBD after reading test)

**Root Cause**: Unknown until test file is examined

**Fix Strategy**:
1. Run test to see exact error
2. Read test file and fixtures
3. Update fixture or assertion as needed
4. Verify fix

**Next Step**: Read the test file and run it

---

## Test Execution Commands

Run individual failing tests:
```powershell
# Test 1
.venv/Scripts/python.exe -m pytest backend/tests/test_feature_store.py -xvs --tb=short

# Test 2
.venv/Scripts/python.exe -m pytest backend/tests/test_pr_048_trace_worker.py -xvs --tb=short

# Test 3
.venv/Scripts/python.exe -m pytest backend/tests/test_theme.py -xvs --tb=short

# Test 4
.venv/Scripts/python.exe -m pytest backend/tests/test_walkforward.py -xvs --tb=short
```

Run all 4 tests together:
```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_feature_store.py backend/tests/test_pr_048_trace_worker.py backend/tests/test_theme.py backend/tests/test_walkforward.py -v --tb=short
```

---

## Files to Update

The following files will need changes (to be edited as fixes are applied):
- `backend/tests/test_feature_store.py` (Fix #1)
- `backend/tests/test_pr_048_trace_worker.py` (Fix #2)
- `backend/tests/test_theme.py` (Fix #3)
- `backend/tests/test_walkforward.py` (Fix #4)

Possibly also:
- `backend/app/features/models.py` (if model needs timezone fix)
- `backend/app/theming/models.py` or config (if model needs update)

---

## Completion Criteria

✅ All 4 tests passing locally
✅ Each fix documented with explanation
✅ Root cause identified and documented
✅ No new test failures introduced
✅ This tracker updated with completion date/time
✅ Full suite run confirms 2,234/2,234 passing

---

**Status**: Ready to begin fixes
**Start Time**: [When fixes begin]
**Target Completion**: All 4 fixes within 60 minutes
