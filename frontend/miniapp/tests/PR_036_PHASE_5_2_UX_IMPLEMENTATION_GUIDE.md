# PR-036 Phase 5.2: UX Features Implementation Guide

**Phase**: 5.2 UX Features
**Duration**: 2 hours
**Tasks**: Optimistic UI, Toast Notifications, Haptic Feedback, Telemetry

---

## Task 1: Optimistic UI Implementation (30 mins)

### Goal
Remove card immediately on action, restore on error, disable buttons during pending state.

### Implementation File: `page.tsx`

```typescript
// Current code - BEFORE
export default function ApprovalsPage() {
  const [signals, setSignals] = useState<Signal[]>([]);

  const handleApprove = async (signalId: string) => {
    try {
      await approveSignal(signalId);
      // Card removed AFTER API completes
      setSignals(prev => prev.filter(s => s.id !== signalId));
    } catch (error) {
      // Error toast
    }
  };

  return (
    <div className="space-y-4">
      {signals.map(signal => (
        <SignalCard
          key={signal.id}
          signal={signal}
          onApprove={() => handleApprove(signal.id)}
          isLoading={false}  // Not tracking pending state
        />
      ))}
    </div>
  );
}

// NEW code - AFTER (Optimistic UI)
export default function ApprovalsPage() {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [pendingSignalIds, setPendingSignalIds] = useState<Set<string>>(new Set());

  const handleApprove = async (signalId: string) => {
    // 1. Optimistically remove card
    const previousSignals = signals;
    setSignals(prev => prev.filter(s => s.id !== signalId));

    // 2. Mark as pending (disable button)
    setPendingSignalIds(prev => new Set([...prev, signalId]));

    try {
      // 3. Make API call
      await approveSignal(signalId);
      // Success - card already removed, just clear pending
      setPendingSignalIds(prev => {
        const newSet = new Set(prev);
        newSet.delete(signalId);
        return newSet;
      });
    } catch (error) {
      // 4. On error - RESTORE card
      setSignals(previousSignals);
      setPendingSignalIds(prev => {
        const newSet = new Set(prev);
        newSet.delete(signalId);
        return newSet;
      });

      // Show error toast
      showErrorToast(`Failed to approve signal: ${error.message}`);
    }
  };

  const handleReject = async (signalId: string) => {
    // Same pattern as approve
    const previousSignals = signals;
    setSignals(prev => prev.filter(s => s.id !== signalId));
    setPendingSignalIds(prev => new Set([...prev, signalId]));

    try {
      await rejectSignal(signalId);
      setPendingSignalIds(prev => {
        const newSet = new Set(prev);
        newSet.delete(signalId);
        return newSet;
      });
    } catch (error) {
      setSignals(previousSignals);
      setPendingSignalIds(prev => {
        const newSet = new Set(prev);
        newSet.delete(signalId);
        return newSet;
      });

      showErrorToast(`Failed to reject signal: ${error.message}`);
    }
  };

  return (
    <div className="space-y-4">
      {signals.map(signal => (
        <SignalCard
          key={signal.id}
          signal={signal}
          onApprove={() => handleApprove(signal.id)}
          onReject={() => handleReject(signal.id)}
          isPending={pendingSignalIds.has(signal.id)}  // Pass pending state
        />
      ))}
    </div>
  );
}
```

### Implementation File: `components/SignalCard.tsx`

