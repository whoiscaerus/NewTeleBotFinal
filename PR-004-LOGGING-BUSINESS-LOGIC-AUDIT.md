# PR-004: AuthN/AuthZ Core - Comprehensive Business Logic Audit

**Audit Date**: November 3, 2025
**Status**: 🟡 PARTIAL - 55 existing tests, identified 35+ gaps
**Coverage**: ~60% - Missing critical business logic and edge cases

## Executive Summary

PR-004 implements authentication and authorization with JWT tokens and Argon2id password hashing. Current test suite covers **55 tests** validating core functionality, but **35+ critical gaps** exist in:

1. **Endpoint Integration Tests** - API routes not fully tested (POST /login, POST /register, GET /me)
2. **Session/Token Lifecycle** - Token refresh (planned), multi-device sessions, token revocation
3. **Brute-Force Protection** - Decorator applied but behavior not validated, throttle timing
4. **Database Constraints** - Cascade delete behavior, foreign key integrity
5. **Error Edge Cases** - SQL injection attempts, malformed requests, race conditions
6. **Concurrent Operations** - Multiple simultaneous logins, token validation under load
7. **Security Validation** - Password policy enforcement details, rate limiting, IP tracking
8. **RBAC Enforcement** - Role hierarchy (owner > admin > user), permission cascading
9. **Last Login Timestamp** - Updated on successful auth but not tested for updates
10. **Telegram Integration** - telegram_user_id deduplication not fully tested

## Implementation Architecture

### Core Components

```
backend/app/auth/
├── models.py              # User model with role enum, timestamps
├── service.py             # AuthService (create, auth, verify, mint JWT)
├── jwt_handler.py         # JWTHandler (token creation/validation)
├── routes.py              # FastAPI endpoints (/register, /login, /me)
├── rbac.py                # RBAC utilities (require_roles decorator)
├── utils.py               # Helper functions (hash_password, verify_password, create_access_token, decode_token)
├── schemas.py             # Pydantic models (LoginRequest, UserResponse)
└── dependencies.py        # FastAPI dependency functions (get_current_user)
```

### Key Business Rules

**User Model**:
- Unique email, unique telegram_user_id (nullable)
- Role: owner, admin, user (default: user)
- Timestamps: created_at, updated_at, last_login_at

**Password Security**:
- Argon2id hashing (memory/time cost from settings)
- Minimum 8 characters
- Case-sensitive verification
- Handles invalid hashes gracefully (returns False, no crash)

**JWT Claims**:
- sub: user_id
- role: user role
- exp: expiration (15 minutes default)
- iat: issued at
- Optional: telegram_user_id, aud (audience)

**Rate Limiting & Throttle**:
- @rate_limit(10 req/min) on /register, /login
- @abuse_throttle(5 failures = 5 min lockout) on /login
- Per-IP tracking (simple in-memory, Redis later)

**RBAC**:
- Owner > Admin > User in permission hierarchy
- require_roles(*roles) decorator for protected endpoints
- Uniform error messages on auth failure

## Existing Test Coverage (55 tests)

### Test Classes & Coverage

