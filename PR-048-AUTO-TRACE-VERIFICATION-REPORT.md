╔═══════════════════════════════════════════════════════════════════════════╗
║                    PR-048 VERIFICATION REPORT - AUTO-TRACE               ║
║           Auto-Trace to Third-Party Trackers (Post-Close)                ║
║                                                                           ║
║   Status: ⚠️  NOT YET IMPLEMENTED - Ready for Development                ║
╚═══════════════════════════════════════════════════════════════════════════╝

---

# EXECUTIVE SUMMARY

**PR-048 Per Master PR Document:**
```
Name: Auto-Trace to Third-Party Trackers (Post-Close)
Goal: Boost trust by pushing closed trades to third-party trackers
      (e.g., Myfxbook) after a safe delay
```

**Current Status**: ❌ **NOT IMPLEMENTED**

---

# MASTER PR SPECIFICATION

## Goal
Boost trust by pushing **closed trades** to third-party trackers (e.g., Myfxbook) after a safe delay.

## Scope
* Background job that watches for newly closed trades and posts them.
* Pluggable adapter interface; start with webhook/export file.

## Required Deliverables

```
backend/app/trust/trace_adapters.py   # interface + stub adapters
backend/app/trust/tracer.py           # enqueue_closed_trade(trade_id), worker
backend/schedulers/trace_worker.py    # cron/queue consumer
```

## Dependency
Trade schema & close events from your store (migrated in PR-016, modeled after `DemoNoStochRSI.py`).

## Security Requirements
* Strip client identifiers; delay publish until after exit.

## Telemetry
* `trust_traces_pushed_total{adapter}` (counter by adapter type)
* `trust_trace_fail_total` (counter for failures)

## Tests
* Trade closes → queued → posted
* Failure → retry/backoff

---

# CURRENT STATE ANALYSIS

## ❌ **Missing Files** (All 3 Required Deliverables)

```
❌ backend/app/trust/trace_adapters.py      NOT FOUND
❌ backend/app/trust/tracer.py              NOT FOUND
❌ backend/schedulers/trace_worker.py       NOT FOUND
```

### What Exists in /backend/app/trust/ (Different PR)

```
⚠️  graph.py         (Trust scoring - PR-049)
⚠️  models.py        (Risk Controls - Old PR-048, being replaced)
⚠️  routes.py        (Risk Controls - Old PR-048, being replaced)
⚠️  service.py       (Risk Controls - Old PR-048, being replaced)
```

**Note**: Old PR-048 (Risk Controls) docs are still in `/docs/prs/`. These should be **archived or removed** since that PR is no longer in the plan.

## ❌ **Missing Tests**

```
❌ backend/tests/test_pr_048_auto_trace.py  NOT FOUND

Current (Incorrect):
⚠️  backend/tests/test_pr_048_risk_controls.py  (804 lines, old PR, should be deleted)
```

## ❌ **Old Documentation** (Needs Replacement)

```
Found in /docs/prs/:
⚠️  PR-048-IMPLEMENTATION-PLAN.md            (OLD: Risk Controls)
⚠️  PR-048-IMPLEMENTATION-COMPLETE.md        (OLD: Risk Controls)
⚠️  PR-048-ACCEPTANCE-CRITERIA.md            (OLD: Risk Controls)
⚠️  PR-048-BUSINESS-IMPACT.md                (OLD: Risk Controls)
```

These 4 files describe the OLD PR-048 (Risk Controls). They need to be replaced with correct Auto-Trace documentation.

---

# IMPLEMENTATION STATUS BREAKDOWN

## 1. Backend Logic: trace_adapters.py

**Status**: ❌ NOT STARTED

**Required Features**:
- [ ] Abstract `TraceAdapter` base class
- [ ] Methods: `async def post_trade(trade_id, stripped_data) -> bool`
- [ ] Retry configuration (backoff, max attempts)
- [ ] Error handling and logging
- [ ] Adapter registry system

**Stub Adapters Needed**:
- [ ] `MyfxbookAdapter` - webhook posting to Myfxbook
- [ ] `FileExportAdapter` - export to local/S3 file
- [ ] `WebhookAdapter` - generic webhook posting

**Dependencies**:
- ✅ Trade models (exists from PR-016)
- ✅ Signal models (exists from PR-021)
- ✅ Approval models (exists from PR-022)

---

## 2. Backend Worker: tracer.py

**Status**: ❌ NOT STARTED

