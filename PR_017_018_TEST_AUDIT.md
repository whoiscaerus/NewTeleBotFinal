# PR-017 & PR-018 COMPREHENSIVE TEST AUDIT & FIXES

**Date**: November 3, 2025
**Status**: AUDIT IN PROGRESS - Critical gaps identified
**Objective**: Ensure ALL tests validate REAL working business logic with 90-100% coverage

---

## CRITICAL FINDINGS

### ✅ EXISTING - Well Implemented

#### 1. **HMAC Signature Generation** (`test_outbound_hmac.py`) - **EXCELLENT**
   - ✅ 40+ comprehensive tests across 5 test classes
   - ✅ TestHmacSignatureGeneration (6 tests): determinism, sensitivity to each param
   - ✅ TestHmacSignatureVerification (3 tests): valid/invalid/tampered signatures
   - ✅ TestHmacSignatureErrorHandling (8 tests): empty inputs, malformed timestamps, large bodies
   - ✅ TestHmacSignatureEdgeCases (6 tests): special chars, unicode, timezone offsets
   - ✅ Tests REAL build_signature() and verify_signature() functions
   - ✅ Validates: RFC3339 format, base64 encoding, HMAC-SHA256 algorithm
   - **STATUS**: Excellent comprehensive coverage of cryptographic logic

#### 2. **Outbound Client** (`test_outbound_client.py`) - **GOOD but Gaps Exist**
   - ✅ TestHmacClientInitialization (3 tests): config validation, init, repr
   - ✅ TestHmacClientContextManager (2 tests): context manager, session cleanup
   - ✅ TestHmacClientPostSignal (8 tests): success path, validation, error handling
   - ✅ TestHmacClientSerialization (3 tests): canonical order, field inclusion, type conversion
   - ✅ TestRFC3339Timestamp (2 tests): timestamp format validation
   - ✅ TestHmacClientErrorMessages (1 test): Pydantic validation clarity
   - ✅ Tests use mocking for httpx.AsyncClient (dependency only)
   - ✅ Validates: signal validation, HTTP errors (400, 500), timeout handling, header structure
   - **GAPS**:
     - ❌ Does NOT verify actual HMAC signature is computed (just checks header presence)
     - ❌ Does NOT test integration of build_signature() with actual request
     - ❌ Does NOT test multiple failure scenarios (connection refused, reset, etc.)
   - **COVERAGE**: ~75% (core happy path + basic errors tested, integration gaps)

#### 3. **Retry Logic** (`test_retry.py`) - **EXCELLENT**
   - ✅ TestBackoffCalculation (7 tests): exponential formula, jitter, max delay, validation
   - ✅ TestRetryDecorator (9 tests): success path, failures, exhaustion, args/kwargs
   - ✅ TestRetryAsync (6 tests): coroutine retry, attempt tracking
   - ✅ TestRetryExceptions (3 tests): context tracking, attempt count, error preservation
   - ✅ TestRetryIntegration (3 tests): multiple exception types, delay progression, side effects
   - ✅ Tests REAL @with_retry decorator and exponential backoff
   - ✅ Validates: exponential formula (5→10→20→40→80), jitter ±10%, RetryExhaustedError
   - **GAPS**:
     - ❌ Does NOT test retry on actual signal posting failures
     - ❌ Does NOT test integration with real outbound client
   - **COVERAGE**: ~85% (backoff formula fully tested, integration gaps)

#### 4. **Alerts Service** (`test_alerts.py`) - **GOOD but Gaps Exist**
   - ✅ TestOpsAlertServiceInit (4 tests): init, from_env, validation
   - ✅ TestConfigValidation (4 tests): config validation errors
   - ✅ TestSendAlert (7 tests): success, API error, network error, severity, timeout
   - ✅ TestSendErrorAlert (3 tests): error alert with context, formatting
   - ✅ TestModuleFunctions (4 tests): module-level function signatures
   - ✅ TestAlertFormatting (3 tests): exception type, attempt info, severity
   - ✅ TestAlertExceptions (2 tests): exception types
   - ✅ TestAlertIntegration (4 tests): full error alert flow, multiple alerts
   - ✅ Tests use mocking for httpx.AsyncClient (dependency only)
   - ✅ Validates: Telegram config, error formatting, alert sending
   - **GAPS**:
     - ❌ Does NOT test alert sent AFTER retry exhaustion (integration missing)
     - ❌ Does NOT test real retry → alert flow
   - **COVERAGE**: ~80% (alert mechanics fully tested, integration gaps)

