"use client";

/**
 * Root layout for Telegram Mini App
 *
 * Providers:
 * - TelegramProvider: Telegram SDK initialization
 * - Dark mode support
 */

import { TelegramProvider } from "./_providers/TelegramProvider";
import "./globals.css";

export const metadata = {
  title: "Trading Platform",
  description: "Telegram Mini App for trading signals",
  viewport: "width=device-width, initial-scale=1, user-scalable=no",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* Telegram WebApp SDK */}
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
      </head>
      <body className="antialiased">
        <TelegramProvider>
          {children}
        </TelegramProvider>
      </body>
    </html>
  );
}
