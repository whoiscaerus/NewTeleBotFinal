# PR-039 Integration Guide: Mini App Account & Devices

## Overview

**PR-039** implements **self-service device management** for MT5 EAs within the Mini App. It is correctly positioned as a **standalone feature** that does **NOT directly depend on PR-033** (payments), though both are wired into the Mini App system.

---

## Dependency Chain Analysis

### PR-039's Actual Dependencies

```
PR-039 (Devices) depends on:
├── PR-023a (Device Registry & HMAC Secrets) ✅ REQUIRED
│   └── Device model, registration, secret generation, revoke
├── PR-035 (Mini App Bootstrap) ✅ REQUIRED
│   └── Next.js app, JWT auth, API wrapper
├── PR-036 (Approval Console) ✅ ALREADY EXISTS
│   └── Main Mini App layout, navigation
└── PR-037 (Plan Gating) ⚠️ OPTIONAL
    └── If gating device features behind entitlements
```

### PR-033's Role (NOT a Dependency)

**PR-033 (Fiat Payments)** provides:
- ✅ Stripe checkout sessions
- ✅ Payment webhooks → entitlement activation
- ✅ Portal session creation
- ✅ Invoice storage

**PR-039 (Devices) does NOT need this because:**
- Device management is **free** (no payment required)
- Device operations (register, revoke) are **entitlement-agnostic**
- Device registration returns secret, no billing integration
- Copy-trading pricing (+30%) is in **PR-045**, not PR-039

---

## System Architecture Overview

```
Mini App (Frontend)
├── Page: /billing (PR-038) → Stripe portal, invoices → USES PR-033
├── Page: /devices (PR-039) → Device list, register, revoke → USES PR-023a
├── Page: /approvals (PR-036) → Signal approval
└── Page: /settings (future)

Backend APIs
├── /api/v1/billing/* → PR-033 (Stripe + entitlements)
├── /api/v1/devices/* → PR-023a (Device registry)
├── /api/v1/signals/* → PR-021/022 (Signal ingestion + approvals)
└── /api/v1/subscriptions/* → PR-028 (Entitlements)
```

---

## Integration Points: PR-039 with Existing PRs

### 1. With PR-023a (Device Registry) - **DIRECT DEPENDENCY**

**What PR-023a Provides:**
- Device registration endpoint
- Secret generation and hashing
- Device list endpoint
- Rename/revoke endpoints
- Device model in database

**How PR-039 Uses It:**
```typescript
// frontend/miniapp/components/AddDeviceModal.tsx
async function handleRegisterDevice(name: string) {
  // Calls backend POST /api/v1/devices/register
  const response = await fetch('/api/v1/devices/register', {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${jwt_token}` },
    body: JSON.stringify({ name })
  });

  // Returns: { device_id, device_secret } (secret shown ONCE)
  const { device_id, device_secret } = await response.json();
}
```

### 2. With PR-035 (Mini App Bootstrap) - **REQUIRED FOUNDATION**

**What PR-035 Provides:**
- Next.js App Router setup
- Telegram WebApp SDK integration
- JWT authentication bridge
- API fetch wrapper

**How PR-039 Uses It:**
```typescript
// frontend/miniapp/app/devices/page.tsx
'use client';

import { useAuth } from '@/lib/auth';  // From PR-035
import { getDevices, registerDevice } from '@/lib/api';  // From PR-035

export default function DevicesPage() {
  const { user, jwt } = useAuth();  // From PR-035's TelegramProvider

  const devices = await getDevices();  // Uses jwt in header automatically
  return <DeviceList devices={devices} />;
}
```

### 3. With PR-036 (Approval Console) - **NAVIGATION CONTEXT**

**What PR-036 Provides:**
- Main Mini App layout and navigation
- Signal approval flow
- Navigation menu/sidebar

**How PR-039 Integrates:**
```typescript
// Navigation in Mini App layout (PR-036)
const navItems = [
  { href: '/approvals', label: 'Approve Signals', icon: '✓' },
  { href: '/billing', label: 'Billing', icon: '💳' },      // PR-038
  { href: '/devices', label: 'Devices', icon: '📱' },      // PR-039 ← YOU ARE HERE
];
```

### 4. With PR-037 (Plan Gating) - **OPTIONAL ENHANCEMENT**

**Scenario 1: Free Users Can Register 1 Device**
```python
# backend/app/billing/gates.py
@require_entitlement("device_registration")  # Could gate this
async def register_device(user_id: str, name: str):
    # Implementation in PR-023a
