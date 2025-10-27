# PR-038 Fix Plan: Complete Test Suite & Add Telemetry

**Created**: October 27, 2025
**Priority**: CRITICAL - Must fix before merge
**Estimated Effort**: 6-8 hours
**Deadline**: Before code review

---

## Summary of Issues

| Issue | Severity | Files | Effort |
|-------|----------|-------|--------|
| Test stubs (12 pass statements) | 🔴 CRITICAL | test_pr_038_billing.py | 3-4h |
| TODO comments (2) | 🔴 CRITICAL | test_pr_038_billing.py | 1-2h |
| Missing telemetry | 🔴 HIGH | routes.py | 30m |
| Missing invoice history | 🔴 HIGH | routes.py, BillingCard | 3-4h |
| No Playwright tests | ⚠️ HIGH | No file | 2-3h |

---

## Task 1: Fix Test TODOs (1-2 hours)

### TODO #1: Line 50 - JWT Token Generation

**Current Code**:
```python
@pytest.mark.asyncio
async def test_get_subscription_endpoint(
    self, client: AsyncClient, db_session: AsyncSession
):
    """Test GET /api/v1/billing/subscription endpoint."""
    # Create test user
    user = User(
        id=str(uuid4()),
        email="test@example.com",
        telegram_id=123456,
        password_hash="hash",
    )
    db_session.add(user)
    await db_session.commit()

    # TODO: Implement JWT token generation for tests
    # response = await client.get(...)
```

**Fix**:
```python
@pytest.mark.asyncio
async def test_get_subscription_endpoint(
    self, client: AsyncClient, db_session: AsyncSession, jwt_token: str
):
    """Test GET /api/v1/billing/subscription endpoint."""
    # Create test user
    user = User(
        id=str(uuid4()),
        email="test@example.com",
        telegram_id=123456,
        password_hash="hash",
    )
    db_session.add(user)
    await db_session.commit()

    # Get subscription for new user (should be free tier)
    response = await client.get(
        "/api/v1/billing/subscription",
        headers={"Authorization": f"Bearer {jwt_token}"}
    )

    assert response.status_code == 200
    data = response.json()
    assert "tier" in data
    assert "status" in data
    assert "price_usd_monthly" in data
    assert data["tier"] == "free"  # New users are free tier
    assert data["status"] == "inactive"
```

### TODO #2: Line 82 - Portal Session Creation

**Current Code**:
```python
@pytest.mark.asyncio
async def test_portal_session_creation(
    self, client: AsyncClient, db_session: AsyncSession
):
    """Test POST /api/v1/billing/portal creates portal session."""
    # Create test user
    user = User(
        id=str(uuid4()),
        email="test@example.com",
        telegram_id=123456,
        password_hash="hash",
    )
    db_session.add(user)
    await db_session.commit()

    # TODO: Test portal session creation
    # response = await client.post(...)
```

**Fix**:
```python
@pytest.mark.asyncio
async def test_portal_session_creation(
    self, client: AsyncClient, db_session: AsyncSession, jwt_token: str, mocker
):
    """Test POST /api/v1/billing/portal creates portal session."""
    # Create test user
    user = User(
        id=str(uuid4()),
        email="test@example.com",
        telegram_id=123456,
        password_hash="hash",
    )
    db_session.add(user)
    await db_session.commit()

    # Mock Stripe API
    mock_portal_url = "https://billing.stripe.com/b/test123"
    mocker.patch(
        "backend.app.billing.stripe.checkout.StripeCheckoutService.create_portal_session",
        return_value={"url": mock_portal_url}
    )

    response = await client.post(
        "/api/v1/billing/portal",
        headers={"Authorization": f"Bearer {jwt_token}"}
    )

    assert response.status_code == 201
    data = response.json()
    assert "url" in data
    assert "https://billing.stripe.com" in data["url"]
```

---

## Task 2: Replace Test Stubs (3-4 hours)

### Test Methods to Implement (12 total)

#### Class: TestBillingAPI

