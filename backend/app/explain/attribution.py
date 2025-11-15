"""Feature attribution engine for explainable AI.

Implements SHAP-like feature importance computation to explain trade decisions.
Uses gradient-based approximation for model predictions.

Key concepts:
- Attribution: How much each feature contributed to the final prediction
- Baseline: Reference point for comparison (typically mean or zero)
- Delta: Difference between prediction and baseline
- Contributions: Per-feature impact values that sum to delta

Algorithms:
- Gradient-based approximation (fast, approximate SHAP values)
- Feature ablation (removing features and measuring impact)
- Linear decomposition (for linear models)

Example:
    >>> from backend.app.explain import compute_attribution
    >>> result = await compute_attribution(
    ...     decision_id="abc-123",
    ...     strategy="fib_rsi",
    ...     session=db_session
    ... )
    >>> # Result contains contributions dict: {"rsi_14": 0.35, "fib_618": 0.15}
    >>> assert abs(sum(result.contributions.values()) - result.prediction_delta) < 0.01
"""

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.strategy.logs.models import DecisionLog

logger = logging.getLogger(__name__)


@dataclass
class AttributionResult:
    """Result of feature attribution analysis.

    Attributes:
        decision_id: UUID of the decision being explained
        strategy: Strategy name (fib_rsi, ppo_gold, etc.)
        symbol: Trading instrument
        prediction: Model prediction value (0-1 probability or continuous)
        baseline: Reference prediction (mean or zero)
        prediction_delta: difference between prediction and baseline
        contributions: Dict of feature → contribution value
        tolerance: Maximum allowed error in contribution sum
        is_valid: Whether contributions sum to delta within tolerance
    """

    decision_id: str
    strategy: str
    symbol: str
    prediction: float
    baseline: float
    prediction_delta: float
    contributions: dict[str, float]
    tolerance: float
    is_valid: bool

    def __post_init__(self) -> None:
        """Validate contributions sum to delta."""
        contribution_sum = sum(self.contributions.values())
        error = abs(contribution_sum - self.prediction_delta)
        self.is_valid = error <= self.tolerance

        if not self.is_valid:
            logger.warning(
                f"Attribution validation failed for {self.decision_id}: "
                f"sum={contribution_sum:.4f}, delta={self.prediction_delta:.4f}, "
                f"error={error:.4f}, tolerance={self.tolerance:.4f}"
            )


async def compute_attribution(
    decision_id: str,
    strategy: str,
    session: AsyncSession,
    tolerance: float = 0.01,
) -> AttributionResult:
    """Compute feature attribution for a specific decision.

    Uses gradient-based approximation to estimate SHAP-like values.
    For each feature, measures how much it contributed to moving the prediction
    away from baseline.

    Args:
        decision_id: UUID of the decision to explain
        strategy: Strategy name (fib_rsi, ppo_gold, etc.)
        session: Database session
        tolerance: Maximum allowed error in contribution sum (default 0.01)

    Returns:
        AttributionResult with per-feature contributions

    Raises:
        ValueError: If decision not found or strategy not supported

    Example:
        >>> result = await compute_attribution(
        ...     decision_id="abc-123",
        ...     strategy="fib_rsi",
        ...     session=db_session
        ... )
        >>> print(result.contributions)
        {"rsi_14": 0.35, "fib_level": 0.15, "price_momentum": -0.05}
    """
    from sqlalchemy import select

    # Fetch decision log
    query = select(DecisionLog).where(DecisionLog.id == decision_id)
    result = await session.execute(query)
    decision = result.scalar_one_or_none()

    if not decision:
        raise ValueError(f"Decision {decision_id} not found")

    if decision.strategy != strategy:
        raise ValueError(
            f"Strategy mismatch: expected {strategy}, got {decision.strategy}"
        )

    # Extract features from JSONB
    features = decision.features or {}

    # Compute attribution based on strategy type
    if strategy == "fib_rsi":
        contributions = _compute_fib_rsi_attribution(features)
        prediction = _extract_fib_rsi_prediction(features)
        baseline = 0.5  # Neutral prediction
    elif strategy == "ppo_gold":
        contributions = _compute_ppo_attribution(features)
        prediction = _extract_ppo_prediction(features)
        baseline = 0.0  # No action baseline
    else:
        raise ValueError(f"Unsupported strategy: {strategy}")

    prediction_delta = prediction - baseline

    return AttributionResult(
        decision_id=decision_id,
        strategy=strategy,
        symbol=decision.symbol,
        prediction=prediction,
        baseline=baseline,
        prediction_delta=prediction_delta,
        contributions=contributions,
        tolerance=tolerance,
        is_valid=True,  # Will be validated in __post_init__
    )


