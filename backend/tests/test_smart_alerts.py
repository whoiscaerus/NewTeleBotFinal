"""
PR-065: Smart Alert Rules - Comprehensive Tests

Tests for smart rule creation, evaluation, cooldown, mute/unmute, and multi-channel delivery.
Coverage target: 100% business logic validation.
"""

from datetime import datetime, timedelta, UTC
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select

from backend.app.alerts.rules import (
    NotificationChannel,
    RuleType,
    SmartAlertRule,
    SmartRuleEvaluator,
    SmartRuleService,
)
from backend.app.core.errors import ValidationError

# ============================================================================
# FIXTURES
# ============================================================================


@pytest_asyncio.fixture
async def smart_rule_service():
    """Create smart rule service instance."""
    return SmartRuleService()


@pytest_asyncio.fixture
async def test_user(db_session):
    """Create test user."""
    from backend.app.auth.models import User

    user = User(
        id=str(uuid4()),
        email=f"test_user_{uuid4()}@example.com",
        password_hash="hashed_password_test",
        telegram_user_id="123456789",
        created_at=datetime.utcnow(),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def smart_rule(db_session, test_user):
    """Create test smart rule."""
    rule = SmartAlertRule(
        id=str(uuid4()),
        user_id=test_user.id,
        symbol="GOLD",
        rule_type=RuleType.CROSS_ABOVE.value,
        threshold_value=2000.0,
        cooldown_minutes=60,
        is_muted=False,
        channels=["telegram"],
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(rule)
    await db_session.commit()
    await db_session.refresh(rule)
    return rule


# ============================================================================
# TESTS: CREATE SMART RULE
# ============================================================================


@pytest.mark.asyncio
async def test_create_cross_above_rule(db_session, smart_rule_service, test_user):
    """Test creating cross-above rule."""
    result = await smart_rule_service.create_rule(
        db=db_session,
        user_id=test_user.id,
        symbol="GOLD",
        rule_type=RuleType.CROSS_ABOVE,
        threshold_value=2000.0,
        cooldown_minutes=60,
        channels=[NotificationChannel.TELEGRAM],
    )

    assert result["rule_id"] is not None
    assert result["symbol"] == "GOLD"
    assert result["rule_type"] == RuleType.CROSS_ABOVE.value
    assert result["threshold_value"] == 2000.0
    assert result["cooldown_minutes"] == 60
    assert result["is_muted"] is False
    assert result["channels"] == ["telegram"]


@pytest.mark.asyncio
async def test_create_percent_change_rule(db_session, smart_rule_service, test_user):
    """Test creating percent-change rule with window."""
    result = await smart_rule_service.create_rule(
        db=db_session,
        user_id=test_user.id,
        symbol="GOLD",
        rule_type=RuleType.PERCENT_CHANGE,
        threshold_value=2.0,  # 2% change
        window_minutes=60,  # Over 1 hour
        cooldown_minutes=120,
        channels=[NotificationChannel.TELEGRAM, NotificationChannel.EMAIL],
    )

    assert result["rule_id"] is not None
    assert result["rule_type"] == RuleType.PERCENT_CHANGE.value
    assert result["threshold_value"] == 2.0
    assert result["window_minutes"] == 60
    assert result["channels"] == ["telegram", "email"]


@pytest.mark.asyncio
async def test_create_percent_change_without_window_fails(
    db_session, smart_rule_service, test_user
):
    """Test creating percent_change rule without window_minutes raises error."""
    with pytest.raises(ValidationError, match="window_minutes required"):
        await smart_rule_service.create_rule(
            db=db_session,
            user_id=test_user.id,
            symbol="GOLD",
            rule_type=RuleType.PERCENT_CHANGE,
            threshold_value=2.0,
            window_minutes=None,  # Missing required parameter
        )


@pytest.mark.asyncio
async def test_create_rsi_threshold_rule(db_session, smart_rule_service, test_user):
    """Test creating RSI threshold rule with default period."""
    result = await smart_rule_service.create_rule(
        db=db_session,
        user_id=test_user.id,
        symbol="GOLD",
        rule_type=RuleType.RSI_THRESHOLD,
        threshold_value=70.0,  # Overbought
        rsi_period=None,  # Should default to 14
        cooldown_minutes=30,
    )

    assert result["rule_id"] is not None
    assert result["rule_type"] == RuleType.RSI_THRESHOLD.value
    assert result["threshold_value"] == 70.0
    assert result["rsi_period"] == 14  # Default


@pytest.mark.asyncio
async def test_create_daily_high_touch_rule(db_session, smart_rule_service, test_user):
    """Test creating daily high touch rule."""
    result = await smart_rule_service.create_rule(
        db=db_session,
        user_id=test_user.id,
        symbol="GOLD",
        rule_type=RuleType.DAILY_HIGH_TOUCH,
        threshold_value=99.5,  # Within 0.5% of daily high
        cooldown_minutes=240,  # 4 hours
    )

    assert result["rule_id"] is not None
    assert result["rule_type"] == RuleType.DAILY_HIGH_TOUCH.value
    assert result["threshold_value"] == 99.5


# ============================================================================
# TESTS: EVALUATE CROSS-ABOVE
# ============================================================================


@pytest.mark.asyncio
async def test_cross_above_first_evaluation():
    """Test cross-above first evaluation stores price without triggering."""
    evaluator = SmartRuleEvaluator()
    rule = SmartAlertRule(
        rule_type=RuleType.CROSS_ABOVE.value,
        threshold_value=2000.0,
        previous_price=None,  # First evaluation
    )

    triggered, reason = await evaluator.evaluate_cross_above(rule, 1950.0)

    assert triggered is False
    assert "no previous price" in reason.lower()


@pytest.mark.asyncio
async def test_cross_above_triggers_when_crossing_up():
    """Test cross-above triggers when price crosses threshold upward."""
    evaluator = SmartRuleEvaluator()
    rule = SmartAlertRule(
        rule_type=RuleType.CROSS_ABOVE.value,
        threshold_value=2000.0,
        previous_price=1995.0,  # Was below threshold
    )

    triggered, reason = await evaluator.evaluate_cross_above(rule, 2005.0)  # Now above

    assert triggered is True
    assert "crossed above 2000.0" in reason.lower()
    assert "1995.00" in reason
    assert "2005.00" in reason


@pytest.mark.asyncio
async def test_cross_above_does_not_trigger_when_staying_above():
    """Test cross-above does not trigger when price stays above threshold."""
    evaluator = SmartRuleEvaluator()
    rule = SmartAlertRule(
        rule_type=RuleType.CROSS_ABOVE.value,
        threshold_value=2000.0,
        previous_price=2010.0,  # Was above
    )

    triggered, reason = await evaluator.evaluate_cross_above(
        rule, 2020.0
    )  # Still above

    assert triggered is False


@pytest.mark.asyncio
async def test_cross_above_does_not_trigger_when_staying_below():
    """Test cross-above does not trigger when price stays below threshold."""
    evaluator = SmartRuleEvaluator()
    rule = SmartAlertRule(
        rule_type=RuleType.CROSS_ABOVE.value,
        threshold_value=2000.0,
        previous_price=1990.0,  # Was below
    )

    triggered, reason = await evaluator.evaluate_cross_above(
        rule, 1995.0
    )  # Still below

    assert triggered is False


# ============================================================================
# TESTS: EVALUATE CROSS-BELOW
# ============================================================================


@pytest.mark.asyncio
async def test_cross_below_triggers_when_crossing_down():
    """Test cross-below triggers when price crosses threshold downward."""
    evaluator = SmartRuleEvaluator()
    rule = SmartAlertRule(
        rule_type=RuleType.CROSS_BELOW.value,
        threshold_value=2000.0,
        previous_price=2005.0,  # Was above threshold
    )

    triggered, reason = await evaluator.evaluate_cross_below(rule, 1995.0)  # Now below

    assert triggered is True
    assert "crossed below 2000.0" in reason.lower()
    assert "2005.00" in reason
    assert "1995.00" in reason


@pytest.mark.asyncio
async def test_cross_below_does_not_trigger_when_staying_below():
    """Test cross-below does not trigger when price stays below threshold."""
    evaluator = SmartRuleEvaluator()
    rule = SmartAlertRule(
        rule_type=RuleType.CROSS_BELOW.value,
        threshold_value=2000.0,
        previous_price=1990.0,  # Was below
    )

    triggered, reason = await evaluator.evaluate_cross_below(
        rule, 1985.0
    )  # Still below

    assert triggered is False


# ============================================================================
# TESTS: EVALUATE PERCENT CHANGE
# ============================================================================


@pytest.mark.asyncio
async def test_percent_change_triggers_on_increase():
    """Test percent_change triggers when increase exceeds threshold."""
    evaluator = SmartRuleEvaluator()
    rule = SmartAlertRule(
        rule_type=RuleType.PERCENT_CHANGE.value,
        threshold_value=2.0,  # 2% threshold
        window_minutes=60,
    )

    # Price increased from 2000 to 2050 = 2.5% increase
    historical_prices = [
        (datetime.now(UTC) - timedelta(minutes=65), 2000.0),
        (datetime.now(UTC) - timedelta(minutes=60), 2000.0),
        (datetime.now(UTC) - timedelta(minutes=30), 2020.0),
    ]

    triggered, reason = await evaluator.evaluate_percent_change(
        rule, 2050.0, historical_prices
    )

    assert triggered is True
    assert "2.50%" in reason  # 2.5% increase
    assert "increase" in reason.lower()


@pytest.mark.asyncio
async def test_percent_change_triggers_on_decrease():
    """Test percent_change triggers when decrease exceeds threshold."""
    evaluator = SmartRuleEvaluator()
    rule = SmartAlertRule(
        rule_type=RuleType.PERCENT_CHANGE.value,
        threshold_value=2.0,  # 2% threshold
        window_minutes=60,
    )

    # Price decreased from 2000 to 1950 = 2.5% decrease
    historical_prices = [
        (datetime.now(UTC) - timedelta(minutes=60), 2000.0),
        (datetime.now(UTC) - timedelta(minutes=30), 1980.0),
    ]

    triggered, reason = await evaluator.evaluate_percent_change(
        rule, 1950.0, historical_prices
    )

    assert triggered is True
    assert "2.50%" in reason
    assert "decrease" in reason.lower()


@pytest.mark.asyncio
async def test_percent_change_does_not_trigger_below_threshold():
    """Test percent_change does not trigger when change below threshold."""
    evaluator = SmartRuleEvaluator()
    rule = SmartAlertRule(
        rule_type=RuleType.PERCENT_CHANGE.value,
        threshold_value=2.0,  # 2% threshold
        window_minutes=60,
    )

    # Price changed from 2000 to 2010 = 0.5% increase (below 2%)
    historical_prices = [
        (datetime.now(UTC) - timedelta(minutes=60), 2000.0),
    ]

    triggered, reason = await evaluator.evaluate_percent_change(
        rule, 2010.0, historical_prices
    )

    assert triggered is False


@pytest.mark.asyncio
async def test_percent_change_no_historical_data():
    """Test percent_change returns false when no historical data."""
    evaluator = SmartRuleEvaluator()
    rule = SmartAlertRule(
        rule_type=RuleType.PERCENT_CHANGE.value,
        threshold_value=2.0,
        window_minutes=60,
    )

    triggered, reason = await evaluator.evaluate_percent_change(rule, 2000.0, [])

    assert triggered is False
    assert "insufficient" in reason.lower()


# ============================================================================
# TESTS: EVALUATE RSI THRESHOLD
# ============================================================================


@pytest.mark.asyncio
async def test_rsi_overbought_triggers():
    """Test RSI threshold triggers on overbought condition."""
    evaluator = SmartRuleEvaluator()
    rule = SmartAlertRule(
        rule_type=RuleType.RSI_THRESHOLD.value,
        threshold_value=70.0,  # Overbought threshold
        rsi_period=14,
    )

    triggered, reason = await evaluator.evaluate_rsi_threshold(rule, 75.0)  # Overbought

    assert triggered is True
    assert "overbought" in reason.lower()
    assert "75.0" in reason
    assert "70.0" in reason


@pytest.mark.asyncio
async def test_rsi_oversold_triggers():
    """Test RSI threshold triggers on oversold condition."""
    evaluator = SmartRuleEvaluator()
    rule = SmartAlertRule(
        rule_type=RuleType.RSI_THRESHOLD.value,
        threshold_value=30.0,  # Oversold threshold
        rsi_period=14,
    )

    triggered, reason = await evaluator.evaluate_rsi_threshold(rule, 25.0)  # Oversold

    assert triggered is True
    assert "oversold" in reason.lower()
    assert "25.0" in reason
    assert "30.0" in reason


@pytest.mark.asyncio
async def test_rsi_neutral_does_not_trigger():
    """Test RSI threshold does not trigger in neutral zone."""
    evaluator = SmartRuleEvaluator()
    rule = SmartAlertRule(
        rule_type=RuleType.RSI_THRESHOLD.value,
        threshold_value=70.0,
        rsi_period=14,
    )

    triggered, reason = await evaluator.evaluate_rsi_threshold(rule, 50.0)  # Neutral

    assert triggered is False


@pytest.mark.asyncio
async def test_rsi_no_data():
    """Test RSI threshold returns false when RSI data unavailable."""
    evaluator = SmartRuleEvaluator()
    rule = SmartAlertRule(
        rule_type=RuleType.RSI_THRESHOLD.value,
        threshold_value=70.0,
    )

    triggered, reason = await evaluator.evaluate_rsi_threshold(rule, None)

    assert triggered is False
    assert "not available" in reason.lower()


# ============================================================================
# TESTS: EVALUATE DAILY HIGH/LOW TOUCH
# ============================================================================


@pytest.mark.asyncio
async def test_daily_high_touch_triggers():
    """Test daily high touch triggers when price reaches high."""
    evaluator = SmartRuleEvaluator()
    rule = SmartAlertRule(
        rule_type=RuleType.DAILY_HIGH_TOUCH.value,
        threshold_value=99.5,  # Within 0.5% of high
    )

    daily_high = 2050.0
    current_price = 2048.0  # 2048/2050 = 99.9% of high

    triggered, reason = await evaluator.evaluate_daily_high_touch(
        rule, current_price, daily_high
    )

    assert triggered is True
    assert "touched daily high" in reason.lower()
    assert "2048.00" in reason
    assert "2050.00" in reason


@pytest.mark.asyncio
async def test_daily_high_touch_does_not_trigger_far_from_high():
    """Test daily high touch does not trigger when far from high."""
    evaluator = SmartRuleEvaluator()
    rule = SmartAlertRule(
        rule_type=RuleType.DAILY_HIGH_TOUCH.value,
        threshold_value=99.5,
    )

    daily_high = 2050.0
    current_price = 2000.0  # 2000/2050 = 97.6% (below 99.5%)

    triggered, reason = await evaluator.evaluate_daily_high_touch(
        rule, current_price, daily_high
    )

    assert triggered is False


@pytest.mark.asyncio
async def test_daily_low_touch_triggers():
    """Test daily low touch triggers when price reaches low."""
    evaluator = SmartRuleEvaluator()
    rule = SmartAlertRule(
        rule_type=RuleType.DAILY_LOW_TOUCH.value,
        threshold_value=100.5,  # Within 0.5% of low
    )

    daily_low = 1950.0
    current_price = 1952.0  # 1952/1950 = 100.1% of low

    triggered, reason = await evaluator.evaluate_daily_low_touch(
        rule, current_price, daily_low
    )

    assert triggered is True
    assert "touched daily low" in reason.lower()


# ============================================================================
# TESTS: COOLDOWN LOGIC
# ============================================================================


@pytest.mark.asyncio
async def test_cooldown_allows_first_trigger(smart_rule_service):
    """Test cooldown allows trigger when never triggered before."""
    rule = SmartAlertRule(
        last_triggered_at=None,
        cooldown_minutes=60,
    )

    can_trigger, available_at = await smart_rule_service.check_cooldown(rule)

    assert can_trigger is True
    assert available_at is None


@pytest.mark.asyncio
async def test_cooldown_blocks_quick_retrigger(smart_rule_service):
    """Test cooldown blocks trigger within cooldown period."""
    rule = SmartAlertRule(
        last_triggered_at=datetime.utcnow() - timedelta(minutes=30),  # 30 min ago
        cooldown_minutes=60,  # 60 min cooldown
    )

    can_trigger, available_at = await smart_rule_service.check_cooldown(rule)

    assert can_trigger is False
    assert available_at is not None
    assert available_at > datetime.utcnow()


@pytest.mark.asyncio
async def test_cooldown_allows_after_period_expires(smart_rule_service):
    """Test cooldown allows trigger after cooldown period expires."""
    rule = SmartAlertRule(
        last_triggered_at=datetime.utcnow() - timedelta(minutes=90),  # 90 min ago
        cooldown_minutes=60,  # 60 min cooldown
    )

    can_trigger, available_at = await smart_rule_service.check_cooldown(rule)

    assert can_trigger is True
    assert available_at is None


# ============================================================================
# TESTS: MUTE/UNMUTE
# ============================================================================


@pytest.mark.asyncio
async def test_mute_rule(db_session, smart_rule_service, smart_rule, test_user):
    """Test muting a smart rule."""
    result = await smart_rule_service.mute_rule(
        db=db_session, rule_id=smart_rule.id, user_id=test_user.id
    )

    assert result["rule_id"] == smart_rule.id
    assert result["is_muted"] is True

    # Verify in database
    db_result = await db_session.execute(
        select(SmartAlertRule).where(SmartAlertRule.id == smart_rule.id)
    )
    updated_rule = db_result.scalar_one()
    assert updated_rule.is_muted is True


@pytest.mark.asyncio
async def test_unmute_rule(db_session, smart_rule_service, test_user):
    """Test unmuting a smart rule."""
    # Create muted rule
    muted_rule = SmartAlertRule(
        id=str(uuid4()),
        user_id=test_user.id,
        symbol="GOLD",
        rule_type=RuleType.CROSS_ABOVE.value,
        threshold_value=2000.0,
        cooldown_minutes=60,
        is_muted=True,  # Start muted
        channels=["telegram"],
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(muted_rule)
    await db_session.commit()
    await db_session.refresh(muted_rule)

    result = await smart_rule_service.unmute_rule(
        db=db_session, rule_id=muted_rule.id, user_id=test_user.id
    )

    assert result["rule_id"] == muted_rule.id
    assert result["is_muted"] is False

    # Verify in database
    db_result = await db_session.execute(
        select(SmartAlertRule).where(SmartAlertRule.id == muted_rule.id)
    )
    updated_rule = db_result.scalar_one()
    assert updated_rule.is_muted is False


@pytest.mark.asyncio
async def test_mute_nonexistent_rule_fails(db_session, smart_rule_service, test_user):
    """Test muting non-existent rule raises error."""
    with pytest.raises(ValidationError, match="not found"):
        await smart_rule_service.mute_rule(
            db=db_session, rule_id="nonexistent-id", user_id=test_user.id
        )


@pytest.mark.asyncio
async def test_mute_other_users_rule_fails(
    db_session, smart_rule_service, smart_rule, test_user
):
    """Test muting another user's rule raises error."""
    other_user_id = str(uuid4())

    with pytest.raises(ValidationError, match="not found"):
        await smart_rule_service.mute_rule(
            db=db_session, rule_id=smart_rule.id, user_id=other_user_id
        )


# ============================================================================
# TESTS: EVALUATE RULE (INTEGRATION)
# ============================================================================


@pytest.mark.asyncio
async def test_evaluate_rule_muted_does_not_trigger(
    db_session, smart_rule_service, test_user
):
    """Test muted rule does not trigger even when condition met."""
    rule = SmartAlertRule(
        id=str(uuid4()),
        user_id=test_user.id,
        symbol="GOLD",
        rule_type=RuleType.CROSS_ABOVE.value,
        threshold_value=2000.0,
        cooldown_minutes=60,
        is_muted=True,  # Muted
        channels=["telegram"],
        is_active=True,
        previous_price=1995.0,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(rule)
    await db_session.commit()
    await db_session.refresh(rule)

    market_data = {"current_price": 2005.0}  # Would trigger if not muted

    triggered, reason = await smart_rule_service.evaluate_rule(
        db=db_session, rule=rule, market_data=market_data
    )

    assert triggered is False
    assert "muted" in reason.lower()


@pytest.mark.asyncio
async def test_evaluate_rule_in_cooldown_does_not_trigger(
    db_session, smart_rule_service, test_user
):
    """Test rule in cooldown does not trigger even when condition met."""
    rule = SmartAlertRule(
        id=str(uuid4()),
        user_id=test_user.id,
        symbol="GOLD",
        rule_type=RuleType.CROSS_ABOVE.value,
        threshold_value=2000.0,
        cooldown_minutes=60,
        is_muted=False,
        channels=["telegram"],
        is_active=True,
        previous_price=1995.0,
        last_triggered_at=datetime.utcnow() - timedelta(minutes=30),  # In cooldown
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(rule)
    await db_session.commit()
    await db_session.refresh(rule)

    market_data = {"current_price": 2005.0}

    triggered, reason = await smart_rule_service.evaluate_rule(
        db=db_session, rule=rule, market_data=market_data
    )

    assert triggered is False
    assert "cooldown" in reason.lower()


@pytest.mark.asyncio
async def test_evaluate_rule_updates_state_on_trigger(
    db_session, smart_rule_service, test_user
):
    """Test rule updates state (last_triggered_at, previous_price) on trigger."""
    rule = SmartAlertRule(
        id=str(uuid4()),
        user_id=test_user.id,
        symbol="GOLD",
        rule_type=RuleType.CROSS_ABOVE.value,
        threshold_value=2000.0,
        cooldown_minutes=60,
        is_muted=False,
        channels=["telegram"],
        is_active=True,
        previous_price=1995.0,
        last_triggered_at=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(rule)
    await db_session.commit()
    await db_session.refresh(rule)

    market_data = {"current_price": 2005.0}

    triggered, reason = await smart_rule_service.evaluate_rule(
        db=db_session, rule=rule, market_data=market_data
    )

    assert triggered is True

    # Verify state updated
    db_result = await db_session.execute(
        select(SmartAlertRule).where(SmartAlertRule.id == rule.id)
    )
    updated_rule = db_result.scalar_one()
    assert updated_rule.previous_price == 2005.0
    assert updated_rule.last_triggered_at is not None
    assert updated_rule.last_evaluation_at is not None


# ============================================================================
# TESTS: UPDATE RULE
# ============================================================================


@pytest.mark.asyncio
async def test_update_rule_threshold(
    db_session, smart_rule_service, smart_rule, test_user
):
    """Test updating rule threshold."""
    from backend.app.alerts.rules import SmartRuleUpdate

    update = SmartRuleUpdate(threshold_value=2100.0)

    result = await smart_rule_service.update_rule(
        db=db_session, rule_id=smart_rule.id, user_id=test_user.id, updates=update
    )

    assert result["threshold_value"] == 2100.0

    # Verify in database
    db_result = await db_session.execute(
        select(SmartAlertRule).where(SmartAlertRule.id == smart_rule.id)
    )
    updated_rule = db_result.scalar_one()
    assert updated_rule.threshold_value == 2100.0


@pytest.mark.asyncio
async def test_update_rule_cooldown_and_channels(
    db_session, smart_rule_service, smart_rule, test_user
):
    """Test updating cooldown and channels."""
    from backend.app.alerts.rules import SmartRuleUpdate

    update = SmartRuleUpdate(
        cooldown_minutes=120,
        channels=[NotificationChannel.TELEGRAM, NotificationChannel.PUSH],
    )

    result = await smart_rule_service.update_rule(
        db=db_session, rule_id=smart_rule.id, user_id=test_user.id, updates=update
    )

    assert result["cooldown_minutes"] == 120
    assert set(result["channels"]) == {"telegram", "push"}


# ============================================================================
# TESTS: MULTI-CHANNEL SUPPORT
# ============================================================================


@pytest.mark.asyncio
async def test_create_rule_with_multiple_channels(
    db_session, smart_rule_service, test_user
):
    """Test creating rule with multiple notification channels."""
    result = await smart_rule_service.create_rule(
        db=db_session,
        user_id=test_user.id,
        symbol="GOLD",
        rule_type=RuleType.CROSS_ABOVE,
        threshold_value=2000.0,
        cooldown_minutes=60,
        channels=[
            NotificationChannel.TELEGRAM,
            NotificationChannel.PUSH,
            NotificationChannel.EMAIL,
        ],
    )

    assert set(result["channels"]) == {"telegram", "push", "email"}


@pytest.mark.asyncio
async def test_create_rule_defaults_to_telegram_only(
    db_session, smart_rule_service, test_user
):
    """Test creating rule without channels defaults to Telegram only."""
    result = await smart_rule_service.create_rule(
        db=db_session,
        user_id=test_user.id,
        symbol="GOLD",
        rule_type=RuleType.CROSS_ABOVE,
        threshold_value=2000.0,
        cooldown_minutes=60,
        channels=None,  # No channels specified
    )

    assert result["channels"] == ["telegram"]
