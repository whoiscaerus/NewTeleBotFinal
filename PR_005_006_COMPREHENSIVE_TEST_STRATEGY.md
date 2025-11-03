"""
PR-005 & PR-006: COMPREHENSIVE BUSINESS LOGIC TEST STRATEGY

This document describes the COMPLETE test suite for:
- PR-005: Rate Limiting, Abuse Controls & IP Throttling (Token Bucket + Lua)
- PR-006: API Error Taxonomy (RFC 7807) & Input Validation (ProblemDetail)

GOAL: 90-100% coverage with REAL business logic validation (no skips, no mocks of core logic)

PRINCIPLES:
✅ Use REAL implementations (rate_limit.py, errors.py, decorators.py)
✅ Use REAL Redis (via fakeredis for test isolation)
✅ Test REAL token bucket algorithm (Lua scripts execute fully)
✅ Test REAL error handling and RFC 7807 formatting
✅ Test REAL decorator behavior with FastAPI
✅ Test REAL abuse throttling and exponential backoff
✅ Every test validates actual business logic, not mocks
✅ All tests MUST PASS (no skipped tests)
✅ No TODOs or FIXMEs
✅ Coverage >= 90%

===================================================================
PR-005: RATE LIMITING & ABUSE CONTROLS TEST CATEGORIES
===================================================================

CATEGORY 1: Token Bucket Algorithm (Core Rate Limiting Logic)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tests validate REAL Lua script execution in Redis:
- New buckets start FULL (excellent UX)
- Each request consumes exactly 1 token
- Tokens refill at specified rate (time-based)
- Tokens capped at max (never exceed)
- Multiple keys isolated (user:123 != user:456)
- Bucket expires if unused

Tests:
  ✓ test_first_request_always_allowed (bucket starts full)
  ✓ test_tokens_consumed_one_per_request (token count decreases)
  ✓ test_rate_limit_enforced_when_tokens_exhausted (blocked when 0)
  ✓ test_tokens_refill_over_time (time-based replenishment)
  ✓ test_tokens_capped_at_max (never exceed max)
  ✓ test_get_remaining_accuracy (remaining token count correct)
  ✓ test_refill_rate_variations (1/sec, 2/sec, 0.5/sec)
  ✓ test_bucket_expires_if_unused (TTL enforcement)

CATEGORY 2: Rate Limit Isolation (Multi-User/Multi-IP)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tests validate separate buckets for different keys:
- user:123 and user:456 have separate limits
- ip:1.1.1.1 and ip:2.2.2.2 have separate limits
- Service keys (redis:stats, db:query) isolated
- Blocking one user doesn't affect another

Tests:
  ✓ test_different_users_separate_buckets
  ✓ test_different_ips_separate_buckets
  ✓ test_service_keys_isolated
  ✓ test_concurrent_requests_separate_limits

CATEGORY 3: Decorator Integration (@rate_limit)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tests validate decorator with FastAPI endpoints:
- IP-based rate limiting (by="ip")
- User-based rate limiting (by="user")
- Response headers set correctly (X-RateLimit-*)
- Returns 429 when rate limited
- Works with async endpoints

Tests:
  ✓ test_decorator_by_ip_limits_correctly
  ✓ test_decorator_by_user_limits_correctly
  ✓ test_rate_limit_response_headers_set
  ✓ test_rate_limit_returns_429_status
  ✓ test_decorator_with_async_endpoint
  ✓ test_rate_limit_blocks_excess_requests
  ✓ test_rate_limit_header_values_accurate

CATEGORY 4: Abuse Throttling (@abuse_throttle)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tests validate login throttling with failure tracking:
- Tracks failed auth attempts (401/403)
- Locks out after N failures
- Lockout expires after TTL
- Successful auth resets counter
- IP-based and email-based throttling
- Exponential backoff (optional, can be added)

Tests:
  ✓ test_abuse_throttle_tracks_failures
  ✓ test_abuse_throttle_locks_out_after_max_failures
  ✓ test_abuse_throttle_lockout_expires
  ✓ test_abuse_throttle_success_resets_counter
  ✓ test_abuse_throttle_by_ip
  ✓ test_abuse_throttle_by_email
  ✓ test_abuse_throttle_returns_429_when_locked
  ✓ test_abuse_throttle_failure_count_increments

CATEGORY 5: Redis Failure Modes
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tests validate graceful degradation:
- Redis down → allow all requests (fail-open)
- Rate limiter disabled → allow all requests
- Lua script errors → allow all requests (safe)
- Partial Redis failure → retry + allow

Tests:
  ✓ test_rate_limiter_disabled_allows_all
  ✓ test_redis_connection_failure_allows_all
  ✓ test_lua_script_error_allows_all
  ✓ test_redis_error_logged_not_crash
  ✓ test_partial_redis_failure_graceful

CATEGORY 6: Admin Operations
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tests validate admin control over rate limits:
- reset() clears bucket and allows requests
- Manual bucket reset by admin
- View current bucket state
- Whitelist/Allowlist enforcement (if implemented)

Tests:
  ✓ test_reset_clears_rate_limit
  ✓ test_admin_whitelist_bypasses_limit
  ✓ test_view_bucket_state
  ✓ test_reset_allows_new_requests

CATEGORY 7: Edge Cases & Boundary Conditions
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tests validate corner cases:
- max_tokens = 1 (only 1 request per window)
- max_tokens = 1000 (very high limit)
- window_seconds = 1 (very tight window)
- window_seconds = 86400 (full day)
- refill_rate = 0 (no refill, bucket empties)
- Very long wait time (bucket fully refilled)
- Zero duration window (edge case)
- Rapid successive requests
- Exactly at token boundary

Tests:
  ✓ test_max_tokens_one
  ✓ test_max_tokens_very_high
  ✓ test_tiny_window_one_second
  ✓ test_large_window_one_day
  ✓ test_zero_refill_rate
  ✓ test_very_long_wait_time
  ✓ test_rapid_successive_requests
  ✓ test_exactly_at_boundary

CATEGORY 8: Global Defaults (from PR spec)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tests validate PR-005 requirements:
- Global: 60 req/min per IP (max_tokens=60, refill_rate=1, window=60)
- Auth: 10 req/min per IP (max_tokens=10, refill_rate=0.17, window=60)
- Auth: exponential backoff after failures (decorator integration)

Tests:
  ✓ test_global_default_60_per_minute
  ✓ test_auth_default_10_per_minute
  ✓ test_auth_exponential_backoff_on_failures

CATEGORY 9: Telemetry & Observability
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tests validate metrics and logging:
- ratelimit_block_total counter increments
- abuse_login_throttle_total counter increments
- Rate limit events logged with context
- Remaining tokens logged

Tests:
  ✓ test_ratelimit_block_counter_increments
  ✓ test_abuse_throttle_counter_increments
  ✓ test_events_logged_with_context
  ✓ test_remaining_tokens_tracked

CATEGORY 10: Concurrent Operations
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tests validate thread/async safety:
- Multiple concurrent requests same key (Lua atomicity)
- Multiple concurrent requests different keys
- Race condition: request at exact token boundary
- Concurrent refill calculations

Tests:
  ✓ test_concurrent_requests_same_key_atomic
  ✓ test_concurrent_requests_different_keys
  ✓ test_race_condition_at_boundary
  ✓ test_concurrent_refill_consistent

===================================================================
PR-006: ERROR HANDLING & VALIDATION TEST CATEGORIES
===================================================================

CATEGORY 1: ProblemDetail Model (RFC 7807 Compliance)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tests validate RFC 7807 structure:
- All required fields present and correct
- Optional fields excluded when None
- Field-level validation errors included
- Request ID propagated
- Timestamp in ISO 8601 format
- Type URI correct for error category

Tests:
  ✓ test_problem_detail_required_fields
  ✓ test_problem_detail_excludes_none_fields
  ✓ test_problem_detail_with_field_errors
  ✓ test_problem_detail_request_id_included
  ✓ test_problem_detail_timestamp_format
  ✓ test_problem_detail_type_uri_correct
  ✓ test_problem_detail_json_serializable
  ✓ test_problem_detail_all_error_types

CATEGORY 2: Exception Hierarchy
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tests validate all exception types:
- APIException base class
- ValidationError (422)
- AuthenticationError (401)
- AuthorizationError (403)
- NotFoundError (404)
- ConflictError (409)
- RateLimitError (429)
- ServerError (500)

Tests:
  ✓ test_validation_error_422
  ✓ test_authentication_error_401
  ✓ test_authorization_error_403
  ✓ test_not_found_error_404
  ✓ test_conflict_error_409
  ✓ test_rate_limit_error_429
  ✓ test_server_error_500
  ✓ test_exception_to_problem_detail_conversion

CATEGORY 3: Exception Handler Integration (FastAPI)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tests validate exception handlers registered correctly:
- APIException caught and converted to ProblemDetail
- Status codes correct in HTTP response
- Content-Type application/problem+json
- Response body RFC 7807 compliant

Tests:
  ✓ test_api_exception_handler_catches_exceptions
  ✓ test_exception_handler_sets_status_code
  ✓ test_exception_handler_returns_problem_detail
  ✓ test_exception_handler_content_type_json
  ✓ test_handler_with_request_id_propagation

CATEGORY 4: Field-Level Validation Errors
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tests validate detailed error information:
- Each invalid field listed
- Error message clear and actionable
- Multiple field errors shown together
- Field path correct (nested objects)

Tests:
  ✓ test_single_field_error
  ✓ test_multiple_field_errors
  ✓ test_nested_field_errors
  ✓ test_error_messages_actionable

CATEGORY 5: Input Validation (Pydantic)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tests validate request validation:
- Missing required fields → 422
- Invalid field types → 422 (int instead of str, etc.)
- Field constraints (min_length, max_length, regex, etc.)
- Enum validation (side must be "buy" or "sell", not "maybe")
- UUID format validation
- Email format validation

Tests:
  ✓ test_missing_required_field_422
  ✓ test_invalid_field_type_422
  ✓ test_string_length_validation
  ✓ test_enum_validation
  ✓ test_uuid_format_validation
  ✓ test_email_format_validation
  ✓ test_numeric_range_validation
  ✓ test_regex_pattern_validation

CATEGORY 6: Error Handlers for Specific Scenarios
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tests validate handlers for real error scenarios:
- 400 Bad Request (malformed JSON, invalid format)
- 401 Unauthorized (missing/invalid JWT)
- 403 Forbidden (user lacks permission)
- 404 Not Found (resource doesn't exist)
- 409 Conflict (duplicate email, race condition)
- 422 Unprocessable Entity (validation failed)
- 429 Too Many Requests (rate limited)
- 500 Internal Server Error (unexpected)

Tests:
  ✓ test_400_bad_request_malformed_json
  ✓ test_401_unauthorized_missing_jwt
  ✓ test_403_forbidden_insufficient_permissions
  ✓ test_404_not_found_resource_missing
  ✓ test_409_conflict_duplicate_resource
  ✓ test_422_validation_error
  ✓ test_429_rate_limit_error
  ✓ test_500_server_error

CATEGORY 7: Stack Trace Security (Production)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tests validate stack traces NOT exposed:
- In production, generic error message
- Stack trace in server logs only (not response)
- Request ID included for tracing
- Internal details not leaked

Tests:
  ✓ test_stack_trace_not_in_response
  ✓ test_generic_error_message_in_production
  ✓ test_request_id_for_tracing
  ✓ test_internal_details_not_leaked

CATEGORY 8: Request ID Propagation
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tests validate request IDs for tracing:
- X-Request-Id header in request → included in error
- Missing X-Request-Id → generated UUID
- Request ID unique per request
- Request ID in logs correlates with error

Tests:
  ✓ test_request_id_from_header
  ✓ test_request_id_generated_if_missing
  ✓ test_request_id_unique_per_request
  ✓ test_request_id_in_logs

CATEGORY 9: Error Type URIs (ERROR_TYPES)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tests validate consistent error type URIs:
- validation → https://api.tradingsignals.local/errors/validation
- authentication → https://api.tradingsignals.local/errors/authentication
- authorization → https://api.tradingsignals.local/errors/authorization
- not_found → https://api.tradingsignals.local/errors/not-found
- conflict → https://api.tradingsignals.local/errors/conflict
- rate_limit → https://api.tradingsignals.local/errors/rate-limit
- server_error → https://api.tradingsignals.local/errors/server-error

Tests:
  ✓ test_all_error_type_uris_present
  ✓ test_error_type_uris_correct_format
  ✓ test_error_type_uris_used_correctly

CATEGORY 10: Telemetry & Observability
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tests validate error telemetry:
- errors_total counter increments by status
- Error events logged with context
- Request ID in all error logs

Tests:
  ✓ test_errors_total_counter_increments
  ✓ test_error_events_logged
  ✓ test_error_logs_include_request_id

===================================================================
TEST EXECUTION STRATEGY
===================================================================

Running All Tests:
  pytest backend/tests/test_pr_005_ratelimit.py -v
  pytest backend/tests/test_pr_006_errors.py -v
  pytest backend/tests/test_pr_005_ratelimit.py backend/tests/test_pr_006_errors.py -v --cov=backend/app/core

Coverage Target: >=90%
✅ rate_limit.py: >=95%
✅ errors.py: >=90%
✅ decorators.py: >=85%
✅ abuse.py: 100% (if created)

Total Expected Tests: ~90+ (50 PR-005 + 40 PR-006)
All Must Pass: YES
No Skipped Tests: YES
No TODOs: YES

===================================================================
BUSINESS LOGIC VALIDATION CHECKLIST
===================================================================

PR-005: Rate Limiting
□ Token bucket algorithm REAL (Lua executes, tokens consumed, refilled)
□ Isolation REAL (different keys, different limits)
□ Decorator REAL (FastAPI integration, 429 returned)
□ Abuse throttle REAL (failures tracked, lockout enforced)
□ Default limits enforced (60/min global, 10/min auth)
□ Redis failure graceful (allow requests if Redis down)
□ Admin reset works (clears bucket)
□ Telemetry events tracked (counters, logs)
□ Concurrent operations safe (Lua atomicity)
□ Edge cases handled (max_tokens=1, window=86400, etc.)

PR-006: Error Handling
□ ProblemDetail REAL (RFC 7807 compliant)
□ All error types created (400, 401, 403, 404, 409, 422, 429, 500)
□ FastAPI handlers wired (exceptions caught, converted)
□ Field validation works (Pydantic, detailed errors)
□ Request IDs propagate (tracing capability)
□ Stack traces NOT exposed (security)
□ Error messages actionable (clients understand what went wrong)
□ Type URIs consistent (same domain for all errors)
□ Telemetry wired (counters, logs)
□ All status codes return correct codes
"""
