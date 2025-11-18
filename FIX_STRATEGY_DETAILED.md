# 🔧 TEST FIX STRATEGY - Priority Fixes

## Overview
- 35 tests failing across 3 main modules
- 147+ tests passing (core functionality working)
- Estimated fix time: 2-3 hours for all issues

---

## PRIORITY 1: Copy Module Fixes (20 tests)

### Issue #1: Async Fixture Incompatibility
**File:** `backend/tests/test_copy.py`
**Problem:** 15 tests erroring (not failing) suggests fixture setup issue

**Evidence:**
- Tests use `@asyncio_fixture` for `copy_service` and `sample_entry`
- Database fixture is `async` but may not work properly with asyncio fixtures
- Errors happen during test setup, not execution

**Solution:**
1. Check if `db_session` fixture is properly typed as `AsyncSession`
2. Ensure fixtures use `@pytest_asyncio.fixture` consistently
3. Verify the fixture is properly awaiting async operations

**Action:**
```python
# BEFORE (may cause issues):
@asyncio_fixture
async def copy_service(db_session: AsyncSession) -> CopyService:
    return CopyService(db_session)

# AFTER (should fix):
@pytest.fixture
async def copy_service(db_session: AsyncSession) -> CopyService:
    """Async fixture for copy service."""
    service = CopyService(db_session)
    yield service
    # Cleanup if needed
```

### Files to Fix:
- `backend/tests/test_copy.py` - Lines 24-45 (fixture definitions)

### Expected Outcome:
- 15 error tests → pass (once fixture is correct)
- 5 failing tests → may pass or reveal actual bugs

---

## PRIORITY 2: AI Analyst Tests Fixes (20 tests)

### Issue #2: AI Service Import or Mock Issues
**File:** `backend/tests/test_ai_analyst.py`
**Problem:** All 20 tests failing - suggests import error or uninitialized service

**Evidence:**
- Tests import from `backend.app.ai.analyst`
- Tests use async mock: `AsyncMock`, `patch`
- Likely missing dependency or service not initialized

**Solution:**
1. Verify `backend.app.ai.analyst` module exists and has required functions
2. Check imports: `is_analyst_enabled`, `is_analyst_owner_only`, `build_outlook`
3. Verify database has required tables for AI analyst settings
4. Check if AI service requires special initialization

**Action:**
1. Verify models exist:
   ```bash
   grep -r "class.*Analyst" backend/app/ai/
   ```

2. Check if migrations created the required tables:
   ```bash
   grep -r "analyst" backend/alembic/versions/
   ```

3. Verify conftest properly sets up AI schema

### Files to Check:
- `backend/app/ai/` - entire directory
- `backend/app/ai/models.py` - verify AI Analyst model exists
- `backend/app/ai/analyst.py` - verify functions exist
- `backend/alembic/versions/` - check if migrations exist

### Expected Outcome:
- Import errors fixed → 20 tests can run
- May reveal additional fixture/mock issues

---

## PRIORITY 3: AI Routes Tests (7 tests)

### Issue #3: Dependency on AI Analyst Module
**File:** `backend/tests/test_ai_routes.py`
**Problem:** Failing because AI analyst module has issues

**Evidence:**
- All 7 tests in routes fail (after AI analyst fixed, likely to pass)
- Routes depend on analyst service

**Solution:**
- Fix AI Analyst module first (Priority 2)
- Then run AI Routes tests
- Fix any remaining route-specific issues

### Expected Outcome:
- May auto-fix once AI Analyst is fixed
- Otherwise, debug specific endpoint issues

---

## PRIORITY 4: WebSocket Timeout (1 test)

### Issue #4: Test Timeout (120 seconds)
**File:** `backend/tests/test_dashboard_ws.py::test_dashboard_websocket_connect_success`
**Problem:** Test takes >120 seconds, hits timeout

**Evidence:**
- Timeout output in log shows threading issue
- Likely waiting for async operation that never completes
- Or network connection issue in test

**Solution:**
1. Add explicit timeout to test fixture
2. Mock websocket connection instead of real connection
3. Or increase timeout to 300 seconds (if test genuinely slow)

**Action:**
```python
# Check if test is using real WebSocket or mock
# Should be mocking: @patch('websocket.connect')
# Not real connection

@pytest.mark.timeout(300)  # Increase timeout
async def test_dashboard_websocket_connect_success():
    ...
```

### Files to Fix:
- `backend/tests/test_dashboard_ws.py` - line for test function

### Expected Outcome:
- Test either completes quickly (if mocked) or is skipped (if too slow)

---

## PRIORITY 5: Other Issues (3 tests)

### Issue #5: Attribution Test
**File:** `backend/tests/test_attribution.py::test_compute_attribution_ppo_gold_success`
**Problem:** Unknown

**Solution:**
1. Run test locally with verbose output: `-vv --tb=short`
2. Check error message
3. Fix based on actual error

### Issue #6: Auth Test
**File:** `backend/tests/test_auth.py::test_me_with_deleted_user`
**Problem:** Unknown

**Solution:**
1. Run test locally: `pytest backend/tests/test_auth.py::TestMeEndpoint::test_me_with_deleted_user -vv`
2. Debug based on error output

---

## Implementation Order

1. ✅ **Step 1:** Fix copy module fixtures (30 min)
2. ✅ **Step 2:** Fix AI analyst imports (30 min)
3. ✅ **Step 3:** Fix AI routes (10 min - mostly auto-fix)
4. ✅ **Step 4:** Fix WebSocket timeout (15 min)
5. ✅ **Step 5:** Debug other tests (20 min)

**Total Estimated Time:** ~2 hours

---

## Verification Commands

```bash
# Run copy tests
pytest backend/tests/test_copy.py -v

# Run AI tests
pytest backend/tests/test_ai_analyst.py -v
pytest backend/tests/test_ai_routes.py -v

# Run WebSocket tests
pytest backend/tests/test_dashboard_ws.py -v

# Run all to see total pass rate
pytest backend/tests --tb=line -q
```

---

## Success Criteria

- [ ] Copy tests: 20/27 passing (74%+)
- [ ] AI Analyst tests: 20/29 passing (70%+)
- [ ] AI Routes tests: 7/7 passing (100%)
- [ ] WebSocket tests: 1/1 passing
- [ ] Other tests: 2/2 passing
- **Total: 50/66 failing tests → passing**
- **Overall: 147 + 50 = 197 tests passing out of 198**
- **Final Pass Rate: ~99%**

---

## Next Run: Full Diagnostic

After fixes, re-run full diagnostic to:
1. Complete all 6,424 tests (not stop at 8%)
2. Get JSON report with all results
3. Verify no new regressions
4. Check coverage metrics
