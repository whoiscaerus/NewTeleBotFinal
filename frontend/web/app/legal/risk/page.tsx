import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'Risk Disclosure',
  description: 'Important risk disclosures for forex and cryptocurrency trading',
};

export default function RiskPage() {
  return (
    <div className="py-20 px-4">
      <div className="max-w-4xl mx-auto prose dark:prose-invert">
        <h1>Risk Disclosure Statement</h1>
        <p className="text-sm text-gray-500">Last updated: November 9, 2025</p>

        <div className="bg-red-50 dark:bg-red-900/20 border-2 border-red-500 rounded-lg p-6 my-8">
          <h3 className="text-red-700 dark:text-red-400 mt-0">⚠️ High-Risk Warning</h3>
          <p className="text-red-600 dark:text-red-300 mb-0">
            Trading forex, indices, and cryptocurrencies involves SUBSTANTIAL RISK OF LOSS.
            You may lose some or all of your invested capital. Only trade with money you can afford to lose.
          </p>
        </div>

        <h2>1. Nature of Trading Risks</h2>

        <h3>1.1 Leverage Risk</h3>
        <p>
          Forex and CFD trading involves leverage, which magnifies both gains and losses.
          A small market movement can result in large losses exceeding your initial deposit.
        </p>
        <p>
          <strong>Example:</strong> With 1:100 leverage, a 1% adverse price move can wipe out 100%
          of your account balance.
        </p>

        <h3>1.2 Market Volatility</h3>
        <p>
          Financial markets are highly volatile. Prices can move rapidly due to economic data,
          geopolitical events, or market sentiment, resulting in significant losses.
        </p>

        <h3>1.3 Liquidity Risk</h3>
        <p>
          During periods of low liquidity (e.g., market open/close, major news events), you may
          experience slippage or be unable to execute trades at desired prices.
        </p>

        <h3>1.4 Gap Risk</h3>
        <p>
          Markets can "gap" over weekends or during news events, causing prices to jump significantly.
          Stop-loss orders may be executed at worse prices than expected.
        </p>

        <h2>2. Copy-Trading Specific Risks</h2>

        <h3>2.1 Automated Execution Failures</h3>
        <p>
          Copy-trading relies on technology (Expert Advisors, broker APIs, internet connectivity).
          Technical failures may result in:
        </p>
        <ul>
          <li>Missed entries or exits</li>
          <li>Delayed execution causing slippage</li>
          <li>Incorrect position sizes</li>
          <li>Stop-loss or take-profit not being set</li>
        </ul>
        <p>
          <strong>You are responsible for monitoring your account</strong> and manually intervening if
          automation fails.
        </p>

        <h3>2.2 Strategy Risk</h3>
        <p>
          Past performance does not guarantee future results. A strategy that was profitable historically
          may become unprofitable due to changing market conditions.
        </p>

        <h3>2.3 Broker Risk</h3>
        <p>
          Your broker may reject orders, increase spreads, or experience downtime, affecting
          copy-trading execution. We have no control over broker actions.
        </p>

        <h2>3. Signal Provider Risks</h2>

        <h3>3.1 No Guarantees</h3>
        <p>
          We make no guarantees about:
        </p>
        <ul>
          <li>Profitability of signals</li>
          <li>Accuracy of entry/exit prices</li>
          <li>Win rate or risk-reward ratios</li>
          <li>Maximum drawdown or risk metrics</li>
        </ul>

        <h3>3.2 Performance Metrics</h3>
        <p>
          Published performance metrics (equity curve, win rate, Sharpe ratio) are based on
          historical data and may not reflect your actual results due to:
        </p>
        <ul>
          <li>Different account sizes</li>
          <li>Broker spread/commission differences</li>
          <li>Execution delays or slippage</li>
          <li>Subscription start date (mid-strategy entry)</li>
        </ul>

        <h3>3.3 Not Financial Advice</h3>
        <p>
          Signals are provided for informational purposes only and do not constitute financial advice,
          investment recommendations, or solicitations. You are solely responsible for all trading decisions.
        </p>

        <h2>4. Your Responsibilities</h2>
        <p>
          By using TeleBot, you acknowledge that you:
        </p>
        <ul>
          <li>Understand the risks of leveraged trading</li>
          <li>Have sufficient knowledge and experience to evaluate signals</li>
          <li>Will only trade with risk capital you can afford to lose</li>
          <li>Will monitor your account regularly and manage risk</li>
          <li>Accept full responsibility for trading outcomes</li>
        </ul>

        <h2>5. Risk Management Best Practices</h2>
        <p>
          To reduce risk, we recommend:
        </p>
        <ul>
          <li><strong>Position Sizing:</strong> Never risk more than 1-2% of account per trade</li>
          <li><strong>Stop-Loss:</strong> Always use stop-loss orders (even with copy-trading)</li>
          <li><strong>Diversification:</strong> Don't allocate 100% of capital to one strategy</li>
          <li><strong>Account Monitoring:</strong> Check your account daily</li>
          <li><strong>Emergency Plan:</strong> Know how to manually close trades if automation fails</li>
        </ul>

        <h2>6. Regulatory Considerations</h2>

        <h3>6.1 Not Regulated Advice</h3>
        <p>
          TeleBot is a technology platform providing signal distribution services. We are not:
        </p>
        <ul>
          <li>A licensed investment advisor</li>
          <li>A regulated broker or dealing firm</li>
          <li>A fund manager or portfolio manager</li>
        </ul>

        <h3>6.2 Your Broker's Regulation</h3>
        <p>
          You are responsible for choosing a properly regulated broker (e.g., FCA, ASIC, CySEC).
          Ensure your broker offers investor protections such as negative balance protection
          and compensation schemes.
        </p>

        <h2>7. Limitation of Liability</h2>
        <p>
          TeleBot and its affiliates are not liable for:
        </p>
        <ul>
          <li>Trading losses of any kind</li>
          <li>Broker failures or order rejections</li>
          <li>Technical failures or connectivity issues</li>
          <li>Inaccurate signals or delayed data</li>
        </ul>
        <p>
          See our{' '}
          <Link href="/legal/terms" className="text-primary-500 hover:underline">
            Terms of Service
          </Link>{' '}
          for full liability terms.
        </p>

        <h2>8. Acknowledgement</h2>
        <p>
          By using TeleBot, you acknowledge that you have read, understood, and accept this
          Risk Disclosure Statement in full.
        </p>

        <hr className="my-8" />

        <div className="flex gap-4 text-sm">
          <Link href="/legal/terms" className="text-primary-500 hover:underline">
            Terms of Service
          </Link>
          <Link href="/legal/privacy" className="text-primary-500 hover:underline">
            Privacy Policy
          </Link>
          <Link href="/legal/cookies" className="text-primary-500 hover:underline">
            Cookie Policy
          </Link>
        </div>
      </div>
    </div>
  );
}
