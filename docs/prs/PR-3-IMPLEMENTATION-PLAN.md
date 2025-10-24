# PR-3: Signals Domain v1 - Implementation Plan

**Status:** 🔄 IN PROGRESS  
**Depends on:** PR-2 ✅ COMPLETE  
**Priority:** HIGH  
**Estimated Effort:** 2 days  

---

## 🎯 Overview

Implement the core signals domain: accept trading signals from external producers (like DemoNoStoch), validate them, store in PostgreSQL with JSONB payload, and support HMAC signature verification for secure signal ingestion.

**Key Features:**
- ✅ Signal model with JSONB payload support
- ✅ HMAC-SHA256 signature validation
- ✅ Producer ID tracking
- ✅ Payload size limits
- ✅ Timestamp freshness validation (5-minute window)
- ✅ Comprehensive audit logging

---

## 📁 Files to Create

### 1. Database Layer

#### `backend/app/signals/models.py` (NEW)
SQLAlchemy model for Signal with:
- `id`: UUID PK (auto-generated)
- `instrument`: TEXT indexed (e.g., "XAUUSD", "EURUSD")
- `side`: SMALLINT indexed (0=buy, 1=sell)
- `time`: TIMESTAMPTZ indexed (signal creation time)
- `payload`: JSONB nullable (strategy data like RSI, Bollinger Bands)
- `version`: INT default 1 (signal format version)
- `status`: SMALLINT indexed (0=new, 1=queued, 2=closed)
- `created_at`: TIMESTAMPTZ default now()
- `updated_at`: TIMESTAMPTZ auto-updated on changes

**Indexes:**
- `ix_signals_instrument_time` (instrument, time)
- `ix_signals_status` (status)

#### `backend/alembic/versions/0002_signals.py` (NEW)
Alembic migration:
- Create `signals` table with all fields
- Add indexes
- Add `updated_at` trigger (PostgreSQL)

### 2. API Layer

#### `backend/app/signals/schemas.py` (NEW)
Pydantic models:

**`SignalCreate`**
```python
class SignalCreate(BaseModel):
    instrument: str  # Regex: ^[A-Z0-9._-]{2,20}$
    side: int        # 0 or 1 only
    time: datetime   # ISO8601 format
    payload: dict    # Optional, max 32KB
    version: int     # Default 1
```

**`SignalOut`**
```python
class SignalOut(BaseModel):
    id: str
    status: int
    created_at: datetime
```

#### `backend/app/signals/routes.py` (NEW)
FastAPI route:
```
POST /api/v1/signals
```

Headers:
- `X-Producer-Id`: string (required)
- `X-Timestamp`: ISO8601 (required if HMAC enabled)
- `X-Signature`: base64 (required if HMAC enabled)

Body: `SignalCreate`

Logic:
1. Validate headers (if HMAC enabled)
2. Validate payload structure
3. Check payload size (≤32KB)
4. Create signal in DB
5. Return 201 with `SignalOut`

#### `backend/app/signals/service.py` (NEW)
Helper functions:
- `create_signal(db, data, producer_id)` → Signal
- `validate_hmac_signature(body, timestamp, producer_id, signature, secret)` → bool
- `validate_signal_payload(payload)` → dict

### 3. Tests

#### `backend/tests/test_signals_routes.py` (NEW)
42+ test cases covering:

**Happy Path (3 tests)**
- ✅ Valid signal → 201 created
- ✅ Signal stored in DB correctly
- ✅ Response format matches SignalOut

**Validation (8 tests)**
- ✅ Invalid instrument (regex violation) → 422
- ✅ Invalid side (not 0 or 1) → 422
- ✅ Missing time field → 422
- ✅ Invalid ISO8601 time → 422
- ✅ Unknown fields in payload → 422
- ✅ Payload type invalid (not dict) → 422
- ✅ All field combos tested

**Payload Size (3 tests)**
- ✅ Valid 1KB payload → 201
- ✅ Valid 32KB payload → 201
- ✅ Oversized 33KB payload → 413

**HMAC Disabled (5 tests)**
- ✅ No HMAC headers → 201 (allowed)
- ✅ With HMAC headers but disabled → 201 (ignored)
- ✅ Producer ID optional when disabled
- ✅ Signature optional when disabled
- ✅ Timestamp optional when disabled

**HMAC Enabled (12 tests)**
- ✅ Valid signature → 201
- ✅ Missing X-Producer-Id → 401
- ✅ Missing X-Signature → 401
- ✅ Missing X-Timestamp → 401
- ✅ Invalid signature → 401
- ✅ Tampered body → 401
- ✅ Timestamp > 5 minutes old → 401
- ✅ Timestamp in future → 401
- ✅ Malformed base64 signature → 401
- ✅ Empty producer ID → 400
- ✅ Clock skew exactly 5 minutes → 201 (allowed)
- ✅ Clock skew 5.1 minutes → 401 (rejected)

**Database Integration (8 tests)**
- ✅ Signal persists across requests
- ✅ Timestamps auto-set correctly
- ✅ Status defaults to 0 (new)
- ✅ Version defaults to 1
- ✅ Payload stored as-is in JSONB
- ✅ Instrument indexed for queries
- ✅ Multiple signals don't conflict
- ✅ Concurrent signal creates don't deadlock

