"use client";

import React, { useState, useEffect } from "react";
import { logger } from "@/lib/logger";
import { formatDistanceToNow } from "date-fns";

export interface Signal {
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

export interface SignalCardProps {
  approvalId: string;
  signal: Signal;
  isProcessing: boolean;
  onApprove: (approvalId: string, signalId: string) => void;
  onReject: (approvalId: string, signalId: string) => void;
}

/**
 * SignalCard Component
 *
 * Displays a single pending trading signal with approve/reject buttons.
 * Shows entry price, SL, TP, RR ratio, and relative creation time.
 *
 * @example
 * <SignalCard
 *   approvalId="approval-123"
 *   signal={signal}
 *   isProcessing={false}
 *   onApprove={handleApprove}
 *   onReject={handleReject}
 * />
 */
export const SignalCard: React.FC<SignalCardProps> = ({
  approvalId,
  signal,
  isProcessing,
  onApprove,
  onReject,
}) => {
  const [relativeTime, setRelativeTime] = useState<string>("");

  // Update relative time every second
  useEffect(() => {
    const updateTime = () => {
      try {
        setRelativeTime(formatDistanceToNow(new Date(signal.created_at), { addSuffix: true }));
      } catch (err) {
        logger.warn("Failed to format relative time", { error: err });
        setRelativeTime("just now");
      }
    };

    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, [signal.created_at]);

  const sideColor = signal.side === "buy" ? "text-green-400" : "text-red-400";
  const sideBg = signal.side === "buy" ? "bg-green-500 bg-opacity-20" : "bg-red-500 bg-opacity-20";

  return (
    <div
      data-testid={`signal-card-${approvalId}`}
      className={`rounded-lg border border-blue-400 border-opacity-30 p-4 backdrop-blur-sm transition-all duration-300 ${
        isProcessing
          ? "opacity-50 scale-95 pointer-events-none bg-blue-900 bg-opacity-50"
          : "hover:border-opacity-50 hover:bg-blue-900 hover:bg-opacity-20"
      }`}
    >
      {/* Header: Instrument + Side */}
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

      {/* Price Levels */}
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
          <span className="float-right text-green-300 font-mono">
            {signal.take_profit.toFixed(2)}
          </span>
        </p>
      </div>

      {/* Relative Time */}
      <p className="text-xs text-gray-400 mb-4">{relativeTime}</p>

      {/* Action Buttons */}
      <div className="flex gap-3">
        <button
          onClick={() => {
            logger.info("Reject button clicked", { approvalId, signalId: signal.id });
            onReject(approvalId, signal.id);
          }}
          disabled={isProcessing}
          data-testid={`reject-button-${approvalId}`}
          className="flex-1 px-3 py-2 bg-red-500 text-white rounded-lg font-semibold hover:bg-red-600 disabled:bg-red-400 disabled:opacity-50 transition-colors"
        >
          {isProcessing ? "..." : "❌ Reject"}
        </button>
        <button
          onClick={() => {
            logger.info("Approve button clicked", { approvalId, signalId: signal.id });
            onApprove(approvalId, signal.id);
          }}
          disabled={isProcessing}
          data-testid={`approve-button-${approvalId}`}
          className="flex-1 px-3 py-2 bg-green-500 text-white rounded-lg font-semibold hover:bg-green-600 disabled:bg-green-400 disabled:opacity-50 transition-colors"
        >
          {isProcessing ? "..." : "✅ Approve"}
        </button>
      </div>
    </div>
  );
};

SignalCard.displayName = "SignalCard";
