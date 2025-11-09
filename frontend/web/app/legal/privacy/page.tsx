import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'Privacy Policy',
  description: 'Privacy policy and data protection practices for TeleBot',
};

export default function PrivacyPage() {
  return (
    <div className="py-20 px-4">
      <div className="max-w-4xl mx-auto prose dark:prose-invert">
        <h1>Privacy Policy</h1>
        <p className="text-sm text-gray-500">Last updated: November 9, 2025</p>

        <p>
          This Privacy Policy describes how TeleBot ("we", "us", "our") collects, uses, and protects
          your personal information when you use our Service.
        </p>

        <h2>1. Information We Collect</h2>

        <h3>1.1 Information You Provide</h3>
        <ul>
          <li><strong>Account Information:</strong> Telegram ID, username, email address</li>
          <li><strong>Payment Information:</strong> Billing address, payment method (processed by Stripe)</li>
          <li><strong>Trading Preferences:</strong> Risk parameters, alert settings, notification preferences</li>
        </ul>

        <h3>1.2 Automatically Collected Information</h3>
        <ul>
          <li><strong>Usage Data:</strong> Pages visited, features used, session duration</li>
          <li><strong>Device Information:</strong> Browser type, OS, IP address</li>
          <li><strong>Trading Data:</strong> Signal approvals, trade execution records, performance metrics</li>
        </ul>

        <h3>1.3 Broker Integration Data</h3>
        <ul>
          <li>MT5 account numbers (encrypted)</li>
          <li>Trade execution confirmations</li>
          <li>Account balance snapshots (for analytics only)</li>
        </ul>
        <p><strong>Note:</strong> We never store your broker login credentials.</p>

        <h2>2. How We Use Your Information</h2>
        <p>We use your information to:</p>
        <ul>
          <li>Provide and improve the Service</li>
          <li>Process payments and manage subscriptions</li>
          <li>Send trading signals and notifications</li>
          <li>Generate analytics and performance reports</li>
          <li>Provide customer support</li>
          <li>Detect and prevent fraud or abuse</li>
          <li>Comply with legal obligations</li>
        </ul>

        <h2>3. Data Sharing & Disclosure</h2>
        <p>We share your information only as described below:</p>

        <h3>3.1 Service Providers</h3>
        <ul>
          <li><strong>Stripe:</strong> Payment processing (PCI-DSS compliant)</li>
          <li><strong>Telegram:</strong> Message delivery via Telegram Bot API</li>
          <li><strong>AWS:</strong> Cloud hosting and data storage (encrypted at rest)</li>
        </ul>

        <h3>3.2 Legal Requirements</h3>
        <p>
          We may disclose your information if required by law, court order, or government request,
          or to protect our rights or the safety of others.
        </p>

        <h3>3.3 Business Transfers</h3>
        <p>
          In the event of a merger, acquisition, or sale of assets, your information may be
          transferred to the acquiring entity.
        </p>

        <h3>3.4 With Your Consent</h3>
        <p>
          We may share anonymized performance data publicly (e.g., on our /performance page)
          only with your explicit opt-in consent.
        </p>

        <h2>4. Data Retention</h2>
        <ul>
          <li><strong>Active accounts:</strong> We retain data while your account is active</li>
          <li><strong>Closed accounts:</strong> Data deleted within 90 days unless legally required</li>
          <li><strong>Trading records:</strong> Retained for 7 years per financial regulations</li>
        </ul>

        <h2>5. Your Rights (GDPR)</h2>
        <p>If you are in the EU/UK, you have the right to:</p>
        <ul>
          <li><strong>Access:</strong> Request a copy of your personal data</li>
          <li><strong>Rectification:</strong> Correct inaccurate or incomplete data</li>
          <li><strong>Erasure:</strong> Request deletion of your data ("right to be forgotten")</li>
          <li><strong>Portability:</strong> Export your data in machine-readable format</li>
          <li><strong>Objection:</strong> Object to processing for marketing purposes</li>
          <li><strong>Withdraw Consent:</strong> Opt out of optional data processing</li>
        </ul>
        <p>
          To exercise these rights, contact us at privacy@telebot.trading or via your account settings.
        </p>

        <h2>6. Security Measures</h2>
        <p>We protect your data using:</p>
        <ul>
          <li>AES-256 encryption at rest</li>
          <li>TLS 1.3 encryption in transit</li>
          <li>Multi-factor authentication for admin access</li>
          <li>Regular security audits and penetration testing</li>
          <li>Role-based access control (RBAC)</li>
        </ul>
        <p>
          However, no system is 100% secure. You are responsible for keeping your account
          credentials confidential.
        </p>

        <h2>7. Cookies & Tracking</h2>
        <p>
          We use essential cookies for authentication and preferences. See our{' '}
          <Link href="/legal/cookies" className="text-primary-500 hover:underline">
            Cookie Policy
          </Link>{' '}
          for details.
        </p>

        <h2>8. Third-Party Links</h2>
        <p>
          Our Service may contain links to third-party websites (e.g., broker login portals).
          We are not responsible for their privacy practices.
        </p>

        <h2>9. Children's Privacy</h2>
        <p>
          The Service is not intended for users under 18. We do not knowingly collect data
          from minors. If we discover such data, we will delete it immediately.
        </p>

        <h2>10. International Data Transfers</h2>
        <p>
          Your data may be transferred to and processed in countries outside the EU/UK
          (e.g., US-based AWS servers). We use Standard Contractual Clauses (SCCs) to
          ensure adequate protection.
        </p>

        <h2>11. Changes to This Policy</h2>
        <p>
          We may update this Privacy Policy from time to time. Material changes will be
          notified via email or in-app notification 30 days before taking effect.
        </p>

        <h2>12. Contact Us</h2>
        <p>
          For privacy questions or to exercise your rights:
          <br />
          Email: privacy@telebot.trading
          <br />
          Telegram: @TeleBotSupport
          <br />
          Address: TeleBot Ltd., London, United Kingdom
        </p>

        <hr className="my-8" />

        <div className="flex gap-4 text-sm">
          <Link href="/legal/terms" className="text-primary-500 hover:underline">
            Terms of Service
          </Link>
          <Link href="/legal/risk" className="text-primary-500 hover:underline">
            Risk Disclosure
          </Link>
          <Link href="/legal/cookies" className="text-primary-500 hover:underline">
            Cookie Policy
          </Link>
        </div>
      </div>
    </div>
  );
}
