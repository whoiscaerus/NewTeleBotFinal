"use client";

import React, { useState, useEffect } from "react";
import { useTelegram } from "@/app/_providers/TelegramProvider";
import { SignalCard } from "@/components/SignalCard";
import { fetchPendingApprovals, approveSignal, rejectSignal, PendingApproval } from "@/lib/approvals";
import { logger } from "@/lib/logger";
import { showSuccessToast, showErrorToast } from "@/lib/toastNotifications";
import { vibrateSuccess, vibrateError } from "@/lib/hapticFeedback";
import {
  trackApprovalClick,
  trackRejectionClick,
  trackApprovalSuccess,
  trackApprovalError,
  trackRejectionSuccess,
  trackRejectionError,
} from "@/lib/telemetry";

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
  const [approvals, setApprovals] = useState<PendingApproval[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [processing, setProcessing] = useState<string | null>(null);

  // Fetch pending approvals
  const handleFetchApprovals = async () => {
    if (!jwt) return;

    try {
      setLoading(true);
      const data = await fetchPendingApprovals(jwt);
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
      handleFetchApprovals();
      const interval = setInterval(handleFetchApprovals, 5000); // Poll every 5s
      return () => clearInterval(interval);
    }
  }, [authLoading, jwt]);

  // Handle approval with optimistic UI
  const handleApprove = async (approvalId: string, signalId: string) => {
    if (!jwt) return;

    // OPTIMISTIC: Capture original state before removing
    const removedApproval = approvals.find((a) => a.id === approvalId);

    try {
      setProcessing(approvalId);

      // TELEMETRY: Track approval click (with signal metadata)
      const confidence = (removedApproval?.signal.payload?.confidence as number) || 0;
      const maturity = (removedApproval?.signal.payload?.maturity as number) || 0;
      trackApprovalClick({
        signal_id: signalId,
        approval_id: approvalId,
        confidence,
        maturity,
        instrument: removedApproval?.signal.instrument,
        side: removedApproval?.signal.side,
      });

      // OPTIMISTIC: Remove immediately from UI
      setApprovals((prev) => prev.filter((a) => a.id !== approvalId));

      // Make API call
      await approveSignal(jwt, approvalId);

      // TELEMETRY: Track success
      trackApprovalSuccess({
        signal_id: signalId,
        approval_id: approvalId,
      });

      // Success feedback: Toast + Haptic
      showSuccessToast("Signal approved!");
      await vibrateSuccess();

      logger.info("Signal approved", { approval_id: approvalId, signal_id: signalId });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to approve signal";

      // TELEMETRY: Track error
      trackApprovalError({
        signal_id: signalId,
        error: message,
      });

      // ROLLBACK: Restore the removed approval if API call failed
      if (removedApproval) {
        setApprovals((prev) => [...prev, removedApproval]);
      }

      // Error feedback: Toast + Haptic
      showErrorToast(message);
      await vibrateError();

      setError(message);
      logger.error("Failed to approve signal - restored to list", {
        approval_id: approvalId,
        error: err,
      });
    } finally {
      setProcessing(null);
    }
  };

  // Handle rejection with optimistic UI
  const handleReject = async (approvalId: string, signalId: string) => {
    if (!jwt) return;

    // OPTIMISTIC: Capture original state before removing
    const removedApproval = approvals.find((a) => a.id === approvalId);

    try {
      setProcessing(approvalId);

      // TELEMETRY: Track rejection click (with signal metadata)
      const confidence = (removedApproval?.signal.payload?.confidence as number) || 0;
      const maturity = (removedApproval?.signal.payload?.maturity as number) || 0;
      trackRejectionClick({
        signal_id: signalId,
        approval_id: approvalId,
        confidence,
        maturity,
        instrument: removedApproval?.signal.instrument,
        side: removedApproval?.signal.side,
      });

      // OPTIMISTIC: Remove immediately from UI
      setApprovals((prev) => prev.filter((a) => a.id !== approvalId));

      // Make API call
      await rejectSignal(jwt, approvalId);

      // TELEMETRY: Track success
      trackRejectionSuccess({
        signal_id: signalId,
        approval_id: approvalId,
      });

      // Success feedback: Toast + Haptic
      showSuccessToast("Signal rejected!");
      await vibrateSuccess();

      logger.info("Signal rejected", { approval_id: approvalId, signal_id: signalId });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to reject signal";

      // TELEMETRY: Track error
      trackRejectionError({
        signal_id: signalId,
        error: message,
      });

      // ROLLBACK: Restore the removed approval if API call failed
      if (removedApproval) {
        setApprovals((prev) => [...prev, removedApproval]);
      }

      // Error feedback: Toast + Haptic
      showErrorToast(message);
      await vibrateError();

      setError(message);
      logger.error("Failed to reject signal - restored to list", {
        approval_id: approvalId,
        error: err,
      });
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
            onClick={handleFetchApprovals}
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
          {approvals.map((approval) => (
            <SignalCard
              key={approval.id}
              approvalId={approval.id}
              signal={approval.signal}
              isProcessing={processing === approval.id}
              onApprove={handleApprove}
              onReject={handleReject}
            />
          ))}
        </div>

        {/* Pull to refresh hint */}
        <p className="text-center text-xs text-gray-400 mt-8">
          Polling every 5 seconds for new signals
        </p>
      </div>
    </div>
  );
}
