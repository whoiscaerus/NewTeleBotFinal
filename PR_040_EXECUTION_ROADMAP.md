# 🎯 PR-040 EXECUTION ROADMAP - STEP BY STEP

**Status**: Ready to fix | 5 issues identified | 2.5h to production-ready

---

## BEFORE YOU START

**Read These First** (in order):
1. ✅ `PR_040_AUDIT_SUMMARY.md` (this is the overview) ← START HERE
2. ✅ `PR_040_CRITICAL_ISSUES.md` (exact code to fix) ← USE THIS
3. ✅ `PR_040_AUDIT_REPORT.md` (full technical details) ← FOR DEEP DIVE
4. ✅ `PR_040_IMPLEMENTATION_MATRIX.md` (spec vs reality) ← REFERENCE

**Time Required**: 2.5-3 hours total
**Difficulty**: LOW-MEDIUM (straightforward fixes, no redesign needed)

---

## FIX EXECUTION PLAN

### ⏱️ PHASE 1: FIXES (2h 10m)

#### FIX #1: Add Telemetry Metrics [15 min] 🟡

**What**: Add 3 missing metrics to Prometheus collector

**Where**: `backend/app/observability/metrics.py`

**What to Add**: (in `MetricsCollector.__init__()`)
```python
self.billing_webhook_replay_block_total = Counter(...)
self.billing_webhook_invalid_sig_total = Counter(...)
self.idempotent_hits_total = Counter(...)
```

**Full Code**: See `PR_040_CRITICAL_ISSUES.md` → "ISSUE #1"

**Verification**:
```
✅ No syntax errors in metrics.py
✅ metrics module imports successfully
```

---

#### FIX #2: Implement Entitlements Activation [30 min] 🔴

**What**: Replace TODO stub with working implementation

**Where**: `backend/app/billing/webhooks.py`, lines 345-365

**Current**: Commented placeholder code, nothing happens

**After**: Real database insert of UserEntitlement records

**Full Code**: See `PR_040_CRITICAL_ISSUES.md` → "ISSUE #2"

**What Gets Executed**:
```
User pays for premium
  ↓
Stripe webhook received
  ↓
_activate_entitlements("usr_123", "premium")
  ↓
INSERT INTO user_entitlements (user_id, plan_code, entitlements)
VALUES ('usr_123', 'premium', {'signals_enabled': true, 'max_devices': 5, ...})
  ↓
✅ User now has premium features
```

**Verification**:
```
✅ No syntax errors
✅ Function uses correct database model
✅ Proper error handling
✅ Logging added
```

---

#### FIX #3: Implement Payment Event Logging [20 min] 🔴

**What**: Replace TODO stub with working implementation

**Where**: `backend/app/billing/webhooks.py`, lines 390-437

**Current**: Commented placeholder code, no logging happens

**After**: Real database insert of PaymentEvent records

**Full Code**: See `PR_040_CRITICAL_ISSUES.md` → "ISSUE #3"

**What Gets Executed**:
```
Payment webhook received
  ↓
_log_payment_event(
    user_id="usr_123",
    event_type="checkout_completed",
    plan_code="premium",
    amount=2999
)
  ↓
INSERT INTO payment_events (...)
INSERT INTO audit_logs (...)  # For compliance
  ↓
✅ Payment logged in database + audit trail
```

**Verification**:
```
✅ No syntax errors
✅ Uses PaymentEvent and AuditLog models
✅ JSON serialization for metadata
✅ Proper error handling
```

---

#### FIX #4: Move Idempotency to Core [20 min] 🟡

**What**: Reorganize file location + consolidate code

**Current**:
```
backend/app/billing/idempotency.py          ← WRONG LOCATION
backend/app/billing/security.py             ← Has duplicate code
backend/app/core/                           ← No idempotency.py
```

**After**:
```
backend/app/core/idempotency.py             ← CORRECT LOCATION
backend/app/billing/security.py             ← Uses from core
backend/app/billing/webhooks.py             ← Uses from core
```

**Steps**:
1. Open `backend/app/billing/idempotency.py` (copy all content)
2. Create `backend/app/core/idempotency.py` (paste content)
3. Update imports in `security.py` (from backend.app.core.idempotency import ...)
4. Remove duplicate code from `security.py`
5. Delete old file `backend/app/billing/idempotency.py`

