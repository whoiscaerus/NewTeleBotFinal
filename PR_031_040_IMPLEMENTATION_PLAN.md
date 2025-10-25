# PR-031-040 IMPLEMENTATION PLAN

**Date**: October 25, 2025
**Status**: Ready for Implementation
**Total PRs**: 10 features across payment & Mini App layers
**Estimated Time**: 20-24 hours
**Priority**: CRITICAL (payment + user engagement)

---

## 📋 EXECUTIVE SUMMARY

This phase implements the complete **payment & Mini App layer** for the trading platform. After successful Telegram shop/checkout in PR-027-030, now we add:

1. **Payments** (PR-031-032): Stripe webhooks + Telegram Stars alternative
2. **Telegram Polish** (PR-033-034): Marketing broadcasts + onboarding guides
3. **Mini App** (PR-035-040): Complete mobile web UI with auth, approvals, account linking, positions

**Key Achievement**: Users can pay via Stripe or Telegram Stars → get entitlement → trade via bot or Mini App

---

## 🔗 DEPENDENCY CHAIN

```
✅ PR-027-030 COMPLETE (Telegram webhook, catalog, pricing, shop)
    ↓
PR-031 (Stripe webhook)
    ↓
PR-032 (Telegram Stars) → [Parallel] PR-033-034 (Marketing/Guides)
    ↓
PR-035 (Mini App OAuth)
    ↓
PR-036 (Mini App Approvals) → [Parallel] PR-037 (Mini App Billing/Devices)
    ↓
PR-038 (Mini App Payment Hardening)
    ↓
PR-039 (Account Linking)
    ↓
PR-040 (Live Positions Display)
```

**Critical Path**: PR-031 → PR-032 → PR-035 → PR-036 → PR-037 → PR-038 → PR-039 → PR-040

---

## 📊 DATABASE SCHEMA CHANGES

### New Migrations Required: 3

#### Migration 010: Stripe Events & Idempotency
```sql
-- Track Stripe webhook events (idempotent processing)
CREATE TABLE stripe_events (
    id VARCHAR(36) PRIMARY KEY,
    event_id VARCHAR(255) UNIQUE NOT NULL,     -- Stripe event ID
    event_type VARCHAR(100) NOT NULL,          -- charge.succeeded, charge.failed, etc
    payment_method VARCHAR(50) NOT NULL,       -- 'stripe' or 'telegram_stars'
    customer_id VARCHAR(255),
    amount_cents INT NOT NULL,
    currency VARCHAR(3) DEFAULT 'USD',
    status INT DEFAULT 0,                       -- 0=pending, 1=processed, 2=failed
    idempotency_key VARCHAR(255),
    processed_at TIMESTAMP,
    error_message TEXT,
    webhook_timestamp TIMESTAMP NOT NULL,
    received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_event_id (event_id),
    INDEX idx_idempotency (idempotency_key),
    INDEX idx_status_created (status, created_at)
);

-- Account linking: User → MT5 account mapping
CREATE TABLE account_links (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    mt5_account_id VARCHAR(50) NOT NULL,
    mt5_login VARCHAR(50) NOT NULL,
    broker_name VARCHAR(100),                   -- e.g., "ICMarkets", "FXOpen"
    is_primary BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    verified_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE KEY unique_user_mt5 (user_id, mt5_account_id),
    INDEX idx_user_id (user_id),
    INDEX idx_mt5_login (mt5_login)
);

-- Account information cache (equity, drawdown, positions)
CREATE TABLE account_info (
    id VARCHAR(36) PRIMARY KEY,
    account_link_id VARCHAR(36) NOT NULL,
    balance DECIMAL(20,2),
    equity DECIMAL(20,2),
    free_margin DECIMAL(20,2),
    margin_used DECIMAL(20,2),
    margin_level DECIMAL(10,2),
    drawdown_percent DECIMAL(6,2),
    open_positions_count INT DEFAULT 0,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (account_link_id) REFERENCES account_links(id) ON DELETE CASCADE,
    INDEX idx_account_link_id (account_link_id)
);
```

