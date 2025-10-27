# PR-039 ↔ PR-033 Integration - Test Plan

## Test Scenarios

### Tier 1: Navigation & Basic UI

#### Test 1.1: Billing → Devices Navigation
```
Precondition: User at /billing page
Steps:
  1. Locate AccountNav component
  2. Click "Devices" tab
  3. Verify page navigates to /devices
  4. Verify "Devices" tab shows as active (blue highlight)
  5. Verify "Billing" tab shows as inactive (gray)
Expected: ✅ Smooth navigation, correct visual state
```

#### Test 1.2: Devices → Billing Navigation
```
Precondition: User at /devices page
Steps:
  1. Locate AccountNav component
  2. Click "Billing" tab
  3. Verify page navigates to /billing
  4. Verify "Billing" tab shows as active
  5. Verify "Devices" tab shows as inactive
Expected: ✅ Smooth navigation, correct visual state
```

#### Test 1.3: Device Count Badge Display
```
Precondition: User has 3 registered devices, premium tier
Steps:
  1. Navigate to /billing
  2. Observe AccountNav device badge
  3. Should show "3/5" with green indicator
  4. Navigate to /devices
  5. Observe AccountNav device badge
  6. Should show same "3/5" with green indicator
Expected: ✅ Badge displays count and limit consistently
```

#### Test 1.4: Tier Badge Display
```
Precondition: User has premium subscription
Steps:
  1. Navigate to any page with AccountNav
  2. Observe tier badge in AccountNav
  3. Should show "premium" in blue badge
  4. For free tier, badge should not show
Expected: ✅ Tier displays correctly (free tier hidden, others shown)
```

---

### Tier 2: Device Gating - Free Tier

#### Test 2.1: Free User - Cannot Add 2nd Device
```
Precondition: User has free tier, 1 device registered
Steps:
  1. Navigate to /devices
  2. Observe "Add Device" button state
  3. Should show "1/1 device" in badge (orange)
  4. Try to click "Add Device" button
  5. Button should be DISABLED (greyed out)
  6. Hover over button → should show tooltip "Device limit reached"
Expected: ✅ Button disabled with clear message
```

#### Test 2.2: Free User - See Device Limit Error Card
```
Precondition: User has free tier, 1 device registered
Steps:
  1. Navigate to /devices
  2. Scroll down to find error/warning cards
  3. Should see RED card: "Device Limit Reached"
  4. Card should show: "1/1 devices"
  5. Card should have "Upgrade to premium for 5 devices" link
Expected: ✅ Error card visible with upgrade CTA
```

#### Test 2.3: Free User - Click Upgrade from Device Limit Card
```
Precondition: At /devices with device limit error card visible
Steps:
  1. Locate "Upgrade to premium" link
  2. Click the link
  3. Should navigate to /billing
  4. Should scroll to upgrade/plan section (optional)
Expected: ✅ Navigates back to billing to upgrade
```

#### Test 2.4: Free User - Add Device After Upgrade to Premium
```
Precondition: User upgrades from free to premium tier
Steps:
  1. Subscription updated to premium
  2. Navigate to /devices (page may need refresh)
  3. Should see "1/5 device" (green, plenty room)
  4. "Add Device" button should be ENABLED ✅
  5. Error card should be GONE
  6. No warning cards
Expected: ✅ Can now add more devices with premium
```

---

### Tier 3: Device Gating - Premium Tier

#### Test 3.1: Premium User - Add Multiple Devices
```
Precondition: User has premium tier, 0 devices
Steps:
  1. Navigate to /devices
  2. Should see "0/5" in green (plenty room)
  3. Add device 1: "EA-01" ✅ success
  4. Add device 2: "EA-02" ✅ success
  5. Add device 3: "EA-03" ✅ success
  6. Add device 4: "EA-04" ✅ success
  7. Add device 5: "EA-05" ✅ success
  8. Try add device 6: Button should be DISABLED
Expected: ✅ Can add up to 5, 6th blocked
```

#### Test 3.2: Premium User - Warning at 75% Capacity
```
Precondition: User has premium tier, 4 devices (80%)
Steps:
  1. Navigate to /devices
  2. Should see "4/5" in orange (warning color)
  3. Should see AMBER warning card: "Approaching Device Limit"
  4. Card shows: "1 slot remaining"
  5. "Add Device" button still ENABLED (not at limit yet)
Expected: ✅ Warning shows at 75%, button still works
```

#### Test 3.3: Premium User - Error at 100% Capacity
```
Precondition: User has premium tier, 5 devices (100%)
Steps:
  1. Navigate to /devices
  2. Should see "5/5" in red (error color)
  3. Should see RED error card: "Device Limit Reached"
  4. Card shows: "5/5 devices"
  5. "Add Device" button DISABLED
  6. Error card has "Upgrade to vip" link
Expected: ✅ Error shows at 100%, button disabled
```

