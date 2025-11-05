"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useTelegram } from "@/app/_providers/TelegramProvider";
import { apiGet, apiPost, apiDelete } from "@/lib/api";
import { logger } from "@/lib/logger";
import AccountNav from "@/components/AccountNav";
import InvoiceList from "@/components/InvoiceList";

interface Subscription {
  tier: "free" | "premium" | "vip" | "enterprise";
  status: "active" | "past_due" | "canceled";
  current_period_start: string;
  current_period_end: string;
  price_usd_monthly: number;
}

interface Device {
  id: string;
  name: string;
  device_key: string;
  is_active: boolean;
  created_at: string;
  last_seen: string;
  secret?: string; // Only shown once on creation
}

/**
 * Mini App Billing Page
 *
 * Displays subscription status, plan details, and device management.
 * Users can view current tier, upgrade, manage billing, and register EAs.
 *
 * @example
 * Navigate to /billing → see tier + expiry → upgrade or manage devices
 */
export default function BillingPage() {
  const router = useRouter();
  const { jwt, isLoading: authLoading, error: authError } = useTelegram();
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [devices, setDevices] = useState<Device[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAddDevice, setShowAddDevice] = useState(false);
  const [newDeviceName, setNewDeviceName] = useState("");
  const [copiedSecret, setCopiedSecret] = useState<string | null>(null);

  // Fetch subscription and devices
  const fetchData = async () => {
    if (!jwt) return;

    try {
      setLoading(true);

      // Fetch subscription (JWT handled automatically by apiGet)
      const subData = await apiGet<Subscription>("/api/v1/billing/subscription");
      setSubscription(subData || null);

      // Fetch devices
      const devicesData = await apiGet<Device[]>("/api/v1/devices");
      setDevices(devicesData || []);

      setError(null);
      logger.info("Billing data fetched", {
        tier: subData?.tier,
        devices_count: devicesData?.length || 0,
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to fetch billing data";
      setError(message);
      logger.error("Failed to fetch billing data", { error: err });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!authLoading && jwt) {
      fetchData();
    }
  }, [authLoading, jwt]);

  // Add new device
  const handleAddDevice = async () => {
    if (!jwt || !newDeviceName.trim()) return;

    try {
      const response = await apiPost<Device>(
        "/api/v1/devices",
        { name: newDeviceName }
      );

      if (response) {
        setDevices((prev) => [...prev, response]);
        setCopiedSecret(response.secret || "");
        setNewDeviceName("");

        logger.info("Device registered", {
          device_id: response.id,
          device_name: newDeviceName,
        });
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to register device";
      logger.error("Failed to register device", { error: err });
      alert(`Error: ${message}`);
    }
  };

  // Revoke device
  const handleRevokeDevice = async (deviceId: string) => {
    if (!jwt) return;

    if (!window.confirm("Revoke this device? The EA will need to re-register.")) return;

    try {
      await apiDelete(`/api/v1/devices/${deviceId}`);

      setDevices((prev) => prev.filter((d) => d.id !== deviceId));

      logger.info("Device revoked", { device_id: deviceId });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to revoke device";
      logger.error("Failed to revoke device", { device_id: deviceId, error: err });
      alert(`Error: ${message}`);
    }
  };

  // Copy secret to clipboard
  const handleCopySecret = (secret: string) => {
    navigator.clipboard.writeText(secret);
    setCopiedSecret(secret);
    setTimeout(() => setCopiedSecret(null), 2000);
  };

  // Auth loading
  if (authLoading) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-blue-900 to-blue-800 flex items-center justify-center">
        <div className="text-center text-white">
          <div className="animate-spin rounded-full h-12 w-12 border-4 border-blue-300 border-t-white mx-auto mb-4" />
          <p>Loading billing...</p>
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
          <p>Fetching billing...</p>
        </div>
      </div>
    );
  }

  // Main content
  return (
    <div className="min-h-screen bg-gradient-to-b from-blue-900 to-blue-800 p-4 pb-20">
      <div className="max-w-md mx-auto">
        <h1 className="text-2xl font-bold text-white mb-2">Account & Billing</h1>

        {/* Account Navigation */}
        <div className="mb-6">
          <AccountNav
            tier={subscription?.tier}
            deviceCount={devices.length}
          />
        </div>

        {/* Subscription Card */}
        {subscription && (
          <div className="bg-gradient-to-br from-purple-500 to-purple-600 rounded-lg p-4 mb-6 text-white shadow-lg">
            <div className="flex justify-between items-start mb-4">
              <div>
                <p className="text-sm text-purple-100 mb-1">Current Plan</p>
                <p className="text-2xl font-bold capitalize">{subscription.tier}</p>
              </div>
              <div
                className={`px-3 py-1 rounded-full text-xs font-semibold ${
                  subscription.status === "active"
                    ? "bg-green-500 bg-opacity-30 text-green-200"
                    : "bg-red-500 bg-opacity-30 text-red-200"
                }`}
              >
                {subscription.status === "active" ? "✅ Active" : "⚠️ Past Due"}
              </div>
            </div>

            {/* Expiry countdown */}
            <div className="bg-purple-900 bg-opacity-40 rounded p-3 mb-4">
              <p className="text-xs text-purple-200 mb-1">Next billing date</p>
              <p className="font-mono font-semibold">
                {new Date(subscription.current_period_end).toLocaleDateString()}
              </p>
            </div>

            {/* Price */}
            <p className="text-lg">
              ${subscription.price_usd_monthly}
              <span className="text-sm text-purple-200">/month</span>
            </p>

            {/* Upgrade button */}
            {subscription.tier === "free" && (
              <button className="w-full mt-4 px-4 py-2 bg-white text-purple-600 rounded-lg font-semibold hover:bg-gray-100 transition-colors">
                🚀 Upgrade Plan
              </button>
            )}
          </div>
        )}

        {/* Invoice History Section */}
        <div className="mb-6">
          <h2 className="text-xl font-bold text-white mb-4">📜 Invoice History</h2>
          {jwt && <InvoiceList jwt={jwt} />}
        </div>

        {/* Devices Section */}
        <div className="mb-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-xl font-bold text-white">EA Devices</h2>
            {devices.length > 0 && (
              <button
                onClick={() => router.push("/devices")}
                className="text-sm text-blue-300 hover:text-blue-200 font-medium underline"
              >
                View All →
              </button>
            )}
          </div>

          {/* Add Device Form */}
          {!showAddDevice ? (
            <button
              onClick={() => setShowAddDevice(true)}
              className="w-full px-4 py-3 bg-blue-500 text-white rounded-lg font-semibold hover:bg-blue-600 transition-colors mb-4"
            >
              ➕ Register New Device
            </button>
          ) : (
            <div className="bg-blue-900 bg-opacity-40 border border-blue-400 border-opacity-30 rounded-lg p-4 mb-4">
              <input
                type="text"
                placeholder="Device name (e.g., EA-01)"
                value={newDeviceName}
                onChange={(e) => setNewDeviceName(e.target.value)}
                className="w-full px-3 py-2 rounded bg-blue-800 text-white placeholder-gray-400 text-sm mb-3 focus:outline-none focus:ring-2 focus:ring-blue-300"
              />
              <div className="flex gap-2">
                <button
                  onClick={handleAddDevice}
                  className="flex-1 px-3 py-2 bg-green-500 text-white rounded-lg text-sm font-semibold hover:bg-green-600 transition-colors"
                >
                  Register
                </button>
                <button
                  onClick={() => setShowAddDevice(false)}
                  className="flex-1 px-3 py-2 bg-gray-600 text-white rounded-lg text-sm font-semibold hover:bg-gray-700 transition-colors"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {/* Device List */}
          {devices.length === 0 ? (
            <div className="bg-blue-900 bg-opacity-30 border border-blue-400 border-opacity-20 rounded-lg p-4 text-center text-gray-300 text-sm">
              No devices registered yet. Add one to connect your EA.
            </div>
          ) : (
            <div className="space-y-3">
              {devices.map((device) => (
                <div
                  key={device.id}
                  className="bg-blue-900 bg-opacity-40 border border-blue-400 border-opacity-30 rounded-lg p-4"
                >
                  <div className="flex justify-between items-start mb-2">
                    <div>
                      <p className="text-white font-semibold">{device.name}</p>
                      <p
                        className={`text-xs ${
                          device.is_active ? "text-green-300" : "text-gray-400"
                        }`}
                      >
                        {device.is_active ? "🟢 Active" : "⚪ Offline"}
                      </p>
                    </div>
                  </div>

                  {/* Secret (shown once) */}
                  {device.secret && (
                    <div className="bg-red-500 bg-opacity-20 border border-red-400 border-opacity-40 rounded p-2 mb-3 text-sm">
                      <p className="text-xs text-red-200 mb-1">🔐 Secret (shown once):</p>
                      <div className="flex justify-between items-center gap-2">
                        <code className="text-white font-mono text-xs break-all">
                          {device.secret}
                        </code>
                        <button
                          onClick={() => handleCopySecret(device.secret!)}
                          className="px-2 py-1 bg-red-500 hover:bg-red-600 text-white text-xs rounded whitespace-nowrap"
                        >
                          {copiedSecret === device.secret ? "✅" : "📋"}
                        </button>
                      </div>
                    </div>
                  )}

                  {/* Last seen */}
                  <p className="text-xs text-gray-400 mb-3">
                    Last seen: {new Date(device.last_seen).toLocaleString()}
                  </p>

                  {/* Revoke button */}
                  <button
                    onClick={() => handleRevokeDevice(device.id)}
                    className="w-full px-2 py-1 bg-red-500 text-white text-xs rounded hover:bg-red-600 transition-colors"
                  >
                    🗑️ Revoke Device
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Error message */}
        {error && (
          <div className="bg-red-500 bg-opacity-20 border border-red-400 rounded-lg p-4 text-red-200 text-sm">
            {error}
          </div>
        )}
      </div>
    </div>
  );
}
