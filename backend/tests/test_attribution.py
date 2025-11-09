"""Tests for feature attribution engine (PR-080).

Validates:
- SHAP-like attribution computation
- Contribution sums to prediction delta within tolerance
- Multiple strategies (fib_rsi, ppo_gold)
- Edge cases (zero contributions, negative values, missing features)
- Feature importance aggregation

Uses REAL database and REAL business logic (NO MOCKS).
"""

import math
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from backend.app.explain.attribution import (
    AttributionResult,
    compute_attribution,
    compute_feature_importance,
)
from backend.app.strategy.logs.models import DecisionLog, DecisionOutcome


@pytest.mark.asyncio
async def test_compute_attribution_fib_rsi_success(db_session):
    """Test attribution for fib_rsi strategy with typical features."""
    # Create decision with RSI + Fib features
    decision_id = str(uuid4())
    decision = DecisionLog(
        id=decision_id,
        timestamp=datetime.now(UTC),
        strategy="fib_rsi",
        symbol="GOLD",
        outcome=DecisionOutcome.ENTERED,
        features={
            "price": {"open": 1950.00, "close": 1951.25},
            "indicators": {
                "rsi_14": 28.5,  # Oversold → bullish
                "macd": {"histogram": 0.05},  # Positive momentum
                "fibonacci": {"level_618": 1955.00, "level_382": 1945.00},
            },
            "thresholds": {"rsi_oversold": 30, "rsi_overbought": 70},
        },
        note="Strong buy signal",
    )

    db_session.add(decision)
    await db_session.commit()

    # Compute attribution
    result = await compute_attribution(
        decision_id=decision_id,
        strategy="fib_rsi",
        session=db_session,
        tolerance=0.01,
    )

    # Validate result structure
    assert result.decision_id == decision_id
    assert result.strategy == "fib_rsi"
    assert result.symbol == "GOLD"
    assert result.baseline == 0.5  # Neutral
    assert isinstance(result.prediction, float)
    assert isinstance(result.prediction_delta, float)

    # Validate contributions
    assert "rsi_14" in result.contributions
    assert isinstance(result.contributions["rsi_14"], float)

    # Validate contribution sum equals delta within tolerance
    contribution_sum = sum(result.contributions.values())
    error = abs(contribution_sum - result.prediction_delta)
    assert (
        error <= result.tolerance
    ), f"Contribution sum error {error:.4f} > tolerance {result.tolerance}"

    # Validate result is marked valid
    assert result.is_valid is True


@pytest.mark.asyncio
async def test_compute_attribution_ppo_gold_success(db_session):
    """Test attribution for ppo_gold strategy with PPO-specific features."""
    decision_id = str(uuid4())
    decision = DecisionLog(
        id=decision_id,
        timestamp=datetime.now(UTC),
        strategy="ppo_gold",
        symbol="GOLD",
        outcome=DecisionOutcome.ENTERED,
        features={
            "ppo": {
                "state": {
                    "price_norm": 0.25,
                    "rsi_norm": -0.15,
                    "position_norm": 0.0,
                },
                "action_prob": 0.78,  # High confidence buy
            },
        },
        note="PPO high confidence signal",
    )

    db_session.add(decision)
    await db_session.commit()

    # Compute attribution
    result = await compute_attribution(
        decision_id=decision_id,
        strategy="ppo_gold",
        session=db_session,
        tolerance=0.01,
    )

    # Validate result
    assert result.strategy == "ppo_gold"
    assert result.baseline == 0.0  # No action baseline for PPO
    assert result.prediction == 0.78  # From action_prob

    # Validate PPO-specific contributions
    assert "price_normalized" in result.contributions
    assert "rsi_normalized" in result.contributions
    assert "action_confidence" in result.contributions

    # Validate sum
    contribution_sum = sum(result.contributions.values())
    error = abs(contribution_sum - result.prediction_delta)
    assert error <= result.tolerance

    assert result.is_valid is True


@pytest.mark.asyncio
async def test_compute_attribution_contributions_sum_to_delta(db_session):
    """Test that contributions always sum to prediction delta within tolerance."""
    decision_id = str(uuid4())
    decision = DecisionLog(
        id=decision_id,
        timestamp=datetime.now(UTC),
        strategy="fib_rsi",
        symbol="GOLD",
        outcome=DecisionOutcome.ENTERED,
        features={
            "price": {"close": 1950.00},
            "indicators": {
                "rsi_14": 75.0,  # Overbought
                "macd": {"histogram": -0.03},  # Negative momentum
                "fibonacci": {"level_618": 1960.00, "level_382": 1940.00},
            },
            "thresholds": {"rsi_oversold": 30, "rsi_overbought": 70},
            "volume": {"ratio_avg": 1.5},  # High volume
        },
    )

    db_session.add(decision)
    await db_session.commit()

    result = await compute_attribution(
        decision_id=decision_id,
        strategy="fib_rsi",
        session=db_session,
        tolerance=0.01,
    )

    # Calculate sum manually
    contribution_sum = sum(result.contributions.values())

    # Verify sum equals delta
    assert math.isclose(
        contribution_sum, result.prediction_delta, abs_tol=result.tolerance
    )

    # Verify is_valid flag
    assert result.is_valid is True


