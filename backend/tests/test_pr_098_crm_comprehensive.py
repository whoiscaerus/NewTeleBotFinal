"""
PR-098: Comprehensive CRM Tests

Tests ALL business logic:
- Playbook execution engine
- Event triggers
- Quiet hours enforcement
- Discount code generation
- Owner DM scheduling
- Step advancement
- Conversion tracking
- Message delivery integration

NO MOCKS for core business logic - validates REAL service behavior.
"""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.models import User
from backend.app.crm.models import (
    CRMDiscountCode,
    CRMPlaybookExecution,
    CRMStepExecution,
)
from backend.app.crm.playbooks import (
    PLAYBOOKS,
    execute_pending_steps,
    mark_converted,
    start_playbook,
)
from backend.app.crm.triggers import (
    trigger_churn_risk,
    trigger_inactivity,
    trigger_milestone,
    trigger_payment_failed,
    trigger_trial_ending,
    trigger_winback,
)
from backend.app.messaging.bus import MessagingBus
from backend.app.prefs.models import UserPreferences

# ===== FIXTURES =====


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create test user."""
    user = User(
        id=str(uuid4()),
        telegram_id=123456789,
        username="test_user",
        email="test@example.com",
        hashed_password="test_hash",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def user_prefs(db_session: AsyncSession, test_user: User) -> UserPreferences:
    """Create user preferences with quiet hours OFF."""
    prefs = UserPreferences(
        user_id=test_user.id,
        instruments_enabled=["gold"],
        alert_types_enabled=["price"],
        notify_via_telegram=True,
        notify_via_email=True,
        notify_via_push=False,
        quiet_hours_enabled=False,  # Default: no quiet hours
        quiet_hours_start=None,
        quiet_hours_end=None,
        timezone="UTC",
        digest_frequency="immediate",
        notify_entry_failure=True,
        notify_exit_failure=True,
    )
    db_session.add(prefs)
    await db_session.commit()
    await db_session.refresh(prefs)
    return prefs


@pytest_asyncio.fixture
async def mock_messaging_bus() -> MessagingBus:
    """Create mock messaging bus (doesn't actually send)."""
    bus = MessagingBus()
    # Don't initialize Redis (tests will mock enqueue_message if needed)
    return bus


# ===== PLAYBOOK DEFINITIONS TESTS =====


@pytest.mark.asyncio
async def test_playbook_definitions_exist():
    """Test all required playbooks are defined."""
    required_playbooks = [
        "payment_failed_rescue",
        "trial_ending",
        "inactivity_nudge",
        "winback",
        "milestone_congrats",
        "churn_risk",
    ]

    for playbook_name in required_playbooks:
        assert playbook_name in PLAYBOOKS, f"Playbook {playbook_name} not found"

        playbook = PLAYBOOKS[playbook_name]
        assert "name" in playbook
        assert "trigger" in playbook
        assert "steps" in playbook
        assert len(playbook["steps"]) > 0


@pytest.mark.asyncio
async def test_playbook_steps_valid():
    """Test playbook steps have valid structure."""
    for playbook_name, playbook in PLAYBOOKS.items():
        for i, step in enumerate(playbook["steps"]):
            assert "type" in step, f"{playbook_name} step {i} missing type"
            assert step["type"] in [
                "send_message",
                "discount_code",
                "owner_dm",
                "wait",
            ]

            if step["type"] == "send_message":
                assert "channel" in step
                assert "template" in step
                assert step["channel"] in ["email", "telegram", "push"]


# ===== PLAYBOOK EXECUTION TESTS =====


@pytest.mark.asyncio
async def test_start_playbook_creates_execution(
    db_session: AsyncSession, test_user: User
):
    """Test starting a playbook creates execution record."""
    context = {"amount": 20, "subscription_id": "sub_123"}

    execution = await start_playbook(
        db_session, test_user.id, "payment_failed_rescue", context
    )

    assert execution.id is not None
    assert execution.user_id == test_user.id
    assert execution.playbook_name == "payment_failed_rescue"
    assert execution.trigger_event == "payment_failed"
    assert execution.status == "active"
    assert execution.current_step == 0
    assert execution.total_steps == 3  # payment_failed_rescue has 3 steps
    assert execution.context == context


@pytest.mark.asyncio
async def test_start_playbook_prevents_duplicates(
    db_session: AsyncSession, test_user: User
):
    """Test starting same playbook twice returns existing execution."""
    context = {"amount": 20}

    execution1 = await start_playbook(
        db_session, test_user.id, "payment_failed_rescue", context
    )

    execution2 = await start_playbook(
        db_session, test_user.id, "payment_failed_rescue", context
    )

    assert execution1.id == execution2.id  # Same execution returned


@pytest.mark.asyncio
async def test_execute_step_sends_message(
    db_session: AsyncSession, test_user: User, user_prefs: UserPreferences, monkeypatch
):
    """Test executing send_message step."""
    # Mock messaging bus enqueue_message
    messages_sent = []

    async def mock_enqueue(
        self, user_id, channel, template_name, template_vars, priority
    ):
        messages_sent.append(
            {
                "user_id": user_id,
                "channel": channel,
                "template_name": template_name,
            }
        )
        return str(uuid4())

    monkeypatch.setattr(MessagingBus, "enqueue_message", mock_enqueue)

    # Start playbook
    context = {"amount": 20}
    execution = await start_playbook(db_session, test_user.id, "trial_ending", context)

    # Execute first step (send_message)
    bus = MessagingBus()
    await execute_pending_steps(db_session, bus)

    # Verify message was sent
    assert len(messages_sent) == 1
    assert messages_sent[0]["user_id"] == test_user.id
    assert messages_sent[0]["channel"] == "email"
    assert messages_sent[0]["template_name"] == "trial_ending_reminder"

    # Verify step execution record created
    result = await db_session.execute(
        select(CRMStepExecution).where(CRMStepExecution.execution_id == execution.id)
    )
    step_records = result.scalars().all()
    assert len(step_records) == 1
    assert step_records[0].status == "completed"
    assert step_records[0].step_type == "send_message"


@pytest.mark.asyncio
async def test_quiet_hours_blocks_message(
    db_session: AsyncSession, test_user: User, user_prefs: UserPreferences, monkeypatch
):
    """Test quiet hours prevents message send."""
    # Enable quiet hours (current time is in quiet hours)
    from datetime import datetime

    now = datetime.utcnow()
    user_prefs.quiet_hours_enabled = True
    user_prefs.quiet_hours_start = (now - timedelta(hours=1)).time()
    user_prefs.quiet_hours_end = (now + timedelta(hours=1)).time()
    await db_session.commit()

    # Mock messaging bus
    messages_sent = []

    async def mock_enqueue(
        self, user_id, channel, template_name, template_vars, priority
    ):
        messages_sent.append({"user_id": user_id})
        return str(uuid4())

    monkeypatch.setattr(MessagingBus, "enqueue_message", mock_enqueue)

    # Start playbook
    execution = await start_playbook(
        db_session, test_user.id, "inactivity_nudge", {"days_inactive": 14}
    )

    # Execute step
    bus = MessagingBus()
    await execute_pending_steps(db_session, bus)

    # Verify NO message was sent
    assert len(messages_sent) == 0

    # Verify step marked as skipped
    result = await db_session.execute(
        select(CRMStepExecution).where(CRMStepExecution.execution_id == execution.id)
    )
    step_records = result.scalars().all()
    assert len(step_records) == 1
    assert step_records[0].status == "skipped"
    assert step_records[0].error_message == "quiet_hours"


@pytest.mark.asyncio
async def test_discount_code_created_with_message(
    db_session: AsyncSession, test_user: User, user_prefs: UserPreferences, monkeypatch
):
    """Test discount code is created when step includes discount_percent."""

    # Mock messaging bus
    async def mock_enqueue(
        self, user_id, channel, template_name, template_vars, priority
    ):
        return str(uuid4())

    monkeypatch.setattr(MessagingBus, "enqueue_message", mock_enqueue)

    # Start playbook with discount step
    execution = await start_playbook(
        db_session,
        test_user.id,
        "trial_ending",
        {"trial_end_date": datetime.utcnow().isoformat()},
    )

    # Execute steps
    bus = MessagingBus()
    await execute_pending_steps(db_session, bus)  # Step 0

    # Advance to step 1 (has discount)
    await db_session.refresh(execution)
    execution.next_action_at = datetime.utcnow()  # Make step 1 ready
    await db_session.commit()

    await execute_pending_steps(db_session, bus)  # Step 1

    # Verify discount code created
    result = await db_session.execute(
        select(CRMDiscountCode).where(CRMDiscountCode.user_id == test_user.id)
    )
    discount_codes = result.scalars().all()
    assert len(discount_codes) == 1
    assert discount_codes[0].percent_off == 15  # trial_ending step 2 has 15%
    assert discount_codes[0].max_uses == 1
    assert discount_codes[0].used_count == 0


@pytest.mark.asyncio
async def test_owner_dm_sent(
    db_session: AsyncSession, test_user: User, user_prefs: UserPreferences, monkeypatch
):
    """Test owner DM step sends notification to owner."""
    # Mock messaging bus
    owner_messages = []

    async def mock_enqueue(
        self, user_id, channel, template_name, template_vars, priority
    ):
        if user_id == "owner":
            owner_messages.append(template_vars)
        return str(uuid4())

    monkeypatch.setattr(MessagingBus, "enqueue_message", mock_enqueue)

    # Start playbook with owner DM step
    execution = await start_playbook(
        db_session,
        test_user.id,
        "payment_failed_rescue",
        {"amount": 20, "email": test_user.email},
    )

    # Execute all steps (0: email, 1: telegram, 2: owner DM)
    bus = MessagingBus()

    # Step 0
    await execute_pending_steps(db_session, bus)

    # Step 1 (24h delay)
    await db_session.refresh(execution)
    execution.next_action_at = datetime.utcnow()
    await db_session.commit()
    await execute_pending_steps(db_session, bus)

    # Step 2 (48h delay - owner DM)
    await db_session.refresh(execution)
    execution.next_action_at = datetime.utcnow()
    await db_session.commit()
    await execute_pending_steps(db_session, bus)

    # Verify owner DM sent
    assert len(owner_messages) == 1
    assert test_user.id in owner_messages[0]["message"]
    assert test_user.email in owner_messages[0]["message"]


@pytest.mark.asyncio
async def test_playbook_advances_through_steps(
    db_session: AsyncSession, test_user: User, user_prefs: UserPreferences, monkeypatch
):
    """Test playbook advances from step 0 → 1 → 2 → completed."""

    # Mock messaging bus
    async def mock_enqueue(
        self, user_id, channel, template_name, template_vars, priority
    ):
        return str(uuid4())

    monkeypatch.setattr(MessagingBus, "enqueue_message", mock_enqueue)

    # Start 2-step playbook
    execution = await start_playbook(
        db_session,
        test_user.id,
        "trial_ending",
        {"trial_end_date": datetime.utcnow().isoformat()},
    )

    assert execution.current_step == 0
    assert execution.status == "active"

    bus = MessagingBus()

    # Execute step 0
    await execute_pending_steps(db_session, bus)
    await db_session.refresh(execution)
    assert execution.current_step == 1
    assert execution.status == "active"

    # Execute step 1
    execution.next_action_at = datetime.utcnow()  # Make ready
    await db_session.commit()
    await execute_pending_steps(db_session, bus)
    await db_session.refresh(execution)

    assert execution.current_step == 2  # Beyond last step
    assert execution.status == "completed"
    assert execution.completed_at is not None


@pytest.mark.asyncio
async def test_mark_converted_stops_playbook(db_session: AsyncSession, test_user: User):
    """Test marking execution as converted stops playbook."""
    execution = await start_playbook(
        db_session, test_user.id, "payment_failed_rescue", {"amount": 20}
    )

    assert execution.status == "active"

    # Mark as converted
    await mark_converted(db_session, execution.id, conversion_value=20)

    # Verify status changed
    await db_session.refresh(execution)
    assert execution.status == "abandoned"
    assert execution.converted_at is not None
    assert execution.conversion_value == 20


# ===== EVENT TRIGGER TESTS =====


@pytest.mark.asyncio
async def test_trigger_payment_failed_starts_rescue(
    db_session: AsyncSession, test_user: User
):
    """Test payment_failed event starts rescue playbook."""
    await trigger_payment_failed(
        db_session,
        user_id=test_user.id,
        subscription_id="sub_123",
        amount=20.0,
        currency="GBP",
    )

    # Verify execution created
    result = await db_session.execute(
        select(CRMPlaybookExecution)
        .where(CRMPlaybookExecution.user_id == test_user.id)
        .where(CRMPlaybookExecution.playbook_name == "payment_failed_rescue")
    )
    execution = result.scalar_one_or_none()

    assert execution is not None
    assert execution.status == "active"
    assert execution.context["amount"] == 20.0
    assert execution.context["subscription_id"] == "sub_123"


@pytest.mark.asyncio
async def test_trigger_trial_ending_starts_nudge(
    db_session: AsyncSession, test_user: User
):
    """Test trial_expiring_soon event starts trial_ending playbook."""
    trial_end = datetime.utcnow() + timedelta(days=3)

    await trigger_trial_ending(db_session, test_user.id, trial_end)

    # Verify execution created
    result = await db_session.execute(
        select(CRMPlaybookExecution)
        .where(CRMPlaybookExecution.user_id == test_user.id)
        .where(CRMPlaybookExecution.playbook_name == "trial_ending")
    )
    execution = result.scalar_one_or_none()

    assert execution is not None
    assert execution.context["days_remaining"] == 3


@pytest.mark.asyncio
async def test_trigger_inactivity_starts_nudge(
    db_session: AsyncSession, test_user: User
):
    """Test inactivity_14d event starts inactivity_nudge playbook."""
    last_activity = datetime.utcnow() - timedelta(days=14)

    await trigger_inactivity(db_session, test_user.id, last_activity)

    # Verify execution created
    result = await db_session.execute(
        select(CRMPlaybookExecution)
        .where(CRMPlaybookExecution.user_id == test_user.id)
        .where(CRMPlaybookExecution.playbook_name == "inactivity_nudge")
    )
    execution = result.scalar_one_or_none()

    assert execution is not None
    assert execution.context["days_inactive"] == 14


@pytest.mark.asyncio
async def test_trigger_churn_risk_starts_playbook(
    db_session: AsyncSession, test_user: User
):
    """Test churn_risk_detected event starts churn_risk playbook."""
    await trigger_churn_risk(
        db_session,
        test_user.id,
        risk_score=0.75,
        risk_factors=["declining_usage", "negative_pnl"],
    )

    # Verify execution created
    result = await db_session.execute(
        select(CRMPlaybookExecution)
        .where(CRMPlaybookExecution.user_id == test_user.id)
        .where(CRMPlaybookExecution.playbook_name == "churn_risk")
    )
    execution = result.scalar_one_or_none()

    assert execution is not None
    assert execution.context["risk_score"] == 0.75
    assert "declining_usage" in execution.context["risk_factors"]


@pytest.mark.asyncio
async def test_trigger_milestone_starts_congrats(
    db_session: AsyncSession, test_user: User
):
    """Test new_high_watermark event starts milestone_congrats playbook."""
    await trigger_milestone(
        db_session, test_user.id, milestone_type="new_profit_high", value=1000.0
    )

    # Verify execution created
    result = await db_session.execute(
        select(CRMPlaybookExecution)
        .where(CRMPlaybookExecution.user_id == test_user.id)
        .where(CRMPlaybookExecution.playbook_name == "milestone_congrats")
    )
    execution = result.scalar_one_or_none()

    assert execution is not None
    assert execution.context["value"] == 1000.0


@pytest.mark.asyncio
async def test_trigger_winback_starts_playbook(
    db_session: AsyncSession, test_user: User
):
    """Test subscription_cancelled event starts winback playbook."""
    cancelled_at = datetime.utcnow()

    await trigger_winback(
        db_session, test_user.id, cancelled_at, subscription_tier="premium"
    )

    # Verify execution created
    result = await db_session.execute(
        select(CRMPlaybookExecution)
        .where(CRMPlaybookExecution.user_id == test_user.id)
        .where(CRMPlaybookExecution.playbook_name == "winback")
    )
    execution = result.scalar_one_or_none()

    assert execution is not None
    assert execution.context["subscription_tier"] == "premium"


# ===== EDGE CASES & ERROR HANDLING =====


@pytest.mark.asyncio
async def test_invalid_playbook_name_raises_error(
    db_session: AsyncSession, test_user: User
):
    """Test starting non-existent playbook raises ValueError."""
    with pytest.raises(ValueError, match="Unknown playbook"):
        await start_playbook(
            db_session, test_user.id, "nonexistent_playbook", {}  # type: ignore
        )


@pytest.mark.asyncio
async def test_execution_continues_on_step_error(
    db_session: AsyncSession, test_user: User, user_prefs: UserPreferences, monkeypatch
):
    """Test execution continues even if a step fails."""
    # Mock messaging bus to fail on first call, succeed on second
    call_count = [0]

    async def mock_enqueue_with_error(
        self, user_id, channel, template_name, template_vars, priority
    ):
        call_count[0] += 1
        if call_count[0] == 1:
            raise RuntimeError("Simulated send error")
        return str(uuid4())

    monkeypatch.setattr(MessagingBus, "enqueue_message", mock_enqueue_with_error)

    execution = await start_playbook(
        db_session,
        test_user.id,
        "trial_ending",
        {"trial_end_date": datetime.utcnow().isoformat()},
    )

    bus = MessagingBus()

    # Execute step 0 (will fail)
    await execute_pending_steps(db_session, bus)

    # Verify moved to next step despite error
    await db_session.refresh(execution)
    assert execution.current_step == 1  # Advanced anyway

    # Verify error recorded
    result = await db_session.execute(
        select(CRMStepExecution)
        .where(CRMStepExecution.execution_id == execution.id)
        .where(CRMStepExecution.step_number == 0)
    )
    failed_step = result.scalar_one_or_none()
    assert failed_step is not None
    assert failed_step.status == "failed"
    assert "Simulated send error" in failed_step.error_message


@pytest.mark.asyncio
async def test_discount_code_has_correct_expiry(
    db_session: AsyncSession, test_user: User, user_prefs: UserPreferences, monkeypatch
):
    """Test discount codes expire after 7 days."""

    async def mock_enqueue(
        self, user_id, channel, template_name, template_vars, priority
    ):
        return str(uuid4())

    monkeypatch.setattr(MessagingBus, "enqueue_message", mock_enqueue)

    execution = await start_playbook(
        db_session,
        test_user.id,
        "winback",
        {"cancelled_at": datetime.utcnow().isoformat(), "subscription_tier": "free"},
    )

    bus = MessagingBus()

    # Execute step 0
    await execute_pending_steps(db_session, bus)

    # Execute step 1 (has 30% discount)
    await db_session.refresh(execution)
    execution.next_action_at = datetime.utcnow()
    await db_session.commit()
    await execute_pending_steps(db_session, bus)

    # Verify discount code
    result = await db_session.execute(
        select(CRMDiscountCode).where(CRMDiscountCode.user_id == test_user.id)
    )
    code = result.scalar_one_or_none()

    assert code is not None
    assert code.percent_off == 30  # winback step has 30%

    # Check expiry (should be ~7 days from now)
    time_until_expiry = code.expires_at - datetime.utcnow()
    assert 6.5 <= time_until_expiry.days <= 7.5  # Allow some tolerance


@pytest.mark.asyncio
async def test_no_duplicate_executions_per_playbook(
    db_session: AsyncSession, test_user: User
):
    """Test user can't have multiple active executions of same playbook."""
    # Start first execution
    execution1 = await start_playbook(
        db_session, test_user.id, "inactivity_nudge", {"days_inactive": 14}
    )

    # Try to start second execution
    execution2 = await start_playbook(
        db_session, test_user.id, "inactivity_nudge", {"days_inactive": 15}
    )

    # Should return same execution
    assert execution1.id == execution2.id

    # Verify only one execution in DB
    result = await db_session.execute(
        select(CRMPlaybookExecution)
        .where(CRMPlaybookExecution.user_id == test_user.id)
        .where(CRMPlaybookExecution.playbook_name == "inactivity_nudge")
    )
    executions = result.scalars().all()
    assert len(executions) == 1