```typescript
// BEFORE - No pending state handling
export function SignalCard({ signal, onApprove, onReject }: Props) {
  return (
    <div data-testid="signal-card">
      <button
        data-testid="approve-btn"
        onClick={() => onApprove()}
        className="bg-green-500 px-4 py-2 rounded"
      >
        Approve
      </button>
      <button
        data-testid="reject-btn"
        onClick={() => onReject()}
        className="bg-red-500 px-4 py-2 rounded"
      >
        Reject
      </button>
    </div>
  );
}

// AFTER - With pending state
interface SignalCardProps {
  signal: Signal;
  onApprove: () => void;
  onReject: () => void;
  isPending?: boolean;  // NEW
}

export function SignalCard({
  signal,
  onApprove,
  onReject,
  isPending = false  // NEW
}: SignalCardProps) {
  return (
    <div data-testid="signal-card">
      <button
        data-testid="approve-btn"
        onClick={() => onApprove()}
        disabled={isPending}  // NEW
        className={`
          bg-green-500 px-4 py-2 rounded
          ${isPending ? 'opacity-50 cursor-not-allowed' : 'hover:bg-green-600'}
        `}
      >
        {isPending ? 'Processing...' : 'Approve'}
      </button>
      <button
        data-testid="reject-btn"
        onClick={() => onReject()}
        disabled={isPending}  // NEW
        className={`
          bg-red-500 px-4 py-2 rounded
          ${isPending ? 'opacity-50 cursor-not-allowed' : 'hover:bg-red-600'}
        `}
      >
        {isPending ? 'Processing...' : 'Reject'}
      </button>
    </div>
  );
}
```

### Testing Optimistic UI
```typescript
// Test: Should remove card immediately
test('should remove card immediately on approve', async () => {
  render(<ApprovalsPage signals={[signal1, signal2, signal3]} />);

  let cardCount = screen.getAllByTestId('signal-card').length;
  expect(cardCount).toBe(3);

  // Click approve
  const approveBtn = screen.getAllByTestId('approve-btn')[0];
  fireEvent.click(approveBtn);

  // Card should be removed IMMEDIATELY (not waiting for API)
  cardCount = screen.queryAllByTestId('signal-card').length;
  expect(cardCount).toBe(2);
});

// Test: Should restore on error
test('should restore card on error', async () => {
  // Mock API to fail
  mockApproveSignal.mockRejectedValueOnce(new Error('Network error'));

  render(<ApprovalsPage signals={[signal1, signal2, signal3]} />);

  // Click approve
  const approveBtn = screen.getAllByTestId('approve-btn')[0];
  fireEvent.click(approveBtn);

  // Wait for error to be handled
  await waitFor(() => {
    const cardCount = screen.getAllByTestId('signal-card').length;
    expect(cardCount).toBe(3);  // Restored
  });
});
```

---

## Task 2: Toast Notifications Implementation (30 mins)

### Installation
```bash
npm install react-toastify
```

### Setup: `app/layout.tsx`

```typescript
import { ToastContainer } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';

export default function RootLayout({ children }) {
  return (
    <html>
      <body>
        {children}

        {/* Toast container - renders all toasts */}
        <ToastContainer
          position="bottom-right"
          autoClose={3000}
          hideProgressBar={false}
          newestOnTop={true}
          closeOnClick
          rtl={false}
          pauseOnFocusLoss
          draggable
          pauseOnHover
          theme="dark"  // or "light"
        />
      </body>
    </html>
  );
}
```

### Helper: `lib/toastNotifications.ts`

```typescript
import { toast, ToastOptions } from 'react-toastify';

const defaultOptions: ToastOptions = {
  position: 'bottom-right',
  autoClose: 3000,
  hideProgressBar: false,
};

export const showSuccessToast = (message: string) => {
  toast.success(message, {
    ...defaultOptions,
    icon: '✅',
  });
};

export const showErrorToast = (message: string) => {
  toast.error(message, {
    ...defaultOptions,
    icon: '❌',
  });
};

export const showInfoToast = (message: string) => {
  toast.info(message, {
    ...defaultOptions,
    icon: 'ℹ️',
  });
};

export const showWarningToast = (message: string) => {
  toast.warning(message, {
    ...defaultOptions,
    icon: '⚠️',
  });
};
```

### Implementation: `page.tsx`

