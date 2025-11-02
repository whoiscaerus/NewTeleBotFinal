"use client";

import React from "react";

interface TradeDistributionData {
  instrument: string;
  num_trades: number;
  winning_trades: number;
  total_pnl: number;
  win_rate_percent: number;
}

interface DistributionProps {
  data: TradeDistributionData[];
  title?: string;
}

/**
 * Component: Distribution
 *
 * Displays trade distribution and performance by instrument.
 * Shows counts, win rates, and P&L per instrument.
 *
 * @example
 * <Distribution data={tradesByInstrument} title="Trades by Instrument" />
 */
export const Distribution: React.FC<DistributionProps> = ({
  data,
  title = "Trade Distribution by Instrument",
}) => {
  if (!data || data.length === 0) {
    return (
      <div className="text-center text-gray-500 py-8">
        No distribution data available
      </div>
    );
  }

  // Sort by number of trades (descending)
  const sorted = [...data].sort((a, b) => b.num_trades - a.num_trades);

  // Get max trades for bar width scaling
  const maxTrades = Math.max(...sorted.map((d) => d.num_trades));

  // Get color based on win rate
  const getWinRateColor = (winRate: number) => {
    if (winRate < 40) return "text-red-600 dark:text-red-400";
    if (winRate < 50) return "text-orange-600 dark:text-orange-400";
    if (winRate < 60) return "text-yellow-600 dark:text-yellow-400";
    return "text-green-600 dark:text-green-400";
  };

  const getBarColor = (winRate: number) => {
    if (winRate < 40) return "bg-red-500";
    if (winRate < 50) return "bg-orange-500";
    if (winRate < 60) return "bg-yellow-500";
    return "bg-green-500";
  };

  return (
    <div className="w-full">
      <h3 className="text-lg font-semibold mb-4 text-gray-800 dark:text-gray-200">
        {title}
      </h3>

      <div className="space-y-4">
        {sorted.map((item) => {
          const barWidth = (item.num_trades / maxTrades) * 100;
          const pnlColor = item.total_pnl >= 0 ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400";

          return (
            <div
              key={item.instrument}
              className="bg-white dark:bg-gray-800 rounded-lg p-4 hover:shadow-md transition"
            >
              {/* Header row */}
              <div className="flex justify-between items-start mb-2">
                <div className="flex-1">
                  <p className="font-semibold text-gray-800 dark:text-gray-200">
                    {item.instrument}
                  </p>
                  <p className="text-xs text-gray-600 dark:text-gray-400">
                    {item.num_trades} trades
                  </p>
                </div>
                <div className="text-right">
                  <p className={`font-bold text-sm ${pnlColor}`}>
                    £{item.total_pnl.toLocaleString(undefined, {
                      maximumFractionDigits: 2,
                    })}
                  </p>
                  <p
                    className={`text-xs font-semibold ${getWinRateColor(
                      item.win_rate_percent
                    )}`}
                  >
                    {item.win_rate_percent.toFixed(1)}% win
                  </p>
                </div>
              </div>

              {/* Progress bar */}
              <div className="flex items-center gap-2">
                <div className="flex-1 bg-gray-200 dark:bg-gray-700 rounded-full h-2 overflow-hidden">
                  <div
                    className={`h-full ${getBarColor(item.win_rate_percent)} transition-all`}
                    style={{ width: `${barWidth}%` }}
                  />
                </div>
                <span className="text-xs font-semibold text-gray-600 dark:text-gray-400 whitespace-nowrap">
                  {item.winning_trades}/{item.num_trades}
                </span>
              </div>

              {/* Stats row */}
              <div className="grid grid-cols-3 gap-2 mt-3 text-xs">
                <div className="bg-gray-100 dark:bg-gray-700 rounded px-2 py-1">
                  <p className="text-gray-600 dark:text-gray-400">Avg P&L</p>
                  <p className="font-semibold text-gray-800 dark:text-gray-200">
                    £{(item.total_pnl / item.num_trades).toFixed(2)}
                  </p>
                </div>
                <div className="bg-gray-100 dark:bg-gray-700 rounded px-2 py-1">
                  <p className="text-gray-600 dark:text-gray-400">Winners</p>
                  <p className="font-semibold text-green-600 dark:text-green-400">
                    {item.winning_trades}
                  </p>
                </div>
                <div className="bg-gray-100 dark:bg-gray-700 rounded px-2 py-1">
                  <p className="text-gray-600 dark:text-gray-400">Losers</p>
                  <p className="font-semibold text-red-600 dark:text-red-400">
                    {item.num_trades - item.winning_trades}
                  </p>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Summary footer */}
      <div className="mt-6 p-4 bg-gray-100 dark:bg-gray-800 rounded-lg">
        <div className="grid grid-cols-3 gap-4 text-center">
          <div>
            <p className="text-xs text-gray-600 dark:text-gray-400">Total Trades</p>
            <p className="text-xl font-bold text-gray-800 dark:text-gray-200">
              {sorted.reduce((sum, d) => sum + d.num_trades, 0)}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-600 dark:text-gray-400">Instruments</p>
            <p className="text-xl font-bold text-gray-800 dark:text-gray-200">
              {sorted.length}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-600 dark:text-gray-400">Avg Win Rate</p>
            <p className="text-xl font-bold text-gray-800 dark:text-gray-200">
              {(
                sorted.reduce((sum, d) => sum + d.win_rate_percent, 0) /
                sorted.length
              ).toFixed(1)}
              %
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Distribution;