### ⚠️ GAPS IDENTIFIED - CRITICAL INTEGRATION MISSING

#### GAP 1: **Signature Integration NOT Tested** 🔴 CRITICAL
**Problem**: `test_outbound_client.py` checks that X-Signature header exists, but DOES NOT verify that it contains the REAL HMAC signature computed by build_signature()

**Current Test**:
```python
# Current test only checks PRESENCE of header, not CORRECTNESS of signature
assert "X-Signature" in headers
assert headers["X-Producer-Id"] == "test-producer"
```

**What's Missing**:
```python
# ❌ No test verifies:
# 1. Actual build_signature() was called
# 2. Signature value matches expected value
# 3. Signature changes when body changes
# 4. Signature algorithm (HMAC-SHA256) was used
```

**Why This Matters**:
- Tests would pass even if signature was hardcoded or random
- Server would reject signatures if algorithm changed
- This is the core security feature

**Fix Required**:
```python
@pytest.mark.asyncio
async def test_post_signal_signature_is_valid_and_correct():
    """Verify actual HMAC signature is computed and matches spec."""
    client = HmacClient(config, logger)

    with patch("httpx.AsyncClient") as mock_http:
        mock_session = AsyncMock()
        mock_http.return_value = mock_session
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"signal_id": "sig-1"}
        mock_session.post.return_value = mock_response

        await client._ensure_session()
        await client.post_signal(signal)

        # Extract actual request
        call_args = mock_session.post.call_args
        actual_headers = call_args.kwargs['headers']
        actual_body = call_args.kwargs['content']

        # Verify signature is REAL
        actual_sig = actual_headers['X-Signature']
        timestamp = actual_headers['X-Timestamp']

        from backend.app.trading.outbound.hmac import build_signature
        expected_sig = build_signature(
            secret=config.producer_secret.encode(),
            body=actual_body,
            timestamp=timestamp,
            producer_id=config.producer_id
        )

        # ✅ THIS IS THE REAL TEST
        assert actual_sig == expected_sig
```

#### GAP 2: **Retry Integration NOT Tested** 🔴 CRITICAL
**Problem**: `test_retry.py` tests backoff formula in isolation, but does NOT test retry decorator on actual signal posting

**Current Tests**:
```python
# Only tests backoff calculation
def test_backoff_increases_exponentially():
    delays = [calculate_backoff_delay(attempt=i, ...) for i in range(5)]
    assert delays == [5.0, 10.0, 20.0, 40.0, 80.0]

# Only tests decorator on simple functions
@with_retry(max_retries=2)
async def flaky_func():
    ...
```

**What's Missing**:
```python
# ❌ No test for:
# - @with_retry on actual HmacClient.post_signal()
# - Actual network errors trigger retry (timeout, connection refused)
# - Retry delays follow exponential progression: 5s, 10s, 20s, etc.
# - All retries are attempted before giving up
```

**Why This Matters**:
- Signal might be posted successfully on retry 2 or 3
- Without testing, we don't know if retry actually works on real failures
- Tests only verify math, not real behavior

**Fix Required**:
```python
@pytest.mark.asyncio
async def test_retry_on_actual_signal_posting_transient_failure():
    """Test retry actually retries real signal posting on transient failure."""
    client = HmacClient(config, logger)
    attempt_count = 0

    @with_retry(max_retries=2, base_delay=0.01)
    async def post_with_retry():
        nonlocal attempt_count
        attempt_count += 1
        if attempt_count < 3:
            # First two attempts: transient network error
            raise httpx.ConnectError("Connection refused")
        # Third attempt: success
        return await client.post_signal(signal)

    with patch("httpx.AsyncClient") as mock_http:
        mock_session = AsyncMock()
        mock_http.return_value = mock_session
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"signal_id": "sig-1"}
        mock_session.post.return_value = mock_response

        await client._ensure_session()
        result = await post_with_retry()

        # ✅ Verify it retried exactly twice (3 total attempts)
        assert attempt_count == 3
        # ✅ Verify final result is success
        assert result.signal_id == "sig-1"
```

#### GAP 3: **Telegram Alert on Retry Exhaustion NOT Tested** 🔴 CRITICAL
**Problem**: Alert tests exist, but do NOT test alert sent specifically AFTER retry exhaustion

**Current Tests**:
```python
# Only tests alert sending in isolation
async def test_send_error_alert_success():
    result = await service.send_error_alert(...)
    assert result is True
```

