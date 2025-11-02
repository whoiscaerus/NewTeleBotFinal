"use client";

import React from "react";

interface HeatmapProps {
  data: any[];
  type: "hour" | "dow" | "month";
  title: string;
}

/**
 * Component: Heatmap
 *
 * Visualizes trade performance data in heatmap format.
 * Shows win rates or PnL across different time periods.
 *
 * @example
 * <Heatmap data={hourBuckets} type="hour" title="Hour of Day" />
 */
export const Heatmap: React.FC<HeatmapProps> = ({ data, type, title }) => {
  if (!data || data.length === 0) {
    return <div className="text-gray-500 text-center py-8">No data available</div>;
  }

  // Determine color based on win rate
  const getColor = (winRate: number) => {
    if (winRate === 0) return "bg-gray-100 dark:bg-gray-700";
    if (winRate < 30) return "bg-red-200 dark:bg-red-900";
    if (winRate < 50) return "bg-orange-200 dark:bg-orange-900";
    if (winRate < 70) return "bg-yellow-200 dark:bg-yellow-900";
    return "bg-green-200 dark:bg-green-900";
  };

  // Hour heatmap: 24-hour grid (4 rows x 6 columns)
  if (type === "hour") {
    return (
      <div>
        <h3 className="text-sm font-semibold mb-4 text-gray-700 dark:text-gray-300">
          {title}
        </h3>
        <div className="grid grid-cols-6 gap-1">
          {data.map((bucket) => (
            <div
              key={bucket.hour}
              className={`p-3 rounded text-center cursor-pointer hover:opacity-80 transition ${getColor(
                bucket.win_rate_percent
              )}`}
              title={`Hour ${bucket.hour}: ${bucket.win_rate_percent?.toFixed(1)}% win rate (${bucket.num_trades} trades)`}
            >
              <div className="text-xs font-semibold">{bucket.hour}:00</div>
              <div className="text-xs mt-1">{bucket.win_rate_percent?.toFixed(0)}%</div>
              <div className="text-xs text-gray-600 dark:text-gray-400">
                ({bucket.num_trades})
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  // Day of week heatmap: 7-day grid
  if (type === "dow") {
    return (
      <div>
        <h3 className="text-sm font-semibold mb-4 text-gray-700 dark:text-gray-300">
          {title}
        </h3>
        <div className="grid grid-cols-7 gap-2">
          {data.map((bucket) => (
            <div
              key={bucket.day_of_week}
              className={`p-3 rounded text-center cursor-pointer hover:opacity-80 transition ${getColor(
                bucket.win_rate_percent
              )}`}
              title={`${bucket.day_name}: ${bucket.win_rate_percent?.toFixed(1)}% win rate (${bucket.num_trades} trades)`}
            >
              <div className="text-xs font-semibold">{bucket.day_name}</div>
              <div className="text-xs mt-1">{bucket.win_rate_percent?.toFixed(0)}%</div>
              <div className="text-xs text-gray-600 dark:text-gray-400">
                ({bucket.num_trades})
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  // Month heatmap: 12-month grid (3 rows x 4 columns)
  if (type === "month") {
    return (
      <div>
        <h3 className="text-sm font-semibold mb-4 text-gray-700 dark:text-gray-300">
          {title}
        </h3>
        <div className="grid grid-cols-4 gap-2">
          {data.map((bucket) => (
            <div
              key={bucket.month}
              className={`p-3 rounded text-center cursor-pointer hover:opacity-80 transition ${getColor(
                bucket.win_rate_percent
              )}`}
              title={`${bucket.month_name}: ${bucket.win_rate_percent?.toFixed(1)}% win rate (${bucket.num_trades} trades)`}
            >
              <div className="text-xs font-semibold">{bucket.month_name}</div>
              <div className="text-xs mt-1">{bucket.win_rate_percent?.toFixed(0)}%</div>
              <div className="text-xs text-gray-600 dark:text-gray-400">
                ({bucket.num_trades})
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return null;
};
