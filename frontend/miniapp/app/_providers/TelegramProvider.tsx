"use client";

/**
 * Telegram WebApp Provider
 *
 * Handles:
 * - Telegram SDK initialization
 * - initData parsing and JWT exchange
 * - Theme syncing with Telegram UI
 * - Safe viewport configuration
 * - Haptic feedback
 */

import React, { createContext, ReactNode, useContext, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

// Types for Telegram WebApp
interface TelegramUser {
  id: number;
  is_bot: boolean;
  first_name: string;
  last_name?: string;
  username?: string;
  language_code?: string;
  is_premium?: boolean;
  added_to_attachment_menu?: boolean;
  allows_write_to_pm?: boolean;
  photo_url?: string;
}

interface TelegramWebApp {
  ready: () => void;
  expand: () => void;
  close: () => void;
  MainButton: {
    text: string;
    color: string;
    textColor: string;
    isVisible: boolean;
    isActive: boolean;
    setText: (text: string) => void;
    show: () => void;
    hide: () => void;
    enable: () => void;
    disable: () => void;
    onClick: (callback: () => void) => void;
  };
  HapticFeedback: {
    impactOccurred: (style: "light" | "medium" | "heavy") => void;
    notificationOccurred: (type: "error" | "success" | "warning") => void;
    selectionChanged: () => void;
  };
  ThemeParams: {
    bg_color?: string;
    text_color?: string;
    hint_color?: string;
    link_color?: string;
    button_color?: string;
    button_text_color?: string;
  };
  initData: string;
  initDataUnsafe: {
    query_id?: string;
    user?: TelegramUser;
    auth_date?: number;
    hash?: string;
    start_param?: string;
  };
  viewportHeight: number;
  viewportStableHeight: number;
  headerColor: string;
  backgroundColor: string;
  setHeaderColor: (color: string) => void;
  setBackgroundColor: (color: string) => void;
  onViewportChanged: (callback: () => void) => void;
  isExpanded: boolean;
  isDark: boolean;
  isVerticallyStacked: boolean;
  colorScheme: "light" | "dark";
  onThemeChanged: (callback: () => void) => void;
  requestWriteAccess: () => void;
  openLink: (url: string, options?: { try_instant_view?: boolean }) => void;
  openTelegramLink: (url: string) => void;
  openInvoice: (url: string, callback?: (status: string) => void) => void;
}

interface TelegramContextType {
  webApp: TelegramWebApp | null;
  user: TelegramUser | null;
  jwt: string | null;
  isLoading: boolean;
  error: string | null;
  isDark: boolean;
  haptic: {
    light: () => void;
    medium: () => void;
    heavy: () => void;
    success: () => void;
    error: () => void;
    warning: () => void;
  };
}

const TelegramContext = createContext<TelegramContextType | undefined>(undefined);

interface TelegramProviderProps {
  children: ReactNode;
}

/**
 * TelegramProvider: Wraps app with Telegram SDK initialization
 *
 * Usage:
 * ```tsx
 * export default function RootLayout({ children }) {
 *   return (
 *     <TelegramProvider>
 *       {children}
 *     </TelegramProvider>
 *   );
 * }
 * ```
 *
 * Then use hook:
 * ```tsx
 * const { user, jwt, haptic } = useTelegram();
 * ```
 */
export function TelegramProvider({ children }: TelegramProviderProps) {
  const router = useRouter();
  const [webApp, setWebApp] = useState<TelegramWebApp | null>(null);
  const [user, setUser] = useState<TelegramUser | null>(null);
  const [jwt, setJwt] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isDark, setIsDark] = useState(false);

  useEffect(() => {
    // Initialize Telegram SDK
    const initTelegram = async () => {
      try {
        // Access Telegram WebApp from window
        const tg = (window as any).Telegram?.WebApp;

        if (!tg) {
          throw new Error("Telegram WebApp SDK not available");
        }

        // Expand app to full height
        tg.ready();
        tg.expand();

        // Get user info
        const telegramUser = tg.initDataUnsafe?.user;
        if (!telegramUser) {
          throw new Error("No user data available");
        }

        setWebApp(tg);
        setUser(telegramUser);
        setIsDark(tg.colorScheme === "dark");

        // Setup theme change listener
        tg.onThemeChanged?.(() => {
          setIsDark(tg.colorScheme === "dark");
        });

        // Exchange initData for JWT
        const initData = tg.initData;
        if (initData) {
          const jwtResponse = await fetch(
            `${process.env.NEXT_PUBLIC_API_URL}/api/v1/miniapp/exchange-initdata`,
            {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
              },
              body: JSON.stringify({
                init_data: initData,
              }),
            }
          );

          if (!jwtResponse.ok) {
            const errorData = await jwtResponse.json();
            throw new Error(errorData.detail || "Failed to exchange initData for JWT");
          }

          const { access_token } = await jwtResponse.json();
          setJwt(access_token);

          // Store JWT in localStorage for API calls
          localStorage.setItem("jwt_token", access_token);
        }

        setIsLoading(false);
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : "Unknown error";
        setError(errorMessage);
        setIsLoading(false);
      }
    };

    initTelegram();
  }, []);

  const haptic = {
    light: () => webApp?.HapticFeedback?.impactOccurred?.("light"),
    medium: () => webApp?.HapticFeedback?.impactOccurred?.("medium"),
    heavy: () => webApp?.HapticFeedback?.impactOccurred?.("heavy"),
    success: () => webApp?.HapticFeedback?.notificationOccurred?.("success"),
    error: () => webApp?.HapticFeedback?.notificationOccurred?.("error"),
    warning: () => webApp?.HapticFeedback?.notificationOccurred?.("warning"),
  };

  const value: TelegramContextType = {
    webApp,
    user,
    jwt,
    isLoading,
    error,
    isDark,
    haptic,
  };

  return (
    <TelegramContext.Provider value={value}>
      {children}
    </TelegramContext.Provider>
  );
}

/**
 * Hook to access Telegram context
 *
 * Usage:
 * ```tsx
 * const { user, jwt, isDark, haptic } = useTelegram();
 * ```
 */
export function useTelegram(): TelegramContextType {
  const context = useContext(TelegramContext);
  if (!context) {
    throw new Error("useTelegram must be used within TelegramProvider");
  }
  return context;
}
