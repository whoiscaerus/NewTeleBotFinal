# PR-4 Implementation Plan: Approvals Domain v1

**Status:** � PHASE 2-3: IMPLEMENTATION (90% COMPLETE)  
**Branch:** `feat/4-approvals-domain-v1`  
**Depends On:** ✅ PR-3 (Signals Domain)  
**Estimated Effort:** 2-3 days  
**Priority:** HIGH (blocks PR-5, PR-6)

---

## 📋 Executive Overview

### Goal
Allow authenticated users to approve/reject trading signals with consent versioning and audit trail (IP, user agent, timestamp).

### Key Features
- ✅ Signal approval/rejection tracking (decision: 0=approved, 1=rejected)
- ✅ Consent versioning for compliance
- ✅ Audit trail (IP address, user agent captured)
- ✅ Duplicate prevention (unique signal_id, user_id constraint)
- ✅ JWT authentication required
- ✅ Telemetry counter for approvals

### Business Value
- Users can granularly control signal execution
- Audit trail enables compliance audits
- Duplicate prevention prevents double approvals
- Opens path for user-configurable approval workflows (PR-6+)

---

## 📊 Implementation Scope

### Files to Create (8)
```
✅ backend/app/approvals/models.py         (Approval ORM model)
✅ backend/app/approvals/schemas.py        (Pydantic schemas)
✅ backend/app/approvals/routes.py         (API endpoints)
✅ backend/app/approvals/service.py        (Business logic)
✅ backend/alembic/versions/0003_approvals.py  (Database migration)
✅ backend/tests/test_approvals_routes.py  (Test suite)
✅ docs/prs/PR-4-IMPLEMENTATION-PLAN.md    (This file)
✅ docs/prs/PR-4-ACCEPTANCE-CRITERIA.md
✅ docs/prs/PR-4-BUSINESS-IMPACT.md
✅ docs/prs/PR-4-IMPLEMENTATION-COMPLETE.md
✅ scripts/verify/verify-pr-4.sh           (Verification script)
```

### Files to Update (1)
```
✅ backend/app/orchestrator/main.py        (Register approvals router)
```

### Database Schema
```sql
CREATE TABLE approvals (
    id UUID PRIMARY KEY,
    signal_id UUID NOT NULL REFERENCES signals(id),
    user_id UUID NOT NULL,
    device_id UUID NULL,  -- Future: device tracking
    decision SMALLINT NOT NULL,  -- 0=approved, 1=rejected
    consent_version TEXT NOT NULL,
    ip INET,
    ua TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX ix_approvals_signal_user ON approvals(signal_id, user_id);
CREATE INDEX ix_approvals_user_created ON approvals(user_id, created_at);
```

---

## 🔄 Phase-by-Phase Implementation

### PHASE 1: Planning (CURRENT - 30 minutes)
**Status:** 🔄 IN PROGRESS

**Tasks:**
- [x] Read full PR-4 spec from New_Master_Prs.md
- [x] Create this implementation plan
- [x] Identify database schema requirements
- [x] List all acceptance criteria
- [ ] **NEXT:** Move to Phase 2 (Database)

---

### PHASE 2: Database & Alembic (1 hour)
**Next Step**

**Tasks:**
1. Create migration: `backend/alembic/versions/0003_approvals.py`
   - Create approvals table with all columns
   - Add unique index on (signal_id, user_id)
   - Add index on (user_id, created_at)
   - Include foreign key to signals(id)

2. Create SQLAlchemy model: `backend/app/approvals/models.py`
   - Approval class with all fields
   - Relationships to Signal, User
   - Table args with indexes
   - Type hints on all fields
   - Docstring with usage examples

3. Test locally:
   ```bash
   cd backend
   alembic upgrade head
   # Verify table created in database
   ```

---

### PHASE 3: Core Implementation (2 hours)
**Then**

**3a. Schemas & Service Layer**

Create `backend/app/approvals/schemas.py`:
```python
class ApprovalRequest(BaseModel):
    """Request to approve/reject a signal."""
    signal_id: str = Field(..., min_length=36, max_length=36)
    decision: int = Field(..., ge=0, le=1)  # 0=approved, 1=rejected
    consent_version: str = Field(..., min_length=1, max_length=255)

class ApprovalOut(BaseModel):
    """Approval response."""
    approval_id: str
    status: str  # "approved" or "rejected"
```