#### Migration 011: Marketing & Broadcasts
```sql
CREATE TABLE broadcast_templates (
    id VARCHAR(36) PRIMARY KEY,
    admin_id VARCHAR(36) NOT NULL,
    title VARCHAR(255) NOT NULL,
    message_text TEXT NOT NULL,
    cta_button_text VARCHAR(100),
    cta_url VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (admin_id) REFERENCES users(id),
    INDEX idx_admin_id (admin_id)
);

CREATE TABLE broadcasts (
    id VARCHAR(36) PRIMARY KEY,
    template_id VARCHAR(36) NOT NULL,
    target_segment VARCHAR(100),                -- 'all', 'premium', 'free', 'vip'
    scheduled_at TIMESTAMP,
    sent_at TIMESTAMP,
    status INT DEFAULT 0,                       -- 0=draft, 1=scheduled, 2=sent, 3=failed
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (template_id) REFERENCES broadcast_templates(id),
    INDEX idx_status_scheduled (status, scheduled_at)
);

CREATE TABLE broadcast_analytics (
    id VARCHAR(36) PRIMARY KEY,
    broadcast_id VARCHAR(36) NOT NULL,
    user_id VARCHAR(36),
    delivered_at TIMESTAMP,
    viewed_at TIMESTAMP,
    cta_clicked_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (broadcast_id) REFERENCES broadcasts(id),
    FOREIGN KEY (user_id) REFERENCES users(id),
    INDEX idx_broadcast_id (broadcast_id),
    INDEX idx_user_id (user_id)
);
```

#### Migration 012: FAQ & Knowledge Base
```sql
CREATE TABLE knowledge_articles (
    id VARCHAR(36) PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    category VARCHAR(100),                     -- 'trading', 'billing', 'devices', 'general'
    content TEXT NOT NULL,
    search_keywords VARCHAR(500),
    language VARCHAR(10) DEFAULT 'en',
    is_published BOOLEAN DEFAULT FALSE,
    view_count INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_category (category),
    INDEX idx_language (language),
    FULLTEXT INDEX ft_content (title, content)
);
```

---

## 📁 DIRECTORY STRUCTURE

```
backend/
  app/
    billing/
      stripe/                           ← NEW
        __init__.py
        models.py                       ← Stripe event tracking
        webhooks.py                     ← Webhook handler (idempotent)
        handlers.py                     ← Event processors (charge.succeeded, etc)
        client.py                       ← Stripe API wrapper

    telegram/
      payments.py                       ← NEW (Telegram Stars integration)
      handlers/
        marketing.py                    ← NEW (Broadcast sending)
        guides.py                       ← NEW (Help/FAQ commands)

    marketing/                          ← NEW
      __init__.py
      broadcasts/
        models.py                       ← Broadcast, template models
        service.py                      ← Broadcast scheduling, sending
        routes.py                       ← Admin API for campaigns
      templates.py                      ← Template management
      cta.py                            ← CTA button tracking

    knowledge/                          ← NEW
      __init__.py
      models.py                         ← Knowledge article models
      service.py                        ← KB operations
      faq.py                            ← FAQ data + seeding

    oauth/                              ← NEW
      __init__.py
      mini_app.py                       ← OAuth bridge for Mini App
      schemas.py                        ← OAuth request/response models

    accounts/                           ← NEW
      __init__.py
      models.py                         ← Account link, account info
      service.py                        ← Account linking logic
      routes.py                         ← Link/unlink endpoints

    positions/                          ← NEW
      __init__.py
      service.py                        ← Live position fetching from MT5
      routes.py                         ← GET /positions endpoint
      schemas.py                        ← Position schemas

    billing/
      idempotency.py                    ← NEW (Idempotency for payments)

  alembic/
    versions/
      010_add_stripe_and_accounts.py
      011_add_marketing.py
      012_add_knowledge_base.py

frontend/
  src/app/
    miniapp/                            ← NEW
      layout.tsx                        ← Layout with tabs
      auth.tsx                          ← OAuth flow
      approvals.tsx                     ← Pending signal approvals
      billing.tsx                       ← Subscription/tier display
      devices.tsx                       ← Device management UI
      positions.tsx                     ← Live positions display
      payment.tsx                       ← Mini App payment form
      components/
        SignalCard.tsx                  ← Signal display component
        PositionCard.tsx                ← Position display component
        BillingStatus.tsx               ← Tier + expiry display
```

