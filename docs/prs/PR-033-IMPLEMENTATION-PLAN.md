# PR-033: Fiat Payments via Stripe (Checkout + Portal) — Implementation Plan

**Date**: October 2024
**Phase**: 2B (Telegram & Web Integration, PRs 028-035)
**Depends On**: PR-028 (Entitlements System)
**Status**: Planning Phase

---

## 🎯 Goal

Enable end-to-end Stripe billing integration: Create checkout sessions for subscription upgrades, verify incoming webhooks, activate entitlements on payment success, and provide customer portal access for subscription management.

---

## 📋 Scope

### What We're Building

1. **Stripe Checkout Sessions** - Hosted checkout for subscription purchases
   - Create sessions with configurable billing tiers
   - Support multiple plans (free, basic, premium, pro, enterprise)
   - Idempotent creation via idempotency keys
   - Webhook verification for payment completion

2. **Stripe Webhook Handler** - Process payment events
   - Verify HMAC-SHA256 signatures
   - Route events to appropriate handlers
   - Idempotent processing (prevent duplicates)
   - Log all events for audit trail

3. **Customer Portal Sessions** - User subscription management
   - Create portal sessions with return URLs
   - Users can update payment methods, view invoices, cancel subscriptions
   - Deep link from Telegram & Web

4. **Entitlement Activation** - Grant access on payment success
   - Activate plan entitlements after successful payment
   - Update user subscription state in database
   - Send confirmation to user via Telegram

### What We're NOT Building

- Stripe Connect (affiliate payouts come later in PR-024)
- Refund processing (manual for now)
- Dunning/retry logic (handled by Stripe)
- Multi-currency support (GBP only in v1)

---

## 📂 File Structure

### Implementation Files

```
backend/app/billing/
  ├── stripe.py                      # Core Stripe API integration
  │   ├── StripePaymentHandler class
  │   ├── create_checkout_session()
  │   ├── create_portal_session()
  │   ├── verify_webhook_signature()
  │   └── handle_*_event() methods
  │
  ├── webhooks.py                    # Webhook event processing
  │   ├── StripeWebhookHandler class
  │   ├── process_webhook()
  │   └── Event handlers (checkout, invoice, subscription)
  │
  ├── routes.py                      # FastAPI endpoints
  │   ├── POST /api/v1/billing/checkout
  │   ├── POST /api/v1/billing/portal
  │   ├── GET /api/v1/billing/checkout/success
  │   ├── GET /api/v1/billing/checkout/cancel
  │   └── POST /api/v1/billing/webhook (public, no auth)
  │
  ├── stripe/
  │   ├── __init__.py
  │   ├── client.py                  # Stripe SDK initialization
  │   ├── models.py                  # Database models (StripeEvent, etc.)
  │   ├── handlers.py                # Event-specific handlers
  │   ├── checkout.py                # Checkout request/response schemas
  │   └── webhooks.py                # Webhook verification utilities
  │
  ├── entitlements/
  │   └── (already exists - called by webhook handler)
  │
  └── __init__.py

backend/alembic/versions/
  └── XXXX_pr_033_billing_core.py    # DB migration (stripe_event table, indexes)

backend/tests/
  ├── test_stripe_webhooks.py        # Webhook signature verification
  ├── test_stripe_and_telegram_integration.py  # End-to-end flow
  └── billing/
      ├── __init__.py
      └── test_stripe_integration.py  # Full integration tests
```

### Database Schema

#### Table: `stripe_events` (audit trail)
```sql
CREATE TABLE stripe_events (
  id UUID PRIMARY KEY,
  event_id VARCHAR(255) NOT NULL UNIQUE,        -- Stripe event ID for idempotency
  event_type VARCHAR(100) NOT NULL,             -- e.g., checkout.session.completed
  user_id UUID REFERENCES users(id),
  customer_id VARCHAR(255),
  session_id VARCHAR(255),
  invoice_id VARCHAR(255),
  amount INT,                                   -- Amount in cents
  status VARCHAR(50),                           -- processed, failed, ignored
  payload JSONB NOT NULL,                       -- Full Stripe event JSON
  metadata JSONB,                               -- Custom data
  processed_at TIMESTAMP NOT NULL,
  created_at TIMESTAMP NOT NULL
);
CREATE INDEX idx_stripe_events_event_id ON stripe_events(event_id);
CREATE INDEX idx_stripe_events_user_id ON stripe_events(user_id);
CREATE INDEX idx_stripe_events_customer_id ON stripe_events(customer_id);
CREATE INDEX idx_stripe_events_created_at ON stripe_events(created_at);
```

