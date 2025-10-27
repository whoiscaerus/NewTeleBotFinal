# PR-034 Implementation Plan: Telegram Native Payments

**Status**: Planning Phase ✅
**Date**: October 27, 2025
**Target Completion**: October 28, 2025 (2-3 hours)
**Depends On**: PR-033 (Stripe) ✅, PR-028 (Entitlements) ✅, PR-026 (Telegram Webhook) ✅

---

## 📋 Overview

Implement **Telegram native payments** as an **alternative to Stripe** for in-app purchases. Users can choose between:

1. **Stripe Checkout** (PR-033) → Browser-based, more payment methods
2. **Telegram Payments** (PR-034) → In-app native, seamless experience

Both flow to the same **Entitlements** system (PR-028), ensuring unified billing logic.

---

## 🎯 Goals

**Primary**:
- Enable users to purchase plans directly within Telegram using native Telegram Payment flow
- Seamless integration with PR-033 Stripe backend (same entitlements, same catalog)
- Alternative payment method → increased conversion (especially mobile/developing markets)

**Secondary**:
- Reduce dependency on external checkout flows
- Support multiple payment providers simultaneously
- Maintain audit trail of all payment events

---

## 📁 File Structure

```
backend/app/telegram/
  ├── payments.py                    # NEW: Core Telegram payment handler
  └── handlers/
      └── shop.py                    # NEW/MODIFY: /buy command with payment choice

backend/app/billing/
  └── telegram_payments.py           # NEW: Integration with entitlements (PR-028)

backend/alembic/versions/
  └── 0010_telegram_payments.py      # NEW: Database migration

backend/tests/
  ├── test_telegram_payments.py      # NEW: Payment handler tests (25+ tests)
  ├── test_telegram_payments_integration.py  # NEW: End-to-end flow tests
  └── test_telegram_payment_security.py      # NEW: Security & tamper tests

docs/prs/
  ├── PR-034-IMPLEMENTATION-PLAN.md  # This file ✅
  ├── PR-034-ACCEPTANCE-CRITERIA.md  # To be created
  ├── PR-034-BUSINESS-IMPACT.md      # To be created
  └── PR-034-IMPLEMENTATION-COMPLETE.md  # To be created
```

---

## 🏗️ Architecture

### Payment Flow Diagram

```
User in Telegram
    ↓
/buy command
    ↓
    +─────────────────────────────┬──────────────────────────┐
    ↓                             ↓                          ↓
Choose Plan            Select Payment Method         Cancel
    ↓                             ↓
[Plans List]     ┌────────────────┼────────────────┐
Gold 1m = £25    │                │                │
Silver 3m = £60  ↓                ↓                ↓
...         [Stripe]        [Telegram Pay]    [Cancel]
                ↓                ↓
            Send to           send_invoice()
            /checkout        ↓
            (PR-033)      Telegram User Confirms
                          ↓
                      process_webhook()
                          ↓
                    ✅ activate_entitlement()
                          ↓
                    Notify user → /me/entitlements
```

### Data Flow

```
1. User /buy → shop handler lists available payment methods
2. User chooses "Telegram Pay" → send_invoice() to Telegram API
3. Telegram sends pre_checkout_query → validate_pre_checkout()
   - Check amount matches catalog
   - Check user can purchase (not already premium, etc.)
4. User confirms payment in Telegram → successful_payment update
5. Backend receives successful_payment webhook
   - Verify payload signature + amount
   - Activate entitlement (calls PR-028)
   - Log to TelegramPaymentEvent table
   - Send confirmation message to user
```

---

## 📊 Database Schema

### New Table: `telegram_payment_events`

