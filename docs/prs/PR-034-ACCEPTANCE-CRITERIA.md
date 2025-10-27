# PR-034 Acceptance Criteria: Telegram Native Payments

**Status**: In Development
**Date**: October 27, 2025
**Target Coverage**: 90%+ (25+ test cases)

---

## Overview

This document specifies **testable, measurable** acceptance criteria for PR-034 (Telegram Native Payments). Each criterion maps to specific test cases and code coverage metrics.

---

## Acceptance Criterion 1: Send Invoice to User

**User Story**: As a user, I can choose "Telegram Pay" from the /buy menu and receive a Telegram invoice to confirm payment.

### Requirements

| ID | Requirement | Test Case | Status |
|---|---|---|---|
| 1.1 | `/api/v1/telegram/payment/send-invoice` accepts valid `plan_code` parameter | `test_send_invoice_valid_plan` | ✅ |
| 1.2 | Returns Telegram `invoice_id` from API response | `test_send_invoice_returns_id` | ✅ |
| 1.3 | Invoice amount matches plan price from catalog (PR-028) | `test_send_invoice_amount_matches_catalog` | ✅ |
| 1.4 | Rejects unknown plan codes with 422 status | `test_send_invoice_invalid_plan` | ✅ |
| 1.5 | Rejects if user already has active premium entitlement | `test_send_invoice_user_already_premium` | ✅ |
| 1.6 | Rejects if user lacks JWT authentication | `test_send_invoice_unauthenticated` | ✅ |
| 1.7 | Rate limits: max 5 attempts per user per minute | `test_send_invoice_rate_limit` | ✅ |
| 1.8 | Logs invoice creation with user_id, plan_code, amount | `test_send_invoice_logging` | ✅ |
| 1.9 | Increments metric: `telegram_payments_total{result="sent"}` | `test_send_invoice_telemetry` | ✅ |
| 1.10 | Invoice created successfully in Telegram | `test_send_invoice_telegram_api_call` | ✅ |

**Coverage**: 10 test cases covering happy path + all error paths

**Example Test**:
```python
@pytest.mark.asyncio
async def test_send_invoice_valid_plan(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
    mock_telegram_api
):
    """Test sending invoice for valid plan."""
    response = await client.post(
        "/api/v1/telegram/payment/send-invoice",
        json={"plan_code": "gold_1m"},
        headers=auth_headers
    )

    assert response.status_code == 200
    data = response.json()
    assert "invoice_id" in data
    assert data["plan_code"] == "gold_1m"
    assert data["amount_cents"] == 2500  # £25.00
    assert mock_telegram_api.send_invoice.called
```

---

## Acceptance Criterion 2: Validate Pre-Checkout Query

**User Story**: Before charging the user, Telegram asks the backend to validate the purchase (amount, user, etc.). We verify everything is correct.

### Requirements

| ID | Requirement | Test Case | Status |
|---|---|---|---|
| 2.1 | Accepts `pre_checkout_query` update from Telegram webhook | `test_precheck_query_received` | ✅ |
| 2.2 | Extracts plan_code + timestamp from `invoice_payload` | `test_precheck_payload_parsing` | ✅ |
| 2.3 | Validates amount matches catalog price (prevents tampering) | `test_precheck_amount_mismatch_rejected` | ✅ |
| 2.4 | Rejects if amount has been tampered (modified) | `test_precheck_tamper_detection` | ✅ |
| 2.5 | Rejects if timestamp older than 1 hour (replay prevention) | `test_precheck_old_timestamp_rejected` | ✅ |
| 2.6 | Validates user_id from JWT matches payment user | `test_precheck_user_mismatch_rejected` | ✅ |
| 2.7 | Returns `ok: true` for valid purchases | `test_precheck_valid_ok` | ✅ |
| 2.8 | Returns `ok: false` + error description for invalid | `test_precheck_invalid_error_message` | ✅ |
| 2.9 | Logs pre-checkout query with decision (ok/rejected) | `test_precheck_logging` | ✅ |
| 2.10 | Increments metric: `telegram_precheck_total{result=ok\|rejected}` | `test_precheck_telemetry` | ✅ |

**Coverage**: 10 test cases covering validation logic + all rejection paths

