"use client";

import React, { useState, useEffect } from "react";
import { EquityChartComponent } from "@/components/EquityChart";
import { Heatmap } from "@/components/Heatmap";
import { getEquityCurve, getHourBuckets, getDowBuckets, getMonthBuckets } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { logger } from "@/lib/logger";

/**
 * Page: Analytics Dashboard
 *
 * Displays:
 * - Equity curve chart
 * - Hour-of-day performance heatmap
 * - Day-of-week performance heatmap
 * - Month performance heatmap
 * - Key metrics summary
 */
export default function AnalyticsPage() {
  const { user } = useAuth();

  // State
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [equityData, setEquityData] = useState<any>(null);
  const [hourBuckets, setHourBuckets] = useState<any[]>([]);
  const [dowBuckets, setDowBuckets] = useState<any[]>([]);
  const [monthBuckets, setMonthBuckets] = useState<any[]>([]);
  const [dateRange, setDateRange] = useState({ start: null, end: null });

  // Load all analytics data
  useEffect(() => {
    loadAnalyticsData();
  }, []);

  const loadAnalyticsData = async () => {
    try {
      setLoading(true);
      setError(null);

      logger.info("Loading analytics data");

      // Determine date range (last 90 days)
      const end = new Date();
      const start = new Date(end.getTime() - 90 * 24 * 60 * 60 * 1000);

      setDateRange({
        start: start.toISOString().split("T")[0],
        end: end.toISOString().split("T")[0],
      });

      // Load all data in parallel
      const [equity, hours, dows, months] = await Promise.all([
        getEquityCurve({
          start_date: start.toISOString().split("T")[0],
          end_date: end.toISOString().split("T")[0],
        }).catch((err) => {
          logger.error("Failed to load equity data", { error: err });
          return null;
        }),
        getHourBuckets({
          start_date: start.toISOString().split("T")[0],
          end_date: end.toISOString().split("T")[0],
        }).catch((err) => {
          logger.error("Failed to load hour buckets", { error: err });
          return [];
        }),
        getDowBuckets({
          start_date: start.toISOString().split("T")[0],
          end_date: end.toISOString().split("T")[0],
        }).catch((err) => {
          logger.error("Failed to load day-of-week buckets", { error: err });
          return [];
        }),
        getMonthBuckets({
          start_date: start.toISOString().split("T")[0],
          end_date: end.toISOString().split("T")[0],
        }).catch((err) => {
          logger.error("Failed to load month buckets", { error: err });
          return [];
        }),
      ]);

      setEquityData(equity);
      setHourBuckets(hours);
      setDowBuckets(dows);
      setMonthBuckets(months);

      logger.info("Analytics data loaded successfully", {
        equity_points: equity?.points?.length || 0,
        hour_buckets: hours?.length || 0,
        dow_buckets: dows?.length || 0,
        month_buckets: months?.length || 0,
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load analytics";
      setError(message);
      logger.error("Error loading analytics", { error: err });
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-gray-500">Loading analytics...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-red-500 text-center">
          <p className="text-lg font-semibold">Error loading analytics</p>
          <p className="text-sm">{error}</p>
          <button
            onClick={loadAnalyticsData}
            className="mt-4 px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
          >
            Try Again
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8 p-4 md:p-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold">Analytics</h1>
        <p className="text-gray-500 mt-2">
          Performance analysis from {dateRange.start} to {dateRange.end}
        </p>
      </div>

      {/* Summary Stats */}
      {equityData && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-white dark:bg-gray-800 rounded-lg p-4">
            <p className="text-gray-600 dark:text-gray-400 text-sm">Total Return</p>
            <p
              className={`text-2xl font-bold ${
                equityData.total_return_percent >= 0 ? "text-green-500" : "text-red-500"
              }`}
            >
              {equityData.total_return_percent?.toFixed(2)}%
            </p>
          </div>

          <div className="bg-white dark:bg-gray-800 rounded-lg p-4">
            <p className="text-gray-600 dark:text-gray-400 text-sm">Max Drawdown</p>
            <p className="text-2xl font-bold text-red-500">
              {equityData.max_drawdown_percent?.toFixed(2)}%
            </p>
          </div>

          <div className="bg-white dark:bg-gray-800 rounded-lg p-4">
            <p className="text-gray-600 dark:text-gray-400 text-sm">Days</p>
            <p className="text-2xl font-bold">{equityData.days_in_period}</p>
          </div>

          <div className="bg-white dark:bg-gray-800 rounded-lg p-4">
            <p className="text-gray-600 dark:text-gray-400 text-sm">Final Equity</p>
            <p className="text-2xl font-bold">£{equityData.final_equity?.toLocaleString()}</p>
          </div>
        </div>
      )}

      {/* Equity Curve Chart */}
      {equityData && equityData.points && equityData.points.length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-lg p-6">
          <h2 className="text-xl font-semibold mb-4">Equity Curve</h2>
          <EquityChartComponent data={equityData.points} />
        </div>
      )}

      {/* Heatmaps */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Hour of Day Heatmap */}
        {hourBuckets && hourBuckets.length > 0 && (
          <div className="bg-white dark:bg-gray-800 rounded-lg p-6">
            <h2 className="text-xl font-semibold mb-4">Hour of Day Performance</h2>
            <Heatmap
              data={hourBuckets}
              type="hour"
              title="Win Rate by Hour (0-23)"
            />
          </div>
        )}

        {/* Day of Week Heatmap */}
        {dowBuckets && dowBuckets.length > 0 && (
          <div className="bg-white dark:bg-gray-800 rounded-lg p-6">
            <h2 className="text-xl font-semibold mb-4">Day of Week Performance</h2>
            <Heatmap
              data={dowBuckets}
              type="dow"
              title="Win Rate by Day"
            />
          </div>
        )}
      </div>

      {/* Month Heatmap */}
      {monthBuckets && monthBuckets.length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-lg p-6">
          <h2 className="text-xl font-semibold mb-4">Monthly Performance</h2>
          <Heatmap
            data={monthBuckets}
            type="month"
            title="Win Rate by Month"
          />
        </div>
      )}

      {/* Empty State */}
      {(!equityData || !equityData.points || equityData.points.length === 0) && (
        <div className="text-center text-gray-500 py-12">
          <p>No trading data available for the selected period.</p>
        </div>
      )}
    </div>
  );
}