```

**Scenario 2: Premium Users Can Register Multiple**
```python
# In PR-039 logic or PR-023a
MAX_DEVICES_FREE = 1
MAX_DEVICES_PREMIUM = 5

if subscription_tier == "premium":
    max_devices = MAX_DEVICES_PREMIUM
else:
    max_devices = MAX_DEVICES_FREE
```

### 5. With PR-033 (Payments) - **SEPARATE BUT ADJACENT**

Both pages exist in Mini App but are **independent**:

| Feature | PR-033 | PR-039 | Interaction |
|---------|--------|--------|-------------|
| Dependency | PR-028 (Entitlements) | PR-023a (Device Registry) | None |
| User flows | Billing/checkout | Device mgmt | Can use both in same session |
| Database | Stripe customer, invoices | Devices, secrets | Different tables |
| Authorization | JWT + Stripe customer ID | JWT only | Both use JWT from PR-035 |

**Example User Flow:**
```
1. User opens Mini App (PR-035 bootstrap)
2. Navigates to /billing → sees plan (PR-033)
3. Clicks "Manage Devices" → goes to /devices (PR-039)
4. Registers new device → gets secret once (PR-023a)
5. Copies secret to MT5 EA configuration
6. Returns to billing → reviews invoice (PR-033)
```

---

## Implementation Plan for PR-039

### Phase 1: Backend Foundation (Already exists PR-023a)

**Files to use/verify exist:**
```python
# backend/app/clients/models.py
class Device(Base):
    id: str
    client_id: str
    name: str
    secret_hash: str  # argon2id(device_secret)
    revoked: bool
    last_seen: datetime

# backend/app/clients/routes.py
@router.post("/api/v1/devices/register", status_code=201)
@router.get("/api/v1/devices/me")
@router.patch("/api/v1/devices/{id}")
@router.post("/api/v1/devices/{id}/revoke")
```

### Phase 2: Frontend Components (PR-039 - NEW)

**Files to create:**

1. **`frontend/miniapp/app/devices/page.tsx`** (Main page)
```typescript
'use client';

import { useEffect, useState } from 'react';
import { DeviceList } from '@/components/DeviceList';
import { AddDeviceModal } from '@/components/AddDeviceModal';
import { useAuth } from '@/lib/auth';

export default function DevicesPage() {
  const { jwt } = useAuth();
  const [devices, setDevices] = useState([]);
  const [showModal, setShowModal] = useState(false);

  useEffect(() => {
    loadDevices();
  }, []);

  async function loadDevices() {
    const response = await fetch('/api/v1/devices/me', {
      headers: { 'Authorization': `Bearer ${jwt}` }
    });
    setDevices(await response.json());
  }

  return (
    <div className="p-4 space-y-4">
      <h1 className="text-2xl font-bold">My Devices</h1>
      <DeviceList devices={devices} onDeviceRemoved={loadDevices} />
      <button onClick={() => setShowModal(true)} className="btn-primary">
        + Add Device
      </button>
      {showModal && (
        <AddDeviceModal
          onSuccess={() => {
            setShowModal(false);
            loadDevices();
          }}
          onClose={() => setShowModal(false)}
        />
      )}
    </div>
  );
}
```

2. **`frontend/miniapp/components/DeviceList.tsx`**
```typescript
'use client';

import { Device } from '@/types';

interface DeviceListProps {
  devices: Device[];
  onDeviceRemoved: () => void;
}