Create `backend/app/approvals/service.py`:
```python
async def create_approval(
    db: AsyncSession,
    signal_id: str,
    user_id: str,
    decision: int,
    consent_version: str,
    ip: str,
    ua: str,
) -> Approval:
    """Create approval with duplicate checking."""
    # 1. Verify signal exists
    # 2. Check no duplicate approval (same signal_id, user_id)
    # 3. Create & store approval
    # 4. Log audit trail
    # 5. Return created approval
```

**3b. API Routes**

Create `backend/app/approvals/routes.py`:
```python
@router.post("/api/v1/approve", status_code=201)
async def create_approval(
    request: ApprovalRequest,
    current_user = Depends(get_current_user),  # Mock for now
    db: AsyncSession = Depends(get_db),
):
    """
    Approve or reject a signal.
    
    - Requires JWT authentication
    - Returns 404 if signal not found
    - Returns 409 if duplicate approval by same user
    - Returns 422 if validation fails
    - Returns 201 on success
    """
```

**3c. Register Router**

Update `backend/app/orchestrator/main.py`:
```python
from backend.app.approvals.routes import router as approvals_router
app.include_router(approvals_router)
```

---

### PHASE 4: Comprehensive Testing (1.5 hours)
**Then**

Create `backend/tests/test_approvals_routes.py`:

**Test Cases (15 total):**

1. **Happy Path (2 tests)**
   - `test_approve_signal_success` → 201, approval created
   - `test_reject_signal_success` → 201, rejection created

2. **Signal Validation (2 tests)**
   - `test_nonexistent_signal` → 404
   - `test_invalid_signal_id_format` → 422

3. **Duplicate Prevention (2 tests)**
   - `test_duplicate_approval_same_user` → 409
   - `test_approval_different_user_allowed` → 201

4. **Authentication (2 tests)**
   - `test_missing_jwt` → 401
   - `test_invalid_jwt` → 401

5. **Request Validation (3 tests)**
   - `test_missing_decision_field` → 422
   - `test_invalid_decision_value` → 422
   - `test_missing_consent_version` → 422

6. **Audit Trail (2 tests)**
   - `test_ip_captured_in_approval` → verify DB
   - `test_user_agent_captured` → verify DB

7. **Edge Cases (2 tests)**
   - `test_empty_consent_version` → 422
   - `test_long_consent_version` → accepted if <255 chars

**Coverage Target:** ≥90% of implementation files

---

### PHASE 5: Local CI/CD (30 minutes)
**Then**

**Verify Locally:**
```bash
# 1. Format code
python -m black backend/app/approvals backend/tests/test_approvals_routes.py

# 2. Lint code
ruff check backend/app/approvals backend/tests/test_approvals_routes.py

# 3. Run tests
python -m pytest backend/tests/test_approvals_routes.py -v --tb=short

# 4. Check coverage
python -m pytest backend/tests/ --cov=backend/app/approvals --cov-report=term-missing

# 5. Run all tests (including PR-1, PR-2, PR-3)
python -m pytest backend/tests/ -q --tb=no
# Must show: ≥86 total tests passing (71 existing + 15 new)
```

---

### PHASE 6: Documentation (45 minutes)
**Then**

**Create 4 Documents:**

1. **PR-4-ACCEPTANCE-CRITERIA.md**
   - List all 15 test cases
   - Map each to acceptance criterion
   - Document edge cases

2. **PR-4-BUSINESS-IMPACT.md**
   - Revenue impact (enables approval workflows → upsell)
   - User experience (granular control)
   - Compliance (audit trail)
   - Scalability (unique index prevents duplicates)

3. **PR-4-IMPLEMENTATION-COMPLETE.md**
   - Checklist of all 8 files created
   - Test results (15/15 passing)
   - Coverage percentage
   - Verification script status
   - Any deviations from plan

4. **PR-4-INDEX.md** (links to above)

---

### PHASE 7: Verification & Commit (30 minutes)
**Then**

**Verification Script:** Create `scripts/verify/verify-pr-4.sh`
```bash
#!/bin/bash

# 1. Create signal via PR-3 endpoint
# 2. Approve signal via PR-4 endpoint
# 3. Verify approval in database
# 4. Check audit trail (IP, UA)
# 5. Attempt duplicate → verify 409
# 6. Verify all tests passing

echo "✅ PR-4 Verification Complete"
```