---

## 🔴 CRITICAL: PAYMENT IDEMPOTENCY

### The Problem
Stripe sends webhooks with retry logic (exponential backoff). If our handler crashes or network fails:
- Webhook retried by Stripe with same event_id
- Without idempotency: charge appears twice → duplicate entitlement → revenue loss

### The Solution (PR-031)
```python
# backend/app/billing/idempotency.py

@dataclass
class IdempotencyKey:
    key: str
    operation: str  # 'charge', 'refund', 'cancel'

async def process_idempotent(
    db: AsyncSession,
    idempotency_key: str,
    operation: str,
    process_fn: Callable,
    *args, **kwargs
):
    """Process with idempotency guarantee."""
    # 1. Check if already processed
    result = await db.execute(
        select(StripeEvent).where(
            StripeEvent.idempotency_key == idempotency_key
        )
    )
    existing = result.scalars().first()

    if existing and existing.status == PROCESSED:
        return existing.result  # Return cached result

    # 2. Process
    try:
        result = await process_fn(*args, **kwargs)

        # 3. Mark as processed
        event.status = PROCESSED
        event.result = result
        await db.commit()

        return result
    except Exception as e:
        event.status = FAILED
        event.error_message = str(e)
        await db.commit()
        raise
```

---

## 🎯 IMPLEMENTATION PHASES

### PHASE 1: PAYMENT BACKEND (PR-031-032) — 3-4 hours

#### PR-031: Stripe Webhook Integration
**Files**: 4 backend + 1 migration

1. **backend/app/billing/stripe/__init__.py** (8 lines)
   - Exports: `StripeWebhookHandler`, `StripeClient`

2. **backend/app/billing/stripe/models.py** (45 lines)
   - `StripeEvent`: id, event_id, event_type, amount_cents, status, idempotency_key, processed_at, error_message
   - Properties: `is_processed`, `is_failed`

3. **backend/app/billing/stripe/webhooks.py** (100 lines)
   - `@router.post("/stripe/webhook")`
   - Signature verification: `verify_stripe_signature(body, sig_header, secret)`
   - Webhook routing: charge.succeeded, charge.failed, charge.refunded
   - Idempotent handling: check event_id before processing

4. **backend/app/billing/stripe/handlers.py** (150 lines)
   - `handle_charge_succeeded(event)`: Grant entitlement → call `grant_entitlement(user_id, entitlement_type)`
   - `handle_charge_failed(event)`: Log failure, send alert to user
   - `handle_charge_refunded(event)`: Revoke entitlement, audit

5. **backend/app/billing/stripe/client.py** (80 lines)
   - Stripe API wrapper: `create_payment_intent()`, `retrieve_charge()`, `retrieve_customer()`
   - Error handling: translate Stripe errors to domain errors

6. **Migration 010** (migration 010_add_stripe_and_accounts.py)
   - Creates: stripe_events, account_links, account_info tables
   - Indexes: event_id (unique), idempotency_key, status

**Test Scenarios**:
- ✅ Webhook with valid signature → processed
- ✅ Webhook with invalid signature → rejected (401)
- ✅ Duplicate event_id → idempotent (processed once)
- ✅ Charge succeeded → entitlement granted
- ✅ Charge failed → error logged, user notified

**Quality Gate**: 100% type hints, error handling on all Stripe calls, logging with user_id + event_id

---

#### PR-032: Telegram Payments (Stars)
**Files**: 1 backend

1. **backend/app/telegram/payments.py** (120 lines)
   - `handle_successful_payment()`: Same as Stripe (grant entitlement)
   - `handle_refund()`: Process refund
   - Integration with PR-031 handlers (same `grant_entitlement()` call)

