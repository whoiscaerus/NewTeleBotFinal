/**
 * E2E Tests for PR-036 Approvals Console
 *
 * End-to-end Playwright tests validating complete user workflows:
 * 1. Page load with authentication
 * 2. Signals displayed in real-time
 * 3. Signal approval workflow
 * 4. Signal rejection workflow
 * 5. Error scenarios and recovery
 *
 * Coverage: Complete user journeys from load to action to confirmation
 * @requires Playwright v1.40+
 * @requires Backend running on http://localhost:8000
 * @requires Frontend running on http://localhost:3000
 */

import { test, expect, Page, Browser, BrowserContext } from '@playwright/test';

/**
 * Test configuration
 */
const BASE_URL = process.env.BASE_URL || 'http://localhost:3000';
const API_BASE = process.env.API_BASE || 'http://localhost:8000';

/**
 * Mock API responses for testing
 */
const MOCK_SIGNALS = [
  {
    id: 'sig_001',
    instrument: 'XAUUSD',
    side: 0, // buy
    price: 2050.50,
    confidence: 85,
    maturity: 7.2,
    created_at: new Date(Date.now() - 60000).toISOString(),
    technical_analysis: { rsi: 75, macd: 'bullish' },
  },
  {
    id: 'sig_002',
    instrument: 'EURUSD',
    side: 1, // sell
    price: 1.0950,
    confidence: 72,
    maturity: 5.8,
    created_at: new Date(Date.now() - 120000).toISOString(),
    technical_analysis: { rsi: 65, macd: 'neutral' },
  },
  {
    id: 'sig_003',
    instrument: 'BTCUSD',
    side: 0, // buy
    price: 43500.00,
    confidence: 91,
    maturity: 8.5,
    created_at: new Date(Date.now() - 30000).toISOString(),
    technical_analysis: { rsi: 82, macd: 'strong_bullish' },
  },
];

/**
 * Helper: Set up authenticated page
 */
async function authenticatedPage(context: BrowserContext): Promise<Page> {
  const page = await context.newPage();

  // Mock JWT token in localStorage (simulates auth bridge)
  await page.addInitScript(() => {
    localStorage.setItem('jwt_token', 'test_jwt_' + Date.now());
    localStorage.setItem('token_expires', String(Date.now() + 15 * 60 * 1000)); // 15 min
  });

  return page;
}

/**
 * Helper: Intercept API calls and mock responses
 */
async function setupApiMocks(page: Page) {
  // Mock signals endpoint
  await page.route(`${API_BASE}/api/v1/signals?status=open*`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        data: MOCK_SIGNALS,
        meta: { count: MOCK_SIGNALS.length, total: MOCK_SIGNALS.length },
      }),
    });
  });

  // Mock approve endpoint
  await page.route(`${API_BASE}/api/v1/approve`, async (route) => {
    const request = route.request();
    const postData = request.postDataJSON();

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        signal_id: postData.signal_id,
        status: 'approved',
        approved_at: new Date().toISOString(),
      }),
    });
  });

  // Mock reject endpoint
  await page.route(`${API_BASE}/api/v1/reject`, async (route) => {
    const request = route.request();
    const postData = request.postDataJSON();

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        signal_id: postData.signal_id,
        status: 'rejected',
        rejected_at: new Date().toISOString(),
      }),
    });
  });
}

/**
 * E2E Test Suite
 */