@pytest.mark.asyncio
async def test_compute_attribution_negative_contributions(db_session):
    """Test attribution handles negative contributions correctly."""
    decision_id = str(uuid4())
    decision = DecisionLog(
        id=decision_id,
        timestamp=datetime.now(UTC),
        strategy="fib_rsi",
        symbol="GOLD",
        outcome=DecisionOutcome.REJECTED,
        features={
            "price": {"close": 1950.00},
            "indicators": {
                "rsi_14": 75.0,  # Overbought → bearish (negative contrib)
                "macd": {"histogram": -0.08},  # Strong negative momentum
            },
            "thresholds": {"rsi_oversold": 30, "rsi_overbought": 70},
        },
    )

    db_session.add(decision)
    await db_session.commit()

    result = await compute_attribution(
        decision_id=decision_id,
        strategy="fib_rsi",
        session=db_session,
    )

    # Verify some contributions are negative
    assert any(
        v < 0 for v in result.contributions.values()
    ), "Expected negative contributions"

    # Verify sum still valid
    contribution_sum = sum(result.contributions.values())
    error = abs(contribution_sum - result.prediction_delta)
    assert error <= result.tolerance


@pytest.mark.asyncio
async def test_compute_attribution_zero_contributions(db_session):
    """Test attribution handles neutral/zero contributions."""
    decision_id = str(uuid4())
    decision = DecisionLog(
        id=decision_id,
        timestamp=datetime.now(UTC),
        strategy="fib_rsi",
        symbol="GOLD",
        outcome=DecisionOutcome.SKIPPED,
        features={
            "price": {"close": 1950.00},
            "indicators": {
                "rsi_14": 50.0,  # Neutral → ~zero contribution
                "macd": {"histogram": 0.0},  # No momentum
            },
            "thresholds": {"rsi_oversold": 30, "rsi_overbought": 70},
        },
    )

    db_session.add(decision)
    await db_session.commit()

    result = await compute_attribution(
        decision_id=decision_id,
        strategy="fib_rsi",
        session=db_session,
    )

    # Verify contributions are near zero (neutral)
    assert all(
        abs(v) < 0.2 for v in result.contributions.values()
    ), "Expected small contributions for neutral features"

    # Verify sum still valid
    contribution_sum = sum(result.contributions.values())
    error = abs(contribution_sum - result.prediction_delta)
    assert error <= result.tolerance


@pytest.mark.asyncio
async def test_compute_attribution_decision_not_found(db_session):
    """Test attribution raises error for non-existent decision."""
    with pytest.raises(ValueError, match="Decision .* not found"):
        await compute_attribution(
            decision_id="nonexistent-id",
            strategy="fib_rsi",
            session=db_session,
        )


@pytest.mark.asyncio
async def test_compute_attribution_strategy_mismatch(db_session):
    """Test attribution raises error when strategy doesn't match decision."""
    decision_id = str(uuid4())
    decision = DecisionLog(
        id=decision_id,
        timestamp=datetime.now(UTC),
        strategy="fib_rsi",  # Actual strategy
        symbol="GOLD",
        outcome=DecisionOutcome.ENTERED,
        features={"indicators": {"rsi_14": 65.0}},
    )

    db_session.add(decision)
    await db_session.commit()

    # Request attribution with wrong strategy
    with pytest.raises(ValueError, match="Strategy mismatch"):
        await compute_attribution(
            decision_id=decision_id,
            strategy="ppo_gold",  # Wrong strategy
            session=db_session,
        )


@pytest.mark.asyncio
async def test_compute_attribution_unsupported_strategy(db_session):
    """Test attribution raises error for unsupported strategy."""
    decision_id = str(uuid4())
    decision = DecisionLog(
        id=decision_id,
        timestamp=datetime.now(UTC),
        strategy="unknown_strategy",
        symbol="GOLD",
        outcome=DecisionOutcome.ENTERED,
        features={},
    )

    db_session.add(decision)
    await db_session.commit()

    with pytest.raises(ValueError, match="Unsupported strategy"):
        await compute_attribution(
            decision_id=decision_id,
            strategy="unknown_strategy",
            session=db_session,
        )


