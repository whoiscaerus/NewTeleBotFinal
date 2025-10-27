# PR-039 ↔ PR-033 Integration Architecture

## Page Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    Mini App Home/Dashboard                   │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ├─────────────────┬──────────────────┐
                 │                 │                  │
         ┌─────────────┐    ┌──────────────┐  ┌────────────┐
         │  Approvals  │    │  Billing     │  │  Devices   │
         │  (Current)  │    │  (PR-033)    │  │  (PR-039)  │
         └─────────────┘    └──────┬───────┘  └─────┬──────┘
                                   │                 │
                                   └────────┬────────┘
                                            │
                                    ┌───────▼───────┐
                                    │  AccountNav   │
                                    │  (NEW)        │
                                    │               │
                                    │ Billing│Device│
                                    └───────┬───────┘
                                            │
                        ┌───────────────────┴──────────────────┐
                        │                                      │
                   ┌────▼──────┐                        ┌──────▼────┐
                   │ /billing   │                       │ /devices   │
                   │  Page      │◄─────────────────────►│  Page      │
                   │            │  "View All Devices"   │            │
                   │ PR-033 +   │                       │ PR-039 +   │
                   │ Enhanced   │                       │ Enhanced   │
                   └────┬───────┘                       └──────┬─────┘
                        │                                      │
        ┌───────────────┤                      ┌───────────────┤
        │               │                      │               │
        │         ┌─────▼──────────────┐       │               │
        │         │ Subscription Data  │       │               │
        │         │ (tier, status)     │       │               │
        │         └────────────────────┘       │               │
        │                                      │               │
        │         ┌─────────────────────┐      │               │
        │         │ Device List + Count │      │               │
        │         │ (from API)          │      │               │
        │         └─────────────────────┘      │               │
        │                                      │               │
        └──────────────────┬───────────────────┘               │
                           │                                   │
                      ┌────▼────────────┐                      │
                      │ useDeviceGating │                      │
                      │ (NEW Hook)      │◄─────────────────────┘
                      │                 │
                      │ Tier → Limit    │
                      │ Count→ Available│
                      │ Can Add? Yes/No │
                      │ Warnings        │
                      └────┬────────────┘
                           │
          ┌────────────────┤
          │                │
   ┌──────▼──────┐  ┌──────▼──────┐
   │ On Devices  │  │  On Billing │
   │ Page:       │  │  Page:      │
   │             │  │             │
   │ • Show gat  │  │ • Show tier │
   │ • Warn if   │  │ • Show dev  │
   │   75%+      │  │ • Link to   │
   │ • Disable   │  │   devices   │
   │   button if │  │             │
   │   at limit  │  │             │
   └─────────────┘  └─────────────┘
```

---

## Data Flow on Device Registration

```
User clicks "Add Device"
    │
    └─► Device Count = 1/5 (premium tier)
         canAddMore = true
         Warning = none
         Button = ENABLED ✅
         │
         └─► User enters device name
              │
              └─► DeviceList component
                   checks: canAddMore?
                   │
                   ├─ TRUE → Button enabled ✅
                   │         onClick → API call
                   │         │
                   │         └─► POST /api/v1/devices
                   │              {name: "EA-01", secret: "..."}
                   │              │
                   │              └─► Success
                   │                   Device Count = 2/5
                   │                   Update UI
                   │                   Telemetry: miniapp_device_register_total
                   │
                   └─ FALSE → Button disabled ❌
                              Title: "Device limit reached"
                              Error card shown
```

---

## Device Limit Enforcement

```
    ┌─────────────────────────────────────┐
    │ User's Subscription Tier            │
    │ (fetched on page load)              │
    └──────────────┬──────────────────────┘
                   │
                   ▼
    ┌─────────────────────────────────────┐
    │ useDeviceGating Hook                │
    │ Maps Tier → Device Limit            │
    │                                     │
    │ free      → limit=1                 │
    │ premium   → limit=5                 │
    │ vip       → limit=10                │
    │ enterprise→ limit=999               │
    └──────────────┬──────────────────────┘
                   │
                   ▼
    ┌─────────────────────────────────────┐
    │ Current Device Count                │
    │ (fetched from API on load)          │
    └──────────────┬──────────────────────┘
                   │
                   ▼
    ┌─────────────────────────────────────┐
    │ Calculate Gating State              │
    │                                     │
    │ canAddMore = count < limit          │
    │ percentUsed = (count/limit) * 100   │
    │ remaining = max(0, limit - count)   │
    │ isFull = count >= limit             │
    └──────────────┬──────────────────────┘
                   │
                   ▼
    ┌─────────────────────────────────────┐
    │ Render Appropriate UI               │
    │                                     │
    │ IF isFull:                          │
    │   → Error card (RED)                │
    │   → Button DISABLED                 │
    │   → Show upgrade CTA                │
    │                                     │
    │ ELSE IF percentUsed >= 75:          │
    │   → Warning card (AMBER)            │
    │   → Button ENABLED                  │
    │   → Show "slots remaining"          │
    │                                     │
    │ ELSE:                               │
    │   → Info card (BLUE)                │
    │   → Button ENABLED                  │
    │   → Show device count               │
    └─────────────────────────────────────┘