export function DeviceList({ devices, onDeviceRemoved }: DeviceListProps) {
  async function handleRevoke(deviceId: string) {
    const confirmed = confirm('Are you sure? This will stop your EA from accessing your signals.');
    if (!confirmed) return;

    const response = await fetch(`/api/v1/devices/${deviceId}/revoke`, {
      method: 'POST'
    });

    if (response.ok) {
      toast.success('Device revoked');
      onDeviceRemoved();
    } else {
      toast.error('Failed to revoke device');
    }
  }

  if (devices.length === 0) {
    return <p className="text-gray-500">No devices registered yet.</p>;
  }

  return (
    <div className="space-y-3">
      {devices.map(device => (
        <div key={device.id} className="border rounded p-3 flex justify-between items-center">
          <div>
            <h3 className="font-semibold">{device.name}</h3>
            <p className="text-xs text-gray-500">
              Last seen: {device.last_seen ? formatDate(device.last_seen) : 'Never'}
            </p>
          </div>
          <button
            onClick={() => handleRevoke(device.id)}
            className="btn-danger-sm"
          >
            Revoke
          </button>
        </div>
      ))}
    </div>
  );
}
```

3. **`frontend/miniapp/components/AddDeviceModal.tsx`**
```typescript
'use client';

import { useState } from 'react';
import { toast } from '@/lib/toast';

interface AddDeviceModalProps {
  onSuccess: () => void;
  onClose: () => void;
}

export function AddDeviceModal({ onSuccess, onClose }: AddDeviceModalProps) {
  const [name, setName] = useState('');
  const [secret, setSecret] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleRegister() {
    if (!name.trim()) {
      toast.error('Please enter a device name');
      return;
    }

    setLoading(true);
    try {
      const response = await fetch('/api/v1/devices/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name })
      });

      if (response.status === 409) {
        toast.error('Device name already exists');
        return;
      }

      if (!response.ok) throw new Error('Registration failed');

      const { device_id, device_secret } = await response.json();
      setSecret(device_secret);  // Show ONCE

    } catch (error) {
      toast.error('Failed to register device');
    } finally {
      setLoading(false);
    }
  }

  // Show secret display screen
  if (secret) {
    return (
      <Modal onClose={onClose}>
        <h2 className="text-xl font-bold mb-4">Device Secret</h2>
        <p className="text-sm text-yellow-600 mb-4">
          ⚠️ Save this secret now. You won't see it again!
        </p>

        <div className="bg-gray-100 p-4 rounded font-mono text-sm mb-4 break-all">
          {secret}
        </div>

        <button
          onClick={() => {
            navigator.clipboard.writeText(secret);
            toast.success('Copied to clipboard!');
          }}
          className="btn-primary w-full mb-2"
        >
          📋 Copy to Clipboard
        </button>

        <button
          onClick={() => {
            onSuccess();
            onClose();
          }}
          className="btn-secondary w-full"
        >
          Done
        </button>
      </Modal>
    );
  }

  // Show registration form
  return (
    <Modal onClose={onClose}>
      <h2 className="text-xl font-bold mb-4">Register New Device</h2>

      <input
        type="text"
        placeholder="e.g., MT5 EA - Live Account"
        value={name}
        onChange={(e) => setName(e.target.value)}
        className="input-field w-full mb-4"
      />

      <button
        onClick={handleRegister}
        disabled={loading}
        className="btn-primary w-full"
      >
        {loading ? 'Registering...' : 'Register Device'}
      </button>
    </Modal>
  );
}
```

### Phase 3: Telemetry Integration

**Record in backend when device operations happen:**
```python
# backend/app/clients/routes.py
from backend.app.telemetry import record_metric

@router.post("/api/v1/devices/register")
async def register_device(user_id: str, req: DeviceRegisterIn):
    device = await create_device(user_id, req.name)

    # Telemetry
    record_metric('miniapp_device_register_total', 1, {'success': 'true'})
    return device

