# PR-036 PHASE 5.2 EXECUTION CHECKLIST

**Ready to Start**: Phase 5.2 UX Features Implementation
**Duration**: 2 hours total
**Tasks**: 4 (Optimistic UI, Toasts, Haptic, Telemetry)
**Start Time**: Now ⏳

---

## 📋 PHASE 5.2 ROADMAP

```
PHASE 5.2: UX FEATURES IMPLEMENTATION (2 hours)
│
├─ TASK 1: Optimistic UI ✏️ (30 mins)
│  ├─ Remove card immediately on action
│  ├─ Restore card on error
│  ├─ Disable buttons while pending
│  └─ Run tests to validate
│
├─ TASK 2: Toast Notifications 📢 (30 mins)
│  ├─ Install react-toastify
│  ├─ Setup ToastContainer
│  ├─ Show success/error messages
│  └─ Run tests to validate
│
├─ TASK 3: Haptic Feedback 📳 (15 mins)
│  ├─ Create vibration patterns
│  ├─ Trigger on success/error
│  ├─ Test on device
│  └─ Run tests to validate
│
├─ TASK 4: Telemetry Tracking 📊 (30 mins)
│  ├─ Create tracking functions
│  ├─ Track user actions
│  ├─ Send metadata with events
│  └─ Run tests to validate
│
└─ FINAL: Validation ✅ (15 mins)
   ├─ Run all Jest tests: npm test
   ├─ Run all E2E tests: npx playwright test
   ├─ Verify 100% coverage
   └─ Ready for Phase 5.3
```

---

## ✅ PRE-PHASE CHECKLIST

Before starting Task 1:

```
□ Read PHASE_5_2_QUICK_START.md
□ Review PHASE_5_1_COMPLETION_REPORT.md
□ Understand task 4 UX features
□ Current tests all passing: npm test
□ No uncommitted changes: git status
□ Ready to implement first task
```

---

## 🎯 TASK 1: OPTIMISTIC UI (30 mins)

**What**: Remove card immediately on action, restore on error

### Step 1.1: Modify `page.tsx` (15 mins)
```
File: app/approvals/page.tsx

Changes:
├─ Add: pendingSignalIds state (tracks which signals being processed)
├─ Modify: handleApprove() function
│  ├─ Remove card FIRST (optimistic)
│  ├─ Make API call
│  └─ Restore on error (rollback)
└─ Modify: handleReject() function (same pattern)

Code Location: Search for "handleApprove = async (signalId: string)"
Expected: Update optimistically before API call
Test: Click approve → card gone immediately
```

### Step 1.2: Modify `SignalCard.tsx` (10 mins)
```
File: components/SignalCard.tsx

Changes:
├─ Add: isPending prop
├─ Disable buttons when isPending
├─ Change button text to "Processing..."
└─ Add opacity effect while pending

Code Location: Search for "onClick={() => onApprove()}"
Expected: Buttons disabled and greyed out during pending
Test: Click approve → buttons disabled
```

### Step 1.3: Test (5 mins)
```bash
npm test -- SignalCard          # Component tests
npm test -- page                # Page tests
Expected: All tests still passing
```

### Step 1.4: Validation
```
□ Cards removed immediately (before API response)
□ Cards restored if API fails
□ Buttons disabled while pending
□ Button text shows "Processing..."
□ Tests passing: npm test
```

---

## 📢 TASK 2: TOAST NOTIFICATIONS (30 mins)

**What**: Show success/error messages that auto-dismiss

### Step 2.1: Install Package (2 mins)
```bash
npm install react-toastify
```

### Step 2.2: Create Helper (5 mins)
```
File: lib/toastNotifications.ts (NEW FILE)

Content:
├─ Import: toast from 'react-toastify'
├─ Export: showSuccessToast(message)
├─ Export: showErrorToast(message)
├─ Export: showInfoToast(message)
└─ Export: showWarningToast(message)

Code: ~40 lines
Example:
  export const showSuccessToast = (message: string) => {
    toast.success(message, { autoClose: 3000 });
  };
```