```
✅ TestPasswordHashing (6 tests)
   - Argon2id algorithm verification
   - Different hash per password (salt)
   - Case sensitivity
   - Invalid hash handling
   - Empty string edge case
   Coverage: 100% for hash_password() and verify_password()

✅ TestJWTTokens (10 tests)
   - Valid JWT structure (3-part)
   - Subject claim presence
   - Role claim presence
   - Expiration & issued-at claims
   - Custom expiry delta
   - Token decoding success/failure
   - Expired token rejection
   - Tampered token rejection
   - Malformed token handling
   Coverage: 100% for create_access_token() and decode_token()

✅ TestAuthServiceUserCreation (8 tests)
   - Valid user creation
   - Password hashing (not plaintext)
   - Duplicate email rejection
   - Duplicate telegram_user_id rejection
   - Weak password rejection
   - Telegram ID inclusion
   - Default role (user)
   - Custom role (admin, owner)
   Coverage: 100% for create_user()

✅ TestAuthServiceVerifyPassword (3 tests)
   - Correct password verification
   - Incorrect password rejection
   - Invalid hash format handling
   Coverage: 100% for verify_password()

✅ TestAuthServiceAuthentication (4 tests)
   - Valid credentials authentication
   - Wrong password rejection
   - Nonexistent email rejection
   - Case-sensitive email matching (documents behavior)
   Coverage: 75% for authenticate_user() [missing last_login_at update validation]

✅ TestAuthServiceIntegration (3 tests)
   - Full signup → login → JWT flow
   - User persistence in database
   - Multiple independent users
   Coverage: 80% for integration scenarios

✅ TestBruteForceThrottle (4 tests)
   - Decorator applied to login endpoint
   - Failed login returns 401
   - Correct login returns 200 with token
   - Multiple failed attempts return 401
   Coverage: 50% [decorator applied but throttle behavior/timing not validated]

✅ TestAccountLockout (3 tests)
   - AuthService exists and initialized
   - Failed authentication returns None
   - Successful authentication returns user
   Coverage: 50% [lockout mechanism not implemented/tested]

✅ TestRBACDecorator (3 tests)
   - JWT contains role claim
   - User model has role field
   - Default role is user
   Coverage: 60% [permission enforcement not tested]

✅ TestJWTClaimsValidation (9 tests)
   - Subject claim presence
   - Role claim presence
   - Expiration claim presence
   - Issued-at claim presence
   - iat < exp invariant
   - Expired token validation
   - Tampered signature rejection
   - Malformed token rejection
   - decode_token extracts user ID correctly
   Coverage: 95% for JWT claims

✅ TestAuthWorkflow (3 tests)
   - Complete auth workflow (create → auth → token → decode)
   - Invalid credentials prevent token issuance
   - Expired token denied access
   Coverage: 85% for complete workflows

Total: 55 tests covering core auth logic
```

## Gap Analysis (35+ Missing Tests)

### Category 1: Endpoint Integration (10 gaps)

**Gap 1.1: POST /register endpoint contract** ❌
- **Current**: No test validates endpoint exists and accepts request
- **Missing**: Test response schema (id, email, role in response)
- **Impact**: Cannot verify registration API contract
- **Fix**: `test_register_endpoint_returns_201_with_user_object`

**Gap 1.2: POST /register rate limiting (10/min)** ❌
- **Current**: No test validates rate limit behavior on /register
- **Missing**: 11th request should return 429
- **Impact**: Attackers can brute-force registration endpoint
- **Fix**: `test_register_rate_limit_429_after_10_requests`

**Gap 1.3: POST /login endpoint returns token** ❌
- **Current**: Tested in TestBruteForceThrottle but not detailed
- **Missing**: Verify response schema (access_token, token_type, expires_in)
- **Impact**: Frontend might not parse response correctly
- **Fix**: `test_login_endpoint_returns_access_token_with_schema`

**Gap 1.4: GET /me with valid token** ❌
- **Current**: No test
- **Missing**: GET /me should return user profile (id, email, role)
- **Impact**: Cannot verify authenticated user retrieval
- **Fix**: `test_get_me_with_valid_token_returns_user_profile`

**Gap 1.5: GET /me with invalid token returns 401** ❌
- **Current**: No test
- **Missing**: Invalid/expired token should return 401
- **Impact**: Expired sessions not handled correctly
- **Fix**: `test_get_me_invalid_token_returns_401`

**Gap 1.6: GET /me without token returns 401** ❌
- **Current**: No test
- **Missing**: Missing Authorization header should return 401
- **Impact**: Unauthenticated access not blocked
- **Fix**: `test_get_me_no_token_returns_401`

**Gap 1.7: Register with duplicate email returns 400** ❌
- **Current**: Service method tested, endpoint not tested
- **Missing**: POST /register twice with same email → 400
- **Impact**: Duplicate registrations possible via API
- **Fix**: `test_register_duplicate_email_returns_400`

**Gap 1.8: Register with weak password returns 422** ❌
- **Current**: Service tested, endpoint validation not tested
- **Missing**: POST /register with <8 char password → 422
- **Impact**: Weak passwords accepted via API
- **Fix**: `test_register_weak_password_returns_422_with_validation_error`

**Gap 1.9: Login with missing email field returns 422** ❌
- **Current**: No test
- **Missing**: POST /login missing email field → 422 with error details
- **Impact**: Invalid requests not caught
- **Fix**: `test_login_missing_email_returns_422_validation_error`

**Gap 1.10: Login with missing password field returns 422** ❌
- **Current**: No test
- **Missing**: POST /login missing password → 422
- **Impact**: Invalid requests not caught
- **Fix**: `test_login_missing_password_returns_422_validation_error`

