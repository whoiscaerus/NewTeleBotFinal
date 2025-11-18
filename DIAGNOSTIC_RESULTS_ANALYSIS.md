# ✅ CI/CD TEST DIAGNOSTIC RESULTS - ANALYSIS

## Status: ⚠️ PARTIAL RUN - Tests stopped at ~8% completion

The GitHub Actions diagnostic workflow ran but stopped early. Here's what we can see:

---

## RESULTS FROM AVAILABLE OUTPUT

### Tests That PASSED (Confirmed Working):
- ✅ **Backtest Adapters** (14/14 tests) - 100% PASSING
  - CSV adapter tests (valid files, filtering, validation, error handling)
  - Parquet adapter tests (valid files, timezone handling, schema validation)

- ✅ **Backtest Runner** (19/19 tests) - 100% PASSING
  - Position PnL calculations (long & short)
  - Stop loss & take profit triggers
  - Report metrics (Sharpe, Sortino, Calmar ratios)
  - Export formats (HTML, CSV, JSON)

- ✅ **Integration Tests** (27/27 tests) - 100% PASSING
  - Position tracking & acknowledgment
  - Close commands polling
  - Position monitoring & SL/TP breach detection
  - EA poll redaction & data privacy

- ✅ **Marketing Scheduler** (27/27 tests) - 100% PASSING
  - Scheduler initialization & execution
  - Interval management

- ✅ **Cache Tests** (54/54 tests) - 100% PASSING
  - Candle cache operations
  - Signal publish cache
  - Concurrent operations
  - Large values & special characters

### Tests That FAILED (35 confirmed failures):

**AI Analyst Tests** (20 failures):
- ❌ `test_get_analyst_status`
- ❌ `test_toggle_disable_via_api`
- ❌ `test_toggle_enable_via_api`
- ❌ `test_toggle_owner_only_flag`
- ❌ `test_toggle_persists_across_sessions`
- ❌ `test_correlations_computed`
- ❌ `test_data_citations_complete`
- ❌ `test_extreme_values_handled`
- ❌ `test_instruments_covered`
- ❌ `test_narrative_coherence`
- ❌ `test_no_pii_leaked`
- ❌ `test_outlook_api_endpoint_owner_only`
- ❌ `test_outlook_includes_data_citations`
- ❌ `test_timestamps_utc`
- ❌ `test_volatility_zones_calculated`
- ❌ `test_zero_trades_handled`
- ❌ `test_scheduler_generates_when_enabled`
- ❌ `test_scheduler_increments_metrics`
- ❌ `test_scheduler_owner_only_sends_to_owner`
- ❌ `test_scheduler_public_sends_to_all`

**AI Routes Tests** (7 failures):
- ❌ `test_chat_new_session`
- ❌ `test_chat_with_session_id`
- ❌ `test_escalate_session`
- ❌ `test_get_session`
- ❌ `test_list_sessions`
- ❌ `test_list_sessions_with_pagination`
- ❌ `test_rate_limiting_chat`

**Attribution Tests** (1 failure):
- ❌ `test_compute_attribution_ppo_gold_success`

**Auth Tests** (1 failure):
- ❌ `test_me_with_deleted_user`

**Copy Tests** (5 failures):
- ❌ `test_create_copy_entry_with_variants`
- ❌ `test_cannot_create_duplicate_key`
- ❌ `test_create_entry_without_variants`
- ❌ `test_list_entries_with_type_filter`
- ❌ `test_list_entries_with_status_filter`

### Tests With ERRORS (15 confirmed errors):

**Copy Tests** (all 15 errors):
- ⚠️ `test_update_entry_metadata`
- ⚠️ `test_update_entry_status`
- ⚠️ `test_add_variant_to_existing_entry`
- ⚠️ `test_add_ab_test_variant`
- ⚠️ `test_resolve_copy_basic`
- ⚠️ `test_resolve_copy_locale_fallback`
- ⚠️ `test_resolve_copy_missing_locale_falls_back_to_english`
- ⚠️ `test_resolve_copy_draft_entries_not_returned`
- ⚠️ `test_ab_test_impression_tracking`
- ⚠️ `test_ab_test_conversion_tracking`
- ⚠️ `test_ab_test_variant_selection`
- ⚠️ `test_delete_entry_cascades_to_variants`
- ⚠️ `test_copy_entry_default_variant_property`
- ⚠️ `test_copy_entry_get_variant_method`
- ⚠️ `test_resolve_copy_multiple_keys_mixed_results`

### Tests with TIMEOUTS:

- ⏱️ `test_dashboard_websocket_connect_success` (120s timeout)

---

## SUMMARY SO FAR

| Category | Count | Status |
|----------|-------|--------|
| Tests Run | ~800 | 🔄 Partial |
| Passed | 147+ | ✅ |
| Failed | 35 | ❌ |
| Errors | 15 | ⚠️ |
| Timeout | 1 | ⏱️ |
| **Total Visible** | ~198 | |

### Pass Rate (of completed tests): ~74%

---

## IDENTIFIED ISSUES

### Issue #1: Copy Module Problems (15 tests failing/erroring)
**Root Cause:** Likely database or schema issue with copy_entries/copy_variants tables
**Affected:** `test_copy.py` - 20 of 27 tests affected
**Fix Priority:** HIGH - This module is completely broken

### Issue #2: AI Analyst & Routes Problems (27 tests failing)
**Root Cause:** Unknown dependency issue (AI services, database, or async fixture problem)
**Affected:** `test_ai_analyst.py` (20 failures), `test_ai_routes.py` (7 failures)
**Fix Priority:** HIGH - Large number of failures

### Issue #3: WebSocket Timeout
**Root Cause:** Test takes longer than 120 seconds
**Affected:** `test_dashboard_websocket_connect_success`
**Fix Priority:** MEDIUM - Single test, timeout related

### Issue #4: Auth Test Failure
**Root Cause:** Unknown
**Affected:** `test_me_with_deleted_user`
**Fix Priority:** LOW - Single test

---

## WHAT WE KNOW WORKS (147+ tests passing):

✅ All backtest functionality
✅ All integration tests
✅ All cache operations
✅ Most marketing scheduler tests

---

## NEXT STEPS

The test run was cut off at ~8% completion (~800 tests). We need to:

1. **Re-run the diagnostic** with increased timeout (currently 120s per test)
2. **Check if there are resource constraints** in GitHub Actions
3. **Fix the identified issues** (Copy module, AI services, WebSocket)
4. **Run targeted tests** for the failing modules

---

## Files Available

- `full_test_run_output.log` - Partial test output (560 lines)
- `collection_output.txt` - Test collection metadata

**Note:** JSON report file was not generated (test run incomplete)