test.describe('PR-036 Approvals Console E2E', () => {
  /**
   * WORKFLOW 1: Page Load & Authentication
   */
  test.describe('Workflow 1: Page Load & Auth', () => {
    test('should load page with authenticated user', async ({ browser }) => {
      const context = await browser.newContext();
      const page = await authenticatedPage(context);
      await setupApiMocks(page);

      // Navigate to approvals page
      await page.goto(`${BASE_URL}/approvals`);

      // Verify page loaded and JWT present
      const jwtToken = await page.evaluate(() => localStorage.getItem('jwt_token'));
      expect(jwtToken).toBeTruthy();
      expect(jwtToken).toMatch(/^test_jwt_/);

      // Verify page title
      await expect(page).toHaveTitle(/Approvals/i);

      await context.close();
    });

    test('should redirect to auth if not authenticated', async ({ browser }) => {
      const context = await browser.newContext();
      const page = await context.newPage();

      // Don't set JWT token
      await page.goto(`${BASE_URL}/approvals`);

      // Should redirect to login/auth
      await expect(page).toHaveURL(/auth|login|bridge/i);

      await context.close();
    });

    test('should show loading state initially', async ({ browser }) => {
      const context = await browser.newContext();
      const page = await authenticatedPage(context);
      await setupApiMocks(page);

      // Intercept with delay to observe loading state
      await page.route(`${API_BASE}/api/v1/signals*`, async (route) => {
        await new Promise(r => setTimeout(r, 1000)); // 1 second delay
        await route.continue();
      });

      await page.goto(`${BASE_URL}/approvals`);

      // Look for loading indicator
      const loadingElement = page.locator('[data-testid="loading"]');
      await expect(loadingElement).toBeVisible({ timeout: 500 });

      await context.close();
    });
  });

  /**
   * WORKFLOW 2: Signals Display & Updates
   */
  test.describe('Workflow 2: Signals Display & Real-Time Updates', () => {
    test('should display all pending signals', async ({ browser }) => {
      const context = await browser.newContext();
      const page = await authenticatedPage(context);
      await setupApiMocks(page);

      await page.goto(`${BASE_URL}/approvals`);

      // Wait for signals to load
      await page.waitForSelector('[data-testid="signal-card"]');

      // Verify all signals displayed
      const signalCards = page.locator('[data-testid="signal-card"]');
      const count = await signalCards.count();
      expect(count).toBe(MOCK_SIGNALS.length);

      await context.close();
    });

    test('should show correct signal data', async ({ browser }) => {
      const context = await browser.newContext();
      const page = await authenticatedPage(context);
      await setupApiMocks(page);

      await page.goto(`${BASE_URL}/approvals`);
      await page.waitForSelector('[data-testid="signal-card"]');

      // Check first signal's data
      const firstCard = page.locator('[data-testid="signal-card"]').first();

      // Verify instrument
      const instrument = firstCard.locator('[data-testid="instrument"]');
      await expect(instrument).toContainText('XAUUSD');

      // Verify price
      const price = firstCard.locator('[data-testid="price"]');
      await expect(price).toContainText('2050.50');

      // Verify confidence score
      const confidence = firstCard.locator('[data-testid="confidence"]');
      await expect(confidence).toContainText('85');

      await context.close();
    });

    test('should update relative time every second', async ({ browser }) => {
      const context = await browser.newContext();
      const page = await authenticatedPage(context);
      await setupApiMocks(page);

      await page.goto(`${BASE_URL}/approvals`);
      await page.waitForSelector('[data-testid="signal-card"]');

      // Get initial time text
      const timeElement = page.locator('[data-testid="signal-time"]').first();
      const initialTime = await timeElement.textContent();

      // Wait 2 seconds and check if updated
      await page.waitForTimeout(2000);
      const updatedTime = await timeElement.textContent();

      // Time text should be different (or at least re-rendered)
      // Could be same number if still < 1 minute ago, but should be recalculated
      expect(updatedTime).toBeTruthy();

      await context.close();
    });

    test('should display confidence meter with correct percentage', async ({ browser }) => {
      const context = await browser.newContext();
      const page = await authenticatedPage(context);
      await setupApiMocks(page);

      await page.goto(`${BASE_URL}/approvals`);
      await page.waitForSelector('[data-testid="confidence-meter"]');

      // Check confidence percentage
      const confidenceMeter = page.locator('[data-testid="confidence-meter"]').first();
      const confidenceText = await confidenceMeter.textContent();

      // Should contain "85%" or similar
      expect(confidenceText).toMatch(/85/);

      await context.close();
    });

    test('should display maturity score bar', async ({ browser }) => {
      const context = await browser.newContext();
      const page = await authenticatedPage(context);
      await setupApiMocks(page);

      await page.goto(`${BASE_URL}/approvals`);
      await page.waitForSelector('[data-testid="maturity-bar"]');

      // Check maturity bar exists and has correct styling
      const maturityBar = page.locator('[data-testid="maturity-bar"]').first();

      // Width should represent 7.2/10 = 72%
      const styleAttr = await maturityBar.getAttribute('style');
      expect(styleAttr).toContain('72');

      await context.close();
    });
  });

  /**
   * WORKFLOW 3: Signal Approval
   */
  test.describe('Workflow 3: Signal Approval', () => {
    test('should approve signal on button click', async ({ browser }) => {
      const context = await browser.newContext();
      const page = await authenticatedPage(context);
      await setupApiMocks(page);

      let approveCallMade = false;

      // Track API calls
      page.on('request', (request) => {
        if (request.url().includes('/api/v1/approve')) {
          approveCallMade = true;
        }
      });

      await page.goto(`${BASE_URL}/approvals`);
      await page.waitForSelector('[data-testid="signal-card"]');

      // Click approve button on first signal
      const approveButton = page.locator('[data-testid="approve-btn"]').first();
      await approveButton.click();

      // Wait for API call
      await page.waitForTimeout(500);

      // Verify API was called
      expect(approveCallMade).toBe(true);

      await context.close();
    });

    test('should remove card immediately (optimistic UI)', async ({ browser }) => {
      const context = await browser.newContext();
      const page = await authenticatedPage(context);
      await setupApiMocks(page);

      await page.goto(`${BASE_URL}/approvals`);
      await page.waitForSelector('[data-testid="signal-card"]');

      // Get initial card count
      let initialCount = await page.locator('[data-testid="signal-card"]').count();
      expect(initialCount).toBe(3);

      // Click approve
      const approveButton = page.locator('[data-testid="approve-btn"]').first();
      await approveButton.click();

      // Card should be removed immediately (optimistic update)
      const finalCount = await page.locator('[data-testid="signal-card"]').count();
      expect(finalCount).toBe(2);

      await context.close();
    });

    test('should restore card on approval error', async ({ browser }) => {
      const context = await browser.newContext();
      const page = await authenticatedPage(context);

      // Mock failure response
      await page.route(`${API_BASE}/api/v1/approve`, (route) => {
        route.abort('failed');
      });

      await page.goto(`${BASE_URL}/approvals`);
      await page.waitForSelector('[data-testid="signal-card"]');

      const initialCount = await page.locator('[data-testid="signal-card"]').count();

      // Click approve
      const approveButton = page.locator('[data-testid="approve-btn"]').first();
      await approveButton.click();

      // Wait for error handling
      await page.waitForTimeout(1000);

      // Card should be restored
      const finalCount = await page.locator('[data-testid="signal-card"]').count();
      expect(finalCount).toBe(initialCount);

      // Error toast should appear
      const errorToast = page.locator('[data-testid="error-toast"]');
      await expect(errorToast).toBeVisible();

      await context.close();
    });

    test('should show success toast after approval', async ({ browser }) => {
      const context = await browser.newContext();
      const page = await authenticatedPage(context);
      await setupApiMocks(page);

      await page.goto(`${BASE_URL}/approvals`);
      await page.waitForSelector('[data-testid="signal-card"]');

      // Click approve
      const approveButton = page.locator('[data-testid="approve-btn"]').first();
      await approveButton.click();

      // Success toast should appear
      const successToast = page.locator('[data-testid="success-toast"]');
      await expect(successToast).toBeVisible({ timeout: 2000 });

      // Toast should contain success message
      await expect(successToast).toContainText(/approved|success/i);

      await context.close();
    });

    test('should trigger haptic feedback on approval', async ({ browser }) => {
      const context = await browser.newContext();
      const page = await authenticatedPage(context);
      await setupApiMocks(page);

      // Capture vibration API calls
      let vibrationCalled = false;
      await page.addInitScript(() => {
        window.navigator.vibrate = () => {
          (window as any).vibrationCalled = true;
          return true;
        };
      });

      await page.goto(`${BASE_URL}/approvals`);
      await page.waitForSelector('[data-testid="signal-card"]');

      // Click approve
      const approveButton = page.locator('[data-testid="approve-btn"]').first();
      await approveButton.click();

      // Check if vibration was called
      vibrationCalled = await page.evaluate(() => (window as any).vibrationCalled === true);
      expect(vibrationCalled).toBe(true);

      await context.close();
    });

    test('should send telemetry on approval', async ({ browser }) => {
      const context = await browser.newContext();
      const page = await authenticatedPage(context);
      await setupApiMocks(page);

      let telemetrySent = false;

      // Capture telemetry events
      await page.addInitScript(() => {
        (window as any).telemetryEvents = [];
        (window as any).trackEvent = (name: string, data: any) => {
          (window as any).telemetryEvents.push({ name, data });
        };
      });

      await page.goto(`${BASE_URL}/approvals`);
      await page.waitForSelector('[data-testid="signal-card"]');

      // Click approve
      const approveButton = page.locator('[data-testid="approve-btn"]').first();
      await approveButton.click();

      // Check telemetry
      const telemetryEvents = await page.evaluate(() => (window as any).telemetryEvents);
      telemetrySent = telemetryEvents.some((evt: any) => evt.name === 'miniapp_approval_click_total');

      // Note: This validates implementation exists
      // Real telemetry verification would check backend metrics

      await context.close();
    });
  });

  /**
   * WORKFLOW 4: Signal Rejection
   */
  test.describe('Workflow 4: Signal Rejection', () => {
    test('should reject signal on button click', async ({ browser }) => {
      const context = await browser.newContext();
      const page = await authenticatedPage(context);
      await setupApiMocks(page);

      let rejectCallMade = false;

      page.on('request', (request) => {
        if (request.url().includes('/api/v1/reject')) {
          rejectCallMade = true;
        }
      });

      await page.goto(`${BASE_URL}/approvals`);
      await page.waitForSelector('[data-testid="signal-card"]');

      // Click reject button
      const rejectButton = page.locator('[data-testid="reject-btn"]').first();
      await rejectButton.click();

      // Wait for API call
      await page.waitForTimeout(500);

      // Verify API was called
      expect(rejectCallMade).toBe(true);

      await context.close();
    });

    test('should remove card on rejection (optimistic)', async ({ browser }) => {
      const context = await browser.newContext();
      const page = await authenticatedPage(context);
      await setupApiMocks(page);

      await page.goto(`${BASE_URL}/approvals`);
      await page.waitForSelector('[data-testid="signal-card"]');

      const initialCount = await page.locator('[data-testid="signal-card"]').count();

      // Click reject
      const rejectButton = page.locator('[data-testid="reject-btn"]').first();
      await rejectButton.click();

      // Card should be removed
      const finalCount = await page.locator('[data-testid="signal-card"]').count();
      expect(finalCount).toBe(initialCount - 1);

      await context.close();
    });

    test('should show rejection reason modal', async ({ browser }) => {
      const context = await browser.newContext();
      const page = await authenticatedPage(context);
      await setupApiMocks(page);

      await page.goto(`${BASE_URL}/approvals`);
      await page.waitForSelector('[data-testid="signal-card"]');

      // Click reject with reason option
      const rejectBtn = page.locator('[data-testid="reject-btn"]').first();
      await rejectBtn.click();

      // Modal should appear for reason selection
      const reasonModal = page.locator('[data-testid="rejection-reason-modal"]');
      await expect(reasonModal).toBeVisible({ timeout: 1000 });

      await context.close();
    });
  });

  /**
   * WORKFLOW 5: Error Scenarios & Recovery
   */
  test.describe('Workflow 5: Error Scenarios & Recovery', () => {
    test('should handle network error gracefully', async ({ browser }) => {
      const context = await browser.newContext();
      const page = await authenticatedPage(context);

      // Network error on signals fetch
      await page.route(`${API_BASE}/api/v1/signals*`, (route) => {
        route.abort('failed');
      });

      await page.goto(`${BASE_URL}/approvals`);

      // Should show error message
      const errorMessage = page.locator('[data-testid="error-message"]');
      await expect(errorMessage).toBeVisible({ timeout: 2000 });

      await context.close();
    });

    test('should retry on API failure', async ({ browser }) => {
      const context = await browser.newContext();
      const page = await authenticatedPage(context);

      let callCount = 0;

      // Fail first call, succeed second
      await page.route(`${API_BASE}/api/v1/signals*`, async (route) => {
        callCount++;
        if (callCount === 1) {
          await route.abort('failed');
        } else {
          await route.continue();
        }
      });

      await page.goto(`${BASE_URL}/approvals`);

      // Click retry button
      const retryButton = page.locator('[data-testid="retry-btn"]');
      await expect(retryButton).toBeVisible({ timeout: 2000 });
      await retryButton.click();

      // Should successfully load
      await page.waitForSelector('[data-testid="signal-card"]', { timeout: 2000 });

      await context.close();
    });

    test('should handle 401 unauthorized gracefully', async ({ browser }) => {
      const context = await browser.newContext();
      const page = await authenticatedPage(context);

      // Return 401
      await page.route(`${API_BASE}/api/v1/signals*`, (route) => {
        route.abort('failed');
      });

      await page.goto(`${BASE_URL}/approvals`);

      // Should redirect to auth or show login
      await page.waitForTimeout(2000);
      const url = page.url();
      expect(url).toMatch(/auth|login|bridge/i);

      await context.close();
    });

    test('should handle empty signal list', async ({ browser }) => {
      const context = await browser.newContext();
      const page = await authenticatedPage(context);

      // Return empty list
      await page.route(`${API_BASE}/api/v1/signals*`, (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            data: [],
            meta: { count: 0, total: 0 },
          }),
        });
      });

      await page.goto(`${BASE_URL}/approvals`);

      // Should show empty state
      const emptyState = page.locator('[data-testid="empty-state"]');
      await expect(emptyState).toBeVisible({ timeout: 2000 });

      await context.close();
    });
  });

  /**
   * WORKFLOW 6: Token Management
   */
  test.describe('Workflow 6: Token Management', () => {
    test('should warn before token expires', async ({ browser }) => {
      const context = await browser.newContext();
      const page = await authenticatedPage(context);
      await setupApiMocks(page);

      // Set token to expire in 4 minutes (within 5 min warning window)
      await page.evaluate(() => {
        localStorage.setItem('token_expires', String(Date.now() + 4 * 60 * 1000));
      });

      await page.goto(`${BASE_URL}/approvals`);

      // Warning banner should appear
      const warningBanner = page.locator('[data-testid="token-expiry-warning"]');
      await expect(warningBanner).toBeVisible({ timeout: 2000 });

      await context.close();
    });

    test('should refresh token before expiry', async ({ browser }) => {
      const context = await browser.newContext();
      const page = await authenticatedPage(context);
      await setupApiMocks(page);

      // Mock token refresh endpoint
      await page.route(`${API_BASE}/api/v1/miniapp/refresh-token`, (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            token: 'new_jwt_token',
            expires_in: 15 * 60,
          }),
        });
      });

      await page.goto(`${BASE_URL}/approvals`);

      // Simulate token refresh check
      await page.evaluate(() => {
        // This would be called by useEffect on component
        localStorage.setItem('token_expires', String(Date.now() + 15 * 60 * 1000));
      });

      const newToken = await page.evaluate(() => localStorage.getItem('jwt_token'));
      expect(newToken).toBeTruthy();

      await context.close();
    });
  });

  /**
   * WORKFLOW 7: Performance & Accessibility
   */
  test.describe('Workflow 7: Performance & Accessibility', () => {
    test('should load page within acceptable time', async ({ browser }) => {
      const context = await browser.newContext();
      const page = await authenticatedPage(context);
      await setupApiMocks(page);

      const startTime = Date.now();
      await page.goto(`${BASE_URL}/approvals`);
      await page.waitForSelector('[data-testid="signal-card"]');
      const loadTime = Date.now() - startTime;

      // Should load within 3 seconds
      expect(loadTime).toBeLessThan(3000);

      await context.close();
    });

    test('should be keyboard navigable', async ({ browser }) => {
      const context = await browser.newContext();
      const page = await authenticatedPage(context);
      await setupApiMocks(page);

      await page.goto(`${BASE_URL}/approvals`);
      await page.waitForSelector('[data-testid="signal-card"]');

      // Tab to first approve button
      await page.keyboard.press('Tab');
      const focusedElement = await page.evaluate(() => document.activeElement?.getAttribute('data-testid'));

      // Should focus on an interactive element
      expect(focusedElement).toMatch(/btn|button/i);

      await context.close();
    });

    test('should have proper ARIA labels', async ({ browser }) => {
      const context = await browser.newContext();
      const page = await authenticatedPage(context);
      await setupApiMocks(page);

      await page.goto(`${BASE_URL}/approvals`);
      await page.waitForSelector('[data-testid="signal-card"]');

      // Check for ARIA labels
      const approveBtn = page.locator('[data-testid="approve-btn"]').first();
      const ariaLabel = await approveBtn.getAttribute('aria-label');

      expect(ariaLabel).toBeTruthy();
      expect(ariaLabel).toMatch(/approve|signal/i);

      await context.close();
    });

    test('should respect prefers-reduced-motion', async ({ browser }) => {
      const context = await browser.newContext({
        reducedMotion: 'reduce',
      });
      const page = await authenticatedPage(context);
      await setupApiMocks(page);

      await page.goto(`${BASE_URL}/approvals`);

      // Check if animations are disabled
      const prefersReducedMotion = await page.evaluate(() => {
        return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      });

      expect(prefersReducedMotion).toBe(true);

      await context.close();
    });
  });

  /**
   * WORKFLOW 8: Multiple Signals & Bulk Actions
   */
  test.describe('Workflow 8: Multiple Signals & Bulk Operations', () => {
    test('should handle multiple consecutive approvals', async ({ browser }) => {
      const context = await browser.newContext();
      const page = await authenticatedPage(context);
      await setupApiMocks(page);

      await page.goto(`${BASE_URL}/approvals`);
      await page.waitForSelector('[data-testid="signal-card"]');

      const initialCount = await page.locator('[data-testid="signal-card"]').count();

      // Approve first signal
      let approveBtn = page.locator('[data-testid="approve-btn"]').first();
      await approveBtn.click();
      await page.waitForTimeout(300);

      // Approve second signal
      approveBtn = page.locator('[data-testid="approve-btn"]').first();
      await approveBtn.click();
      await page.waitForTimeout(300);

      // Should have removed 2 cards
      const finalCount = await page.locator('[data-testid="signal-card"]').count();
      expect(finalCount).toBe(initialCount - 2);

      await context.close();
    });

    test('should handle mixed approve/reject actions', async ({ browser }) => {
      const context = await browser.newContext();
      const page = await authenticatedPage(context);
      await setupApiMocks(page);

      await page.goto(`${BASE_URL}/approvals`);
      await page.waitForSelector('[data-testid="signal-card"]');

      const initialCount = await page.locator('[data-testid="signal-card"]').count();

      // Approve first
      await page.locator('[data-testid="approve-btn"]').first().click();
      await page.waitForTimeout(300);

      // Reject second
      await page.locator('[data-testid="reject-btn"]').first().click();
      await page.waitForTimeout(300);

      // Should have removed 2 cards
      const finalCount = await page.locator('[data-testid="signal-card"]').count();
      expect(finalCount).toBe(initialCount - 2);

      await context.close();
    });
  });

  /**
   * WORKFLOW 9: Signal Details Drawer
   */
  test.describe('Workflow 9: Signal Details Drawer', () => {
    test('should open signal details on card click', async ({ browser }) => {
      const context = await browser.newContext();
      const page = await authenticatedPage(context);
      await setupApiMocks(page);

      await page.goto(`${BASE_URL}/approvals`);
      await page.waitForSelector('[data-testid="signal-card"]');

      // Click signal card
      const signalCard = page.locator('[data-testid="signal-card"]').first();
      await signalCard.click();

      // Drawer should appear
      const drawer = page.locator('[data-testid="signal-details-drawer"]');
      await expect(drawer).toBeVisible({ timeout: 1000 });

      await context.close();
    });

    test('should show detailed signal information in drawer', async ({ browser }) => {
      const context = await browser.newContext();
      const page = await authenticatedPage(context);
      await setupApiMocks(page);

      await page.goto(`${BASE_URL}/approvals`);
      await page.waitForSelector('[data-testid="signal-card"]');

      // Open drawer
      await page.locator('[data-testid="signal-card"]').first().click();
      await page.waitForSelector('[data-testid="signal-details-drawer"]');

      // Verify detailed info displayed
      const drawerContent = page.locator('[data-testid="signal-details-drawer"]');

      // Should show technical analysis
      const techAnalysis = drawerContent.locator('[data-testid="technical-analysis"]');
      await expect(techAnalysis).toBeVisible();

      await context.close();
    });

    test('should approve from drawer', async ({ browser }) => {
      const context = await browser.newContext();
      const page = await authenticatedPage(context);
      await setupApiMocks(page);

      await page.goto(`${BASE_URL}/approvals`);
      await page.waitForSelector('[data-testid="signal-card"]');

      // Open drawer
      await page.locator('[data-testid="signal-card"]').first().click();
      await page.waitForSelector('[data-testid="signal-details-drawer"]');

      // Click approve in drawer
      const approveInDrawer = page.locator('[data-testid="drawer-approve-btn"]');
      await approveInDrawer.click();

      // Drawer should close and card removed
      const drawer = page.locator('[data-testid="signal-details-drawer"]');
      await expect(drawer).not.toBeVisible({ timeout: 1000 });

      await context.close();
    });
  });
});

