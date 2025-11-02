# PR-048: Auto-Trace to Third-Party Trackers - Acceptance Criteria

**PR ID**: PR-048
**Feature**: Auto-Trace to Third-Party Trackers (Post-Close)
**Domain**: Trust & Transparency
**Status**: 🟢 READY FOR TEST IMPLEMENTATION
**Last Updated**: 2025-01-15

---

## Overview

This document maps all acceptance criteria from the Master PR specification to test cases, ensuring comprehensive coverage and traceability.

---

## Acceptance Criteria → Test Mapping

### Criterion 1: Automatic Trade Posting After Safe Delay
**Goal**: Closed trades posted to trackers automatically, never before exit

**Master Spec**:
> "Create a background job that listens for trade close events. When a trade closes, enqueue it for posting to third-party trackers. Posts MUST be delayed by T+X minutes (configurable, default 5) to ensure trade is fully exited and fees calculated."

**Test Case(s)**:
- ✅ `test_delay_enforcement_prevents_early_posting` - Verify deadline calculation enforced
- ✅ `test_delay_enforcement_allows_after_deadline` - Verify posting occurs after deadline
- ✅ `test_trade_closed_event_triggers_enqueue` - Verify close event → enqueue
- ✅ `test_full_flow_trade_to_posted` - End-to-end: close → queue → post

**Coverage**: 4 tests
**Status**: Tests Created, Implementations Pending
**Verification Method**: Mock Redis sorted set by deadline, verify zrangebyscore only returns past deadline

---

### Criterion 2: Pluggable Adapter Architecture for Multiple Trackers
**Goal**: Support different tracker integrations via adapter pattern

**Master Spec**:
> "Design a pluggable adapter interface. Implement three adapters: (1) Myfxbook webhook, (2) local file export to S3, (3) generic webhook. Easy to add more adapters without changing core logic."

**Test Case(s)**:
- ✅ `test_myfxbook_adapter_posts_successfully` - Myfxbook posts trade
- ✅ `test_file_export_adapter_creates_file` - File export creates JSONL
- ✅ `test_webhook_adapter_custom_headers` - Webhook supports custom auth
- ✅ `test_multiple_adapters_both_post` - Multiple adapters called for single trade
- ✅ `test_worker_calls_all_enabled_adapters` - Worker posts to all configured

**Coverage**: 5 tests
**Status**: Tests Created, Implementations Pending
**Verification Method**: Mock HTTP, file I/O, verify adapter methods called with correct payloads

---

### Criterion 3: Exponential Backoff Retry Strategy
**Goal**: Resilient posting with smart retry scheduling

**Master Spec**:
> "If posting fails: 1st retry after 5s, 2nd after 30s, 3rd after 5m, 4th after 30m, 5th+ after 1h (capped). Max 5 retries total. Avoid thundering herd."

**Test Case(s)**:
- ✅ `test_adapter_backoff_calculation` - Verify backoff formula: 5 * 6^n capped
- ✅ `test_myfxbook_adapter_retries_on_network_error` - Verify 500 returns retriable
- ✅ `test_worker_retry_backoff_schedule` - Verify deadline scheduling
- ✅ `test_worker_gives_up_after_5_retries` - Verify max 5 attempts
- ✅ `test_network_timeout_triggers_backoff` - Timeout → retry

**Coverage**: 5 tests
**Status**: Tests Created, Implementations Pending
**Verification Method**: Assert backoff values, mock timer, verify zset deadline updates

---

### Criterion 4: Automatic PII Removal Before External Posting
**Goal**: Never expose user personally identifiable information to trackers

**Master Spec**:
> "Before posting ANY data to external trackers, strip PII: remove user_id, email, name, client_id, account details. Keep: instrument, prices, times, P&L, signal_id. Verify no PII ever sent externally."

**Test Case(s)**:
- ✅ `test_strip_pii_removes_user_identifiers` - Verify PII stripped
- ✅ `test_pii_not_in_any_external_call` - Verify external calls have no PII
- ✅ `test_no_pii_in_logs` - Verify logs don't expose PII

