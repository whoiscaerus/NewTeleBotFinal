"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

interface AccountNavProps {
  /**
   * Current subscription tier to show active nav state
   * free | premium | vip | enterprise
   */
  tier?: string;
  /**
   * Current device count for gating display
   */
  deviceCount?: number;
}

/**
 * AccountNav Component
 *
 * Unified navigation between Billing and Devices pages.
 * Shows links to both pages with context about tier and device limits.
 *
 * @example
 * <AccountNav tier="premium" deviceCount={3} />
 */
export const AccountNav: React.FC<AccountNavProps> = ({ tier = "free", deviceCount = 0 }) => {
  const pathname = usePathname();

  // Device limits per tier
  const deviceLimits: Record<string, number> = {
    free: 1,
    premium: 5,
    vip: 10,
    enterprise: 999,
  };

  const limit = deviceLimits[tier as keyof typeof deviceLimits] || 1;
  const isBillingActive = pathname?.includes("/billing");
  const isDevicesActive = pathname?.includes("/devices");

  return (
    <nav className="flex gap-2 mb-6 border-b border-gray-200 dark:border-gray-700">
      {/* Billing Link */}
      <Link
        href="/billing"
        className={`py-3 px-4 font-medium border-b-2 transition-colors flex items-center gap-2 ${
          isBillingActive
            ? "border-blue-600 text-blue-600 dark:text-blue-400"
            : "border-transparent text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200"
        }`}
      >
        <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
          <path d="M4 4a2 2 0 00-2 2v4a2 2 0 002 2V6h10a2 2 0 00-2-2H4zm2 6a2 2 0 012-2h8a2 2 0 012 2v4a2 2 0 01-2 2H8a2 2 0 01-2-2v-4zm6 4a2 2 0 100-4 2 2 0 000 4z" />
        </svg>
        Billing
        {tier && tier !== "free" && (
          <span className="text-xs bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 px-2 py-1 rounded-full">
            {tier}
          </span>
        )}
      </Link>

      {/* Devices Link */}
      <Link
        href="/devices"
        className={`py-3 px-4 font-medium border-b-2 transition-colors relative flex items-center gap-2 ${
          isDevicesActive
            ? "border-blue-600 text-blue-600 dark:text-blue-400"
            : "border-transparent text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200"
        }`}
      >
        <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
          <path d="M10.707 2.293a1 1 0 00-1.414 0l-7 7a1 1 0 001.414 1.414L4 10.414V17a1 1 0 001 1h2a1 1 0 001-1v-2a1 1 0 011-1h2a1 1 0 011 1v2a1 1 0 001 1h2a1 1 0 001-1v-6.586l.293.293a1 1 0 001.414-1.414l-7-7z" />
        </svg>
        Devices
        {deviceCount !== undefined && (
          <span className={`text-xs px-2 py-1 rounded-full ${
            deviceCount >= limit
              ? "bg-red-100 dark:bg-red-900 text-red-800 dark:text-red-200"
              : "bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200"
          }`}>
            {deviceCount}/{limit}
          </span>
        )}
      </Link>
    </nav>
  );
};

export default AccountNav;
