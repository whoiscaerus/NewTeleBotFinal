# PR-024-026 Implementation Plan

**Date**: October 25, 2025
**Objective**: Implement Affiliate System, Device Registry, and Execution Store
**Estimated Time**: 4-5 hours
**Scope**: 1,150+ lines of production code across 3 PRs

---

## PR-024: Affiliate System (Referrals & Commission Tracking)

### Scope
- User referral link generation (unique tokens)
- Referrer/referred tracking with hierarchy
- Commission calculation (tiered)
- Payout processing (scheduled, status tracking)
- Commission ledger (transaction history)

### Files to Create
```
backend/app/affiliates/
├── __init__.py
├── models.py                (120 lines) - Affiliate, Referral, Commission, Payout models
├── schema.py                (100 lines) - Pydantic schemas for API
├── service.py               (350 lines) - Business logic (generate link, track, calculate)
└── routes.py                (80 lines)  - API endpoints

backend/alembic/versions/
└── 004_add_affiliates.py    (90 lines)  - Database migration
```

### Database Schema
```sql
CREATE TABLE affiliates (
    id STRING(36) PRIMARY KEY,
    user_id STRING(36) NOT NULL UNIQUE FK users.id,
    referral_token STRING(32) NOT NULL UNIQUE,
    commission_tier INT DEFAULT 0,
    total_commission FLOAT DEFAULT 0,
    paid_commission FLOAT DEFAULT 0,
    pending_commission FLOAT DEFAULT 0,
    created_at DATETIME,
    INDEX ix_affiliates_token(referral_token)
);

CREATE TABLE referrals (
    id STRING(36) PRIMARY KEY,
    referrer_id STRING(36) NOT NULL FK affiliates.user_id,
    referred_user_id STRING(36) NOT NULL UNIQUE FK users.id,
    status INT DEFAULT 0,               -- 0=pending, 1=activated
    created_at DATETIME,
    activated_at DATETIME,
    INDEX ix_referrals_referrer(referrer_id),
    INDEX ix_referrals_referred(referred_user_id)
);

CREATE TABLE commissions (
    id STRING(36) PRIMARY KEY,
    referrer_id STRING(36) NOT NULL FK users.id,
    referred_user_id STRING(36) NOT NULL FK users.id,
    trade_id STRING(36),
    amount FLOAT NOT NULL,
    tier INT NOT NULL,
    status INT DEFAULT 0,               -- 0=pending, 1=paid, 2=refunded
    created_at DATETIME,
    paid_at DATETIME,
    INDEX ix_commissions_referrer(referrer_id),
    INDEX ix_commissions_status(status)
);

CREATE TABLE commission_payouts (
    id STRING(36) PRIMARY KEY,
    referrer_id STRING(36) NOT NULL FK users.id,
    amount FLOAT NOT NULL,
    status INT DEFAULT 0,               -- 0=pending, 1=processing, 2=completed, 3=failed
    bank_account STRING(50),
    reference STRING(50),
    created_at DATETIME,
    paid_at DATETIME,
    INDEX ix_payouts_referrer(referrer_id),
    INDEX ix_payouts_status(status)
);
```

### Key Endpoints
- `POST /api/v1/affiliates/register` - Enable affiliate program
- `GET /api/v1/affiliates/link` - Get referral link
- `GET /api/v1/affiliates/stats` - Get earnings stats
- `POST /api/v1/affiliates/payout` - Request payout
- `GET /api/v1/affiliates/history` - Commission history

---

## PR-025: Device Registry & Polling Loop

### Scope
- Device registration with user linking
- HMAC key generation and management
- Polling endpoint for pending signals
- Multi-device support per user

### Files to Create
```
backend/app/clients/devices/
├── __init__.py
├── models.py                (100 lines) - Device model with HMAC key
├── schema.py                (80 lines)  - Device registration/update schemas
├── service.py               (180 lines) - Device lifecycle management
└── routes.py                (100 lines) - Registration, polling endpoints

backend/alembic/versions/
└── 005_add_devices.py       (80 lines)  - Database migration
```

### Database Schema
```sql
CREATE TABLE devices (
    id STRING(36) PRIMARY KEY,
    user_id STRING(36) NOT NULL FK users.id,
    device_name STRING(100),
    hmac_key STRING(64) NOT NULL UNIQUE,
    last_poll DATETIME,
    last_ack DATETIME,
    is_active BOOLEAN DEFAULT TRUE,
    created_at DATETIME,
    updated_at DATETIME,
    INDEX ix_devices_user(user_id),
    INDEX ix_devices_hmac(hmac_key)
);
```