**Coverage**: 3 tests
**Status**: Tests Created, Implementations Pending
**Verification Method**: Compare before/after, inspect HTTP payloads, check log output

---

### Criterion 5: Telemetry & Observability Metrics
**Goal**: Full visibility into trace posting performance and failures

**Master Spec**:
> "Record Prometheus metrics: (1) trust_traces_pushed_total{adapter} - counter, (2) trust_trace_fail_total{adapter, reason} - counter, (3) trust_trace_queue_pending{adapter} - gauge, (4) trust_trace_post_duration_seconds{adapter} - histogram"

**Test Case(s)**:
- ✅ `test_telemetry_traces_pushed_counter` - Counter incremented per adapter
- ✅ `test_telemetry_trace_fail_counter` - Fail counter incremented
- ✅ `test_telemetry_queue_pending_gauge` - Queue size gauge set
- ✅ `test_worker_records_telemetry` - Worker updates all metrics

**Coverage**: 4 tests
**Status**: Tests Created, Implementations Pending
**Verification Method**: Mock Prometheus client, verify counter/gauge/histogram updates

---

### Criterion 6: Full Error Handling & Recovery
**Goal**: Graceful degradation on adapter/network failures

**Master Spec**:
> "If adapter fails (network error, auth failure, timeout), log full context (trade_id, adapter name, retry_count, error reason). Continue processing other trades. After 5 failed retries, abandon with alert."

**Test Case(s)**:
- ✅ `test_error_logging_includes_full_context` - Errors logged with trade_id, adapter, retry
- ✅ `test_malformed_adapter_response_retried` - Invalid response retried
- ✅ `test_worker_continues_on_single_adapter_failure` - One adapter fails, others proceed
- ✅ `test_alert_on_repeated_failures` - Alert after 5 retries
- ✅ `test_abandon_after_max_retries` - Trace deleted after max

**Coverage**: 5 tests
**Status**: Tests Created, Implementations Pending
**Verification Method**: Mock errors, verify logging, check queue deletion

---

### Criterion 7: Configuration & Environment Variables
**Goal**: Externalize all configuration for dev/staging/prod

**Master Spec**:
> "Support configuration via environment variables: TRACE_DELAY_MINUTES (default 5), TRACE_RETRY_MAX_ATTEMPTS (default 5), TRACE_RETRY_BACKOFF_BASE (default 5), TRACE_ENABLED_ADAPTERS (comma-sep list), MYFXBOOK_WEBHOOK_URL, MYFXBOOK_WEBHOOK_TOKEN, FILE_EXPORT_TYPE (s3|local), S3_BUCKET, WEBHOOK_ENDPOINT, WEBHOOK_AUTH_HEADER, WEBHOOK_AUTH_TOKEN"

**Test Case(s)**:
- (Coverage via integration tests - uses settings)
- ✅ `test_full_flow_trade_to_posted` - Uses configured delay
- ✅ `test_worker_calls_all_enabled_adapters` - Uses TRACE_ENABLED_ADAPTERS

**Coverage**: 2 tests (implicit)
**Status**: Tests Created, Implementations Pending
**Verification Method**: Set env vars, verify adapter initialization

---

### Criterion 8: Background Job Architecture (Celery)
**Goal**: Reliable async processing without blocking API

**Master Spec**:
> "Implement as Celery periodic task running every 5 minutes. Task retrieves pending traces from Redis, batches (max 10 per run), posts to each configured adapter, updates queue state. Handle Redis failures gracefully."

**Test Case(s)**:
- ✅ `test_worker_processes_single_trade` - Worker batch processing
- ✅ `test_worker_skips_not_ready` - Worker checks deadlines
- ✅ `test_concurrent_multiple_trades` - Concurrent batch processing

**Coverage**: 3 tests
**Status**: Tests Created, Implementations Pending
**Verification Method**: Mock Celery beat, verify task_run() every 5 min, mock Redis

