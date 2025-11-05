"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, CheckCircle2, Clock, Pause, Play, Eye, EyeOff } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { logger } from "@/lib/logger";
import { api } from "@/lib/api";

interface RiskSettings {
  max_leverage: number;
  max_per_trade_risk_percent: number;
  total_exposure_percent: number;
  daily_stop_percent: number;
}

interface CopyStatus {
  enabled: boolean;
  is_paused: boolean;
  pause_reason: string | null;
  paused_at: string | null;
  last_breach_at: string | null;
  last_breach_reason: string | null;
  risk_parameters: RiskSettings;
  consent_version: string;
  consent_accepted_at: string | null;
}

/**
 * Copy-Trading Settings Page (Mini App)
 *
 * Risk & Compliance Controls (PR-046)
 *
 * Allows users to:
 * - View current risk parameters
 * - Update risk parameters (max leverage, max trade risk, exposure, daily stop)
 * - View pause/breach status
 * - Manually pause/resume copy-trading
 * - View consent acceptance history
 * - Accept new disclosure versions
 *
 * Features:
 * - Real-time status updates
 * - Pause confirmation on manual pause
 * - Auto-resume availability after 24 hours
 * - Risk parameter validation
 * - Visual breach indicators
 */
export default function CopySettingsPage() {
  const router = useRouter();
  const { user, isLoading: authLoading } = useAuth();

  const [status, setStatus] = useState<CopyStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Form state
  const [formData, setFormData] = useState<Partial<RiskSettings>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showConfirmPause, setShowConfirmPause] = useState(false);
  const [showSettings, setShowSettings] = useState(false);

  useEffect(() => {
    if (authLoading) return;
    if (!user) {
      router.push("/");
      return;
    }

    fetchStatus();
  }, [user, authLoading]);

  const fetchStatus = async () => {
    try {
      setLoading(true);
      const response: any = await api.get("/api/v1/copy/status");
      setStatus(response);
      setFormData(response.risk_parameters || {});
      setError(null);
    } catch (err) {
      logger.error("Failed to fetch copy status", { error: err });
      setError("Failed to load copy-trading status");
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateRiskSettings = async () => {
    try {
      setIsSubmitting(true);
      setError(null);

      // Validate ranges
      if (
        (formData.max_leverage !== undefined && (formData.max_leverage < 1 || formData.max_leverage > 10)) ||
        (formData.max_per_trade_risk_percent !== undefined && (formData.max_per_trade_risk_percent < 0.1 || formData.max_per_trade_risk_percent > 10)) ||
        (formData.total_exposure_percent !== undefined && (formData.total_exposure_percent < 20 || formData.total_exposure_percent > 100)) ||
        (formData.daily_stop_percent !== undefined && (formData.daily_stop_percent < 1 || formData.daily_stop_percent > 50))
      ) {
        setError("Invalid parameter ranges");
        return;
      }

      const response: any = await api.put("/api/v1/copy/risk", formData);
      setStatus(prev => prev ? { ...prev, risk_parameters: response.risk_parameters } : null);
      setSuccess("Risk settings updated successfully");
      setShowSettings(false);

      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      logger.error("Failed to update risk settings", { error: err });
      setError("Failed to update settings");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handlePauseCopyTrading = async () => {
    try {
      setIsSubmitting(true);
      setError(null);

      await api.post("/api/v1/copy/pause", {});
      setStatus(prev => prev ? { ...prev, is_paused: true, pause_reason: "manual_pause" } : null);
      setSuccess("Copy-trading paused");
      setShowConfirmPause(false);

      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      logger.error("Failed to pause copy trading", { error: err });
      setError("Failed to pause copy-trading");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleResumeCopyTrading = async () => {
    try {
      setIsSubmitting(true);
      setError(null);

      await api.post("/api/v1/copy/resume", {});
      setStatus(prev => prev ? { ...prev, is_paused: false, pause_reason: null } : null);
      setSuccess("Copy-trading resumed");

      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      logger.error("Failed to resume copy trading", { error: err });
      setError("Failed to resume copy-trading");
    } finally {
      setIsSubmitting(false);
    }
  };

  if (authLoading || loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-slate-900">
        <div className="text-white">Loading...</div>
      </div>
    );
  }

  if (!status) {
    return (
      <div className="min-h-screen bg-slate-900 p-4">
        <div className="bg-red-900/30 border border-red-700 rounded-lg p-4 text-red-200">
          {error || "Failed to load copy-trading settings"}
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-900 text-white p-4 pb-20">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Pause className="w-6 h-6" />
          Copy-Trading Settings
        </h1>
        <p className="text-slate-400 mt-1">Risk parameters & compliance controls (PR-046)</p>
      </div>

      {/* Status Alerts */}
      {error && (
        <div className="mb-4 bg-red-900/30 border border-red-700 rounded-lg p-4 flex items-start gap-3">
          <AlertCircle className="w-5 h-5 mt-0.5 flex-shrink-0" />
          <div>
            <div className="font-semibold">Error</div>
            <div className="text-sm text-red-200">{error}</div>
          </div>
        </div>
      )}

      {success && (
        <div className="mb-4 bg-green-900/30 border border-green-700 rounded-lg p-4 flex items-start gap-3">
          <CheckCircle2 className="w-5 h-5 mt-0.5 flex-shrink-0" />
          <div className="text-sm text-green-200">{success}</div>
        </div>
      )}

      {/* Status Card */}
      <div className="bg-slate-800 border border-slate-700 rounded-lg p-6 mb-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">Copy-Trading Status</h2>
          {status.enabled ? (
            <div className={`flex items-center gap-2 px-3 py-1 rounded-full ${status.is_paused ? "bg-yellow-900/30 text-yellow-200" : "bg-green-900/30 text-green-200"}`}>
              {status.is_paused ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
              {status.is_paused ? "Paused" : "Active"}
            </div>
          ) : (
            <div className="px-3 py-1 rounded-full bg-slate-700 text-slate-300">Disabled</div>
          )}
        </div>

        <div className="space-y-2 text-sm">
          {status.is_paused && (
            <div className="bg-yellow-900/20 border border-yellow-700/50 rounded p-3">
              <div className="font-semibold text-yellow-200">🛑 Paused: {status.pause_reason}</div>
              {status.last_breach_reason && (
                <div className="text-yellow-200/80 text-xs mt-1">Last breach: {status.last_breach_reason}</div>
              )}
              {status.paused_at && (
                <div className="text-yellow-200/80 text-xs mt-1">
                  <Clock className="w-3 h-3 inline mr-1" />
                  Auto-resume: {new Date(new Date(status.paused_at).getTime() + 24 * 60 * 60 * 1000).toLocaleString()}
                </div>
              )}
            </div>
          )}

          {status.last_breach_at && (
            <div>
              <span className="text-slate-400">Last Breach:</span>
              <div className="text-red-300">{new Date(status.last_breach_at).toLocaleString()}</div>
            </div>
          )}

          <div>
            <span className="text-slate-400">Consent Version:</span>
            <div className="text-blue-300">v{status.consent_version}</div>
          </div>
        </div>

        {/* Pause/Resume Buttons */}
        {status.enabled && (
          <div className="flex gap-2 mt-4">
            {!status.is_paused ? (
              <button
                onClick={() => setShowConfirmPause(true)}
                className="flex-1 bg-yellow-600 hover:bg-yellow-700 text-white py-2 rounded font-medium transition"
              >
                Pause Trading
              </button>
            ) : (
              <button
                onClick={handleResumeCopyTrading}
                disabled={isSubmitting}
                className="flex-1 bg-green-600 hover:bg-green-700 text-white py-2 rounded font-medium transition disabled:opacity-50"
              >
                {isSubmitting ? "Resuming..." : "Resume Trading"}
              </button>
            )}
          </div>
        )}
      </div>

      {/* Risk Parameters */}
      <div className="bg-slate-800 border border-slate-700 rounded-lg p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">Risk Parameters</h2>
          {!showSettings && (
            <button
              onClick={() => setShowSettings(true)}
              className="text-blue-400 hover:text-blue-300 text-sm font-medium"
            >
              Edit
            </button>
          )}
        </div>

        {!showSettings ? (
          <div className="grid grid-cols-2 gap-4">
            <div className="bg-slate-700/50 rounded p-4">
              <div className="text-slate-400 text-sm">Max Leverage</div>
              <div className="text-2xl font-bold text-blue-300">{status.risk_parameters.max_leverage}x</div>
            </div>
            <div className="bg-slate-700/50 rounded p-4">
              <div className="text-slate-400 text-sm">Max Trade Risk</div>
              <div className="text-2xl font-bold text-blue-300">{status.risk_parameters.max_per_trade_risk_percent}%</div>
            </div>
            <div className="bg-slate-700/50 rounded p-4">
              <div className="text-slate-400 text-sm">Total Exposure</div>
              <div className="text-2xl font-bold text-blue-300">{status.risk_parameters.total_exposure_percent}%</div>
            </div>
            <div className="bg-slate-700/50 rounded p-4">
              <div className="text-slate-400 text-sm">Daily Stop Loss</div>
              <div className="text-2xl font-bold text-blue-300">{status.risk_parameters.daily_stop_percent}%</div>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-slate-400 mb-2">Max Leverage (1x - 10x)</label>
              <input
                type="number"
                min="1"
                max="10"
                step="0.5"
                value={formData.max_leverage || ""}
                onChange={(e) => setFormData({ ...formData, max_leverage: parseFloat(e.target.value) })}
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-white focus:outline-none focus:border-blue-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-400 mb-2">Max Trade Risk % (0.1% - 10%)</label>
              <input
                type="number"
                min="0.1"
                max="10"
                step="0.1"
                value={formData.max_per_trade_risk_percent || ""}
                onChange={(e) => setFormData({ ...formData, max_per_trade_risk_percent: parseFloat(e.target.value) })}
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-white focus:outline-none focus:border-blue-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-400 mb-2">Total Exposure % (20% - 100%)</label>
              <input
                type="number"
                min="20"
                max="100"
                step="1"
                value={formData.total_exposure_percent || ""}
                onChange={(e) => setFormData({ ...formData, total_exposure_percent: parseFloat(e.target.value) })}
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-white focus:outline-none focus:border-blue-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-400 mb-2">Daily Stop Loss % (1% - 50%)</label>
              <input
                type="number"
                min="1"
                max="50"
                step="1"
                value={formData.daily_stop_percent || ""}
                onChange={(e) => setFormData({ ...formData, daily_stop_percent: parseFloat(e.target.value) })}
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-white focus:outline-none focus:border-blue-500"
              />
            </div>

            <div className="flex gap-2">
              <button
                onClick={handleUpdateRiskSettings}
                disabled={isSubmitting}
                className="flex-1 bg-blue-600 hover:bg-blue-700 text-white py-2 rounded font-medium transition disabled:opacity-50"
              >
                {isSubmitting ? "Saving..." : "Save Changes"}
              </button>
              <button
                onClick={() => setShowSettings(false)}
                className="flex-1 bg-slate-700 hover:bg-slate-600 text-white py-2 rounded font-medium transition"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Risk Explanation */}
      <div className="mt-6 bg-slate-800/50 border border-slate-700/50 rounded-lg p-4 text-sm text-slate-400">
        <div className="font-semibold text-slate-300 mb-2">⚠️ Risk Protection</div>
        <ul className="space-y-1 text-xs">
          <li>• <strong>Max Leverage:</strong> Maximum position size relative to account equity</li>
          <li>• <strong>Max Trade Risk:</strong> Maximum loss allowed per single trade</li>
          <li>• <strong>Total Exposure:</strong> Maximum combined value of all open positions</li>
          <li>• <strong>Daily Stop Loss:</strong> Maximum cumulative losses per day before auto-pause</li>
        </ul>
      </div>

      {/* Pause Confirmation Modal */}
      {showConfirmPause && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
          <div className="bg-slate-800 border border-slate-700 rounded-lg p-6 max-w-sm">
            <h3 className="text-lg font-bold mb-2">Pause Copy-Trading?</h3>
            <p className="text-slate-300 text-sm mb-4">
              Copy-trading will be paused. You can resume manually or after 24 hours.
            </p>
            <div className="flex gap-2">
              <button
                onClick={handlePauseCopyTrading}
                disabled={isSubmitting}
                className="flex-1 bg-red-600 hover:bg-red-700 text-white py-2 rounded font-medium transition disabled:opacity-50"
              >
                {isSubmitting ? "Pausing..." : "Pause"}
              </button>
              <button
                onClick={() => setShowConfirmPause(false)}
                className="flex-1 bg-slate-700 hover:bg-slate-600 text-white py-2 rounded font-medium transition"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