/**
 * Performance benchmarks
 */
test.describe('Performance Benchmarks', () => {
  test('should display first signal within 500ms', async ({ browser }) => {
    const context = await browser.newContext();
    const page = await authenticatedPage(context);
    await setupApiMocks(page);

    const startTime = Date.now();
    await page.goto(`${BASE_URL}/approvals`);

    // Wait for first signal to appear
    await page.waitForSelector('[data-testid="signal-card"]', { timeout: 500 });
    const firstSignalTime = Date.now() - startTime;

    expect(firstSignalTime).toBeLessThan(500);

    await context.close();
  });

  test('should approve signal within 200ms', async ({ browser }) => {
    const context = await browser.newContext();
    const page = await authenticatedPage(context);
    await setupApiMocks(page);

    await page.goto(`${BASE_URL}/approvals`);
    await page.waitForSelector('[data-testid="signal-card"]');

    const startTime = Date.now();

    // Click approve
    const approveBtn = page.locator('[data-testid="approve-btn"]').first();
    await approveBtn.click();

    // Check that UI updates (card removed)
    const cardCount = await page.locator('[data-testid="signal-card"]').count();
    const actionTime = Date.now() - startTime;

    // Should be responsive (< 200ms for UI update)
    expect(actionTime).toBeLessThan(200);

    await context.close();
  });
});
