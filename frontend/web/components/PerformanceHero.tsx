"use client";

import React from "react";

interface PerformanceHeroProps {
  totalTrades?: number;
  winRate?: number;
  profitFactor?: number;
}

/**
 * PerformanceHero Component
 *
 * Hero section with headline, key metrics, and CTA button.
 * Displays headline + primary metric + call-to-action.
 *
 * @param totalTrades - Number of closed trades (optional)
 * @param winRate - Win rate as decimal (optional, e.g., 0.6573)
 * @param profitFactor - Profit factor (optional, e.g., 2.15)
 *
 * @example
 * <PerformanceHero totalTrades={143} winRate={0.6573} profitFactor={2.15} />
 *
 * @returns React component
 */
export function PerformanceHero({
  totalTrades = 143,
  winRate = 0.6573,
  profitFactor = 2.15,
}: PerformanceHeroProps): React.ReactNode {
  const winRatePercent = (winRate * 100).toFixed(1);

  return (
    <div className="text-center">
      {/* Main Headline */}
      <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold text-white mb-4 leading-tight">
        Proven Trading
        <span className="bg-gradient-to-r from-blue-400 to-cyan-400 bg-clip-text text-transparent">
          {" "}
          Excellence
        </span>
      </h1>

      {/* Subheading with Key Metrics */}
      <div className="mt-6 mb-8">
        <p className="text-xl sm:text-2xl text-slate-300 mb-4">
          {totalTrades} Closed Trades • {winRatePercent}% Win Rate • {profitFactor}x Profit Factor
        </p>
        <p className="text-lg text-slate-400">
          Real results. Transparent metrics. 24+ hour delay for safety.
        </p>
      </div>

      {/* Key Stats Row */}
      <div className="grid grid-cols-3 gap-4 max-w-md mx-auto mb-8">
        <div className="bg-slate-700/50 rounded-lg p-3 border border-slate-600">
          <p className="text-sm text-slate-400">Closed Trades</p>
          <p className="text-2xl font-bold text-blue-400">{totalTrades}</p>
        </div>
        <div className="bg-slate-700/50 rounded-lg p-3 border border-slate-600">
          <p className="text-sm text-slate-400">Win Rate</p>
          <p className="text-2xl font-bold text-green-400">{winRatePercent}%</p>
        </div>
        <div className="bg-slate-700/50 rounded-lg p-3 border border-slate-600">
          <p className="text-sm text-slate-400">Profit Factor</p>
          <p className="text-2xl font-bold text-cyan-400">{profitFactor}x</p>
        </div>
      </div>

      {/* CTA Buttons */}
      <div className="flex flex-col sm:flex-row gap-4 justify-center">
        <button className="px-8 py-3 bg-blue-600 hover:bg-blue-700 text-white font-semibold rounded-lg transition transform hover:scale-105">
          View Pricing
        </button>
        <button className="px-8 py-3 bg-slate-700 hover:bg-slate-600 text-white font-semibold rounded-lg border border-slate-600 transition">
          View Documentation
        </button>
      </div>

      {/* Trust Badge */}
      <p className="mt-6 text-sm text-slate-400">
        ✓ Verified Results • ✓ Delayed Data • ✓ No Forward Guidance
      </p>
    </div>
  );
}