**Error Handling (4 tests)**
- ✅ DB connection error → 500
- ✅ Invalid JSON request body → 400
- ✅ Content-Type not application/json → 415
- ✅ Unknown route → 404

---

## 🔧 Implementation Sequence

### Phase 1: Database (30 min)
1. Create `backend/app/signals/models.py`
   - Define Signal SQLAlchemy model
   - All field types + constraints

2. Create `backend/alembic/versions/0002_signals.py`
   - Migration script
   - Indexes
   - Trigger

3. Run locally: `alembic upgrade head`

### Phase 2: Schemas (30 min)
1. Create `backend/app/signals/schemas.py`
   - SignalCreate with validators
   - SignalOut response model

2. Test with Pydantic: validate() calls

### Phase 3: Service (45 min)
1. Create `backend/app/signals/service.py`
   - `create_signal()` 
   - `validate_hmac_signature()`
   - `validate_signal_payload()`
   - Error handling + logging

### Phase 4: Routes (45 min)
1. Create `backend/app/signals/routes.py`
   - POST /api/v1/signals
   - Header parsing
   - HMAC validation flow
   - Payload size check
   - DB insert
   - Response format

2. Update `backend/app/orchestrator/main.py`
   - Include signals router: `app.include_router(signals_router, prefix="/api/v1")`

### Phase 5: Tests (2 hours)
1. Create `backend/tests/test_signals_routes.py`
   - All 42 test cases
   - Test fixtures for HMAC secrets
   - Parametrized tests for validation matrix

2. Run locally: `pytest backend/tests/test_signals_routes.py -v --cov=backend/app/signals`

3. Verify coverage ≥90%

### Phase 6: Documentation (45 min)
1. Create PR docs:
   - PR-3-ACCEPTANCE-CRITERIA.md (which tests verify what)
   - PR-3-BUSINESS-IMPACT.md (revenue/strategy)
   - PR-3-IMPLEMENTATION-COMPLETE.md (final checklist)

2. Create verification script: `scripts/verify/verify-pr-3.sh`

### Phase 7: CI/CD (15 min)
1. Local pre-commit:
   ```bash
   python -m black backend/
   ruff check backend/
   pytest backend/tests/ --cov=backend/app --cov-report=term-missing
   ```

2. Push to GitHub

3. Monitor Actions tab

---

## 📋 Environment Variables

Add to `.env` and `.env.example`:

```env
# Signals Configuration
SIGNALS_PAYLOAD_MAX_BYTES=32768
HMAC_PRODUCER_ENABLED=false
HMAC_PRODUCER_SECRET=your-secret-key-here-change-in-production
```

---

## 🔐 Security Considerations

1. **HMAC Validation**
   - Use SHA256
   - Canonical format: `{body}{timestamp}{producer_id}`
   - 5-minute clock skew window (not configurable, secure)

2. **Payload Sanitization**
   - Max 32KB (prevent DoS)
   - JSONB type ensures valid JSON
   - No code execution possible (just data)

3. **Logging**
   - Log signal ID, instrument, side (safe)
   - NEVER log raw payload values (security)
   - Log HMAC validation results (audit trail)

4. **Rate Limiting** (future PR)
   - Currently unlimited (add in PR-X)

---

## 🧪 Coverage Goals

- **Line Coverage:** ≥90% of `backend/app/signals/`
- **Branch Coverage:** All HMAC paths tested
- **Integration:** Database persistence verified

**Target:** 42 test cases, ~200 lines of test code

---

## 📊 Acceptance Criteria

Each test case maps to acceptance criterion:

| # | Criterion | Test(s) | Expected |
|---|-----------|---------|----------|
| 1 | Valid signal ingested | test_valid_signal | 201 + DB row |
| 2 | Invalid instrument rejected | test_invalid_instrument | 422 |
| 3 | Oversized payload rejected | test_oversized_payload | 413 |
| 4 | HMAC enabled → signature required | test_hmac_required | 401 |
| 5 | HMAC validation works | test_hmac_valid | 201 |
| 6 | Bad HMAC rejected | test_hmac_invalid | 401 |
| 7 | Clock skew enforced (5min) | test_clock_skew_5min | 201/401 |
| 8 | Payload stored in JSONB | test_payload_persisted | ✅ |
| 9 | Concurrent creates don't deadlock | test_concurrent_signals | ✅ |
| 10 | No raw payloads in logs | test_payload_not_logged | ✅ |

---

## ⚠️ Known Limitations

None identified at this stage. All requirements from spec are included.

---

## 🔄 Rollback Plan

If PR-3 needs revert:
1. `git revert <commit-hash>`
2. `alembic downgrade -1` (reverts signal table)
3. Tests automatically use new conftest.py (no cleanup needed)

---

## 📅 Timeline

**Estimated Total:** ~6 hours of focused work

- Phase 1 (DB): 30 min ✅
- Phase 2 (Schemas): 30 min ✅
- Phase 3 (Service): 45 min ✅
- Phase 4 (Routes): 45 min ✅
- Phase 5 (Tests): 2 hours ✅
- Phase 6 (Docs): 45 min ✅
- Phase 7 (CI/CD): 15 min ✅

---

## 📞 Questions / Blockers

None at planning stage. PR-2 (database) is complete and verified. All requirements clear.

**Next:** Begin Phase 1 - Database layer implementation.
