"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { DeviceList } from "@/components/DeviceList";
import { AddDeviceModal } from "@/components/AddDeviceModal";
import AccountNav from "@/components/AccountNav";
import { useAuth } from "@/lib/auth";
import { logger } from "@/lib/logger";
import { useDeviceGating } from "@/lib/useDeviceGating";

interface Device {
  id: string;
  name: string;
  is_active: boolean;
  created_at: string;
  last_seen: string;
}

// Type for newly created devices from API (minimal response)
interface NewDevice {
  id: string;
  name: string;
  secret?: string;
}

interface Subscription {
  tier: "free" | "premium" | "vip" | "enterprise";
  status: "active" | "past_due" | "canceled";
}

/**
 * Devices Page (Mini App)
 *
 * Self-service device management for MT5 EAs.
 * Users can:
 * - List registered devices
 * - Register new devices (reveals secret once)
 * - Rename devices
 * - Revoke devices
 *
 * Security: Device secret shown once; copy-to-clipboard only; not re-rendered.
 * Integration: Fetches subscription tier for device count gating (PR-033).
 * Telemetry: miniapp_device_register_total, miniapp_device_revoke_total
 */
export default function DevicesPage() {
  const router = useRouter();
  const { user, isLoading: authLoading } = useAuth();
  const [devices, setDevices] = useState<Device[]>([]);
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAddModal, setShowAddModal] = useState(false);
  const [jwt, setJwt] = useState<string | null>(null);

  // Device gating based on tier
  const gating = useDeviceGating(
    subscription?.tier || "free",
    devices.length
  );

  // Fetch JWT from auth context
  useEffect(() => {
    // JWT would be fetched from auth provider in real implementation
    // For now, assume it's available
    if (!authLoading && user) {
      // fetchJWT();
    }
  }, [authLoading, user]);

  // Fetch devices and subscription
  const fetchData = async () => {
    if (!jwt) return;

    try {
      setLoading(true);

      // Fetch subscription for device limit context
      const subResponse = await fetch("/api/v1/billing/subscription", {
        headers: {
          Authorization: `Bearer ${jwt}`,
        },
      });

      if (subResponse.ok) {
        const subData = await subResponse.json();
        setSubscription(subData);
        logger.info("Subscription fetched", { tier: subData?.tier });
      }

      // Fetch devices
      const deviceResponse = await fetch("/api/v1/devices", {
        headers: {
          Authorization: `Bearer ${jwt}`,
        },
      });

      if (!deviceResponse.ok) {
        throw new Error("Failed to fetch devices");
      }

      const deviceData = await deviceResponse.json();
      setDevices(deviceData || []);
      setError(null);

      logger.info("Devices loaded", { count: deviceData.length });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load devices";
      logger.error("Devices load failed", { error: message });
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (jwt) {
      fetchData();
    }
  }, [jwt]);

  const handleDeviceCreated = (newDevice: NewDevice) => {
    // Convert NewDevice to full Device with default values
    const fullDevice: Device = {
      id: newDevice.id,
      name: newDevice.name,
      is_active: true,  // New devices are active by default
      created_at: new Date().toISOString(),
      last_seen: new Date().toISOString(),
    };
    setDevices((prev) => [...prev, fullDevice]);
    setShowAddModal(false);
    logger.info("Device added to list", {
      deviceId: newDevice.id,
      name: newDevice.name,
    });
  };

  const handleDeviceRevoked = (deviceId: string) => {
    setDevices((prev) => prev.filter((d) => d.id !== deviceId));
    logger.info("Device removed from list", { deviceId });
  };

  return (
    <div className="space-y-6 pb-8">
      {/* Account Navigation */}
      <AccountNav
        tier={subscription?.tier}
        deviceCount={devices.length}
      />

      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
          MT5 Devices
        </h1>
        <p className="text-gray-600 dark:text-gray-300 mt-1">
          Register and manage your EA instances for automated trading
        </p>
      </div>

      {/* Info Card */}
      <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
        <div className="flex items-start gap-3">
          <svg
            className="w-5 h-5 text-blue-600 dark:text-blue-400 mt-0.5 flex-shrink-0"
            fill="currentColor"
            viewBox="0 0 20 20"
          >
            <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
          </svg>
          <div>
            <h3 className="font-medium text-blue-900 dark:text-blue-300">
              Device Secret Security
            </h3>
            <p className="text-sm text-blue-800 dark:text-blue-200 mt-1">
              Device secrets are shown only once after registration. Store them
              securely in your EA configuration. Lost secrets can be recovered by
              revoking and re-registering the device.
            </p>
          </div>
        </div>
      </div>

      {/* Device Limit Warning (if at capacity) */}
      {gating.isFull && (
        <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg p-4">
          <div className="flex items-start gap-3">
            <svg
              className="w-5 h-5 text-amber-600 dark:text-amber-400 mt-0.5 flex-shrink-0"
              fill="currentColor"
              viewBox="0 0 20 20"
            >
              <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
            </svg>
            <div className="flex-1">
              <h3 className="font-medium text-amber-900 dark:text-amber-300">
                Device Limit Reached
              </h3>
              <p className="text-sm text-amber-800 dark:text-amber-200 mt-1">
                You've reached the {gating.limit}-device limit for your {gating.tier} plan.
                {gating.getUpgradeMessage() && (
                  <>
                    {" "}
                    <button
                      onClick={() => router.push("/billing")}
                      className="font-semibold underline hover:no-underline"
                    >
                      {gating.getUpgradeMessage()}
                    </button>
                  </>
                )}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Device Usage Indicator (if near capacity) */}
      {!gating.isFull && gating.percentUsed >= 75 && (
        <div className="bg-orange-50 dark:bg-orange-900/20 border border-orange-200 dark:border-orange-800 rounded-lg p-4">
          <div className="flex items-start gap-3">
            <svg
              className="w-5 h-5 text-orange-600 dark:text-orange-400 mt-0.5 flex-shrink-0"
              fill="currentColor"
              viewBox="0 0 20 20"
            >
              <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
            </svg>
            <div>
              <h3 className="font-medium text-orange-900 dark:text-orange-300">
                Approaching Device Limit
              </h3>
              <p className="text-sm text-orange-800 dark:text-orange-200 mt-1">
                You have {gating.remaining} device slot{gating.remaining === 1 ? "" : "s"} remaining.
                {gating.getUpgradeMessage() && (
                  <>
                    {" "}
                    <button
                      onClick={() => router.push("/billing")}
                      className="font-semibold underline hover:no-underline"
                    >
                      {gating.getUpgradeMessage()}
                    </button>
                  </>
                )}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Loading State */}
      {loading && (
        <div className="bg-white dark:bg-gray-800 rounded-lg p-8 text-center">
          <div className="inline-block animate-spin">
            <svg
              className="w-8 h-8 text-blue-600"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
              />
            </svg>
          </div>
          <p className="text-gray-500 mt-2">Loading devices...</p>
        </div>
      )}

      {/* Error State */}
      {error && !loading && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
          <div className="flex items-start gap-3">
            <svg
              className="w-5 h-5 text-red-600 dark:text-red-400 mt-0.5 flex-shrink-0"
              fill="currentColor"
              viewBox="0 0 20 20"
            >
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
            </svg>
            <div>
              <h3 className="font-medium text-red-800 dark:text-red-200">
                Failed to load devices
              </h3>
              <p className="text-red-700 dark:text-red-300 text-sm mt-1">{error}</p>
            </div>
          </div>
        </div>
      )}

      {/* Device List */}
      {!loading && (
        <DeviceList
          devices={devices}
          jwt={jwt || undefined}
          canAddMore={gating.canAddMore}
          limitMessage={`Device limit reached (${gating.currentCount}/${gating.limit})`}
          onOpenAddModal={() => setShowAddModal(true)}
          onDeviceRevoked={handleDeviceRevoked}
        />
      )}

      {/* Add Device Modal */}
      <AddDeviceModal
        isOpen={showAddModal}
        jwt={jwt || undefined}
        onDeviceCreated={handleDeviceCreated}
        onClose={() => setShowAddModal(false)}
      />

      {/* How to Use */}
      <div className="bg-white dark:bg-gray-800 rounded-lg p-6 shadow-sm">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          How to Set Up Your EA
        </h3>
        <ol className="space-y-3 text-gray-700 dark:text-gray-300">
          <li className="flex gap-3">
            <span className="flex-shrink-0 w-6 h-6 rounded-full bg-blue-600 text-white flex items-center justify-center text-sm font-semibold">
              1
            </span>
            <span>Click "Add Device" above to register your MT5 EA</span>
          </li>
          <li className="flex gap-3">
            <span className="flex-shrink-0 w-6 h-6 rounded-full bg-blue-600 text-white flex items-center justify-center text-sm font-semibold">
              2
            </span>
            <span>Copy the device secret and store it securely</span>
          </li>
          <li className="flex gap-3">
            <span className="flex-shrink-0 w-6 h-6 rounded-full bg-blue-600 text-white flex items-center justify-center text-sm font-semibold">
              3
            </span>
            <span>
              Add the device ID and secret to your EA configuration file
            </span>
          </li>
          <li className="flex gap-3">
            <span className="flex-shrink-0 w-6 h-6 rounded-full bg-blue-600 text-white flex items-center justify-center text-sm font-semibold">
              4
            </span>
            <span>
              Start your EA - it will authenticate and begin polling for signals
            </span>
          </li>
        </ol>
      </div>
    </div>
  );
}