```typescript
import { showSuccessToast, showErrorToast } from '@/lib/toastNotifications';

export default function ApprovalsPage() {
  const handleApprove = async (signalId: string) => {
    const previousSignals = signals;
    setSignals(prev => prev.filter(s => s.id !== signalId));
    setPendingSignalIds(prev => new Set([...prev, signalId]));

    try {
      await approveSignal(signalId);

      // Success - show toast
      showSuccessToast('✅ Signal approved successfully');  // NEW

      setPendingSignalIds(prev => {
        const newSet = new Set(prev);
        newSet.delete(signalId);
        return newSet;
      });
    } catch (error) {
      setSignals(previousSignals);
      setPendingSignalIds(prev => {
        const newSet = new Set(prev);
        newSet.delete(signalId);
        return newSet;
      });

      // Error - show toast
      showErrorToast(
        `Failed to approve signal: ${error instanceof Error ? error.message : 'Unknown error'}`
      );  // NEW
    }
  };

  const handleReject = async (signalId: string) => {
    const previousSignals = signals;
    setSignals(prev => prev.filter(s => s.id !== signalId));
    setPendingSignalIds(prev => new Set([...prev, signalId]));

    try {
      // Show reason modal first if needed
      const reason = await getRejectReason();  // Or skip if no reason needed

      await rejectSignal(signalId, reason);

      // Success - show toast
      showSuccessToast('✅ Signal rejected');  // NEW

      setPendingSignalIds(prev => {
        const newSet = new Set(prev);
        newSet.delete(signalId);
        return newSet;
      });
    } catch (error) {
      setSignals(previousSignals);
      setPendingSignalIds(prev => {
        const newSet = new Set(prev);
        newSet.delete(signalId);
        return newSet;
      });

      // Error - show toast
      showErrorToast(
        `Failed to reject signal: ${error instanceof Error ? error.message : 'Unknown error'}`
      );  // NEW
    }
  };

  return (
    <div className="space-y-4">
      {signals.map(signal => (
        <SignalCard
          key={signal.id}
          signal={signal}
          onApprove={() => handleApprove(signal.id)}
          onReject={() => handleReject(signal.id)}
          isPending={pendingSignalIds.has(signal.id)}
        />
      ))}
    </div>
  );
}
```

### Testing Toasts
```typescript
test('should show success toast on approve', async () => {
  mockApproveSignal.mockResolvedValueOnce({ success: true });

  render(<ApprovalsPage />);

  const approveBtn = screen.getAllByTestId('approve-btn')[0];
  fireEvent.click(approveBtn);

  // Toast should appear
  await waitFor(() => {
    const toast = screen.getByText(/Signal approved successfully/i);
    expect(toast).toBeInTheDocument();
  });
});

test('should show error toast on failure', async () => {
  mockApproveSignal.mockRejectedValueOnce(new Error('API Error'));

  render(<ApprovalsPage />);

  const approveBtn = screen.getAllByTestId('approve-btn')[0];
  fireEvent.click(approveBtn);

  // Error toast should appear
  await waitFor(() => {
    const errorToast = screen.getByText(/Failed to approve signal/i);
    expect(errorToast).toBeInTheDocument();
  });
});
```

---

## Task 3: Haptic Feedback Implementation (15 mins)

### Helper: `lib/hapticFeedback.ts`

```typescript
/**
 * Haptic feedback patterns for common user interactions
 * Uses Navigator.vibrate API (mobile devices only)
 */

export type HapticPattern = 'success' | 'error' | 'warning' | 'tap';

const PATTERNS: Record<HapticPattern, number | number[]> = {
  tap: [20],                    // Single short vibration
  success: [50, 30, 100],       // Double tap
  error: [200, 100, 200],       // Three quick pulses
  warning: [100, 200, 100],     // Warning pulse
};

export const triggerHaptic = (pattern: HapticPattern = 'tap'): boolean => {
  // Check if device supports vibration
  const vibrate = navigator.vibrate || (navigator as any).webkitVibrate;

  if (!vibrate) {
    console.debug('Device does not support vibration API');
    return false;
  }

  try {
    vibrate.call(navigator, PATTERNS[pattern]);
    return true;
  } catch (error) {
    console.error('Haptic feedback failed:', error);
    return false;
  }
};
```

