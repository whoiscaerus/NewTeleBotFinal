# PR-018 Phase 1: Implementation Plan

**PR**: 018 - Resilient Retries/Backoff & Telegram Error Alerts
**Date**: October 25, 2025
**Phase**: 1/5 (Planning)
**Estimated Duration**: 30 minutes (Phase 1), 4-5 hours total (Phases 2-5)

---

## 1. Executive Overview

**Goal**: Never drop a signal silently. Add production-grade retry logic with exponential backoff to the HMAC client (PR-017), and alert ops team via Telegram on persistent failures.

**Purpose**: Ensures signals aren't lost due to transient network issues. Alerts dev team immediately on systemic failures.

**Integration**:
- Wraps PR-017's HmacClient with retry logic
- Uses Telegram bot for alerts (existing capability)
- Enables PR-019 (trading loop hardening)

---

## 2. Specification Analysis

### From Master Doc (PR-018)

**Goal**: Never drop a signal silently; alert ops on persistent failures.

**Files to Deliver**:
```
backend/app/core/retry.py        # Retry/backoff logic with jitter
backend/app/ops/alerts.py        # send_owner_alert(text) for Telegram
```

**Environment Variables**:
- `MAX_RETRIES=5` (default, tunable)
- `RETRY_DELAY_SECONDS=5` (base delay for backoff)
- `OPS_TELEGRAM_CHAT_ID` (from secrets)
- `OPS_TELEGRAM_BOT_TOKEN` (from secrets)

**Telemetry** (Metrics):
- `retries_total{operation}` (counter, track retries by operation)
- `alerts_sent_total` (counter, track Telegram alerts)

**Tests**:
- Retry stops on success
- Retry alerts after exhausting attempts
- Exponential backoff with jitter

**Verification**:
- Force outbound client to fail
- Observe Telegram DM with error alert

---

## 3. Dependency Analysis

### Depends On
- ✅ **PR-017**: HmacClient (signal delivery client)
- ✅ **PR-009**: Observability (logging, metrics - already in system)
- ✅ **Telegram Bot**: Existing capability (used for signals)

### Required for
- ⏳ **PR-019**: Trading loop hardening (will use retry decorators)
- ⏳ **PR-021**: Signals API (will use retry on server endpoints)
- ⏳ **Phase 2**: Production deployment (retry required for reliability)

---

## 4. Architecture Design

### Retry Strategy

**Exponential Backoff Formula**:
```python
delay = base_delay * (multiplier ^ attempt) + jitter
delay = min(delay, max_delay)

Where:
  base_delay = RETRY_DELAY_SECONDS (5s default)
  multiplier = 2 (exponential)
  attempt = 0, 1, 2, 3, 4 (for 5 retries)
  jitter = random(0, delay * 0.1) (±10% randomness)
  max_delay = 120s (prevent infinite backoff)

Timeline:
  Attempt 0: 5s + jitter
  Attempt 1: 10s + jitter
  Attempt 2: 20s + jitter
  Attempt 3: 40s + jitter
  Attempt 4: 80s + jitter
  Total: ~155 seconds (≈2.6 minutes)
```

**Retry Logic**:
```python
with_retry(
    func=post_signal,
    max_retries=5,
    base_delay=5,
    backoff_multiplier=2,
    jitter=True
)

Behavior:
  1. Call post_signal()
  2. If succeeds: return result
  3. If fails:
     - Wait (delay + jitter)
     - Retry
  4. After 5 failed attempts:
     - Send Telegram alert: "Signal delivery failed after 5 retries"
     - Raise exception
```

### Telegram Alert Strategy

**Alert Conditions**:
- Persistent failures after max retries exhausted
- HTTP 5xx errors (server issues)
- Signature validation failures (security issue)
- Configuration problems (missing credentials)

**Alert Format**:
```
🚨 Signal Delivery Failed
Operation: post_signal
Signal ID: sig-abc-123
Error: HTTP 500 - Internal Server Error
Attempts: 5/5
Timestamp: 2025-10-25 14:30:45Z
Action: Manual review required
```

**Alert Severity Levels**:
- ERROR: Single signal failed, retried, will notify
- CRITICAL: Multiple consecutive failures, needs immediate attention
- DEBUG: Retry attempt logs (in structured logs, not Telegram)

---

## 5. File Specifications

### File 1: backend/app/core/retry.py

