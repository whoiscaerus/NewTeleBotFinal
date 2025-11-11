"""
AI Analyst - Market outlook generation service (PR-091).

Generates daily AI-written "Market Outlook" with:
- Narrative summary with data citations
- Volatility zones
- Correlated risk view
- GOLD analytics context (RSI/ROC)

Depends on:
- PR-052: Equity & Drawdown Engine
- PR-053: Performance Metrics (Sharpe, Sortino)
- PR-062: AI Assistant Infrastructure
"""

import logging
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.ai.models import FeatureFlag
from backend.app.ai.schemas import CorrelationPair, OutlookReport, VolatilityZone
from backend.app.analytics.equity import EquitySeries

logger = logging.getLogger(__name__)


class FeatureDisabledError(Exception):
    """Raised when attempting to use a disabled feature."""

    pass


async def is_analyst_enabled(db: AsyncSession) -> bool:
    """
    Check if AI Analyst feature is enabled.

    Args:
        db: Database session

    Returns:
        bool: True if enabled, False otherwise
    """
    stmt = select(FeatureFlag).where(FeatureFlag.name == "ai_analyst")
    result = await db.execute(stmt)
    flag = result.scalar_one_or_none()

    if flag is None:
        logger.warning("AI Analyst feature flag not found, assuming disabled")
        return False

    return flag.enabled


async def is_analyst_owner_only(db: AsyncSession) -> bool:
    """
    Check if AI Analyst is in owner-only mode.

    Args:
        db: Database session

    Returns:
        bool: True if owner-only, False for public
    """
    stmt = select(FeatureFlag).where(FeatureFlag.name == "ai_analyst")
    result = await db.execute(stmt)
    flag = result.scalar_one_or_none()

    if flag is None:
        logger.warning("AI Analyst feature flag not found, assuming owner-only")
        return True

    return flag.owner_only


async def build_outlook(
    db: AsyncSession,
    target_date: date | None = None,
    instrument: str = "GOLD",
) -> OutlookReport:
    """
    Build AI-written market outlook with analytics data.

    Args:
        db: Database session
        target_date: Date for outlook (defaults to today)
        instrument: Instrument to analyze (default: GOLD)

    Returns:
        OutlookReport: Structured outlook with narrative, zones, correlations

    Raises:
        FeatureDisabledError: If AI Analyst is disabled
        ValueError: If data is insufficient for analysis

    Example:
        >>> outlook = await build_outlook(db, date(2024, 1, 15))
        >>> assert "Sharpe Ratio:" in outlook.narrative
        >>> assert len(outlook.volatility_zones) == 3
        >>> assert len(outlook.correlations) >= 1
    """
    # Check if feature is enabled
    if not await is_analyst_enabled(db):
        raise FeatureDisabledError("AI Analyst Mode is disabled")

    if target_date is None:
        target_date = date.today()

    logger.info(
        f"Building market outlook for {target_date} ({instrument})",
        extra={"target_date": target_date.isoformat(), "instrument": instrument},
    )

    # Pull analytics data (PR-052: Equity/Drawdown)
    try:
        equity_series = await _fetch_equity_series(db, target_date, days=90)
        drawdown_pct = _calculate_max_drawdown(equity_series)
    except Exception as e:
        logger.error(f"Failed to fetch equity data: {e}", exc_info=True)
        equity_series = None
        drawdown_pct = Decimal("0")

    # Pull performance metrics (PR-053: Sharpe, Sortino, Volatility)
    try:
        metrics = await _fetch_performance_metrics(db, target_date)
    except Exception as e:
        logger.error(f"Failed to fetch performance metrics: {e}", exc_info=True)
        metrics = {
            "sharpe_ratio": 0.0,
            "sortino_ratio": 0.0,
            "volatility_pct": 0.0,
            "win_rate": 0.0,
        }

    # Pull GOLD analytics context (RSI/ROC from existing analytics)
    try:
        gold_context = await _fetch_gold_context(db, target_date)
    except Exception as e:
        logger.error(f"Failed to fetch GOLD context: {e}", exc_info=True)
        gold_context = {"rsi": 50.0, "roc": 0.0}

    # Calculate volatility zones
    volatility_zones = _calculate_volatility_zones(metrics.get("volatility_pct", 0.0))

    # Calculate correlations (placeholder - would need multi-asset data)
    correlations = _calculate_correlations(instrument)

    # Generate narrative with data citations
    narrative = _generate_narrative(
        instrument=instrument,
        target_date=target_date,
        equity_series=equity_series,
        drawdown_pct=drawdown_pct,
        metrics=metrics,
        gold_context=gold_context,
        volatility_zones=volatility_zones,
        correlations=correlations,
    )

    # Build data citations dict
    data_citations = {
        "sharpe_ratio": metrics.get("sharpe_ratio", 0.0),
        "sortino_ratio": metrics.get("sortino_ratio", 0.0),
        "max_drawdown_pct": float(drawdown_pct),
        "volatility_pct": metrics.get("volatility_pct", 0.0),
        "win_rate": metrics.get("win_rate", 0.0),
        "rsi": gold_context.get("rsi", 50.0),
        "roc": gold_context.get("roc", 0.0),
    }

    logger.info(
        f"Outlook generated successfully for {target_date}",
        extra={
            "narrative_length": len(narrative),
            "zones": len(volatility_zones),
            "correlations": len(correlations),
        },
    )

    return OutlookReport(
        narrative=narrative,
        volatility_zones=volatility_zones,
        correlations=correlations,
        data_citations=data_citations,
        generated_at=datetime.utcnow(),
        instruments_covered=[instrument],
    )


