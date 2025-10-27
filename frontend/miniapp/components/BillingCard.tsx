"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";

interface Plan {
  name: string;
  tier: "free" | "premium" | "vip" | "enterprise";
  price: number;
  currency: string;
  features: string[];
}

interface Subscription {
  tier: "free" | "premium" | "vip" | "enterprise";
  status: "active" | "past_due" | "canceled";
  current_period_start: string;
  current_period_end: string;
  price_usd_monthly: number;
}

interface BillingCardProps {
  /** Current subscription data */
  subscription?: Subscription | null;
  /** Loading state */
  loading?: boolean;
  /** Error message if any */
  error?: string | null;
  /** JWT token for API calls */
  jwt?: string;
  /** Callback when upgrade clicked */
  onUpgradeClick?: (plan: string) => void;
  /** Callback when manage portal clicked */
  onManageClick?: () => void;
}

/**
 * BillingCard Component
 *
 * Displays current subscription plan, status, and billing actions.
 * Shows "Upgrade Plan" and "Manage Billing" buttons with links to Stripe.
 *
 * @example
 * <BillingCard
 *   subscription={subData}
 *   jwt={token}
 *   onUpgradeClick={(plan) => console.log("Upgrade to", plan)}
 *   onManageClick={() => window.open(portalUrl)}
 * />
 */