**Key Difference**: Telegram Stars are first-party payments (no webhook signature verification needed, Telegram SDK handles it)

---

### PHASE 2: TELEGRAM POLISH (PR-033-034) — 2.5 hours

#### PR-033: Marketing & Broadcasting
**Files**: 4 backend

1. **backend/app/marketing/broadcasts/models.py** (60 lines)
   - `BroadcastTemplate`: title, message_text, cta_button_text, cta_url, is_active
   - `Broadcast`: template_id, target_segment, scheduled_at, sent_at, status
   - `BroadcastAnalytics`: user_id, delivered_at, viewed_at, cta_clicked_at

2. **backend/app/marketing/broadcasts/service.py** (180 lines)
   - `create_broadcast()`: Admin creates campaign
   - `schedule_broadcast()`: Queue for background task
   - `send_broadcast()`: Iterate users → send Telegram message with CTA
   - `track_cta_click()`: Log when user clicks button

3. **backend/app/marketing/broadcasts/routes.py** (80 lines)
   - `POST /api/v1/admin/broadcasts` (admin only)
   - `GET /api/v1/admin/broadcasts/{id}/analytics`
   - Authentication: admin role required

4. **backend/app/telegram/handlers/marketing.py** (60 lines)
   - `handle_broadcast_command()`: `/broadcast` admin command
   - Interface to broadcast service

**Test Scenarios**:
- ✅ Create broadcast template
- ✅ Schedule for future time
- ✅ Segment: send to premium users only
- ✅ Track CTA clicks
- ✅ Analytics shows delivery/view/click rates

---

#### PR-034: Guides & Onboarding
**Files**: 2 backend

1. **backend/app/knowledge/faq.py** (100 lines)
   - Static FAQ data: common questions (trading, billing, devices)
   - Seed with `--create-faq` command

2. **backend/app/telegram/handlers/guides.py** (80 lines)
   - `/help` command → show menu (trading, billing, devices, general)
   - User selects topic → fetch KB articles + send as Telegram message
   - Integration with `KnowledgeService` (created later in PR-053)

**Test Scenarios**:
- ✅ `/help` shows menu
- ✅ Select topic → relevant articles sent
- ✅ Search articles by keyword

---

### PHASE 3: MINI APP FRONTEND + BACKEND (PR-035-040) — 15+ hours

#### PR-035: Mini App OAuth & Initialization
**Files**: 2 backend + 2 frontend

**Backend**:

1. **backend/app/oauth/mini_app.py** (120 lines)
   - `@router.post("/oauth/mini_app/start")`
     - Input: `{ telegram_id, telegram_hash }`
     - Output: `{ qr_code_url, auth_code }`
   - `@router.post("/oauth/mini_app/callback")`
     - Input: `{ auth_code, signature }`
     - Output: `{ jwt_token, expires_in, user: { id, tier, is_premium } }`
   - Verification: HMAC-SHA256 (same as webhook verification)
   - Session creation: Short-lived JWT (15 min) + refresh token

2. **backend/app/oauth/schemas.py** (40 lines)
   - `MiniAppAuthRequest`, `MiniAppAuthResponse`

**Frontend** (`frontend/src/app/miniapp/`):

1. **auth.tsx** (150 lines)
   - OAuth flow: Open Telegram Login Widget → user approves → callback to backend
   - Store JWT in localStorage (production: httpOnly cookie)
   - Auto-redirect to `/miniapp/approvals` after auth

2. **layout.tsx** (80 lines)
   - Tab navigation: Approvals | Billing | Devices | Positions
   - Tab bar at bottom (mobile-optimized)
   - Protected routes: redirect to auth if no JWT

**Test Scenarios**:
- ✅ QR code generates
- ✅ OAuth callback validates signature
- ✅ JWT issued with 15-min expiry
- ✅ Refresh token extends session
- ✅ Tab navigation works
- ✅ Invalid JWT → redirect to auth