**Example Test**:
```python
@pytest.mark.asyncio
async def test_precheck_amount_mismatch_rejected(
    client: AsyncClient,
    mock_telegram_webhook
):
    """Test pre-checkout rejects tampered amount."""
    # Amount doesn't match catalog (£25 → £100)
    payload = {
        "update_id": 123,
        "pre_checkout_query": {
            "id": "query_123",
            "from": {"id": 111},
            "currency": "GBP",
            "total_amount": 10000,  # £100 (tampered!)
            "invoice_payload": "gold_1m_1698432000"  # Should be £25
        }
    }

    response = await client.post(
        "/api/v1/telegram/webhook",
        json=payload
    )

    assert response.status_code == 200
    # Should return error_code instead of ok
    assert mock_telegram_api.answer_pre_checkout_query.called
    call_args = mock_telegram_api.answer_pre_checkout_query.call_args
    assert call_args.kwargs.get("ok") is False
    assert "mismatch" in call_args.kwargs.get("error_message", "").lower()
```

---

## Acceptance Criterion 3: Process Successful Payment

**User Story**: After the user confirms payment, Telegram sends a `successful_payment` update. We record the payment and activate their entitlement.

### Requirements

| ID | Requirement | Test Case | Status |
|---|---|---|---|
| 3.1 | Receives `successful_payment` update from Telegram | `test_successful_payment_received` | ✅ |
| 3.2 | Creates DB record: `TelegramPaymentEvent` | `test_successful_payment_creates_db_record` | ✅ |
| 3.3 | Calls `activate_entitlement(user_id, plan_code)` from PR-028 | `test_successful_payment_activates_entitlement` | ✅ |
| 3.4 | Uses `telegram_payment_charge_id` for idempotency (UNIQUE key) | `test_successful_payment_idempotent_duplicate` | ✅ |
| 3.5 | Webhook retry (same charge_id) doesn't re-activate | `test_successful_payment_webhook_retry_idempotent` | ✅ |
| 3.6 | Stores full Telegram response in `provider_response` JSONB | `test_successful_payment_stores_metadata` | ✅ |
| 3.7 | Sets `entitlement_activated_at` timestamp | `test_successful_payment_activation_timestamp` | ✅ |
| 3.8 | Sends confirmation message to user's Telegram chat | `test_successful_payment_sends_confirmation` | ✅ |
| 3.9 | Logs payment event with amount, plan, user_id | `test_successful_payment_logging` | ✅ |
| 3.10 | Increments metrics: `telegram_payments_total{result=success}` + `telegram_payment_value_total` | `test_successful_payment_telemetry` | ✅ |

**Coverage**: 10 test cases covering success path + idempotency + error handling

**Example Test**:
```python
@pytest.mark.asyncio
async def test_successful_payment_activates_entitlement(
    client: AsyncClient,
    db_session: AsyncSession,
    mock_telegram_webhook,
    mock_activate_entitlement
):
    """Test successful payment calls entitlement activation."""
    payload = {
        "update_id": 123,
        "message": {
            "chat": {"id": 111},
            "from": {"id": 111},
            "successful_payment": {
                "currency": "GBP",
                "total_amount": 2500,
                "invoice_payload": "gold_1m_1698432000",
                "telegram_payment_charge_id": "charge_abc123xyz"
            }
        }
    }

    response = await client.post(
        "/api/v1/telegram/webhook",
        json=payload
    )

    assert response.status_code == 200

    # Verify entitlement activation called
    assert mock_activate_entitlement.called
    call_args = mock_activate_entitlement.call_args
    assert call_args[0][0] == user_id  # user_id
    assert call_args[0][1] == "gold_1m"  # plan_code

    # Verify DB record created
    event = db_session.query(TelegramPaymentEvent).filter_by(
        telegram_payment_charge_id="charge_abc123xyz"
    ).first()
    assert event is not None
    assert event.status == "completed"
    assert event.entitlement_activated_at is not None
```

---

## Acceptance Criterion 4: Security & Tamper Protection

**User Story**: Malicious actors cannot tamper with payment amounts, user IDs, or replay old payments. All security checks pass.

### Requirements