async def _fetch_equity_series(
    db: AsyncSession, target_date: date, days: int = 90
) -> EquitySeries | None:
    """
    Fetch equity series for the last N days (PR-052).

    Args:
        db: Database session
        target_date: End date
        days: Lookback period

    Returns:
        EquitySeries or None if insufficient data
    """
    # This would call PR-052's compute_equity_series
    # For now, return placeholder to avoid import errors
    logger.info(f"Fetching equity series (last {days} days)")
    return None  # TODO: Integrate with PR-052's EquitySeries


async def _fetch_performance_metrics(
    db: AsyncSession, target_date: date
) -> dict[str, float]:
    """
    Fetch performance metrics (PR-053).

    Args:
        db: Database session
        target_date: Date for metrics

    Returns:
        Dict with sharpe_ratio, sortino_ratio, volatility_pct, win_rate
    """
    # This would call PR-053's PerformanceMetrics
    logger.info("Fetching performance metrics (90-day window)")

    # Placeholder values (would integrate with PR-053)
    return {
        "sharpe_ratio": 1.25,
        "sortino_ratio": 1.50,
        "volatility_pct": 12.5,
        "win_rate": 65.0,
    }


async def _fetch_gold_context(db: AsyncSession, target_date: date) -> dict[str, float]:
    """
    Fetch GOLD RSI/ROC context from existing analytics.

    Args:
        db: Database session
        target_date: Date for context

    Returns:
        Dict with rsi, roc values
    """
    logger.info("Fetching GOLD RSI/ROC context")

    # Placeholder values (would integrate with existing GOLD analytics)
    return {"rsi": 62.5, "roc": 2.3}


def _calculate_max_drawdown(equity_series: EquitySeries | None) -> Decimal:
    """
    Calculate maximum drawdown from equity series.

    Args:
        equity_series: Equity time series

    Returns:
        Decimal: Max drawdown as percentage (negative)
    """
    if equity_series is None:
        return Decimal("0")

    # Placeholder (PR-052 provides this)
    return Decimal("-15.3")


def _calculate_volatility_zones(volatility_pct: float) -> list[VolatilityZone]:
    """
    Calculate volatility zones (low/medium/high).

    Args:
        volatility_pct: Current volatility percentage

    Returns:
        List of 3 VolatilityZone objects
    """
    zones = [
        VolatilityZone(
            level="low",
            threshold=10.0,
            description="Calm market conditions, expect tight ranges",
        ),
        VolatilityZone(
            level="medium",
            threshold=20.0,
            description="Moderate volatility, normal trading conditions",
        ),
        VolatilityZone(
            level="high",
            threshold=30.0,
            description="Elevated volatility, expect wide swings",
        ),
    ]

    # Determine current zone
    current_level = "low"
    if volatility_pct >= 30.0:
        current_level = "high"
    elif volatility_pct >= 20.0:
        current_level = "medium"

    logger.info(
        f"Volatility zones calculated: current={current_level} ({volatility_pct:.1f}%)"
    )

    return zones


