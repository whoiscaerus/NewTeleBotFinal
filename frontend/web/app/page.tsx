import { Button, Card, Badge } from '@telebot/ui';
import Link from 'next/link';

/**
 * Landing Page
 *
 * Professional marketing page with hero section, features, social proof,
 * and clear CTAs for sign-up and pricing.
 */
export default function HomePage() {
  return (
    <div className="flex flex-col">
      {/* Hero Section */}
      <section className="relative bg-gradient-to-b from-primary-50 to-white dark:from-primary-950 dark:to-gray-900 py-20 px-4">
        <div className="max-w-6xl mx-auto text-center">
          <Badge variant="info" size="md" className="mb-6">
            🚀 Now with Copy-Trading
          </Badge>

          <h1 className="text-5xl md:text-6xl font-bold text-gray-900 dark:text-white mb-6">
            Professional Trading Signals
            <span className="block text-primary-500 mt-2">
              Direct to Your Telegram
            </span>
          </h1>

          <p className="text-xl text-gray-600 dark:text-gray-300 mb-8 max-w-3xl mx-auto">
            Receive curated trading signals for Gold, Indices, and Crypto with automated risk management,
            approval workflows, and optional copy-trading.
          </p>

          <div className="flex flex-col sm:flex-row gap-4 justify-center mb-12">
            <Link href="/pricing">
              <Button variant="primary" size="lg">
                View Pricing
              </Button>
            </Link>
            <Link href="/performance">
              <Button variant="outline" size="lg">
                View Performance
              </Button>
            </Link>
          </div>

          {/* Trust Indicators */}
          <div className="flex flex-wrap justify-center gap-8 text-center">
            <div>
              <div className="text-3xl font-bold text-gray-900 dark:text-white">2,500+</div>
              <div className="text-sm text-gray-600 dark:text-gray-400">Active Users</div>
            </div>
            <div>
              <div className="text-3xl font-bold text-gray-900 dark:text-white">95%</div>
              <div className="text-sm text-gray-600 dark:text-gray-400">Win Rate</div>
            </div>
            <div>
              <div className="text-3xl font-bold text-gray-900 dark:text-white">1.8</div>
              <div className="text-sm text-gray-600 dark:text-gray-400">Avg Risk:Reward</div>
            </div>
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section className="py-20 px-4 bg-white dark:bg-gray-900">
        <div className="max-w-6xl mx-auto">
          <h2 className="text-4xl font-bold text-center text-gray-900 dark:text-white mb-12">
            Why Choose TeleBot?
          </h2>

          <div className="grid md:grid-cols-3 gap-8">
            <Card variant="elevated" padding="lg">
              <div className="text-4xl mb-4">📊</div>
              <h3 className="text-xl font-bold mb-3 text-gray-900 dark:text-white">
                Advanced Analytics
              </h3>
              <p className="text-gray-600 dark:text-gray-300">
                Real-time equity curves, drawdown tracking, and performance metrics.
                Full transparency with every trade.
              </p>
            </Card>

            <Card variant="elevated" padding="lg">
              <div className="text-4xl mb-4">🔒</div>
              <h3 className="text-xl font-bold mb-3 text-gray-900 dark:text-white">
                Risk Management
              </h3>
              <p className="text-gray-600 dark:text-gray-300">
                Every signal includes pre-calculated stop-loss and take-profit levels.
                Approve or reject with one tap.
              </p>
            </Card>

            <Card variant="elevated" padding="lg">
              <div className="text-4xl mb-4">⚡</div>
              <h3 className="text-xl font-bold mb-3 text-gray-900 dark:text-white">
                Copy-Trading
              </h3>
              <p className="text-gray-600 dark:text-gray-300">
                100% automated execution with FXPro integration. Upgrade to premium
                for hands-free trading.
              </p>
            </Card>

            <Card variant="elevated" padding="lg">
              <div className="text-4xl mb-4">📱</div>
              <h3 className="text-xl font-bold mb-3 text-gray-900 dark:text-white">
                Telegram Native
              </h3>
              <p className="text-gray-600 dark:text-gray-300">
                Receive signals instantly via Telegram Mini App. No separate app
                installs or logins required.
              </p>
            </Card>

            <Card variant="elevated" padding="lg">
              <div className="text-4xl mb-4">🎯</div>
              <h3 className="text-xl font-bold mb-3 text-gray-900 dark:text-white">
                Multi-Asset Coverage
              </h3>
              <p className="text-gray-600 dark:text-gray-300">
                Gold (XAUUSD), major indices (SP500, NASDAQ), and top cryptocurrencies.
                Diversify across markets.
              </p>
            </Card>

            <Card variant="elevated" padding="lg">
              <div className="text-4xl mb-4">🏆</div>
              <h3 className="text-xl font-bold mb-3 text-gray-900 dark:text-white">
                Proven Track Record
              </h3>
              <p className="text-gray-600 dark:text-gray-300">
                Verified performance with third-party tracking. Public equity curve
                and closed trade history.
              </p>
            </Card>
          </div>
        </div>
      </section>

      {/* How It Works Section */}
      <section className="py-20 px-4 bg-gray-50 dark:bg-gray-800">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-4xl font-bold text-center text-gray-900 dark:text-white mb-12">
            How It Works
          </h2>

          <div className="space-y-8">
            <div className="flex gap-6 items-start">
              <div className="flex-shrink-0 w-12 h-12 bg-primary-500 text-white rounded-full flex items-center justify-center font-bold text-xl">
                1
              </div>
              <div>
                <h3 className="text-xl font-bold mb-2 text-gray-900 dark:text-white">
                  Connect Your Broker
                </h3>
                <p className="text-gray-600 dark:text-gray-300">
                  Link your MT5 account (FXPro, IC Markets, or any broker) via our secure
                  Expert Advisor. No passwords shared.
                </p>
              </div>
            </div>

            <div className="flex gap-6 items-start">
              <div className="flex-shrink-0 w-12 h-12 bg-primary-500 text-white rounded-full flex items-center justify-center font-bold text-xl">
                2
              </div>
              <div>
                <h3 className="text-xl font-bold mb-2 text-gray-900 dark:text-white">
                  Receive Signals
                </h3>
                <p className="text-gray-600 dark:text-gray-300">
                  Get real-time trading signals via Telegram with entry price, stop-loss,
                  and take-profit levels clearly marked.
                </p>
              </div>
            </div>

            <div className="flex gap-6 items-start">
              <div className="flex-shrink-0 w-12 h-12 bg-primary-500 text-white rounded-full flex items-center justify-center font-bold text-xl">
                3
              </div>
              <div>
                <h3 className="text-xl font-bold mb-2 text-gray-900 dark:text-white">
                  Approve or Auto-Execute
                </h3>
                <p className="text-gray-600 dark:text-gray-300">
                  Free users approve each signal manually. Premium users enjoy 100% automated
                  execution with copy-trading.
                </p>
              </div>
            </div>

            <div className="flex gap-6 items-start">
              <div className="flex-shrink-0 w-12 h-12 bg-primary-500 text-white rounded-full flex items-center justify-center font-bold text-xl">
                4
              </div>
              <div>
                <h3 className="text-xl font-bold mb-2 text-gray-900 dark:text-white">
                  Track Performance
                </h3>
                <p className="text-gray-600 dark:text-gray-300">
                  View detailed analytics, equity curves, and trade history in your personal
                  dashboard. Export reports anytime.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-20 px-4 bg-primary-500 text-white">
        <div className="max-w-4xl mx-auto text-center">
          <h2 className="text-4xl font-bold mb-6">
            Ready to Start Trading Smarter?
          </h2>
          <p className="text-xl mb-8 opacity-90">
            Join thousands of traders using TeleBot for consistent, data-driven trading decisions.
          </p>
          <Link href="/pricing">
            <Button variant="secondary" size="lg">
              View Plans & Pricing
            </Button>
          </Link>
        </div>
      </section>
    </div>
  );
}
