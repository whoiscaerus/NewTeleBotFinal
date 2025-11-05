# PR-036 COMPREHENSIVE AUDIT & IMPLEMENTATION PLAN

**Date**: November 4, 2025
**Status**: AUDIT IN PROGRESS
**Goal**: 100% Specification Coverage + 100% Test Coverage

---

## SPECIFICATION REQUIREMENTS (from Final_Master_Prs.md)

### Deliverables (REQUIRED)
```
✅ frontend/miniapp/app/approvals/page.tsx          # IMPLEMENTED
✅ frontend/miniapp/components/SignalCard.tsx        # IMPLEMENTED
❌ frontend/miniapp/components/SignalDetails.tsx     # MISSING - Details drawer
❌ frontend/miniapp/actions/approve.ts               # MISSING - Backend action
```

### Backend APIs (ASSUMED COMPLETE)
```
✅ /api/v1/signals?status=open           (PR-021)
✅ /api/v1/approve                       (PR-022)
```

### UX Requirements
```
❌ Optimistic UI - NOT IMPLEMENTED
❌ Fallback toast on failure - NOT IMPLEMENTED
❌ Haptic feedback - NOT IMPLEMENTED
✅ List open signals - IMPLEMENTED (page.tsx)
❌ Search/filter - NOT IMPLEMENTED
✅ Details drawer - COMPONENT MISSING (SignalDetails.tsx)
```

### Visuals
```
❌ "Confidence Meter" bar - NOT IMPLEMENTED
❌ "Signal Maturity" bar - NOT IMPLEMENTED
✅ Risk/Reward ratio badge - IMPLEMENTED
✅ Price levels (Entry/SL/TP) - IMPLEMENTED
```

### Telemetry
```
❌ miniapp_approval_click_total{decision} - NOT IMPLEMENTED
❌ miniapp_signal_view_total - NOT IMPLEMENTED
```

### Tests
```
❌ UI state toggles - NOT IMPLEMENTED
❌ API called with JWT - NOT IMPLEMENTED
❌ Errors surfaced gracefully - NOT IMPLEMENTED
❌ NO TEST FILES EXIST - 0% Coverage
```

---

## IMPLEMENTATION STATUS BREAKDOWN

### ✅ IMPLEMENTED (Partially)

#### 1. page.tsx (201 lines)
**What works:**
- Fetch pending approvals with JWT
- Display approvals with polling (5s)
- Approve/reject buttons
- Loading states
- Error handling (basic)
- State management

**What's missing:**
- Optimistic UI updates
- Toast notifications for success/failure
- Search/filter functionality
- No telemetry tracking
- No haptic feedback

**Issues found:**
- ❌ NO TESTS to verify this works
- ❌ No test for polling mechanism
- ❌ No test for error recovery
- ❌ No test for edge cases (expired tokens, network failure)

---

#### 2. SignalCard.tsx (143 lines)
**What works:**
- Display signal details (instrument, side, prices)
- Real-time relative time (updates per second)
- RR ratio badge
- Approve/reject buttons with loading states
- Proper props and TypeScript types

**What's missing:**
- No confidence meter bar
- No signal maturity bar
- No telemetry tracking on clicks
- No haptic feedback on button press

**Issues found:**
- ❌ NO TESTS to verify component rendering
- ❌ No test for relative time updates
- ❌ No test for button callbacks
- ❌ No test for edge cases (missing data, invalid dates)

---

#### 3. approvals.ts (208 lines - Service Layer)
**What works:**
- fetchPendingApprovals() - Get pending list
- approveSignal() - Submit approval
- rejectSignal() - Submit rejection
- formatRelativeTime() - Relative time helper
- isTokenValid() - Token expiration check
- getRemainingSeconds() - Countdown helper
- Proper error handling and logging

**Issues found:**
- ❌ NO TESTS to verify API calls work
- ❌ No test for JWT header inclusion
- ❌ No test for error scenarios
- ❌ No test for pagination (skip/limit)
- ❌ No test for timestamp filtering (since)

