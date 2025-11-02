"use client";

import React, { useState, useEffect } from "react";
import { useAuth } from "@/lib/auth";
import { logger } from "@/lib/logger";

interface RevenueSummary {
  date: string;
  mrr_gbp: number;
  arr_gbp: number;
  active_subscribers: number;
  annual_plan_subscribers: number;
  monthly_plan_subscribers: number;
  churn_rate_percent: number;
  arpu_gbp: number;
}

interface Cohort {
  cohort_month: string;
  initial_subscribers: number;
  retention_data: Record<string, number>;
  churn_rates: Record<string, number>;
  total_revenue_gbp: number;
  average_lifetime_value_gbp: number;
}

/**
 * Page: Admin Revenue Dashboard
 *
 * Shows:
 * - MRR, ARR, churn, ARPU
 * - Cohort retention analysis
 * - Historical revenue trends
 */
export default function RevenuePage() {
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<RevenueSummary | null>(null);
  const [cohorts, setCohorts] = useState<Cohort[]>([]);
  const [monthsBack, setMonthsBack] = useState(12);

  useEffect(() => {
    loadRevenueData();
  }, [monthsBack]);

  const loadRevenueData = async () => {
    try {
      setLoading(true);
      setError(null);

      logger.info("Loading revenue data");

      // Get summary
      const summaryResponse = await fetch("/api/v1/revenue/summary", {
        headers: {
          Authorization: `Bearer ${localStorage.getItem("jwt_token")}`,
        },
      });

      if (!summaryResponse.ok) {
        throw new Error("Failed to load revenue summary");
      }

      const summaryData = await summaryResponse.json();
      setSummary(summaryData);

      // Get cohorts
      const cohortsResponse = await fetch(
        `/api/v1/revenue/cohorts?months_back=${monthsBack}`,
        {
          headers: {
            Authorization: `Bearer ${localStorage.getItem("jwt_token")}`,
          },
        }
      );

      if (cohortsResponse.ok) {
        const cohortsData = await cohortsResponse.json();
        setCohorts(cohortsData);
      }

      logger.info("Revenue data loaded");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load revenue data";
      setError(message);
      logger.error("Error loading revenue", { error: err });
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-gray-500">Loading revenue dashboard...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-red-500 text-center">
          <p>{error}</p>
          <button
            onClick={loadRevenueData}
            className="mt-4 px-4 py-2 bg-blue-500 text-white rounded"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8 p-6">
      {/* Header */}
      <div>
        <h1 className="text-4xl font-bold">Revenue Dashboard</h1>
        <p className="text-gray-600 mt-2">Business metrics and KPIs</p>
      </div>

      {/* Key Metrics */}
      {summary && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {/* MRR */}
          <div className="bg-white rounded-lg shadow p-6">
            <p className="text-gray-600 text-sm">Monthly Recurring Revenue</p>
            <p className="text-3xl font-bold text-blue-600">
              £{summary.mrr_gbp.toLocaleString(undefined, { maximumFractionDigits: 2 })}
            </p>
            <p className="text-xs text-gray-500 mt-1">As of {summary.date}</p>
          </div>

          {/* ARR */}
          <div className="bg-white rounded-lg shadow p-6">
            <p className="text-gray-600 text-sm">Annual Recurring Revenue</p>
            <p className="text-3xl font-bold text-green-600">
              £{summary.arr_gbp.toLocaleString(undefined, { maximumFractionDigits: 2 })}
            </p>
            <p className="text-xs text-gray-500 mt-1">MRR × 12</p>
          </div>

          {/* ARPU */}
          <div className="bg-white rounded-lg shadow p-6">
            <p className="text-gray-600 text-sm">Average Revenue Per User</p>
            <p className="text-3xl font-bold text-purple-600">
              £{summary.arpu_gbp.toLocaleString(undefined, { maximumFractionDigits: 2 })}
            </p>
            <p className="text-xs text-gray-500 mt-1">MRR / Active Users</p>
          </div>

          {/* Churn Rate */}
          <div className="bg-white rounded-lg shadow p-6">
            <p className="text-gray-600 text-sm">Monthly Churn Rate</p>
            <p className={`text-3xl font-bold ${summary.churn_rate_percent < 5 ? "text-green-600" : "text-red-600"}`}>
              {summary.churn_rate_percent.toFixed(2)}%
            </p>
            <p className="text-xs text-gray-500 mt-1">Current month</p>
          </div>
        </div>
      )}

      {/* Subscribers */}
      {summary && (
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-xl font-bold mb-4">Active Subscriptions</h2>
          <div className="grid grid-cols-3 gap-4">
            <div className="text-center">
              <p className="text-4xl font-bold text-gray-800">
                {summary.active_subscribers}
              </p>
              <p className="text-gray-600 mt-1">Total Active</p>
            </div>
            <div className="text-center">
              <p className="text-4xl font-bold text-blue-600">
                {summary.annual_plan_subscribers}
              </p>
              <p className="text-gray-600 mt-1">Annual Plans</p>
            </div>
            <div className="text-center">
              <p className="text-4xl font-bold text-purple-600">
                {summary.monthly_plan_subscribers}
              </p>
              <p className="text-gray-600 mt-1">Monthly Plans</p>
            </div>
          </div>
        </div>
      )}

      {/* Cohort Analysis */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-bold">Cohort Retention Analysis</h2>
          <select
            value={monthsBack}
            onChange={(e) => setMonthsBack(parseInt(e.target.value))}
            className="px-3 py-1 border rounded text-sm"
          >
            <option value={6}>Last 6 months</option>
            <option value={12}>Last 12 months</option>
            <option value={24}>Last 24 months</option>
          </select>
        </div>

        {cohorts.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b">
                  <th className="text-left py-2 px-2">Cohort</th>
                  <th className="text-right py-2 px-2">Users</th>
                  <th className="text-right py-2 px-2">Retention (M0)</th>
                  <th className="text-right py-2 px-2">Retention (M1)</th>
                  <th className="text-right py-2 px-2">Total Revenue</th>
                  <th className="text-right py-2 px-2">Avg LTV</th>
                </tr>
              </thead>
              <tbody>
                {cohorts.map((cohort) => (
                  <tr key={cohort.cohort_month} className="border-b hover:bg-gray-50">
                    <td className="py-3 px-2 font-semibold">{cohort.cohort_month}</td>
                    <td className="text-right py-3 px-2">
                      {cohort.initial_subscribers}
                    </td>
                    <td className="text-right py-3 px-2">
                      {cohort.retention_data[0] ? (
                        <>
                          {cohort.retention_data[0]}
                          <span className="text-gray-500 ml-1">
                            ({((cohort.retention_data[0] / cohort.initial_subscribers) * 100).toFixed(0)}%)
                          </span>
                        </>
                      ) : (
                        "N/A"
                      )}
                    </td>
                    <td className="text-right py-3 px-2">
                      {cohort.retention_data[1] ? (
                        <>
                          {cohort.retention_data[1]}
                          <span className="text-gray-500 ml-1">
                            ({((cohort.retention_data[1] / cohort.initial_subscribers) * 100).toFixed(0)}%)
                          </span>
                        </>
                      ) : (
                        "N/A"
                      )}
                    </td>
                    <td className="text-right py-3 px-2">
                      £{cohort.total_revenue_gbp.toLocaleString(undefined, {
                        maximumFractionDigits: 2,
                      })}
                    </td>
                    <td className="text-right py-3 px-2">
                      £{cohort.average_lifetime_value_gbp.toLocaleString(undefined, {
                        maximumFractionDigits: 2,
                      })}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-gray-500 py-8 text-center">No cohort data available</p>
        )}
      </div>

      {/* Notes */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
        <p className="text-sm text-blue-800">
          <strong>📊 Revenue Metrics:</strong>
        </p>
        <ul className="text-sm text-blue-700 mt-2 space-y-1 ml-4">
          <li>• <strong>MRR:</strong> Sum of all active monthly subscription prices</li>
          <li>• <strong>ARR:</strong> MRR × 12 (projected annual revenue)</li>
          <li>• <strong>ARPU:</strong> Average revenue per user (MRR / Active Users)</li>
          <li>• <strong>Churn Rate:</strong> % of subscribers who canceled this month</li>
          <li>• <strong>Cohort Retention:</strong> % of users from each month still active</li>
        </ul>
      </div>
    </div>
  );
}