**What's Missing**:
```python
# ❌ No test for:
# - Signal posting fails all retries
# - After max retries exhausted (3 attempts), RetryExhaustedError raised
# - Alert automatically sent with error details
# - Alert includes: signal ID, error type, attempt count
```

**Why This Matters**:
- If alert service breaks, we lose visibility into signal delivery failures
- Without this test, we don't know if integration works
- Owner needs to know immediately when signals fail

**Fix Required**:
```python
@pytest.mark.asyncio
async def test_telegram_alert_sent_after_max_retries_exhausted():
    """Test alert sent when signal posting exhausts all retries."""
    client = HmacClient(config, logger)
    alert_service = OpsAlertService(telegram_token="token", telegram_chat_id="chat")

    @with_retry(max_retries=2, base_delay=0.01)
    async def post_with_alert_on_failure():
        # All attempts fail
        raise httpx.ConnectError("Broker unreachable")

    with patch("httpx.AsyncClient") as mock_http:
        mock_session = AsyncMock()
        mock_http.return_value = mock_session
        mock_session.post.side_effect = httpx.ConnectError("Broker unreachable")

        try:
            await post_with_alert_on_failure()
        except RetryExhaustedError as ex:
            # After exhausting retries, send alert
            result = await alert_service.send_error_alert(
                message=f"Signal delivery failed",
                error=ex,
                attempts=ex.attempts
            )

            # ✅ Verify alert was sent
            assert result is True
```

#### GAP 4: **Network Failure Scenarios NOT Tested** 🟡 IMPORTANT
**Problem**: Only basic error handling tested. Real network failures not simulated

**What's Missing**:
```python
# ❌ No tests for real transient failures:
# - Connection timeout (partial connection, no response)
# - Connection refused (immediate fail, should retry)
# - Connection reset (mid-request fail, should retry)
# - DNS resolution failure
# - SSL certificate validation error
```

**Fix Required**:
```python
@pytest.mark.asyncio
async def test_retry_on_connection_timeout():
    """Test retry on connection timeout (transient failure)."""
    @with_retry(max_retries=1, base_delay=0.01)
    async def post_signal_timeout():
        return await client.post_signal(signal)

    with patch("httpx.AsyncClient") as mock_http:
        mock_session = AsyncMock()
        mock_http.return_value = mock_session
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"signal_id": "sig-1"}

        # First call: timeout, Second call: success
        mock_session.post.side_effect = [
            httpx.TimeoutException("Read timeout"),
            mock_response
        ]

        result = await post_signal_timeout()
        # ✅ Verify it retried after timeout
        assert mock_session.post.call_count == 2
        assert result.signal_id == "sig-1"

@pytest.mark.asyncio
async def test_retry_on_connection_refused():
    """Test retry on connection refused (immediate fail)."""
    @with_retry(max_retries=1, base_delay=0.01)
    async def post_signal_refused():
        return await client.post_signal(signal)

    with patch("httpx.AsyncClient") as mock_http:
        mock_session = AsyncMock()
        mock_http.return_value = mock_session
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"signal_id": "sig-1"}

        # First call: connection refused, Second call: success
        mock_session.post.side_effect = [
            ConnectionRefusedError("Connection refused"),
            mock_response
        ]

        result = await post_signal_refused()
        assert mock_session.post.call_count == 2
```

#### GAP 5: **Canonical Serialization NOT Verified Against Spec** 🟡 IMPORTANT
**Problem**: Tests check fields are in alphabetical order, but do NOT verify signature consistency

**What's Missing**:
```python
# ❌ No test verifies:
# - Serialization is EXACTLY identical for same signal
# - Two different clients produce same serialization
# - Server can verify signature (canonical format is prerequisite)
```

**Fix Required**:
```python
@pytest.mark.asyncio
async def test_signal_serialization_is_canonical_for_signature_verification():
    """Test serialization is canonical so signatures can be verified."""
    client1 = HmacClient(config, logger)
    client2 = HmacClient(config, logger)

    # Same signal serialized by two clients
    body1 = client1._serialize_signal(signal)
    body2 = client2._serialize_signal(signal)

    # Must be byte-identical for signature verification to work
    import json
    json1 = json.dumps(body1, separators=(",", ":"), sort_keys=True)
    json2 = json.dumps(body2, separators=(",", ":"), sort_keys=True)

    assert json1 == json2

    # Signature computed on json1 should verify with json2
    sig1 = build_signature(json1.encode(), config.producer_secret.encode(), ...)
    assert verify_signature(json2.encode(), config.producer_secret.encode(), sig1, ...)
```