---

### ❌ MISSING (Critical)

#### 1. SignalDetails.tsx (COMPONENT)
**Why it's needed**: Spec says "details drawer"

**What should it do**:
- Display full signal details in drawer/modal
- Show confidence meter bar (from payload.confidence)
- Show signal maturity bar (calculated from age)
- Show extended metadata (if available)
- Close button and navigation

**Component spec**:
```tsx
interface SignalDetailsProps {
  signal: Signal;
  isOpen: boolean;
  onClose: () => void;
  confidence?: number; // 0-100
  maturityScore?: number; // 0-100
}
```

---

#### 2. approve.ts (ACTION)
**Why it's needed**: Spec requires "actions/approve.ts"

**What should it do**:
- Server action wrapper for approveSignal()
- Include telemetry tracking
- Return optimistic response
- Handle errors gracefully
- Include haptic feedback trigger

**Function spec**:
```typescript
async function approveAction(
  approvalId: string,
  jwt: string
): Promise<{
  success: boolean;
  message?: string;
  error?: string;
}>
```

---

## MISSING UX FEATURES

### 1. Optimistic UI ❌
**What it should do:**
- When user clicks approve, immediately remove card from list
- Show loading indicator
- If backend fails, show toast and restore card

**Current behavior:** No optimistic updates (waits for backend)

---

### 2. Toast Notifications ❌
**What it should do:**
- Success: "Signal approved! ✅"
- Error: "Failed to approve. Try again?"
- Info: "Token expiring soon"

**Current behavior:** Only console logs and state errors

---

### 3. Haptic Feedback ❌
**What it should do:**
- Vibrate on button press (mobile)
- Different pattern for approve vs reject

**Current behavior:** No haptic feedback

---

### 4. Search/Filter ❌
**What it should do:**
- Filter by instrument (GOLD, AAPL, etc.)
- Sort by time, confidence, RR ratio
- Search by symbol

**Current behavior:** Only displays all signals

---

### 5. Confidence Meter ❌
**Data**: Should come from signal.payload.confidence (0-100)
**Visual**: Progress bar, color-coded (red < 50%, yellow 50-75%, green > 75%)

---

### 6. Signal Maturity Bar ❌
**Data**: Calculated from signal.created_at age
**Visual**: Progress bar showing signal age vs timeout
**Example**: If signal valid for 5 minutes, show % expired

---

## TELEMETRY TRACKING ❌ (NOT IMPLEMENTED)

### Required Metrics:
1. `miniapp_approval_click_total{decision="approve"|"reject"}`
   - Where: SignalCard component
   - When: User clicks button
   - What: Count by approve vs reject

2. `miniapp_signal_view_total`
   - Where: page.tsx
   - When: User views signals list
   - What: Count of loaded signals

---

## TEST COVERAGE: 0% → 100% PLAN

### Phase 1: Unit Tests (Jest)

#### 1.1 SignalCard Component Tests
**File**: `frontend/miniapp/tests/SignalCard.spec.tsx`
**Tests needed**:
- ✅ Renders with valid props
- ✅ Displays signal data correctly (instrument, side, prices)
- ✅ RR ratio displayed and formatted correctly
- ✅ Approve button calls onApprove callback
- ✅ Reject button calls onReject callback
- ✅ Loading state disables buttons
- ✅ Relative time updates every second
- ✅ Relative time stops updating on unmount
- ✅ Invalid dates handled gracefully
- ✅ Missing optional fields don't crash

**Coverage target**: 100% of component logic

---

#### 1.2 Service Functions Tests
**File**: `frontend/miniapp/tests/approvals.spec.ts`
**Tests needed**:
- ✅ fetchPendingApprovals() returns correct data
- ✅ JWT header included in request
- ✅ Pagination params (skip, limit) passed correctly
- ✅ Timestamp filter (since) passed correctly
- ✅ formatRelativeTime() calculates correctly (secs, mins, hours, days)
- ✅ isTokenValid() checks expiration correctly
- ✅ getRemainingSeconds() calculates remaining time
- ✅ Error handling on network failure
- ✅ Error handling on invalid JWT
- ✅ Error handling on invalid data