---

#### PR-036: Mini App Approvals UI
**Files**: 1 frontend + 1 backend

**Frontend**:

1. **frontend/src/app/miniapp/approvals.tsx** (180 lines)
   - Fetch pending signals: `GET /api/v1/approvals/pending` (Mini App specific endpoint)
   - Real-time updates: WebSocket or polling every 3 seconds
   - Signal card: instrument, side, entry price, SL, TP, signal time
   - Approve button: `POST /api/v1/approvals/{id}/approve` → remove from list
   - Reject button: `POST /api/v1/approvals/{id}/reject` → mark rejected

**Backend**:

1. **backend/app/telegram/api/approvals.py** (100 lines)
   - `GET /api/v1/approvals/pending` (new endpoint for Mini App)
   - Same as PR-022 approvals, but returns full signal details
   - Filter: only signals pending approval (not already approved/rejected)

**Test Scenarios**:
- ✅ Load pending signals
- ✅ Approve signal → API call succeeds → removed from list
- ✅ Reject signal → marked rejected
- ✅ Real-time updates work
- ✅ No signals → show "No pending approvals"

---

#### PR-037: Mini App Billing & Devices
**Files**: 2 frontend

1. **frontend/src/app/miniapp/billing.tsx** (120 lines)
   - Show current tier: Free / Premium / VIP / Enterprise
   - Subscription expiry countdown (if applicable)
   - Upgrade button: links to `/miniapp/payment` (PR-038)
   - Payment history: last 5 transactions

2. **frontend/src/app/miniapp/devices.tsx** (140 lines)
   - List linked devices
   - Device info: name, device_id, HMAC key (obfuscated), last seen
   - Add device: `POST /api/v1/devices/register`
   - Remove device: `DELETE /api/v1/devices/{id}`
   - Buttons: Unlink, View details

**Backend** (No changes for this PR — uses existing PR-025 devices API)

**Test Scenarios**:
- ✅ Display current tier + expiry
- ✅ Add device → generates new HMAC key
- ✅ Remove device → can no longer use for polling
- ✅ Device list updates in real-time

---

#### PR-038: Mini App Payment Hardening
**Files**: 1 backend + 1 frontend

**Backend**:

1. **backend/app/billing/idempotency.py** (80 lines)
   - `process_idempotent()`: Generic idempotency wrapper
   - Checks for duplicate `idempotency_key` before processing
   - Returns cached result if already processed
   - Used by: PR-031 (Stripe), PR-032 (Telegram Stars)

**Frontend**:

1. **frontend/src/app/miniapp/payment.tsx** (160 lines)
   - Show product tiers with pricing
   - Select tier → open payment form
   - Payment methods: Stripe + Telegram Stars
   - Error handling: network failure → retry with backoff
   - Success: show "Payment successful! Tier upgraded."
   - Idempotency: generate `idempotency_key` before submit → don't retry same key

**Payment Flow**:
```
User clicks "Upgrade to Premium"
  ↓
Show payment form (Stripe or Telegram Stars)
  ↓
Generate idempotency_key (UUIDv4)
  ↓
User enters payment details + clicks "Pay"
  ↓
Send to backend with idempotency_key
  ↓
Backend processes idempotently:
  - Check if key already processed
  - If yes: return cached result
  - If no: process, store result, return
  ↓
Frontend shows success/error
  ↓
Network failure? Retry with same idempotency_key
  → Backend returns cached result (no duplicate charge)
```

**Test Scenarios**:
- ✅ Submit payment → success
- ✅ Retry with same idempotency_key → same result (no double charge)
- ✅ Network failure → auto-retry
- ✅ Invalid tier → 400 error
- ✅ User not authenticated → 401 error

---

#### PR-039: Account Linking
**Files**: 3 backend + migration

1. **backend/app/accounts/models.py** (50 lines)
   - `AccountLink`: user_id, mt5_account_id, mt5_login, broker_name, is_primary, verified_at
   - `AccountInfo`: account_link_id, balance, equity, free_margin, drawdown_percent

