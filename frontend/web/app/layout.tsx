import type { Metadata, Viewport } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';
import { ThemeProvider } from '@/components/ThemeProvider';
import { AuthProvider } from '@/lib/auth';
import Header from '@/components/Header';
import Footer from '@/components/Footer';

const inter = Inter({ subsets: ['latin'], variable: '--font-inter' });

export const metadata: Metadata = {
  title: {
    default: 'TeleBot - Professional Trading Signal Platform',
    template: '%s | TeleBot',
  },
  description: 'Receive curated trading signals for Gold, Indices, and Crypto with automated risk management and copy-trading capabilities.',
  keywords: ['trading signals', 'forex', 'gold trading', 'crypto trading', 'copy trading', 'algorithmic trading', 'MT5'],
  authors: [{ name: 'TeleBot' }],
  creator: 'TeleBot',
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL || 'https://telebot.trading'),
  openGraph: {
    type: 'website',
    locale: 'en_GB',
    url: '/',
    title: 'TeleBot - Professional Trading Signal Platform',
    description: 'Receive curated trading signals for Gold, Indices, and Crypto with automated risk management.',
    siteName: 'TeleBot',
    images: [
      {
        url: '/og-image.png',
        width: 1200,
        height: 630,
        alt: 'TeleBot Trading Platform',
      },
    ],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'TeleBot - Professional Trading Signal Platform',
    description: 'Receive curated trading signals for Gold, Indices, and Crypto',
    images: ['/og-image.png'],
  },
  manifest: '/manifest.json',
  icons: {
    icon: '/favicon.ico',
    apple: '/icons/icon-192.png',
  },
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: '#ffffff' },
    { media: '(prefers-color-scheme: dark)', color: '#0a0a0a' },
  ],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={inter.variable}>
        <ThemeProvider>
          <AuthProvider>
            <div className="flex min-h-screen flex-col">
              <Header />
              <main className="flex-1">{children}</main>
              <Footer />
            </div>
          </AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
