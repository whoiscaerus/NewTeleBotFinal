"use client";

import React, { useState } from "react";
import { logger } from "@/lib/logger";

interface Device {
  id: string;
  name: string;
  secret?: string;
}

interface AddDeviceModalProps {
  /** Is modal open */
  isOpen: boolean;
  /** JWT token for API calls */
  jwt?: string;
  /** Callback when device created */
  onDeviceCreated?: (device: Device) => void;
  /** Callback to close modal */
  onClose?: () => void;
  /** Loading state */
  loading?: boolean;
}

/**
 * AddDeviceModal Component
 *
 * Modal for registering a new MT5 EA device.
 * Displays device secret ONCE after creation.
 * Users must copy-to-clipboard; secret not shown again.
 *
 * Security: Device secret shown once; copy-to-clipboard only; not re-rendered.
 *
 * @example
 * <AddDeviceModal
 *   isOpen={showModal}
 *   jwt={token}
 *   onDeviceCreated={handleCreated}
 *   onClose={() => setShowModal(false)}
 * />
 */
export const AddDeviceModal: React.FC<AddDeviceModalProps> = ({
  isOpen,
  jwt,
  onDeviceCreated,
  onClose,
  loading = false,
}) => {
  const [deviceName, setDeviceName] = useState("");
  const [createdDevice, setCreatedDevice] = useState<Device | null>(null);
  const [copied, setCopied] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!jwt) return;
    if (!deviceName.trim()) {
      setError("Device name required");
      return;
    }

    try {
      setSubmitting(true);
      setError(null);

      const response = await fetch("/api/v1/devices", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${jwt}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ name: deviceName.trim() }),
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || "Failed to create device");
      }

      const device: Device = await response.json();
      setCreatedDevice(device);
      logger.info("Device created", { deviceId: device.id, name: device.name });
      onDeviceCreated?.(device);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to create device";
      setError(message);
      logger.error("Device creation failed", { error: err });
    } finally {
      setSubmitting(false);
    }
  };

  const handleCopySecret = async () => {
    if (!createdDevice?.secret) return;

    try {
      await navigator.clipboard.writeText(createdDevice.secret);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
      logger.info("Device secret copied to clipboard");
    } catch (err) {
      logger.error("Copy failed", { error: err });
    }
  };

  const handleClose = () => {
    setDeviceName("");
    setCreatedDevice(null);
    setCopied(false);
    setError(null);
    onClose?.();
  };

  return (
    <div className="fixed inset-0 bg-black/50 dark:bg-black/70 flex items-center justify-center z-50 p-4">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
            Register Device
          </h3>
          <button
            onClick={handleClose}
            className="text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
          >
            <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
              <path
                fillRule="evenodd"
                d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
                clipRule="evenodd"
              />
            </svg>
          </button>
        </div>

        {/* Body */}
        <div className="px-6 py-6 space-y-4">
          {/* Before device created - show form */}
          {!createdDevice ? (
            <>
              <p className="text-sm text-gray-600 dark:text-gray-400">
                Register your MT5 EA instance to enable automated trading.
              </p>

              {error && (
                <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3">
                  <p className="text-red-700 dark:text-red-300 text-sm">{error}</p>
                </div>
              )}

              <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Device Name
                  </label>
                  <input
                    type="text"
                    value={deviceName}
                    onChange={(e) => setDeviceName(e.target.value)}
                    placeholder="e.g., MT5-EA-1, TradingBot-GOLD"
                    disabled={submitting}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
                  />
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    Choose a unique name for identification
                  </p>
                </div>

                <button
                  type="submit"
                  disabled={submitting || !deviceName.trim()}
                  className="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors disabled:opacity-50"
                >
                  {submitting ? "Creating..." : "Create Device"}
                </button>
              </form>
            </>
          ) : (
            <>
              {/* After device created - show secret */}
              <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-4">
                <h4 className="font-semibold text-green-900 dark:text-green-300 mb-2">
                  ✓ Device Created!
                </h4>
                <p className="text-sm text-green-800 dark:text-green-200">
                  {createdDevice.name}
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Device Secret (shown once)
                </label>
                <div className="bg-gray-100 dark:bg-gray-700 rounded-lg p-4 font-mono text-sm break-all select-all text-gray-900 dark:text-gray-100">
                  {createdDevice.secret}
                </div>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
                  ⚠️ Save this secret securely. It won't be shown again.
                </p>
              </div>

              <div className="space-y-2">
                <button
                  onClick={handleCopySecret}
                  className={`w-full px-4 py-2 rounded-lg font-medium transition-colors ${
                    copied
                      ? "bg-green-500 text-white"
                      : "bg-gray-200 dark:bg-gray-700 text-gray-900 dark:text-white hover:bg-gray-300 dark:hover:bg-gray-600"
                  }`}
                >
                  {copied ? "✓ Copied!" : "Copy Secret"}
                </button>
                <button
                  onClick={handleClose}
                  className="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium"
                >
                  Done
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default AddDeviceModal;