**Purpose**: Provide `with_retry` decorator and retry utilities

**Functions**:
```python
def with_retry(
    func: Callable,
    max_retries: int = 5,
    base_delay: float = 5.0,
    backoff_multiplier: float = 2.0,
    jitter: bool = True,
    max_delay: float = 120.0,
    logger: logging.Logger | None = None
) -> Callable:
    """
    Decorator for retry logic with exponential backoff.

    Args:
        func: Function to retry
        max_retries: Max retry attempts (≤10)
        base_delay: Initial delay in seconds (≥1)
        backoff_multiplier: Exponential multiplier (≥1)
        jitter: Add random jitter (±10%)
        max_delay: Cap on delay (≥base_delay)
        logger: Optional logger for retry attempts

    Returns:
        Wrapped function with retry logic

    Raises:
        RetryExhaustedError: After max retries failed
    """

async def retry_async(
    coro: Coroutine,
    max_retries: int = 5,
    base_delay: float = 5.0,
    backoff_multiplier: float = 2.0,
    jitter: bool = True,
    max_delay: float = 120.0,
    logger: logging.Logger | None = None
) -> Any:
    """
    Retry an async coroutine with exponential backoff.

    Args:
        coro: Async coroutine to retry
        max_retries: Max retry attempts
        base_delay: Initial delay in seconds
        backoff_multiplier: Exponential multiplier
        jitter: Add random jitter
        max_delay: Cap on delay
        logger: Optional logger

    Returns:
        Result from successful execution

    Raises:
        RetryExhaustedError: After max retries failed
    """

def calculate_backoff_delay(
    attempt: int,
    base_delay: float = 5.0,
    multiplier: float = 2.0,
    max_delay: float = 120.0,
    jitter: bool = True
) -> float:
    """
    Calculate backoff delay for given attempt.

    Args:
        attempt: Attempt number (0-based)
        base_delay: Base delay in seconds
        multiplier: Exponential multiplier
        max_delay: Maximum delay cap
        jitter: Add ±10% random variation

    Returns:
        Delay in seconds before next attempt
    """
```

**Exceptions**:
```python
class RetryError(Exception):
    """Base exception for retry operations."""
    pass

class RetryExhaustedError(RetryError):
    """Raised when all retry attempts exhausted."""

    def __init__(
        self,
        message: str,
        attempts: int,
        last_error: Exception,
        operation: str = "unknown"
    ):
        self.attempts = attempts
        self.last_error = last_error
        self.operation = operation
        super().__init__(message)
```

**Size Estimate**: ~200 lines

### File 2: backend/app/ops/alerts.py

**Purpose**: Send alerts to ops team via Telegram

**Functions**:
```python
async def send_owner_alert(
    message: str,
    severity: str = "ERROR",
    logger: logging.Logger | None = None
) -> bool:
    """
    Send alert to ops team via Telegram.

    Args:
        message: Alert message text
        severity: Alert level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        logger: Optional logger

    Returns:
        True if sent successfully, False if failed

    Raises:
        AlertConfigError: Missing Telegram credentials
    """

async def send_signal_delivery_error(
    signal_id: str,
    error: Exception,
    attempts: int,
    operation: str = "post_signal",
    logger: logging.Logger | None = None
) -> bool:
    """
    Send signal delivery error alert.

    Args:
        signal_id: Failed signal ID
        error: Exception that occurred
        attempts: Number of attempts made
        operation: Operation name (e.g., post_signal)
        logger: Optional logger

    Returns:
        True if sent successfully
    """

class OpsAlertService:
    """Service for managing operational alerts."""

    def __init__(
        self,
        telegram_token: str | None = None,
        telegram_chat_id: str | None = None,
        logger: logging.Logger | None = None
    ):
        """Initialize alert service with credentials."""

    async def send(
        self,
        message: str,
        severity: str = "ERROR",
        include_timestamp: bool = True
    ) -> bool:
        """Send alert via Telegram."""

    def validate_config(self) -> None:
        """Validate Telegram credentials are set."""
```

**Size Estimate**: ~150 lines

---

## 6. Test Strategy

### Unit Tests: backend/tests/test_retry.py

**Test Classes** (35+ tests):

**TestBackoffCalculation**:
1. test_backoff_starts_at_base_delay
2. test_backoff_increases_exponentially
3. test_backoff_respects_max_delay
4. test_backoff_with_jitter_varies
5. test_backoff_without_jitter_deterministic

