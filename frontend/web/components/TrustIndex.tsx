/**
 * TrustIndex Component (PR-050)
 *
 * Displays public trust index metrics for trader verification.
 * Shows: accuracy, risk/reward ratio, verified trades percentage, trust band.
 *
 * Usage:
 * ```
 * <TrustIndex userId="user123" />
 * <TrustIndex
 *   accuracyMetric={0.65}
 *   averageRR={1.8}
 *   verifiedTradesPct={65}
 *   trustBand="expert"
 * />
 * ```
 */

"use client";

import React, { useState, useEffect } from "react";

interface TrustIndexData {
  user_id: string;
  accuracy_metric: number;  // 0-1
  average_rr: number;       // Risk/reward ratio
  verified_trades_pct: number;  // 0-100
  trust_band: "unverified" | "verified" | "expert" | "elite";
  calculated_at: string;    // ISO date
  valid_until: string;      // ISO date
}

interface TrustIndexProps {
  userId?: string;
  accuracyMetric?: number;
  averageRR?: number;
  verifiedTradesPct?: number;
  trustBand?: "unverified" | "verified" | "expert" | "elite";
  onDataLoaded?: (data: TrustIndexData) => void;
  className?: string;
}

/**
 * MeterBar - Horizontal meter component
 * @param value - Value 0-1 or 0-100 depending on type
 * @param max - Maximum value
 * @param label - Label for the meter
 * @param unit - Unit suffix (%, x, etc)
 */