export const BillingCard: React.FC<BillingCardProps> = ({
  subscription,
  loading = false,
  error = null,
  jwt,
  onUpgradeClick,
  onManageClick,
}) => {
  const router = useRouter();
  const [openingPortal, setOpeningPortal] = useState(false);
  const [openingCheckout, setOpeningCheckout] = useState(false);

  // Get plan info from tier
  const getPlanInfo = (tier: string) => {
    const plans: { [key: string]: Plan } = {
      free: {
        name: "Free",
        tier: "free",
        price: 0,
        currency: "USD",
        features: ["Basic access", "Limited signals"],
      },
      premium: {
        name: "Premium",
        tier: "premium",
        price: 29,
        currency: "USD",
        features: ["Premium signals", "Advanced analytics", "Email support"],
      },
      vip: {
        name: "VIP",
        tier: "vip",
        price: 99,
        currency: "USD",
        features: ["All Premium features", "Copy trading", "Priority support"],
      },
      enterprise: {
        name: "Enterprise",
        tier: "enterprise",
        price: 299,
        currency: "USD",
        features: ["All VIP features", "Custom API", "Dedicated support"],
      },
    };
    return plans[tier] || plans.free;
  };

  const handleManagePortal = async () => {
    if (!jwt) return;

    try {
      setOpeningPortal(true);

      const response = await fetch("/api/v1/billing/portal", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${jwt}`,
          "Content-Type": "application/json",
        },
      });

      if (!response.ok) {
        throw new Error("Failed to open portal");
      }

      const data = await response.json();
      if (data.url) {
        window.open(data.url, "_blank");
        onManageClick?.();
      }
    } catch (err) {
      console.error("Portal error:", err);
    } finally {
      setOpeningPortal(false);
    }
  };

  const handleUpgrade = (plan: string) => {
    router.push(`/checkout?plan=${plan}`);
    onUpgradeClick?.(plan);
  };

  // Loading state
  if (loading) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 animate-pulse">
        <div className="h-6 bg-gray-200 dark:bg-gray-700 rounded w-1/3 mb-4"></div>
        <div className="h-12 bg-gray-200 dark:bg-gray-700 rounded mb-4"></div>
        <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-2/3"></div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-6">
        <h3 className="font-semibold text-red-800 dark:text-red-200 mb-2">
          Error loading subscription
        </h3>
        <p className="text-red-700 dark:text-red-300 text-sm">{error}</p>
      </div>
    );
  }

  const currentPlan = subscription ? getPlanInfo(subscription.tier) : getPlanInfo("free");
  const nextPlanTier =
    subscription?.tier === "free"
      ? "premium"
      : subscription?.tier === "premium"
        ? "vip"
        : subscription?.tier === "vip"
          ? "enterprise"
          : "enterprise";

  return (
    <div className="bg-gradient-to-br from-white to-gray-50 dark:from-gray-800 dark:to-gray-900 rounded-lg shadow-md border border-gray-200 dark:border-gray-700 overflow-hidden">
      {/* Header */}
      <div className="bg-gradient-to-r from-blue-600 to-indigo-600 px-6 py-4">
        <h3 className="text-white font-semibold text-lg">Current Plan</h3>
      </div>

      {/* Content */}
      <div className="p-6 space-y-6">
        {/* Plan Info */}
        <div>
          <div className="flex items-baseline justify-between mb-4">
            <h4 className="text-2xl font-bold text-gray-900 dark:text-white">
              {currentPlan.name}
            </h4>
            {currentPlan.price > 0 && (
              <span className="text-3xl font-bold text-blue-600 dark:text-blue-400">
                ${currentPlan.price}
                <span className="text-sm text-gray-600 dark:text-gray-400 font-normal">
                  /month
                </span>
              </span>
            )}
          </div>

          {/* Status Badge */}
          <div className="flex items-center gap-2">
            <span
              className={`px-3 py-1 rounded-full text-xs font-semibold ${
                subscription?.status === "active"
                  ? "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300"
                  : subscription?.status === "past_due"
                    ? "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300"
                    : "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300"
              }`}
            >
              {subscription?.status || "inactive"}
            </span>
          </div>

          {/* Period info */}
          {subscription && (
            <p className="text-sm text-gray-600 dark:text-gray-400 mt-2">
              Renews on{" "}
              {new Date(subscription.current_period_end).toLocaleDateString()}
            </p>
          )}
        </div>

        {/* Features List */}
        <div className="space-y-2">
          <h5 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
            Included Features
          </h5>
          <ul className="space-y-1">
            {currentPlan.features.map((feature, i) => (
              <li key={i} className="flex items-center text-sm text-gray-600 dark:text-gray-400">
                <svg
                  className="w-4 h-4 mr-2 text-green-500"
                  fill="currentColor"
                  viewBox="0 0 20 20"
                >
                  <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                </svg>
                {feature}
              </li>
            ))}
          </ul>
        </div>

        {/* Action Buttons */}
        <div className="space-y-3 pt-4 border-t border-gray-200 dark:border-gray-700">
          {subscription?.status === "active" && (
            <>
              {/* Manage Billing Button */}
              <button
                onClick={handleManagePortal}
                disabled={openingPortal}
                className="w-full px-4 py-2 bg-white dark:bg-gray-700 text-gray-900 dark:text-white border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors font-medium disabled:opacity-50"
              >
                {openingPortal ? "Opening..." : "Manage Billing"}
              </button>

              {/* Upgrade Button (if not on highest tier) */}
              {subscription.tier !== "enterprise" && (
                <button
                  onClick={() => handleUpgrade(nextPlanTier)}
                  className="w-full px-4 py-2 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white rounded-lg transition-all font-medium shadow-md hover:shadow-lg"
                >
                  Upgrade Plan
                </button>
              )}
            </>
          )}

          {!subscription || subscription.status !== "active" && (
            <button
              onClick={() => handleUpgrade("premium")}
              className="w-full px-4 py-2 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white rounded-lg transition-all font-medium shadow-md hover:shadow-lg"
            >
              Get Started
            </button>
          )}
        </div>

        {/* Billing Info */}
        <div className="text-xs text-gray-500 dark:text-gray-400 text-center pt-4 border-t border-gray-200 dark:border-gray-700">
          <p>Billed securely via Stripe</p>
          <p>Cancel anytime, no questions asked</p>
        </div>
      </div>
    </div>
  );
};

export default BillingCard;
