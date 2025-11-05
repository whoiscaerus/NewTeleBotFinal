# PR-027: Mini App Approval Console - AUDIT & COMPREHENSIVE FIX PLAN

**Status**: 🔴 INCOMPLETE - Critical gaps in backend & frontend implementation
**Date**: 2025-01-XX
**Objective**: Verify full business logic implementation and comprehensive test coverage

---

## PART 1: SPECIFICATION REVIEW

### PR-27 Requirements (From Master Doc)

**Goal**: Build the main Mini App screen: pending approvals list with one-tap approve/reject, real-time updates via polling.

**Backend Endpoints Required**:
1. `GET /api/v1/approvals/pending` - NEW ENDPOINT (NOT IMPLEMENTED)
   - Auth: JWT session token (from PR-26)
   - Query: `?since=<iso_timestamp>` (optional, for polling)
   - Logic: Return approvals with decision=NULL for user's signals, created after `since`
   - Response includes:
     - signal_id, instrument, side, lot_size, created_at
     - approval_token (short-lived JWT, 5-minute expiry)
     - expires_at

2. `POST /api/v1/approvals` - EXISTS (from PR-022)
   - Used to create approval with decision

**Frontend Components Required**:
1. `frontend/src/app/miniapp/approvals/page.tsx` - PARTIALLY EXISTS
2. `frontend/src/components/miniapp/ApprovalCard.tsx` - MISSING
3. `frontend/src/components/miniapp/SignalDetails.tsx` - MISSING
4. `frontend/src/lib/api/approvals.ts` - MISSING (API client functions)

**Testing Required**:
1. Backend: `backend/tests/test_pr_27_approvals_pending.py` - NOT EXISTS
2. Frontend: `frontend/tests/miniapp-approvals.spec.ts` - NOT EXISTS

**Documentation Required**:
1. `docs/prs/PR-27-IMPLEMENTATION-PLAN.md`
2. `docs/prs/PR-27-IMPLEMENTATION-COMPLETE.md`
3. `docs/prs/PR-27-ACCEPTANCE-CRITERIA.md`
4. `docs/prs/PR-27-BUSINESS-IMPACT.md`

---

## PART 2: CURRENT IMPLEMENTATION AUDIT

### Backend Status

#### ✅ EXISTS (from PR-022 Approvals)
```
backend/app/approvals/models.py (111 lines)
- Approval model with fields: id, signal_id, client_id, user_id, decision, consent_version, reason, ip, ua, created_at
- Includes UniqueConstraint(signal_id, user_id) - prevents duplicate approvals
- Includes helpful indexes for queries

backend/app/approvals/schema.py (35 lines)
- ApprovalCreate: signal_id, decision (approved|rejected), reason, consent_version
- ApprovalOut: id, signal_id, user_id, decision, reason, consent_version, created_at
- MISSING: approval_token field
- MISSING: expires_at field

backend/app/approvals/service.py (109 lines)
- ApprovalService.approve_signal(): creates approval, updates signal status
- Includes PR-048 integration (RiskService.calculate_current_exposure)
- Proper error handling with APIError

backend/app/approvals/routes.py (302 lines)
- POST /api/v1/approvals: create approval endpoint (201)
- GET /api/v1/approvals/{approval_id}: get single approval
- GET /api/v1/approvals: list approvals for current user
- Includes proper JWT auth via get_current_user
- Includes metrics recording (approvals_total, approval_latency_seconds)
- Includes audit logging
```

#### 🔴 MISSING - GET /api/v1/approvals/pending Endpoint
```
Required endpoint for mini app:
- Should filter: decision == NULL (pending)
- Should filter: signal.user_id == current_user.id
- Should support: ?since=<iso_timestamp> parameter
- Should include: signal details (instrument, side, lot_size)
- Should return: approval_token (5-min expiry), expires_at
- Should record metrics: miniapp_approvals_viewed_total

Currently: Page tries to call /api/v1/approvals/pending but endpoint doesn't exist
Result: Frontend requests will 404
```