### Category 2: Session & Token Lifecycle (8 gaps)

**Gap 2.1: Last login timestamp updated on successful auth** ❌
- **Current**: Service updates last_login_at but not tested
- **Missing**: Verify last_login_at changes after authenticate_user()
- **Impact**: User login history lost
- **Fix**: `test_authenticate_user_updates_last_login_timestamp`

**Gap 2.2: Multiple logins generate unique tokens** ❌
- **Current**: No test
- **Missing**: Login same user twice → different tokens
- **Impact**: Same token issued for multiple logins (session hijack risk)
- **Fix**: `test_multiple_logins_generate_different_tokens`

**Gap 2.3: Token contains all required claims** ❌
- **Current**: Individual claims tested, not all together
- **Missing**: Single token decode validates all claims present
- **Impact**: Missing claims not detected
- **Fix**: `test_token_contains_all_required_claims_together`

**Gap 2.4: Token algorithm is HS256 (or configured algorithm)** ❌
- **Current**: No test validates algorithm
- **Missing**: JWT header has correct algorithm
- **Impact**: Wrong algorithm accepted
- **Fix**: `test_token_uses_correct_algorithm`

**Gap 2.5: Token audience claim (aud) when provided** ❌
- **Current**: No test for audience validation
- **Missing**: Token with aud claim validates correctly
- **Impact**: Audience validation missing
- **Fix**: `test_token_with_audience_claim_validated`

**Gap 2.6: Concurrent token validation under load** ❌
- **Current**: No test
- **Missing**: 50 simultaneous decode_token() calls succeed
- **Impact**: Thread safety not validated
- **Fix**: `test_concurrent_token_validation_thread_safe`

**Gap 2.7: Token expiration time calculation** ❌
- **Current**: Tested but not with different settings
- **Missing**: Expiration respects JWT_EXPIRATION_HOURS setting
- **Impact**: Token TTL incorrect if settings change
- **Fix**: `test_token_expiration_respects_settings`

**Gap 2.8: User ID correctly extracted from token** ❌
- **Current**: Tested but as part of larger flow
- **Missing**: decode_token() directly returns user ID in 'sub'
- **Impact**: User ID extraction can fail silently
- **Fix**: `test_decode_token_sub_claim_matches_user_id`

### Category 3: Brute-Force & Throttle (7 gaps)

**Gap 3.1: Failed login increments counter per IP** ❌
- **Current**: Decorator exists, behavior not tested
- **Missing**: Failed attempts tracked and incremented per IP
- **Impact**: Brute-force protection not working
- **Fix**: `test_abuse_throttle_increments_counter_per_ip`

**Gap 3.2: 5 failed attempts trigger throttle** ❌
- **Current**: Tested returns 401, but not that 5th triggers throttle
- **Missing**: 5th failed attempt should start returning 429
- **Impact**: After 5 failures, user can continue trying
- **Fix**: `test_abuse_throttle_returns_429_after_5_failures`

**Gap 3.3: Throttle lockout duration (300 seconds)** ❌
- **Current**: No test validates lockout timing
- **Missing**: After lockout, no attempts allowed for 5 minutes
- **Impact**: Lockout time not enforced
- **Fix**: `test_abuse_throttle_lockout_duration_300_seconds`

**Gap 3.4: Throttle counter resets after 5 minutes** ❌
- **Current**: No test
- **Missing**: After lockout expires, counter resets
- **Impact**: Lock persists indefinitely
- **Fix**: `test_abuse_throttle_counter_resets_after_lockout_expires`

**Gap 3.5: Successful login resets throttle counter** ❌
- **Current**: No test
- **Missing**: After successful login, counter = 0
- **Impact**: Lockout persists even after correct password
- **Fix**: `test_abuse_throttle_counter_resets_on_successful_login`

**Gap 3.6: Different IPs have independent throttle counters** ❌
- **Current**: No test
- **Missing**: IP1 fails 5 times (locked), IP2 can still login
- **Impact**: Throttling affects other users
- **Fix**: `test_abuse_throttle_independent_per_ip`

**Gap 3.7: Uniform error messages on all failures** ❌
- **Current**: No test validates message consistency
- **Missing**: Wrong password & nonexistent user both return same message
- **Impact**: Email enumeration attack possible
- **Fix**: `test_login_uniform_error_message_all_failures`

### Category 4: Database & Persistence (6 gaps)