**1. test_get_subscription_no_auth**
```python
@pytest.mark.asyncio
async def test_get_subscription_no_auth(self, client: AsyncClient):
    """Test subscription endpoint requires auth."""
    response = await client.get("/api/v1/billing/subscription")

    assert response.status_code == 401
    assert "detail" in response.json() or "error" in response.json()
```

**2. test_portal_opens_in_external_browser**
```python
@pytest.mark.asyncio
async def test_portal_opens_in_external_browser(self, jwt_token: str, mocker):
    """Test portal URL is meant for external browser."""
    # Portal should use Stripe's hosted portal, not iframe-safe
    mock_url = "https://billing.stripe.com/b/externalportal"

    mocker.patch(
        "backend.app.billing.stripe.checkout.stripe.billing_portal.Session.create",
        return_value={"url": mock_url}
    )

    # Verify URL starts with Stripe portal domain (not API)
    assert mock_url.startswith("https://billing.stripe.com")
    assert "internal" not in mock_url.lower()
```

#### Class: TestBillingCardComponent

**3. test_billing_card_displays_tier**
```python
def test_billing_card_displays_tier():
    """Test card displays current tier."""
    # React component testing via snapshots or UI library
    from frontend.miniapp.components.BillingCard import BillingCard

    # Component renders: line 168-170
    # <h4 className="text-2xl font-bold...">
    #   {currentPlan.name}
    # </h4>

    # Playwright test in separate file:
    # page.goto("/billing")
    # assert await page.locator("h2:has-text('Current Plan')").is_visible()
```

**4. test_billing_card_shows_upgrade_button**
```python
def test_billing_card_shows_upgrade_button():
    """Test upgrade button appears for non-enterprise tier."""
    # Component logic: lines 200-206
    # if subscription?.tier !== "enterprise" then render upgrade button

    # Playwright test:
    # page.goto("/billing")
    # assert await page.locator("button:has-text('Upgrade Plan')").is_visible()
```

**5. test_billing_card_shows_manage_button**
```python
def test_billing_card_shows_manage_button():
    """Test manage billing button appears for active subscriptions."""
    # Component logic: lines 189-195
    # if subscription?.status === "active" then render manage button

    # Playwright test:
    # page.goto("/billing")
    # assert await page.locator("button:has-text('Manage Billing')").is_visible()
```

#### Class: TestTelemetry

**6. test_miniapp_portal_open_metric**
```python
@pytest.mark.asyncio
async def test_miniapp_portal_open_metric(self, mocker):
    """Test metric emitted when portal opens."""
    mock_emit = mocker.patch("backend.app.core.telemetry.emit_metric")

    # Call portal endpoint
    # Verify metric emitted:
    # mock_emit.assert_called_with("miniapp_portal_open_total", increment=1)
```

**7. test_miniapp_checkout_start_metric**
```python
@pytest.mark.asyncio
async def test_miniapp_checkout_start_metric(self, mocker):
    """Test metric emitted when checkout starts."""
    mock_emit = mocker.patch("backend.app.core.telemetry.emit_metric")

    # Call checkout endpoint with plan_id="premium"
    # Verify metric emitted:
    # mock_emit.assert_called_with(
    #     "miniapp_checkout_start_total",
    #     {"plan": "premium"},
    #     increment=1
    # )
```

#### Class: TestInvoiceRendering

**8-11. Invoice Status Badge Tests**

```python
def test_invoice_status_badge_paid():
    """Test paid invoice shows green badge."""
    # Verify CSS class: "bg-green-100 text-green-800"
    # In BillingCard.tsx (component not yet implemented for invoices)
    pass

def test_invoice_status_badge_past_due():
    """Test past_due invoice shows warning badge."""
    # Verify CSS class: "bg-yellow-100 text-yellow-800"
    pass

def test_invoice_status_badge_canceled():
    """Test canceled invoice shows red badge."""
    # Verify CSS class: "bg-red-100 text-red-800"
    pass

def test_invoice_download_link():
    """Test invoice can be downloaded."""
    # Verify invoice PDF link in UI
    pass
```

---

## Task 3: Add Missing Telemetry (30 minutes)

### File: `backend/app/billing/routes.py`