**TestRetryDecorator**:
6. test_retry_succeeds_first_attempt
7. test_retry_succeeds_after_failures
8. test_retry_exhausts_after_max_attempts
9. test_retry_preserves_exception_context
10. test_retry_logs_attempts
11. test_retry_with_async_function
12. test_retry_with_timeout

**TestRetryAsync**:
13. test_retry_async_succeeds
14. test_retry_async_fails_exhausted
15. test_retry_async_exponential_delay
16. test_retry_async_with_jitter
17. test_retry_async_respects_max_delay

**TestRetryExceptions**:
18. test_retry_exhausted_error_contains_context
19. test_retry_exhausted_tracks_attempts
20. test_retry_exhausted_preserves_last_error

### Unit Tests: backend/tests/test_alerts.py

**Test Classes** (20+ tests):

**TestOpsAlertService**:
1. test_send_alert_success
2. test_send_alert_validates_config
3. test_send_alert_handles_telegram_error
4. test_send_alert_formats_message_correctly
5. test_send_alert_includes_timestamp

**TestSignalDeliveryAlert**:
6. test_send_signal_delivery_error_includes_signal_id
7. test_send_signal_delivery_error_includes_attempts
8. test_send_signal_delivery_error_formats_correctly

**TestAlertValidation**:
9. test_alert_config_error_on_missing_token
10. test_alert_config_error_on_missing_chat_id
11. test_alert_retry_on_telegram_timeout

### Integration Tests: backend/tests/test_retry_integration.py

**Test Classes** (15+ tests):

**TestRetryWithHmacClient**:
1. test_hmac_client_with_retry_succeeds_on_200
2. test_hmac_client_with_retry_retries_on_500
3. test_hmac_client_with_retry_fails_after_max_attempts
4. test_hmac_client_with_retry_sends_alert_on_exhaustion
5. test_hmac_client_with_retry_respects_timeout

**TestRetryWithSignal**:
6. test_signal_delivery_retries_on_network_error
7. test_signal_delivery_does_not_retry_on_validation_error
8. test_signal_delivery_alert_includes_full_context

---

## 7. Test Coverage Targets

**Test Coverage Goals**:
- Unit tests: ≥90% on retry.py and alerts.py
- Integration tests: ≥80% on retry-client integration
- Edge cases: All error paths covered
- Total: ≥85% coverage

**Coverage by Component**:
- Backoff calculation: 100%
- Retry decorator: 95% (sync + async)
- Alert service: 85% (network calls mocked)
- Exception handling: 100%

---

## 8. Acceptance Criteria

1. ✅ Retry logic with exponential backoff implemented
2. ✅ Jitter support (±10% randomness)
3. ✅ Max retry limit enforced (default: 5)
4. ✅ Backoff delay capped at maximum
5. ✅ Async/await support for coroutines
6. ✅ Telegram alert integration
7. ✅ Alert on persistent failures
8. ✅ Configuration from environment variables
9. ✅ Metrics/telemetry hooks
10. ✅ 100% type hints on all functions
11. ✅ Comprehensive docstrings
12. ✅ Test coverage ≥85%
13. ✅ Black formatted code
14. ✅ No TODOs or placeholders
15. ✅ Security validated (no secrets in logs)
16. ✅ Error messages clear and actionable
17. ✅ Logging structured and contextual
18. ✅ Works with PR-017 HmacClient
19. ✅ Enables PR-019 and PR-021
20. ✅ Production-ready code

---

## 9. Timeline & Phases

### Phase 1: Planning (30 min) - **IN PROGRESS**
- ✅ Read PR-018 specification
- ✅ Create implementation plan
- ✅ Identify dependencies
- ✅ Design architecture
- ✅ Outline test strategy

### Phase 2: Implementation (2 hours) - **NEXT**
- Create retry.py (200 lines, retry logic + backoff)
- Create alerts.py (150 lines, Telegram alerts)
- Create exceptions for retry module
- Type hints on all functions
- Docstrings with examples
- Black formatting

### Phase 3: Testing (1.5 hours)
- test_retry.py (35+ tests for backoff/retry logic)
- test_alerts.py (20+ tests for alert service)
- test_retry_integration.py (15+ tests for integration)
- Achieve ≥85% coverage
- All 70+ tests passing