---

### Criterion 9: Queue Management & TTL
**Goal**: Prevent queue memory leaks with automatic cleanup

**Master Spec**:
> "Store queue entries in Redis with 7-day TTL. If a trace remains in queue >7 days (max retries exceeded + network down), auto-delete. Monitor queue size in Prometheus gauge."

**Test Case(s)**:
- ✅ `test_enqueue_closed_trade_sets_deadline` - Verify 7-day TTL set
- ✅ `test_db_cleanup_old_queue_entries` - Verify old entries cleaned
- ✅ `test_telemetry_queue_pending_gauge` - Monitor queue size

**Coverage**: 3 tests
**Status**: Tests Created, Implementations Pending
**Verification Method**: Mock Redis expire, verify zrem on 7-day boundary

---

### Criterion 10: Integration with Trade Close Event
**Goal**: Seamless integration with existing trade lifecycle

**Master Spec**:
> "Hook into existing trade close event (from PR-016). When trade.status changes to CLOSED, immediately: (1) Check if user opted in to tracing (user.tracing_enabled), (2) Check if signal has tracing_adapters config, (3) Enqueue with adapters list, (4) Fire event to async worker."

**Test Case(s)**:
- ✅ `test_trade_closed_event_triggers_enqueue` - Event listener fires enqueue
- ✅ `test_full_flow_trade_to_posted` - End-to-end including trade model

**Coverage**: 2 tests (implicit)
**Status**: Tests Created, Implementations Pending
**Verification Method**: Publish trade close event, verify queue entries created

---

## Summary by Test Category

### Adapter Interface Tests (5)
| Test | Criterion | Status |
|------|-----------|--------|
| test_myfxbook_adapter_posts_successfully | #2, #3 | Impl Pending |
| test_myfxbook_adapter_retries_on_network_error | #3 | Impl Pending |
| test_file_export_adapter_creates_file | #2 | Impl Pending |
| test_webhook_adapter_custom_headers | #2 | Impl Pending |
| test_adapter_backoff_calculation | #3 | Impl Pending |

### Queue Management Tests (7)
| Test | Criterion | Status |
|------|-----------|--------|
| test_enqueue_closed_trade_sets_deadline | #1, #9 | Impl Pending |
| test_delay_enforcement_prevents_early_posting | #1 | Impl Pending |
| test_delay_enforcement_allows_after_deadline | #1 | Impl Pending |
| test_strip_pii_removes_user_identifiers | #4 | Impl Pending |
| test_mark_success_deletes_from_queue | #3 | Impl Pending |
| test_schedule_retry_with_backoff | #3 | Impl Pending |
| test_abandon_after_max_retries | #3, #6 | Impl Pending |

### Worker Job Tests (8)
| Test | Criterion | Status |
|------|-----------|--------|
| test_worker_processes_single_trade | #8 | Impl Pending |
| test_worker_retry_backoff_schedule | #3, #8 | Impl Pending |
| test_worker_gives_up_after_5_retries | #3, #6 | Impl Pending |
| test_worker_success_deletes_queue | #3 | Impl Pending |
| test_worker_calls_all_enabled_adapters | #2, #7 | Impl Pending |
| test_worker_skips_not_ready | #1, #8 | Impl Pending |
| test_worker_records_telemetry | #5, #8 | Impl Pending |
| test_worker_continues_on_single_adapter_failure | #6 | Impl Pending |

### Telemetry Tests (6)
| Test | Criterion | Status |
|------|-----------|--------|
| test_telemetry_traces_pushed_counter | #5 | Impl Pending |
| test_telemetry_trace_fail_counter | #5 | Impl Pending |
| test_telemetry_queue_pending_gauge | #5, #9 | Impl Pending |
| test_error_logging_includes_full_context | #6 | Impl Pending |
| test_no_pii_in_logs | #4 | Impl Pending |
| test_alert_on_repeated_failures | #6 | Impl Pending |