**Files Modified**:
- ✅ Create: `backend/app/core/idempotency.py`
- ✅ Update: `backend/app/billing/security.py` (imports)
- ✅ Delete: `backend/app/billing/idempotency.py`

**Verification**:
```
✅ idempotency.py exists in /core/
✅ No duplicate code in security.py
✅ Imports work correctly
✅ No import errors in modules
```

---

#### FIX #5: Implement Integration Tests [45 min] 🟡

**What**: Replace 3 empty test stubs with real implementations

**Where**: `backend/tests/test_pr_040_security.py`, lines 333-370

**Current**: 3 test methods with only `pass`

**After**: Real test implementations

**Tests to Implement**:
1. `test_webhook_endpoint_requires_valid_signature()`
   - POST invalid signature
   - Verify 403 rejection

2. `test_webhook_endpoint_rejects_replay_attacks()`
   - Send same webhook twice
   - First: processes it
   - Second: returns cached result

3. `test_webhook_endpoint_returns_rfc7807_on_error()`
   - POST with invalid format
   - Verify RFC7807 error response

**Full Code**: See `PR_040_CRITICAL_ISSUES.md` → "ISSUE #5"

**Verification**:
```
✅ No syntax errors in tests
✅ All 3 tests runnable
✅ Tests verify expected behavior
```

---

### ⏱️ PHASE 2: TESTING (1 hour)

#### TEST: Unit Tests
```bash
.venv\Scripts\python.exe -m pytest backend/tests/test_pr_040_security.py -v
```

**Expected Result**:
```
25 passed (not 23)
- 23 original tests still passing ✅
- 2 integration tests now implemented ✅
- 0 errors
```

**If Fails**:
- Check syntax in your edits
- Run specific test: `pytest ...::test_name -v`
- Review error message

---

#### TEST: Code Coverage
```bash
.venv\Scripts\python.exe -m pytest backend/app/billing --cov=backend/app/billing --cov-report=term-missing -q
```

**Expected Result**:
```
TOTAL: >90% coverage
Missing lines should be error paths only
```

---

#### TEST: Manual Webhook (if possible)

If you can trigger a real Stripe webhook:

```
1. Send test payment webhook
2. Verify in database:
   - ✅ UserEntitlement record created
   - ✅ PaymentEvent record created
   - ✅ AuditLog entry created
3. Verify in logs:
   - ✅ Entitlements activated
   - ✅ Payment event logged
4. Verify metrics:
   - ✅ Replay block counter incremented (if replayed)
   - ✅ Idempotent hits incremented (if replayed)
```

---

### ⏱️ PHASE 3: REVIEW & CLEANUP (30 min)

#### CODE REVIEW CHECKLIST

Before committing, verify:

- [ ] No syntax errors (IDE shows no red squiggles)
- [ ] No TODO/FIXME comments in new code
- [ ] All imports work (no ImportError)
- [ ] All docstrings present and clear
- [ ] Type hints on all functions
- [ ] Error handling for all database operations
- [ ] Logging for all important steps
- [ ] No generic `Exception` catches (use specific exceptions)

---

#### TEST RESULTS VERIFICATION

- [ ] 25/25 tests PASSING (up from 23)
- [ ] 0 FAILED
- [ ] 0 ERRORS
- [ ] Coverage >90%
- [ ] No warnings in test output

---

#### FINAL VALIDATION

```bash
# Run full billing tests
.venv\Scripts\python.exe -m pytest backend/tests/test_pr_040_security.py -v

# Check for regressions in other tests
.venv\Scripts\python.exe -m pytest backend/tests/test_pr_038_billing.py -v

# Verify no import errors
.venv\Scripts\python.exe -c "from backend.app.billing.security import *; print('OK')"
.venv\Scripts\python.exe -c "from backend.app.core.idempotency import *; print('OK')"
```

---

## TIMELINE ESTIMATES