2. **backend/app/accounts/service.py** (140 lines)
   - `link_account()`: User provides MT5 login credentials → verify → create link
   - `get_primary_account()`: Get active account for user
   - `get_all_accounts()`: List all linked accounts
   - Verification: Connect to MT5 via PR-011 `MT5SessionManager` → fetch account info
   - If successful: mark as `verified_at` = now

3. **backend/app/accounts/routes.py** (100 lines)
   - `POST /api/v1/accounts/link` (link new account)
   - `GET /api/v1/accounts` (list accounts)
   - `PUT /api/v1/accounts/{id}/primary` (set primary)
   - `DELETE /api/v1/accounts/{id}` (unlink)

4. **Migration 011** (create account_links, account_info tables)

**Test Scenarios**:
- ✅ Link valid MT5 account → verified
- ✅ Link invalid account → error "Account not found"
- ✅ Set primary account
- ✅ List all linked accounts
- ✅ Unlink account → can't trade from it

---

#### PR-040: Live Positions Display
**Files**: 2 backend + 1 frontend

**Backend**:

1. **backend/app/positions/service.py** (120 lines)
   - `get_live_positions(user_id, account_link_id)`: Query MT5 via PR-011, return positions
   - `fetch_account_equity(user_id)`: Get balance/equity/drawdown
   - Caching: 30-second TTL (positions update slowly)
   - Error handling: MT5 timeout → return cached, log error