**Coverage target**: 100% of service logic

---

#### 1.3 Page Component Tests
**File**: `frontend/miniapp/tests/ApprovalsPage.spec.tsx`
**Tests needed**:
- ✅ Renders loading state before auth
- ✅ Shows error if auth fails
- ✅ Fetches approvals on mount
- ✅ Sets up polling interval (5s)
- ✅ Clears polling interval on unmount
- ✅ handleApprove removes card optimistically
- ✅ handleReject removes card optimistically
- ✅ Error on approve shows error message
- ✅ Error on reject shows error message
- ✅ Empty state when no approvals

**Coverage target**: 100% of page logic

---

### Phase 2: Integration Tests (Playwright)

**File**: `frontend/miniapp/tests/approvals.e2e.ts`
**Tests needed**:
- ✅ Full user flow: Load → Approve → Success
- ✅ Full user flow: Load → Reject → Success
- ✅ Full user flow: Approve fails → Show error
- ✅ Polling fetches new signals every 5 seconds
- ✅ Approval token expires → Show warning
- ✅ Network error → Show error, retry works
- ✅ Empty state when no signals
- ✅ UI elements exist and are interactive

---

### Phase 3: Business Logic Validation

**What needs validation**:
1. ✅ Approvals list is user-isolated (no cross-user data)
2. ✅ Approve call includes correct approval ID
3. ✅ JWT token is always included
4. ✅ Expired tokens are detected and handled
5. ✅ Optimistic UI rollback on error
6. ✅ Telemetry recorded for all user actions
7. ✅ Backend API contract matched (response format)

---

## ACTION ITEMS (Priority Order)

### CRITICAL (Must Have)
- [ ] Create SignalDetails.tsx component
- [ ] Create approve.ts action
- [ ] Create comprehensive unit tests (jest)
- [ ] Create integration tests (playwright)
- [ ] Implement optimistic UI
- [ ] Implement toast notifications
- [ ] Add telemetry tracking

### IMPORTANT (Should Have)
- [ ] Add confidence meter bar
- [ ] Add signal maturity bar
- [ ] Add haptic feedback
- [ ] Add search/filter

### NICE-TO-HAVE (Could Have)
- [ ] Advanced analytics
- [ ] Signal recommendations
- [ ] Batch operations

---

## ESTIMATION

| Task | Effort | Time |
|------|--------|------|
| Create missing components | 2 hours | Create SignalDetails + approve.ts |
| Unit tests (phase 1) | 3 hours | Jest tests for all components/services |
| Integration tests (phase 2) | 2 hours | Playwright E2E scenarios |
| Optimistic UI + Toasts | 2 hours | UI feedback mechanisms |
| Telemetry + Haptics | 1 hour | Tracking and mobile feedback |
| Bars (confidence + maturity) | 1 hour | Visual components |
| Search/Filter (optional) | 2 hours | Can defer to v2 |
| Documentation | 1 hour | PR docs (plan, complete, criteria, impact) |
| **TOTAL** | **14 hours** | From now to complete PR-036 |

---

## SUCCESS CRITERIA

✅ All deliverables created (page, SignalCard, SignalDetails, approve action)
✅ ALL UX features implemented (optimistic UI, toasts, haptics, feedback)
✅ 100% test coverage on all implemented code
✅ All business logic validated by tests
✅ No edge cases left untested
✅ API contracts verified
✅ Telemetry tracking enabled
✅ 4 PR documentation files complete
✅ Zero TODO/FIXME in code
✅ GitHub Actions passing

---

**Session Goal**: Complete ALL of PR-036 with full business logic validation and 100% test coverage. No shortcuts.