#### 🟡 INCOMPLETE - Approval Model
```
MISSING FIELDS in Approval model:
- approval_token: str (short-lived JWT for approval action)
- expires_at: datetime (when token expires)

These fields should be stored for:
1. Audit trail (which token was used for which approval)
2. Preventing token replay attacks
3. Showing user token expiry countdown

Alternative: Generate on-the-fly at response time (simpler, but less auditable)
Recommendation: Store in DB for security & audit
```

#### 🟡 INCOMPLETE - Signal Model
```
MISSING FIELD in Signal model:
- lot_size: float (position size in lots)

Frontend needs this to display: "0.04 lots" on approval card
Options:
1. Calculate from payload (may not always available)
2. Add as explicit field (best for consistency)
3. Include in Approval model (denormalize from signal payload)

Current: Frontend code assumes signal has lot_size but Signal model doesn't have it
```

### Frontend Status

#### ✅ PARTIALLY EXISTS
```
frontend/miniapp/app/approvals/page.tsx (250+ lines)
- Fetches from /api/v1/approvals/pending (correct endpoint)
- Displays signal cards with approve/reject buttons
- 5-second polling loop implemented
- Loading/error/empty states present
- Approve/reject button handlers exist
- Uses JWT from useTelegram() hook

ISSUES:
1. All logic in single page.tsx (should be components)
2. Assumes signal object in approval response (needs to verify schema match)
3. Timestamps shown as full ISO (should be relative time: "2 min ago")
4. No token expiry countdown display
5. No telemetry metrics (miniapp_approvals_viewed_total, miniapp_approval_actions_total)
6. No ApprovalCard.tsx component (inlined in page)
7. No SignalDetails.tsx component (not needed in current version)
8. No API client functions (approvals.ts) - all logic inline
```

#### 🔴 MISSING - Component Separation
```
Required components:
- ApprovalCard.tsx: Single approval card (reusable)
- SignalDetails.tsx: Expandable signal details view (optional for phase 1)
- approvals.ts: API client functions (fetchPendingApprovals, approveSignal, rejectSignal)
```

#### 🔴 MISSING - UX Enhancements
```
1. Relative time display ("2 min ago" vs full ISO timestamp)
2. Token expiry countdown ("Expires in 3m 45s")
3. Telemetry metrics emission
4. Toast notifications on success/error (Nice to have)
5. Haptic feedback on approval/rejection (Telegram feature)
6. Keyboard accessibility (focus management, ENTER to approve)
```

#### 🔴 MISSING - Tests
```
frontend/tests/miniapp-approvals.spec.ts - NOT EXISTS
Should test:
1. Page loads with pending approvals list
2. Approval card displays correct signal data
3. Approve button sends request and removes card
4. Reject button sends request and removes card
5. Empty state shown when no approvals
6. Error handling and retry
7. Polling updates list
8. Token expiry countdown works
```

### Test Coverage Status

#### 🔴 MISSING - Backend Tests
```
backend/tests/test_pr_27_approvals_pending.py - NOT EXISTS

Should include:
1. TestApprovalPendingEndpoint:
   - Returns pending approvals for current user
   - Returns empty list when none pending
   - Includes signal details in response
   - Includes approval_token and expires_at
   - Filters by since parameter correctly
   - Excludes already-decided approvals
   - Requires JWT authentication

2. TestApprovalToken:
   - Token generated with 5-minute expiry
   - Token is valid JWT format
   - Different token for each approval

3. TestApprovalFiltering:
   - Only user's own signals shown
   - Already-approved/rejected excluded
   - Orders by created_at DESC

4. TestErrorHandling:
   - 401 without JWT
   - 400 with invalid since parameter
   - 500 on database error

5. Integration:
   - Fetch → Approve → No longer pending
   - Multiple signals from multiple users isolated

Target: ≥95% coverage
```

