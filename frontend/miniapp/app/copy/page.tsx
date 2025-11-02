"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, CheckCircle2, Clock, Toggle2, ArrowRight, Settings } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { logger } from "@/lib/logger";
import { api } from "@/lib/api";

interface CopySettings {
  enabled: boolean;
  risk_multiplier: number;
  max_drawdown_percent: number;
  max_position_size_lot: number;
  max_daily_trades: number;
  trades_today: number;
  markup_percent: number;
}

/**
 * Copy-Trading Main Page (Mini App)
 *
 * Copy-Trading Integration with Pricing Uplift (PR-045)
 *
 * Features:
 * - Enable/disable copy-trading with +30% pricing
 * - Display current copy-trading status
 * - Show risk parameters
 * - Navigate to settings for risk configuration
 * - Display pricing tier information
 * - Consent acceptance flow
 * - Auto-execution status
 *
 * Business Logic:
 * - Trades auto-execute without approval when enabled
 * - +30% markup applied to subscription price
 * - Risk controls enforced (max position, daily trades, drawdown)
 * - Explicit consent required before enabling
 */
export default function CopyTradingPage() {
  const router = useRouter();
  const { user } = useAuth();

  const [copySettings, setCopySettings] = useState<CopySettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [enableLoading, setEnableLoading] = useState(false);
  const [showEnableConfirm, setShowEnableConfirm] = useState(false);
  const [showDisableConfirm, setShowDisableConfirm] = useState(false);

  // Load copy-trading settings
  useEffect(() => {
    loadCopySettings();
  }, []);

  const loadCopySettings = async () => {
    try {
      setLoading(true);
      const response = await api.get("/api/v1/copy/status");
      const settings: CopySettings = {
        enabled: response.data.enabled,
        risk_multiplier: response.data.risk_parameters?.risk_multiplier || 1.0,
        max_drawdown_percent: response.data.risk_parameters?.max_drawdown_percent || 20.0,
        max_position_size_lot: response.data.risk_parameters?.max_position_size_lot || 5.0,
        max_daily_trades: response.data.risk_parameters?.max_daily_trades || 50,
        trades_today: response.data.risk_parameters?.trades_today || 0,
        markup_percent: 30.0,
      };
      setCopySettings(settings);
      setError(null);
    } catch (err) {
      logger.error("Failed to load copy settings", { error: err });
      setError("Failed to load copy-trading settings");
    } finally {
      setLoading(false);
    }
  };

  const handleEnableCopyTrading = async () => {
    try {
      setEnableLoading(true);

      // First, accept disclosure (if not already accepted)
      try {
        await api.post("/api/v1/copy/consent");
      } catch (e) {
        // User may have already accepted - continue
        if ((e as any)?.response?.status !== 400) {
          throw e;
        }
      }

      // Then enable copy-trading
      await api.post("/api/v1/copy/enable", {
        consent_version: "1.0",
        risk_multiplier: 1.0,
      });

      logger.info("Copy-trading enabled", { user_id: user?.id });
      setShowEnableConfirm(false);
      await loadCopySettings();
    } catch (err) {
      logger.error("Failed to enable copy-trading", { error: err });
      setError("Failed to enable copy-trading. Please try again.");
    } finally {
      setEnableLoading(false);
    }
  };

  const handleDisableCopyTrading = async () => {
    try {
      setEnableLoading(true);
      await api.post("/api/v1/copy/disable");
      logger.info("Copy-trading disabled", { user_id: user?.id });
      setShowDisableConfirm(false);
      await loadCopySettings();
    } catch (err) {
      logger.error("Failed to disable copy-trading", { error: err });
      setError("Failed to disable copy-trading. Please try again.");
    } finally {
      setEnableLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gradient-to-br from-slate-900 to-slate-800">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  const status = copySettings?.enabled ? "enabled" : "disabled";
  const isAutoExecuting = copySettings?.enabled;

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 to-slate-800 p-4">
      <div className="max-w-2xl mx-auto space-y-6">
        {/* Header */}
        <div className="space-y-2">
          <h1 className="text-3xl font-bold text-white">Copy-Trading</h1>
          <p className="text-slate-400">
            Automatic trade execution with +30% pricing tier
          </p>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="bg-red-900/20 border border-red-500/50 rounded-lg p-4 flex gap-3">
            <AlertCircle className="h-5 w-5 text-red-500 flex-shrink-0 mt-0.5" />
            <div>
              <h3 className="font-semibold text-red-200">Error</h3>
              <p className="text-red-300 text-sm">{error}</p>
            </div>
          </div>
        )}

        {/* Status Card */}
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-6 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div
                className={`w-3 h-3 rounded-full ${
                  isAutoExecuting ? "bg-green-500" : "bg-slate-500"
                }`}
              ></div>
              <span className="text-sm font-medium text-slate-300">
                {isAutoExecuting ? "Enabled" : "Disabled"}
              </span>
            </div>
            <span className="text-2xl font-bold text-blue-400">+30%</span>
          </div>

          <p className="text-slate-300 text-sm">
            {isAutoExecuting
              ? "Your trades will execute automatically without approval."
              : "Enable copy-trading to trade automatically with 24/7 execution."}
          </p>

          {/* Action Buttons */}
          <div className="flex gap-3">
            {!isAutoExecuting ? (
              <button
                onClick={() => setShowEnableConfirm(true)}
                className="flex-1 bg-blue-600 hover:bg-blue-700 text-white font-semibold py-3 rounded-lg transition flex items-center justify-center gap-2"
              >
                <Toggle2 className="h-4 w-4" />
                Enable Copy-Trading
              </button>
            ) : (
              <>
                <button
                  onClick={() => router.push("/copy/settings")}
                  className="flex-1 bg-slate-700 hover:bg-slate-600 text-white font-semibold py-3 rounded-lg transition flex items-center justify-center gap-2"
                >
                  <Settings className="h-4 w-4" />
                  Settings
                </button>
                <button
                  onClick={() => setShowDisableConfirm(true)}
                  className="flex-1 bg-red-900/20 hover:bg-red-900/30 text-red-300 font-semibold py-3 rounded-lg transition border border-red-700/50 flex items-center justify-center gap-2"
                >
                  <Toggle2 className="h-4 w-4" />
                  Disable
                </button>
              </>
            )}
          </div>
        </div>

        {/* Pricing Information */}
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-6 space-y-4">
          <h2 className="font-semibold text-white flex items-center gap-2">
            <CheckCircle2 className="h-5 w-5 text-green-400" />
            Pricing Tier
          </h2>
          <div className="space-y-3">
            <div className="flex justify-between items-center">
              <span className="text-slate-300">Base Price</span>
              <span className="font-semibold text-white">£19.99/month</span>
            </div>
            <div className="border-t border-slate-700"></div>
            <div className="flex justify-between items-center">
              <span className="text-blue-300">Copy-Trading Markup</span>
              <span className="font-semibold text-blue-300">+£6.00 (+30%)</span>
            </div>
            <div className="border-t border-slate-700"></div>
            <div className="flex justify-between items-center">
              <span className="text-slate-200 font-semibold">Total Price</span>
              <span className="font-bold text-white text-lg">£25.99/month</span>
            </div>
          </div>
        </div>

        {/* Features */}
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-6 space-y-4">
          <h2 className="font-semibold text-white">Key Features</h2>
          <ul className="space-y-3">
            <li className="flex gap-3">
              <CheckCircle2 className="h-5 w-5 text-green-400 flex-shrink-0 mt-0.5" />
              <span className="text-slate-300">
                <strong className="text-white">100% Auto-Execution</strong> - Trades execute automatically without your approval
              </span>
            </li>
            <li className="flex gap-3">
              <CheckCircle2 className="h-5 w-5 text-green-400 flex-shrink-0 mt-0.5" />
              <span className="text-slate-300">
                <strong className="text-white">Risk Controls</strong> - Safeguards on leverage, position size, and daily losses
              </span>
            </li>
            <li className="flex gap-3">
              <CheckCircle2 className="h-5 w-5 text-green-400 flex-shrink-0 mt-0.5" />
              <span className="text-slate-300">
                <strong className="text-white">24/7 Trading</strong> - Signals executed round the clock
              </span>
            </li>
            <li className="flex gap-3">
              <CheckCircle2 className="h-5 w-5 text-green-400 flex-shrink-0 mt-0.5" />
              <span className="text-slate-300">
                <strong className="text-white">Pause on Breach</strong> - Automatically pauses if risk limits exceeded
              </span>
            </li>
          </ul>
        </div>

        {/* Risk Parameters */}
        {isAutoExecuting && copySettings && (
          <div className="bg-slate-800 border border-slate-700 rounded-lg p-6 space-y-4">
            <h2 className="font-semibold text-white">Risk Parameters</h2>
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-slate-700/50 rounded-lg p-3">
                <p className="text-xs text-slate-400">Max Position Size</p>
                <p className="font-semibold text-white">{copySettings.max_position_size_lot.toFixed(1)} lots</p>
              </div>
              <div className="bg-slate-700/50 rounded-lg p-3">
                <p className="text-xs text-slate-400">Max Daily Trades</p>
                <p className="font-semibold text-white">{copySettings.max_daily_trades}</p>
              </div>
              <div className="bg-slate-700/50 rounded-lg p-3">
                <p className="text-xs text-slate-400">Trades Today</p>
                <p className="font-semibold text-white">{copySettings.trades_today}/{copySettings.max_daily_trades}</p>
              </div>
              <div className="bg-slate-700/50 rounded-lg p-3">
                <p className="text-xs text-slate-400">Max Drawdown</p>
                <p className="font-semibold text-white">{copySettings.max_drawdown_percent.toFixed(1)}%</p>
              </div>
            </div>
          </div>
        )}

        {/* Confirmation Dialog - Enable */}
        {showEnableConfirm && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
            <div className="bg-slate-800 border border-slate-700 rounded-lg max-w-md w-full p-6 space-y-4">
              <h3 className="font-bold text-white text-lg">Enable Copy-Trading?</h3>
              <p className="text-slate-300">
                By enabling copy-trading, you accept automatic trade execution with the following:
              </p>
              <ul className="text-sm text-slate-300 space-y-2 list-disc list-inside">
                <li>+30% pricing markup (£25.99/month)</li>
                <li>Automatic trade execution without approval</li>
                <li>Risk controls and safeguards</li>
                <li>Auto-pause on risk breaches</li>
              </ul>
              <div className="flex gap-3">
                <button
                  onClick={() => setShowEnableConfirm(false)}
                  className="flex-1 bg-slate-700 hover:bg-slate-600 text-white font-semibold py-2 rounded-lg transition"
                  disabled={enableLoading}
                >
                  Cancel
                </button>
                <button
                  onClick={handleEnableCopyTrading}
                  className="flex-1 bg-blue-600 hover:bg-blue-700 text-white font-semibold py-2 rounded-lg transition disabled:opacity-50"
                  disabled={enableLoading}
                >
                  {enableLoading ? "Enabling..." : "Enable"}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Confirmation Dialog - Disable */}
        {showDisableConfirm && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
            <div className="bg-slate-800 border border-slate-700 rounded-lg max-w-md w-full p-6 space-y-4">
              <h3 className="font-bold text-white text-lg">Disable Copy-Trading?</h3>
              <p className="text-slate-300">
                Pending signals will require your approval after disabling. This action cannot be undone immediately.
              </p>
              <div className="flex gap-3">
                <button
                  onClick={() => setShowDisableConfirm(false)}
                  className="flex-1 bg-slate-700 hover:bg-slate-600 text-white font-semibold py-2 rounded-lg transition"
                  disabled={enableLoading}
                >
                  Cancel
                </button>
                <button
                  onClick={handleDisableCopyTrading}
                  className="flex-1 bg-red-600 hover:bg-red-700 text-white font-semibold py-2 rounded-lg transition disabled:opacity-50"
                  disabled={enableLoading}
                >
                  {enableLoading ? "Disabling..." : "Disable"}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