```
Activity                    Estimated    Actual    Variance
─────────────────────────────────────────────────────────────
Read audit docs             20 min       ___       ±5 min
Fix #1: Metrics             15 min       ___       ±5 min
Fix #2: Entitlements        30 min       ___       ±10 min
Fix #3: Logging             20 min       ___       ±10 min
Fix #4: File location       20 min       ___       ±5 min
Fix #5: Integration tests   45 min       ___       ±15 min
─────────────────────────────────────────────────────────────
SUBTOTAL (Fixes):           2h 10m       ___       ±1 hour

Testing & Validation        1h           ___       ±30 min
Code Review Checklist       30 min       ___       ±10 min
─────────────────────────────────────────────────────────────
TOTAL ESTIMATE:             3h 40m       ___       ±1.5 hours
```

---

## SUCCESS CRITERIA

### ✅ Ready When:

- [x] All 5 fixes applied
- [x] 25/25 tests PASSING (or >92% excluding database fixture issues)
- [x] >90% code coverage
- [x] No syntax errors
- [x] No TODO/FIXME comments
- [x] All docstrings present
- [x] Type hints complete
- [x] Error handling comprehensive
- [x] Manual testing completed
- [x] Code review passed

### ❌ NOT Ready When:

- [ ] Any test failures
- [ ] Coverage <90%
- [ ] TODO placeholders remain
- [ ] Missing error handling
- [ ] Generic Exception catches
- [ ] Manual testing shows bugs

---

## ROLLBACK PLAN (if needed)

If something breaks during implementation:

```bash
# Revert all changes
git checkout HEAD -- backend/app/billing/
git checkout HEAD -- backend/app/core/
git checkout HEAD -- backend/app/observability/metrics.py
git checkout HEAD -- backend/tests/test_pr_040_security.py

# Start over
git pull origin main
```

---

## COMMIT MESSAGE (when ready)

```
fix(pr-040): Complete payment security hardening implementation

- Add billing_webhook_replay_block_total and idempotent_hits_total metrics
- Implement _activate_entitlements() to grant features after payment
- Implement _log_payment_event() for audit trail compliance
- Move idempotency.py to /core/ for reusability
- Implement webhook endpoint integration tests
- Add RFC7807 error response format validation

Fixes #40
Test: 25/25 passing, >90% coverage
```

---

## NEXT AFTER THIS

Once PR-040 is merged and tested:

1. ✅ Move to PR-041: MT5 EA SDK & Reference EA
2. ✅ Continue PRs 42-50 (encryption, positions, price alerts, copy-trading, etc.)
3. ✅ Track all fixes in changelog

---

## SUPPORT

**Questions?**
- Technical: See `PR_040_AUDIT_REPORT.md` for deep details
- Code: See `PR_040_CRITICAL_ISSUES.md` for exact implementations
- Status: See `PR_040_FINAL_VERDICT.md` for production readiness

**Files Created**:
- `PR_040_AUDIT_SUMMARY.md` ← Overview
- `PR_040_CRITICAL_ISSUES.md` ← Implementation guide (USE THIS)
- `PR_040_AUDIT_REPORT.md` ← Full technical analysis
- `PR_040_IMPLEMENTATION_MATRIX.md` ← Spec comparison
- `PR_040_FINAL_VERDICT.md` ← Deployment readiness
- `PR_040_EXECUTION_ROADMAP.md` ← This file

---

## STATUS TRACKER

Copy this and update as you go:

```
PHASE 1: FIXES
[ ] Fix #1: Metrics (15 min) - Start: ___ End: ___
[ ] Fix #2: Entitlements (30 min) - Start: ___ End: ___
[ ] Fix #3: Logging (20 min) - Start: ___ End: ___
[ ] Fix #4: File location (20 min) - Start: ___ End: ___
[ ] Fix #5: Tests (45 min) - Start: ___ End: ___

PHASE 2: TESTING
[ ] Unit tests passing (25/25)
[ ] Coverage >90%
[ ] Manual testing complete

PHASE 3: REVIEW
[ ] Code review checklist complete
[ ] No syntax errors
[ ] Documentation updated
[ ] Ready for merge

STATUS: ⏳ READY TO START
```

---

**Last Updated**: October 27, 2025
**Ready to Begin**: ✅ YES
**Estimated Completion**: ~4 hours from start
**Difficulty Level**: 🟡 MEDIUM (straightforward, well-specified)

👉 **NEXT STEP**: Read `PR_040_CRITICAL_ISSUES.md` and start with Fix #1