### Step 2.3: Setup in `layout.tsx` (5 mins)
```
File: app/layout.tsx

Changes:
├─ Import: ToastContainer from 'react-toastify'
├─ Import: CSS from 'react-toastify/dist/ReactToastify.css'
└─ Add: <ToastContainer position="bottom-right" autoClose={3000} />

Location: In root layout JSX, after children
```

### Step 2.4: Use in `page.tsx` (10 mins)
```
File: app/approvals/page.tsx

Changes:
├─ Import: showSuccessToast, showErrorToast
├─ In handleApprove() success: showSuccessToast('✅ Signal approved')
├─ In handleApprove() error: showErrorToast('Failed to approve')
├─ In handleReject() success: showSuccessToast('✅ Signal rejected')
└─ In handleReject() error: showErrorToast('Failed to reject')

Code: ~15 lines
Location: Success path and catch blocks
```

### Step 2.5: Test (8 mins)
```bash
npm test -- page                # Page tests
Expected: Toast tests passing
Manual: Click approve → see green success message
Manual: Trigger error → see red error message
```

### Step 2.6: Validation
```
□ Success toast appears on approve
□ Error toast appears on failure
□ Toast auto-dismisses after 3 seconds
□ Multiple toasts don't overlap
□ Dark/light mode works
□ Tests passing: npm test
```

---

## 📳 TASK 3: HAPTIC FEEDBACK (15 mins)

**What**: Device vibration on success/error

### Step 3.1: Create Helper (5 mins)
```
File: lib/hapticFeedback.ts (NEW FILE)

Content:
├─ Define: PATTERNS object with success/error
├─ Export: triggerHaptic(pattern: 'success' | 'error')
├─ Check: navigator.vibrate support
└─ Call: navigator.vibrate with pattern

Code: ~30 lines

Patterns:
├─ Success: [50, 30, 100]    (double tap feel)
└─ Error: [200, 100, 200]    (warning feel)
```

### Step 3.2: Use in `approvals.ts` (5 mins)
```
File: lib/approvals.ts

Changes:
├─ Import: triggerHaptic from lib/hapticFeedback
├─ In approveSignal() on success: triggerHaptic('success')
├─ In approveSignal() on error: triggerHaptic('error')
├─ In rejectSignal() on success: triggerHaptic('success')
└─ In rejectSignal() on error: triggerHaptic('error')

Code: ~5 lines
Location: After API response is received
```

### Step 3.3: Test (5 mins)
```bash
npm test -- lib/hapticFeedback  # Utility tests
Expected: Tests passing
Manual: Test on mobile device or emulator
  → Approve: Feel double-tap vibration
  → Error: Feel warning vibration
```

### Step 3.4: Validation
```
□ Success pattern triggers on approve
□ Error pattern triggers on failure
□ Device support checked
□ Vibrations feel different (success vs error)
□ Tests passing: npm test
```

---

## 📊 TASK 4: TELEMETRY (30 mins)

**What**: Track user actions for analytics

### Step 4.1: Create Helper (15 mins)
```
File: lib/telemetry.ts (NEW FILE)

Content:
├─ Import: uuid for request IDs
├─ Define: TelemetryEvent interface
├─ Export: trackEvent(name, metadata)
├─ Export: trackApprovalClick(signalId, confidence, maturity)
├─ Export: trackRejectionClick(signalId, confidence, maturity)
├─ Export: trackError(errorType, signalId)
└─ Export: trackSignalDetailView(signalId)

Code: ~100 lines

Events tracked:
├─ miniapp_approval_click_total
├─ miniapp_rejection_click_total
├─ miniapp_signal_detail_view_total
└─ miniapp_error_total
```

### Step 4.2: Use in `page.tsx` (8 mins)
```
File: app/approvals/page.tsx

Changes:
├─ Import: trackApprovalClick, trackRejectionClick, trackError
├─ In handleApprove(): trackApprovalClick(signal.id, confidence, maturity)
├─ In handleReject(): trackRejectionClick(signal.id, confidence, maturity)
├─ In catch blocks: trackError('approval_failed', signal.id)

Code: ~20 lines
Location: At start of action handler, in catch blocks
```

