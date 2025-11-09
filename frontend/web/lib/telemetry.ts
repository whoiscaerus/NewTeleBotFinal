/**
 * Telemetry Client Library
 *
 * Tracks page views and Core Web Vitals (CWV) for performance monitoring.
 * Sends data to backend telemetry endpoints.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000';

interface PageViewData {
  route: string;
  referrer?: string;
  timestamp: number;
}

interface CWVData {
  lcp?: number;  // Largest Contentful Paint (seconds)
  fid?: number;  // First Input Delay (milliseconds)
  cls?: number;  // Cumulative Layout Shift (score)
  ttfb?: number; // Time to First Byte (milliseconds)
  tti?: number;  // Time to Interactive (milliseconds) - PR-086
}

/**
 * Track a page view
 */
export async function trackPageView(route: string): Promise<void> {
  try {
    const data: PageViewData = {
      route,
      referrer: document.referrer || undefined,
      timestamp: Date.now(),
    };

    await fetch(`${API_BASE}/api/v1/web/pageview`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(data),
      // Don't block navigation
      keepalive: true,
    });
  } catch (error) {
    // Silently fail (don't block user experience)
    console.warn('Failed to track page view:', error);
  }
}

/**
 * Track Core Web Vitals
 */
export async function trackCoreWebVitals(cwv: CWVData): Promise<void> {
  try {
    await fetch(`${API_BASE}/api/v1/web/cwv`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(cwv),
      keepalive: true,
    });
  } catch (error) {
    console.warn('Failed to track CWV:', error);
  }
}

/**
 * Initialize telemetry tracking
 * Call this once on app mount (typically in root layout)
 */
export function initTelemetry(): void {
  // Track initial page view
  if (typeof window !== 'undefined') {
    trackPageView(window.location.pathname);

    // Listen for route changes (Next.js App Router)
    const observer = new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        if (entry.entryType === 'navigation') {
          trackPageView(window.location.pathname);
        }
      }
    });

    try {
      observer.observe({ entryTypes: ['navigation'] });
    } catch (e) {
      // PerformanceObserver not supported
    }
  }
}

/**
 * Initialize Core Web Vitals tracking
 * Requires 'web-vitals' library
 */
export async function initCWVTracking(): Promise<void> {
  if (typeof window === 'undefined') return;

  try {
    const { onLCP, onFID, onCLS, onTTFB, onTTI } = await import('web-vitals');

    const cwvData: CWVData = {};

    onLCP((metric) => {
      cwvData.lcp = metric.value / 1000; // Convert to seconds
      trackCoreWebVitals(cwvData);
    });

    onFID((metric) => {
      cwvData.fid = metric.value;
      trackCoreWebVitals(cwvData);
    });

    onCLS((metric) => {
      cwvData.cls = metric.value;
      trackCoreWebVitals(cwvData);
    });

    onTTFB((metric) => {
      cwvData.ttfb = metric.value;
      trackCoreWebVitals(cwvData);
    });

    // PR-086: Track Time to Interactive
    if (typeof onTTI === 'function') {
      onTTI((metric) => {
        cwvData.tti = metric.value;
        trackCoreWebVitals(cwvData);
      });
    }
  } catch (error) {
    console.warn('Failed to initialize CWV tracking:', error);
  }
}