### Phase 4: Verification (30 min)
- Coverage report (≥85%)
- Type checking (100% hints)
- Black formatting verified
- Security validation
- Create PHASE-4-VERIFICATION-COMPLETE.md

### Phase 5: Documentation (45 min)
- IMPLEMENTATION-COMPLETE.md
- BUSINESS-IMPACT.md
- QUICK-REFERENCE.md
- Update CHANGELOG.md

---

## 10. Key Design Decisions

### 1. Exponential Backoff with Jitter
**Why**: Prevents thundering herd (all clients retrying simultaneously)
**Alternative**: Linear backoff (simpler, less effective)
**Choice**: Exponential + jitter (industry standard)

### 2. Async/Await Support
**Why**: HmacClient is async, integration seamless
**Alternative**: Sync only (limits use cases)
**Choice**: Both sync and async (maximum flexibility)

### 3. Decorator Pattern
**Why**: Easy to apply to any function/coroutine
**Alternative**: Context manager (more verbose)
**Choice**: Decorator (cleanest API)

### 4. Telegram Alerts
**Why**: Immediate ops notification, alerting already in system
**Alternative**: Email, Slack, webhook (additional integrations)
**Choice**: Telegram (uses existing bot token)

### 5. Configuration from Environment
**Why**: No hardcoding, deploy-time flexibility
**Alternative**: Config file
**Choice**: Environment variables (12-factor app)

---

## 11. Known Constraints & Assumptions

### Constraints
- Max retries ≤ 10 (prevent infinite loops)
- Base delay ≥ 1 second (prevent CPU spinning)
- Backoff multiplier ≥ 1 (prevent negative delays)
- Total retry time ≤ 10 minutes (prevent hanging)

### Assumptions
- Telegram bot token is valid and active
- Server failures are transient (not permanent)
- Network timeouts are recoverable (not auth failures)
- All operations are idempotent (PR-017 idempotency key)

---

## 12. Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|-----------|
| Infinite retry loop | Low | High | Max retry cap + timeout |
| Alert spam (too many) | Medium | Medium | Alert deduplication (Phase 2+) |
| Telegram credentials missing | Medium | High | Config validation at startup |
| Network still failing after retries | High | Low | Will alert ops, manual intervention |
| Retry logic too aggressive | Low | Medium | Conservative defaults (5 retries, 5s base) |

---

## 13. Success Criteria

**Phase 1 Complete When**:
- [ ] Specification analyzed and documented
- [ ] Architecture designed with diagrams
- [ ] File specs detailed (functions, parameters, returns)
- [ ] Test strategy outlined (test classes, test cases)
- [ ] Implementation plan created
- [ ] Phase 2 ready to execute

**Phase 5 Complete (PR-018 Done) When**:
- [ ] All 70+ tests passing
- [ ] Coverage ≥85%
- [ ] Type hints 100%
- [ ] Black formatted
- [ ] 4 documentation files created
- [ ] CHANGELOG updated
- [ ] Ready for code review and merge

---

## 14. Deliverables Summary

**Code**:
- `backend/app/core/retry.py` (~200 lines)
- `backend/app/ops/alerts.py` (~150 lines)

**Tests**:
- `backend/tests/test_retry.py` (~350 lines, 35+ tests)
- `backend/tests/test_alerts.py` (~250 lines, 20+ tests)
- `backend/tests/test_retry_integration.py` (~300 lines, 15+ tests)

**Documentation**:
- `docs/prs/PR-018-IMPLEMENTATION-PLAN.md` (This file)
- `docs/prs/PR-018-IMPLEMENTATION-COMPLETE.md`
- `docs/prs/PR-018-BUSINESS-IMPACT.md`
- `docs/prs/PR-018-QUICK-REFERENCE.md`
- Updated `CHANGELOG.md`

**Total**:
- Production code: 350 lines
- Test code: 900+ lines
- Documentation: 2,000+ lines
- Tests: 70+ passing
- Coverage: ≥85%

---

## 15. Next Steps

✅ **Phase 1 (Planning) Complete**

**Proceed to Phase 2** (Implementation):
1. Create backend/app/core/retry.py (200 lines)
2. Create backend/app/ops/alerts.py (150 lines)
3. Add exception classes
4. Add 100% type hints
5. Add comprehensive docstrings
6. Run Black formatting

**Estimated Time**: 2 hours for Phase 2

---

**Status**: ✅ **PHASE 1 PLAN COMPLETE** - Ready for Phase 2 Implementation