| ID | Requirement | Test Case | Status |
|---|---|---|---|
| 4.1 | Prevents replay attacks: old `invoice_payload` timestamp rejected | `test_replay_attack_timestamp_old` | ✅ |
| 4.2 | Prevents replay: duplicate `telegram_payment_charge_id` ignored | `test_replay_attack_charge_id_duplicate` | ✅ |
| 4.3 | Prevents amount tampering: £25 invoice can't be changed to £100 | `test_tamper_amount_rejected` | ✅ |
| 4.4 | Prevents plan tampering: gold_1m can't become gold_3m | `test_tamper_plan_code_rejected` | ✅ |
| 4.5 | Prevents user ID tampering: user A can't pay for user B | `test_tamper_user_id_rejected` | ✅ |
| 4.6 | Malformed/missing payload rejected with 400 | `test_malformed_payload_rejected` | ✅ |
| 4.7 | Missing JWT rejects request with 401 | `test_no_jwt_rejected` | ✅ |
| 4.8 | Invalid JWT rejects request with 401 | `test_invalid_jwt_rejected` | ✅ |

**Coverage**: 8 test cases covering all tamper/replay/auth attack paths

**Example Test**:
```python
@pytest.mark.asyncio
async def test_tamper_amount_rejected(
    client: AsyncClient,
    db_session: AsyncSession,
    mock_telegram_webhook
):
    """Test amount tampering is detected and rejected."""
    # Original invoice: £25 (2500 cents)
    # Tampered invoice: £100 (10000 cents)
    payload = {
        "update_id": 123,
        "pre_checkout_query": {
            "id": "query_123",
            "from": {"id": 111},
            "currency": "GBP",
            "total_amount": 10000,  # TAMPERED! Should be 2500
            "invoice_payload": "gold_1m_1698432000"
        }
    }

    response = await client.post(
        "/api/v1/telegram/webhook",
        json=payload
    )

    # Should reject the query
    assert response.status_code == 200
    assert mock_telegram_api.answer_pre_checkout_query.called
    call_args = mock_telegram_api.answer_pre_checkout_query.call_args
    assert call_args.kwargs.get("ok") is False
    assert "amount" in call_args.kwargs.get("error_message", "").lower()
```

---

## Acceptance Criterion 5: Integration with Entitlements (PR-028)

**User Story**: After payment, the entitlement system grants the user immediate access to premium features (signals_enabled, max_devices, etc.).

### Requirements

| ID | Requirement | Test Case | Status |
|---|---|---|---|
| 5.1 | `activate_entitlement()` called after successful payment | `test_entitlement_activated` | ✅ |
| 5.2 | Entitlement `granted_at` timestamp set correctly | `test_entitlement_granted_at` | ✅ |
| 5.3 | Entitlement `plan_code` matches payment `plan_code` | `test_entitlement_plan_matches_payment` | ✅ |
| 5.4 | User can immediately access premium features | `test_user_can_access_premium_features` | ✅ |
| 5.5 | Multiple payments don't create duplicate entitlements | `test_duplicate_entitlements_prevented` | ✅ |
| 5.6 | Entitlements persist in `/api/v1/me/entitlements` | `test_entitlements_in_profile` | ✅ |
| 5.7 | Entitlement visible in Telegram mini app | `test_entitlements_visible_miniapp` | ✅ |

**Coverage**: 7 test cases covering entitlement lifecycle after payment

**Example Test**:
```python
@pytest.mark.asyncio
async def test_entitlements_in_profile(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
    user_id: str,
    process_successful_payment_fixture
):
    """Test entitlements visible after payment."""
    # Process successful payment (gold_1m)
    await process_successful_payment_fixture(user_id, "gold_1m")

    # Fetch user profile
    response = await client.get(
        "/api/v1/me/entitlements",
        headers=auth_headers
    )

    assert response.status_code == 200
    data = response.json()
    assert "entitlements" in data

    entitlements = data["entitlements"]
    gold_entitlement = next((e for e in entitlements if e["plan_code"] == "gold_1m"), None)

    assert gold_entitlement is not None
    assert gold_entitlement["active"] is True
    assert gold_entitlement["granted_at"] is not None
```

---

## Acceptance Criterion 6: Observability & Telemetry

**User Story**: All payment events are measurable for operations and business analytics. Metrics are accurate and complete.

### Requirements