```

---

## Navigation State

```
                ┌─────────────────────┐
                │   AccountNav Comp    │
                │                     │
                │ Billing│  Devices   │
                │         ▲           │
                └────┬────┼───────────┘
                     │    │
           ┌─────────┘    └──────────┐
           │                         │
           ▼                         ▼
    ┌─────────────┐          ┌──────────────┐
    │ /billing    │          │ /devices     │
    │ (active)    │          │ (inactive)   │
    │             │          │              │
    │ Billing tab │          │ Devices tab  │
    │ highlighted │          │ normal       │
    │ (blue)      │          │              │
    └─────────────┘          └──────────────┘

                           OR

    ┌─────────────┐          ┌──────────────┐
    │ /billing    │          │ /devices     │
    │ (inactive)  │          │ (active)     │
    │             │          │              │
    │ Billing tab │          │ Devices tab  │
    │ normal      │          │ highlighted  │
    │             │          │ (blue)       │
    └─────────────┘          └──────────────┘

Navigation state determined by:
  usePathname() hook from next/navigation
  Shows active page with border-bottom highlight
```

---

## Component Hierarchy

```
Mini App Layout
│
├─ Approvals Page (existing)
│
├─ Billing Page (/billing) ─── PR-033 + Enhanced
│  │
│  ├─ AccountNav (NEW)
│  │  ├─ Link to /billing (active)
│  │  └─ Link to /devices (inactive)
│  │
│  ├─ Subscription Card
│  │  └─ Fetches: /api/v1/billing/subscription
│  │
│  ├─ Invoice List
│  │
│  ├─ Devices Section (inline)
│  │  ├─ Device List (via DeviceList component)
│  │  └─ Device Add Form
│  │  └─ "View All Devices" link → /devices
│  │
│  └─ Upgrade Plan Section
│     └─ Links to Stripe checkout
│
└─ Devices Page (/devices) ─── PR-039 + Enhanced
   │
   ├─ AccountNav (NEW)
   │  ├─ Link to /billing (inactive)
   │  └─ Link to /devices (active)
   │
   ├─ Page Header
   │
   ├─ Device Gating Warnings (conditional)
   │  ├─ Info Card: Security info
   │  ├─ Amber Warning: Approaching limit (75%+)
   │  └─ Red Error: At limit (100%)
   │
   ├─ DeviceList Component (enhanced)
   │  ├─ Receive: canAddMore, limitMessage props
   │  ├─ "Add Device" button (enabled/disabled based on gating)
   │  └─ Device list with revoke buttons
   │
   ├─ AddDeviceModal Component
   │  └─ Shows secret once after creation
   │
   └─ How to Setup Guide
```

---

## API Endpoints Used

```
GET /api/v1/billing/subscription
   Response: {tier, status, current_period_start, current_period_end, price}
   Used by: Both /billing and /devices pages
   Purpose: Get subscription tier for device limit calculation

GET /api/v1/devices
   Response: [{id, name, is_active, created_at, last_seen}, ...]
   Used by: Both /billing and /devices pages
   Purpose: Get device list and count

POST /api/v1/devices
   Body: {name}
   Response: {id, name, secret (shown once), created_at}
   Used by: /devices page
   Purpose: Register new device
   Guard: Frontend disables if at limit

DELETE /api/v1/devices/{id}
   Used by: Both pages
   Purpose: Revoke device

PATCH /api/v1/devices/{id}
   Body: {name}
   Used by: Device list
   Purpose: Rename device
```

---

## Integration Benefits

```
┌─────────────────────────────────────────────────────────────┐
│                   Before Integration                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  /billing page     /devices page                           │
│  ├─ Standalone    ├─ Standalone                           │
│  ├─ No links      ├─ No links                             │
│  ├─ Users miss    ├─ Users confused                       │
│  │  devices page  │  about limits                         │
│  └─ No gating     └─ No context                           │
│                                                             │
│  Result: Poor UX, high support tickets                     │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                   After Integration                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  /billing page     /devices page                           │
│  ├─ Connected     ├─ Connected                            │
│  ├─ Tab links     ├─ Tab links                            │
│  ├─ Discover      ├─ Clear limits                         │
│  │  devices       ├─ Smart warnings                       │
│  ├─ See count     ├─ Upgrade CTAs                         │
│  ├─ Manage inline ├─ Easy navigation                      │
│  └─ Deep link     └─ Tier context                         │
│                                                             │
│  Result: Excellent UX, clear path to upgrade              │
│          Better engagement, more conversions               │
└─────────────────────────────────────────────────────────────┘
```

---

## Summary

✅ **Bidirectional Navigation** - Tabs on both pages
✅ **Device Count Gating** - By subscription tier
✅ **Smart Warnings** - Info/Amber/Red based on usage
✅ **Upgrade CTAs** - Guide users to billing
✅ **Synchronized State** - Both pages show same data
✅ **Full Type Safety** - TypeScript throughout
✅ **Responsive Design** - Works on mobile
✅ **Dark Mode** - Complete support

**Integration Status: ✅ COMPLETE**
