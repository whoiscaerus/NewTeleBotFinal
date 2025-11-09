import Link from 'next/link';

/**
 * Footer Component
 *
 * Site footer with links to legal pages, social media, and company info.
 */
export default function Footer() {
  const currentYear = new Date().getFullYear();

  return (
    <footer className="bg-gray-50 dark:bg-gray-900 border-t border-gray-200 dark:border-gray-800">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-8">
          {/* Company */}
          <div>
            <div className="flex items-center gap-2 mb-4">
              <span className="text-2xl">📊</span>
              <span className="font-bold text-lg text-gray-900 dark:text-white">
                TeleBot
              </span>
            </div>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              Professional trading signal platform for Gold, Indices, and Crypto.
            </p>
          </div>

          {/* Product */}
          <div>
            <h3 className="font-semibold text-gray-900 dark:text-white mb-4">
              Product
            </h3>
            <ul className="space-y-2">
              <li>
                <Link
                  href="/pricing"
                  className="text-sm text-gray-600 dark:text-gray-400 hover:text-primary-500"
                >
                  Pricing
                </Link>
              </li>
              <li>
                <Link
                  href="/performance"
                  className="text-sm text-gray-600 dark:text-gray-400 hover:text-primary-500"
                >
                  Performance
                </Link>
              </li>
              <li>
                <a
                  href="https://t.me/YourBot"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm text-gray-600 dark:text-gray-400 hover:text-primary-500"
                >
                  Telegram Bot
                </a>
              </li>
            </ul>
          </div>

          {/* Legal */}
          <div>
            <h3 className="font-semibold text-gray-900 dark:text-white mb-4">
              Legal
            </h3>
            <ul className="space-y-2">
              <li>
                <Link
                  href="/legal/terms"
                  className="text-sm text-gray-600 dark:text-gray-400 hover:text-primary-500"
                >
                  Terms of Service
                </Link>
              </li>
              <li>
                <Link
                  href="/legal/privacy"
                  className="text-sm text-gray-600 dark:text-gray-400 hover:text-primary-500"
                >
                  Privacy Policy
                </Link>
              </li>
              <li>
                <Link
                  href="/legal/risk"
                  className="text-sm text-gray-600 dark:text-gray-400 hover:text-primary-500"
                >
                  Risk Disclosure
                </Link>
              </li>
              <li>
                <Link
                  href="/legal/cookies"
                  className="text-sm text-gray-600 dark:text-gray-400 hover:text-primary-500"
                >
                  Cookie Policy
                </Link>
              </li>
            </ul>
          </div>

          {/* Support */}
          <div>
            <h3 className="font-semibold text-gray-900 dark:text-white mb-4">
              Support
            </h3>
            <ul className="space-y-2">
              <li>
                <a
                  href="https://t.me/YourSupportBot"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm text-gray-600 dark:text-gray-400 hover:text-primary-500"
                >
                  Telegram Support
                </a>
              </li>
              <li>
                <a
                  href="mailto:support@telebot.trading"
                  className="text-sm text-gray-600 dark:text-gray-400 hover:text-primary-500"
                >
                  Email Support
                </a>
              </li>
            </ul>
          </div>
        </div>

        <div className="mt-12 pt-8 border-t border-gray-200 dark:border-gray-800">
          <div className="flex flex-col md:flex-row justify-between items-center gap-4">
            <p className="text-sm text-gray-600 dark:text-gray-400">
              © {currentYear} TeleBot. All rights reserved.
            </p>
            <p className="text-xs text-gray-500 dark:text-gray-500">
              Trading involves substantial risk. Only trade with funds you can afford to lose.
            </p>
          </div>
        </div>
      </div>
    </footer>
  );
}