**Required Features**:
- [ ] `TraceQueue` class (enqueue pending trades)
- [ ] `enqueue_closed_trade(trade_id, adapter_type)` function
- [ ] Trade lifecycle watcher
- [ ] T+X delay enforcement (configurable, e.g., T+5 minutes)
- [ ] Payload stripping (remove client identifiers)
- [ ] Error handling and retry logic

**Business Logic**:
1. Listen for trade close events
2. Wait T+X delay after close
3. Strip PII/client info from trade data
4. Queue for posting
5. Post to configured adapters
6. Handle failures with exponential backoff

**Dependencies**:
- ✅ Redis (exists from PR-006 pattern)
- ✅ Celery (exists from project setup)
- ✅ Trade store (PR-016)

---

## 3. Background Job: trace_worker.py

**Status**: ❌ NOT STARTED

**Required Features**:
- [ ] Celery periodic task (runs on schedule, e.g., every 5 minutes)
- [ ] Queue consumer logic
- [ ] Adapter invocation
- [ ] Retry policy (exponential backoff: 5s, 30s, 5m, 1h)
- [ ] Error logging with full context
- [ ] Telemetry recording

**Job Flow**:
1. Fetch pending traces from queue
2. For each trace:
   - Check if T+X delay satisfied
   - Attempt post via adapter
   - On success: delete from queue, record metric
   - On failure: increment retry count, schedule backoff, record metric

**Env Config**:
```
TRACE_DELAY_MINUTES=5           # T+5 after close before posting
TRACE_RETRY_MAX_ATTEMPTS=5
TRACE_RETRY_BACKOFF_BASE=5      # seconds
TRACE_BATCH_SIZE=10             # per job run
TRACE_ENABLED_ADAPTERS=myfxbook,file  # which adapters to use
```

---

## 4. Tests: test_pr_048_auto_trace.py

**Status**: ❌ NOT STARTED

**Required Test Suites** (target ≥90% coverage):

### Suite 1: Adapter Interface
- [ ] `test_myfxbook_adapter_valid_post()` - Happy path
- [ ] `test_myfxbook_adapter_network_error()` - Retry on failure
- [ ] `test_webhook_adapter_custom_endpoint()` - Generic webhook
- [ ] `test_file_export_adapter_s3()` - Export to S3
- [ ] `test_adapter_pii_stripping()` - Client data removed

### Suite 2: Tracer Queue Logic
- [ ] `test_enqueue_closed_trade()` - Add to queue
- [ ] `test_delay_enforcement()` - T+5 prevents immediate posting
- [ ] `test_delay_enforcement_satisfied()` - Posting after delay
- [ ] `test_strip_client_identifiers()` - Remove email, names, account IDs
- [ ] `test_payload_validation()` - Trade data schema

### Suite 3: Worker Job
- [ ] `test_worker_processes_single_trade()` - Basic flow
- [ ] `test_worker_batch_processes()` - Multiple trades
- [ ] `test_worker_retry_backoff()` - 5s, 30s, 5m, 1h delays
- [ ] `test_worker_skips_not_ready()` - Delay not yet satisfied
- [ ] `test_worker_max_retries()` - Gives up after 5 attempts
- [ ] `test_worker_success_deletes_queue()` - Cleanup

### Suite 4: Telemetry & Error Handling
- [ ] `test_telemetry_traces_pushed_total()` - Counter by adapter
- [ ] `test_telemetry_trace_fail_total()` - Failure counter
- [ ] `test_error_logging_full_context()` - Include trade_id, adapter, error
- [ ] `test_no_pii_in_logs()` - PII redacted from output

### Suite 5: Integration
- [ ] `test_trade_close_event_triggers_queue()` - End-to-end
- [ ] `test_full_flow_with_delay_retry()` - Complete scenario
- [ ] `test_multiple_adapters_same_trade()` - Fan-out posting

**Coverage Target**: ≥90% of trace module

---

# DOCUMENTATION STATUS

## ❌ **Documentation Needs Replacement**

The following 4 files in `/docs/prs/` currently describe the OLD Risk Controls PR-048:

1. **PR-048-IMPLEMENTATION-PLAN.md** (459 lines)
   - Current: Risk Controls database schema & endpoints
   - Needed: Auto-Trace architecture, adapter pattern, queue design

2. **PR-048-ACCEPTANCE-CRITERIA.md**
   - Current: Risk profile CRUD, exposure calculation tests
   - Needed: Trade close→queue→post, delay enforcement, retry/backoff