```sql
CREATE TABLE telegram_payment_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- User & Telegram IDs
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    telegram_user_id BIGINT NOT NULL,
    telegram_chat_id BIGINT NOT NULL,

    -- Payment Identifiers
    telegram_payment_charge_id VARCHAR(255) UNIQUE NOT NULL,  -- From telegram
    invoice_payload VARCHAR(255) NOT NULL,                    -- plan_code + timestamp

    -- Amount & Plan
    amount_cents INT NOT NULL,  -- 2500 = £25.00
    currency VARCHAR(3) NOT NULL DEFAULT 'GBP',
    plan_code VARCHAR(50) NOT NULL,  -- 'gold_1m', 'silver_3m'

    -- Status
    status VARCHAR(50) NOT NULL,  -- 'pending', 'completed', 'failed', 'cancelled'

    -- Provider Details
    provider_name VARCHAR(50) NOT NULL DEFAULT 'telegram',
    provider_response JSONB,  -- Full response from Telegram

    -- Entitlement Activation
    entitlement_activated_at TIMESTAMP,
    entitlement_id UUID REFERENCES entitlements(id),

    -- Audit
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Indexes
    KEY idx_telegram_payment_events_user_id (user_id),
    KEY idx_telegram_payment_events_status (status),
    KEY idx_telegram_payment_events_created_at (created_at),
    UNIQUE KEY idx_telegram_payment_events_charge_id (telegram_payment_charge_id)
);
```

### Indexes
- `(user_id, created_at)` - Query user's payment history
- `(status, created_at)` - Find pending payments
- `(telegram_payment_charge_id)` - Idempotency (prevent duplicates)

---

## 🔌 API Endpoints

### Backend Endpoints (Internal)

#### 1. **POST `/api/v1/telegram/payment/webhook`** (Public, Telegram sends here)
- Receives Telegram `successful_payment` update
- Validates payload signature (from Telegram)
- Calls `_activate_entitlement(user_id, plan_code)`
- Returns `200 OK` to Telegram

Request body (from Telegram):
```json
{
  "update_id": 123456,
  "message": {
    "message_id": 789,
    "from": {"id": 111222, "is_bot": false},
    "chat": {"id": 111222, "type": "private"},
    "successful_payment": {
      "currency": "GBP",
      "total_amount": 2500,
      "invoice_payload": "gold_1m_1698432000",
      "telegram_payment_charge_id": "charge_telegram_abc123xyz"
    }
  }
}
```

#### 2. **POST `/api/v1/telegram/payment/pre-checkout`** (Telegram calls during checkout confirmation)
- Validates user's pre-checkout query (before charging)
- Checks amount matches catalog price
- Returns `ok: true` or `ok: false` + error message

---

## 🔐 Security Considerations

### 1. **Payload Validation**
- Parse `invoice_payload` → extract `plan_code` + `timestamp`
- Verify timestamp is recent (< 1 hour old) to prevent replay
- Validate amount matches `STRIPE_PRICE_MAP_JSON[plan_code]`
- Reject if amounts don't match (prevents tampering)

### 2. **Telegram Webhook Verification**
- Telegram sends updates via webhook; no signature on updates themselves
- Use `bot_token` to verify identity (already secured via TLS)
- Optional: Verify `from.id` is the authenticated user

