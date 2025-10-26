"use client";

import React, { useState, useEffect } from "react";
import { useTelegram } from "@/app/_providers/TelegramProvider";
import { apiGet, apiPost } from "@/lib/api";
import { logger } from "@/lib/logger";

interface Signal {
  id: string;
  instrument: string;
  side: "buy" | "sell";
  entry_price: number;
  stop_loss: number;
  take_profit: number;
  risk_reward_ratio: number;
  created_at: string;
  payload: Record<string, unknown>;
}

interface Approval {
  id: string;
  signal_id: string;
  signal: Signal;
  status: "pending" | "approved" | "rejected";
}

/**
 * Mini App Approvals Page
 *
 * Displays pending trading signals with one-tap approve/reject functionality.
 * Auto-polls for new signals every 5 seconds.
 *
 * @example
 * Navigate to /approvals → see pending signals → tap approve/reject
 */
export default function ApprovalsPage() {
  const { jwt, isLoading: authLoading, error: authError } = useTelegram();
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [processing, setProcessing] = useState<string | null>(null);

  // Fetch pending approvals
  const fetchApprovals = async () => {
    if (!jwt) return;

    try {
      setLoading(true);
      const data = await apiGet<Approval[]>("/api/v1/approvals/pending", {
        headers: { Authorization: `Bearer ${jwt}` },
      });
      setApprovals(data || []);
      setError(null);
      logger.info("Approvals fetched", {
        count: data?.length || 0,
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to fetch approvals";
      setError(message);
      logger.error("Failed to fetch approvals", { error: err });
    } finally {
      setLoading(false);
    }
  };

  // Set up polling on mount
  useEffect(() => {
    if (!authLoading && jwt) {
      fetchApprovals();
      const interval = setInterval(fetchApprovals, 5000); // Poll every 5s
      return () => clearInterval(interval);
    }
  }, [authLoading, jwt]);

  // Handle approval
  const handleApprove = async (approvalId: string, signalId: string) => {
    if (!jwt) return;

    try {
      setProcessing(approvalId);
      await apiPost(
        `/api/v1/approvals/${approvalId}/approve`,
        {},
        { headers: { Authorization: `Bearer ${jwt}` } }
      );

      // Remove from list
      setApprovals((prev) => prev.filter((a) => a.id !== approvalId));
      logger.info("Signal approved", { approval_id: approvalId, signal_id: signalId });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to approve signal";
      setError(message);
      logger.error("Failed to approve signal", { approval_id: approvalId, error: err });
    } finally {
      setProcessing(null);
    }
  };

  // Handle rejection
  const handleReject = async (approvalId: string, signalId: string) => {
    if (!jwt) return;

    try {
      setProcessing(approvalId);
      await apiPost(
        `/api/v1/approvals/${approvalId}/reject`,
        {},
        { headers: { Authorization: `Bearer ${jwt}` } }
      );

      // Remove from list
      setApprovals((prev) => prev.filter((a) => a.id !== approvalId));
      logger.info("Signal rejected", { approval_id: approvalId, signal_id: signalId });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to reject signal";
      setError(message);
      logger.error("Failed to reject signal", { approval_id: approvalId, error: err });
    } finally {
      setProcessing(null);
    }
  };

  // Auth loading
  if (authLoading) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-blue-900 to-blue-800 flex items-center justify-center">
        <div className="text-center text-white">
          <div className="animate-spin rounded-full h-12 w-12 border-4 border-blue-300 border-t-white mx-auto mb-4" />
          <p>Authenticating...</p>
        </div>
      </div>
    );
  }

  // Auth error
  if (authError) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-blue-900 to-blue-800 flex items-center justify-center p-4">
        <div className="text-center text-red-300">
          <p className="text-lg font-semibold mb-2">Authentication Error</p>
          <p className="text-sm">{authError}</p>
          <button
            onClick={() => window.location.reload()}
            className="mt-4 px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600 transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  // Loading state
  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-blue-900 to-blue-800 flex items-center justify-center">
        <div className="text-center text-white">
          <div className="animate-spin rounded-full h-12 w-12 border-4 border-blue-300 border-t-white mx-auto mb-4" />
          <p>Loading signals...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-blue-900 to-blue-800 p-4">
        <div className="max-w-md mx-auto mt-8">
          <div className="bg-red-500 bg-opacity-20 border border-red-400 rounded-lg p-4 text-red-200 mb-4">
            <p className="font-semibold mb-2">Error</p>
            <p className="text-sm">{error}</p>
          </div>
          <button
            onClick={fetchApprovals}
            className="w-full px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  // Empty state
  if (approvals.length === 0) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-blue-900 to-blue-800 p-4">
        <div className="max-w-md mx-auto mt-16 text-center">
          <div className="text-6xl mb-4">🎯</div>
          <h1 className="text-2xl font-bold text-white mb-2">All Caught Up!</h1>
          <p className="text-blue-200 mb-8">No pending signals right now.</p>
          <p className="text-sm text-blue-300">
            New signals will appear here when they're ready for approval.
          </p>
        </div>
      </div>
    );
  }

  // Main content
  return (
    <div className="min-h-screen bg-gradient-to-b from-blue-900 to-blue-800 p-4 pb-20">
      <div className="max-w-md mx-auto">
        <h1 className="text-2xl font-bold text-white mb-2">Pending Approvals</h1>
        <p className="text-blue-200 text-sm mb-6">{approvals.length} signal(s) waiting</p>

        <div className="space-y-4">
          {approvals.map((approval) => {
            const signal = approval.signal;
            const isProcessing = processing === approval.id;
            const sideColor = signal.side === "buy" ? "text-green-400" : "text-red-400";
            const sideBg = signal.side === "buy" ? "bg-green-500 bg-opacity-20" : "bg-red-500 bg-opacity-20";

            return (
              <div
                key={approval.id}
                data-testid="signal-card"
                className={`rounded-lg border border-blue-400 border-opacity-30 p-4 backdrop-blur-sm transition-all ${
                  isProcessing ? "opacity-50" : "hover:border-opacity-50"
                }`}
              >
                {/* Header */}
                <div className="flex justify-between items-start mb-3">
                  <div>
                    <p className="text-white font-bold text-lg">{signal.instrument}</p>
                    <p className={`text-sm font-semibold ${sideColor}`}>
                      {signal.side === "buy" ? "📈 BUY" : "📉 SELL"}
                    </p>
                  </div>
                  <div className={`rounded px-2 py-1 text-xs font-semibold ${sideBg} text-white`}>
                    RR: {signal.risk_reward_ratio.toFixed(2)}
                  </div>
                </div>

                {/* Price levels */}
                <div className="bg-blue-900 bg-opacity-40 rounded p-3 mb-3 text-sm text-blue-100 space-y-1">
                  <p>
                    <span className="text-gray-400">Entry:</span>
                    <span className="float-right text-white font-mono font-semibold">
                      {signal.entry_price.toFixed(2)}
                    </span>
                  </p>
                  <p>
                    <span className="text-gray-400">SL:</span>
                    <span className="float-right text-red-300 font-mono">{signal.stop_loss.toFixed(2)}</span>
                  </p>
                  <p>
                    <span className="text-gray-400">TP:</span>
                    <span className="float-right text-green-300 font-mono">{signal.take_profit.toFixed(2)}</span>
                  </p>
                </div>

                {/* Time */}
                <p className="text-xs text-gray-400 mb-4">
                  {new Date(signal.created_at).toLocaleTimeString([], {
                    hour: "2-digit",
                    minute: "2-digit",
                    hour12: true,
                  })}
                </p>

                {/* Buttons */}
                <div className="flex gap-3">
                  <button
                    onClick={() => handleReject(approval.id, signal.id)}
                    disabled={isProcessing}
                    data-testid="reject-button"
                    className="flex-1 px-3 py-2 bg-red-500 text-white rounded-lg font-semibold hover:bg-red-600 disabled:bg-red-400 disabled:opacity-50 transition-colors"
                  >
                    {isProcessing ? "..." : "❌ Reject"}
                  </button>
                  <button
                    onClick={() => handleApprove(approval.id, signal.id)}
                    disabled={isProcessing}
                    data-testid="approve-button"
                    className="flex-1 px-3 py-2 bg-green-500 text-white rounded-lg font-semibold hover:bg-green-600 disabled:bg-green-400 disabled:opacity-50 transition-colors"
                  >
                    {isProcessing ? "..." : "✅ Approve"}
                  </button>
                </div>
              </div>
            );
          })}
        </div>

        {/* Pull to refresh hint */}
        <p className="text-center text-xs text-gray-400 mt-8">
          Polling every 5 seconds for new signals
        </p>
      </div>
    </div>
  );
}
