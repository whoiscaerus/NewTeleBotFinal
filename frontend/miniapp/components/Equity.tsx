"use client";

import React from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

interface EquityPoint {
  date: string;
  equity: number;
  cumulative_pnl: number;
  drawdown_percent: number;
}

interface EquityProps {
  data: EquityPoint[];
  title?: string;
}

/**
 * Component: Equity Chart
 *
 * Displays equity curve with event markers and drawdown overlay.
 * Shows cumulative profit/loss over time.
 *
 * @example
 * <Equity data={equityPoints} title="Account Equity" />
 */
export const Equity: React.FC<EquityProps> = ({ data, title = "Equity Curve" }) => {
  if (!data || data.length === 0) {
    return (
      <div className="text-center text-gray-500 py-8">
        No equity data available
      </div>
    );
  }

  // Format data for chart
  const chartData = data.map((point) => ({
    date: new Date(point.date).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
    }),
    equity: Math.round(point.equity),
    pnl: Math.round(point.cumulative_pnl),
    dd: Math.abs(Math.round(point.drawdown_percent * 100) / 100),
  }));

  // Calculate min/max for better Y-axis scaling
  const equities = chartData.map((d) => d.equity);
  const minEquity = Math.min(...equities);
  const maxEquity = Math.max(...equities);
  const range = maxEquity - minEquity;
  const padding = range * 0.1;

  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload;
      return (
        <div className="bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded p-3 shadow-lg">
          <p className="text-xs font-semibold text-gray-700 dark:text-gray-300">
            {data.date}
          </p>
          <p className="text-sm text-blue-600 dark:text-blue-400">
            Equity: £{data.equity.toLocaleString()}
          </p>
          <p
            className={`text-sm ${
              data.pnl >= 0 ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"
            }`}
          >
            PnL: £{data.pnl.toLocaleString()}
          </p>
          <p className="text-sm text-red-600 dark:text-red-400">
            Drawdown: {data.dd}%
          </p>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="w-full h-full">
      <h3 className="text-lg font-semibold mb-4 text-gray-800 dark:text-gray-200">
        {title}
      </h3>
      <ResponsiveContainer width="100%" height={300}>
        <LineChart
          data={chartData}
          margin={{ top: 5, right: 30, left: 0, bottom: 5 }}
        >
          <CartesianGrid
            strokeDasharray="3 3"
            stroke="#e5e7eb"
            className="dark:stroke-gray-700"
          />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 12 }}
            className="text-gray-600 dark:text-gray-400"
          />
          <YAxis
            domain={[minEquity - padding, maxEquity + padding]}
            tick={{ fontSize: 12 }}
            className="text-gray-600 dark:text-gray-400"
          />
          <Tooltip content={<CustomTooltip />} />
          <Legend />
          <Line
            type="monotone"
            dataKey="equity"
            stroke="#3b82f6"
            dot={false}
            isAnimationActive={false}
            name="Equity (£)"
            strokeWidth={2}
          />
          <Line
            type="monotone"
            dataKey="pnl"
            stroke="#10b981"
            dot={false}
            isAnimationActive={false}
            name="Cumulative PnL (£)"
            strokeWidth={2}
            strokeDasharray="5 5"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
};

export default Equity;
