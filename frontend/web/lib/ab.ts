/**
 * A/B Testing Library
 *
 * Provides experiment framework for conversion optimization:
 * - Variant assignment (URL param or cookie-based)
 * - Persistent variant storage
 * - Telemetry tracking
 * - SSR-compatible
 */

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000';

/**
 * Experiment configuration
 */
export interface Experiment {
  name: string;
  variants: string[];
  weights?: number[]; // Optional weights (default: equal distribution)
  cookie_days?: number; // Persistence duration (default: 30)
}

/**
 * Variant assignment result
 */
export interface VariantAssignment {
  experiment: string;
  variant: string;
  source: 'url' | 'cookie' | 'assigned';
}

/**
 * Get variant for an experiment
 *
 * Priority:
 * 1. URL param (?variant=control)
 * 2. Existing cookie
 * 3. Weighted random assignment
 *
 * @param experiment - Experiment configuration
 * @returns Variant assignment
 *
 * @example
 * const variant = getVariant({
 *   name: 'hero_copy',
 *   variants: ['control', 'benefit_focused', 'urgency']
 * });
 * console.log(variant.variant); // 'control'
 */
export function getVariant(experiment: Experiment): VariantAssignment {
  const { name, variants, weights, cookie_days = 30 } = experiment;

  if (variants.length === 0) {
    throw new Error(`Experiment "${name}" must have at least one variant`);
  }

  // 1. Check URL parameter (for testing/preview)
  if (typeof window !== 'undefined') {
    const urlParams = new URLSearchParams(window.location.search);
    const urlVariant = urlParams.get('variant');

    if (urlVariant && variants.includes(urlVariant)) {
      // Set cookie for persistence
      setVariant(name, urlVariant, cookie_days);
      trackVariantView(name, urlVariant);

      return {
        experiment: name,
        variant: urlVariant,
        source: 'url',
      };
    }
  }

  // 2. Check existing cookie
  const cookieVariant = getCookie(`ab_${name}`);
  if (cookieVariant && variants.includes(cookieVariant)) {
    trackVariantView(name, cookieVariant);

    return {
      experiment: name,
      variant: cookieVariant,
      source: 'cookie',
    };
  }

  // 3. Assign new variant (weighted random)
  const assignedVariant = assignVariant(variants, weights);
  setVariant(name, assignedVariant, cookie_days);
  trackVariantView(name, assignedVariant);

  return {
    experiment: name,
    variant: assignedVariant,
    source: 'assigned',
  };
}

/**
 * Set variant cookie
 *
 * @param experiment - Experiment name
 * @param variant - Variant name
 * @param days - Cookie expiration (default: 30)
 */
export function setVariant(
  experiment: string,
  variant: string,
  days: number = 30
): void {
  if (typeof document === 'undefined') return; // SSR guard

  const expires = new Date();
  expires.setDate(expires.getDate() + days);

  document.cookie = `ab_${experiment}=${variant}; expires=${expires.toUTCString()}; path=/; SameSite=Lax`;
}

/**
 * Get cookie value
 *
 * @param name - Cookie name
 * @returns Cookie value or null
 */
function getCookie(name: string): string | null {
  if (typeof document === 'undefined') return null; // SSR guard

  const match = document.cookie.match(new RegExp(`(^| )${name}=([^;]+)`));
  return match ? match[2] : null;
}

/**
 * Assign variant using weighted random selection
 *
 * @param variants - Array of variant names
 * @param weights - Optional weights (default: equal distribution)
 * @returns Selected variant
 */
function assignVariant(variants: string[], weights?: number[]): string {
  // Default to equal weights
  const normalizedWeights = weights || variants.map(() => 1);

  if (normalizedWeights.length !== variants.length) {
    throw new Error('Weights array must match variants array length');
  }

  // Calculate cumulative weights
  const totalWeight = normalizedWeights.reduce((sum, w) => sum + w, 0);
  const cumulativeWeights = normalizedWeights.reduce((acc, w) => {
    const lastWeight = acc.length > 0 ? acc[acc.length - 1] : 0;
    acc.push(lastWeight + w);
    return acc;
  }, [] as number[]);

  // Random selection
  const random = Math.random() * totalWeight;
  const index = cumulativeWeights.findIndex((w) => random < w);

  return variants[index >= 0 ? index : variants.length - 1];
}

/**
 * Track variant view to telemetry endpoint
 *
 * @param experiment - Experiment name
 * @param variant - Variant name
 */
async function trackVariantView(experiment: string, variant: string): Promise<void> {
  try {
    await fetch(`${API_BASE}/api/v1/web/ab`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        experiment,
        variant,
        timestamp: Date.now(),
      }),
    });
  } catch (error) {
    // Fail silently (telemetry should not break UX)
    console.error('Failed to track A/B variant view:', error);
  }
}

/**
 * Track conversion event
 *
 * @param experiment - Experiment name
 * @param variant - Variant name
 * @param event - Conversion event name (e.g., 'signup', 'purchase')
 */
export async function trackConversion(
  experiment: string,
  variant: string,
  event: string
): Promise<void> {
  try {
    await fetch(`${API_BASE}/api/v1/web/ab/conversion`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        experiment,
        variant,
        event,
        timestamp: Date.now(),
      }),
    });
  } catch (error) {
    console.error('Failed to track A/B conversion:', error);
  }
}

/**
 * Clear all experiment cookies (for testing)
 */
export function clearExperiments(): void {
  if (typeof document === 'undefined') return;

  const cookies = document.cookie.split(';');
  for (const cookie of cookies) {
    const name = cookie.split('=')[0].trim();
    if (name.startsWith('ab_')) {
      document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;`;
    }
  }
}

/**
 * Predefined experiments
 */
export const EXPERIMENTS = {
  HERO_COPY: {
    name: 'hero_copy',
    variants: ['control', 'benefit_focused', 'urgency'],
    weights: [0.34, 0.33, 0.33], // Equal distribution
    cookie_days: 30,
  },
  CTA_BUTTON: {
    name: 'cta_button',
    variants: ['get_started', 'start_trading', 'join_now'],
    weights: [0.5, 0.25, 0.25], // Control gets 50%
    cookie_days: 30,
  },
  PRICING_LAYOUT: {
    name: 'pricing_layout',
    variants: ['3_tier', '4_tier_with_enterprise'],
    weights: [0.7, 0.3], // Control gets 70%
    cookie_days: 30,
  },
} as const;