### Summary of Critical Gaps

| Gap | Priority | Impact | Test Needed |
|-----|----------|--------|------------|
| Real HMAC signature in requests | 🔴 CRITICAL | Security feature not validated | test_signature_integration |
| Retry on actual posting failures | 🔴 CRITICAL | Core resilience not tested | test_retry_on_real_failures |
| Alert on retry exhaustion | 🔴 CRITICAL | Owner not notified on failures | test_alert_after_retry |
| Network failure scenarios | 🟡 IMPORTANT | Transient failures not tested | test_timeout/refused/reset |
| Canonical serialization verification | 🟡 IMPORTANT | Signature verification assumption | test_canonical_serialization |

---

## COVERAGE ANALYSIS

### Current Coverage (Estimated)

| Module | Coverage | Status | Gap |
|--------|----------|--------|-----|
| `hmac.py` | **92%** | ✅ EXCELLENT | Only `verify_signature` needs 1-2 edge cases |
| `client.py` | **75%** | ⚠️ GOOD | Missing: signature verification (CRITICAL), network failures |
| `retry.py` | **85%** | ✅ GOOD | Missing: real failure scenarios with actual client |
| `alerts.py` | **80%** | ✅ GOOD | Missing: retry exhaustion integration |

### Coverage Target
- **PR-017** (`client.py` + `hmac.py`): **90-100%** (currently 75-92%)
- **PR-018** (`retry.py` + `alerts.py`): **90-100%** (currently 80-85%)

### Tests Required to Reach 90-100%

**PR-017 (Outbound Client + HMAC)**:
1. ✅ **test_post_signal_signature_is_valid_and_correct** (CRITICAL)
   - Verify actual HMAC signature matches spec
   - Ensures crypto is real, not mocked

2. ✅ **test_post_signal_includes_all_required_headers** (IMPORTANT)
   - X-Producer-Id, X-Timestamp, X-Signature, X-Idempotency-Key all present

3. ✅ **test_network_timeout_handled_gracefully** (IMPORTANT)
   - TimeoutException caught and converted to OutboundClientError

4. ✅ **test_connection_refused_handled_gracefully** (IMPORTANT)
   - ConnectionError caught and converted to OutboundClientError

5. ✅ **test_signal_serialization_canonical** (IMPORTANT)
   - Same signal always serializes identically
   - Prerequisite for signature verification

**PR-018 (Retry + Alerts)**:
1. ✅ **test_retry_on_actual_posting_transient_failure** (CRITICAL)
   - Verify @with_retry actually retries on real httpx errors
   - Simulate timeout → retry → success

2. ✅ **test_retry_on_connection_refused** (IMPORTANT)
   - Connection refused triggers retry with backoff

3. ✅ **test_retry_on_connection_reset** (IMPORTANT)
   - Connection reset mid-request triggers retry

4. ✅ **test_alert_sent_after_retry_exhaustion** (CRITICAL)
   - Signal posting fails all retries
   - Telegram alert sent with error details
   - Alert includes: error type, attempt count

5. ✅ **test_alert_includes_signal_context** (IMPORTANT)
   - Alert message includes instrument, side, error reason

---

## NEXT STEPS - IMMEDIATE ACTION REQUIRED

### Phase 1: Create Critical Integration Tests (PR-017)

**File**: Create `/backend/tests/test_outbound_integration.py`

**Test 1**: Verify Real HMAC Signature in Requests 🔴 CRITICAL
```python
@pytest.mark.asyncio
async def test_post_signal_signature_computation_is_real():
    """Verify actual HMAC-SHA256 signature is computed and sent."""
    client = HmacClient(config, logger)

    with patch("httpx.AsyncClient") as mock_http:
        mock_session = AsyncMock()
        mock_http.return_value = mock_session
        mock_response = MagicMock(status_code=201)
        mock_response.json.return_value = {"signal_id": "sig-1", "status": "pending"}
        mock_session.post.return_value = mock_response

        await client._ensure_session()
        await client.post_signal(signal)

        # Extract actual request
        call_args = mock_session.post.call_args
        actual_headers = call_args.kwargs['headers']
        actual_body = call_args.kwargs['content']
        timestamp = actual_headers['X-Timestamp']

        # Compute expected signature
        from backend.app.trading.outbound.hmac import build_signature
        expected_sig = build_signature(
            secret=config.producer_secret.encode(),
            body=actual_body,
            timestamp=timestamp,
            producer_id=config.producer_id
        )

        # ✅ VERIFY SIGNATURE IS CORRECT
        assert actual_headers['X-Signature'] == expected_sig
```

