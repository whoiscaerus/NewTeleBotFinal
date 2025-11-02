/**
 * TrustBadge Component
 *
 * Displays user trust score with visual tier indicator.
 * Shows: score, tier (bronze/silver/gold), percentile, and component breakdown.
 *
 * Usage:
 * ```
 * <TrustBadge userId="user123" />
 * <TrustBadge score={75.5} tier="silver" percentile={65} components={{...}} />
 * ```
 */

"use client";

import React, { useState, useEffect } from "react";

interface ComponentsBreakdown {
  performance: number;
  tenure: number;
  endorsements: number;
}

interface TrustScoreData {
  user_id: string;
  score: number;
  tier: "bronze" | "silver" | "gold";
  percentile: number;
  components: ComponentsBreakdown;
  calculated_at: string;
}

interface TrustBadgeProps {
  userId?: string;
  score?: number;
  tier?: "bronze" | "silver" | "gold";
  percentile?: number;
  components?: ComponentsBreakdown;
  showDetails?: boolean;
  onScoreLoaded?: (data: TrustScoreData) => void;
  className?: string;
}

/**
 * ProgressBar - Simple progress bar component
 * @param value - Value from 0-100
 * @param className - CSS classes
 */
function ProgressBar({ value, className = "" }: { value: number; className?: string }) {
  const percentage = Math.min(100, Math.max(0, value));
  return (
    <div className={`w-full h-2 bg-slate-600 rounded-full overflow-hidden ${className}`}>
      <div
        className="h-full bg-gradient-to-r from-blue-500 to-cyan-400"
        style={{ width: `${percentage}%` }}
      />
    </div>
  );
}

/**
 * TrustBadge Component
 *
 * Displays user trust score as visual badge with tier indicator.
 * Can be compact (score + tier only) or expanded (with components).
 *
 * @example
 * // Compact badge fetching data from API
 * <TrustBadge userId="user123" />
 *
 * @example
 * // With pre-loaded data
 * <TrustBadge
 *   score={75.5}
 *   tier="silver"
 *   percentile={65}
 *   components={{ performance: 80, tenure: 70, endorsements: 65 }}
 * />
 */
