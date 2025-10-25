# READY FOR NEXT: PR-024-025 Implementation Plan

**Status**: ✅ PR-020-023 Complete and Committed
**Next Phase**: Ready to implement PR-024 & PR-025
**Estimated Time**: 4-5 hours total

---

## What's Ready to Start

### PR-024: Affiliate System (Referrals & Commission Tracking)
**Dependency**: PR-010 (DB), PR-004 (Auth/RBAC), PR-008 (Audit) - ✅ ALL COMPLETE

**Scope**:
- User referral links (unique tokens, tracking URLs)
- Referrer hierarchy (track who referred whom)
- Commission calculation (percentage-based, tiered)
- Payout processing (scheduled, status tracking)
- Referral statistics (conversion rates, earnings)
- Commission ledger (transaction history)

**Estimated Lines**: 600-800
**Key Components**:
- Referral model (user_id, referrer_id, status, created_at)
- Commission model (referrer_id, referred_user_id, amount, tier, paid_at)
- ReferralService (generate_link, track_signup, calculate_commission)
- PayoutService (calculate_earnings, process_payout, ledger)
- ReferralRoutes (GET earnings, POST payout request)

---

### PR-025: Telegram Bot Integration (Signal Notifications)
**Dependency**: PR-021 (Signals API), PR-017 (Telegram setup), PR-018 (Alerts) - ✅ ALL COMPLETE

**Scope**:
- Signal notifications to user's Telegram
- User approval workflow via Telegram (Reply with /approve or /reject)
- Performance updates (daily/weekly stats)
- Alert escalation (failed trades, drawdown warnings)
- Telegram command handling (/start, /stats, /portfolio, /settings)
- Rich formatted messages (performance tables, price alerts)

**Estimated Lines**: 800-1000
**Key Components**:
- TelegramSignalHandler (receive signal, format message, send notification)
- TelegramApprovalHandler (receive approval via message, validate, update DB)
- TelegramCommandHandler (/stats, /portfolio, /settings, /help)
- MessageFormatter (render performance table, price data, alerts)
- TelegramRoutes (webhooks, command processing)

---

## Current Project State

### Completed (P1A Core + P1B API Layer Start)
✅ PR-001-010: Foundation (DB, Auth, Config, Logging, Cache, Validation, etc.)
✅ PR-011-019: Trading Core (MT5, Data fetch, Strategy engine, Order building, Telegram setup, Alerts, Account mgmt)
✅ PR-020-023: API Layer Part 1 (Charting, Signals API, Approvals, Reconciliation)

### Ready to Start (P1B API Layer)
⏳ PR-024: Affiliate System
⏳ PR-025: Telegram Integration

### To Be Implemented (P2+)
📋 PR-026-040+: Dashboard, Admin, Payment, Advanced Features

---

## PR-024 Detailed Specification

### Files to Create
```
backend/app/affiliates/
├── __init__.py
├── models.py                (100 lines)
├── schema.py                (80 lines)
├── service.py               (400 lines)
├── routes.py                (150 lines)
└── payout.py                (180 lines)

backend/alembic/versions/
└── 004_add_affiliates.py    (80 lines)
```

### Database Schema
```sql
CREATE TABLE affiliates (
    id STRING(36) PRIMARY KEY,
    user_id STRING(36) NOT NULL UNIQUE FK,
    referral_token STRING(32) NOT NULL UNIQUE,
    commission_tier INT DEFAULT 0,
    total_commission FLOAT DEFAULT 0,
    paid_commission FLOAT DEFAULT 0,
    pending_commission FLOAT DEFAULT 0,
    created_at DATETIME
);

CREATE TABLE referrals (
    id STRING(36) PRIMARY KEY,
    referrer_id STRING(36) NOT NULL FK,
    referred_user_id STRING(36) NOT NULL UNIQUE FK,
    status INT DEFAULT 0,               -- 0=pending, 1=activated, 2=cancelled
    created_at DATETIME,
    activated_at DATETIME
);

CREATE TABLE commissions (
    id STRING(36) PRIMARY KEY,
    referrer_id STRING(36) NOT NULL FK,
    referred_user_id STRING(36) NOT NULL FK,
    trade_id STRING(36),
    amount FLOAT NOT NULL,
    tier INT NOT NULL,
    status INT DEFAULT 0,               -- 0=pending, 1=paid, 2=refunded
    created_at DATETIME,
    paid_at DATETIME
);

CREATE TABLE commission_payouts (
    id STRING(36) PRIMARY KEY,
    referrer_id STRING(36) NOT NULL FK,
    amount FLOAT NOT NULL,
    status INT DEFAULT 0,               -- 0=pending, 1=processing, 2=completed, 3=failed
    bank_account STRING(50),
    reference STRING(50),
    created_at DATETIME,
    paid_at DATETIME
);
```

