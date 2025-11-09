import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'Terms of Service',
  description: 'Terms and conditions for using TeleBot trading signal platform',
};

export default function TermsPage() {
  return (
    <div className="py-20 px-4">
      <div className="max-w-4xl mx-auto prose dark:prose-invert">
        <h1>Terms of Service</h1>
        <p className="text-sm text-gray-500">Last updated: November 9, 2025</p>

        <h2>1. Acceptance of Terms</h2>
        <p>
          By accessing or using TeleBot ("Service"), you agree to be bound by these Terms of Service
          ("Terms"). If you do not agree to these Terms, do not use the Service.
        </p>

        <h2>2. Description of Service</h2>
        <p>
          TeleBot provides trading signal distribution, analytics, and optional automated execution
          services ("Copy-Trading") for financial instruments including forex, indices, and cryptocurrencies.
        </p>
        <p>
          <strong>Important:</strong> Trading involves substantial risk of loss. Past performance does not
          guarantee future results. You are solely responsible for all trading decisions.
        </p>

        <h2>3. Eligibility</h2>
        <p>You must:</p>
        <ul>
          <li>Be at least 18 years old</li>
          <li>Have legal capacity to enter contracts in your jurisdiction</li>
          <li>Not be prohibited from using financial services under applicable law</li>
          <li>Provide accurate registration information</li>
        </ul>

        <h2>4. Account Registration</h2>
        <p>
          You are responsible for maintaining the confidentiality of your account credentials.
          You agree to notify us immediately of any unauthorized use of your account.
        </p>

        <h2>5. Subscription Plans & Billing</h2>
        <h3>5.1 Free Tier</h3>
        <p>
          Free tier provides access to signals with manual approval workflow.
          We reserve the right to modify or discontinue the free tier at any time.
        </p>

        <h3>5.2 Premium Tier (Copy-Trading)</h3>
        <p>
          Premium subscriptions are billed monthly in advance. By upgrading to Premium, you authorize
          us to charge your payment method on a recurring basis until you cancel.
        </p>
        <p>
          Premium tier includes automated execution ("Copy-Trading") at a 30% premium over base pricing.
        </p>

        <h3>5.3 Cancellation & Refunds</h3>
        <ul>
          <li>You may cancel your subscription at any time via your account settings</li>
          <li>Cancellations take effect at the end of the current billing period</li>
          <li>First-time Premium subscribers: 7-day money-back guarantee</li>
          <li>No refunds for partial months or unused services</li>
        </ul>

        <h2>6. Trading Risks & Disclaimers</h2>
        <h3>6.1 No Financial Advice</h3>
        <p>
          Signals provided by TeleBot are for informational purposes only and do not constitute
          financial advice, investment recommendations, or solicitations to buy or sell securities.
        </p>

        <h3>6.2 Risk of Loss</h3>
        <p>
          Trading forex, indices, and cryptocurrencies involves substantial risk of loss.
          You may lose some or all of your invested capital. Only trade with funds you can afford to lose.
        </p>

        <h3>6.3 No Guarantees</h3>
        <p>
          We make no guarantees about:
        </p>
        <ul>
          <li>Profitability or performance of signals</li>
          <li>Accuracy or timeliness of data</li>
          <li>Availability or uptime of the Service</li>
          <li>Execution prices or slippage</li>
        </ul>

        <h3>6.4 Copy-Trading Risks</h3>
        <p>
          Automated execution carries additional risks including:
        </p>
        <ul>
          <li>Technical failures or connectivity issues</li>
          <li>Broker execution delays or rejections</li>
          <li>Market gaps or extreme volatility</li>
          <li>Errors in trade parameters or risk calculations</li>
        </ul>
        <p>
          You retain full responsibility for monitoring your account and managing risk when using
          copy-trading features.
        </p>

        <h2>7. Acceptable Use</h2>
        <p>You agree not to:</p>
        <ul>
          <li>Share your account credentials with others</li>
          <li>Reverse engineer or attempt to extract source code</li>
          <li>Use the Service for any illegal purpose</li>
          <li>Interfere with or disrupt the Service</li>
          <li>Scrape or harvest data without authorization</li>
          <li>Resell or redistribute signals without written permission</li>
        </ul>

        <h2>8. Intellectual Property</h2>
        <p>
          All content, trademarks, and materials on TeleBot are owned by us or our licensors.
          You may not copy, modify, or distribute any content without written permission.
        </p>

        <h2>9. Third-Party Services</h2>
        <p>
          The Service integrates with third-party platforms (Telegram, MT5 brokers, payment processors).
          We are not responsible for the availability, content, or actions of these third parties.
        </p>

        <h2>10. Data Privacy</h2>
        <p>
          Your use of the Service is governed by our{' '}
          <Link href="/legal/privacy" className="text-primary-500 hover:underline">
            Privacy Policy
          </Link>, which describes how we collect, use, and protect your data.
        </p>

        <h2>11. Limitation of Liability</h2>
        <p>
          TO THE MAXIMUM EXTENT PERMITTED BY LAW, TELEBOT AND ITS AFFILIATES SHALL NOT BE LIABLE FOR:
        </p>
        <ul>
          <li>Any trading losses or damages arising from use of signals</li>
          <li>Indirect, incidental, consequential, or punitive damages</li>
          <li>Loss of profits, revenue, data, or business opportunities</li>
          <li>Service interruptions, errors, or delays</li>
        </ul>
        <p>
          OUR TOTAL LIABILITY SHALL NOT EXCEED THE AMOUNT YOU PAID US IN THE 12 MONTHS PRECEDING THE CLAIM.
        </p>

        <h2>12. Indemnification</h2>
        <p>
          You agree to indemnify and hold harmless TeleBot from any claims, losses, or damages
          arising from your use of the Service, violation of these Terms, or infringement of third-party rights.
        </p>

        <h2>13. Termination</h2>
        <p>
          We may suspend or terminate your account at any time for:
        </p>
        <ul>
          <li>Violation of these Terms</li>
          <li>Fraudulent activity or payment disputes</li>
          <li>Prolonged inactivity</li>
          <li>Legal or regulatory requirements</li>
        </ul>
        <p>
          Upon termination, you lose access to the Service and we are not obligated to retain your data.
        </p>

        <h2>14. Modifications to Terms</h2>
        <p>
          We may update these Terms at any time. Material changes will be notified via email or
          in-app notification. Continued use after changes constitutes acceptance.
        </p>

        <h2>15. Governing Law & Dispute Resolution</h2>
        <p>
          These Terms are governed by the laws of England and Wales.
          Disputes shall be resolved through binding arbitration in London, England.
        </p>

        <h2>16. Contact</h2>
        <p>
          For questions about these Terms, contact us at:
          <br />
          Email: legal@telebot.trading
          <br />
          Telegram: @TeleBotSupport
        </p>

        <hr className="my-8" />

        <div className="flex gap-4 text-sm">
          <Link href="/legal/privacy" className="text-primary-500 hover:underline">
            Privacy Policy
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