#### 🔴 MISSING - Frontend Tests
```
frontend/tests/miniapp-approvals.spec.ts - NOT EXISTS

Should test:
1. Page load and authentication
2. Pending approvals list rendering
3. Signal card display with all fields
4. Approve/reject buttons and callbacks
5. Optimistic UI (buttons disable during request)
6. Empty state
7. Error handling with retry
8. Polling mechanism (5-second interval)
9. Telemetry metrics recording
10. Token expiry countdown

Target: ≥90% coverage
```

---

## PART 3: BUSINESS LOGIC GAPS ANALYSIS

### Flow 1: User Views Pending Approvals
```
Current State:
1. Frontend calls GET /api/v1/approvals/pending
2. Backend returns... NOTHING (endpoint doesn't exist)
3. Frontend shows 404 error

Required State:
1. Frontend calls GET /api/v1/approvals/pending?since=<timestamp>
2. Backend queries: SELECT * FROM approvals WHERE user_id=? AND decision=NULL AND created_at > since
3. For each approval, fetch associated signal data
4. Generate 5-minute approval_token (JWT with approval.id as subject)
5. Return: [{ signal_id, instrument, side, lot_size, created_at, approval_token, expires_at }]
6. Record metric: miniapp_approvals_viewed_total counter
```

### Flow 2: User Approves a Signal
```
Current State:
1. Frontend sends POST /api/v1/approvals with signal_id & decision
   - But spec says approval_token should be used instead
2. Backend creates approval
3. Signal status changes from NEW to APPROVED

Issue: Approval workflow confusion
- Spec mentions "approval_token" sent to /api/v1/approve/telegram
- But current implementation uses direct signal_id + decision at /api/v1/approvals

Required State (align with spec):
1. Frontend includes approval_token (from pending list) in request
2. Backend validates token (JWT, not expired, valid user)
3. Backend creates approval with token as proof
4. Signal status changes
5. Record metric: miniapp_approval_actions_total{decision="approve"}

OR: Keep current flow but rename endpoint for clarity
- Current: POST /api/v1/approvals (create approval with signal_id)
- Better: Verify this supports both: session auth + approval_token validation
```

### Flow 3: Polling for New Approvals
```
Required:
1. Frontend calls GET /api/v1/approvals/pending?since=<last_fetch_timestamp>
2. Backend only returns approvals created after `since`
3. Frontend updates list, shows new cards
4. Frontend continues polling every 5 seconds

Current Issue: Endpoint doesn't exist, so polling fails
```

### Security Implications
```
Issues to Address:
1. Approval tokens need expiry (5 minutes per spec)
2. Tokens must be tied to user session
3. Tokens must be one-time or reusable? (Spec unclear)
4. Risk check integration (already in place via PR-048)
5. User isolation (only user's own signals visible)
6. Audit trail (IP, UA, timestamp logged per signal)
```

---

## PART 4: IMPLEMENTATION PLAN

### Phase 1: Backend - Approval Model & Schema Updates (1 hour)

**Task 1.1**: Update Approval model
```python
# Add fields to backend/app/approvals/models.py
approval_token: Mapped[str | None] = mapped_column(
    String(500),
    nullable=True,
    doc="Short-lived JWT token for approval action",
)
expires_at: Mapped[datetime | None] = mapped_column(
    nullable=True,
    doc="Token expiry timestamp",
)

# Add property
def is_token_valid(self) -> bool:
    """Check if approval token is still valid."""
    if not self.expires_at:
        return False
    return datetime.utcnow() < self.expires_at
```

**Task 1.2**: Update ApprovalOut schema
```python
# Add fields to backend/app/approvals/schema.py
class ApprovalOut(BaseModel):
    id: str
    signal_id: str
    user_id: str
    decision: str
    reason: str | None
    consent_version: int
    created_at: datetime
    approval_token: str | None  # ADD
    expires_at: datetime | None  # ADD
```

