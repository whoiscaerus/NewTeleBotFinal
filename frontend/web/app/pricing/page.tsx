import { Card, Button, Badge } from '@telebot/ui';
import Link from 'next/link';

/**
 * Pricing Page
 *
 * Displays tiered pricing with clear feature breakdowns:
 * - Standard tier: Manual approval
 * - Premium tier: Auto-execution (Copy-Trading)
 * - Enterprise tier: Custom solutions
 */
export default function PricingPage() {
  const tiers = [
    {
      name: 'Standard',
      price: '£39',
      period: 'per month',
      description: 'Perfect for traders who want full control with manual approvals',
      features: [
        'Unlimited trading signals',
        'Manual approval workflow',
        'Basic analytics dashboard',
        'Telegram notifications',
        'Email support',
        '1 MT5 account connection',
      ],
      cta: 'Get Started',
      ctaLink: '/pricing#checkout',
      badge: null,
    },
    {
      name: 'Premium',
      price: '£59',
      period: 'per month',
      description: '100% automated copy-trading with advanced features',
      features: [
        'Everything in Standard, plus:',
        '✨ 100% auto-execution (copy-trading)',
        'Advanced analytics & reports',
        'Priority support',
        'Custom risk parameters',
        'Up to 3 MT5 accounts',
        'Export trade history',
        'Price alerts',
      ],
      cta: 'Start Free Trial',
      ctaLink: '/pricing#checkout',
      badge: 'Most Popular',
    },
    {
      name: 'Enterprise',
      price: 'Custom',
      period: 'contact us',
      description: 'Tailored solutions for institutions and high-volume traders',
      features: [
        'Everything in Premium, plus:',
        'Dedicated account manager',
        'Custom strategy integration',
        'White-label options',
        'API access',
        'Unlimited MT5 accounts',
        'SLA guarantees',
        'Custom integrations',
      ],
      cta: 'Contact Sales',
      ctaLink: '/pricing#contact',
      badge: null,
    },
  ];

  return (
    <div className="py-20 px-4">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="text-center mb-16">
          <h1 className="text-5xl font-bold text-gray-900 dark:text-white mb-4">
            Simple, Transparent Pricing
          </h1>
          <p className="text-xl text-gray-600 dark:text-gray-300 max-w-3xl mx-auto">
            Choose the plan that fits your trading style. All plans include unlimited signals
            and full access to our analytics platform.
          </p>
        </div>

        {/* Pricing Cards */}
        <div className="grid md:grid-cols-3 gap-8 mb-16">
          {tiers.map((tier) => (
            <Card
              key={tier.name}
              variant={tier.badge ? 'elevated' : 'default'}
              padding="lg"
              className={tier.badge ? 'border-2 border-primary-500' : ''}
            >
              {tier.badge && (
                <div className="mb-4">
                  <Badge variant="success" size="md">
                    {tier.badge}
                  </Badge>
                </div>
              )}

              <h3 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">
                {tier.name}
              </h3>

              <div className="mb-4">
                <span className="text-4xl font-bold text-gray-900 dark:text-white">
                  {tier.price}
                </span>
                {tier.period && (
                  <span className="text-gray-600 dark:text-gray-400 ml-2">
                    / {tier.period}
                  </span>
                )}
              </div>

              <p className="text-gray-600 dark:text-gray-300 mb-6">
                {tier.description}
              </p>

              <ul className="space-y-3 mb-8">
                {tier.features.map((feature, idx) => (
                  <li key={idx} className="flex items-start gap-2">
                    <span className={feature.startsWith('✨') ? 'text-primary-500' : 'text-green-500'}>
                      {feature.startsWith('✨') ? '✨' : '✓'}
                    </span>
                    <span className="text-gray-700 dark:text-gray-200">
                      {feature.replace('✨ ', '')}
                    </span>
                  </li>
                ))}
              </ul>

              <Link href={tier.ctaLink}>
                <Button
                  variant={tier.badge ? 'primary' : 'outline'}
                  size="lg"
                  fullWidth
                >
                  {tier.cta}
                </Button>
              </Link>
            </Card>
          ))}
        </div>

        {/* FAQ Section */}
        <div className="max-w-3xl mx-auto mt-20">
          <h2 className="text-3xl font-bold text-center text-gray-900 dark:text-white mb-12">
            Frequently Asked Questions
          </h2>

          <div className="space-y-6">
            <Card variant="default" padding="lg">
              <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-2">
                What's the difference between manual and auto-execution?
              </h3>
              <p className="text-gray-600 dark:text-gray-300">
                Standard tier requires you to approve each signal manually via Telegram before it's executed.
                Premium tier enables copy-trading where signals are executed automatically
                on your MT5 account without approval.
              </p>
            </Card>

            <Card variant="default" padding="lg">
              <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-2">
                Can I cancel anytime?
              </h3>
              <p className="text-gray-600 dark:text-gray-300">
                Yes! All paid plans are billed monthly and can be canceled at any time.
                You'll retain access until the end of your billing period.
              </p>
            </Card>

            <Card variant="default" padding="lg">
              <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-2">
                Do you offer refunds?
              </h3>
              <p className="text-gray-600 dark:text-gray-300">
                We offer a 7-day money-back guarantee for first-time Premium subscribers.
                If you're not satisfied, contact support within 7 days for a full refund.
              </p>
            </Card>

            <Card variant="default" padding="lg">
              <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-2">
                Which brokers do you support?
              </h3>
              <p className="text-gray-600 dark:text-gray-300">
                We support any MT5 broker (FXPro, IC Markets, Pepperstone, etc.).
                Our Expert Advisor connects securely without sharing passwords.
              </p>
            </Card>

            <Card variant="default" padding="lg">
              <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-2">
                Is my data secure?
              </h3>
              <p className="text-gray-600 dark:text-gray-300">
                Yes. We use bank-grade encryption, never store your broker passwords,
                and are fully GDPR compliant. See our{' '}
                <Link href="/legal/privacy" className="text-primary-500 hover:underline">
                  Privacy Policy
                </Link>{' '}
                for details.
              </p>
            </Card>
          </div>
        </div>

        {/* CTA */}
        <div className="text-center mt-16">
          <p className="text-gray-600 dark:text-gray-300 mb-4">
            Still have questions?
          </p>
          <Link href="https://t.me/YourSupportBot">
            <Button variant="outline" size="lg">
              Contact Support
            </Button>
          </Link>
        </div>
      </div>
    </div>
  );
}
