"use client";

/**
 * Model Explainability & Decision Explorer
 *
 * Admin interface for understanding "why" trading decisions were made.
 * Features:
 * - Decision search with filters (date, strategy, outcome, symbol)
 * - Feature attribution visualization (SHAP-like contributions)
 * - Decision timeline with drill-down
 * - Export capabilities (CSV/JSON)
 *
 * Integration:
 * - backend/app/explain/attribution.py: Feature importance computation
 * - backend/app/strategy/logs/routes.py: Decision search API
 *
 * Example:
 *   User searches for "fib_rsi" strategy decisions from last 7 days
 *   → Table shows 50 decisions with outcome/symbol
 *   → Click on decision → Attribution chart shows RSI contributed 35%, Fib 15%
 */

import React, { useState, useEffect } from "react";
import { Line, Bar } from "react-chartjs-2";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend,
} from "chart.js";

// Register Chart.js components
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend
);

interface Decision {
  id: string;
  timestamp: string;
  strategy: string;
  symbol: string;
  outcome: string;
  features: Record<string, any>;
  note: string | null;
}

interface Attribution {
  decision_id: string;
  strategy: string;
  symbol: string;
  prediction: number;
  baseline: number;
  prediction_delta: number;
  contributions: Record<string, number>;
  is_valid: boolean;
}

interface SearchFilters {
  strategy: string;
  symbol: string;
  outcome: string;
  start_date: string;
  end_date: string;
  page: number;
  page_size: number;
}