### Key Endpoints
- `POST /api/v1/affiliates/register` - Enable affiliate program
- `GET /api/v1/affiliates/link` - Get referral link
- `GET /api/v1/affiliates/stats` - Get earnings stats
- `POST /api/v1/affiliates/payout` - Request payout
- `GET /api/v1/affiliates/history` - Commission history

---

## PR-025 Detailed Specification

### Files to Create
```
backend/app/telegram/
├── __init__.py
├── handlers.py              (400 lines) - Signal/Approval handlers
├── commands.py              (300 lines) - Command processing
├── formatter.py             (250 lines) - Message formatting
├── routes.py                (150 lines) - Webhook endpoints
└── utils.py                 (100 lines) - Utilities

backend/app/notifications/
├── __init__.py
└── telegram_service.py      (150 lines)
```

### Telegram Commands
- `/start` - Register/authenticate user
- `/stats` - Show daily performance
- `/portfolio` - List active signals
- `/approve <signal_id>` - Approve signal
- `/reject <signal_id>` - Reject signal
- `/settings` - Show preferences
- `/help` - Show help

### Notification Types
1. **Signal Notifications**: New signal received
2. **Approval Requests**: Action required from user
3. **Performance Updates**: Daily/weekly stats
4. **Trade Alerts**: Trade closed, SL/TP hit
5. **Drawdown Alerts**: 10%, 15%, 20% threshold crossings

### Message Format Examples
```
Signal Notification:
🟢 BUY XAUUSD
Entry: 1950.50
RSI: 75.5
Confidence: 85%

[Approve] [Reject]
```

```
Performance Update:
📊 Weekly Stats
Signals: 12 total, 8 approved, 5 executed
Win Rate: 60%
Profit: +$2,450
ROI: +12.3%
```

---

## Workflow for Next Session

### Phase 1: Discovery & Planning (30 min)
1. Read PR-024 spec from master document
2. Read PR-025 spec from master document
3. Create IMPLEMENTATION-PLAN.md
4. Verify dependencies
5. Create ACCEPTANCE-CRITERIA.md

### Phase 2: Database Design (15 min)
1. Extract schema for PR-024
2. Extract schema for PR-025
3. Create Alembic migrations (004, 005)
4. Create SQLAlchemy models

### Phase 3: Core Implementation (3 hours)
1. Implement PR-024 Affiliate System
   - Models, schemas, service
   - Routes and endpoints
   - Payout processing
2. Implement PR-025 Telegram Integration
   - Signal handlers
   - Command processing
   - Message formatting
   - Webhook routes

### Phase 4: Testing (1.5 hours)
1. Unit tests for affiliate logic
2. Unit tests for Telegram handlers
3. Integration tests
4. E2E tests (signal flow → telegram notification → approval)

### Phase 5: CI/CD & Documentation (45 min)
1. Fix linting issues
2. Commit to main
3. Push to GitHub
4. Create documentation

---

## Quick Reference: What's Already Built for PR-024-025

### Available for PR-024:
- User model (PR-004) ✅
- Database infrastructure (PR-010) ✅
- Authentication/RBAC (PR-004) ✅
- Audit logging (PR-008) ✅
- Error handling patterns ✅
- Transaction management ✅

### Available for PR-025:
- Telegram bot setup (PR-017) ✅
- Signal ingestion (PR-021) ✅
- Approval workflow (PR-022) ✅
- Alert system (PR-018) ✅
- Async task queue (Redis) ✅
- User preferences storage (PR-006) ✅

---

## Command to Start PR-024-025

When ready, run:
```bash
# Create planning document
git checkout main
git pull origin main

# Then request: "Implement PR-024 and PR-025"
```

---

## Estimated Impact

**PR-024 (Affiliate System)**:
- Enables user monetization path
- Growth via referral mechanism
- Revenue model for platform
- Reduces customer acquisition cost

**PR-025 (Telegram Integration)**:
- Pushes signals directly to users
- User approvals without web login
- Performance transparency
- Real-time alerts
- Significantly improves user engagement

---

## Success Criteria

### PR-024 Complete When:
✅ All affiliate endpoints functional
✅ Commission calculation verified
✅ Payout processing working
✅ ≥90% test coverage
✅ All acceptance criteria passing

### PR-025 Complete When:
✅ Telegram bot receiving signals
✅ User can approve/reject via Telegram
✅ Performance stats formatting correct
✅ All commands working
✅ ≥90% test coverage

---

**Status**: 🟢 **READY TO PROCEED WITH PR-024-025**

Say "Continue: Next PRs" or "Implement PR-024 and PR-025" to begin!