**Final Commit:**
```bash
git add .
git commit -m "PR-4: Approvals Domain v1 - 15/15 tests passing (86/86 total)"
git push origin feat/4-approvals-domain-v1
```

---

## 📝 Acceptance Criteria (15 total)

| # | Criterion | Test Case | Status |
|----|-----------|-----------|--------|
| 1 | Approve signal → 201 | `test_approve_signal_success` | ⏳ TODO |
| 2 | Reject signal → 201 | `test_reject_signal_success` | ⏳ TODO |
| 3 | Nonexistent signal → 404 | `test_nonexistent_signal` | ⏳ TODO |
| 4 | Invalid signal format → 422 | `test_invalid_signal_id_format` | ⏳ TODO |
| 5 | Duplicate approval → 409 | `test_duplicate_approval_same_user` | ⏳ TODO |
| 6 | Different user can approve → 201 | `test_approval_different_user_allowed` | ⏳ TODO |
| 7 | Missing JWT → 401 | `test_missing_jwt` | ⏳ TODO |
| 8 | Invalid JWT → 401 | `test_invalid_jwt` | ⏳ TODO |
| 9 | Missing decision → 422 | `test_missing_decision_field` | ⏳ TODO |
| 10 | Invalid decision (>1) → 422 | `test_invalid_decision_value` | ⏳ TODO |
| 11 | Missing consent_version → 422 | `test_missing_consent_version` | ⏳ TODO |
| 12 | IP captured in DB | `test_ip_captured_in_approval` | ⏳ TODO |
| 13 | User agent captured in DB | `test_user_agent_captured` | ⏳ TODO |
| 14 | Empty consent_version → 422 | `test_empty_consent_version` | ⏳ TODO |
| 15 | Long consent_version accepted | `test_long_consent_version` | ⏳ TODO |

---

## 🔗 Dependencies & Integration

### Depends On
- ✅ **PR-3:** Signals table exists (FK required)
- ✅ **PR-1:** FastAPI app running
- ✅ **PR-2:** PostgreSQL database

### Blocks
- ⏳ **PR-5:** Devices (needs approval tracking context)
- ⏳ **PR-6b:** Entitlements (needs user structure)
- ⏳ **PR-12:** Rate limiting (applies to /approve endpoint)

### Integration Points
1. **Database:** Uses signals.id as FK
2. **Authentication:** Mocks User JWT for now (PR-8 implements real JWT)
3. **Logging:** Uses structured JSON logging from PR-1
4. **API:** Follows /api/v1/ naming from PR-1

---

## 🛡️ Security Considerations

### Authentication
- JWT required (mocked via `current_user` dependency)
- Return 401 for missing/invalid tokens

### Authorization
- Users can only approve their own signals
- Will be enforced in later PRs (PR-12 adds user isolation)

### Input Validation
- signal_id: UUID format validation
- decision: Only 0 or 1 allowed
- consent_version: Non-empty, ≤255 characters
- All inputs escaped/typed

### Audit Trail
- IP address captured from request
- User agent captured from headers
- Timestamp captured (UTC)
- Enables compliance investigations

### Duplicate Prevention
- Unique index on (signal_id, user_id)
- Database constraint prevents duplicates
- Return 409 if duplicate attempted

---

## 📊 Estimated Effort Breakdown

| Phase | Task | Est. Time | Notes |
|-------|------|-----------|-------|
| 1 | Planning | 30 min | Current phase ✅ |
| 2 | Database & Migration | 1 hour | Alembic + SQLAlchemy model |
| 3 | Core Implementation | 2 hours | Routes, schemas, service layer |
| 4 | Testing | 1.5 hours | 15 test cases, ≥90% coverage |
| 5 | Local CI/CD | 30 min | Format, lint, test verification |
| 6 | Documentation | 45 min | 4 required docs + session notes |
| 7 | Verification & Commit | 30 min | Final checks + git commit |
| **TOTAL** | | **6.5 hours** | **~2-3 work days** |

---

## ✅ Ready to Begin?

**Current Status:** Planning complete ✅

**Next Steps:**
1. Move to PHASE 2 (Database migration)
2. Create `0003_approvals.py` migration
3. Create SQLAlchemy Approval model
4. Test migration locally
5. Continue through all 7 phases

**Expected Completion:** 2-3 days
**Target Test Count:** 15 new tests (86 total with PR-1/2/3)
**Target Coverage:** ≥90% on all new files

---

**Let's build PR-4! 🚀**