### 3. **Idempotency**
- `telegram_payment_charge_id` is UNIQUE in DB
- On webhook retries → duplicate insert fails gracefully
- Return success immediately (don't re-activate)

### 4. **Rate Limiting**
- Max 5 payment attempts per user per minute
- Prevent spam/brute force attempts

### 5. **Entitlement Activation**
- Calls PR-028 `activate_entitlement()` which is idempotent
- Same payment won't double-activate premium features

---

## 🔧 Environment Variables

```bash
# Telegram Payment Configuration
TELEGRAM_PAYMENT_PROVIDER_TOKEN="<provider_token>"        # From PSP (Stripe, etc.)
TELEGRAM_PAYMENT_CURRENCY="GBP"                           # Default currency
TELEGRAM_PAYMENT_ENABLED=true                             # Feature flag

# Plan Pricing (inherited from PR-028)
# Already defined in STRIPE_PRICE_MAP_JSON, reuse same prices
```

---

## 📈 Telemetry (Prometheus Metrics)

```python
# Counter: Total payment attempts
telegram_payments_total = Counter(
    'telegram_payments_total',
    'Total Telegram payment attempts',
    ['result', 'plan_code']  # result: success, failed, cancelled
)

# Counter: Payment value sum (business metric)
telegram_payment_value_total = Counter(
    'telegram_payment_value_total',
    'Total value of Telegram payments (pence)',
    ['plan_code', 'currency']
)

# Histogram: Payment processing latency
telegram_payment_processing_seconds = Histogram(
    'telegram_payment_processing_seconds',
    'Time to process Telegram payment (invoke → entitlement)',
    buckets=[0.5, 1.0, 2.0, 5.0]
)

# Gauge: Pending payments
telegram_payments_pending = Gauge(
    'telegram_payments_pending',
    'Number of unresolved Telegram payments'
)

# Counter: Pre-checkout queries
telegram_precheck_total = Counter(
    'telegram_precheck_total',
    'Telegram pre-checkout queries',
    ['result']  # result: ok, rejected
)
```

---

## ✅ Test Plan (25+ Tests)

### Unit Tests (`test_telegram_payments.py`)

#### **Payment Handler Tests** (10 tests)
1. ✅ `test_send_invoice_valid_plan` - Happy path
2. ✅ `test_send_invoice_invalid_plan` - Unknown plan code
3. ✅ `test_send_invoice_amount_mismatch` - Price doesn't match catalog
4. ✅ `test_send_invoice_user_already_premium` - Can't purchase twice
5. ✅ `test_send_invoice_rate_limit` - Max attempts per minute
6. ✅ `test_validate_pre_checkout_ok` - Valid pre-checkout
7. ✅ `test_validate_pre_checkout_amount_mismatch` - Amount doesn't match
8. ✅ `test_validate_pre_checkout_invalid_payload` - Malformed payload
9. ✅ `test_handle_successful_payment_creates_event` - DB entry created
10. ✅ `test_handle_successful_payment_activates_entitlement` - Calls PR-028

### Integration Tests (`test_telegram_payments_integration.py`)

#### **Full Flow Tests** (8 tests)
1. ✅ `test_end_to_end_purchase_flow` - User buys plan, entitlement activated
2. ✅ `test_telegram_payment_with_notification` - User receives confirmation
3. ✅ `test_multiple_payments_same_user` - Different plans
4. ✅ `test_entitlement_persists_after_payment` - Data integrity
5. ✅ `test_payment_reconciliation` - DB audit trail complete
6. ✅ `test_parallel_payments` - Concurrent purchases don't conflict
7. ✅ `test_webhook_retry_idempotent` - Same webhook twice = no double-charge
8. ✅ `test_failed_entitlement_activation` - Graceful failure handling

### Security & Tamper Tests (`test_telegram_payment_security.py`)

#### **Security Tests** (7 tests)
1. ✅ `test_replay_attack_prevented` - Old timestamp rejected
2. ✅ `test_amount_tampering_rejected` - Modified amount rejected
3. ✅ `test_plan_code_tampering_rejected` - Modified plan rejected
4. ✅ `test_user_id_tampering_rejected` - Cross-user payment prevented
5. ✅ `test_malformed_payload_rejected` - Invalid JSON rejected
6. ✅ `test_rate_limit_enforced` - Spam attacks blocked
7. ✅ `test_duplicate_charge_id_idempotent` - No double-charging

---

## 🎯 Acceptance Criteria

### Criterion 1: Send Invoice
- ✅ `/api/v1/telegram/payment/send-invoice` accepts valid plan code
- ✅ Returns invoice ID from Telegram API
- ✅ Rejects unknown plans with 422
- ✅ Rejects if user already premium with 409

### Criterion 2: Validate Pre-Checkout
- ✅ Validates amount matches catalog price
- ✅ Returns `ok: true` for valid purchases
- ✅ Returns `ok: false` for tampered amounts
- ✅ Handles missing/malformed payload

### Criterion 3: Process Successful Payment
- ✅ Creates `TelegramPaymentEvent` in DB
- ✅ Calls `activate_entitlement()` from PR-028
- ✅ Idempotent on webhook retry (no double-activation)
- ✅ Sends confirmation message to user

### Criterion 4: Security & Validation
- ✅ Validates payload signature with Telegram
- ✅ Prevents replay attacks (timestamp validation)
- ✅ Prevents amount tampering (price reconciliation)
- ✅ Prevents user ID tampering (JWT validation)

### Criterion 5: Observability
- ✅ All metrics recorded (counters, histograms)
- ✅ Audit trail in DB (full event history)
- ✅ Error events logged with context
- ✅ No sensitive data in logs (amounts only, no API keys)

---

## 🔄 Implementation Phases

### Phase 1: Core Handler (30 minutes)
- [ ] Create `backend/app/telegram/payments.py`
- [ ] Implement `send_invoice(user_id, plan_code)`
- [ ] Implement `validate_pre_checkout(payload)`
- [ ] Implement `handle_successful_payment(update)`
- [ ] Add telemetry counters

### Phase 2: Webhook Integration (20 minutes)
- [ ] Create webhook endpoint in `backend/app/telegram/routes.py`
- [ ] Wire to Telegram update dispatcher
- [ ] Error handling + retry logic
- [ ] Logging with structured JSON

### Phase 3: Database & Entitlements (20 minutes)
- [ ] Create Alembic migration (0010)
- [ ] Create `TelegramPaymentEvent` SQLAlchemy model
- [ ] Create `telegram_payments.py` service (integrate with PR-028)
- [ ] Test idempotency

### Phase 4: Unit Tests (45 minutes)
- [ ] Write 25+ unit tests covering all happy paths + error cases
- [ ] Test tamper detection
- [ ] Test idempotency
- [ ] Verify 90%+ coverage

### Phase 5: Integration Tests (30 minutes)
- [ ] Write end-to-end flow tests
- [ ] Mock Telegram API responses
- [ ] Verify entitlement activation
- [ ] Test concurrent payments

### Phase 6: Shop Handler Update (15 minutes)
- [ ] Modify `/buy` command to show payment choice
- [ ] Add buttons for "Stripe" vs "Telegram Pay"
- [ ] Route to appropriate payment flow

### Phase 7: Documentation (45 minutes)
- [ ] Create PR-034-ACCEPTANCE-CRITERIA.md
- [ ] Create PR-034-BUSINESS-IMPACT.md
- [ ] Create PR-034-IMPLEMENTATION-COMPLETE.md
- [ ] Update `/docs/INDEX.md`

**Total: 2.5-3 hours**

---

## 🚀 Success Metrics

### Code Quality
- ✅ 90%+ test coverage (all modules)
- ✅ Zero TODOs or placeholders
- ✅ All functions have docstrings + type hints
- ✅ Black formatting compliant
- ✅ All security checks pass

### Testing
- ✅ 25+ tests, all passing
- ✅ All acceptance criteria verified
- ✅ Security tests for tampering/replay
- ✅ Integration tests passing

### Production Readiness
- ✅ Error handling on all external calls
- ✅ Logging with context (user_id, plan_code, amount)
- ✅ Idempotency enforced
- ✅ Rate limiting active
- ✅ Telemetry complete

### Documentation
- ✅ 4 documentation files created
- ✅ Business impact quantified
- ✅ All features documented
- ✅ Examples provided

---

## 📚 References & Dependencies

**Depends On**:
- ✅ PR-028 (Entitlements) - Call `activate_entitlement(user_id, plan_code)`
- ✅ PR-033 (Stripe) - Same catalog/pricing reused
- ✅ PR-026 (Telegram Webhook) - Uses same webhook infrastructure

**Referenced By**:
- PR-035 (Mini App) - Mini App users can choose Telegram Pay
- PR-045 (Copy-Trading) - Telegram Pay can be used for premium tiers

**Related Files**:
- `backend/app/billing/catalog.py` (PR-028) - Plan definitions
- `backend/app/telegram/routes.py` (PR-026) - Webhook router
- `backend/app/core/auth.py` - JWT verification for API

---

## 🎬 Quick Start Checklist

Before starting implementation:

- [ ] Read this plan end-to-end ✅
- [ ] Review PR-028 entitlements integration pattern
- [ ] Review PR-033 payment webhook pattern
- [ ] Verify Telegram Payment Provider token available
- [ ] Review test patterns from PR-031, PR-032, PR-033
- [ ] Setup local test with sandbox provider

---

**Next Action**: Begin **Phase 2A: Core Handler Implementation**
