# NEXT PHASE IMPLEMENTATION CHECKLIST

**Priority**: Continue fixing all failing tests - no skipping
**Previous Session**: Fixed 3 major failure patterns, 155+ tests verified passing
**Current Session Goal**: Apply patterns to remaining test modules

## PHASE 1: EXTEND CLEAR_AUTH_OVERRIDE PATTERN (Est. 1 hour)

### Tasks
- [ ] **Task 1a**: Apply clear_auth_override to test_auth.py
  - File: `backend/tests/test_auth.py`
  - Tests needing fix: All tests with "without_token", "invalid_token", "expired_token"
  - Pattern: Add `clear_auth_override` parameter to test function
  - Verification: pytest backend/tests/test_auth.py::test_me_without_token -v
  - Expected: Should return 401, not 200

- [ ] **Task 1b**: Apply clear_auth_override to remaining approvals tests
  - File: `backend/tests/test_approvals_routes.py`
  - Tests needing fix: Any test expecting 401/403 that's getting 200/201
  - Pattern: Same as above
  - Verification: Run full test file
  - Expected: 7/7 tests passing instead of current 6/7

- [ ] **Task 1c**: Apply clear_auth_override to users_routes tests
  - File: `backend/tests/test_users_routes.py` (if exists)
  - Pattern: Same pattern
  - Expected: +10-20 tests passing

### Quick Test After Completion
```powershell
# Should see 150+ tests still passing
.venv/Scripts/python.exe -m pytest backend/tests/test_education.py backend/tests/test_signals_routes.py -q
```

---

## PHASE 2: IMPLEMENT RBAC OWNERSHIP VALIDATION (Est. 1.5 hours)

### Context
- Test `test_approval_not_signal_owner_returns_403` is failing
- User A creates signal, User B tries to approve it → Should get 403 Forbidden
- Currently: Returning 201 (success) because no ownership check exists

### Tasks
- [ ] **Task 2a**: Add ownership validation to ApprovalService
  - File: `backend/app/approvals/service.py`
  - Method: `approve_signal(signal_id, user_id, ...)`
  - After signal retrieval: Check `if signal.user_id != user_id: raise ValueError("You don't have permission to approve this signal")`
  - Pattern: Match other ValueError patterns for consistent handling
  - Verification: Run test suite to check error is raised correctly

- [ ] **Task 2b**: Verify route layer handles ownership error
  - File: `backend/app/approvals/routes.py`
  - The existing ValueError handler should catch it
  - Check if route needs to map "permission" → 403 or just use 400
  - May need: Add check for "permission" keyword to return 403

- [ ] **Task 2c**: Test with create_auth_token fixture
  - Use `create_auth_token(user2)` to create approval as different user
  - Verify 403 response
  - Verify error message is clear

### Verification
```powershell
# Run approvals tests with ownership check
.venv/Scripts/python.exe -m pytest backend/tests/test_approvals_routes.py::TestCreateApprovalEndpoint::test_approval_not_signal_owner_returns_403 -v
# Expected: PASSED ✅
```

---

## PHASE 3: FIX WEBSOCKET TESTS (Est. 2 hours)

### Context
- File: `backend/tests/test_dashboard_ws.py` (6 tests, all failing)
- Likely issue: WebSocket connections not handling auth properly
- Same clear_auth_override pattern probably applies

### Tasks
- [ ] **Task 3a**: Analyze test_dashboard_ws.py
  - Read the test file
  - Identify what tests are expecting (connection allowed/denied)
  - Check for global mock issues
  - Identify which tests need auth validation vs which need auth bypass

- [ ] **Task 3b**: Apply clear_auth_override where needed
  - Tests expecting to connect without token → Use clear_auth_override
  - Should then get 401 or WebSocket rejection
  - Tests expecting authorized connection → Provide token from create_auth_token()

- [ ] **Task 3c**: Fix WebSocket auth headers
  - WebSocket usually passes auth differently than HTTP (in headers differently)
  - May need: Extract token extraction logic for WebSocket
  - Check if `backend/app/auth/dependencies.py` has WebSocket-specific handlers

### Verification
```powershell
# Run WebSocket tests
.venv/Scripts/python.exe -m pytest backend/tests/test_dashboard_ws.py -v
# Expected: 6/6 PASSED ✅
```

---

## PHASE 4: SYSTEMATIC MODULE REVIEW (Est. 3-4 hours)

### Context
- 200+ test files, ~6000 tests total
- So far verified 155+ tests passing
- Need to identify next failure patterns

### Tasks
- [ ] **Task 4a**: Generate comprehensive test status
  - Run: `pytest --collect-only -q > test_inventory.txt` 
  - Count by module: Which modules have most failures
  - Identify top 5 failing modules

- [ ] **Task 4b**: Run top 5 failing modules individually
  - Run each module with `-v` flag
  - Capture error patterns (not individual tests)
  - Look for recurring issues (same as auth, same as error handling, etc.)

