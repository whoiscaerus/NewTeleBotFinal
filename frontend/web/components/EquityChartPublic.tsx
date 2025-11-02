"use client";

import React, { useState, useEffect } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";

interface EquityDataPoint {
  date: string;
  equity: number;
  returns_percent: number;
}

interface EquityChartData {
  points: EquityDataPoint[];
  final_equity: number;
  delay_applied_minutes: number;
  data_as_of: string;
}

/**
 * EquityChartPublic Component
 *
 * Displays equity curve with interactive tooltips using Recharts.
 * - Loads data from /api/v1/public/performance/equity
 * - Shows historical equity progression
 * - Day-level granularity only (no intra-day data leak)
 * - Interactive tooltips on hover
 * - Loading and error states
 *
 * @example
 * <EquityChartPublic />
 *
 * @returns React component with equity chart
 */
export function EquityChartPublic(): React.ReactNode {
  const [data, setData] = useState<EquityDataPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [finalEquity, setFinalEquity] = useState<number>(10000);

  useEffect(() => {
    const fetchEquityData = async () => {
      try {
        setLoading(true);
        setError(null);

        // Fetch equity curve from public API
        const response = await fetch(
          "/api/v1/public/performance/equity?delay_minutes=1440"
        );

        if (!response.ok) {
          throw new Error(`API error: ${response.statusText}`);
        }

        const result: EquityChartData = await response.json();

        // Transform data for chart
        const chartData = result.points.map((point) => ({
          date: new Date(point.date).toLocaleDateString("en-GB"),
          equity: Number(point.equity.toFixed(2)),
          returns_percent: point.returns_percent,
        }));

        setData(chartData);
        setFinalEquity(result.final_equity);
      } catch (err) {
        const message = err instanceof Error ? err.message : "Failed to load equity data";
        setError(message);
        console.error("Equity data fetch error:", err);

        // Return empty data on error (graceful degradation)
        setData([]);
        setFinalEquity(10000);
      } finally {
        setLoading(false);
      }
    };

    fetchEquityData();
  }, []);

  // Loading State
  if (loading) {
    return (
      <div className="w-full h-80 flex items-center justify-center bg-slate-700/50 rounded-lg">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-400 mx-auto mb-4"></div>
          <p className="text-slate-300">Loading equity curve...</p>
        </div>
      </div>
    );
  }

  // Error State
  if (error) {
    return (
      <div className="w-full h-80 flex items-center justify-center bg-red-900/20 rounded-lg border border-red-700">
        <div className="text-center">
          <p className="text-red-300 mb-2">⚠️ Unable to load equity data</p>
          <p className="text-sm text-red-400">{error}</p>
        </div>
      </div>
    );
  }

  // Empty State
  if (!data || data.length === 0) {
    return (
      <div className="w-full h-80 flex items-center justify-center bg-slate-700/50 rounded-lg">
        <div className="text-center">
          <p className="text-slate-400">No closed trades available yet</p>
          <p className="text-sm text-slate-500 mt-1">
            Equity curve will appear after your first closed trade
          </p>
        </div>
      </div>
    );
  }

  // Custom Tooltip
  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      const point = payload[0].payload;
      return (
        <div className="bg-slate-800 border border-slate-600 rounded p-3 shadow-lg">
          <p className="text-slate-300 text-sm">
            <span className="font-semibold">{point.date}</span>
          </p>
          <p className="text-cyan-400 text-sm">
            Equity: £{point.equity.toLocaleString("en-GB", {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
            })}
          </p>
          <p className={`text-sm ${point.returns_percent >= 0 ? "text-green-400" : "text-red-400"}`}>
            Return: {point.returns_percent.toFixed(2)}%
          </p>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="w-full">
      {/* Chart Stats */}
      <div className="mb-4 grid grid-cols-2 gap-4">
        <div className="bg-slate-700/50 rounded p-3 border border-slate-600">
          <p className="text-slate-400 text-sm">Current Equity</p>
          <p className="text-2xl font-bold text-cyan-400">
            £{finalEquity.toLocaleString("en-GB", {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
            })}
          </p>
        </div>
        <div className="bg-slate-700/50 rounded p-3 border border-slate-600">
          <p className="text-slate-400 text-sm">Total Trades</p>
          <p className="text-2xl font-bold text-blue-400">{data.length}</p>
        </div>
      </div>

      {/* Chart Container */}
      <div className="w-full h-96 bg-slate-900/50 rounded-lg p-4 border border-slate-700">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart
            data={data}
            margin={{ top: 5, right: 30, left: 0, bottom: 5 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#475569" />
            <XAxis
              dataKey="date"
              stroke="#94a3b8"
              style={{ fontSize: "12px" }}
              tick={{ fill: "#cbd5e1" }}
            />
            <YAxis
              stroke="#94a3b8"
              style={{ fontSize: "12px" }}
              tick={{ fill: "#cbd5e1" }}
              tickFormatter={(value) =>
                `£${(value / 1000).toFixed(0)}k`
              }
            />
            <Tooltip content={<CustomTooltip />} />
            <Legend
              wrapperStyle={{ paddingTop: "20px" }}
              iconType="line"
            />
            <Line
              type="monotone"
              dataKey="equity"
              stroke="#06b6d4"
              dot={false}
              strokeWidth={2}
              isAnimationActive={false}
              name="Equity (£)"
              yAxisId="left"
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Chart Info */}
      <div className="mt-4 text-xs text-slate-400">
        <p>
          📊 Chart displays daily closing equity. Data delayed 24+ hours for safety.
          Each point represents equity after all trades closed that day.
        </p>
      </div>
    </div>
  );
}
