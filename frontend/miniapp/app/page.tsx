"use client";

/**
 * Mini App Landing Page
 *
 * Shows user info, loading state, and navigation
 */

import { useEffect, useState } from "react";
import { useTelegram } from "./_providers/TelegramProvider";
import { apiGet } from "./lib/api";

interface UserProfile {
  id: string;
  email: string;
  name: string;
}

export default function Home() {
  const { user, jwt, isLoading, error, isDark, haptic } = useTelegram();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loadingProfile, setLoadingProfile] = useState(false);

  // Load user profile after JWT obtained
  useEffect(() => {
    if (jwt) {
      loadProfile();
    }
  }, [jwt]);

  const loadProfile = async () => {
    try {
      setLoadingProfile(true);
      const data = await apiGet<UserProfile>("/api/v1/auth/me");
      setProfile(data);
      haptic.success?.();
    } catch (err) {
      console.error("Failed to load profile:", err);
      haptic.error?.();
    } finally {
      setLoadingProfile(false);
    }
  };

  if (isLoading) {
    return (
      <div className={`flex items-center justify-center min-h-screen ${isDark ? "bg-gray-900" : "bg-white"}`}>
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500 mx-auto mb-4"></div>
          <p className={isDark ? "text-gray-300" : "text-gray-600"}>Initializing Mini App...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={`flex items-center justify-center min-h-screen ${isDark ? "bg-gray-900" : "bg-white"}`}>
        <div className="text-center">
          <p className="text-red-500 font-semibold mb-2">❌ Error</p>
          <p className={isDark ? "text-gray-300" : "text-gray-600"}>{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className={`min-h-screen ${isDark ? "bg-gray-900 text-white" : "bg-white text-gray-900"}`}>
      {/* Header */}
      <header className={`${isDark ? "bg-gray-800" : "bg-gray-100"} p-4 border-b ${isDark ? "border-gray-700" : "border-gray-200"}`}>
        <h1 className="text-2xl font-bold">📊 Trading Platform</h1>
      </header>

      {/* Main Content */}
      <main className="p-4 space-y-4">
        {/* User Info Card */}
        {user && (
          <div className={`${isDark ? "bg-gray-800" : "bg-gray-50"} rounded-lg p-4 border ${isDark ? "border-gray-700" : "border-gray-200"}`}>
            <h2 className="text-lg font-semibold mb-2">Welcome!</h2>
            <div className="space-y-1 text-sm">
              <p>
                <span className="font-medium">Name:</span> {user.first_name} {user.last_name || ""}
              </p>
              {user.username && (
                <p>
                  <span className="font-medium">Username:</span> @{user.username}
                </p>
              )}
              <p>
                <span className="font-medium">User ID:</span> {user.id}
              </p>
              {user.is_premium && (
                <p className="text-yellow-500 font-semibold">⭐ Premium Member</p>
              )}
            </div>
          </div>
        )}

        {/* Profile Card */}
        {profile && (
          <div className={`${isDark ? "bg-gray-800" : "bg-gray-50"} rounded-lg p-4 border ${isDark ? "border-gray-700" : "border-gray-200"}`}>
            <h2 className="text-lg font-semibold mb-2">Profile</h2>
            <div className="space-y-1 text-sm">
              <p>
                <span className="font-medium">Email:</span> {profile.email}
              </p>
              <p>
                <span className="font-medium">User ID:</span> {profile.id}
              </p>
            </div>
          </div>
        )}

        {/* Navigation Buttons */}
        <div className="grid grid-cols-2 gap-3 mt-6">
          <button
            onClick={() => haptic.medium?.()}
            className="py-3 px-4 bg-blue-500 text-white rounded-lg font-semibold hover:bg-blue-600 transition"
          >
            📈 Signals
          </button>
          <button
            onClick={() => haptic.medium?.()}
            className="py-3 px-4 bg-green-500 text-white rounded-lg font-semibold hover:bg-green-600 transition"
          >
            💳 Billing
          </button>
          <button
            onClick={() => haptic.medium?.()}
            className="py-3 px-4 bg-purple-500 text-white rounded-lg font-semibold hover:bg-purple-600 transition"
          >
            ⚙️ Settings
          </button>
          <button
            onClick={() => haptic.medium?.()}
            className="py-3 px-4 bg-gray-500 text-white rounded-lg font-semibold hover:bg-gray-600 transition"
          >
            ℹ️ Help
          </button>
        </div>

        {/* Debug Info */}
        <div className={`${isDark ? "bg-gray-800 border-gray-700" : "bg-gray-50 border-gray-200"} rounded-lg p-4 border mt-6`}>
          <p className="text-xs font-mono">
            <span className="font-semibold">JWT Present:</span> {jwt ? "✅" : "❌"}
          </p>
          <p className="text-xs font-mono">
            <span className="font-semibold">Profile Loaded:</span> {profile ? "✅" : loadingProfile ? "⏳" : "❌"}
          </p>
          <p className="text-xs font-mono">
            <span className="font-semibold">Theme:</span> {isDark ? "🌙 Dark" : "☀️ Light"}
          </p>
        </div>
      </main>
    </div>
  );
}