- [ ] **Task 4c**: Classify failures by pattern
  - Pattern 1: Global mock issues (need clear_auth_override)
  - Pattern 2: Missing error handling (need service fixes)
  - Pattern 3: Missing fixtures (need conftest updates)
  - Pattern 4: Unimplemented features (business logic gaps)
  - Pattern 5: Other

- [ ] **Task 4d**: Plan fixes by pattern
  - Pattern 1 issues: Use clear_auth_override (quick wins)
  - Pattern 2 issues: Apply error handling strategy (medium effort)
  - Pattern 3 issues: Create fixtures (medium effort)
  - Pattern 4 issues: Implement features (longer effort)

### Quick Test After Completion
```powershell
# Get baseline of how many tests pass/fail overall
.venv/Scripts/python.exe -m pytest backend/tests/ -q --tb=no 2>&1 | tail -5
```

---

## PHASE 5: FIX PATTERN-1 MODULES (Est. 2-3 hours)

### Tasks (These are placeholders - will be filled after Phase 4)
- [ ] **Task 5a**: List all modules needing clear_auth_override
  - From Phase 4 analysis
  - Estimate: 20-30 test files
  - Effort per file: 5-10 minutes

- [ ] **Task 5b**: Apply clear_auth_override systematically
  - Go through identified modules
  - Add fixture to all auth validation tests
  - Verify each batch of 5-10 tests

- [ ] **Task 5c**: Track cumulative progress
  - After each module: Note tests now passing
  - Running total: Started at 155+, target 300+

### Expected Outcome
- 50+ additional tests passing
- Total: 200+ tests verified passing

---

## PHASE 6: FIX PATTERN-2 MODULES (Est. 2-3 hours)

### Tasks (Will be defined after Phase 4)
- [ ] **Task 6a**: List all modules needing error handling improvements
- [ ] **Task 6b**: Apply same IntegrityError + ValueError separation
- [ ] **Task 6c**: Update route handlers to map error types to HTTP codes

### Expected Outcome
- 40+ additional tests passing
- Total: 240+ tests verified passing

---

## PHASE 7: FIX PATTERN-3 MODULES (Est. 1-2 hours)

### Tasks (Will be defined after Phase 4)
- [ ] **Task 7a**: Create missing fixtures
- [ ] **Task 7b**: Add helper functions to conftest
- [ ] **Task 7c**: Update tests to use new fixtures

### Expected Outcome
- 30+ additional tests passing
- Total: 270+ tests verified passing

---

## VALIDATION CHECKLIST

After each phase completion:

- [ ] Run core modules to ensure nothing broke
  ```powershell
  .venv/Scripts/python.exe -m pytest backend/tests/test_education.py backend/tests/test_signals_routes.py -q
  ```

- [ ] Check git status to see what changed
  ```powershell
  git status --short
  ```

- [ ] Verify no new errors introduced
  ```powershell
  .venv/Scripts/python.exe -m pytest backend/tests/test_approvals_routes.py -q
  ```

---

## DOCUMENTATION

### Files to Update After Each Phase
1. `DETAILED_SESSION_NOTES.md` - Add session summary
2. `NEXT_PHASE_CHECKLIST.md` - Update with Phase 4 findings
3. `CHANGELOG.md` - Note which tests were fixed

### Commit Strategy
After each phase (except Phase 4):
```powershell
# Commit changes
git add backend/
git commit -m "Fix [PATTERN] failures in [MODULE_NAME] - [N] tests now passing"
```

---

## ROLLBACK PLAN

If any fix breaks existing tests:
```powershell
# Revert last change
git checkout backend/app/[file].py
# Or revert to last commit
git reset --hard HEAD~1
```

---

## ESTIMATED TIMELINE

| Phase | Est. Time | Running Total | Status |
|-------|-----------|---------------|--------|
| 1. Auth Override | 1 hour | 170+ tests | ➡️ NEXT |
| 2. RBAC Validation | 1.5 hours | 180+ tests | ➡️ NEXT |
| 3. WebSocket Tests | 2 hours | 186+ tests | BLOCKED |
| 4. Module Review | 4 hours | 186+ tests | ANALYSIS |
| 5. Pattern-1 Fixes | 3 hours | 236+ tests | PENDING |
| 6. Pattern-2 Fixes | 3 hours | 276+ tests | PENDING |
| 7. Pattern-3 Fixes | 2 hours | 306+ tests | PENDING |

**Total Estimated Time**: 16-17 hours
**Expected Final Result**: 300+ tests verified passing (50%+ of full suite)

---

## SUCCESS CRITERIA

✅ Session is complete when:
1. All Phase 1-3 tasks completed
2. Phase 4 analysis identifies remaining patterns
3. Plans created for Phase 5-7
4. At least 250+ tests verified passing
5. All changes committed to git

---

## KEY CONTACTS/REFERENCES

- Master PR Document: `/base_files/Final_Master_Prs.md`
- Session Notes: `DETAILED_SESSION_NOTES.md`
- Previous Fixes: `backend/tests/conftest.py` (clear_auth_override pattern)
- Working Services: `backend/app/approvals/` (error handling example)

---

**Remember**: User requirement is to "fix all, no skipping or giving up"
This checklist provides systematic, pattern-based approach to maximize test coverage.