**Task 1.3**: Add PendingApprovalOut schema
```python
# New schema for pending approvals response
class PendingApprovalOut(BaseModel):
    signal_id: str
    instrument: str
    side: str
    lot_size: float
    created_at: datetime
    approval_token: str
    expires_at: datetime
```

**Task 1.4**: Update Signal model (optional - depends on lot_size source)
```python
# If lot_size not in payload, add to Signal:
lot_size: Mapped[float] = mapped_column(
    nullable=True,
    doc="Position size in lots",
)
```

### Phase 2: Backend - GET /api/v1/approvals/pending Endpoint (1.5 hours)

**Task 2.1**: Implement pending endpoint in routes.py
```python
@router.get("/approvals/pending", response_model=list[PendingApprovalOut])
async def get_pending_approvals(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    since: datetime | None = Query(None, description="Only approvals after this timestamp"),
):
    """Get pending approvals for current user (mini app endpoint).

    Returns signals awaiting user approval with short-lived tokens.
    Supports polling with 'since' parameter for efficiency.
    """
```

**Task 2.2**: Query logic
```python
# Query approvals with pending status (decision=NULL)
# That belong to user's signals
# Optionally filtered by since parameter

query = select(Approval, Signal).where(
    (Approval.user_id == current_user.id) &
    (Approval.decision == NULL) &
    (Signal.id == Approval.signal_id)
)

if since:
    query = query.where(Approval.created_at > since)

query = query.order_by(Approval.created_at.desc())
```

**Task 2.3**: Generate approval tokens
```python
# For each pending approval, generate JWT token
# Token expires in 5 minutes
# Store in approval record

from backend.app.auth.jwt_handler import JWTHandler

handler = JWTHandler()
token = handler.create_token(
    subject=str(approval.id),
    audience="miniapp",
    expires_in=5 * 60  # 5 minutes
)
approval.approval_token = token
approval.expires_at = datetime.utcnow() + timedelta(minutes=5)
```

**Task 2.4**: Record telemetry
```python
# Record viewed counter
metrics = get_metrics()
metrics.miniapp_approvals_viewed_total.inc()
```

### Phase 3: Frontend - Component Separation (1 hour)

**Task 3.1**: Create ApprovalCard.tsx
- Extract card rendering from page.tsx
- Props: approval, onApprove, onReject, isProcessing

**Task 3.2**: Create API client functions
- Create frontend/src/lib/api/approvals.ts
- Functions: fetchPendingApprovals, approveSignal, rejectSignal

**Task 3.3**: Update page.tsx
- Import components and API functions
- Clean up logic to use extracted functions

### Phase 4: Frontend - UX Enhancements (1.5 hours)

**Task 4.1**: Add relative time display
- Install date-fns: `npm install date-fns`
- Use: `formatDistanceToNow(new Date(created_at), { addSuffix: true })`
- Shows: "2 minutes ago" instead of ISO timestamp

**Task 4.2**: Add token expiry countdown
- Use useEffect to update every second
- Format: "Expires in 3m 45s"
- Color warning when < 1 minute

**Task 4.3**: Add telemetry metrics
```typescript
// On page load
metrics.miniapp_approvals_viewed_total.inc()

// On approve/reject
metrics.miniapp_approval_actions_total.labels(decision).inc()

// On response
metrics.miniapp_approval_latency_seconds.observe(latency)
```

### Phase 5: Comprehensive Testing (3 hours)

**Task 5.1**: Backend tests (test_pr_27_approvals_pending.py)
- 15+ test cases
- ≥95% coverage
- All business logic paths

**Task 5.2**: Frontend tests (miniapp-approvals.spec.ts)
- 10+ test cases
- ≥90% coverage
- All user flows

**Task 5.3**: Integration tests
- End-to-end: Signal → Pending → Approve → Closed

### Phase 6: Documentation (1 hour)

**Task 6.1**: Create 4 required docs
- IMPLEMENTATION-PLAN.md
- IMPLEMENTATION-COMPLETE.md
- ACCEPTANCE-CRITERIA.md
- BUSINESS-IMPACT.md