export default function ExplainPage() {
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [selectedDecision, setSelectedDecision] = useState<Decision | null>(null);
  const [attribution, setAttribution] = useState<Attribution | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [filters, setFilters] = useState<SearchFilters>({
    strategy: "",
    symbol: "",
    outcome: "",
    start_date: "",
    end_date: "",
    page: 1,
    page_size: 50,
  });

  const [totalResults, setTotalResults] = useState(0);
  const [totalPages, setTotalPages] = useState(0);

  // Search decisions
  const searchDecisions = async () => {
    setLoading(true);
    setError(null);

    try {
      const params = new URLSearchParams();
      if (filters.strategy) params.append("strategy", filters.strategy);
      if (filters.symbol) params.append("symbol", filters.symbol);
      if (filters.outcome) params.append("outcome", filters.outcome);
      if (filters.start_date) params.append("start_date", filters.start_date);
      if (filters.end_date) params.append("end_date", filters.end_date);
      params.append("page", filters.page.toString());
      params.append("page_size", filters.page_size.toString());

      const response = await fetch(`/api/v1/decisions/search?${params}`);
      if (!response.ok) {
        throw new Error(`Search failed: ${response.statusText}`);
      }

      const data = await response.json();
      setDecisions(data.results || []);
      setTotalResults(data.total || 0);
      setTotalPages(data.total_pages || 0);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
      console.error("Search error:", err);
    } finally {
      setLoading(false);
    }
  };

  // Load attribution for selected decision
  const loadAttribution = async (decision: Decision) => {
    setLoading(true);
    setError(null);
    setSelectedDecision(decision);

    try {
      const response = await fetch(
        `/api/v1/explain/attribution?decision_id=${decision.id}&strategy=${decision.strategy}`
      );
      if (!response.ok) {
        throw new Error(`Attribution failed: ${response.statusText}`);
      }

      const data = await response.json();
      setAttribution(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Attribution failed");
      console.error("Attribution error:", err);
    } finally {
      setLoading(false);
    }
  };

  // Initial search
  useEffect(() => {
    searchDecisions();
  }, [filters.page, filters.page_size]); // Re-search on pagination change

  // Prepare attribution chart data
  const getAttributionChartData = () => {
    if (!attribution) return null;

    const features = Object.keys(attribution.contributions);
    const values = Object.values(attribution.contributions);

    return {
      labels: features,
      datasets: [
        {
          label: "Feature Contribution",
          data: values,
          backgroundColor: values.map((v) =>
            v > 0 ? "rgba(75, 192, 192, 0.6)" : "rgba(255, 99, 132, 0.6)"
          ),
          borderColor: values.map((v) =>
            v > 0 ? "rgba(75, 192, 192, 1)" : "rgba(255, 99, 132, 1)"
          ),
          borderWidth: 1,
        },
      ],
    };
  };

  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-7xl mx-auto">
        <h1 className="text-3xl font-bold text-gray-900 mb-8">
          Model Explainability & Decision Explorer
        </h1>

        {/* Search Filters */}
        <div className="bg-white rounded-lg shadow p-6 mb-6">
          <h2 className="text-xl font-semibold mb-4">Search Decisions</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Strategy
              </label>
              <input
                type="text"
                placeholder="e.g., fib_rsi, ppo_gold"
                value={filters.strategy}
                onChange={(e) =>
                  setFilters({ ...filters, strategy: e.target.value })
                }
                className="w-full border border-gray-300 rounded-md px-3 py-2"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Symbol
              </label>
              <input
                type="text"
                placeholder="e.g., GOLD, XAUUSD"
                value={filters.symbol}
                onChange={(e) =>
                  setFilters({ ...filters, symbol: e.target.value })
                }
                className="w-full border border-gray-300 rounded-md px-3 py-2"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Outcome
              </label>
              <select
                value={filters.outcome}
                onChange={(e) =>
                  setFilters({ ...filters, outcome: e.target.value })
                }
                className="w-full border border-gray-300 rounded-md px-3 py-2"
              >
                <option value="">All Outcomes</option>
                <option value="entered">Entered</option>
                <option value="skipped">Skipped</option>
                <option value="rejected">Rejected</option>
                <option value="pending">Pending</option>
                <option value="error">Error</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Start Date
              </label>
              <input
                type="datetime-local"
                value={filters.start_date}
                onChange={(e) =>
                  setFilters({ ...filters, start_date: e.target.value })
                }
                className="w-full border border-gray-300 rounded-md px-3 py-2"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                End Date
              </label>
              <input
                type="datetime-local"
                value={filters.end_date}
                onChange={(e) =>
                  setFilters({ ...filters, end_date: e.target.value })
                }
                className="w-full border border-gray-300 rounded-md px-3 py-2"
              />
            </div>
          </div>

          <button
            onClick={searchDecisions}
            disabled={loading}
            className="mt-4 bg-blue-600 text-white px-6 py-2 rounded-md hover:bg-blue-700 disabled:bg-gray-400"
          >
            {loading ? "Searching..." : "Search"}
          </button>
        </div>

        {/* Error Display */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
            <p className="text-red-800">{error}</p>
          </div>
        )}

        {/* Results Table */}
        <div className="bg-white rounded-lg shadow overflow-hidden mb-6">
          <div className="px-6 py-4 border-b border-gray-200">
            <h2 className="text-xl font-semibold">
              Results ({totalResults} total, page {filters.page}/{totalPages})
            </h2>
          </div>

          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Timestamp
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Strategy
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Symbol
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Outcome
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {decisions.map((decision) => (
                  <tr key={decision.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                      {new Date(decision.timestamp).toLocaleString()}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                      {decision.strategy}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                      {decision.symbol}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span
                        className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${
                          decision.outcome === "entered"
                            ? "bg-green-100 text-green-800"
                            : decision.outcome === "skipped"
                            ? "bg-gray-100 text-gray-800"
                            : decision.outcome === "rejected"
                            ? "bg-red-100 text-red-800"
                            : "bg-yellow-100 text-yellow-800"
                        }`}
                      >
                        {decision.outcome}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm">
                      <button
                        onClick={() => loadAttribution(decision)}
                        className="text-blue-600 hover:text-blue-900"
                      >
                        Explain
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="px-6 py-4 border-t border-gray-200 flex justify-between items-center">
            <button
              onClick={() =>
                setFilters({ ...filters, page: Math.max(1, filters.page - 1) })
              }
              disabled={filters.page === 1 || loading}
              className="px-4 py-2 border border-gray-300 rounded-md disabled:opacity-50"
            >
              Previous
            </button>

            <span className="text-sm text-gray-700">
              Page {filters.page} of {totalPages}
            </span>

            <button
              onClick={() =>
                setFilters({
                  ...filters,
                  page: Math.min(totalPages, filters.page + 1),
                })
              }
              disabled={filters.page === totalPages || loading}
              className="px-4 py-2 border border-gray-300 rounded-md disabled:opacity-50"
            >
              Next
            </button>
          </div>
        </div>

        {/* Attribution Visualization */}
        {selectedDecision && attribution && (
          <div className="bg-white rounded-lg shadow p-6">
            <h2 className="text-xl font-semibold mb-4">
              Feature Attribution: {selectedDecision.strategy} on{" "}
              {selectedDecision.symbol}
            </h2>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
              <div>
                <h3 className="text-sm font-medium text-gray-700 mb-2">
                  Decision Details
                </h3>
                <dl className="space-y-2">
                  <div>
                    <dt className="text-xs text-gray-500">Prediction</dt>
                    <dd className="text-sm font-semibold">
                      {attribution.prediction.toFixed(4)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-gray-500">Baseline</dt>
                    <dd className="text-sm font-semibold">
                      {attribution.baseline.toFixed(4)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-gray-500">Delta</dt>
                    <dd className="text-sm font-semibold">
                      {attribution.prediction_delta.toFixed(4)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-gray-500">Valid</dt>
                    <dd className="text-sm font-semibold">
                      {attribution.is_valid ? (
                        <span className="text-green-600">✓ Yes</span>
                      ) : (
                        <span className="text-red-600">✗ No</span>
                      )}
                    </dd>
                  </div>
                </dl>
              </div>

              <div>
                <h3 className="text-sm font-medium text-gray-700 mb-2">
                  Feature Contributions
                </h3>
                <dl className="space-y-2">
                  {Object.entries(attribution.contributions)
                    .sort(([, a], [, b]) => Math.abs(b) - Math.abs(a))
                    .map(([feature, value]) => (
                      <div key={feature} className="flex justify-between">
                        <dt className="text-xs text-gray-600">{feature}</dt>
                        <dd
                          className={`text-sm font-semibold ${
                            value > 0 ? "text-green-600" : "text-red-600"
                          }`}
                        >
                          {value > 0 ? "+" : ""}
                          {value.toFixed(4)}
                        </dd>
                      </div>
                    ))}
                </dl>
              </div>
            </div>

            {/* Bar Chart */}
            <div className="h-64">
              <Bar
                data={getAttributionChartData()!}
                options={{
                  responsive: true,
                  maintainAspectRatio: false,
                  plugins: {
                    title: {
                      display: true,
                      text: "Feature Contribution to Prediction",
                    },
                    legend: {
                      display: false,
                    },
                  },
                  scales: {
                    y: {
                      beginAtZero: true,
                      title: {
                        display: true,
                        text: "Contribution",
                      },
                    },
                  },
                }}
              />
            </div>

            {/* Decision Note */}
            {selectedDecision.note && (
              <div className="mt-6 p-4 bg-gray-50 rounded-md">
                <h3 className="text-sm font-medium text-gray-700 mb-2">
                  Decision Note
                </h3>
                <p className="text-sm text-gray-600">{selectedDecision.note}</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
