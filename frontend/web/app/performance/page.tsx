"use client";

import React from "react";
import Head from "next/head";
import { PerformanceHero } from "@/components/PerformanceHero";
import { EquityChartPublic } from "@/components/EquityChartPublic";
import { StatsTiles } from "@/components/StatsTiles";

/**
 * Public Performance Page
 *
 * SEO-friendly page displaying aggregated trading performance metrics.
 * Strong disclaimers and transparency-focused copy.
 *
 * Data Rules:
 * - Only closed trades, T+X delay enforced
 * - No PII leak (no user IDs, names, entry prices, SL/TP)
 * - Aggregated metrics only
 * - Day-level granularity for equity curve
 *
 * @example
 * Load: /performance
 * Expected: Hero + Chart + Stats + Disclaimers visible
 *
 * @returns React component for public performance page
 */
export default function PerformancePage(): React.ReactNode {
  const disclaimer = `Past performance is not indicative of future results. This data is provided for informational purposes only and should not be used as investment advice. Trading involves substantial risk of loss. Past results should not be considered as an indication of future success. The methodology and timeframe used to calculate returns may differ from your experience.`;

  const disclaimerTwo = `We do not make predictions or claims about future performance. All data is delayed by at least 24 hours after trade close for safety and verification. Results shown are from closed trades only.`;

  return (
    <>
      <Head>
        <title>Trading Performance | TeleBot - Proven Results, Verified Data</title>
        <meta
          name="description"
          content="Live trading performance metrics with verified results and 24+ hour delay. See win rates, Sharpe ratios, and equity curves for transparent, auditable trading."
        />
        <meta property="og:title" content="Trading Performance | TeleBot" />
        <meta
          property="og:description"
          content="Verified trading performance with transparent metrics and delayed data."
        />
        <meta property="og:type" content="website" />
        <meta
          name="keywords"
          content="trading performance, verified results, win rate, profit factor, equity curve"
        />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </Head>

      <main className="min-h-screen bg-gradient-to-b from-slate-900 via-slate-800 to-slate-900">
        {/* Hero Section */}
        <section className="pt-16 pb-12 px-4 sm:px-6 lg:px-8">
          <PerformanceHero />
        </section>

        {/* Performance Stats Section */}
        <section className="py-12 px-4 sm:px-6 lg:px-8 bg-slate-800/50">
          <div className="max-w-6xl mx-auto">
            <h2 className="text-2xl sm:text-3xl font-bold text-white mb-2 text-center">
              Performance Metrics
            </h2>
            <p className="text-slate-300 text-center mb-8">
              Aggregated statistics from closed trades (24h+ delay)
            </p>
            <StatsTiles />
          </div>
        </section>

        {/* Equity Curve Section */}
        <section className="py-12 px-4 sm:px-6 lg:px-8">
          <div className="max-w-6xl mx-auto">
            <h2 className="text-2xl sm:text-3xl font-bold text-white mb-2 text-center">
              Equity Curve
            </h2>
            <p className="text-slate-300 text-center mb-8">
              Daily closing equity over time (no intra-day data)
            </p>
            <div className="bg-slate-800 rounded-lg border border-slate-700 p-6">
              <EquityChartPublic />
            </div>
          </div>
        </section>

        {/* Disclaimers Section */}
        <section className="py-16 px-4 sm:px-6 lg:px-8 bg-slate-800/50">
          <div className="max-w-4xl mx-auto">
            <h2 className="text-2xl font-bold text-white mb-6 text-center">
              Important Disclaimers
            </h2>

            <div className="space-y-6">
              {/* Disclaimer 1: Past Performance */}
              <div className="bg-red-900/20 border border-red-700 rounded-lg p-4">
                <p className="text-red-100 text-sm sm:text-base">{disclaimer}</p>
              </div>

              {/* Disclaimer 2: No Forward Guidance */}
              <div className="bg-amber-900/20 border border-amber-700 rounded-lg p-4">
                <p className="text-amber-100 text-sm sm:text-base">{disclaimerTwo}</p>
              </div>

              {/* Disclaimer 3: Data Accuracy */}
              <div className="bg-blue-900/20 border border-blue-700 rounded-lg p-4">
                <p className="text-blue-100 text-sm sm:text-base">
                  This data is automatically calculated from closed trades. While we take care
                  to ensure accuracy, we make no warranties regarding completeness or
                  correctness. Always verify important decisions independently.
                </p>
              </div>

              {/* Disclaimer 4: Risk */}
              <div className="bg-orange-900/20 border border-orange-700 rounded-lg p-4">
                <p className="text-orange-100 text-sm sm:text-base">
                  Trading and investing involve substantial risk of loss. Your capital is at
                  risk. Only invest money you can afford to lose completely. Consider consulting
                  a financial advisor before making investment decisions.
                </p>
              </div>
            </div>

            {/* Footer CTA */}
            <div className="mt-8 text-center">
              <p className="text-slate-300 mb-4">
                Ready to explore our trading platform?
              </p>
              <button className="px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white font-semibold rounded-lg transition">
                Get Started
              </button>
            </div>
          </div>
        </section>
      </main>
    </>
  );
}