export function TrustBadge({
  userId,
  score: propsScore,
  tier: propsTier,
  percentile: propsPercentile,
  components: propsComponents,
  showDetails: initialShowDetails = false,
  onScoreLoaded,
  className = "",
}: TrustBadgeProps): React.ReactNode {
  const [score, setScore] = useState<number | null>(propsScore ?? null);
  const [tier, setTier] = useState<string | null>(propsTier ?? null);
  const [percentile, setPercentile] = useState<number | null>(propsPercentile ?? null);
  const [components, setComponents] = useState<ComponentsBreakdown | null>(propsComponents ?? null);
  const [loading, setLoading] = useState(!!userId && !propsScore);
  const [error, setError] = useState<string | null>(null);
  const [showDetails, setShowDetails] = useState(initialShowDetails);

  // Load trust score from API if userId provided
  useEffect(() => {
    if (!userId) return;

    const loadScore = async () => {
      try {
        setLoading(true);
        const response = await fetch(`/api/v1/trust/score/${userId}`);

        if (!response.ok) {
          throw new Error(`Failed to load trust score: ${response.statusText}`);
        }

        const data = (await response.json()) as TrustScoreData;

        setScore(data.score);
        setTier(data.tier);
        setPercentile(data.percentile);
        setComponents(data.components);
        setError(null);

        onScoreLoaded?.(data);
      } catch (err) {
        const message = err instanceof Error ? err.message : "Unknown error";
        setError(message);
        console.error("Failed to load trust score", { user_id: userId, error: err });
      } finally {
        setLoading(false);
      }
    };

    loadScore();
  }, [userId, onScoreLoaded]);

  // Determine tier styling
  const getTierStyles = (tierName: string | null) => {
    const styles: Record<
      string,
      { badge: string; bar: string; text: string; bg: string }
    > = {
      bronze: {
        badge: "border-amber-600/50 bg-amber-900/30 text-amber-200",
        bar: "from-amber-500 to-orange-400",
        text: "text-amber-100",
        bg: "bg-amber-900/20",
      },
      silver: {
        badge: "border-slate-500/50 bg-slate-700/30 text-slate-200",
        bar: "from-slate-400 to-slate-300",
        text: "text-slate-100",
        bg: "bg-slate-700/20",
      },
      gold: {
        badge: "border-yellow-500/50 bg-yellow-900/30 text-yellow-100",
        bar: "from-yellow-400 to-amber-300",
        text: "text-yellow-100",
        bg: "bg-yellow-900/20",
      },
    };

    return styles[tierName || ""] || styles.bronze;
  };

  const tierStyle = getTierStyles(tier);

  if (loading) {
    return (
      <div className={`flex items-center gap-2 ${className}`}>
        <div className="h-8 w-16 animate-pulse rounded bg-slate-600" />
      </div>
    );
  }

  if (error) {
    return (
      <div className={`text-xs text-red-400 ${className}`}>
        ⚠ Error loading score
      </div>
    );
  }

  if (score === null || tier === null) {
    return (
      <div className={`text-xs text-slate-400 ${className}`}>
        Score not calculated
      </div>
    );
  }

  return (
    <>
      {/* Compact Badge Button */}
      <button
        onClick={() => setShowDetails(true)}
        className={`flex items-center gap-3 rounded-lg border ${tierStyle.badge} px-4 py-2 transition-all hover:opacity-100 opacity-90 ${className}`}
        title={`Trust Score: ${score.toFixed(1)}`}
      >
        {/* Score Display */}
        <div className="flex flex-col items-start">
          <div className="text-lg font-bold">{score.toFixed(1)}</div>
          <div className="text-xs font-semibold capitalize">{tier}</div>
        </div>

        {/* Percentile Badge */}
        {percentile !== null && (
          <div className="ml-2 px-2 py-1 rounded bg-slate-600/50 text-xs font-medium">
            {percentile}th
          </div>
        )}
      </button>

      {/* Details Modal - Lightweight without Dialog component */}
      {showDetails && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className="relative w-full max-w-md rounded-lg border border-slate-600 bg-slate-800 p-6 shadow-xl">
            {/* Close Button */}
            <button
              onClick={() => setShowDetails(false)}
              className="absolute right-4 top-4 text-xl text-slate-400 hover:text-slate-200"
            >
              ✕
            </button>

            {/* Header */}
            <h2 className="mb-6 text-xl font-bold">Trust Score Details</h2>

            {/* Main Score Display */}
            <div className={`rounded-lg border ${tierStyle.badge} p-6 text-center mb-6`}>
              <div className="text-5xl font-bold">{score.toFixed(1)}</div>
              <div className="mt-3 text-2xl font-semibold capitalize">{tier}</div>
              {percentile !== null && (
                <div className="mt-2 text-sm text-slate-300">
                  Top {percentile}th percentile
                </div>
              )}
            </div>

            {/* Components Breakdown */}
            {components && (
              <div className="mb-6 space-y-4">
                <h3 className="font-semibold text-slate-100">Score Components</h3>

                {/* Performance */}
                <div>
                  <div className="mb-2 flex justify-between text-sm">
                    <span className="text-slate-300">Performance</span>
                    <span className="font-semibold text-blue-300">
                      {components.performance.toFixed(1)}/100
                    </span>
                  </div>
                  <ProgressBar value={components.performance} />
                  <p className="mt-1 text-xs text-slate-400">
                    Win rate, Sharpe ratio, profit factor
                  </p>
                </div>

                {/* Tenure */}
                <div>
                  <div className="mb-2 flex justify-between text-sm">
                    <span className="text-slate-300">Tenure</span>
                    <span className="font-semibold text-green-300">
                      {components.tenure.toFixed(1)}/100
                    </span>
                  </div>
                  <ProgressBar value={components.tenure} />
                  <p className="mt-1 text-xs text-slate-400">
                    Years active on platform
                  </p>
                </div>

                {/* Endorsements */}
                <div>
                  <div className="mb-2 flex justify-between text-sm">
                    <span className="text-slate-300">Endorsements</span>
                    <span className="font-semibold text-purple-300">
                      {components.endorsements.toFixed(1)}/100
                    </span>
                  </div>
                  <ProgressBar value={components.endorsements} />
                  <p className="mt-1 text-xs text-slate-400">
                    Community verification
                  </p>
                </div>
              </div>
            )}

            {/* Tier Information */}
            <div className="mb-6 rounded-lg bg-slate-700/30 p-4">
              <h4 className="mb-3 font-semibold text-slate-100">Tier Information</h4>
              <div className="space-y-2 text-sm">
                <div className="flex items-start gap-2">
                  <span className="text-amber-400">🥉</span>
                  <div>
                    <strong className="text-amber-100">Bronze:</strong>
                    <p className="text-xs text-slate-400">Score 0-50 (New traders)</p>
                  </div>
                </div>
                <div className="flex items-start gap-2">
                  <span className="text-slate-300">🥈</span>
                  <div>
                    <strong className="text-slate-100">Silver:</strong>
                    <p className="text-xs text-slate-400">Score 50-75 (Verified traders)</p>
                  </div>
                </div>
                <div className="flex items-start gap-2">
                  <span className="text-yellow-400">🥇</span>
                  <div>
                    <strong className="text-yellow-100">Gold:</strong>
                    <p className="text-xs text-slate-400">Score 75+ (Elite traders)</p>
                  </div>
                </div>
              </div>
            </div>

            {/* Close Button */}
            <button
              onClick={() => setShowDetails(false)}
              className="w-full rounded-lg bg-blue-600 hover:bg-blue-700 px-4 py-2 font-medium text-white transition-colors"
            >
              Close
            </button>
          </div>
        </div>
      )}
    </>
  );
}

export default TrustBadge;
