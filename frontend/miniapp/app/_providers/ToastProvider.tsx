"use client";

/**
 * Toast Provider Component
 *
 * Wraps the app with ToastContainer for react-toastify.
 * Provides dark mode support and mobile-optimized styling.
 *
 * @example
 * <ToastProvider>
 *   <YourContent />
 * </ToastProvider>
 */

import React from "react";
import { ToastContainer } from "react-toastify";
import "react-toastify/dist/ReactToastify.css";

export function ToastProvider({ children }: { children: React.ReactNode }) {
  return (
    <>
      {children}
      <ToastContainer
        position="bottom-center"
        autoClose={3000}
        hideProgressBar={false}
        newestOnTop={false}
        closeOnClick
        rtl={false}
        pauseOnFocusLoss
        draggable
        pauseOnHover
        theme="dark"
        // Mobile optimizations
        limit={3}  // Max 3 toasts at once
        style={{
          zIndex: 9999,
        }}
      />
    </>
  );
}