### Integration Tests (6)
| Test | Criterion | Status |
|------|-----------|--------|
| test_trade_closed_event_triggers_enqueue | #1, #10 | Impl Pending |
| test_full_flow_trade_to_posted | #1, #3, #7, #10 | Impl Pending |
| test_full_flow_with_retry | #1, #3, #6 | Impl Pending |
| test_multiple_adapters_both_post | #2 | Impl Pending |
| test_concurrent_multiple_trades | #8 | Impl Pending |
| test_db_cleanup_old_queue_entries | #9 | Impl Pending |

### Edge Cases & Security (5+)
| Test | Criterion | Status |
|------|-----------|--------|
| test_invalid_trade_id_rejected | #1 | Impl Pending |
| test_network_timeout_triggers_backoff | #3, #6 | Impl Pending |
| test_malformed_adapter_response_retried | #6 | Impl Pending |
| test_pii_not_in_any_external_call | #4 | Impl Pending |
| test_adapter_auth_tokens_not_logged | #4 | Impl Pending |

---

## Test Implementation Status

### Total Test Cases: 35+

**Breakdown**:
- Adapter Interface: 5 tests (14%)
- Queue Management: 7 tests (20%)
- Worker Job: 8 tests (23%)
- Telemetry: 6 tests (17%)
- Integration: 6 tests (17%)
- Edge Cases: 5+ tests (15%)

**Coverage Target**: ≥90% for trace modules
- backend/app/trust/trace_adapters.py: 350 lines → target 315+ lines covered
- backend/app/trust/tracer.py: 300 lines → target 270+ lines covered
- backend/schedulers/trace_worker.py: 350 lines → target 315+ lines covered

**Run Tests Locally**:
```bash
.venv/Scripts/python.exe -m pytest backend/tests/test_pr_048_auto_trace.py -v --cov=backend/app/trust --cov=backend/schedulers/trace_worker --cov-report=term-missing
```

**Expected Output**:
```
passed: 35+ tests
PASSED: All core scenarios covered
coverage: ≥90% across trace modules
```

---

## Criterion Coverage Verification

✅ **All 10+ Master Spec Criteria Mapped**:
1. ✅ Automatic posting after safe delay → 4 tests
2. ✅ Pluggable adapter architecture → 5 tests
3. ✅ Exponential backoff retry → 5 tests
4. ✅ PII removal → 3 tests
5. ✅ Telemetry metrics → 4 tests
6. ✅ Error handling & recovery → 5 tests
7. ✅ Configuration via env vars → 2 tests (implicit)
8. ✅ Celery background job → 3 tests
9. ✅ Queue TTL cleanup → 3 tests
10. ✅ Trade close integration → 2 tests

**Total Criterion Coverage**: 36 tests mapped (35+ unique)

---

## Success Criteria

**Phase 4 Complete When**:
- ✅ All 35+ tests created in test_pr_048_auto_trace.py
- ✅ All tests passing locally: `pytest --cov` shows ≥90%
- ✅ All 10 acceptance criteria verified by at least 1 test
- ✅ Edge cases & security scenarios covered (5+ tests)
- ✅ No test TODOs or skipped tests (all @pytest.mark.asyncio)

**Phase 5 Complete When**:
- ✅ Tests passing on GitHub Actions CI/CD
- ✅ Telemetry working (Prometheus metrics visible)
- ✅ Celery task registered and running every 5 min
- ✅ All documentation complete
- ✅ Verification script passing

---

## Next Steps

1. **Implement missing test cases** - Fill in placeholder methods with real logic
2. **Run locally** - Verify coverage ≥90%
3. **Fix any failures** - Debug and adjust code/tests
4. **Push to GitHub** - GitHub Actions runs CI/CD
5. **Verify metrics** - Check Prometheus dashboard for trace activity

---

**Document Status**: 🟢 COMPLETE & READY
**Version**: 1.0
**Last Modified**: 2025-01-15