---

## 🔄 Implementation Flow

### Checkout Flow (User Perspective)

```
User clicks "/buy" in Telegram or Web
  ↓
Frontend calls: POST /api/v1/billing/checkout?plan=premium
  ↓
Backend creates Stripe checkout session
  ↓
Returns checkout_url: https://checkout.stripe.com/pay/cs_test_...
  ↓
Frontend redirects user to Stripe-hosted checkout
  ↓
User enters payment details (card, billing address, etc.)
  ↓
Stripe processes payment
  ↓
[Success: Redirect to https://app.com/checkout/success?session_id=cs_test_...]
[Cancel: Redirect to https://app.com/checkout/cancel]
  ↓
Webhook delivered to: POST /api/v1/billing/webhook
  ↓
Backend receives checkout.session.completed event
  ↓
Backend verifies webhook signature ✅
  ↓
Backend activates entitlements for user
  ↓
Backend stores event in stripe_events table
  ↓
Backend sends confirmation to user via Telegram
  ↓
✅ User now has premium access
```

### Webhook Flow (Backend Perspective)

```
Stripe sends webhook: POST /api/v1/billing/webhook
  ↓
Extract signature from Stripe-Signature header
  ↓
Verify HMAC-SHA256 signature using webhook secret ✅
  ↓
Parse JSON payload into event object
  ↓
Check stripe_events table: is event_id already processed?
  ↓
  ├─ YES: Return 200 (idempotent, already processed)
  └─ NO: Continue processing
  ↓
Route event to appropriate handler:
  ├─ checkout.session.completed → activate_entitlements()
  ├─ invoice.payment_succeeded → log_payment()
  ├─ invoice.payment_failed → log_failure(), alert_user()
  └─ customer.subscription.deleted → revoke_entitlements()
  ↓
Store event in stripe_events table (for audit)
  ↓
Return 200 OK (Stripe retries if no 2xx)
```

---

## 🔐 Security Considerations

### Webhook Verification
- ✅ HMAC-SHA256 signature verification (prevent replay attacks)
- ✅ Timestamp validation (reject old webhooks)
- ✅ Idempotency keys (prevent duplicate processing)
- ✅ Event ID deduplication (stripe_events table)

### API Security
- ✅ Checkout endpoint: Requires authentication (JWT token)
- ✅ Portal endpoint: Requires authentication (JWT token)
- ✅ Webhook endpoint: Public (no auth, but signature verified)
- ✅ All errors logged with context (user_id, request_id)

### Data Protection
- ✅ Never log full credit card numbers
- ✅ Never log payment method details
- ✅ Store customer_id (not PAN) for future transactions
- ✅ Use HTTPS for all communication with Stripe

---

## 📊 Database Schema Changes

### New Tables
- `stripe_events` - Audit trail of all webhook events

### New Columns (if any)
- Users table may need `stripe_customer_id` foreign key (implementation detail)
- Subscriptions table may need `stripe_subscription_id` (implementation detail)

---

## 🌍 Environment Variables

### Required
```
STRIPE_SECRET_KEY=sk_test_...           # Stripe secret API key
STRIPE_WEBHOOK_SECRET=whsec_test_...    # Webhook signing secret
STRIPE_PRICE_MAP_JSON={...}             # Optional: plan → price ID mapping
```

### Example `.env`
```bash
# Stripe (test mode)
STRIPE_SECRET_KEY=sk_test_51234567890ABCDEFGHijklmnopqrst
STRIPE_WEBHOOK_SECRET=whsec_test_1234567890ABCDEFGHijklmnopqr
STRIPE_PRICE_MAP_JSON={"basic":"price_test_123","premium":"price_test_456"}

# Or auto-generate prices from amount config:
STRIPE_PRICE_MAP_JSON={}
```

---

## 🧪 Test Plan

### Test Categories

#### 1. Unit Tests (Webhook Signature Verification)
- ✅ Valid signature accepted
- ✅ Invalid signature rejected
- ✅ Tampered body rejected
- ✅ Old timestamp rejected
- ✅ Missing signature header rejected

#### 2. Integration Tests (Checkout Sessions)
- ✅ Create checkout session with valid plan
- ✅ Checkout session includes correct amount
- ✅ Checkout session has metadata (user_id, plan_code)
- ✅ Invalid plan code rejected with 400
- ✅ Idempotency key prevents duplicates