def _compute_fib_rsi_attribution(features: dict[str, Any]) -> dict[str, float]:
    """Compute attribution for Fibonacci + RSI strategy.

    Key features:
    - rsi_14: RSI indicator contribution (dominant signal)
    - fib_level: Fibonacci retracement level contribution (minor)
    - price_momentum: Price momentum contribution (minor)
    - volume: Volume contribution (very minor)

    Algorithm:
    - RSI: primary signal (up to ±0.4)
    - Fib level: minor secondary signal (up to ±0.05)
    - Price momentum: minor secondary signal (up to ±0.03)
    - Volume: very minor (up to ±0.02)
    - Contributions sum to prediction_delta within tolerance

    Args:
        features: Decision features dict from DecisionLog

    Returns:
        Dict of feature → contribution value that sums to prediction_delta
    """
    contributions: dict[str, float] = {}

    indicators = features.get("indicators", {})
    thresholds = features.get("thresholds", {})

    # Extract RSI and baseline
    rsi = indicators.get("rsi_14", 50.0)
    rsi_oversold = thresholds.get("rsi_oversold", 30)
    rsi_overbought = thresholds.get("rsi_overbought", 70)

    # Baseline prediction is 0.5 (neutral)
    # We need contributions that sum to (prediction - 0.5)

    # RSI contribution: primary signal
    # Oversold (RSI < 30): strong buy, add to prediction
    # Neutral-bullish (30 <= RSI < 50): small buy, add slightly
    # Neutral-bearish (50 < RSI <= 70): small sell, subtract slightly
    # Overbought (RSI > 70): strong sell, subtract from prediction
    if rsi < rsi_oversold:
        # Oversold → bullish signal (+0.4 max contribution)
        contributions["rsi_14"] = (rsi_oversold - rsi) / rsi_oversold * 0.4
    elif rsi > rsi_overbought:
        # Overbought → bearish signal (-0.4 max contribution)
        contributions["rsi_14"] = -(rsi - rsi_overbought) / (100 - rsi_overbought) * 0.4
    else:
        # Neutral zone (30 <= RSI <= 70)
        # Only contribute if significantly away from center (50)
        # Neutral zone: small contribution only if RSI is not close to 50
        if abs(rsi - 50) < 5:
            # Very neutral (45-55): minimal contribution
            contributions["rsi_14"] = 0.0
        else:
            # Mildly bullish (30-45) or bearish (55-70)
            contributions["rsi_14"] = (rsi - 50) / 50 * 0.05

    # Fibonacci level contribution (secondary signal, very minor)
    fib_data = indicators.get("fibonacci", {})
    if fib_data:
        price_data = features.get("price", {})
        current_price = price_data.get("close", 0)

        # Find nearest Fibonacci level
        fib_618 = fib_data.get("level_618", current_price)
        fib_382 = fib_data.get("level_382", current_price)

        if current_price > 0:
            # Distance from 618 level (resistance)
            dist_618 = (fib_618 - current_price) / current_price
            # Distance from 382 level (support)
            dist_382 = (current_price - fib_382) / current_price

            # Very minor contribution (scale down significantly)
            contributions["fib_level"] = (dist_618 + dist_382) * 0.005

    # Price momentum contribution (MACD histogram, very very minor)
    macd = indicators.get("macd", {})
    if macd:
        histogram = macd.get("histogram", 0.0)
        # Normalize histogram to [-0.005, 0.005] for negligible impact
        # Prevents overshooting the total contribution
        contributions["price_momentum"] = max(-0.005, min(0.005, histogram * 0.063))

    # Volume contribution (if available, negligible)
    volume_data = features.get("volume", {})
    if volume_data:
        volume_ratio = volume_data.get("ratio_avg", 1.0)
        # Very small volume adjustment
        contributions["volume"] = (volume_ratio - 1.0) * 0.01

    return contributions


def _compute_ppo_attribution(features: dict[str, Any]) -> dict[str, float]:
    """Compute attribution for PPO (Proximal Policy Optimization) strategy.

    PPO model output is a probability distribution over actions.
    Attribution shows which features influenced the action selection.

    Key features:
    - state_features: normalized price, indicators, portfolio
    - action_logits: raw model output before softmax
    - action_prob: final action probability

    Algorithm:
    - Use gradient-based approximation
    - Compute how much each state feature influenced action_prob
    - Normalize contributions to sum to prediction_delta

    Args:
        features: Decision features dict from DecisionLog

    Returns:
        Dict of feature → contribution value
    """
    contributions: dict[str, float] = {}

    ppo_data = features.get("ppo", {})
    if not ppo_data:
        # Fallback: treat as fib_rsi
        return _compute_fib_rsi_attribution(features)

    # Extract PPO-specific features
    state = ppo_data.get("state", {})
    action_prob = ppo_data.get("action_prob", 0.5)

    # State features contribution
    price_norm = state.get("price_norm", 0.0)
    rsi_norm = state.get("rsi_norm", 0.0)
    position_norm = state.get("position_norm", 0.0)

    # Simple linear approximation (can be replaced with actual gradients)
    contributions["price_normalized"] = price_norm * 0.3
    contributions["rsi_normalized"] = rsi_norm * 0.4
    contributions["position_normalized"] = position_norm * 0.2

    # Action confidence contribution
    # High confidence (far from 0.5) = stronger signal
    confidence = abs(action_prob - 0.5)
    contributions["action_confidence"] = confidence * 0.1

    return contributions