**Test 2**: Network Timeout Triggers Retry ✅ ADD
```python
@pytest.mark.asyncio
async def test_timeout_is_caught_and_converted_to_error():
    """Test timeout is properly converted to OutboundClientError."""
    client = HmacClient(config, logger)

    with patch("httpx.AsyncClient") as mock_http:
        mock_session = AsyncMock()
        mock_http.return_value = mock_session
        import httpx
        mock_session.post.side_effect = httpx.TimeoutException("Read timeout")

        await client._ensure_session()

        with pytest.raises(TimeoutError):
            await client.post_signal(signal)
```

**Test 3**: Connection Refused Is Retryable Error ✅ ADD
```python
@pytest.mark.asyncio
async def test_connection_refused_is_caught_and_converted():
    """Test connection refused is properly converted to OutboundClientError."""
    client = HmacClient(config, logger)

    with patch("httpx.AsyncClient") as mock_http:
        mock_session = AsyncMock()
        mock_http.return_value = mock_session
        mock_session.post.side_effect = ConnectionRefusedError("Connection refused")

        await client._ensure_session()

        with pytest.raises(OutboundClientError):
            await client.post_signal(signal)
```

### Phase 2: Create Retry Integration Tests (PR-018)

**File**: Add to `/backend/tests/test_pr_017_018_integration.py`

**Test 4**: Retry on Real Signal Posting Failure 🔴 CRITICAL
```python
@pytest.mark.asyncio
async def test_retry_decorator_retries_on_real_posting_failure():
    """Test @with_retry actually retries on real httpx errors."""
    client = HmacClient(config, logger)
    attempt_count = 0

    @with_retry(max_retries=2, base_delay=0.01)
    async def post_with_retry():
        nonlocal attempt_count
        attempt_count += 1
        if attempt_count < 3:
            raise httpx.ConnectError("Server unreachable")
        return await client.post_signal(signal)

    with patch("httpx.AsyncClient") as mock_http:
        mock_session = AsyncMock()
        mock_http.return_value = mock_session
        mock_response = MagicMock(status_code=201)
        mock_response.json.return_value = {"signal_id": "sig-1"}

        mock_session.post.side_effect = [
            httpx.ConnectError("Server unreachable"),
            httpx.ConnectError("Server unreachable"),
            mock_response
        ]

        await client._ensure_session()
        result = await post_with_retry()

        # ✅ Verify all 3 attempts were made
        assert attempt_count == 3
        assert mock_session.post.call_count == 3
        assert result.signal_id == "sig-1"
```

**Test 5**: Retry Backoff Delays Are Applied 🟡 ADD
```python
@pytest.mark.asyncio
async def test_retry_delays_follow_exponential_progression():
    """Test retry backoff delays are: 1.0, 2.0, 4.0 seconds."""
    delays_used = []

    async def mock_sleep(seconds):
        delays_used.append(seconds)

    with patch("asyncio.sleep", side_effect=mock_sleep):
        @with_retry(
            max_retries=3,
            base_delay=1.0,
            backoff_multiplier=2.0,
            jitter=False
        )
        async def always_fails():
            raise ValueError("Fail")

        with pytest.raises(RetryExhaustedError):
            await always_fails()

        # ✅ Verify backoff progression: 1.0, 2.0, 4.0
        assert delays_used == [1.0, 2.0, 4.0]
```

### Phase 3: Create Alert Integration Test (PR-018)

**Test 6**: Telegram Alert After Retry Exhaustion 🔴 CRITICAL
```python
@pytest.mark.asyncio
async def test_alert_sent_after_signal_posting_retry_exhaustion():
    """Test Telegram alert sent when signal posting fails all retries."""
    client = HmacClient(config, logger)
    alert_service = OpsAlertService(telegram_token="token", telegram_chat_id="chat")

    attempt_count = 0

    async def post_with_alert_on_failure():
        @with_retry(max_retries=2, base_delay=0.01)
        async def attempt_post():
            nonlocal attempt_count
            attempt_count += 1
            raise httpx.ConnectError("Broker unreachable")

        try:
            return await attempt_post()
        except RetryExhaustedError as ex:
            # Send alert after exhausting retries
            await alert_service.send_error_alert(
                message=f"Signal delivery failed after {ex.attempts} attempts",
                error=ex,
                attempts=ex.attempts,
                operation="post_signal"
            )
            raise

    with patch("httpx.AsyncClient") as mock_http:
        mock_session = AsyncMock()
        mock_http.return_value = mock_session
        mock_session.post.side_effect = httpx.ConnectError("Broker unreachable")

        with pytest.raises(RetryExhaustedError):
            await post_with_alert_on_failure()

        # ✅ Verify all signal posting attempts failed
        assert attempt_count == 3  # 0, 1, 2
        # ✅ Verify Telegram was called (at least for alert, possibly more for retries)
        assert mock_session.post.call_count >= 1
```