@router.post("/api/v1/devices/{device_id}/revoke")
async def revoke_device(device_id: str):
    await revoke_device(device_id)

    # Telemetry
    record_metric('miniapp_device_revoke_total', 1, {'success': 'true'})
```

---

## How PR-039 Does NOT Integrate with PR-033

| Concern | Answer |
|---------|--------|
| Do I need PR-033 to build PR-039? | **NO** - Device mgmt is free, standalone |
| Will PR-039 read Stripe data? | **NO** - Only uses JWT auth and Device Registry |
| Do I need to map entitlements to devices? | **OPTIONAL** - Can gate device count behind premium (PR-037), but not required |
| Can device secret be used for Stripe auth? | **NO** - Device secret (HMAC) is for MT5 EA auth only. Stripe uses separate webhook secret |
| Does PR-039 create invoices? | **NO** - PR-033 creates invoices |
| Do devices appear on billing page? | **NO** - Devices are on `/devices` page (PR-039), billing is on `/billing` page (PR-038) |

---

## Execution Order

**To build PR-039, you MUST complete first:**

1. ✅ **PR-023a** - Device Registry (exists, provides backend endpoints)
2. ✅ **PR-035** - Mini App Bootstrap (exists, provides JWT auth + API wrapper)
3. ✅ **PR-036** - Approval Console (exists, provides layout + navigation)
4. ❓ **PR-037** - Plan Gating (optional, for device count limits)
5. **Then PR-039** ← You are here

**PR-033 (Payments) should be completed BEFORE or AFTER, doesn't matter for PR-039.**

---

## Security Checklist for PR-039

- [ ] Device secret shown **exactly once** (no re-render)
- [ ] Copy-to-clipboard only (no read API for secret)
- [ ] Secret stored as **argon2id hash** in DB (PR-023a responsibility)
- [ ] Revoke endpoint clears secret (device can't auth anymore)
- [ ] JWT required on all device endpoints
- [ ] Device list only shows owner's devices (no data leak)
- [ ] Duplicate name → 409 Conflict with clear error message

---

## Testing Strategy for PR-039

**Unit Tests:**
```python
# backend/tests/test_devices.py
def test_register_device_returns_secret_once():
    """Verify secret is returned on POST /register"""

def test_list_devices_excludes_secret():
    """Verify list endpoint never returns secret"""

def test_duplicate_name_returns_409():
    """Duplicate device names rejected"""

def test_revoke_device_prevents_auth():
    """Revoked device can't auth with old secret"""
```

**Frontend Tests:**
```typescript
// frontend/tests/devices.spec.ts
test('Register device modal shows secret once', async ({ page }) => {
  // Fill form, submit
  await page.fill('[name=device-name]', 'My EA');
  await page.click('[data-testid=register-btn]');

  // Verify secret displayed
  const secret = page.locator('[data-testid=device-secret]');
  await expect(secret).toBeVisible();

  // Verify can copy
  await page.click('[data-testid=copy-secret-btn]');
  await expect(page.locator('text=Copied')).toBeVisible();
});

test('Duplicate device name shows error', async ({ page }) => {
  // Try to create device with same name as existing
  await page.fill('[name=device-name]', 'Existing Device');
  await page.click('[data-testid=register-btn]');

  // Should show error
  await expect(page.locator('text=Device name already exists')).toBeVisible();
});
```

---

## Summary: Is PR-039 Correctly Positioned?

✅ **YES** - PR-039 is correctly positioned as an **independent Mini App feature** that:

- **Does NOT depend on PR-033** (Payments)
- **Depends on PR-023a** (Device Registry) for backend API
- **Depends on PR-035** (Mini App bootstrap) for frontend foundation
- **Lives alongside PR-038** (Billing) in the Mini App
- **Uses same JWT auth pattern** as all Mini App pages
- **Is completely separate** from payment/billing logic

The confusion may have come from both being in the Mini App, but they are in **different sections** with **different backend APIs** and **different purposes**.

---

**Ready to implement PR-039? Start with Phase 1 verification that PR-023a endpoints exist, then build the three TypeScript components in Phase 2.**