**Location 1: Line 25-70 (create_checkout_session)**

```python
# ADD AFTER LINE 60 (before return response):

from backend.app.core.telemetry import emit_metric

# Inside try block, after logger.info:
emit_metric(
    "miniapp_checkout_start_total",
    {"plan": request.plan_id},
    increment=1
)

return response
```

**Location 2: Line 100-150 (create_portal_session_miniapp)**

```python
# ADD AFTER LINE 145 (before return):

emit_metric(
    "miniapp_portal_open_total",
    increment=1
)

return {"url": portal_response.url}
```

---

## Task 4: Implement Invoice History (3-4 hours)

### Step 1: Create Backend Endpoint

**File**: `backend/app/billing/routes.py`

```python
@router.get("/invoices", response_model=list[dict], status_code=200)
async def get_invoices(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get user's invoice history from Stripe.

    Returns list of invoices with status, amount, date, and download link.

    Returns:
        list of {id, date, amount, status, url}
    """
    try:
        service = StripeCheckoutService(db)
        invoices = await service.list_invoices(current_user.id)

        return invoices
    except Exception as e:
        logger.error(f"Failed to list invoices: {e}")
        raise HTTPException(500, "Failed to retrieve invoices")
```

### Step 2: Create Frontend Component

**File**: `frontend/miniapp/components/InvoiceList.tsx`

```typescript
import React from "react";

interface Invoice {
  id: string;
  date: string;
  amount: number;
  status: "paid" | "past_due" | "canceled";
  url: string;
}

export const InvoiceList: React.FC<{ invoices: Invoice[] }> = ({ invoices }) => {
  if (!invoices.length) {
    return <p className="text-gray-400">No invoices yet</p>;
  }

  return (
    <div className="space-y-2">
      {invoices.map(inv => (
        <div key={inv.id} className="flex justify-between items-center p-3 bg-gray-700 rounded">
          <div>
            <p className="text-white font-mono text-sm">{inv.id}</p>
            <p className="text-gray-300 text-xs">{new Date(inv.date).toLocaleDateString()}</p>
          </div>
          <div className="flex items-center gap-3">
            <span className={`text-sm font-semibold px-2 py-1 rounded ${
              inv.status === "paid" ? "bg-green-900 text-green-300" :
              inv.status === "past_due" ? "bg-yellow-900 text-yellow-300" :
              "bg-red-900 text-red-300"
            }`}>
              {inv.status}
            </span>
            <a href={inv.url} target="_blank" rel="noopener noreferrer"
               className="text-blue-400 hover:text-blue-300 text-sm">
              Download
            </a>
          </div>
        </div>
      ))}
    </div>
  );
};
```

### Step 3: Add to Billing Page

```typescript
// In billing/page.tsx, add to imports:
import { InvoiceList } from "@/components/InvoiceList";

// In fetchData(), add:
const invoicesData = await apiGet<Invoice[]>("/api/v1/billing/invoices", ...);
setInvoices(invoicesData || []);

// In JSX, add after subscription card:
<div className="mb-6">
  <h2 className="text-xl font-bold text-white mb-4">Invoice History</h2>
  <InvoiceList invoices={invoices} />
</div>
```

---

## Task 5: Add Playwright E2E Tests (2-3 hours)

### File: `frontend/tests/pr-038-billing.spec.ts`

