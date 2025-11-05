/**
 * Root layout for Telegram Mini App
 *
 * Providers:
 * - TelegramProvider: Telegram SDK initialization
 * - ToastProvider: Toast notifications
 * - Dark mode support
 */

import { TelegramProvider } from "./_providers/TelegramProvider";
import { ToastProvider } from "./_providers/ToastProvider";
import "../styles/globals.css";

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
          <ToastProvider>
            {children}
          </ToastProvider>
        </TelegramProvider>
      </body>
    </html>
  );
}