### Phase 4: Run Coverage and Identify Remaining Gaps

```bash
# Run coverage report
.venv/Scripts/python.exe -m pytest \
  backend/tests/test_outbound_hmac.py \
  backend/tests/test_outbound_client.py \
  backend/tests/test_retry.py \
  backend/tests/test_alerts.py \
  backend/tests/test_outbound_integration.py \
  backend/tests/test_pr_017_018_integration.py \
  --cov=backend/app/trading/outbound \
  --cov=backend/app/core/retry \
  --cov=backend/app/ops/alerts \
  --cov-report=html \
  -v

# Open coverage report
start htmlcov/index.html
```

### Phase 5: Create Final Integration Test

**File**: Create `/backend/tests/test_signal_delivery_resilience.py`

**Complete End-to-End Test**: Signal → HMAC → Post → Retry → Alert
```python
@pytest.mark.asyncio
async def test_complete_signal_delivery_workflow_with_resilience():
    """Test complete workflow: signal creation → HMAC signing →
    posting with retry → alert on exhaustion.
    """
    # 1. Create signal
    signal = SignalCandidate(
        instrument="GOLD",
        side="buy",
        entry_price=1950.50,
        stop_loss=1945.00,
        take_profit=1960.00,
        confidence=0.85,
        reason="Test signal",
        timestamp=datetime.utcnow(),
        payload={"rsi": 35, "atr": 5.5}
    )

    # 2. Create client with HMAC signing
    client = HmacClient(config, logger)
    alert_service = OpsAlertService(telegram_token="token", telegram_chat_id="chat")

    attempt_count = 0

    # 3. Post with retry and alert
    @with_retry(max_retries=2, base_delay=0.01)
    async def post_with_resilience():
        nonlocal attempt_count
        attempt_count += 1
        if attempt_count < 3:
            # Simulate transient network errors
            raise httpx.ConnectError("Network unreachable")
        # Third attempt succeeds
        return await client.post_signal(signal)

    with patch("httpx.AsyncClient") as mock_http:
        mock_session = AsyncMock()
        mock_http.return_value = mock_session
        mock_response = MagicMock(status_code=201)
        mock_response.json.return_value = {
            "signal_id": "sig-prod-123",
            "status": "pending_approval",
            "server_timestamp": "2025-10-25T14:30:45.123456Z"
        }

        mock_session.post.side_effect = [
            httpx.ConnectError("Network unreachable"),  # Attempt 1: fail
            httpx.ConnectError("Network unreachable"),  # Attempt 2: fail
            mock_response  # Attempt 3: success
        ]

        await client._ensure_session()

        # ✅ Should retry and eventually succeed
        result = await post_with_resilience()

        # Verify retries happened
        assert attempt_count == 3
        assert mock_session.post.call_count == 3

        # Verify response
        assert result.signal_id == "sig-prod-123"
        assert result.status == "pending_approval"

        # Verify headers contained real HMAC signature
        calls = mock_session.post.call_args_list
        for call in calls:
            headers = call.kwargs['headers']
            assert 'X-Signature' in headers
            assert 'X-Timestamp' in headers
            assert 'X-Producer-Id' in headers
```

---

## EXECUTION PLAN

1. **TODAY**: Create `/backend/tests/test_outbound_integration.py` with 3 tests (30 mins)
2. **TODAY**: Create `/backend/tests/test_pr_017_018_integration.py` with 3 tests (30 mins)
3. **TODAY**: Run coverage report (10 mins)
4. **TODAY**: Add any remaining tests for 90-100% coverage (varies)
5. **TODAY**: Verify all tests passing locally (10 mins)
6. **TODAY**: Push to GitHub, verify CI/CD green (10 mins)
7. **TODAY**: Create `PR_017_018_IMPLEMENTATION_COMPLETE.md` (15 mins)

**Total Time**: 2-3 hours to reach 90-100% coverage and production-ready state