2. **backend/app/positions/routes.py** (60 lines)
   - `GET /api/v1/positions` (user's primary account)
   - `GET /api/v1/accounts/{account_id}/positions` (specific account)
   - Response: `{ account_equity, account_balance, open_positions: [...] }`

**Frontend**:

1. **frontend/src/app/miniapp/positions.tsx** (150 lines)
   - Fetch positions on mount + auto-refresh every 10 seconds
   - Display: Account equity, balance, drawdown %
   - Position list: symbol, side, volume, entry price, current price, P&L
   - Color coding: Green if profit, red if loss
   - Click position → show details (SL, TP, time opened)

**Test Scenarios**:
- ✅ Load live positions from MT5
- ✅ Show equity + drawdown
- ✅ Auto-refresh every 10 seconds
- ✅ No positions → show "No open positions"
- ✅ MT5 timeout → show cached + warning
- ✅ P&L calculation correct

---

## 🧪 TESTING STRATEGY

### Backend Testing (Target: ≥90% coverage)

**PR-031 (Stripe)**:
- ✅ Webhook signature validation (valid + invalid)
- ✅ Idempotent processing (duplicate event_id)
- ✅ Charge succeeded → entitlement granted
- ✅ Charge failed → error logged
- ✅ Refund → entitlement revoked

**PR-032 (Telegram Stars)**:
- ✅ Successful payment → entitlement granted
- ✅ Refund handling

**PR-033 (Marketing)**:
- ✅ Create broadcast template
- ✅ Schedule broadcast
- ✅ Send to segment (premium only, all users)
- ✅ Track CTA clicks

**PR-034 (Guides)**:
- ✅ `/help` command shows menu
- ✅ Select topic → articles sent

**PR-035 (OAuth)**:
- ✅ OAuth flow completes
- ✅ JWT issued with correct expiry
- ✅ Invalid signature rejected
- ✅ Refresh token extends session

**PR-036-037-038**:
- ✅ Fetch pending approvals
- ✅ Approve/reject signals
- ✅ Display tier + expiry
- ✅ Add/remove devices
- ✅ Idempotent payment processing

**PR-039 (Account Linking)**:
- ✅ Link valid account
- ✅ Link invalid → error
- ✅ Set primary account
- ✅ List accounts
- ✅ Unlink account

**PR-040 (Positions)**:
- ✅ Fetch live positions
- ✅ Calculate P&L correctly
- ✅ Caching works (30s TTL)
- ✅ MT5 timeout → cached + warning

### Frontend Testing (Target: ≥70% coverage)

**PR-035-040 Mini App**:
- ✅ OAuth flow
- ✅ Tab navigation
- ✅ Load pending approvals
- ✅ Approve/reject signals
- ✅ Display tier + countdown
- ✅ Add/remove devices
- ✅ Payment form submission
- ✅ Load live positions
- ✅ Auto-refresh positions

---

## ⚠️ CRITICAL BLOCKERS & RISKS

| Risk | Mitigation |
|------|-----------|
| Stripe key leaks | Use PR-007 secrets provider, redact from logs |
| Payment duplicate charge | Idempotency via event_id + idempotency_key |
| Mini App auth timeout | Refresh token + auto-retry |
| MT5 position fetch slow | 30s cache + show last known + background refresh |
| Webhook signature invalid | Reject with 401, log for investigation |
| Account linking fails | Fallback: suggest user contact support |

---

## 📋 IMPLEMENTATION CHECKLIST

### Phase 1: Payment (PR-031-032)
- [ ] PR-031 backend complete
- [ ] Migration 010 creates tables
- [ ] Stripe webhook signature verification working
- [ ] Idempotent processing validated
- [ ] PR-032 Telegram Stars integration
- [ ] Black formatting ✅
- [ ] Ruff linting ✅
- [ ] MyPy type checking ✅
- [ ] Tests passing (≥90% coverage)

### Phase 2: Telegram Polish (PR-033-034)
- [ ] PR-033 broadcast service complete
- [ ] PR-034 guides/FAQ complete
- [ ] Migration 011 creates tables
- [ ] Marketing endpoints working
- [ ] `/help` command working
- [ ] All quality gates passing

### Phase 3: Mini App (PR-035-040)
- [ ] PR-035 OAuth flow complete
- [ ] PR-036 approvals UI complete
- [ ] PR-037 billing/devices UI complete
- [ ] PR-038 payment hardening complete
- [ ] PR-039 account linking complete
- [ ] PR-040 positions display complete
- [ ] Migration 012 (if needed) complete
- [ ] Frontend tests passing (≥70% coverage)
- [ ] All quality gates passing

### Final Steps
- [ ] All 10 PRs committed to main
- [ ] All migrations applied (head state verified)
- [ ] Documentation complete
- [ ] Session report generated

---

## 🔄 DEPENDENCIES VERIFICATION

Before starting implementation:
- ✅ PR-001-026: ✅ COMPLETE (foundation, trading, core APIs)
- ✅ PR-027-030: ✅ COMPLETE (Telegram webhook, catalog, pricing, shop)
- ✅ PR-004: ✅ COMPLETE (JWT/RBAC — needed for PR-035+ auth)
- ✅ PR-025: ✅ COMPLETE (device registry — needed for PR-037)
- ✅ PR-007: ✅ COMPLETE (secrets management — needed for Stripe/Telegram keys)
- ✅ PR-008: ✅ COMPLETE (audit logging — needed for payment tracking)
- ✅ PR-028: ✅ COMPLETE (entitlements — used by payment handlers)

**All dependencies satisfied. Ready to start.**

---

## 📈 EFFORT BREAKDOWN

| PR | Description | Effort | Status |
|----|-------------|--------|--------|
| PR-031 | Stripe webhooks | 2h | Not Started |
| PR-032 | Telegram Stars | 1.5h | Not Started |
| PR-033 | Marketing/broadcasts | 1.5h | Not Started |
| PR-034 | Guides/onboarding | 1h | Not Started |
| PR-035 | Mini App OAuth | 2h | Not Started |
| PR-036 | Mini App approvals | 2h | Not Started |
| PR-037 | Mini App billing/devices | 2h | Not Started |
| PR-038 | Mini App payment hardening | 1.5h | Not Started |
| PR-039 | Account linking | 1.5h | Not Started |
| PR-040 | Live positions | 2h | Not Started |
| **TOTAL** | **Payment + Mini App Layer** | **~17.5h** | **Not Started** |

---

**READY FOR IMPLEMENTATION. Starting with PR-031 (Stripe Webhooks).**
