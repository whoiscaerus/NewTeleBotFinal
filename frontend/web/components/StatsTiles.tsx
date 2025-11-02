"use client";

import React, { useState, useEffect } from "react";

interface PerformanceMetrics {
  total_trades: number;
  win_rate: number;
  profit_factor: number;
  return_percent: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  calmar_ratio: number;
  avg_rr: number;
  max_drawdown_percent: number;
  data_as_of: string;
  delay_applied_minutes: number;
}

interface StatTileProps {
  icon: string;
  label: string;
  value: number | string;
  unit: string;
  isPositive?: boolean;
  loading?: boolean;
}

/**
 * StatTile Component
 *
 * Individual metric tile with icon, label, value, and color coding.
 *
 * @param icon - Emoji or symbol for the stat
 * @param label - Label text
 * @param value - Numeric or string value
 * @param unit - Unit suffix (%, x, £, etc.)
 * @param isPositive - Whether value is positive (green) or negative (red)
 * @param loading - Show skeleton loading state
 *
 * @returns React component
 */
function StatTile({
  icon,
  label,
  value,
  unit,
  isPositive = true,
  loading = false,
}: StatTileProps): React.ReactNode {
  if (loading) {
    return (
      <div className="bg-slate-700/50 rounded-lg border border-slate-600 p-4 sm:p-6 animate-pulse">
        <div className="h-4 bg-slate-600 rounded mb-2 w-20"></div>
        <div className="h-8 bg-slate-600 rounded w-16"></div>
      </div>
    );
  }

  const colorClass = isPositive
    ? "text-green-400 border-green-700/30 bg-green-900/10"
    : "text-red-400 border-red-700/30 bg-red-900/10";

  return (
    <div className={`rounded-lg border ${colorClass} p-4 sm:p-6 bg-slate-700/30`}>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-slate-400 text-sm font-medium">{label}</p>
          <p className={`text-2xl sm:text-3xl font-bold mt-2 ${colorClass.split(" ")[0]}`}>
            {value}
            <span className="text-lg ml-1">{unit}</span>
          </p>
        </div>
        <div className="text-3xl sm:text-4xl">{icon}</div>
      </div>
    </div>
  );
}

/**
 * StatsTiles Component
 *
 * Grid of 6 performance statistic tiles:
 * - Win Rate (%)
 * - Profit Factor (x)
 * - Sharpe Ratio
 * - Sortino Ratio
 * - Return (%)
 * - Max Drawdown (%)
 *
 * Fetches data from /api/v1/public/performance/summary
 * Includes loading and error states.
 *
 * @example
 * <StatsTiles />
 *
 * @returns React component
 */
export function StatsTiles(): React.ReactNode {
  const [metrics, setMetrics] = useState<PerformanceMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchMetrics = async () => {
      try {
        setLoading(true);
        setError(null);

        const response = await fetch(
          "/api/v1/public/performance/summary?delay_minutes=1440"
        );

        if (!response.ok) {
          throw new Error(`API error: ${response.statusText}`);
        }

        const data: PerformanceMetrics = await response.json();
        setMetrics(data);
      } catch (err) {
        const message = err instanceof Error ? err.message : "Failed to load metrics";
        setError(message);
        console.error("Metrics fetch error:", err);
      } finally {
        setLoading(false);
      }
    };

    fetchMetrics();
  }, []);

  // Error State
  if (error) {
    return (
      <div className="bg-red-900/20 border border-red-700 rounded-lg p-6 text-center">
        <p className="text-red-300">⚠️ Unable to load performance metrics</p>
        <p className="text-sm text-red-400 mt-1">{error}</p>
      </div>
    );
  }

  // Loading States
  if (loading || !metrics) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {[...Array(6)].map((_, i) => (
          <StatTile
            key={i}
            icon=""
            label=""
            value=""
            unit=""
            loading={true}
          />
        ))}
      </div>
    );
  }

  // Format percentage value
  const formatPercent = (value: number): string => {
    return (value * 100).toFixed(1);
  };

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      {/* Win Rate */}
      <StatTile
        icon="🎯"
        label="Win Rate"
        value={formatPercent(metrics.win_rate)}
        unit="%"
        isPositive={metrics.win_rate >= 0.5}
      />

      {/* Profit Factor */}
      <StatTile
        icon="📈"
        label="Profit Factor"
        value={metrics.profit_factor.toFixed(2)}
        unit="x"
        isPositive={metrics.profit_factor >= 1.5}
      />

      {/* Sharpe Ratio */}
      <StatTile
        icon="⚡"
        label="Sharpe Ratio"
        value={metrics.sharpe_ratio.toFixed(2)}
        unit=""
        isPositive={metrics.sharpe_ratio >= 1.0}
      />

      {/* Sortino Ratio */}
      <StatTile
        icon="🛡️"
        label="Sortino Ratio"
        value={metrics.sortino_ratio.toFixed(2)}
        unit=""
        isPositive={metrics.sortino_ratio >= 1.0}
      />

      {/* Total Return */}
      <StatTile
        icon="💰"
        label="Total Return"
        value={metrics.return_percent.toFixed(2)}
        unit="%"
        isPositive={metrics.return_percent >= 0}
      />

      {/* Max Drawdown */}
      <StatTile
        icon="📉"
        label="Max Drawdown"
        value={Math.abs(metrics.max_drawdown_percent).toFixed(2)}
        unit="%"
        isPositive={false}
      />
    </div>
  );
}