### Implementation: `lib/approvals.ts` (Service Layer)

```typescript
import { triggerHaptic } from './hapticFeedback';

export const approveSignal = async (signalId: string): Promise<ApprovalResult> => {
  try {
    const response = await fetch(`${API_BASE}/api/v1/approve`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${getAuthToken()}`,
      },
      body: JSON.stringify({ signal_id: signalId }),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    // Success - trigger success haptic
    triggerHaptic('success');  // NEW

    return response.json();
  } catch (error) {
    // Error - trigger error haptic
    triggerHaptic('error');  // NEW
    throw error;
  }
};

export const rejectSignal = async (signalId: string): Promise<RejectionResult> => {
  try {
    const response = await fetch(`${API_BASE}/api/v1/reject`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${getAuthToken()}`,
      },
      body: JSON.stringify({ signal_id: signalId }),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    // Success - trigger success haptic
    triggerHaptic('success');  // NEW

    return response.json();
  } catch (error) {
    // Error - trigger error haptic
    triggerHaptic('error');  // NEW
    throw error;
  }
};
```

### Testing Haptic Feedback
```typescript
test('should trigger success haptic on approval', async () => {
  const vibrateSpyOn = jest.spyOn(navigator, 'vibrate').mockReturnValue(true);

  mockApproveSignal.mockResolvedValueOnce({ success: true });

  render(<ApprovalsPage />);

  const approveBtn = screen.getAllByTestId('approve-btn')[0];
  fireEvent.click(approveBtn);

  // Vibration should be called with success pattern
  await waitFor(() => {
    expect(vibrateSpyOn).toHaveBeenCalledWith([50, 30, 100]);
  });

  vibrateSpyOn.mockRestore();
});

test('should trigger error haptic on failure', async () => {
  const vibrateSpyOn = jest.spyOn(navigator, 'vibrate').mockReturnValue(true);

  mockApproveSignal.mockRejectedValueOnce(new Error('API Error'));

  render(<ApprovalsPage />);

  const approveBtn = screen.getAllByTestId('approve-btn')[0];
  fireEvent.click(approveBtn);

  // Vibration should be called with error pattern
  await waitFor(() => {
    expect(vibrateSpyOn).toHaveBeenCalledWith([200, 100, 200]);
  });

  vibrateSpyOn.mockRestore();
});
```

---

## Task 4: Telemetry Integration (30 mins)

### Helper: `lib/telemetry.ts`

```typescript
import { v4 as uuidv4 } from 'uuid';

/**
 * Telemetry tracking for miniapp usage analytics
 *
 * Events tracked:
 * - miniapp_approval_click_total
 * - miniapp_rejection_click_total
 * - miniapp_signal_detail_view_total
 * - miniapp_error_total
 */

export interface TelemetryEvent {
  event_name: string;
  timestamp: string;
  user_id?: string;
  signal_id?: string;
  confidence?: number;
  maturity?: number;
  error_type?: string;
  request_id: string;
}

const getRequestId = (): string => {
  // Try to get from localStorage (persisted for session)
  let requestId = sessionStorage.getItem('_request_id');
  if (!requestId) {
    requestId = uuidv4();
    sessionStorage.setItem('_request_id', requestId);
  }
  return requestId;
};

const getAuthToken = (): string | null => {
  return localStorage.getItem('jwt_token');
};

export const trackEvent = async (
  eventName: string,
  metadata?: Partial<TelemetryEvent>
): Promise<void> => {
  try {
    const event: TelemetryEvent = {
      event_name: eventName,
      timestamp: new Date().toISOString(),
      request_id: getRequestId(),
      ...metadata,
    };

    // Send to telemetry endpoint
    await fetch('/api/v1/telemetry/track', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${getAuthToken()}`,
      },
      body: JSON.stringify(event),
      keepalive: true,  // Ensure delivery even if page unloads
    }).catch(error => {
      // Silent failure - don't disrupt user experience
      console.debug('Telemetry tracking failed:', error);
    });
  } catch (error) {
    console.debug('Error tracking event:', error);
  }
};

