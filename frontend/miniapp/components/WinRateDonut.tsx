"use client";

import React from "react";

interface WinRateDonutProps {
  title?: string;
  winRate: number;
  totalTrades: number;
  winningTrades: number;
  losingTrades: number;
}

/**
 * Component: WinRateDonut
 *
 * Displays win rate as a donut chart with win/loss breakdown.
 * Shows percentage and trade counts.
 *
 * @example
 * <WinRateDonut winRate={65} totalTrades={100} winningTrades={65} losingTrades={35} />
 */
export const WinRateDonut: React.FC<WinRateDonutProps> = ({
  title = "Win Rate",
  winRate,
  totalTrades,
  winningTrades,
  losingTrades,
}) => {
  const circumference = 2 * Math.PI * 45; // radius = 45
  const winOffset = circumference * (1 - winRate / 100);

  return (
    <div className="flex flex-col items-center justify-center">
      <h3 className="text-lg font-semibold mb-4 text-gray-800 dark:text-gray-200">
        {title}
      </h3>

      {/* Donut Chart using SVG */}
      <div className="relative w-32 h-32 mb-4">
        <svg viewBox="0 0 100 100" className="w-full h-full">
          {/* Background circle */}
          <circle
            cx="50"
            cy="50"
            r="45"
            fill="none"
            stroke="#e5e7eb"
            strokeWidth="12"
            className="dark:stroke-gray-700"
          />

          {/* Win rate arc (green) */}
          <circle
            cx="50"
            cy="50"
            r="45"
            fill="none"
            stroke="#10b981"
            strokeWidth="12"
            strokeDasharray={`${circumference * (winRate / 100)} ${circumference}`}
            strokeLinecap="round"
            className="transform -rotate-90 origin-center"
          />

          {/* Center text */}
          <text
            x="50"
            y="45"
            textAnchor="middle"
            className="text-2xl font-bold fill-gray-800 dark:fill-gray-200"
            fontSize="20"
          >
            {winRate.toFixed(1)}%
          </text>
          <text
            x="50"
            y="60"
            textAnchor="middle"
            className="text-xs fill-gray-600 dark:fill-gray-400"
            fontSize="10"
          >
            {totalTrades} trades
          </text>
        </svg>
      </div>

      {/* Legend */}
      <div className="grid grid-cols-2 gap-4 w-full">
        <div className="bg-green-50 dark:bg-green-900/20 rounded p-3">
          <p className="text-xs text-gray-600 dark:text-gray-400">Winning</p>
          <p className="text-lg font-bold text-green-600 dark:text-green-400">
            {winningTrades}
          </p>
        </div>
        <div className="bg-red-50 dark:bg-red-900/20 rounded p-3">
          <p className="text-xs text-gray-600 dark:text-gray-400">Losing</p>
          <p className="text-lg font-bold text-red-600 dark:text-red-400">
            {losingTrades}
          </p>
        </div>
      </div>
    </div>
  );
};

export default WinRateDonut;