3. **PR-048-IMPLEMENTATION-COMPLETE.md**
   - Current: Risk Controls implementation verification
   - Needed: Auto-Trace feature checklist

4. **PR-048-BUSINESS-IMPACT.md**
   - Current: Risk management business value
   - Needed: Trust/transparency business value of 3rd-party tracing

---

# DEPENDENCIES - VERIFICATION

## ✅ **All Dependencies Satisfied**

Needed for PR-048 Auto-Trace:

```
✅ PR-016: Trade Store Schema & Close Events
   - Provides: Trade model, close event system, schema
   - Status: Implemented

✅ PR-006: Redis & Celery Setup
   - Provides: Message queue, periodic job infrastructure
   - Status: Implemented

✅ PR-009: Structured Logging & Telemetry
   - Provides: Prometheus metrics, JSON logging
   - Status: Implemented

✅ Redis client library
   - Status: Installed

✅ Celery framework
   - Status: Installed & configured
```

**Recommendation**: PR-048 can proceed immediately. No blocking dependencies.

---

# NEXT STEPS

## 🎯 **To Complete PR-048 Implementation**

### Phase 1: Remove Old Files (Cleanup)
1. Delete `/backend/app/risk/` directory (old PR-048 Risk Controls)
2. Delete `/backend/tests/test_pr_048_risk_controls.py`
3. Archive `/docs/prs/PR-048-*.md` (to `/docs/archive/PR-048-OLD-RISK-CONTROLS/`)

### Phase 2: Create Documentation (Plan)
1. Create new `/docs/prs/PR-048-IMPLEMENTATION-PLAN.md` (Auto-Trace spec)
2. Create new `/docs/prs/PR-048-ACCEPTANCE-CRITERIA.md` (test scenarios)
3. Create new `/docs/prs/PR-048-BUSINESS-IMPACT.md` (trust value)
4. Prepare architecture diagram (adapters, queue, worker flow)

### Phase 3: Implement Backend (Code)
1. Create `/backend/app/trust/trace_adapters.py` (adapter interface + stubs)
2. Create `/backend/app/trust/tracer.py` (queue & enqueue logic)
3. Create `/backend/schedulers/trace_worker.py` (celery task)
4. Create `/backend/app/trust/models.py` (queue DB model if needed)
5. Add migration if DB changes needed

### Phase 4: Implement Tests (Test)
1. Create `/backend/tests/test_pr_048_auto_trace.py` (35+ tests)
2. Run coverage: target ≥90%
3. Verify all acceptance criteria covered

### Phase 5: Document & Verify (Completion)
1. Create `/docs/prs/PR-048-IMPLEMENTATION-COMPLETE.md` (verification checklist)
2. Create verification script: `/scripts/verify/verify-pr-048.sh`
3. Verify GitHub Actions CI/CD passes
4. Verify local tests: `make test-local`

---

# EFFORT ESTIMATE

| Phase | Task | Hours | Status |
|-------|------|-------|--------|
| 1 | Cleanup old files | 0.5 | TODO |
| 2 | Documentation & planning | 2 | TODO |
| 3 | Backend implementation | 6-8 | TODO |
| 4 | Tests & coverage | 3-4 | TODO |
| 5 | Verification & CI/CD | 1-2 | TODO |
| **Total** | | **12-17 hours** | **NOT STARTED** |

**Complexity**: Medium-High (adapter pattern, async queue management, retry logic)

---

# SUMMARY

## Current Status

```
PR-048 (Auto-Trace to Third-Party Trackers): ❌ NOT IMPLEMENTED

✅ Dependencies: All satisfied (PR-016, PR-006, PR-009)
❌ Implementation: 0% complete (3 files not yet created)
❌ Tests: 0% complete (test suite not yet written)
❌ Documentation: Needs replacement (old Risk Controls docs present)
```

## Readiness to Start

**Ready to Start**: ✅ YES
- All dependencies implemented
- No blocking issues
- Clear specification in Master PR document
- Can begin Phase 1 (cleanup) immediately

## Recommendation

**Next Action**:
1. Confirm old Risk Controls PR-048 should be archived
2. Begin Phase 1 cleanup (remove old files)
3. Proceed with Phase 2 (documentation)
4. Implement backend + tests (Phase 3-4)

---

**Report Generated**: November 1, 2025
**Status**: ⚠️ **READY FOR IMPLEMENTATION**
**Master PR Document**: Final_Master_Prs.md (lines 2247-2280)
**Next Action**: Await confirmation to begin implementation