export const trackApprovalClick = (signalId: string, confidence: number, maturity: number) => {
  trackEvent('miniapp_approval_click_total', {
    signal_id: signalId,
    confidence,
    maturity,
  });
};

export const trackRejectionClick = (signalId: string, confidence: number, maturity: number) => {
  trackEvent('miniapp_rejection_click_total', {
    signal_id: signalId,
    confidence,
    maturity,
  });
};

export const trackSignalDetailView = (signalId: string) => {
  trackEvent('miniapp_signal_detail_view_total', {
    signal_id: signalId,
  });
};

export const trackError = (errorType: string, signalId?: string) => {
  trackEvent('miniapp_error_total', {
    error_type: errorType,
    signal_id: signalId,
  });
};
```

### Implementation: `page.tsx`

```typescript
import {
  trackApprovalClick,
  trackRejectionClick,
  trackError,
} from '@/lib/telemetry';

export default function ApprovalsPage() {
  const handleApprove = async (signal: Signal) => {
    const { id, confidence, maturity } = signal;

    const previousSignals = signals;
    setSignals(prev => prev.filter(s => s.id !== id));
    setPendingSignalIds(prev => new Set([...prev, id]));

    try {
      // Track before action
      trackApprovalClick(id, confidence, maturity);  // NEW

      await approveSignal(id);

      showSuccessToast('✅ Signal approved successfully');

      setPendingSignalIds(prev => {
        const newSet = new Set(prev);
        newSet.delete(id);
        return newSet;
      });
    } catch (error) {
      setSignals(previousSignals);
      setPendingSignalIds(prev => {
        const newSet = new Set(prev);
        newSet.delete(id);
        return newSet;
      });

      // Track error
      trackError('approval_failed', id);  // NEW

      showErrorToast(
        `Failed to approve signal: ${error instanceof Error ? error.message : 'Unknown error'}`
      );
    }
  };

  const handleReject = async (signal: Signal) => {
    const { id, confidence, maturity } = signal;

    const previousSignals = signals;
    setSignals(prev => prev.filter(s => s.id !== id));
    setPendingSignalIds(prev => new Set([...prev, id]));

    try {
      // Track before action
      trackRejectionClick(id, confidence, maturity);  // NEW

      await rejectSignal(id);

      showSuccessToast('✅ Signal rejected');

      setPendingSignalIds(prev => {
        const newSet = new Set(prev);
        newSet.delete(id);
        return newSet;
      });
    } catch (error) {
      setSignals(previousSignals);
      setPendingSignalIds(prev => {
        const newSet = new Set(prev);
        newSet.delete(id);
        return newSet;
      });

      // Track error
      trackError('rejection_failed', id);  // NEW

      showErrorToast(
        `Failed to reject signal: ${error instanceof Error ? error.message : 'Unknown error'}`
      );
    }
  };

  return (
    <div className="space-y-4">
      {signals.map(signal => (
        <SignalCard
          key={signal.id}
          signal={signal}
          onApprove={() => handleApprove(signal)}
          onReject={() => handleReject(signal)}
          isPending={pendingSignalIds.has(signal.id)}
        />
      ))}
    </div>
  );
}
```

### Implementation: `components/SignalCard.tsx` (Drawer tracking)

```typescript
import { trackSignalDetailView } from '@/lib/telemetry';

