"use client";

import React, { useState } from "react";
import { logger } from "@/lib/logger";

interface Device {
  id: string;
  name: string;
  is_active: boolean;
  created_at: string;
  last_seen: string;
}

interface DeviceListProps {
  /** List of devices */
  devices: Device[];
  /** Loading state */
  loading?: boolean;
  /** Error message if any */
  error?: string | null;
  /** JWT token for API calls */
  jwt?: string;
  /** Whether user can add more devices (based on tier limit) */
  canAddMore?: boolean;
  /** Message to show if cannot add more devices */
  limitMessage?: string;
  /** Callback when device is revoked */
  onDeviceRevoked?: (deviceId: string) => void;
  /** Callback to open add device modal */
  onOpenAddModal?: () => void;
}

/**
 * DeviceList Component
 *
 * Displays registered MT5 EA devices for the user.
 * Shows device name, status, creation date, last seen.
 * Allows renaming and revoking devices.
 *
 * @example
 * <DeviceList
 *   devices={devicesList}
 *   jwt={token}
 *   onDeviceRevoked={(id) => console.log("Revoked", id)}
 *   onOpenAddModal={() => setShowModal(true)}
 * />
 */
export const DeviceList: React.FC<DeviceListProps> = ({
  devices,
  loading = false,
  error = null,
  jwt,
  canAddMore = true,
  limitMessage = "Device limit reached",
  onDeviceRevoked,
  onOpenAddModal,
}) => {
  const [revoking, setRevoking] = useState<string | null>(null);

  const handleRevoke = async (deviceId: string) => {
    if (!jwt) return;
    if (!window.confirm("Are you sure? This device will lose API access.")) return;

    try {
      setRevoking(deviceId);

      const response = await fetch(`/api/v1/devices/${deviceId}/revoke`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${jwt}`,
          "Content-Type": "application/json",
        },
      });

      if (!response.ok) {
        throw new Error("Failed to revoke device");
      }

      logger.info("Device revoked", { deviceId });
      onDeviceRevoked?.(deviceId);
    } catch (err) {
      logger.error("Revoke failed", { deviceId, error: err });
    } finally {
      setRevoking(null);
    }
  };

  // Loading state
  if (loading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => (
          <div
            key={i}
            className="bg-white dark:bg-gray-800 rounded-lg p-4 animate-pulse"
          >
            <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-1/3 mb-2"></div>
            <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded w-1/2"></div>
          </div>
        ))}
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
        <p className="text-red-700 dark:text-red-300 text-sm">{error}</p>
      </div>
    );
  }

  // Empty state
  if (!devices || devices.length === 0) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg p-8 text-center border border-gray-200 dark:border-gray-700">
        <svg
          className="w-12 h-12 mx-auto text-gray-400 mb-4"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4"
          />
        </svg>
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-1">
          No devices registered
        </h3>
        <p className="text-gray-600 dark:text-gray-400 mb-4">
          Register your MT5 EA to get started with automated trading.
        </p>
        <button
          onClick={onOpenAddModal}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium"
        >
          Add Your First Device
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
          Registered Devices ({devices.length})
        </h3>
        <button
          onClick={onOpenAddModal}
          disabled={!canAddMore}
          className={`px-3 py-1 text-white text-sm rounded-lg font-medium transition-colors ${
            canAddMore
              ? "bg-blue-600 hover:bg-blue-700"
              : "bg-gray-400 cursor-not-allowed"
          }`}
          title={!canAddMore ? limitMessage : "Add a new device"}
        >
          + Add Device
        </button>
      </div>

      {/* Device list */}
      {devices.map((device) => (
        <div
          key={device.id}
          className="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700 hover:shadow-md transition-shadow"
        >
          <div className="flex items-start justify-between mb-3">
            <div className="flex-1">
              <h4 className="font-semibold text-gray-900 dark:text-white">
                {device.name}
              </h4>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                Created {new Date(device.created_at).toLocaleDateString()}
              </p>
            </div>

            {/* Status badge */}
            <span
              className={`px-2 py-1 rounded-full text-xs font-semibold ${
                device.is_active
                  ? "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300"
                  : "bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300"
              }`}
            >
              {device.is_active ? "Active" : "Inactive"}
            </span>
          </div>

          {/* Last seen */}
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
            Last seen:{" "}
            {device.last_seen
              ? new Date(device.last_seen).toLocaleString()
              : "Never"}
          </p>

          {/* Actions */}
          <div className="flex gap-2">
            <button
              disabled={revoking === device.id}
              onClick={() => handleRevoke(device.id)}
              className="flex-1 px-3 py-2 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 hover:bg-red-100 dark:hover:bg-red-900/40 text-sm font-medium rounded transition-colors disabled:opacity-50"
            >
              {revoking === device.id ? "Revoking..." : "Revoke"}
            </button>
          </div>
        </div>
      ))}
    </div>
  );
};

export default DeviceList;
