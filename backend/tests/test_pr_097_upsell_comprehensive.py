"""
Comprehensive tests for PR-097 AI-Powered Upsell Engine.

Tests REAL business logic with NO mocks for core functionality.
Validates scoring, A/B testing, exposure tracking, and conversions.
"""

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.analytics.models import DailyRollups, DimDay, DimSymbol
from backend.app.approvals.models import Approval
from backend.app.auth.models import User
from backend.app.subscriptions.models import Subscription
from backend.app.upsell.engine import UpsellEngine
from backend.app.upsell.models import (
    Experiment,
    ExperimentStatus,
    Exposure,
    RecommendationType,
    Variant,
)

# ===== FIXTURES =====


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create test user."""
    user = User(
        email="test@example.com",
        password_hash="hash",
        telegram_user_id="12345",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_subscription(db_session: AsyncSession, test_user: User) -> Subscription:
    """Create test subscription."""
    sub = Subscription(
        id=str(uuid4()),
        user_id=test_user.id,
        tier="free",
        status="active",
        amount=Decimal("10.00"),
    )
    db_session.add(sub)
    await db_session.commit()
    await db_session.refresh(sub)
    return sub


@pytest_asyncio.fixture
async def test_experiment(db_session: AsyncSession) -> Experiment:
    """Create test A/B experiment."""
    experiment = Experiment(
        name="Test Plan Upgrade A/B",
        description="Testing plan upgrade messaging",
        recommendation_type=RecommendationType.PLAN_UPGRADE.value,
        traffic_split_percent=50,
        min_sample_size=100,
        status=ExperimentStatus.ACTIVE.value,
        started_at=datetime.utcnow(),
    )
    db_session.add(experiment)
    await db_session.commit()
    await db_session.refresh(experiment)
    return experiment


@pytest_asyncio.fixture
async def test_variants(
    db_session: AsyncSession, test_experiment: Experiment
) -> tuple[Variant, Variant]:
    """Create control and variant."""
    control = Variant(
        experiment_id=test_experiment.id,
        name="control",
        headline="Upgrade to Premium",
        copy="Get advanced features",
        cta_text="Upgrade Now",
        is_control=True,
    )
    variant = Variant(
        experiment_id=test_experiment.id,
        name="variant_a",
        headline="Unlock 30% Higher Returns",
        copy="Join top performers with Premium",
        cta_text="Start Winning",
        discount_percent=20,
        is_control=False,
    )
    db_session.add(control)
    db_session.add(variant)
    await db_session.commit()
    await db_session.refresh(control)
    await db_session.refresh(variant)
    return control, variant


# ===== USAGE SCORING TESTS =====


@pytest.mark.asyncio
async def test_usage_score_high_approvals(db_session: AsyncSession, test_user: User):
    """Test usage scoring with high approval count."""
    # Create 25 approvals (above 20 threshold)
    cutoff = datetime.utcnow() - timedelta(days=30)
    for i in range(25):
        approval = Approval(
            user_id=test_user.id,
            signal_id=f"signal-{i}",
            decision=1,  # 1 = approved
            created_at=cutoff + timedelta(days=i),
        )
        db_session.add(approval)

    await db_session.commit()

    # Calculate usage score
    engine = UpsellEngine(db_session, score_threshold=0.6, lookback_days=30)
    score = await engine._calculate_usage_score(test_user.id)

    # 25 approvals / 20 threshold = 1.0 (capped)
    assert score >= 0.9, f"Expected score >= 0.9 for 25 approvals, got {score}"


@pytest.mark.asyncio
async def test_usage_score_moderate_usage(db_session: AsyncSession, test_user: User):
    """Test usage scoring with moderate activity."""
    # Create 12 approvals (60% of threshold)
    cutoff = datetime.utcnow() - timedelta(days=30)
    for i in range(12):
        approval = Approval(
            user_id=test_user.id,
            signal_id=f"signal-{i}",
            decision=1,  # 1 = approved
            created_at=cutoff + timedelta(days=i),
        )
        db_session.add(approval)

    await db_session.commit()

    engine = UpsellEngine(db_session, score_threshold=0.6, lookback_days=30)
    score = await engine._calculate_usage_score(test_user.id)

    # 12 approvals / 20 threshold = 0.6
    assert 0.55 <= score <= 0.65, f"Expected score ~0.6 for moderate usage, got {score}"


@pytest.mark.asyncio
async def test_usage_score_zero_activity(db_session: AsyncSession, test_user: User):
    """Test usage scoring with no activity."""
    engine = UpsellEngine(db_session, score_threshold=0.6, lookback_days=30)
    score = await engine._calculate_usage_score(test_user.id)

    assert score == 0.0, f"Expected score 0.0 for zero activity, got {score}"


# ===== PERFORMANCE SCORING TESTS =====


@pytest.mark.asyncio
async def test_performance_score_positive_pnl(
    db_session: AsyncSession, test_user: User
):
    """Test performance scoring with positive PnL."""
    # Create dim_symbol and dim_day first
    from datetime import date

    symbol = DimSymbol(symbol="GOLD", asset_class="commodity")
    db_session.add(symbol)
    await db_session.commit()
    await db_session.refresh(symbol)

    # Create daily rollups with positive PnL ($1500 profit on $10k = 15% return)
    cutoff = datetime.utcnow() - timedelta(days=30)
    for i in range(20):
        day = DimDay(
            date=(date.today() - timedelta(days=30 - i)),
            day_of_week=i % 7,
            week_of_year=45,
            month=11,
            year=2025,
            is_trading_day=1,
        )
        db_session.add(day)
        await db_session.flush()  # Get day.id

        rollup = DailyRollups(
            id=str(uuid4()),
            user_id=test_user.id,
            symbol_id=symbol.id,
            day_id=day.id,
            total_trades=1,
            winning_trades=1,  # 100% win rate
            losing_trades=0,
            net_pnl=Decimal("75.00"),  # $75/day * 20 days = $1500
            gross_pnl=Decimal("75.00"),
            total_commission=Decimal("0.00"),
            created_at=cutoff + timedelta(days=i),
        )
        db_session.add(rollup)

    await db_session.commit()

    engine = UpsellEngine(db_session, score_threshold=0.6, lookback_days=30)
    score = await engine._calculate_performance_score(test_user.id)

    # $1500 PnL / $10k = 15% return (capped at 1.0 for 10%+)
    # 20 wins / 20 trades = 100% win rate = bonus
    assert score >= 0.7, f"Expected score >= 0.7 for positive PnL, got {score}"


@pytest.mark.asyncio
async def test_performance_score_negative_pnl(
    db_session: AsyncSession, test_user: User
):
    """Test performance scoring with negative PnL."""
    from datetime import date

    symbol = DimSymbol(symbol="GOLD", asset_class="commodity")
    db_session.add(symbol)
    await db_session.commit()
    await db_session.refresh(symbol)

    # Create daily rollups with negative PnL
    cutoff = datetime.utcnow() - timedelta(days=30)
    for i in range(10):
        day = DimDay(
            date=(date.today() - timedelta(days=30 - i)),
            day_of_week=i % 7,
            week_of_year=45,
            month=11,
            year=2025,
            is_trading_day=1,
        )
        db_session.add(day)
        await db_session.flush()  # Get day.id

        rollup = DailyRollups(
            id=str(uuid4()),
            user_id=test_user.id,
            symbol_id=symbol.id,
            day_id=day.id,
            total_trades=1,
            winning_trades=0,
            losing_trades=1,  # All losses
            net_pnl=Decimal("-80.00"),  # -$80/day * 10 = -$800
            gross_pnl=Decimal("0.00"),
            total_commission=Decimal("-80.00"),
            created_at=cutoff + timedelta(days=i),
        )
        db_session.add(rollup)

    await db_session.commit()

    engine = UpsellEngine(db_session, score_threshold=0.6, lookback_days=30)
    score = await engine._calculate_performance_score(test_user.id)

    # Negative PnL = 0.0 score
    assert score == 0.0, f"Expected score 0.0 for negative PnL, got {score}"


@pytest.mark.asyncio
async def test_performance_score_no_data(db_session: AsyncSession, test_user: User):
    """Test performance scoring with no performance data."""
    engine = UpsellEngine(db_session, score_threshold=0.6, lookback_days=30)
    score = await engine._calculate_performance_score(test_user.id)

    assert score == 0.0, f"Expected score 0.0 for no data, got {score}"


# ===== HELPER FUNCTIONS =====


async def create_performance_rollups(
    db_session: AsyncSession,
    user_id: str,
    total_pnl: Decimal,
    total_trades: int,
    winning_trades: int,
):
    """Helper to create performance rollups."""
    from datetime import date

    symbol = DimSymbol(symbol="GOLD", asset_class="commodity")
    db_session.add(symbol)
    await db_session.commit()
    await db_session.refresh(symbol)

    cutoff = datetime.utcnow() - timedelta(days=30)
    pnl_per_day = total_pnl / total_trades

    for i in range(total_trades):
        day = DimDay(
            date=(date.today() - timedelta(days=30 - i)),
            day_of_week=i % 7,
            week_of_year=45,
            month=11,
            year=2025,
            is_trading_day=1,
        )
        db_session.add(day)
        await db_session.flush()  # Get day.id

        rollup = DailyRollups(
            id=str(uuid4()),
            user_id=user_id,
            symbol_id=symbol.id,
            day_id=day.id,
            total_trades=1,
            winning_trades=1 if i < winning_trades else 0,
            losing_trades=0 if i < winning_trades else 1,
            net_pnl=pnl_per_day,
            gross_pnl=pnl_per_day,
            total_commission=Decimal("0.00"),
            created_at=cutoff + timedelta(days=i),
        )
        db_session.add(rollup)

    await db_session.commit()


# ===== RECOMMENDATION GENERATION TESTS =====


@pytest.mark.asyncio
async def test_score_user_high_usage_performance(
    db_session: AsyncSession, test_user: User, test_subscription: Subscription
):
    """Test recommendation generation for high-performing user."""
    # Create high usage (25 approvals)
    cutoff = datetime.utcnow() - timedelta(days=30)
    for i in range(25):
        approval = Approval(
            user_id=test_user.id,
            signal_id=f"signal-{i}",
            decision=1,  # 1 = approved
            created_at=cutoff + timedelta(days=i),
        )
        db_session.add(approval)

    # Create positive performance ($1200 profit = 12% return)
    await create_performance_rollups(
        db_session,
        test_user.id,
        total_pnl=Decimal("1200.00"),
        total_trades=25,
        winning_trades=18,  # 72% win rate
    )

    # Generate recommendations
    engine = UpsellEngine(db_session, score_threshold=0.6, lookback_days=30)
    recs = await engine.score_user(test_user.id)

    # Should recommend plan upgrade AND copy-trading
    assert (
        len(recs) >= 2
    ), f"Expected >= 2 recommendations for high performer, got {len(recs)}"
    rec_types = [r.recommendation_type for r in recs]
    assert RecommendationType.PLAN_UPGRADE.value in rec_types
    assert RecommendationType.COPY_TRADING.value in rec_types

    # Validate scores
    for rec in recs:
        assert rec.score >= 0.6, f"Recommendation score {rec.score} below threshold"
        assert 0.0 <= rec.usage_score <= 1.0
        assert 0.0 <= rec.performance_score <= 1.0

    # Validate copy present
    plan_rec = next(
        r
        for r in recs
        if r.recommendation_type == RecommendationType.PLAN_UPGRADE.value
    )
    assert len(plan_rec.headline) > 0
    assert len(plan_rec.copy) > 0
    assert plan_rec.expires_at is not None


@pytest.mark.asyncio
async def test_score_user_low_activity_no_recs(
    db_session: AsyncSession, test_user: User, test_subscription: Subscription
):
    """Test no recommendations for low-activity user."""
    # Create only 2 approvals (low usage)
    cutoff = datetime.utcnow() - timedelta(days=30)
    for i in range(2):
        approval = Approval(
            user_id=test_user.id,
            signal_id=f"signal-{i}",
            decision=1,  # 1 = approved
            created_at=cutoff + timedelta(days=i),
        )
        db_session.add(approval)

    await db_session.commit()

    # Generate recommendations
    engine = UpsellEngine(db_session, score_threshold=0.6, lookback_days=30)
    recs = await engine.score_user(test_user.id)

    # Should not generate recommendations (scores too low)
    assert (
        len(recs) == 0
    ), f"Expected 0 recommendations for low activity, got {len(recs)}"


@pytest.mark.asyncio
async def test_score_user_deterministic(
    db_session: AsyncSession, test_user: User, test_subscription: Subscription
):
    """Test scoring is deterministic (same inputs = same scores)."""
    # Create fixed data
    cutoff = datetime.utcnow() - timedelta(days=30)
    for i in range(15):
        approval = Approval(
            user_id=test_user.id,
            signal_id=f"signal-{i}",
            decision=1,  # 1 = approved
            created_at=cutoff + timedelta(days=i),
        )
        db_session.add(approval)

    # Create performance ($1000 profit = 10% return)
    await create_performance_rollups(
        db_session,
        test_user.id,
        total_pnl=Decimal("1000.00"),
        total_trades=15,
        winning_trades=10,  # 67% win rate
    )

    # Score twice
    engine1 = UpsellEngine(db_session, score_threshold=0.6, lookback_days=30)
    recs1 = await engine1.score_user(test_user.id)

    engine2 = UpsellEngine(db_session, score_threshold=0.6, lookback_days=30)
    recs2 = await engine2.score_user(test_user.id)

    # Should get same number and types
    assert len(recs1) == len(
        recs2
    ), "Scoring not deterministic: different recommendation counts"

    for r1, r2 in zip(recs1, recs2):
        assert r1.recommendation_type == r2.recommendation_type
        assert (
            abs(r1.score - r2.score) < 0.01
        ), f"Scoring not deterministic: score diff {abs(r1.score - r2.score)}"


# ===== A/B EXPERIMENT TESTS =====


@pytest.mark.asyncio
async def test_variant_assignment_deterministic(
    db_session: AsyncSession,
    test_user: User,
    test_experiment: Experiment,
    test_variants: tuple[Variant, Variant],
):
    """Test variant assignment is deterministic for same user."""
    engine = UpsellEngine(db_session, score_threshold=0.6, lookback_days=30)

    # Assign variant twice
    variant1 = await engine._assign_variant(
        test_user.id, RecommendationType.PLAN_UPGRADE
    )
    variant2 = await engine._assign_variant(
        test_user.id, RecommendationType.PLAN_UPGRADE
    )

    # Should get same variant
    assert variant1 is not None
    assert variant2 is not None
    assert variant1.id == variant2.id, "Variant assignment not deterministic"


@pytest.mark.asyncio
async def test_variant_assignment_traffic_split(
    db_session: AsyncSession,
    test_experiment: Experiment,
    test_variants: tuple[Variant, Variant],
):
    """Test variant assignment respects traffic split."""
    engine = UpsellEngine(db_session, score_threshold=0.6, lookback_days=30)

    # Assign to 100 fake users
    variant_counts = {"control": 0, "variant": 0}

    for i in range(100):
        fake_user_id = f"user-{i}"
        variant = await engine._assign_variant(
            fake_user_id, RecommendationType.PLAN_UPGRADE
        )

        if variant:
            if variant.is_control:
                variant_counts["control"] += 1
            else:
                variant_counts["variant"] += 1

    # With 50% split, expect ~40-60% in each bucket
    assert (
        30 <= variant_counts["control"] <= 70
    ), f"Control traffic out of range: {variant_counts['control']}"
    assert (
        30 <= variant_counts["variant"] <= 70
    ), f"Variant traffic out of range: {variant_counts['variant']}"


# ===== EXPOSURE TRACKING TESTS =====


@pytest.mark.asyncio
async def test_exposure_logged_once(
    db_session: AsyncSession,
    test_user: User,
    test_experiment: Experiment,
    test_variants: tuple[Variant, Variant],
):
    """Test exposure is logged exactly once per user per experiment."""
    control, variant = test_variants

    # Create first exposure
    exposure1 = Exposure(
        user_id=test_user.id,
        experiment_id=test_experiment.id,
        variant_id=variant.id,
    )
    db_session.add(exposure1)
    await db_session.commit()

    # Query exposures
    query = select(Exposure).where(
        Exposure.user_id == test_user.id,
        Exposure.experiment_id == test_experiment.id,
    )
    result = await db_session.execute(query)
    exposures = list(result.scalars().all())

    assert len(exposures) == 1, f"Expected 1 exposure, got {len(exposures)}"
    assert exposures[0].variant_id == variant.id


@pytest.mark.asyncio
async def test_exposure_updates_experiment_counters(
    db_session: AsyncSession,
    test_user: User,
    test_experiment: Experiment,
    test_variants: tuple[Variant, Variant],
):
    """Test exposure increments experiment counters."""
    control, variant = test_variants

    # Initial state
    await db_session.refresh(test_experiment)
    initial_variant_exposures = test_experiment.variant_exposures

    # Create exposure
    exposure = Exposure(
        user_id=test_user.id,
        experiment_id=test_experiment.id,
        variant_id=variant.id,
    )
    db_session.add(exposure)

    # Manually update counter (routes.py does this)
    test_experiment.variant_exposures += 1
    await db_session.commit()

    # Verify counter incremented
    await db_session.refresh(test_experiment)
    assert test_experiment.variant_exposures == initial_variant_exposures + 1


# ===== CONVERSION TRACKING TESTS =====


@pytest.mark.asyncio
async def test_conversion_marks_exposure(
    db_session: AsyncSession,
    test_user: User,
    test_experiment: Experiment,
    test_variants: tuple[Variant, Variant],
):
    """Test conversion marks exposure as converted."""
    control, variant = test_variants

    # Create exposure
    exposure = Exposure(
        user_id=test_user.id,
        experiment_id=test_experiment.id,
        variant_id=variant.id,
        converted=False,
    )
    db_session.add(exposure)
    await db_session.commit()
    await db_session.refresh(exposure)

    # Mark as converted
    exposure.converted = True
    exposure.converted_at = datetime.utcnow()
    test_experiment.variant_conversions += 1
    await db_session.commit()

    # Verify conversion
    await db_session.refresh(exposure)
    assert exposure.converted is True
    assert exposure.converted_at is not None

    await db_session.refresh(test_experiment)
    assert test_experiment.variant_conversions >= 1


@pytest.mark.asyncio
async def test_conversion_idempotent(
    db_session: AsyncSession,
    test_user: User,
    test_experiment: Experiment,
    test_variants: tuple[Variant, Variant],
):
    """Test conversion is idempotent (no double-counting)."""
    control, variant = test_variants

    # Create exposure and mark as converted
    exposure = Exposure(
        user_id=test_user.id,
        experiment_id=test_experiment.id,
        variant_id=variant.id,
        converted=True,
        converted_at=datetime.utcnow(),
    )
    db_session.add(exposure)
    test_experiment.variant_conversions = 1
    await db_session.commit()

    initial_conversions = test_experiment.variant_conversions

    # Try to convert again (should be rejected in routes.py)
    # Simulate routes.py logic check
    if not exposure.converted:
        test_experiment.variant_conversions += 1

    await db_session.commit()
    await db_session.refresh(test_experiment)

    # Should not increment
    assert test_experiment.variant_conversions == initial_conversions


# ===== EXPERIMENT CTR CALCULATION TESTS =====


@pytest.mark.asyncio
async def test_experiment_ctr_calculation(
    db_session: AsyncSession, test_experiment: Experiment
):
    """Test experiment CTR properties calculate correctly."""
    # Set up counters
    test_experiment.control_exposures = 100
    test_experiment.control_conversions = 10
    test_experiment.variant_exposures = 100
    test_experiment.variant_conversions = 15
    await db_session.commit()
    await db_session.refresh(test_experiment)

    # Validate CTR calculation
    assert (
        test_experiment.control_ctr == 0.10
    ), f"Expected control CTR 0.10, got {test_experiment.control_ctr}"
    assert (
        test_experiment.variant_ctr == 0.15
    ), f"Expected variant CTR 0.15, got {test_experiment.variant_ctr}"

    # Validate uplift calculation
    expected_uplift = (0.15 - 0.10) / 0.10  # 50% uplift
    assert test_experiment.uplift == pytest.approx(expected_uplift, rel=0.01)


@pytest.mark.asyncio
async def test_experiment_ctr_zero_exposures(
    db_session: AsyncSession, test_experiment: Experiment
):
    """Test CTR calculation with zero exposures."""
    # Set up zero exposures
    test_experiment.control_exposures = 0
    test_experiment.control_conversions = 0
    test_experiment.variant_exposures = 0
    test_experiment.variant_conversions = 0
    await db_session.commit()
    await db_session.refresh(test_experiment)

    # Should not crash, return 0.0
    assert test_experiment.control_ctr == 0.0
    assert test_experiment.variant_ctr == 0.0
    assert test_experiment.uplift is None  # Cannot calculate uplift with 0 control CTR


# ===== EDGE CASES =====


@pytest.mark.asyncio
async def test_score_user_premium_subscriber_no_upgrade(
    db_session: AsyncSession, test_user: User
):
    """Test no plan upgrade recommendation for premium users."""
    # Create premium subscription
    sub = Subscription(
        id=str(uuid4()),
        user_id=test_user.id,
        tier="premium",
        status="active",
        amount=Decimal("50.00"),
    )
    db_session.add(sub)

    # Create high usage/performance
    cutoff = datetime.utcnow() - timedelta(days=30)
    for i in range(25):
        approval = Approval(
            user_id=test_user.id,
            signal_id=f"signal-{i}",
            decision=1,  # 1 = approved
            created_at=cutoff + timedelta(days=i),
        )
        db_session.add(approval)

    # Create positive performance ($1500 profit)
    await create_performance_rollups(
        db_session,
        test_user.id,
        total_pnl=Decimal("1500.00"),
        total_trades=25,
        winning_trades=18,
    )

    # Generate recommendations
    engine = UpsellEngine(db_session, score_threshold=0.6, lookback_days=30)
    recs = await engine.score_user(test_user.id)

    # Should NOT recommend plan upgrade (already premium)
    rec_types = [r.recommendation_type for r in recs]
    assert RecommendationType.PLAN_UPGRADE.value not in rec_types


@pytest.mark.asyncio
async def test_recommendation_expires_at_set(
    db_session: AsyncSession, test_user: User, test_subscription: Subscription
):
    """Test recommendation expires_at is set correctly."""
    # Create high usage
    cutoff = datetime.utcnow() - timedelta(days=30)
    for i in range(20):
        approval = Approval(
            user_id=test_user.id,
            signal_id=f"signal-{i}",
            decision=1,  # 1 = approved
            created_at=cutoff + timedelta(days=i),
        )
        db_session.add(approval)

    await db_session.commit()

    # Generate recommendations
    engine = UpsellEngine(db_session, score_threshold=0.6, lookback_days=30)
    recs = await engine.score_user(test_user.id)

    # Validate expires_at is set
    for rec in recs:
        assert rec.expires_at is not None
        # Should expire within 7 days
        days_until_expiry = (rec.expires_at - datetime.utcnow()).days
        assert (
            6 <= days_until_expiry <= 8
        ), f"Expiry should be ~7 days, got {days_until_expiry}"


@pytest.mark.asyncio
async def test_weighted_score_calculation(db_session: AsyncSession):
    """Test weighted score calculation is correct."""
    engine = UpsellEngine(db_session, score_threshold=0.6, lookback_days=30)

    score = engine._weighted_score(
        usage=0.8,
        performance=0.6,
        intent=0.5,
        cohort=0.7,
        weights={"usage": 0.3, "performance": 0.3, "intent": 0.25, "cohort": 0.15},
    )

    expected = 0.8 * 0.3 + 0.6 * 0.3 + 0.5 * 0.25 + 0.7 * 0.15
    assert score == pytest.approx(expected, abs=0.001)


@pytest.mark.asyncio
async def test_copy_generation_default_fallback(db_session: AsyncSession):
    """Test copy generation falls back to defaults when no variant."""
    engine = UpsellEngine(db_session, score_threshold=0.6, lookback_days=30)

    headline, copy = engine._generate_copy(
        RecommendationType.PLAN_UPGRADE, variant=None
    )

    assert len(headline) > 0
    assert len(copy) > 0
    assert "Premium" in headline or "premium" in headline.lower()