#### Test 3.4: Premium User - View All Devices Link on Billing
```
Precondition: User on /billing with devices registered
Steps:
  1. Scroll to "EA Devices" section on /billing
  2. Should see "View All Devices →" link next to header
  3. Click the link
  4. Should navigate to /devices
  5. Device list should be visible
Expected: ✅ Easy navigation from billing to full device list
```

---

### Tier 4: Device Gating - VIP/Enterprise

#### Test 4.1: VIP User - High Device Limit
```
Precondition: User has vip tier
Steps:
  1. Navigate to /devices
  2. Should see "X/10" in badge (green)
  3. No warning cards at any capacity
  4. Can add devices up to 10 freely
  5. At 10 devices, button might show limit (depends on design)
Expected: ✅ Can use all 10 device slots
```

#### Test 4.2: Enterprise User - Unlimited Devices
```
Precondition: User has enterprise tier
Steps:
  1. Navigate to /devices
  2. Badge might show "X/999" or "unlimited"
  3. No warning cards ever
  4. Can add many devices without limit
  5. Backend enforces any limit if needed
Expected: ✅ No artificial limits for enterprise
```

---

### Tier 5: Cross-Page Synchronization

#### Test 5.1: Device Count Sync After Registration
```
Precondition: User on /devices, billings open in another tab
Steps:
  1. Register a new device on /devices
  2. Switch to /billing tab
  3. Refresh /billing page
  4. Device count in navigation should update
  5. Device list should show new device
Expected: ✅ Device count synchronized across pages
```

#### Test 5.2: Device Count Sync After Revocation
```
Precondition: User has 3 devices, on /devices
Steps:
  1. Revoke one device (confirm dialog)
  2. Device list updates to show 2 devices
  3. Navigation badge updates to "2/5"
  4. Navigate to /billing
  5. Device count should show 2 devices
  6. Badge on /billing should show "2/5"
Expected: ✅ Revocation synced across pages
```

#### Test 5.3: Subscription Tier Sync
```
Precondition: User subscribed to premium
Steps:
  1. Navigate to /billing
  2. Should see "premium" tier badge
  3. Navigate to /devices
  4. Should see "premium" tier badge
  5. Both pages show same tier
  6. Device limit calculated from same tier
Expected: ✅ Tier information consistent
```

---

### Tier 6: User Workflows

#### Workflow 6.1: Free → Premium Upgrade Journey
```
User Journey:
  1. Free tier user at /devices with 1 device
  2. Wants to add 2nd device
  3. Clicks "Add Device" button → DISABLED
  4. Sees error card with upgrade CTA
  5. Clicks "Upgrade to premium"
  6. Redirected to /billing
  7. Reviews plan: Premium = 5 devices + features
  8. Clicks upgrade/checkout button
  9. Completes Stripe payment
  10. Returns to app with premium tier
  11. Navigates back to /devices
  12. Now can add device 2 ✅
Expected: ✅ Smooth upgrade flow with clear path
```

#### Workflow 6.2: Premium User Manages Multiple EAs
```
User Journey:
  1. Premium user with 3 EAs (EA-prod, EA-staging, EA-dev)
  2. At /billing, sees subscription active
  3. Clicks "View All Devices" to see all 3 EAs
  4. At /devices, sees all 3 with last seen times
  5. Wants to rename EA-staging to EA-testing
  6. Clicks device, updates name ✅
  7. Wants to revoke EA-dev after moving to prod
  8. Clicks revoke, confirms
  9. Device count drops to 2/5
  10. Can add new device for backup ✅
Expected: ✅ Smooth device lifecycle management
```

#### Workflow 6.3: Enterprise User Auditing
```
User Journey:
  1. Enterprise user with 50+ devices (automated traders)
  2. Goes to /devices to audit all active EAs
  3. Sees device list with names, creation dates, last seen
  4. Wants to check billing history
  5. Navigates to /billing tab
  6. Reviews invoices, plans
  7. Wants to manage devices again
  8. Navigates back to /devices tab
  9. All previous state preserved
Expected: ✅ Seamless tab switching with state preservation
```

---

### Tier 7: Edge Cases & Error Handling

#### Test 7.1: No Subscription Data Available
```
Precondition: API fails to return subscription data
Steps:
  1. Navigate to /devices
  2. Subscription fetch fails
  3. Should gracefully default to "free" tier
  4. Should show gating as if free tier (1 device limit)
  5. Error should be logged but page functional
Expected: ✅ Fallback to safe default (free tier)
```

#### Test 7.2: No Devices Data Available
```
Precondition: API fails to return devices list
Steps:
  1. Navigate to /devices
  2. Devices fetch fails
  3. Should show error message to user
  4. Provide "Retry" button
  5. Clicking retry fetches again
Expected: ✅ Error messaging with recovery option
```

#### Test 7.3: Rapid Page Switching
```
Precondition: User rapidly clicks between tabs
Steps:
  1. At /billing, click Devices → /devices
  2. Immediately click Billing → /billing
  3. Immediately click Devices → /devices
  4. No crashed state
  5. Navigation smooth and responsive
Expected: ✅ Handles rapid navigation without issues
```