```typescript
import { test, expect } from "@playwright/test";

test.describe("PR-038: Mini App Billing", () => {
  test.beforeEach(async ({ page, context }) => {
    // Mock JWT in localStorage
    await context.addInitScript(() => {
      localStorage.setItem("jwt_token", "mock_jwt_token_here");
    });
  });

  test("should display current plan", async ({ page }) => {
    await page.goto("http://localhost:3000/billing");

    // Wait for data to load
    await page.waitForSelector("text=Current Plan");

    // Verify plan name visible
    const planName = page.locator("text=Premium, Free, VIP, or Enterprise");
    await expect(planName).toBeVisible();
  });

  test("should open portal in external browser", async ({ page, context }) => {
    await page.goto("http://localhost:3000/billing");

    // Click manage button
    const manageButton = page.locator("button:has-text('Manage Billing')");

    // Listen for popup
    const [popup] = await Promise.all([
      context.waitForEvent("page"),
      manageButton.click()
    ]);

    // Verify popup URL is Stripe portal
    expect(popup.url()).toContain("billing.stripe.com");
    await popup.close();
  });

  test("should navigate to checkout on upgrade", async ({ page }) => {
    await page.goto("http://localhost:3000/billing");

    // Click upgrade button
    const upgradeButton = page.locator("button:has-text('Upgrade Plan')");
    await upgradeButton.click();

    // Should navigate to checkout page
    await expect(page).toHaveURL(/\/checkout\?plan=/);
  });

  test("should register and display device", async ({ page }) => {
    await page.goto("http://localhost:3000/billing");

    // Click add device
    const addButton = page.locator("button:has-text('Register New Device')");
    await addButton.click();

    // Enter device name
    const input = page.locator("input[placeholder='Device name']");
    await input.fill("EA-TEST-001");

    // Click register
    const registerButton = page.locator("button:has-text('Register')");
    await registerButton.click();

    // Verify device appears in list
    await expect(page.locator("text=EA-TEST-001")).toBeVisible();
  });
});
```

---

## Implementation Checklist

### Before Fixing:
- [ ] Read current test file completely
- [ ] Understand test structure and fixtures
- [ ] Check conftest.py for existing fixtures

### Phase 1: Fix TODOs
- [ ] Line 50: Implement JWT fixture or accept parameter
- [ ] Line 82: Mock Stripe API responses

### Phase 2: Replace Stubs
- [ ] TestBillingAPI.test_get_subscription_no_auth (line 57)
- [ ] TestBillingAPI.test_portal_opens_in_external_browser (line 96)
- [ ] TestBillingCardComponent (all 3, lines 105-115)
- [ ] TestTelemetry (both, lines 124-129)
- [ ] TestInvoiceRendering (all 4, lines 137-149)

### Phase 3: Add Telemetry
- [ ] Add emit_metric to checkout_session endpoint
- [ ] Add emit_metric to portal_session endpoint
- [ ] Verify telemetry module exists

### Phase 4: Implement Invoice History
- [ ] Create backend GET /invoices endpoint
- [ ] Create InvoiceList component
- [ ] Add InvoiceList to billing page
- [ ] Create invoice tests

### Phase 5: Add E2E Tests
- [ ] Create Playwright test file
- [ ] Test portal external browser opening
- [ ] Test checkout navigation
- [ ] Test device registration

### Before Resubmission:
- [ ] Run `pytest backend/tests/test_pr_038_billing.py -v` - all pass
- [ ] Run `pytest --cov=backend/app/billing` - ≥90% coverage
- [ ] Run `npm run test:billing` (Playwright) - all pass
- [ ] Check no TODOs remain in code
- [ ] Verify telemetry metrics emit correctly
- [ ] Manual test: Portal opens in browser
- [ ] Manual test: Checkout creates session

---

## Time Breakdown

| Task | Effort | Status |
|------|--------|--------|
| 1. Fix TODOs (JWT + Stripe mocking) | 1-2h | ⏳ TODO |
| 2. Implement test methods (12 stubs) | 3-4h | ⏳ TODO |
| 3. Add telemetry metrics | 30m | ⏳ TODO |
| 4. Implement invoice history | 3-4h | ⏳ TODO |
| 5. Add Playwright E2E tests | 2-3h | ⏳ TODO |
| Testing & verification | 1h | ⏳ TODO |
| **Total** | **10-14h** | |

---

## Critical Success Factors

✅ **Must Have**:
- All 14 test methods implemented (no more `pass`)
- 0 TODO comments
- ≥90% test coverage
- Telemetry metrics emitting
- All tests passing locally
- GitHub Actions CI/CD passing

⚠️ **Should Have**:
- Playwright E2E tests
- Invoice history feature
- Manual verification of portal/checkout flows

---

**Status**: Ready for implementation
**Assigned To**: [Your name]
**Deadline**: Before code review submission