**Gap 4.1: User cascade delete behavior** ❌
- **Current**: No test
- **Missing**: When user deleted, related records handled correctly
- **Impact**: Orphaned records possible
- **Fix**: `test_user_cascade_delete_behavior`

**Gap 4.2: Email uniqueness enforced at DB level** ❌
- **Current**: Service check exists, DB constraint not tested
- **Missing**: Direct duplicate insert fails at DB
- **Impact**: Race condition could create duplicates
- **Fix**: `test_email_unique_constraint_enforced_by_db`

**Gap 4.3: Telegram ID uniqueness enforced at DB level** ❌
- **Current**: Service check exists, constraint not tested
- **Missing**: Direct duplicate insert fails at DB
- **Impact**: Race condition could create duplicates
- **Fix**: `test_telegram_id_unique_constraint_enforced_by_db`

**Gap 4.4: User.id UUID generation** ❌
- **Current**: No test validates UUID v4 format
- **Missing**: User ID is valid UUIDv4 string
- **Impact**: Invalid ID format possible
- **Fix**: `test_user_id_is_valid_uuid_v4`

**Gap 4.5: Email stored lowercase (if normalized)** ❌
- **Current**: Tested as-is, but no test for normalization
- **Missing**: Test if emails normalized to lowercase
- **Impact**: Case sensitivity could cause duplicates (Test@example.com vs test@example.com)
- **Fix**: `test_email_normalization_consistency`

**Gap 4.6: Timestamp precision (UTC vs local)** ❌
- **Current**: No test validates timezone
- **Missing**: Timestamps in UTC, never local time
- **Impact**: Timezone confusion, wrong audit trails
- **Fix**: `test_all_timestamps_stored_in_utc`

### Category 5: Error Edge Cases (6 gaps)

**Gap 5.1: SQL injection in email field** ❌
- **Current**: No test
- **Missing**: Email like `" OR "1"="1` handled safely
- **Impact**: SQL injection vulnerability
- **Fix**: `test_create_user_sql_injection_email_rejected`

**Gap 5.2: XSS payload in email** ❌
- **Current**: No test
- **Missing**: Email with `<script>alert(1)</script>` handled
- **Impact**: XSS vulnerability
- **Fix**: `test_create_user_xss_payload_email_rejected`

**Gap 5.3: Very long password (10KB+)** ❌
- **Current**: No test
- **Missing**: Large password hashed without DoS
- **Impact**: Hash computation DoS possible
- **Fix**: `test_hash_password_very_long_input`

**Gap 5.4: Database connection failure during create_user** ❌
- **Current**: No test
- **Missing**: DB error propagates or handles gracefully
- **Impact**: Unhandled exception crashes request
- **Fix**: `test_create_user_database_connection_failure`

**Gap 5.5: Null/None values in optional fields** ❌
- **Current**: Partially tested (telegram_user_id)
- **Missing**: All optional fields (telegram_user_id, last_login_at) handle None
- **Impact**: Unexpected errors on None values
- **Fix**: `test_user_optional_fields_allow_none`

**Gap 5.6: Unicode characters in password** ❌
- **Current**: No test
- **Missing**: Password with émojis, Chinese characters works
- **Impact**: Unicode passwords rejected
- **Fix**: `test_hash_password_unicode_characters`

### Category 6: RBAC & Permission Enforcement (5 gaps)

**Gap 6.1: Owner can access all endpoints** ❌
- **Current**: No test
- **Missing**: Owner token granted access to all protected routes
- **Impact**: Owner permissions not working
- **Fix**: `test_rbac_owner_can_access_all_endpoints`

**Gap 6.2: Admin can access most but not owner-only** ❌
- **Current**: No test
- **Missing**: Admin blocked from owner-only endpoints
- **Impact**: Permission hierarchy not enforced
- **Fix**: `test_rbac_admin_denied_owner_only_endpoint`

**Gap 6.3: User can only access personal endpoints** ❌
- **Current**: No test
- **Missing**: User blocked from admin/owner endpoints
- **Impact**: User can escalate privileges
- **Fix**: `test_rbac_user_denied_admin_endpoint`

**Gap 6.4: Role modification requires admin** ❌
- **Current**: No endpoint test
- **Missing**: Only admin/owner can change user roles
- **Impact**: Users self-promote to admin
- **Fix**: `test_rbac_only_admin_can_modify_roles`