**Task 6.2**: Create verification script
- verify-pr-27.sh

---

## PART 5: RISK ASSESSMENT

### High Priority (Critical)
- [ ] GET /api/v1/approvals/pending endpoint missing (blocks MVP)
- [ ] Approval token generation logic missing
- [ ] Frontend can't fetch pending approvals (404 error)
- [ ] No test coverage (can't validate business logic)

### Medium Priority (Important)
- [ ] Frontend components not separated (maintainability)
- [ ] Telemetry metrics not recorded (observability)
- [ ] Relative time display missing (UX)
- [ ] Token expiry countdown missing (UX)

### Low Priority (Nice to Have)
- [ ] Toast notifications not implemented
- [ ] Haptic feedback not implemented
- [ ] Keyboard accessibility incomplete
- [ ] No SignalDetails expandable component

---

## PART 6: SUCCESS CRITERIA

### All Acceptance Criteria Passing
- [ ] Pending approvals endpoint returns correct schema
- [ ] Approval tokens generated with 5-minute expiry
- [ ] Frontend displays pending approvals list
- [ ] Approve button creates approval
- [ ] Reject button creates rejection
- [ ] Polling updates list every 5 seconds
- [ ] User isolation (user can't see others' approvals)
- [ ] Error handling (network failures, expired tokens, etc.)
- [ ] Telemetry metrics recorded
- [ ] All tests passing (95%+ backend, 90%+ frontend)

### Code Quality
- [ ] All functions have docstrings + type hints
- [ ] No TODOs or FIXMEs
- [ ] No hardcoded values (use config/env)
- [ ] Proper error handling with logging
- [ ] Black formatted (88 char line length)
- [ ] No secrets in code

### Documentation
- [ ] 4 required PR docs created
- [ ] Verification script created
- [ ] Acceptance criteria documented

---

## IMPLEMENTATION SEQUENCE

**Recommended Order** (minimize dependencies, enable parallel work):

1. ✅ **Task 1**: Update Approval model + schema (backend foundations)
2. ✅ **Task 2**: Implement /api/v1/approvals/pending endpoint (blocks frontend)
3. ✅ **Task 3**: Create backend tests (validates endpoint works)
4. ✅ **Task 4**: Frontend component separation (ready for endpoint)
5. ✅ **Task 5**: Frontend UX enhancements (tokens, timers, metrics)
6. ✅ **Task 6**: Frontend tests (validates UI logic)
7. ✅ **Task 7**: Integration tests (validates full flow)
8. ✅ **Task 8**: Documentation (PR docs + verification)

**Parallel Opportunities**:
- Tasks 3 & 4 can overlap (both need endpoint to be done first)
- Tasks 5 & 6 can overlap (testing during implementation)

**Estimated Timeline**:
- Backend (1-2): 2.5 hours
- Backend tests (3): 1.5 hours
- Frontend (4-5): 2.5 hours
- Frontend tests (6): 1.5 hours
- Integration (7): 1 hour
- Documentation (8): 1 hour
- **Total: ~10 hours**

---

## NEXT STEPS

1. **Verify current state** - Confirm endpoints and tests don't exist
2. **Implement Task 1** - Model & schema updates
3. **Implement Task 2** - Pending endpoint
4. **Create backend tests** - Validate endpoint
5. **Update frontend** - Component separation
6. **Create frontend tests** - Validate UI
7. **Document** - 4 required docs + verification script
8. **Final verification** - All tests passing, coverage requirements met

**Go/No-Go Check**:
- [ ] All backend tests passing (≥95% coverage)
- [ ] All frontend tests passing (≥90% coverage)
- [ ] All acceptance criteria verified
- [ ] All 4 documentation files created
- [ ] Verification script passing
- [ ] Code formatted with Black
- [ ] No TODOs or secrets in code

---

**Status**: Ready to implement Phase 1 (Model updates)
**Owner**: Implementation agent
**Target Completion**: Before token budget exceeded