### Step 4.3: Use in `SignalCard.tsx` (5 mins)
```
File: components/SignalCard.tsx

Changes:
├─ Import: trackSignalDetailView
└─ On card click: trackSignalDetailView(signal.id)

Code: ~5 lines
Location: In onClick handler for card
```

### Step 4.4: Test (2 mins)
```bash
npm test -- telemetry                # Utility tests
npm test -- page                     # Integration tests
Expected: Tests passing
Manual: Open DevTools Network tab
  → Click approve
  → See POST to /api/v1/telemetry
  → Check request body has event data
```

### Step 4.5: Validation
```
□ trackApprovalClick called on approve
□ trackRejectionClick called on reject
□ trackError called on failure
□ trackSignalDetailView called on card click
□ Events include signal_id, confidence, maturity
□ Telemetry endpoint receives POST
□ Tests passing: npm test
```

---

## ✅ PHASE 5.2 COMPLETION CHECKLIST

After all tasks complete:

```
OPTIMISTIC UI:
□ Code changes complete (page.tsx, SignalCard.tsx)
□ Jest tests passing: npm test -- SignalCard
□ Jest tests passing: npm test -- page
□ Manual test: Cards removed immediately
□ Manual test: Cards restored on error

TOAST NOTIFICATIONS:
□ Package installed: npm install react-toastify
□ Helper created: lib/toastNotifications.ts
□ Layout updated: app/layout.tsx
□ Page updated: app/approvals/page.tsx
□ Jest tests passing: npm test
□ Manual test: Success toast appears
□ Manual test: Error toast appears

HAPTIC FEEDBACK:
□ Helper created: lib/hapticFeedback.ts
□ Service updated: lib/approvals.ts
□ Jest tests passing: npm test
□ Manual test on device: Vibrations work

TELEMETRY:
□ Helper created: lib/telemetry.ts
□ Page updated: app/approvals/page.tsx
□ Card updated: components/SignalCard.tsx
□ Jest tests passing: npm test
□ Manual test: Events sent to /api/v1/telemetry

FINAL VALIDATION:
□ All Jest tests passing: npm test
□ All E2E tests passing: npx playwright test
□ Coverage maintained: npm test -- --coverage (100%)
□ No console errors
□ No TypeScript errors: npm run type-check
□ Build succeeds: npm run build
□ Ready for Phase 5.3: YES ✅
```

---

## 🚀 COMMAND REFERENCE

### Testing
```bash
# Run all Jest tests
npm test

# Run specific component test
npm test -- SignalCard
npm test -- page

# Run with coverage
npm test -- --coverage

# Run E2E tests
npx playwright test frontend/miniapp/tests/approvals.e2e.ts

# Run E2E with headed browser
npx playwright test --headed
```

### Debugging
```bash
# Type check
npm run type-check

# Lint
npm run lint

# Format
npm run format

# Build
npm run build
```

---

## ⏱️ TIME TRACKING

| Task | Estimated | Actual | Status |
|------|-----------|--------|--------|
| Task 1: Optimistic UI | 30 min | ⏳ | In Progress |
| Task 2: Toast Notifications | 30 min | ⏳ | Queued |
| Task 3: Haptic Feedback | 15 min | ⏳ | Queued |
| Task 4: Telemetry | 30 min | ⏳ | Queued |
| Final Validation | 15 min | ⏳ | Queued |
| **TOTAL** | **2 hours** | **⏳** | **Ready to Start** |

---

## 📝 NOTES

- Each task is independent and testable
- Run tests after each task before moving to next
- All code examples provided in implementation guide
- Refer to PHASE_5_2_QUICK_START.md for quick reference
- Refer to PR_036_PHASE_5_2_UX_IMPLEMENTATION_GUIDE.md for detailed code
- E2E tests will validate all features work together

---

## 🎯 AFTER PHASE 5.2

Once all 4 tasks complete and tests passing:
1. All Jest tests passing (160/160) ✅
2. All E2E tests passing (55+/55+) ✅
3. Coverage at 100% ✅
4. No console errors ✅
5. Ready for Phase 5.3: Documentation ✅

---

**Start with Task 1: Optimistic UI**

Reference: `PR_036_PHASE_5_2_UX_IMPLEMENTATION_GUIDE.md` - Task 1 section

Good luck! ✨