def _calculate_correlations(instrument: str) -> list[CorrelationPair]:
    """
    Calculate correlations with other instruments.

    Args:
        instrument: Base instrument (e.g., "GOLD")

    Returns:
        List of CorrelationPair objects (top 3)
    """
    # Placeholder correlations (would calculate from multi-asset data)
    correlations = [
        CorrelationPair(
            instrument_a=instrument, instrument_b="USD/JPY", coefficient=-0.65
        ),
        CorrelationPair(
            instrument_a=instrument, instrument_b="US10Y", coefficient=0.42
        ),
        CorrelationPair(instrument_a=instrument, instrument_b="DXY", coefficient=-0.78),
    ]

    logger.info(f"Calculated {len(correlations)} correlations for {instrument}")

    return correlations


def _generate_narrative(
    instrument: str,
    target_date: date,
    equity_series: EquitySeries | None,
    drawdown_pct: Decimal,
    metrics: dict[str, float],
    gold_context: dict[str, float],
    volatility_zones: list[VolatilityZone],
    correlations: list[CorrelationPair],
) -> str:
    """
    Generate AI-written narrative with data citations.

    Args:
        instrument: Instrument analyzed
        target_date: Date of outlook
        equity_series: Equity data
        drawdown_pct: Max drawdown percentage
        metrics: Performance metrics dict
        gold_context: GOLD RSI/ROC values
        volatility_zones: Volatility zones
        correlations: Correlation pairs

    Returns:
        str: Narrative text (200-5000 words)
    """
    # Determine current volatility zone
    volatility_pct = metrics.get("volatility_pct", 0.0)
    current_zone = "low"
    if volatility_pct >= 30.0:
        current_zone = "high"
    elif volatility_pct >= 20.0:
        current_zone = "medium"

    # Handle extreme values gracefully
    sharpe = metrics.get("sharpe_ratio", 0.0)
    sortino = metrics.get("sortino_ratio", 0.0)
    win_rate = metrics.get("win_rate", 0.0)
    rsi = gold_context.get("rsi", 50.0)
    roc = gold_context.get("roc", 0.0)

    # Check for extreme drawdown
    drawdown_warning = ""
    if abs(drawdown_pct) > 50:
        drawdown_warning = (
            f"\n\n⚠️ **EXTREME DRAWDOWN ALERT**: Current drawdown of {drawdown_pct:.1f}% "
            f"is significantly elevated. Exercise extreme caution."
        )

    # Check for zero trades
    if equity_series is None or win_rate == 0.0:
        return (
            f"## Daily Market Outlook - {target_date.strftime('%B %d, %Y')}\n\n"
            f"### {instrument} Analysis\n\n"
            f"**No Trading Activity**: Insufficient data for comprehensive analysis. "
            f"No trades have been executed in the analysis period. "
            f"This outlook will be generated once trading activity resumes.\n\n"
            f"### Data Summary\n"
            f"- Sharpe Ratio: N/A\n"
            f"- Sortino Ratio: N/A\n"
            f"- Max Drawdown: N/A\n"
            f"- Volatility: N/A\n"
            f"- Win Rate: N/A\n"
            f"- RSI (14): {rsi:.1f}\n"
            f"- ROC (10): {roc:.2f}%\n\n"
            f"---\n\n"
            f"*This is an AI-generated analysis. Not financial advice.*"
        )

    # Generate narrative with citations
    narrative = f"""## Daily Market Outlook - {target_date.strftime('%B %d, %Y')}

### {instrument} Analysis

**Performance Overview**

Our {instrument} strategy has delivered a **Sharpe Ratio of {sharpe:.2f}** over the past 90 days, indicating {"strong" if sharpe > 1.5 else "moderate" if sharpe > 1.0 else "developing"} risk-adjusted returns. The **Sortino Ratio of {sortino:.2f}** suggests {"excellent" if sortino > 2.0 else "good" if sortino > 1.5 else "acceptable"} downside risk management, focusing on negative volatility rather than total volatility.

Current **maximum drawdown stands at {drawdown_pct:.1f}%**, which is {"within acceptable parameters" if abs(drawdown_pct) < 20 else "elevated and warrants caution" if abs(drawdown_pct) < 40 else "significantly elevated - exercise extreme caution"}. The strategy maintains a **win rate of {win_rate:.1f}%**, demonstrating {"strong" if win_rate > 70 else "solid" if win_rate > 60 else "moderate"} trade selection.

**Volatility Analysis**

Market volatility is currently at **{volatility_pct:.1f}%**, placing us in the **{current_zone} volatility zone**. {_get_volatility_commentary(current_zone, volatility_pct)}

**Technical Context**

The 14-period Relative Strength Index (RSI) for {instrument} reads **{rsi:.1f}**, suggesting the market is {"overbought - watch for potential pullbacks" if rsi > 70 else "oversold - watch for potential bounces" if rsi < 30 else "in neutral territory"}. The 10-period Rate of Change (ROC) at **{roc:.2f}%** indicates {"bullish momentum" if roc > 2 else "bearish momentum" if roc < -2 else "sideways momentum"}.

**Correlation Analysis**

Cross-asset correlations reveal important relationships:

{_format_correlations(correlations)}

**Outlook**

{"Given the strong risk-adjusted returns and manageable drawdown, the strategy remains well-positioned." if sharpe > 1.0 and abs(drawdown_pct) < 20 else "Monitor current drawdown levels closely and consider risk management adjustments." if abs(drawdown_pct) > 20 else "Focus on rebuilding positive momentum with disciplined risk management."} The {current_zone} volatility environment {"supports active trading with standard position sizing" if current_zone == "low" else "suggests maintaining standard risk parameters" if current_zone == "medium" else "warrants reduced position sizes and tighter stop losses"}.

Traders should remain vigilant for {"continuation patterns" if roc > 0 else "reversal signals"} and manage positions according to their individual risk tolerance.{drawdown_warning}

### Data Citations

- **Sharpe Ratio**: {sharpe:.2f} (90-day rolling)
- **Sortino Ratio**: {sortino:.2f} (90-day rolling)
- **Max Drawdown**: {drawdown_pct:.1f}%
- **Volatility**: {volatility_pct:.1f}% (annualized)
- **Win Rate**: {win_rate:.1f}%
- **RSI (14)**: {rsi:.1f}
- **ROC (10)**: {roc:.2f}%

---

*This is an AI-generated analysis based on historical data. Past performance does not guarantee future results. Not financial advice. Trade at your own risk.*
"""

    return narrative.strip()


def _get_volatility_commentary(zone: str, volatility_pct: float) -> str:
    """Get commentary based on volatility zone."""
    if zone == "low":
        return (
            "This calm environment typically supports tighter stop-losses and "
            "profit targets. Expect price action to remain range-bound with limited breakouts."
        )
    elif zone == "medium":
        return (
            "Normal trading conditions prevail. Standard risk management practices apply. "
            "Watch for trend development opportunities."
        )
    else:  # high
        return (
            "Elevated volatility demands heightened caution. Consider reducing position sizes, "
            "widening stop-losses, and being selective with trade entries. Major directional moves are possible."
        )


def _format_correlations(correlations: list[CorrelationPair]) -> str:
    """Format correlations as bullet points."""
    lines = []
    for corr in correlations:
        strength = "strong" if abs(corr.coefficient) > 0.7 else "moderate"
        direction = "positive" if corr.coefficient > 0 else "negative"
        lines.append(
            f"- **{corr.instrument_b}**: {strength} {direction} correlation "
            f"({corr.coefficient:+.2f}) - "
            f"{'moves in tandem' if corr.coefficient > 0 else 'moves inversely'}"
        )
    return "\n".join(lines)
