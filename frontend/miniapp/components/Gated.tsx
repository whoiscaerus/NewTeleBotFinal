"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { getEntitlements } from "@/lib/api";
import { logger } from "@/lib/logger";

interface GatedProps {
  /** Feature/entitlement required to view content */
  requiredEntitlement: string;
  /** Human-readable feature name for display */
  featureName?: string;
  /** Content to show if user has entitlement */
  children: React.ReactNode;
  /** Fallback UI to show if locked (defaults to upgrade modal) */
  fallback?: React.ReactNode;
  /** Minimum tier required (0=Free, 1=Premium, 2=VIP, 3=Enterprise) */
  minimumTier?: number;
}

/**
 * Gated Component
 *
 * Wraps content to enforce entitlement requirements.
 * Shows locked state with upgrade CTA if user lacks required entitlement.
 *
 * @example
 * <Gated
 *   requiredEntitlement="premium_signals"
 *   featureName="Analytics Dashboard"
 *   minimumTier={1}
 * >
 *   <AnalyticsDashboard />
 * </Gated>
 */
export const Gated: React.FC<GatedProps> = ({
  requiredEntitlement,
  featureName = "This feature",
  children,
  fallback,
  minimumTier = 0,
}) => {
  const router = useRouter();
  const { user, isLoading: authLoading } = useAuth();
  const [hasEntitlement, setHasEntitlement] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (authLoading) return;

    const checkEntitlements = async () => {
      try {
        if (!user) {
          setHasEntitlement(false);
          logger.warn("User not authenticated for gated component", {
            feature: featureName,
            entitlement: requiredEntitlement,
          });
          setLoading(false);
          return;
        }

        const entitlements = await getEntitlements();

        // Check if user has required entitlement
        const userTier = entitlements.tier || 0;
        const hasRequired = entitlements.entitlements?.includes(
          requiredEntitlement
        );

        // Both tier and entitlement checks must pass
        const allowed = userTier >= minimumTier && hasRequired;

        setHasEntitlement(allowed);

        if (!allowed) {
          logger.info("Entitlement check failed", {
            feature: featureName,
            requiredEntitlement,
            userTier,
            minimumTier,
            hasRequired,
          });
        }

        setError(null);
      } catch (err) {
        const message = err instanceof Error ? err.message : "Unknown error";
        logger.error("Failed to check entitlements", {
          feature: featureName,
          error: message,
        });
        setError(message);
        setHasEntitlement(false);
      } finally {
        setLoading(false);
      }
    };

    checkEntitlements();
  }, [user, authLoading, requiredEntitlement, featureName, minimumTier]);

  // Loading state
  if (loading) {
    return <div className="text-gray-400 text-center py-8">Checking access...</div>;
  }

  // Has entitlement - show content
  if (hasEntitlement) {
    return <>{children}</>;
  }

  // Locked - show fallback or default upgrade modal
  if (fallback) {
    return <>{fallback}</>;
  }

  // Default locked UI
  return <DefaultLockedUI featureName={featureName} entitlement={requiredEntitlement} />;
};

/**
 * Default UI for locked/gated features
 * Shows upgrade modal with link to checkout
 */
interface DefaultLockedUIProps {
  featureName: string;
  entitlement: string;
}

const DefaultLockedUI: React.FC<DefaultLockedUIProps> = ({
  featureName,
  entitlement,
}) => {
  const router = useRouter();
  const { user } = useAuth();

  const handleUpgrade = () => {
    if (!user) {
      router.push("/auth/login");
      return;
    }

    // Deep link to checkout with suggested plan
    const plan = getPlanForEntitlement(entitlement);
    router.push(`/checkout?plan=${plan}`);
  };

  return (
    <div className="flex items-center justify-center py-12 px-4">
      <div className="bg-gradient-to-br from-blue-50 to-indigo-50 dark:from-blue-950 dark:to-indigo-950 border border-blue-200 dark:border-blue-800 rounded-lg shadow-lg p-8 max-w-sm w-full text-center">
        {/* Lock Icon */}
        <div className="flex justify-center mb-4">
          <div className="bg-blue-100 dark:bg-blue-900 rounded-full p-4">
            <svg
              className="w-8 h-8 text-blue-600 dark:text-blue-300"
              fill="currentColor"
              viewBox="0 0 24 24"
            >
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm3.5-9c.83 0 1.5-.67 1.5-1.5S16.33 8 15.5 8 14 8.67 14 9.5s.67 1.5 1.5 1.5zm-7 0c.83 0 1.5-.67 1.5-1.5S9.33 8 8.5 8 7 8.67 7 9.5 7.67 11 8.5 11zm3.5 6.5c2.33 0 4.31-1.46 5.11-3.5H6.89c.8 2.04 2.78 3.5 5.11 3.5z" />
            </svg>
          </div>
        </div>

        {/* Title */}
        <h3 className="text-xl font-bold text-gray-900 dark:text-white mb-2">
          {featureName} Locked
        </h3>

        {/* Description */}
        <p className="text-gray-600 dark:text-gray-300 text-sm mb-6">
          Upgrade your plan to access {featureName.toLowerCase()}. Unlock premium
          features with instant activation.
        </p>

        {/* Feature list */}
        <ul className="text-left text-sm mb-6 space-y-2">
          <li className="flex items-center text-gray-700 dark:text-gray-400">
            <svg className="w-4 h-4 mr-2 text-green-500" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
            </svg>
            Premium signals & analysis
          </li>
          <li className="flex items-center text-gray-700 dark:text-gray-400">
            <svg className="w-4 h-4 mr-2 text-green-500" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
            </svg>
            Real-time data & alerts
          </li>
          <li className="flex items-center text-gray-700 dark:text-gray-400">
            <svg className="w-4 h-4 mr-2 text-green-500" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
            </svg>
            Priority 24/7 support
          </li>
        </ul>

        {/* CTA Button */}
        <button
          onClick={handleUpgrade}
          className="w-full bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white font-semibold py-3 px-4 rounded-lg transition-all duration-200 shadow-md hover:shadow-lg"
        >
          Upgrade Now
        </button>

        {/* Alternative */}
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-4">
          Free tier users get limited access to basic features
        </p>
      </div>
    </div>
  );
};

/**
 * Map entitlement name to suggested plan for checkout
 */
function getPlanForEntitlement(entitlement: string): string {
  const planMap: { [key: string]: string } = {
    premium_signals: "premium",
    copy_trading: "vip",
    advanced_analytics: "premium",
    vip_support: "enterprise",
  };
  return planMap[entitlement] || "premium";
}

export default Gated;
