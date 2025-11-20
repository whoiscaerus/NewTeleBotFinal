# PR-110 Implementation Plan: Idempotency Middleware

## 1. Overview
Implement idempotency middleware to prevent duplicate request processing, critical for trading signals and payments. This ensures that if a client retries a request (due to network timeout), the server returns the cached response instead of re-executing the logic.

## 2. Technical Specification

### Files to Create/Modify
- `backend/app/core/middleware.py`: Add `IdempotencyMiddleware` class.
- `backend/app/core/idempotency.py`: Logic for key storage/retrieval in Redis.
- `backend/app/main.py`: Register middleware.
- `backend/tests/core/test_idempotency.py`: Unit tests.

### Logic
1.  **Header Check**: Look for `Idempotency-Key` header.
2.  **Storage**: Use Redis to store `(key, user_id) -> (status_code, body, headers)`.
3.  **Expiration**: Keys expire after 24 hours.
4.  **Concurrency**: Use Redis `SETNX` (set if not exists) to handle race conditions.

### Dependencies
- Redis (already available).

## 3. Acceptance Criteria
- [ ] Requests with same `Idempotency-Key` return cached response.
- [ ] Concurrent requests with same key do not race (only one executes).
- [ ] Different users cannot reuse same key (scope by user_id).
- [ ] Keys expire after 24h.