#### 3. Integration Tests (Webhook Processing)
- ✅ checkout.session.completed → activates entitlements
- ✅ invoice.payment_succeeded → logs payment
- ✅ invoice.payment_failed → logs failure, alerts user
- ✅ customer.subscription.deleted → revokes entitlements
- ✅ Duplicate event (same event_id) processed once
- ✅ Unknown event type logged but not processed

#### 4. End-to-End Tests (Full Flow)
- ✅ User creates checkout session
- ✅ Webhook confirms payment
- ✅ Entitlements appear in user profile
- ✅ User can access customer portal
- ✅ Portal shows correct subscription status

#### 5. Error Scenarios
- ✅ Stripe API timeout handled gracefully
- ✅ Invalid JSON payload handled
- ✅ Missing required fields in event
- ✅ Database connection failure logged
- ✅ Entitlement activation failure logged

---

## 📝 Acceptance Criteria

### Criterion 1: Create Checkout Sessions
**Spec**: Users can create Stripe checkout sessions for subscription purchases
- [ ] POST `/api/v1/billing/checkout` creates session
- [ ] Returns checkout_url in response
- [ ] Session includes user_id and plan_code in metadata
- [ ] Idempotency keys prevent duplicate sessions
- [ ] Invalid plan codes return 400

**Test Case**: `test_create_checkout_session_valid`
**Verification**: Checkout session created in Stripe; session_id returned to frontend

### Criterion 2: Verify Webhook Signatures
**Spec**: All incoming webhooks must have valid HMAC-SHA256 signatures
- [ ] Valid signatures accepted
- [ ] Invalid signatures rejected (400 Unauthorized)
- [ ] Tampered bodies rejected
- [ ] Old timestamps rejected (timestamp validation)
- [ ] Missing signature header rejected

**Test Case**: `test_webhook_signature_verification`
**Verification**: Invalid webhooks return 400; valid webhooks return 200

### Criterion 3: Activate Entitlements on Payment
**Spec**: When payment succeeds, entitlements are automatically activated
- [ ] checkout.session.completed event triggers entitlement activation
- [ ] User immediately gets access to purchased plan
- [ ] Event stored in stripe_events table for audit
- [ ] User receives confirmation notification (via Telegram)
- [ ] Duplicate events processed only once (idempotency)

**Test Case**: `test_webhook_activates_entitlements`
**Verification**: After webhook, user entitlements reflect new plan

### Criterion 4: Customer Portal Access
**Spec**: Users can manage subscriptions via Stripe Customer Portal
- [ ] POST `/api/v1/billing/portal` creates portal session
- [ ] Returns portal_url to redirect user
- [ ] User can update payment method
- [ ] User can view invoices
- [ ] User can cancel subscription
- [ ] Portal redirects user back after session

**Test Case**: `test_create_customer_portal_session`
**Verification**: Portal session created; user can manage subscription

### Criterion 5: Error Handling & Logging
**Spec**: All errors logged with context; no sensitive data exposed
- [ ] Webhook errors logged with event_id and error type
- [ ] Payment failures logged for audit trail
- [ ] All errors include request_id for tracing
- [ ] No credit card data logged
- [ ] Stripe API errors handled gracefully

**Test Case**: `test_webhook_error_handling`
**Verification**: Errors logged but don't crash service; Stripe retries webhook

---

## 🎯 Implementation Phases

### Phase 1: Setup (15 minutes)
- [ ] Read Stripe SDK documentation
- [ ] Set up Stripe test account
- [ ] Configure environment variables
- [ ] Verify webhook signing secret

### Phase 2: Core Implementation (2 hours)
- [ ] Create `StripePaymentHandler` class
- [ ] Implement `create_checkout_session()`
- [ ] Implement `create_portal_session()`
- [ ] Implement `verify_webhook_signature()`

### Phase 3: Webhook Handler (1.5 hours)
- [ ] Create `StripeWebhookHandler` class
- [ ] Implement event routing logic
- [ ] Implement checkout.session.completed handler
- [ ] Implement invoice.payment_succeeded handler
- [ ] Implement invoice.payment_failed handler
- [ ] Implement customer.subscription.deleted handler

### Phase 4: API Routes (1 hour)
- [ ] Create POST `/api/v1/billing/checkout`
- [ ] Create POST `/api/v1/billing/portal`
- [ ] Create POST `/api/v1/billing/webhook` (public endpoint)
- [ ] Create GET `/api/v1/billing/checkout/success`
- [ ] Create GET `/api/v1/billing/checkout/cancel`