#### Test 7.4: Concurrent Device Operations
```
Precondition: Two browser tabs with same account
Steps:
  1. Tab A: Add device 1 at /devices
  2. Tab B: At same time, try add device 2 at /devices
  3. One succeeds, one may fail with "race condition"
  4. User can refresh to see true state
Expected: ⚠️ Possible race condition (expected, use versioning if critical)
```

---

### Tier 8: Mobile/Responsive Testing

#### Test 8.1: Mobile - Navigation on Small Screen
```
Precondition: Mobile device (375px width), /devices page
Steps:
  1. AccountNav should stack or be compact
  2. Tab icons visible
  3. Can tap to navigate
  4. No overflow or wrapping issues
  5. Device count badge visible and readable
Expected: ✅ Responsive design works on mobile
```

#### Test 8.2: Tablet - Layout Optimal
```
Precondition: Tablet device (768px width)
Steps:
  1. Full layout visible without scrolling
  2. Navigation clear
  3. Cards display properly
  4. Buttons easily tappable (44x44px minimum)
Expected: ✅ Optimal tablet experience
```

---

### Tier 9: Dark Mode

#### Test 9.1: Dark Mode - AccountNav Contrast
```
Precondition: App in dark mode, /billing page
Steps:
  1. AccountNav background should contrast with page
  2. Text color readable (white on dark background)
  3. Tier badge should be visible
  4. Device count badge should be visible
  5. Links should have distinct color (blue)
Expected: ✅ All elements readable in dark mode
```

#### Test 9.2: Dark Mode - Error/Warning Cards
```
Precondition: App in dark mode, device limit warning visible
Steps:
  1. Red error card should be visible (not too dark)
  2. Amber warning card should be readable
  3. Blue info card should contrast
  4. Text color appropriate for each background
Expected: ✅ Color scheme works in dark mode
```

---

### Tier 10: Accessibility

#### Test 10.1: Keyboard Navigation
```
Precondition: Using keyboard only (no mouse)
Steps:
  1. Tab through AccountNav elements
  2. Can reach both navigation links
  3. Can activate links with Enter key
  4. Focus visible on buttons
  5. Tab order logical and useful
Expected: ✅ Full keyboard navigation support
```

#### Test 10.2: Screen Reader Support
```
Precondition: Using screen reader (NVDA/JAWS)
Steps:
  1. AccountNav labeled as navigation
  2. Links announced with proper names
  3. Active state announced
  4. Device count announced clearly
  5. Button disabled state announced
Expected: ✅ Screen reader friendly
```

---

## Performance Tests

### Test P1: Page Load Time
```
Benchmark: < 2 seconds to interactive
Measure:
  - Time to render AccountNav
  - Time to fetch subscription data
  - Time to fetch device list
  - Time to render full page

Expected: ✅ < 2s page load
```

### Test P2: Navigation Latency
```
Benchmark: < 300ms for page switch
Measure:
  - Time from click to new page rendered
  - Time for data re-fetch on new page

Expected: ✅ < 300ms navigation
```

### Test P3: Device List Rendering
```
Benchmark: < 500ms to render 10+ devices
Measure:
  - Time to render full device list
  - Time for interactive buttons

Expected: ✅ < 500ms render time
```

---

## Regression Tests

### Test R1: Existing Billing Features
```
Verify existing /billing page features still work:
  - ✅ Subscription card displays
  - ✅ Invoice history shows
  - ✅ Portal link works
  - ✅ Checkout link works
```

### Test R2: Existing Device Features
```
Verify existing /devices page features still work:
  - ✅ Device registration works
  - ✅ Device revocation works
  - ✅ Device renaming works
  - ✅ Secret shown once works
```

---

## Test Execution Checklist

- [ ] Tier 1: Navigation & Basic UI (4 tests)
- [ ] Tier 2: Free Tier Gating (4 tests)
- [ ] Tier 3: Premium Tier Gating (4 tests)
- [ ] Tier 4: VIP/Enterprise Gating (2 tests)
- [ ] Tier 5: Cross-Page Sync (3 tests)
- [ ] Tier 6: User Workflows (3 tests)
- [ ] Tier 7: Edge Cases (4 tests)
- [ ] Tier 8: Mobile/Responsive (2 tests)
- [ ] Tier 9: Dark Mode (2 tests)
- [ ] Tier 10: Accessibility (2 tests)
- [ ] Performance Tests (3 tests)
- [ ] Regression Tests (2 test suites)

**Total: 31+ test scenarios**

---

## Expected Results Summary

✅ **Navigation**: Smooth, responsive, visual feedback
✅ **Gating**: Works per tier (free=1, premium=5, vip=10, enterprise=∞)
✅ **Warnings**: Show at 75%, 100%, with upgrade CTAs
✅ **Sync**: Device count and tier consistent across pages
✅ **UX**: Clear path from device limit to billing upgrade
✅ **Performance**: < 2s load, < 300ms navigation
✅ **Responsiveness**: Works on mobile, tablet, desktop
✅ **Accessibility**: Keyboard and screen reader support

---

**Status: Ready for QA Testing** ✅