### Key Endpoints
- `POST /api/v1/devices/register` - Register new device
- `GET /api/v1/devices` - List user's devices
- `DELETE /api/v1/devices/{id}` - Unlink device
- `GET /api/v1/devices/poll` - Fetch pending signals (with HMAC auth)

---

## PR-026: Execution Store (Device ACK/Fill Reports)

### Scope
- Device reports execution ACKs
- Device reports trade fills
- Reconcile with signals
- Update trade status

### Files to Create
```
backend/app/clients/exec/
├── __init__.py
├── models.py                (100 lines) - ExecutionRecord model
├── schema.py                (80 lines)  - Pydantic schemas
├── service.py               (150 lines) - ACK/fill processing logic
└── routes.py                (80 lines)  - ACK/fill endpoints

backend/alembic/versions/
└── 006_add_execution_store.py (80 lines) - Database migration
```

### Database Schema
```sql
CREATE TABLE execution_records (
    id STRING(36) PRIMARY KEY,
    device_id STRING(36) NOT NULL FK devices.id,
    signal_id STRING(36) NOT NULL FK signals.id,
    trade_id STRING(36),
    ack_type INT NOT NULL,             -- 0=ack, 1=fill, 2=error
    status_code INT,
    error_message STRING(500),
    fill_price FLOAT,
    fill_size FLOAT,
    created_at DATETIME,
    INDEX ix_exec_device(device_id),
    INDEX ix_exec_signal(signal_id),
    INDEX ix_exec_trade(trade_id)
);
```

### Key Endpoints
- `POST /api/v1/exec/ack` - Device ACKs signal received
- `POST /api/v1/exec/fill` - Device reports trade fill
- `GET /api/v1/exec/status/{signal_id}` - Query execution status

---

## Dependencies Verification

✅ **PR-024 depends on**:
- PR-010 (Database) ✅
- PR-004 (Auth/RBAC) ✅
- PR-008 (Audit) ✅

✅ **PR-025 depends on**:
- PR-010 (Database) ✅
- PR-004 (Auth/RBAC) ✅
- PR-007 (Secrets - for HMAC keys) ✅

✅ **PR-026 depends on**:
- PR-010 (Database) ✅
- PR-025 (Device registry) 🔲 (concurrent)
- PR-021 (Signals API) ✅
- PR-016 (Trade store) ✅

---

## Implementation Sequence

### Phase 1: Database Models & Schemas (30 min)
1. Create models for Affiliate, Referral, Commission, Payout
2. Create models for Device
3. Create models for ExecutionRecord
4. Create Pydantic schemas for all

### Phase 2: Business Logic Services (90 min)
1. AffiliateService: link generation, commission calculation, payout
2. DeviceService: registration, HMAC key generation, polling
3. ExecutionService: ACK/fill processing, reconciliation

### Phase 3: API Routes (60 min)
1. Affiliate routes: register, link, stats, payout, history
2. Device routes: register, list, delete, poll
3. Execution routes: ack, fill, status

### Phase 4: Database Migrations (30 min)
1. Migration 004: Affiliates tables
2. Migration 005: Devices table
3. Migration 006: Execution store table

### Phase 5: Linting & Commit (30 min)
1. Run pre-commit hooks
2. Fix any linting issues
3. Commit to GitHub
4. Push to main

---

## Testing Strategy (Next Phase)

**Unit Tests**:
- Affiliate link generation uniqueness
- Commission calculation correctness
- Device HMAC key uniqueness
- Execution reconciliation logic

**Integration Tests**:
- End-to-end referral flow (signup with link → commission calc → payout)
- Device registration → polling → ACK flow
- Execution fill reconciliation

**Acceptance Criteria** (from master doc):
- User can generate referral link
- Signup with referral link tracked
- Commission calculated and paid
- Device registers and gets HMAC key
- Device can poll for signals
- Device can report fills
- Fills reconcile with signals

---

## Code Quality Requirements

✅ All functions have docstrings + type hints
✅ All external calls wrapped in try/except with logging
✅ No TODOs or FIXMEs
✅ No hardcoded values (use settings)
✅ Input validation on all API endpoints
✅ Ownership verification (users see only their data)
✅ Proper exception chaining (`raise ... from e`)
✅ Security: HMAC validation for device polling

---

**Ready to begin implementation!**