export function SignalCard({ signal, onApprove, onReject }: Props) {
  const handleCardClick = () => {
    trackSignalDetailView(signal.id);  // NEW
    // Open drawer
    setDrawerOpen(true);
  };

  return (
    <div
      data-testid="signal-card"
      onClick={handleCardClick}
      className="cursor-pointer"
    >
      {/* Card content */}
    </div>
  );
}
```

### Testing Telemetry
```typescript
test('should track approval click', async () => {
  const trackSpy = jest.spyOn(telemetry, 'trackApprovalClick');

  mockApproveSignal.mockResolvedValueOnce({ success: true });

  render(<ApprovalsPage signals={[signal1]} />);

  const approveBtn = screen.getByTestId('approve-btn');
  fireEvent.click(approveBtn);

  await waitFor(() => {
    expect(trackSpy).toHaveBeenCalledWith(
      signal1.id,
      signal1.confidence,
      signal1.maturity
    );
  });
});

test('should track error when approval fails', async () => {
  const trackErrorSpy = jest.spyOn(telemetry, 'trackError');

  mockApproveSignal.mockRejectedValueOnce(new Error('API Error'));

  render(<ApprovalsPage signals={[signal1]} />);

  const approveBtn = screen.getByTestId('approve-btn');
  fireEvent.click(approveBtn);

  await waitFor(() => {
    expect(trackErrorSpy).toHaveBeenCalledWith('approval_failed', signal1.id);
  });
});
```

---

## Summary: Files to Modify

### Files to Create
```
✅ lib/toastNotifications.ts
✅ lib/hapticFeedback.ts
✅ lib/telemetry.ts
```

### Files to Modify
```
app/layout.tsx              // Add ToastContainer
app/approvals/page.tsx      // Add optimistic UI, call telemetry
components/SignalCard.tsx   // Add isPending prop, call telemetry
lib/approvals.ts            // Add haptic feedback
```

### Code Changes Summary
```
Total Lines Added:     ~450
Test Cases Updated:    15+
Features Implemented:  4 (Optimistic UI, Toasts, Haptic, Telemetry)
```

---

## Testing Checklist for Phase 5.2

After implementing all features:

```
□ Optimistic UI
  □ Card removed immediately on approve
  □ Card restored on error
  □ Button disabled during pending
  □ Button text changes to "Processing..."

□ Toast Notifications
  □ Success toast appears on approve
  □ Error toast appears on failure
  □ Toast auto-dismisses after 3 seconds
  □ Multiple toasts don't overlap

□ Haptic Feedback
  □ [50, 30, 100] pattern on success
  □ [200, 100, 200] pattern on error
  □ No error if device doesn't support

□ Telemetry
  □ Event sent on approval
  □ Event includes signal_id, confidence, maturity
  □ Event sent on error with error_type
  □ Request ID persisted in session
```

---

## Timeline

**Total Phase 5.2 Duration**: 2 hours

1. **Optimistic UI** (30 mins)
   - Modify page.tsx (remove card logic)
   - Modify SignalCard.tsx (isPending prop)
   - Test optimistic UI locally

2. **Toast Notifications** (30 mins)
   - Create toastNotifications.ts
   - Modify layout.tsx (add ToastContainer)
   - Modify page.tsx (call show*Toast functions)
   - Test toasts locally

3. **Haptic Feedback** (15 mins)
   - Create hapticFeedback.ts
   - Modify approvals.ts (call triggerHaptic)
   - Test with mobile device or emulator

4. **Telemetry** (30 mins)
   - Create telemetry.ts
   - Modify page.tsx (call track* functions)
   - Modify SignalCard.tsx (trackSignalDetailView)
   - Test telemetry events

5. **Final Testing** (15 mins)
   - Run jest tests: `npm test`
   - Run E2E tests: `npx playwright test`
   - Verify all 160 Jest + 55 E2E tests pass

**Total Time**: 2 hours