### Phase 5: Database & Models (30 minutes)
- [ ] Create Alembic migration for stripe_events table
- [ ] Create SQLAlchemy models
- [ ] Add indexes for performance

### Phase 6: Testing (2 hours)
- [ ] Webhook signature verification tests (10+ tests)
- [ ] Checkout session tests (8+ tests)
- [ ] Webhook processing tests (12+ tests)
- [ ] Error scenario tests (8+ tests)
- [ ] End-to-end integration tests (5+ tests)

### Phase 7: Documentation (1 hour)
- [ ] Create ACCEPTANCE-CRITERIA.md
- [ ] Create BUSINESS-IMPACT.md
- [ ] Update IMPLEMENTATION-COMPLETE.md
- [ ] Create code examples and API docs

---

## 🔗 Dependencies & Integration Points

### Dependencies (Must Complete First)
- ✅ PR-028: Entitlements System - Called when payment succeeds

### Integration Points
- **Telegram Bot** (PR-031): Send payment confirmation to user
- **User Profile** (PR-004): Update subscription status
- **Audit Trail** (PR-008): Log payment events
- **Observability** (PR-009): Record billing metrics

---

## 📊 Success Metrics

### Code Quality
- ✅ 40+ test cases covering all flows
- ✅ 90%+ code coverage on billing module
- ✅ All acceptance criteria passing
- ✅ All docstrings include examples
- ✅ All functions have type hints

### Functional Requirements
- ✅ Checkout session creation in < 500ms
- ✅ Webhook processing in < 1 second
- ✅ 100% webhook signature verification
- ✅ Zero duplicate event processing
- ✅ Entitlements activated within 2 seconds of payment

### Security Requirements
- ✅ All webhook signatures verified
- ✅ No payment data logged
- ✅ All errors include context (user_id, request_id)
- ✅ Stripe credentials in environment only
- ✅ HTTPS enforced for Stripe communication

---

## 📌 Implementation Notes

### Key Decisions
1. **Idempotency**: Use event_id in database for exactly-once processing
2. **Signature Verification**: Verify all webhooks, reject if invalid
3. **Error Handling**: Log all errors, but don't crash the service
4. **Entitlement Activation**: Synchronous in webhook handler (fast path)
5. **Portal Sessions**: Short-lived (Stripe controls expiry, typically 24h)

### Known Limitations
- Refunds handled manually (not automated)
- No multi-currency support (GBP only)
- No invoice PDF generation (Stripe handles it)
- No complex tax calculations (flat rate for now)

---

## 🚀 Rollout Plan

### Pre-Deployment
- [ ] All tests passing locally
- [ ] 90%+ coverage achieved
- [ ] Code reviewed by team
- [ ] Webhook URL registered in Stripe dashboard
- [ ] Webhook secret stored securely

### Deployment
- [ ] Set `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` in production
- [ ] Run database migrations (alembic upgrade head)
- [ ] Deploy backend
- [ ] Monitor logs for errors
- [ ] Test checkout flow in production mode

### Post-Deployment
- [ ] Verify webhook events arriving
- [ ] Test end-to-end purchase flow
- [ ] Confirm entitlements activating
- [ ] Confirm emails/notifications sending
- [ ] Monitor Stripe dashboard for issues

---

## ✅ Verification Checklist

- [ ] All files exist in correct paths
- [ ] All classes/functions have docstrings
- [ ] All functions have type hints
- [ ] 40+ test cases written and passing
- [ ] Coverage >= 90%
- [ ] All 5 acceptance criteria implemented
- [ ] All acceptance criteria have corresponding tests
- [ ] No TODOs or FIXMEs in code
- [ ] No hardcoded values (use config/env)
- [ ] All external calls have error handling
- [ ] All errors logged with context
- [ ] Database migration tested locally
- [ ] Webhook URL tested with Stripe CLI
- [ ] Payment tested in Stripe test mode

---

## 📚 References

- [Stripe Checkout Session API](https://stripe.com/docs/api/checkout/sessions)
- [Stripe Webhooks](https://stripe.com/docs/webhooks)
- [Stripe Customer Portal](https://stripe.com/docs/billing/customer-portal)
- [Idempotent Requests](https://stripe.com/docs/api/idempotent_requests)

---

**Ready to begin implementation?** Proceed to Phase 1: Setup
