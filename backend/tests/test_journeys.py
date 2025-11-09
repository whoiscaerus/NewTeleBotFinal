"""
PR-066: Journey Automation System - Comprehensive Tests

Tests journey creation, trigger evaluation, step execution, and user progress tracking.
Coverage target: 100% business logic validation.
"""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select

from backend.app.auth.models import User
from backend.app.journeys.engine import JourneyEngine
from backend.app.journeys.models import (
    ActionType,
    Journey,
    JourneyStep,
    StepExecution,
    TriggerType,
    UserJourney,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest_asyncio.fixture
async def journey_engine():
    """Create journey engine instance."""
    return JourneyEngine()


@pytest_asyncio.fixture
async def test_user(db_session):
    """Create test user."""
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
async def admin_user(db_session):
    """Create admin user."""
    admin = User(
        id=str(uuid4()),
        email=f"admin_{uuid4()}@example.com",
        password_hash="hashed_password_test",
        telegram_user_id="987654321",
        created_at=datetime.utcnow(),
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    return admin


@pytest_asyncio.fixture
async def onboarding_journey(db_session, admin_user):
    """Create onboarding journey with steps."""
    journey = Journey(
        id=str(uuid4()),
        name="Onboarding Flow",
        description="Welcome new users",
        trigger_type=TriggerType.SIGNUP.value,
        trigger_config={},
        is_active=True,
        priority=10,
        created_by=admin_user.id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(journey)

    # Step 1: Send welcome email immediately
    step1 = JourneyStep(
        id=str(uuid4()),
        journey_id=journey.id,
        name="Welcome Email",
        order=0,
        action_type=ActionType.SEND_EMAIL.value,
        action_config={"template": "welcome", "subject": "Welcome!"},
        delay_minutes=0,
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(step1)

    # Step 2: Send Telegram message after 5 minutes
    step2 = JourneyStep(
        id=str(uuid4()),
        journey_id=journey.id,
        name="Telegram Intro",
        order=1,
        action_type=ActionType.SEND_TELEGRAM.value,
        action_config={"message": "Welcome to our platform!"},
        delay_minutes=5,
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(step2)

    # Step 3: Apply tag after 1 day
    step3 = JourneyStep(
        id=str(uuid4()),
        journey_id=journey.id,
        name="Apply Onboarded Tag",
        order=2,
        action_type=ActionType.APPLY_TAG.value,
        action_config={"tag": "onboarded"},
        delay_minutes=1440,  # 1 day
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(step3)

    await db_session.commit()
    await db_session.refresh(journey)
    return journey


# ============================================================================
# TESTS: JOURNEY CREATION
# ============================================================================


@pytest.mark.asyncio
async def test_create_journey_basic(db_session, admin_user):
    """Test creating a basic journey."""
    journey = Journey(
        id=str(uuid4()),
        name="Test Journey",
        description="Test description",
        trigger_type=TriggerType.SIGNUP.value,
        trigger_config={},
        is_active=True,
        priority=0,
        created_by=admin_user.id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(journey)
    await db_session.commit()
    await db_session.refresh(journey)

    assert journey.id is not None
    assert journey.name == "Test Journey"
    assert journey.trigger_type == TriggerType.SIGNUP.value
    assert journey.is_active is True


@pytest.mark.asyncio
async def test_create_journey_with_conditional_trigger(db_session, admin_user):
    """Test creating journey with trigger condition."""
    journey = Journey(
        id=str(uuid4()),
        name="Premium Onboarding",
        trigger_type=TriggerType.SIGNUP.value,
        trigger_config={"field": "plan", "op": "eq", "value": "premium"},
        is_active=True,
        created_by=admin_user.id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(journey)
    await db_session.commit()

    assert journey.trigger_config["field"] == "plan"
    assert journey.trigger_config["op"] == "eq"
    assert journey.trigger_config["value"] == "premium"


@pytest.mark.asyncio
async def test_create_journey_steps_with_different_actions(db_session, admin_user):
    """Test creating journey steps with various action types."""
    journey = Journey(
        id=str(uuid4()),
        name="Multi-Action Journey",
        trigger_type=TriggerType.SIGNUP.value,
        is_active=True,
        created_by=admin_user.id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(journey)

    actions = [
        (ActionType.SEND_EMAIL, {"template": "welcome"}),
        (ActionType.SEND_TELEGRAM, {"message": "Hello"}),
        (ActionType.SEND_PUSH, {"title": "Welcome"}),
        (ActionType.APPLY_TAG, {"tag": "new_user"}),
        (ActionType.GRANT_REWARD, {"type": "credit", "value": 10}),
    ]

    for idx, (action_type, config) in enumerate(actions):
        step = JourneyStep(
            id=str(uuid4()),
            journey_id=journey.id,
            name=f"Step {idx}",
            order=idx,
            action_type=action_type.value,
            action_config=config,
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db_session.add(step)

    await db_session.commit()

    # Verify steps created
    result = await db_session.execute(
        select(JourneyStep).where(JourneyStep.journey_id == journey.id)
    )
    steps = result.scalars().all()
    assert len(steps) == 5


# ============================================================================
# TESTS: TRIGGER EVALUATION
# ============================================================================


@pytest.mark.asyncio
async def test_evaluate_trigger_starts_journey(
    db_session, journey_engine, onboarding_journey, test_user
):
    """Test trigger evaluation starts appropriate journey."""
    started_journeys = await journey_engine.evaluate_trigger(
        db=db_session, trigger_type=TriggerType.SIGNUP, user_id=test_user.id, context={}
    )

    assert len(started_journeys) == 1
    assert onboarding_journey.id in started_journeys

    # Verify UserJourney record created
    result = await db_session.execute(
        select(UserJourney)
        .where(UserJourney.user_id == test_user.id)
        .where(UserJourney.journey_id == onboarding_journey.id)
    )
    user_journey = result.scalar_one()
    assert user_journey.status == "active"
    assert user_journey.started_at is not None


@pytest.mark.asyncio
async def test_evaluate_trigger_with_condition_match(
    db_session, journey_engine, admin_user, test_user
):
    """Test trigger evaluation with matching condition."""
    # Create journey with condition
    journey = Journey(
        id=str(uuid4()),
        name="Premium Journey",
        trigger_type=TriggerType.SIGNUP.value,
        trigger_config={"field": "plan", "op": "eq", "value": "premium"},
        is_active=True,
        created_by=admin_user.id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(journey)
    await db_session.commit()

    # Trigger with matching context
    started_journeys = await journey_engine.evaluate_trigger(
        db=db_session,
        trigger_type=TriggerType.SIGNUP,
        user_id=test_user.id,
        context={"plan": "premium"},
    )

    assert len(started_journeys) == 1
    assert journey.id in started_journeys


@pytest.mark.asyncio
async def test_evaluate_trigger_with_condition_no_match(
    db_session, journey_engine, admin_user, test_user
):
    """Test trigger evaluation with non-matching condition."""
    # Create journey with condition
    journey = Journey(
        id=str(uuid4()),
        name="Premium Journey",
        trigger_type=TriggerType.SIGNUP.value,
        trigger_config={"field": "plan", "op": "eq", "value": "premium"},
        is_active=True,
        created_by=admin_user.id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(journey)
    await db_session.commit()

    # Trigger with non-matching context
    started_journeys = await journey_engine.evaluate_trigger(
        db=db_session,
        trigger_type=TriggerType.SIGNUP,
        user_id=test_user.id,
        context={"plan": "free"},
    )

    assert len(started_journeys) == 0


@pytest.mark.asyncio
async def test_evaluate_trigger_idempotency(
    db_session, journey_engine, onboarding_journey, test_user
):
    """Test trigger evaluation is idempotent - doesn't start duplicate journeys."""
    # First trigger
    started_journeys1 = await journey_engine.evaluate_trigger(
        db=db_session, trigger_type=TriggerType.SIGNUP, user_id=test_user.id, context={}
    )
    assert len(started_journeys1) == 1

    # Second trigger (should not start duplicate)
    started_journeys2 = await journey_engine.evaluate_trigger(
        db=db_session, trigger_type=TriggerType.SIGNUP, user_id=test_user.id, context={}
    )
    assert len(started_journeys2) == 0

    # Verify only one UserJourney exists
    result = await db_session.execute(
        select(UserJourney)
        .where(UserJourney.user_id == test_user.id)
        .where(UserJourney.journey_id == onboarding_journey.id)
    )
    user_journeys = result.scalars().all()
    assert len(user_journeys) == 1


@pytest.mark.asyncio
async def test_evaluate_trigger_inactive_journey_skipped(
    db_session, journey_engine, admin_user, test_user
):
    """Test inactive journeys are not triggered."""
    journey = Journey(
        id=str(uuid4()),
        name="Inactive Journey",
        trigger_type=TriggerType.SIGNUP.value,
        is_active=False,  # Inactive
        created_by=admin_user.id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(journey)
    await db_session.commit()

    started_journeys = await journey_engine.evaluate_trigger(
        db=db_session, trigger_type=TriggerType.SIGNUP, user_id=test_user.id, context={}
    )

    assert len(started_journeys) == 0


@pytest.mark.asyncio
async def test_evaluate_trigger_priority_ordering(
    db_session, journey_engine, admin_user, test_user
):
    """Test journeys are evaluated in priority order."""
    # Create two journeys with different priorities
    high_priority = Journey(
        id=str(uuid4()),
        name="High Priority",
        trigger_type=TriggerType.SIGNUP.value,
        priority=100,
        is_active=True,
        created_by=admin_user.id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(high_priority)

    low_priority = Journey(
        id=str(uuid4()),
        name="Low Priority",
        trigger_type=TriggerType.SIGNUP.value,
        priority=10,
        is_active=True,
        created_by=admin_user.id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(low_priority)
    await db_session.commit()

    started_journeys = await journey_engine.evaluate_trigger(
        db=db_session, trigger_type=TriggerType.SIGNUP, user_id=test_user.id, context={}
    )

    # Both should start (no exclusivity unless condition specified)
    assert len(started_journeys) == 2
    # High priority evaluated first
    assert started_journeys[0] == high_priority.id


# ============================================================================
# TESTS: STEP EXECUTION
# ============================================================================


@pytest.mark.asyncio
async def test_execute_steps_immediate(
    db_session, journey_engine, onboarding_journey, test_user
):
    """Test executing immediate steps (no delay)."""
    # Start journey
    user_journey = UserJourney(
        id=str(uuid4()),
        user_id=test_user.id,
        journey_id=onboarding_journey.id,
        status="active",
        started_at=datetime.utcnow(),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(user_journey)
    await db_session.commit()

    # Execute steps
    result = await journey_engine.execute_steps(
        db=db_session, user_journey_id=user_journey.id
    )

    # Only step 0 (no delay) should execute
    assert result["status"] == "executed"
    assert result["executed"] >= 1  # At least welcome email
    assert result["skipped"] >= 1  # Delayed steps skipped

    # Verify step execution recorded
    exec_result = await db_session.execute(
        select(StepExecution)
        .where(StepExecution.user_journey_id == user_journey.id)
        .where(StepExecution.status == "success")
    )
    executions = exec_result.scalars().all()
    assert len(executions) >= 1


@pytest.mark.asyncio
async def test_execute_steps_with_delay(
    db_session, journey_engine, onboarding_journey, test_user
):
    """Test steps respect delay_minutes."""
    # Start journey in the past to allow delayed steps
    past_time = datetime.utcnow() - timedelta(minutes=10)
    user_journey = UserJourney(
        id=str(uuid4()),
        user_id=test_user.id,
        journey_id=onboarding_journey.id,
        status="active",
        started_at=past_time,
        created_at=past_time,
        updated_at=past_time,
    )
    db_session.add(user_journey)
    await db_session.commit()

    # Execute steps
    result = await journey_engine.execute_steps(
        db=db_session, user_journey_id=user_journey.id
    )

    # Step with 5min delay should now execute
    assert result["executed"] >= 2  # Welcome email + Telegram intro


@pytest.mark.asyncio
async def test_execute_steps_idempotency(
    db_session, journey_engine, onboarding_journey, test_user
):
    """Test step execution is idempotent - doesn't re-execute completed steps."""
    user_journey = UserJourney(
        id=str(uuid4()),
        user_id=test_user.id,
        journey_id=onboarding_journey.id,
        status="active",
        started_at=datetime.utcnow(),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(user_journey)
    await db_session.commit()

    # First execution
    result1 = await journey_engine.execute_steps(
        db=db_session, user_journey_id=user_journey.id
    )
    assert result1["executed"] > 0  # At least one step executed

    # Second execution (should not re-execute completed steps)
    result2 = await journey_engine.execute_steps(
        db=db_session, user_journey_id=user_journey.id
    )
    executed_count2 = result2["executed"]

    assert executed_count2 == 0  # No new executions


@pytest.mark.asyncio
async def test_execute_steps_with_condition_pass(
    db_session, journey_engine, admin_user, test_user
):
    """Test step with passing condition executes."""
    journey = Journey(
        id=str(uuid4()),
        name="Conditional Journey",
        trigger_type=TriggerType.SIGNUP.value,
        is_active=True,
        created_by=admin_user.id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(journey)

    # Step with condition
    step = JourneyStep(
        id=str(uuid4()),
        journey_id=journey.id,
        name="Premium Welcome",
        order=0,
        action_type=ActionType.SEND_EMAIL.value,
        action_config={"template": "premium_welcome"},
        condition={"field": "plan", "op": "eq", "value": "premium"},
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(step)
    await db_session.commit()

    # Start journey with matching metadata
    user_journey = UserJourney(
        id=str(uuid4()),
        user_id=test_user.id,
        journey_id=journey.id,
        status="active",
        started_at=datetime.utcnow(),
        metadata={"plan": "premium"},  # Matches condition
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(user_journey)
    await db_session.commit()

    result = await journey_engine.execute_steps(
        db=db_session, user_journey_id=user_journey.id
    )

    assert result["executed"] == 1
    assert result["skipped"] == 0


@pytest.mark.asyncio
async def test_execute_steps_with_condition_fail(
    db_session, journey_engine, admin_user, test_user
):
    """Test step with failing condition is skipped."""
    journey = Journey(
        id=str(uuid4()),
        name="Conditional Journey",
        trigger_type=TriggerType.SIGNUP.value,
        is_active=True,
        created_by=admin_user.id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(journey)

    step = JourneyStep(
        id=str(uuid4()),
        journey_id=journey.id,
        name="Premium Welcome",
        order=0,
        action_type=ActionType.SEND_EMAIL.value,
        action_config={"template": "premium_welcome"},
        condition={"field": "plan", "op": "eq", "value": "premium"},
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(step)
    await db_session.commit()

    # Start journey with non-matching metadata
    user_journey = UserJourney(
        id=str(uuid4()),
        user_id=test_user.id,
        journey_id=journey.id,
        status="active",
        started_at=datetime.utcnow(),
        metadata={"plan": "free"},  # Does not match condition
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(user_journey)
    await db_session.commit()

    result = await journey_engine.execute_steps(
        db=db_session, user_journey_id=user_journey.id
    )

    assert result["executed"] == 0
    assert result["skipped"] == 1

    # Verify step marked as skipped
    exec_result = await db_session.execute(
        select(StepExecution)
        .where(StepExecution.user_journey_id == user_journey.id)
        .where(StepExecution.status == "skipped")
    )
    skipped_exec = exec_result.scalar_one()
    assert skipped_exec is not None


@pytest.mark.asyncio
async def test_execute_steps_journey_completion(
    db_session, journey_engine, admin_user, test_user
):
    """Test journey is marked complete when all steps executed."""
    journey = Journey(
        id=str(uuid4()),
        name="Simple Journey",
        trigger_type=TriggerType.SIGNUP.value,
        is_active=True,
        created_by=admin_user.id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(journey)

    # Single immediate step
    step = JourneyStep(
        id=str(uuid4()),
        journey_id=journey.id,
        name="Welcome",
        order=0,
        action_type=ActionType.SEND_EMAIL.value,
        action_config={"template": "welcome"},
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(step)
    await db_session.commit()

    user_journey = UserJourney(
        id=str(uuid4()),
        user_id=test_user.id,
        journey_id=journey.id,
        status="active",
        started_at=datetime.utcnow(),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(user_journey)
    await db_session.commit()

    result = await journey_engine.execute_steps(
        db=db_session, user_journey_id=user_journey.id
    )

    assert result["executed"] == 1

    # Verify journey marked completed
    await db_session.refresh(user_journey)
    assert user_journey.status == "completed"
    assert user_journey.completed_at is not None


# ============================================================================
# TESTS: CONDITION OPERATORS
# ============================================================================


@pytest.mark.asyncio
async def test_condition_operator_eq(journey_engine):
    """Test equality condition operator."""
    condition = {"field": "plan", "op": "eq", "value": "premium"}
    context = {"plan": "premium"}

    assert journey_engine._evaluate_condition(condition, context) is True

    context_mismatch = {"plan": "free"}
    assert journey_engine._evaluate_condition(condition, context_mismatch) is False


@pytest.mark.asyncio
async def test_condition_operator_ne(journey_engine):
    """Test not-equal condition operator."""
    condition = {"field": "plan", "op": "ne", "value": "free"}
    context = {"plan": "premium"}

    assert journey_engine._evaluate_condition(condition, context) is True

    context_mismatch = {"plan": "free"}
    assert journey_engine._evaluate_condition(condition, context_mismatch) is False


@pytest.mark.asyncio
async def test_condition_operator_gt(journey_engine):
    """Test greater-than condition operator."""
    condition = {"field": "age", "op": "gt", "value": 18}
    context = {"age": 25}

    assert journey_engine._evaluate_condition(condition, context) is True

    context_mismatch = {"age": 15}
    assert journey_engine._evaluate_condition(condition, context_mismatch) is False


@pytest.mark.asyncio
async def test_condition_operator_in(journey_engine):
    """Test in condition operator."""
    condition = {"field": "plan", "op": "in", "value": ["premium", "gold"]}
    context = {"plan": "premium"}

    assert journey_engine._evaluate_condition(condition, context) is True

    context_mismatch = {"plan": "free"}
    assert journey_engine._evaluate_condition(condition, context_mismatch) is False


@pytest.mark.asyncio
async def test_condition_operator_contains(journey_engine):
    """Test contains condition operator."""
    condition = {"field": "tags", "op": "contains", "value": "vip"}
    context = {"tags": ["vip", "early_adopter"]}

    assert journey_engine._evaluate_condition(condition, context) is True

    context_mismatch = {"tags": ["regular"]}
    assert journey_engine._evaluate_condition(condition, context_mismatch) is False


# ============================================================================
# TESTS: ACTION EXECUTION
# ============================================================================


@pytest.mark.asyncio
async def test_action_send_email(db_session, journey_engine, test_user):
    """Test email sending action."""
    result = await journey_engine._send_email(
        test_user.id, {"template": "welcome", "subject": "Hello"}
    )

    assert result["status"] == "sent"
    assert result["channel"] == "email"
    assert result["user_id"] == test_user.id


@pytest.mark.asyncio
async def test_action_send_telegram(db_session, journey_engine, test_user):
    """Test Telegram sending action."""
    result = await journey_engine._send_telegram(test_user.id, {"message": "Welcome!"})

    assert result["status"] == "sent"
    assert result["channel"] == "telegram"
    assert result["user_id"] == test_user.id


@pytest.mark.asyncio
async def test_action_apply_tag(db_session, journey_engine, test_user):
    """Test tag application action."""
    result = await journey_engine._apply_tag(
        db_session, test_user.id, {"tag": "onboarded"}
    )

    assert result["status"] == "applied"
    assert result["tag"] == "onboarded"
    assert result["user_id"] == test_user.id


@pytest.mark.asyncio
async def test_action_grant_reward(db_session, journey_engine, test_user):
    """Test reward granting action."""
    result = await journey_engine._grant_reward(
        db_session, test_user.id, {"type": "credit", "value": 10}
    )

    assert result["status"] == "granted"
    assert result["type"] == "credit"
    assert result["value"] == 10
    assert result["user_id"] == test_user.id


# ============================================================================
# TESTS: ERROR HANDLING
# ============================================================================


@pytest.mark.asyncio
async def test_execute_steps_inactive_journey_skipped(
    db_session, journey_engine, admin_user, test_user
):
    """Test inactive journey steps are not executed."""
    journey = Journey(
        id=str(uuid4()),
        name="Inactive Journey",
        trigger_type=TriggerType.SIGNUP.value,
        is_active=True,
        created_by=admin_user.id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(journey)
    await db_session.commit()

    # Create inactive user journey
    user_journey = UserJourney(
        id=str(uuid4()),
        user_id=test_user.id,
        journey_id=journey.id,
        status="completed",  # Not active
        started_at=datetime.utcnow(),
        completed_at=datetime.utcnow(),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(user_journey)
    await db_session.commit()

    result = await journey_engine.execute_steps(
        db=db_session, user_journey_id=user_journey.id
    )

    assert result["status"] == "skipped"
    assert result["reason"] == "journey not active"


@pytest.mark.asyncio
async def test_execute_steps_updates_current_step(
    db_session, journey_engine, onboarding_journey, test_user
):
    """Test user journey tracks current step."""
    user_journey = UserJourney(
        id=str(uuid4()),
        user_id=test_user.id,
        journey_id=onboarding_journey.id,
        status="active",
        started_at=datetime.utcnow(),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(user_journey)
    await db_session.commit()

    await journey_engine.execute_steps(db=db_session, user_journey_id=user_journey.id)

    await db_session.refresh(user_journey)
    assert user_journey.current_step_id is not None  # Updated to last executed step
    assert user_journey.updated_at is not None


@pytest.mark.asyncio
async def test_condition_missing_field_returns_false(journey_engine):
    """Test condition with missing field in context returns false."""
    condition = {"field": "nonexistent", "op": "eq", "value": "test"}
    context = {"other_field": "value"}

    result = journey_engine._evaluate_condition(condition, context)
    assert result is False