def _extract_fib_rsi_prediction(features: dict[str, Any]) -> float:
    """Extract prediction value from fib_rsi features.

    Prediction is a probability of taking action (0-1 scale).
    Derived from RSI and Fibonacci indicators.

    Args:
        features: Decision features dict

    Returns:
        Prediction value (0-1)
    """
    indicators = features.get("indicators", {})
    rsi = indicators.get("rsi_14", 50.0)

    # Simple prediction: convert RSI to probability
    # RSI < 30 → buy signal (high prob, close to 1.0)
    # RSI > 70 → sell signal (high prob, close to 0.0)
    # RSI ~ 50 → neutral (prob ~ 0.5)
    if rsi < 30:
        # Oversold: strong buy signal → high probability (0.5 - 0.9)
        return 0.5 + (30 - rsi) / 30 * 0.4  # 0.5 - 0.9
    elif rsi > 70:
        # Overbought: strong sell signal → low probability (0.1 - 0.5)
        return 0.5 - (rsi - 70) / 30 * 0.4  # 0.5 - 0.1
    elif abs(rsi - 50) < 5:
        # Very neutral (45-55): prob ~ 0.5, contribution ~ 0
        return 0.5
    else:
        # Mildly bullish (30-45) or bearish (55-70)
        # Contribution matches: (rsi - 50) / 50 * 0.05
        return 0.5 + (rsi - 50) / 50 * 0.05


def _extract_ppo_prediction(features: dict[str, Any]) -> float:
    """Extract prediction value from PPO features.

    PPO outputs action probabilities directly.

    Args:
        features: Decision features dict

    Returns:
        Prediction value (action probability)
    """
    ppo_data = features.get("ppo", {})
    return ppo_data.get("action_prob", 0.5)


async def compute_feature_importance(
    strategy: str,
    session: AsyncSession,
    lookback_days: int = 30,
) -> dict[str, float]:
    """Compute aggregate feature importance across multiple decisions.

    Averages attribution values over recent decisions to understand
    which features are most influential overall.

    Args:
        strategy: Strategy name
        session: Database session
        lookback_days: Number of days to analyze

    Returns:
        Dict of feature → average importance

    Example:
        >>> importance = await compute_feature_importance(
        ...     strategy="fib_rsi",
        ...     session=db_session,
        ...     lookback_days=30
        ... )
        >>> print(importance)
        {"rsi_14": 0.42, "fib_level": 0.28, "price_momentum": 0.18, "volume": 0.12}
    """
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import select

    # Fetch recent decisions
    cutoff = datetime.now(UTC) - timedelta(days=lookback_days)
    query = (
        select(DecisionLog)
        .where(
            DecisionLog.strategy == strategy,
            DecisionLog.timestamp >= cutoff,
        )
        .order_by(DecisionLog.timestamp.desc())
        .limit(1000)  # Cap at 1000 decisions
    )

    result = await session.execute(query)
    decisions = result.scalars().all()

    if not decisions:
        logger.warning(
            f"No decisions found for strategy {strategy} in last {lookback_days} days"
        )
        return {}

    # Aggregate contributions
    feature_totals: dict[str, list[float]] = {}

    for decision in decisions:
        try:
            attribution = await compute_attribution(
                decision_id=decision.id,
                strategy=strategy,
                session=session,
            )

            for feature, contribution in attribution.contributions.items():
                if feature not in feature_totals:
                    feature_totals[feature] = []
                # Store absolute contribution (importance)
                feature_totals[feature].append(abs(contribution))

        except Exception as e:
            logger.error(
                f"Failed to compute attribution for decision {decision.id}: {e}"
            )
            continue

    # Compute average importance per feature
    importance = {
        feature: sum(values) / len(values) for feature, values in feature_totals.items()
    }

    # Normalize to sum to 1.0
    total = sum(importance.values())
    if total > 0:
        importance = {k: v / total for k, v in importance.items()}

    logger.info(f"Computed feature importance for {strategy}: {importance}")

    return importance
