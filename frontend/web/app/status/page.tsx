/*
 * Public System Status Page - PR-100
 *
 * Displays real-time system health status with incident history.
 * Auto-refreshes every 30 seconds.
 */

"use client";

import React, { useState, useEffect } from "react";

interface OpenIncidents {
  critical: number;
  high: number;
  medium: number;
  total: number;
}

interface RecentIncident {
  id: number;
  type: string;
  severity: string;
  opened_at: string;
}

interface SystemHealthStatus {
  status: string;
  uptime_percent: number;
  open_incidents: OpenIncidents;
  last_check: string | null;
  recent_incidents: RecentIncident[];
}

export default function StatusPage() {
  const [status, setStatus] = useState<SystemHealthStatus | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date());

  useEffect(() => {
    // Fetch status on mount
    fetchStatus();

    // Auto-refresh every 30 seconds
    const interval = setInterval(fetchStatus, 30000);

    return () => clearInterval(interval);
  }, []);

  const fetchStatus = async () => {
    try {
      setLoading(true);
      const response = await fetch("/api/v1/health/status");

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data: SystemHealthStatus = await response.json();
      setStatus(data);
      setLastUpdate(new Date());
      setError(null);
    } catch (err) {
      console.error("Failed to fetch system status:", err);
      setError(err instanceof Error ? err.message : "Failed to load status");
    } finally {
      setLoading(false);
    }
  };

  if (loading && !status) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-gray-600">Loading system status...</div>
      </div>
    );
  }

  if (error && !status) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="bg-red-50 border border-red-200 rounded-lg p-6 max-w-md">
          <h2 className="text-red-800 font-semibold mb-2">Error Loading Status</h2>
          <p className="text-red-600">{error}</p>
          <button
            onClick={fetchStatus}
            className="mt-4 px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!status) {
    return null;
  }

  const getStatusColor = (statusValue: string) => {
    switch (statusValue) {
      case "operational":
        return "bg-green-500";
      case "degraded":
        return "bg-yellow-500";
      case "down":
        return "bg-red-500";
      default:
        return "bg-gray-500";
    }
  };

  const getStatusText = (statusValue: string) => {
    switch (statusValue) {
      case "operational":
        return "All Systems Operational";
      case "degraded":
        return "Degraded Performance";
      case "down":
        return "System Outage";
      default:
        return "Unknown Status";
    }
  };

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case "critical":
        return "text-red-700 bg-red-100";
      case "high":
        return "text-orange-700 bg-orange-100";
      case "medium":
        return "text-yellow-700 bg-yellow-100";
      case "low":
        return "text-blue-700 bg-blue-100";
      default:
        return "text-gray-700 bg-gray-100";
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200">
        <div className="max-w-5xl mx-auto px-4 py-6">
          <h1 className="text-3xl font-bold text-gray-900">System Status</h1>
          <p className="text-gray-600 mt-1">
            Last updated: {lastUpdate.toLocaleTimeString()}
          </p>
        </div>
      </div>

      {/* Main Content */}
      <div className="max-w-5xl mx-auto px-4 py-8 space-y-8">
        {/* Overall Status */}
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
          <div className="flex items-center space-x-4">
            <div className={`w-4 h-4 rounded-full ${getStatusColor(status.status)}`} />
            <div>
              <h2 className="text-2xl font-semibold text-gray-900">
                {getStatusText(status.status)}
              </h2>
              <p className="text-gray-600 mt-1">
                {status.uptime_percent.toFixed(2)}% uptime
              </p>
            </div>
          </div>

          {status.last_check && (
            <p className="text-sm text-gray-500 mt-4">
              Last health check: {new Date(status.last_check).toLocaleString()}
            </p>
          )}
        </div>

        {/* Open Incidents Summary */}
        {status.open_incidents.total > 0 && (
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
            <h3 className="text-xl font-semibold text-gray-900 mb-4">
              Open Incidents ({status.open_incidents.total})
            </h3>

            <div className="grid grid-cols-3 gap-4">
              {status.open_incidents.critical > 0 && (
                <div className="bg-red-50 border border-red-200 rounded p-4">
                  <div className="text-3xl font-bold text-red-700">
                    {status.open_incidents.critical}
                  </div>
                  <div className="text-sm text-red-600 mt-1">Critical</div>
                </div>
              )}

              {status.open_incidents.high > 0 && (
                <div className="bg-orange-50 border border-orange-200 rounded p-4">
                  <div className="text-3xl font-bold text-orange-700">
                    {status.open_incidents.high}
                  </div>
                  <div className="text-sm text-orange-600 mt-1">High</div>
                </div>
              )}

              {status.open_incidents.medium > 0 && (
                <div className="bg-yellow-50 border border-yellow-200 rounded p-4">
                  <div className="text-3xl font-bold text-yellow-700">
                    {status.open_incidents.medium}
                  </div>
                  <div className="text-sm text-yellow-600 mt-1">Medium</div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Recent Incidents */}
        {status.recent_incidents.length > 0 && (
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
            <h3 className="text-xl font-semibold text-gray-900 mb-4">Recent Incidents</h3>

            <div className="space-y-3">
              {status.recent_incidents.map((incident) => (
                <div
                  key={incident.id}
                  className="border border-gray-200 rounded-lg p-4 hover:bg-gray-50"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-3">
                      <span
                        className={`px-2 py-1 rounded text-xs font-medium ${getSeverityColor(
                          incident.severity
                        )}`}
                      >
                        {incident.severity.toUpperCase()}
                      </span>
                      <span className="text-gray-900 font-medium">{incident.type}</span>
                    </div>
                    <span className="text-sm text-gray-500">
                      {new Date(incident.opened_at).toLocaleString()}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* No Incidents */}
        {status.open_incidents.total === 0 && status.recent_incidents.length === 0 && (
          <div className="bg-green-50 border border-green-200 rounded-lg p-6 text-center">
            <div className="text-green-700 text-lg font-medium">
              ✓ No incidents reported
            </div>
            <p className="text-green-600 mt-2">All systems are operating normally</p>
          </div>
        )}

        {/* Auto-refresh indicator */}
        <div className="text-center text-sm text-gray-500">
          Auto-refreshing every 30 seconds
        </div>
      </div>
    </div>
  );
}
