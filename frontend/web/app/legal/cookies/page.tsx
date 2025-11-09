import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'Cookie Policy',
  description: 'Information about how TeleBot uses cookies and tracking technologies',
};

export default function CookiesPage() {
  return (
    <div className="py-20 px-4">
      <div className="max-w-4xl mx-auto prose dark:prose-invert">
        <h1>Cookie Policy</h1>
        <p className="text-sm text-gray-500">Last updated: November 9, 2025</p>

        <p>
          This Cookie Policy explains how TeleBot uses cookies and similar tracking technologies
          on our website and web application.
        </p>

        <h2>1. What Are Cookies?</h2>
        <p>
          Cookies are small text files stored on your device when you visit a website. They help
          websites remember your preferences, authenticate your identity, and analyze usage patterns.
        </p>

        <h2>2. Cookies We Use</h2>

        <h3>2.1 Essential Cookies (Always Active)</h3>
        <p>
          These cookies are necessary for the Service to function. You cannot opt out of these cookies.
        </p>
        <table className="min-w-full border">
          <thead>
            <tr>
              <th>Cookie Name</th>
              <th>Purpose</th>
              <th>Duration</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><code>tb_session</code></td>
              <td>Authenticates your session</td>
              <td>7 days</td>
            </tr>
            <tr>
              <td><code>tb_csrf</code></td>
              <td>Prevents cross-site request forgery attacks</td>
              <td>Session</td>
            </tr>
            <tr>
              <td><code>tb_theme</code></td>
              <td>Remembers your dark mode preference</td>
              <td>1 year</td>
            </tr>
          </tbody>
        </table>

        <h3>2.2 Analytics Cookies (Optional)</h3>
        <p>
          We use analytics cookies to understand how users interact with our Service. This helps
          us improve performance and user experience.
        </p>
        <table className="min-w-full border">
          <thead>
            <tr>
              <th>Cookie Name</th>
              <th>Purpose</th>
              <th>Duration</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><code>_tb_analytics</code></td>
              <td>Tracks page views and navigation patterns</td>
              <td>30 days</td>
            </tr>
            <tr>
              <td><code>_tb_cwv</code></td>
              <td>Measures Core Web Vitals (performance metrics)</td>
              <td>1 day</td>
            </tr>
          </tbody>
        </table>

        <h2>3. Third-Party Cookies</h2>

        <h3>3.1 Stripe (Payment Processing)</h3>
        <p>
          When you upgrade to a paid plan, Stripe sets cookies to process payments securely.
          See{' '}
          <a
            href="https://stripe.com/cookies-policy/legal"
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary-500 hover:underline"
          >
            Stripe's Cookie Policy
          </a>.
        </p>

        <h3>3.2 Telegram Login Widget</h3>
        <p>
          The Telegram Login Widget may set cookies for authentication.
          See{' '}
          <a
            href="https://telegram.org/privacy"
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary-500 hover:underline"
          >
            Telegram's Privacy Policy
          </a>.
        </p>

        <h2>4. Local Storage</h2>
        <p>
          In addition to cookies, we use browser local storage to cache:
        </p>
        <ul>
          <li>User preferences (language, timezone)</li>
          <li>Dashboard layout customizations</li>
          <li>Recently viewed signals (for quick access)</li>
        </ul>
        <p>
          Local storage data remains on your device until you clear your browser data.
        </p>

        <h2>5. Managing Cookies</h2>

        <h3>5.1 Browser Settings</h3>
        <p>
          You can control cookies through your browser settings:
        </p>
        <ul>
          <li><strong>Chrome:</strong> Settings → Privacy and Security → Cookies and other site data</li>
          <li><strong>Firefox:</strong> Settings → Privacy & Security → Cookies and Site Data</li>
          <li><strong>Safari:</strong> Preferences → Privacy → Manage Website Data</li>
          <li><strong>Edge:</strong> Settings → Cookies and site permissions → Manage and delete cookies</li>
        </ul>

        <h3>5.2 Opt Out of Analytics</h3>
        <p>
          You can opt out of analytics cookies via your account settings:
          <br />
          Dashboard → Settings → Privacy → Analytics Cookies → Off
        </p>

        <h3>5.3 Do Not Track (DNT)</h3>
        <p>
          We respect "Do Not Track" browser signals. When DNT is enabled, we disable analytics cookies
          automatically.
        </p>

        <h2>6. Consequences of Disabling Cookies</h2>
        <p>
          If you disable essential cookies, you may experience:
        </p>
        <ul>
          <li>Inability to log in or stay logged in</li>
          <li>Loss of preferences (dark mode, language)</li>
          <li>Reduced functionality (e.g., approval workflows may break)</li>
        </ul>
        <p>
          Disabling analytics cookies does not affect Service functionality.
        </p>

        <h2>7. Cookie Lifespan</h2>
        <ul>
          <li><strong>Session cookies:</strong> Deleted when you close your browser</li>
          <li><strong>Persistent cookies:</strong> Remain until expiry date or manual deletion</li>
        </ul>
        <p>
          You can view cookie expiry dates in your browser's developer tools (F12 → Application → Cookies).
        </p>

        <h2>8. Updates to This Policy</h2>
        <p>
          We may update this Cookie Policy from time to time. Changes will be posted on this page
          with a new "Last updated" date.
        </p>

        <h2>9. Contact Us</h2>
        <p>
          For questions about our use of cookies:
          <br />
          Email: privacy@telebot.trading
          <br />
          Telegram: @TeleBotSupport
        </p>

        <hr className="my-8" />

        <div className="flex gap-4 text-sm">
          <Link href="/legal/terms" className="text-primary-500 hover:underline">
            Terms of Service
          </Link>
          <Link href="/legal/privacy" className="text-primary-500 hover:underline">
            Privacy Policy
          </Link>
          <Link href="/legal/risk" className="text-primary-500 hover:underline">
            Risk Disclosure
          </Link>
        </div>
      </div>
    </div>
  );
}
