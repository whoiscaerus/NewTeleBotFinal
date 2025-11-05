"use client";

import React, { useMemo } from "react";
import { Signal } from "@/lib/approvals";
import { logger } from "@/lib/logger";

export interface SignalDetailsProps {
  signal: Signal | null;
  isOpen: boolean;
  onClose: () => void;
  confidence?: number; // 0-100 from signal.payload
  maturityScore?: number; // 0-100 based on age
}

/**
 * SignalDetails Component
 *
 * Displays full signal details in a drawer/modal format.
 * Shows confidence meter, signal maturity bar, and extended metadata.
 *
 * @example
 * <SignalDetails
 *   signal={selectedSignal}
 *   isOpen={isDetailsOpen}
 *   onClose={() => setIsDetailsOpen(false)}
 *   confidence={75}
 *   maturityScore={45}
 * />
 */
export const SignalDetails: React.FC<SignalDetailsProps> = ({
  signal,
  isOpen,
  onClose,
  confidence = 0,
  maturityScore = 0,
}) => {
  if (!isOpen || !signal) return null;

  // Calculate maturity indicator color
  const getMaturityColor = (score: number): string => {
    if (score < 33) return "bg-green-500"; // Fresh signal (green = good)
    if (score < 66) return "bg-yellow-500"; // Aging (yellow = caution)
    return "bg-red-500"; // Old (red = urgent)
  };

  // Calculate confidence color
  const getConfidenceColor = (conf: number): string => {
    if (conf < 50) return "bg-red-500"; // Low confidence
    if (conf < 75) return "bg-yellow-500"; // Medium confidence
    return "bg-green-500"; // High confidence
  };

  // Extract metadata from signal payload
  const metadata = useMemo(() => {
    const payload = signal.payload || {};
    return {
      strategy: payload.strategy as string | undefined,
      timeframe: payload.timeframe as string | undefined,
      rsi: payload.rsi as number | undefined,
      macd: payload.macd as string | undefined,
      trend: payload.trend as string | undefined,
      supportResistance: payload.support_resistance as string | undefined,
      notes: payload.notes as string | undefined,
    };
  }, [signal.payload]);

  // Log drawer opening for telemetry
  React.useEffect(() => {
    if (isOpen) {
      logger.info("Signal details viewed", {
        signal_id: signal?.id,
        instrument: signal?.instrument,
        confidence,
        maturityScore,
      });
    }
  }, [isOpen, signal?.id, signal?.instrument, confidence, maturityScore]);

  return (
    <>
      {/* Overlay - Click to close */}
      <div
        className="fixed inset-0 bg-black bg-opacity-40 z-40"
        onClick={onClose}
        data-testid="details-overlay"
      />

      {/* Drawer - Slide in from bottom/right */}
      <div
        className="fixed bottom-0 right-0 w-full sm:w-96 h-4/5 bg-gray-900 border-l border-blue-500 border-opacity-30 rounded-t-2xl sm:rounded-2xl p-6 overflow-y-auto z-50 transform transition-transform"
        data-testid="details-drawer"
      >
        {/* Header */}
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-2xl font-bold text-white">{signal.instrument}</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white transition-colors text-2xl"
            aria-label="Close details"
            data-testid="close-button"
          >
            ✕
          </button>
        </div>

        {/* Signal Type Badge */}
        <div className="mb-6">
          <div
            className={`inline-block px-3 py-1 rounded-full text-sm font-semibold text-white ${
              signal.side === "buy"
                ? "bg-green-500 bg-opacity-20 border border-green-400"
                : "bg-red-500 bg-opacity-20 border border-red-400"
            }`}
            data-testid="signal-type-badge"
          >
            {signal.side === "buy" ? "📈 BUY SIGNAL" : "📉 SELL SIGNAL"}
          </div>
        </div>

        {/* Price Levels Section */}
        <div className="mb-8 p-4 bg-blue-900 bg-opacity-20 rounded-lg border border-blue-400 border-opacity-20">
          <h3 className="text-sm font-semibold text-gray-300 mb-4 uppercase">Price Levels</h3>

          <div className="space-y-3">
            <div className="flex justify-between items-center">
              <span className="text-gray-400">Entry Price</span>
              <span className="text-white font-mono font-semibold text-lg">
                {signal.entry_price.toFixed(2)}
              </span>
            </div>

            <div className="flex justify-between items-center">
              <span className="text-gray-400">Stop Loss</span>
              <span className="text-red-300 font-mono font-semibold">
                {signal.stop_loss.toFixed(2)}
              </span>
            </div>

            <div className="flex justify-between items-center">
              <span className="text-gray-400">Take Profit</span>
              <span className="text-green-300 font-mono font-semibold">
                {signal.take_profit.toFixed(2)}
              </span>
            </div>

            <div className="border-t border-blue-400 border-opacity-20 pt-3 mt-3 flex justify-between items-center">
              <span className="text-gray-400 font-semibold">Risk/Reward</span>
              <span className="text-yellow-300 font-mono text-lg">
                1:{signal.risk_reward_ratio.toFixed(2)}
              </span>
            </div>
          </div>
        </div>

        {/* Confidence Meter */}
        <div className="mb-8">
          <div className="flex justify-between items-center mb-2">
            <h3 className="text-sm font-semibold text-gray-300 uppercase">Confidence</h3>
            <span className="text-white font-semibold">{confidence}%</span>
          </div>

          <div className="w-full h-3 bg-gray-800 rounded-full overflow-hidden">
            <div
              className={`h-full ${getConfidenceColor(confidence)} transition-all`}
              style={{ width: `${confidence}%` }}
              data-testid="confidence-bar"
            />
          </div>

          <p className="text-xs text-gray-400 mt-2">
            {confidence < 50
              ? "Low - Consider waiting for confirmation"
              : confidence < 75
                ? "Medium - Suitable for most traders"
                : "High - Strong signal with good setup"}
          </p>
        </div>

        {/* Signal Maturity */}
        <div className="mb-8">
          <div className="flex justify-between items-center mb-2">
            <h3 className="text-sm font-semibold text-gray-300 uppercase">Age</h3>
            <span className="text-white font-semibold">{maturityScore}%</span>
          </div>

          <div className="w-full h-3 bg-gray-800 rounded-full overflow-hidden">
            <div
              className={`h-full ${getMaturityColor(maturityScore)} transition-all`}
              style={{ width: `${maturityScore}%` }}
              data-testid="maturity-bar"
            />
          </div>

          <p className="text-xs text-gray-400 mt-2">
            {maturityScore < 33
              ? "Fresh signal - High priority"
              : maturityScore < 66
                ? "Aging - Act soon"
                : "Urgent - Limited time to execute"}
          </p>
        </div>

        {/* Strategy Metadata */}
        {(metadata.strategy || metadata.timeframe || metadata.trend) && (
          <div className="mb-8 p-4 bg-gray-800 bg-opacity-30 rounded-lg border border-gray-700">
            <h3 className="text-sm font-semibold text-gray-300 mb-3 uppercase">Strategy Info</h3>

            <div className="space-y-2 text-sm">
              {metadata.strategy && (
                <div>
                  <span className="text-gray-400">Strategy:</span>
                  <span className="ml-2 text-white">{metadata.strategy}</span>
                </div>
              )}

              {metadata.timeframe && (
                <div>
                  <span className="text-gray-400">Timeframe:</span>
                  <span className="ml-2 text-white">{metadata.timeframe}</span>
                </div>
              )}

              {metadata.trend && (
                <div>
                  <span className="text-gray-400">Trend:</span>
                  <span className="ml-2 text-white">{metadata.trend}</span>
                </div>
              )}

              {metadata.rsi !== undefined && (
                <div>
                  <span className="text-gray-400">RSI:</span>
                  <span className="ml-2 text-white">{metadata.rsi.toFixed(1)}</span>
                </div>
              )}

              {metadata.macd && (
                <div>
                  <span className="text-gray-400">MACD:</span>
                  <span className="ml-2 text-white">{metadata.macd}</span>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Technical Analysis */}
        {(metadata.supportResistance || metadata.notes) && (
          <div className="mb-8 p-4 bg-gray-800 bg-opacity-30 rounded-lg border border-gray-700">
            <h3 className="text-sm font-semibold text-gray-300 mb-3 uppercase">Technical Analysis</h3>

            {metadata.supportResistance && (
              <div className="mb-3">
                <p className="text-xs text-gray-400 mb-1">Support/Resistance</p>
                <p className="text-sm text-white">{metadata.supportResistance}</p>
              </div>
            )}

            {metadata.notes && (
              <div>
                <p className="text-xs text-gray-400 mb-1">Notes</p>
                <p className="text-sm text-white whitespace-pre-wrap">{metadata.notes}</p>
              </div>
            )}
          </div>
        )}

        {/* Signal Metadata */}
        <div className="pt-4 border-t border-gray-700 text-xs text-gray-500 space-y-1">
          <div>
            <span>Signal ID:</span>
            <code className="ml-2 text-gray-400">{signal.id.substring(0, 8)}...</code>
          </div>
          <div>
            <span>Created:</span>
            <span className="ml-2">{new Date(signal.created_at).toLocaleString()}</span>
          </div>
        </div>
      </div>
    </>
  );
};

SignalDetails.displayName = "SignalDetails";
