# PR-036 Phase 5.2 Quick Start Guide

**Phase**: 5.2 UX Features Implementation
**Duration**: 2 hours total
**Files to Modify**: 7 files
**Lines of Code**: ~450 lines

---

## 🎯 The 4 Tasks (In Order)

### TASK 1: Optimistic UI (30 mins)

**What**: Remove card immediately on action, restore on error

**Files to Modify**:
```
✏️ app/approvals/page.tsx          (+60 lines)
✏️ components/SignalCard.tsx       (+20 lines)
```

**Key Code Change** (page.tsx):
```typescript
// BEFORE
handleApprove = () => {
  await approveSignal();
  setSignals(prev => prev.filter(s => s.id !== id)); // Remove AFTER
}

// AFTER
handleApprove = () => {
  setSignals(prev => prev.filter(s => s.id !== id)); // Remove FIRST
  try {
    await approveSignal();
  } catch {
    setSignals(previousSignals); // Restore on error
  }
}
```

**Checklist**:
- [ ] Add `pendingSignalIds` state to page.tsx
- [ ] Update `handleApprove()` to remove card first
- [ ] Update `handleReject()` to remove card first
- [ ] Add error recovery (restore card)
- [ ] Pass `isPending` prop to SignalCard
- [ ] Disable buttons when pending
- [ ] Change button text to "Processing..."
- [ ] Run tests: `npm test -- SignalCard`
- [ ] Verify all tests still pass

---

### TASK 2: Toast Notifications (30 mins)

**What**: Show success/error messages that auto-dismiss

**Files to Modify**:
```
✨ lib/toastNotifications.ts        (+40 lines) [NEW]
✏️ app/layout.tsx                   (+10 lines)
✏️ app/approvals/page.tsx           (+15 lines)
```

**Installation**:
```bash
npm install react-toastify
```

**Key Code Change** (page.tsx):
```typescript
// BEFORE
catch (error) {
  console.error(error);
}

// AFTER
catch (error) {
  showErrorToast(`Failed: ${error.message}`);
}

// On success
showSuccessToast('✅ Signal approved');
```

**Checklist**:
- [ ] Create `lib/toastNotifications.ts`
- [ ] Add `ToastContainer` to `layout.tsx`
- [ ] Import `showSuccessToast`, `showErrorToast`
- [ ] Call on success: `showSuccessToast('✅ Signal approved')`
- [ ] Call on error: `showErrorToast('Failed to approve')`
- [ ] Test toasts appear: `npm test -- page`
- [ ] Verify auto-dismiss after 3 seconds
- [ ] Run all tests: `npm test`

---

### TASK 3: Haptic Feedback (15 mins)

**What**: Device vibration on success/error

**Files to Modify**:
```
✨ lib/hapticFeedback.ts            (+30 lines) [NEW]
✏️ lib/approvals.ts                 (+5 lines)
```

**Key Code Change** (approvals.ts):
```typescript
// BEFORE
export const approveSignal = async () => {
  const response = await fetch(...);
  return response.json();
}

// AFTER
export const approveSignal = async () => {
  const response = await fetch(...);
  if (response.ok) {
    triggerHaptic('success'); // [50, 30, 100]
  } else {
    triggerHaptic('error');   // [200, 100, 200]
  }
  return response.json();
}
```

**Checklist**:
- [ ] Create `lib/hapticFeedback.ts`
- [ ] Define success pattern: [50, 30, 100]
- [ ] Define error pattern: [200, 100, 200]
- [ ] Export `triggerHaptic('success' | 'error')`
- [ ] Add to `approveSignal()` on success
- [ ] Add to `approveSignal()` on error
- [ ] Add to `rejectSignal()` on success
- [ ] Add to `rejectSignal()` on error
- [ ] Test with device/emulator
- [ ] Run tests: `npm test`

---

### TASK 4: Telemetry (30 mins)

**What**: Track user actions for analytics

**Files to Modify**:
```
✨ lib/telemetry.ts                 (+100 lines) [NEW]
✏️ app/approvals/page.tsx           (+20 lines)
✏️ components/SignalCard.tsx        (+5 lines)
```

**Key Code Change** (page.tsx):
```typescript
// BEFORE
handleApprove = async () => {
  await approveSignal();
}

// AFTER
handleApprove = async () => {
  trackApprovalClick(signal.id, signal.confidence, signal.maturity);
  await approveSignal();
}
```

**Checklist**:
- [ ] Create `lib/telemetry.ts`
- [ ] Export `trackApprovalClick(signalId, confidence, maturity)`
- [ ] Export `trackRejectionClick(signalId, confidence, maturity)`
- [ ] Export `trackError(errorType, signalId)`
- [ ] Export `trackSignalDetailView(signalId)`
- [ ] Call `trackApprovalClick()` in handleApprove
- [ ] Call `trackRejectionClick()` in handleReject
- [ ] Call `trackError()` in catch blocks
- [ ] Call `trackSignalDetailView()` on card click
- [ ] Test tracking: Check network requests in DevTools
- [ ] Run tests: `npm test`

---

## 📋 Implementation Checklist

### Before You Start
- [ ] Backup current code (git commit)
- [ ] All Jest tests currently passing: `npm test`
- [ ] All E2E tests read and understood
- [ ] UX implementation guide saved locally

### Optimistic UI
- [ ] Code changes complete
- [ ] Jest tests pass: `npm test -- SignalCard`
- [ ] E2E tests validate: Look for "should remove card immediately"
- [ ] Manual test: Click approve, card gone immediately