**Gap 6.5: require_roles decorator with multiple roles** ❌
- **Current**: Decorator exists, edge cases not tested
- **Missing**: Endpoint requiring ["owner", "admin"] works correctly
- **Impact**: Complex permissions not validated
- **Fix**: `test_rbac_decorator_multiple_roles`

### Category 7: Concurrency & Race Conditions (4 gaps)

**Gap 7.1: Race condition creating same user twice** ❌
- **Current**: No test
- **Missing**: Two simultaneous create_user() calls with same email
- **Impact**: Duplicate user possible in race condition
- **Fix**: `test_race_condition_create_user_same_email`

**Gap 7.2: Race condition on last_login_at** ❌
- **Current**: No test
- **Missing**: Concurrent authenticate_user() calls update correctly
- **Impact**: Last login time incorrect
- **Fix**: `test_race_condition_last_login_concurrent_updates`

**Gap 7.3: Multiple simultaneous login attempts** ❌
- **Current**: No test
- **Missing**: 10 simultaneous authenticate_user() calls succeed
- **Impact**: Concurrent auth failures
- **Fix**: `test_concurrent_authentication_multiple_users`

**Gap 7.4: Token generation under high concurrency** ❌
- **Current**: No test
- **Missing**: 100 simultaneous mint_jwt() calls generate unique tokens
- **Impact**: Token uniqueness not guaranteed
- **Fix**: `test_concurrent_token_generation_uniqueness`

### Category 8: JWT Security Deep Dive (4 gaps)

**Gap 8.1: Token secret key rotation** ❌
- **Current**: No test
- **Missing**: Old token with new secret key fails
- **Impact**: Secret rotation not supported
- **Fix**: `test_token_validation_fails_with_wrong_secret_key`

**Gap 8.2: JWT algorithm confusion attack** ❌
- **Current**: No test
- **Missing**: Token claiming HS256 doesn't accept RS256
- **Impact**: Algorithm confusion vulnerability
- **Fix**: `test_jwt_algorithm_confusion_attack_prevented`

**Gap 8.3: Token with custom issuer claim** ❌
- **Current**: No test
- **Missing**: iss (issuer) claim validation
- **Impact**: Issuer not validated
- **Fix**: `test_jwt_issuer_claim_validation`

**Gap 8.4: Token with extra unrecognized claims** ❌
- **Current**: No test
- **Missing**: Token with unknown claims still decodes
- **Impact**: Unknown claims handling unclear
- **Fix**: `test_jwt_decode_ignores_unknown_claims`

---

## Summary Table

| Category | Gaps | Status |
|----------|------|--------|
| 1. Endpoint Integration | 10 | ❌ MISSING |
| 2. Session & Token Lifecycle | 8 | ❌ MISSING |
| 3. Brute-Force & Throttle | 7 | 🟡 PARTIAL |
| 4. Database & Persistence | 6 | ❌ MISSING |
| 5. Error Edge Cases | 6 | ❌ MISSING |
| 6. RBAC & Permission | 5 | ❌ MISSING |
| 7. Concurrency & Race Conditions | 4 | ❌ MISSING |
| 8. JWT Security Deep Dive | 4 | ❌ MISSING |
| **TOTAL** | **50** | **❌ CRITICAL** |

---

## Recommendations

### Priority 1: Must Implement (Business-Critical)
1. ✅ Endpoint integration tests (all 10)
2. ✅ Brute-force throttle behavior (all 7)
3. ✅ RBAC enforcement (all 5)
4. ✅ Database constraints (all 6)

### Priority 2: Should Implement (Security-Critical)
1. ✅ Error edge cases (all 6)
2. ✅ JWT security deep dive (all 4)
3. ✅ Concurrency handling (all 4)

### Priority 3: Nice to Have (Reliability)
1. ✅ Session lifecycle edge cases (all 8)

---

## Implementation Plan

**Phase 1**: Create `backend/tests/test_pr_004_auth_gaps.py` with 50 comprehensive gap tests
**Phase 2**: Run combined test suite (55 original + 50 gaps = 105 total)
**Phase 3**: Achieve 90%+ coverage on all business logic
**Phase 4**: Document findings and commit to GitHub

**Estimated Time**: 4-6 hours
**Test Count Target**: 105 total (55 + 50 new)
**Coverage Target**: 90-95%
**Expected Bugs Found**: 2-4 (edge cases, race conditions)