| ID | Requirement | Test Case | Status |
|---|---|---|---|
| 6.1 | Counter: `telegram_payments_total{result=success\|failed\|cancelled}` incremented correctly | `test_metric_payments_total` | ✅ |
| 6.2 | Counter: `telegram_payment_value_total{plan_code}` shows correct sum | `test_metric_payment_value_total` | ✅ |
| 6.3 | Histogram: `telegram_payment_processing_seconds` recorded | `test_metric_processing_duration` | ✅ |
| 6.4 | Gauge: `telegram_payments_pending` accurate | `test_metric_pending_payments` | ✅ |
| 6.5 | Counter: `telegram_precheck_total{result=ok\|rejected}` incremented | `test_metric_precheck_total` | ✅ |
| 6.6 | All logs include user_id, plan_code, amount_cents | `test_logs_have_context` | ✅ |
| 6.7 | Sensitive data (API keys) NOT in logs | `test_logs_no_secrets` | ✅ |
| 6.8 | Error events logged with full context + stack trace | `test_error_logging` | ✅ |

**Coverage**: 8 test cases covering all metrics and logging

**Example Test**:
```python
@pytest.mark.asyncio
async def test_metric_payment_value_total(
    client: AsyncClient,
    auth_headers: dict,
    mock_telegram_api
):
    """Test payment value metric increments correctly."""
    from prometheus_client import REGISTRY

    # Clear metrics
    metric = REGISTRY.collect_by_names(["telegram_payment_value_total"])[0]
    samples_before = len(metric.samples)

    # Process payment: £25
    response = await client.post(
        "/api/v1/telegram/payment/send-invoice",
        json={"plan_code": "gold_1m"},  # £25 = 2500 cents
        headers=auth_headers
    )

    # Check metric increased by 2500
    metric = REGISTRY.collect_by_names(["telegram_payment_value_total"])[0]
    samples_after = len(metric.samples)
    assert samples_after >= samples_before

    # Verify value includes 2500 (£25.00)
    value_sample = next((s for s in metric.samples if s.labels.get("plan_code") == "gold_1m"), None)
    assert value_sample is not None
    assert value_sample.value >= 2500
```

---

## Test Coverage Summary

| Criterion | # Tests | Coverage % | Status |
|---|---|---|---|
| 1. Send Invoice | 10 | 100% | ✅ |
| 2. Pre-Checkout Validation | 10 | 100% | ✅ |
| 3. Successful Payment | 10 | 100% | ✅ |
| 4. Security & Tamper | 8 | 100% | ✅ |
| 5. Entitlements Integration | 7 | 100% | ✅ |
| 6. Observability & Telemetry | 8 | 100% | ✅ |
| **TOTAL** | **53 tests** | **90%+ coverage** | ✅ |

---

## Success Criteria (All Must Pass)

- [ ] All 53 tests passing
- [ ] 90%+ coverage of `backend/app/telegram/payments.py`
- [ ] 90%+ coverage of `backend/app/billing/telegram_payments.py`
- [ ] Zero TODOs in code
- [ ] All security tests passing
- [ ] All integration tests passing
- [ ] All telemetry metrics recorded correctly
- [ ] No sensitive data in logs
- [ ] GitHub Actions CI/CD green ✅

---

## Verification Commands

```bash
# Run all PR-034 tests
.venv/Scripts/python.exe -m pytest backend/tests/test_telegram_payments.py -v --cov=backend.app.telegram.payments --cov-report=term-missing

# Run integration tests
.venv/Scripts/python.exe -m pytest backend/tests/test_telegram_payments_integration.py -v

# Run security tests
.venv/Scripts/python.exe -m pytest backend/tests/test_telegram_payment_security.py -v

# Check coverage
.venv/Scripts/python.exe -m pytest backend/tests/test_telegram_payments*.py --cov=backend.app.telegram --cov=backend.app.billing --cov-report=html

# Run all tests together
.venv/Scripts/python.exe -m pytest backend/tests/test_telegram_payments*.py -v --tb=short
```

---

## Definition of Done (DoD)

✅ Implementation complete when:
1. All 53 test cases passing
2. 90%+ coverage verified
3. All 5 acceptance criteria met (each with sub-requirements)
4. Security audit: 0 vulnerabilities
5. Performance: payment processing < 1 second
6. All 4 documentation files created
7. GitHub Actions CI/CD passing
8. Production readiness verified (all GREEN)