### Toast Notifications
- [ ] Dependencies installed: `npm install react-toastify`
- [ ] ToastContainer added to layout.tsx
- [ ] Success toast on approve
- [ ] Error toast on failure
- [ ] Auto-dismiss working (3 seconds)
- [ ] Jest tests pass: `npm test`

### Haptic Feedback
- [ ] triggerHaptic created in lib/hapticFeedback.ts
- [ ] Called on success with [50, 30, 100]
- [ ] Called on error with [200, 100, 200]
- [ ] Device support checked (navigator.vibrate)
- [ ] Jest tests pass: `npm test`
- [ ] Manual test on mobile: Feel vibrations

### Telemetry
- [ ] Telemetry functions created
- [ ] trackApprovalClick() called on approve
- [ ] trackRejectionClick() called on reject
- [ ] trackError() called on failure
- [ ] trackSignalDetailView() called on drawer open
- [ ] Jest tests pass: `npm test`
- [ ] Manual test in DevTools: See POST to /api/v1/telemetry

### Final Validation
- [ ] All Jest tests pass: `npm test`
  - Expected: 160 passed
- [ ] All E2E tests pass: `npx playwright test`
  - Expected: 55+ passed
- [ ] Code coverage maintained: `npm test -- --coverage`
  - Expected: 100%
- [ ] No console errors in browser
- [ ] No console errors in terminal
- [ ] Git diff looks reasonable: `git diff`

---

## 🚀 Command Reference

### Testing
```bash
# Run all Jest tests
npm test

# Run specific test file
npm test -- SignalCard

# Run with coverage
npm test -- --coverage

# Run E2E tests
npx playwright test frontend/miniapp/tests/approvals.e2e.ts

# Run E2E tests headed (watch)
npx playwright test --headed
```

### Code Quality
```bash
# Format code
npm run format

# Lint code
npm run lint

# Type check
npm run type-check

# Build
npm run build
```

### Debugging
```bash
# E2E debug mode
npx playwright test --debug

# Check coverage report
npm test -- --coverage
open coverage/lcov-report/index.html
```

---

## ⏱️ Time Breakdown

| Task | Duration | Status |
|------|----------|--------|
| Optimistic UI | 30 mins | ⏳ Ready |
| Toast Notifications | 30 mins | ⏳ Ready |
| Haptic Feedback | 15 mins | ⏳ Ready |
| Telemetry | 30 mins | ⏳ Ready |
| **Final Testing** | **15 mins** | **⏳ Ready** |
| **TOTAL** | **2 hours** | **⏳ Ready to Start** |

---

## 📚 Reference Files

### Key Files to Review First
1. `PHASE_5_1_COMPLETION_REPORT.md` - This entire phase explained
2. `PR_036_PHASE_5_2_UX_IMPLEMENTATION_GUIDE.md` - Detailed implementation guide
3. `PR_036_E2E_TEST_SUITE_CREATED.md` - E2E tests that validate this
4. `approvals.e2e.ts` - The actual test file to understand

### Code Files to Create
```
NEW FILES:
✨ lib/toastNotifications.ts         (helper functions for toasts)
✨ lib/hapticFeedback.ts             (helper functions for vibration)
✨ lib/telemetry.ts                  (helper functions for tracking)

FILES TO MODIFY:
✏️ app/layout.tsx                    (+ToastContainer)
✏️ app/approvals/page.tsx            (+state, +calls)
✏️ components/SignalCard.tsx         (+isPending prop)
✏️ lib/approvals.ts                  (+haptic calls)
```

---

## 💡 Pro Tips

### Tip 1: Optimistic UI
- **Store previous state** before optimistic update
- **Rollback completely** on error (not partial)
- **Disable all buttons** while pending (prevent double-clicks)

### Tip 2: Toasts
- **Success messages are short**: "✅ Signal approved"
- **Error messages are helpful**: "Failed to approve: Network error"
- **Auto-dismiss avoids clutter**: Use 3 second timeout

### Tip 3: Haptic Feedback
- **Not all devices support**: Always check navigator.vibrate
- **Don't vibrate on every interaction**: Only on significant actions
- **Use patterns for meaning**: Success vs error feels different

### Tip 4: Telemetry
- **Track BEFORE action**: Captures user intent
- **Include signal metadata**: Helps analytics
- **Silent failures**: Don't break UX if tracking fails

---

## ❓ Troubleshooting

### Issue: Tests failing after changes
**Solution**:
1. Check console for errors: `npm test`
2. Review test file: `approvals.spec.ts`
3. Ensure mock data matches new state

### Issue: Toasts not appearing
**Solution**:
1. Check ToastContainer in layout.tsx
2. Verify CSS imported: `import 'react-toastify/dist/ReactToastify.css'`
3. Check network tab for POST to /api/v1/telemetry

### Issue: Haptic not working
**Solution**:
1. Test on physical device (not browser emulator)
2. Check navigator.vibrate support
3. Verify pattern format: [duration1, pause1, duration2]

### Issue: Build fails
**Solution**:
1. Run type check: `npm run type-check`
2. Fix TypeScript errors
3. Verify all imports correct

---

## 📝 Before You Start Phase 5.3

After Phase 5.2 is complete:
```
✅ All Jest tests passing (160/160)
✅ All E2E tests passing (55+/55+)
✅ Coverage at 100%
✅ No console errors
✅ Manually tested on device
↓
THEN START PHASE 5.3: Documentation
- Create PR implementation plan
- Create acceptance criteria
- Create business impact
- Create completion checklist
```

---

**You're ready to implement!** ✨

All code examples provided in the full guide. Each task is isolated and testable.
Estimated time: 2 hours from start to finish (all features + testing).