function MeterBar({
  value,
  max,
  label,
  unit,
  color = "blue",
}: {
  value: number;
  max: number;
  label: string;
  unit: string;
  color?: "blue" | "green" | "yellow" | "red";
}): React.ReactNode {
  const percentage = Math.min(100, (value / max) * 100);

  const colorClasses: Record<string, string> = {
    blue: "from-blue-500 to-cyan-400",
    green: "from-green-500 to-emerald-400",
    yellow: "from-yellow-500 to-orange-400",
    red: "from-red-500 to-pink-400",
  };

  return (
    <div>
      <div className="mb-1 flex justify-between text-sm">
        <span className="text-slate-300">{label}</span>
        <span className="font-semibold text-blue-300">
          {value.toFixed(percentage === 100 ? 0 : 2)}
          {unit}
        </span>
      </div>
      <div className="h-2 w-full rounded-full bg-slate-600 overflow-hidden">
        <div
          className={`h-full bg-gradient-to-r ${colorClasses[color]}`}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
}

/**
 * TrustIndex Component
 *
 * Displays public trader verification metrics.
 * Shows accuracy, R/R ratio, verified trades percentage, and trust band.
 *
 * @example
 * // Fetch from API
 * <TrustIndex userId="user123" />
 *
 * @example
 * // With pre-loaded data
 * <TrustIndex
 *   accuracyMetric={0.65}
 *   averageRR={1.8}
 *   verifiedTradesPct={65}
 *   trustBand="expert"
 * />
 */
export function TrustIndex({
  userId,
  accuracyMetric: propsAccuracy,
  averageRR: propsRR,
  verifiedTradesPct: propsVerified,
  trustBand: propsBand,
  onDataLoaded,
  className = "",
}: TrustIndexProps): React.ReactNode {
  const [accuracy, setAccuracy] = useState<number | null>(propsAccuracy ?? null);
  const [rr, setRR] = useState<number | null>(propsRR ?? null);
  const [verified, setVerified] = useState<number | null>(propsVerified ?? null);
  const [band, setBand] = useState<string | null>(propsBand ?? null);
  const [loading, setLoading] = useState(!!userId && !propsAccuracy);
  const [error, setError] = useState<string | null>(null);

  // Load trust index from API if userId provided
  useEffect(() => {
    if (!userId) return;

    const loadIndex = async () => {
      try {
        setLoading(true);
        const response = await fetch(`/api/v1/public/trust-index/${userId}`);

        if (!response.ok) {
          throw new Error(`Failed to load trust index: ${response.statusText}`);
        }

        const data = (await response.json()) as TrustIndexData;

        setAccuracy(data.accuracy_metric);
        setRR(data.average_rr);
        setVerified(data.verified_trades_pct);
        setBand(data.trust_band);
        setError(null);

        onDataLoaded?.(data);
      } catch (err) {
        const message = err instanceof Error ? err.message : "Unknown error";
        setError(message);
        console.error("Failed to load trust index", { user_id: userId, error: err });
      } finally {
        setLoading(false);
      }
    };

    loadIndex();
  }, [userId, onDataLoaded]);

  // Determine band styling and icon
  const getBandStyles = (bandName: string | null) => {
    const styles: Record<
      string,
      { bg: string; border: string; icon: string; title: string }
    > = {
      unverified: {
        bg: "bg-slate-700/30",
        border: "border-slate-600/50",
        icon: "❓",
        title: "Unverified",
      },
      verified: {
        bg: "bg-blue-900/30",
        border: "border-blue-600/50",
        icon: "✓",
        title: "Verified",
      },
      expert: {
        bg: "bg-purple-900/30",
        border: "border-purple-600/50",
        icon: "⭐",
        title: "Expert",
      },
      elite: {
        bg: "bg-yellow-900/30",
        border: "border-yellow-600/50",
        icon: "👑",
        title: "Elite",
      },
    };

    return styles[bandName || ""] || styles.unverified;
  };

  const bandStyle = getBandStyles(band);

  if (loading) {
    return (
      <div className={`flex items-center gap-2 ${className}`}>
        <div className="h-12 w-full max-w-sm animate-pulse rounded bg-slate-600" />
      </div>
    );
  }

  if (error) {
    return (
      <div className={`text-sm text-red-400 ${className}`}>
        ⚠ Error: {error}
      </div>
    );
  }

  if (accuracy === null || band === null) {
    return (
      <div className={`text-sm text-slate-400 ${className}`}>
        No index data available
      </div>
    );
  }

  return (
    <div
      className={`rounded-lg border ${bandStyle.border} ${bandStyle.bg} p-4 space-y-4 ${className}`}
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-700 pb-3">
        <h3 className="text-lg font-semibold text-slate-100">Trader Verification</h3>
        <div className="flex items-center gap-2">
          <span className="text-2xl">{bandStyle.icon}</span>
          <span className="text-sm font-medium text-slate-300">{bandStyle.title}</span>
        </div>
      </div>

      {/* Metrics Grid */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {/* Accuracy */}
        <div className="rounded-lg bg-slate-700/20 p-3">
          <div className="text-xs text-slate-400 mb-1">Accuracy</div>
          <div className="text-2xl font-bold text-blue-300">
            {(accuracy * 100).toFixed(0)}%
          </div>
          <div className="text-xs text-slate-500 mt-1">Win rate</div>
        </div>

        {/* R/R Ratio */}
        <div className="rounded-lg bg-slate-700/20 p-3">
          <div className="text-xs text-slate-400 mb-1">R/R Ratio</div>
          <div className="text-2xl font-bold text-green-300">
            {rr?.toFixed(2)}x
          </div>
          <div className="text-xs text-slate-500 mt-1">Risk/reward</div>
        </div>

        {/* Verified Trades */}
        <div className="rounded-lg bg-slate-700/20 p-3">
          <div className="text-xs text-slate-400 mb-1">Verified</div>
          <div className="text-2xl font-bold text-purple-300">
            {verified}%
          </div>
          <div className="text-xs text-slate-500 mt-1">Of trades</div>
        </div>

        {/* Trust Band */}
        <div className="rounded-lg bg-slate-700/20 p-3">
          <div className="text-xs text-slate-400 mb-1">Band</div>
          <div className="text-lg font-bold text-yellow-300 capitalize">
            {band}
          </div>
          <div className="text-xs text-slate-500 mt-1">Level</div>
        </div>
      </div>

      {/* Detailed Meters */}
      <div className="space-y-3 pt-2">
        <MeterBar value={accuracy} max={1} label="Accuracy" unit="%" color="blue" />
        <MeterBar value={rr ?? 0} max={3} label="Risk/Reward" unit="x" color="green" />
        <MeterBar value={verified ?? 0} max={100} label="Verified Trades" unit="%" color="yellow" />
      </div>

      {/* Band Information */}
      <div className="rounded-lg bg-slate-700/30 p-3 text-xs text-slate-300 space-y-1 pt-2 border-t border-slate-700">
        <div>
          <strong className="text-slate-200">How bands work:</strong>
        </div>
        <div className="ml-2 space-y-1">
          <div>❓ <strong>Unverified:</strong> Below verification thresholds</div>
          <div>✓ <strong>Verified:</strong> Meets accuracy & R/R standards</div>
          <div>⭐ <strong>Expert:</strong> High accuracy & verified trades</div>
          <div>👑 <strong>Elite:</strong> Top tier - exceptional performance</div>
        </div>
      </div>
    </div>
  );
}

export default TrustIndex;
