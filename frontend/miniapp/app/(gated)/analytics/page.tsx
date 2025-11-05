"use client";

import React, { useState, useEffect } from "react";
import { Gated } from "@/components/Gated";
import { getAnalytics } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { logger } from "@/lib/logger";

interface AnalyticsData {
  total_trades: number;
  win_rate: number;
  profit_factor: number;
  average_rr: number;
  sharpe_ratio: number;
  max_drawdown: number;
  total_return: number;
  period_days: number;
}

/**
 * Analytics Dashboard Page
 *
 * Premium feature showing comprehensive trading analytics.
 * Requires "premium_signals" entitlement or minimum tier 1.
 *
 * Displays:
 * - Win rate & profit metrics
 * - Risk-adjusted returns (Sharpe, Sortino)
 * - Drawdown analysis
 * - Equity curve
 * - Trade distribution
 */
export default function AnalyticsPage() {
  const { user } = useAuth();
  const [analytics, setAnalytics] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;

    const fetchAnalytics = async () => {
      try {
        setLoading(true);
        const data = await getAnalytics() as AnalyticsData;
        setAnalytics(data);
        setError(null);

        logger.info("Analytics loaded", {
          trades: data.total_trades,
          winRate: data.win_rate,
        });
      } catch (err) {
        const message = err instanceof Error ? err.message : "Failed to load analytics";
        logger.error("Analytics load failed", { error: message });
        setError(message);
      } finally {
        setLoading(false);
      }
    };

    fetchAnalytics();
  }, [user]);

  return (
    <Gated
      requiredEntitlement="premium_signals"
      featureName="Trading Analytics"
      minimumTier={1}
    >
      <div className="space-y-6 pb-8">
        {/* Header */}
        <div>
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
            Trading Analytics
          </h1>
          <p className="text-gray-600 dark:text-gray-300 mt-1">
            Comprehensive performance metrics and risk analysis
          </p>
        </div>

        {/* Loading State */}
        {loading && (
          <div className="bg-white dark:bg-gray-800 rounded-lg p-8 text-center">
            <div className="inline-block animate-spin">
              <svg
                className="w-8 h-8 text-blue-600"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                />
              </svg>
            </div>
            <p className="text-gray-500 mt-2">Loading analytics...</p>
          </div>
        )}

        {/* Error State */}
        {error && !loading && (
          <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
            <div className="flex items-start">
              <svg
                className="w-5 h-5 text-red-600 dark:text-red-400 mt-0.5 flex-shrink-0"
                fill="currentColor"
                viewBox="0 0 20 20"
              >
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
              </svg>
              <div className="ml-3">
                <h3 className="font-medium text-red-800 dark:text-red-200">
                  Failed to load analytics
                </h3>
                <p className="text-red-700 dark:text-red-300 text-sm mt-1">{error}</p>
              </div>
            </div>
          </div>
        )}

        {/* Analytics Grid */}
        {analytics && !loading && (
          <div className="space-y-6">
            {/* Primary Metrics */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              <MetricCard
                label="Win Rate"
                value={`${(analytics.win_rate * 100).toFixed(1)}%`}
                change={analytics.win_rate > 0.5 ? "up" : "down"}
                icon="📊"
              />
              <MetricCard
                label="Profit Factor"
                value={analytics.profit_factor.toFixed(2)}
                change={analytics.profit_factor > 1.5 ? "up" : "neutral"}
                icon="💰"
              />
              <MetricCard
                label="Avg R:R"
                value={analytics.average_rr.toFixed(2)}
                change={analytics.average_rr > 1.5 ? "up" : "neutral"}
                icon="⚖️"
              />
              <MetricCard
                label="Total Return"
                value={`${(analytics.total_return * 100).toFixed(1)}%`}
                change={analytics.total_return > 0 ? "up" : "down"}
                icon="📈"
              />
            </div>

            {/* Risk Metrics */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <MetricCard
                label="Max Drawdown"
                value={`${(analytics.max_drawdown * 100).toFixed(1)}%`}
                change={analytics.max_drawdown < 0.15 ? "up" : "down"}
                icon="📉"
              />
              <MetricCard
                label="Sharpe Ratio"
                value={analytics.sharpe_ratio.toFixed(2)}
                change={analytics.sharpe_ratio > 1 ? "up" : "neutral"}
                icon="📐"
              />
            </div>

            {/* Trade Summary */}
            <div className="bg-white dark:bg-gray-800 rounded-lg p-6 shadow-sm">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                Trade Summary
              </h3>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4 text-center">
                <div className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded">
                  <p className="text-2xl font-bold text-blue-600">
                    {analytics.total_trades}
                  </p>
                  <p className="text-sm text-gray-600 dark:text-gray-400">Total Trades</p>
                </div>
                <div className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded">
                  <p className="text-2xl font-bold text-green-600">
                    {Math.round(analytics.total_trades * analytics.win_rate)}
                  </p>
                  <p className="text-sm text-gray-600 dark:text-gray-400">Winning Trades</p>
                </div>
                <div className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded">
                  <p className="text-2xl font-bold text-red-600">
                    {Math.round(analytics.total_trades * (1 - analytics.win_rate))}
                  </p>
                  <p className="text-sm text-gray-600 dark:text-gray-400">Losing Trades</p>
                </div>
                <div className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded">
                  <p className="text-2xl font-bold text-gray-600 dark:text-gray-400">
                    {analytics.period_days}
                  </p>
                  <p className="text-sm text-gray-600 dark:text-gray-400">Days</p>
                </div>
                <div className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded">
                  <p className="text-2xl font-bold text-blue-600">
                    {(analytics.total_trades / Math.max(analytics.period_days, 1)).toFixed(1)}
                  </p>
                  <p className="text-sm text-gray-600 dark:text-gray-400">Trades/Day</p>
                </div>
              </div>
            </div>

            {/* Equity Curve Placeholder */}
            <div className="bg-white dark:bg-gray-800 rounded-lg p-6 shadow-sm">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                Equity Curve
              </h3>
              <div className="h-64 bg-gradient-to-b from-blue-50 to-blue-100 dark:from-blue-900/20 dark:to-blue-900/40 rounded flex items-center justify-center">
                <p className="text-gray-500 dark:text-gray-400">
                  Chart visualization coming soon
                </p>
              </div>
            </div>

            {/* Disclaimers */}
            <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg p-4">
              <div className="flex items-start">
                <svg
                  className="w-5 h-5 text-yellow-600 dark:text-yellow-400 mt-0.5 flex-shrink-0"
                  fill="currentColor"
                  viewBox="0 0 20 20"
                >
                  <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                </svg>
                <div className="ml-3">
                  <h4 className="font-medium text-yellow-800 dark:text-yellow-200">
                    Disclaimer
                  </h4>
                  <p className="text-yellow-700 dark:text-yellow-300 text-sm mt-1">
                    Past performance is not indicative of future results. Trading carries
                    substantial risk of loss. Always trade responsibly and use proper
                    risk management.
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </Gated>
  );
}

/**
 * Metric card component for displaying KPIs
 */
interface MetricCardProps {
  label: string;
  value: string;
  change?: "up" | "down" | "neutral";
  icon?: string;
}

const MetricCard: React.FC<MetricCardProps> = ({
  label,
  value,
  change = "neutral",
  icon,
}) => {
  const changeColor = {
    up: "text-green-600 dark:text-green-400 bg-green-50 dark:bg-green-900/20",
    down: "text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20",
    neutral: "text-gray-600 dark:text-gray-400 bg-gray-50 dark:bg-gray-700/50",
  };

  return (
    <div className={`rounded-lg p-4 ${changeColor[change]} transition-all duration-200`}>
      <div className="flex items-start justify-between mb-2">
        <h4 className="text-sm font-medium text-gray-600 dark:text-gray-300">
          {label}
        </h4>
        {icon && <span className="text-xl">{icon}</span>}
      </div>
      <p className="text-2xl font-bold text-gray-900 dark:text-white">{value}</p>
    </div>
  );
};