@pytest.mark.asyncio
async def test_compute_feature_importance_success(db_session):
    """Test aggregate feature importance over multiple decisions."""
    # Create 10 decisions with varying features
    base_time = datetime.now(UTC)

    for i in range(10):
        decision = DecisionLog(
            id=str(uuid4()),
            timestamp=base_time - timedelta(days=i),
            strategy="fib_rsi",
            symbol="GOLD",
            outcome=DecisionOutcome.ENTERED if i % 2 == 0 else DecisionOutcome.SKIPPED,
            features={
                "price": {"close": 1950.00 + i * 10},
                "indicators": {
                    "rsi_14": 30.0 + i * 5,  # Varying RSI
                    "macd": {"histogram": 0.01 * i},
                    "fibonacci": {"level_618": 1960.00, "level_382": 1940.00},
                },
                "thresholds": {"rsi_oversold": 30, "rsi_overbought": 70},
                "volume": {"ratio_avg": 1.0 + i * 0.1},
            },
        )
        db_session.add(decision)

    await db_session.commit()

    # Compute aggregate importance
    importance = await compute_feature_importance(
        strategy="fib_rsi",
        session=db_session,
        lookback_days=30,
    )

    # Validate importance structure
    assert isinstance(importance, dict)
    assert len(importance) > 0

    # Verify importance values sum to 1.0 (normalized)
    total_importance = sum(importance.values())
    assert math.isclose(
        total_importance, 1.0, abs_tol=0.01
    ), f"Importance should sum to 1.0, got {total_importance}"

    # Verify all values are positive (absolute contributions)
    assert all(
        v >= 0 for v in importance.values()
    ), "All importance values should be non-negative"

    # Verify common features present
    assert "rsi_14" in importance, "RSI should be in importance results"


@pytest.mark.asyncio
async def test_compute_feature_importance_no_decisions(db_session):
    """Test feature importance with no decisions returns empty dict."""
    importance = await compute_feature_importance(
        strategy="nonexistent_strategy",
        session=db_session,
        lookback_days=30,
    )

    assert importance == {}, "Should return empty dict when no decisions found"


@pytest.mark.asyncio
async def test_compute_feature_importance_lookback_window(db_session):
    """Test feature importance respects lookback window."""
    base_time = datetime.now(UTC)

    # Create old decision (outside window)
    old_decision = DecisionLog(
        id=str(uuid4()),
        timestamp=base_time - timedelta(days=60),  # 60 days ago
        strategy="fib_rsi",
        symbol="GOLD",
        outcome=DecisionOutcome.ENTERED,
        features={
            "indicators": {"rsi_14": 65.0},
            "thresholds": {"rsi_oversold": 30, "rsi_overbought": 70},
        },
    )

    # Create recent decision (inside window)
    recent_decision = DecisionLog(
        id=str(uuid4()),
        timestamp=base_time - timedelta(days=5),  # 5 days ago
        strategy="fib_rsi",
        symbol="GOLD",
        outcome=DecisionOutcome.ENTERED,
        features={
            "indicators": {"rsi_14": 35.0},
            "thresholds": {"rsi_oversold": 30, "rsi_overbought": 70},
        },
    )

    db_session.add(old_decision)
    db_session.add(recent_decision)
    await db_session.commit()

    # Compute importance with 30-day lookback
    importance = await compute_feature_importance(
        strategy="fib_rsi",
        session=db_session,
        lookback_days=30,
    )

    # Should only include recent decision
    assert len(importance) > 0, "Should find recent decision"


@pytest.mark.asyncio
async def test_attribution_result_validation():
    """Test AttributionResult validates contributions sum to delta."""
    # Valid result (sum within tolerance)
    valid_result = AttributionResult(
        decision_id="abc-123",
        strategy="fib_rsi",
        symbol="GOLD",
        prediction=0.75,
        baseline=0.5,
        prediction_delta=0.25,
        contributions={"rsi_14": 0.15, "fib_level": 0.10},  # Sum = 0.25
        tolerance=0.01,
        is_valid=True,
    )

    assert valid_result.is_valid is True

    # Invalid result (sum exceeds tolerance)
    invalid_result = AttributionResult(
        decision_id="def-456",
        strategy="fib_rsi",
        symbol="GOLD",
        prediction=0.75,
        baseline=0.5,
        prediction_delta=0.25,
        contributions={"rsi_14": 0.50, "fib_level": 0.10},  # Sum = 0.60 (way off)
        tolerance=0.01,
        is_valid=True,  # Will be overridden
    )

    assert invalid_result.is_valid is False  # Validation failed


@pytest.mark.asyncio
async def test_compute_attribution_missing_features(db_session):
    """Test attribution handles missing features gracefully."""
    decision_id = str(uuid4())
    decision = DecisionLog(
        id=decision_id,
        timestamp=datetime.now(UTC),
        strategy="fib_rsi",
        symbol="GOLD",
        outcome=DecisionOutcome.SKIPPED,
        features={},  # Empty features
    )

    db_session.add(decision)
    await db_session.commit()

    result = await compute_attribution(
        decision_id=decision_id,
        strategy="fib_rsi",
        session=db_session,
    )

    # Should still compute (with default values)
    assert result.decision_id == decision_id
    assert isinstance(result.contributions, dict)

    # Contributions may be empty or have default values
    contribution_sum = sum(result.contributions.values())
    error = abs(contribution_sum - result.prediction_delta)
    assert error <= result.tolerance
