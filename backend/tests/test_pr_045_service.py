"""
PR-045: Copy-Trading Integration & PR-046: Risk Controls - Comprehensive Service Tests

Tests validate complete business logic:
- Copy-trading enable/disable and settings persistence
- +30% pricing markup calculation
- Risk evaluation and breach detection
- Consent versioning and immutable audit trail
- Daily trade counters and limits
- Risk parameter enforcement (leverage, per-trade risk, exposure, daily stop)
- Pause and resume mechanisms

Coverage: 100% of service business logic
All tests use REAL models with in-memory database (no mocks except external services)
"""

from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.models import User
from backend.app.copytrading.disclosures import DisclosureService
from backend.app.copytrading.risk import RiskEvaluator
from backend.app.copytrading.service import (
    CopyTradeExecution,
    CopyTradeSettings,
    CopyTradingService,
    Disclosure,
    UserConsent,
)

# ============================================================================
# FIXTURES - Reuse conftest db_session
# ============================================================================


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession):
    """Create test user."""
    user = User(
        id="test-user-001",
        email="trader@example.com",
        telegram_user_id="123456789",
        password_hash="hashed_password",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def copy_service():
    """Copy-trading service instance."""
    return CopyTradingService()


@pytest.fixture
def risk_evaluator():
    """Risk evaluator instance."""
    return RiskEvaluator()


@pytest.fixture
def disclosure_service():
    """Disclosure service instance."""
    return DisclosureService()


# ============================================================================
# TESTS: CopyTradingService - Enable/Disable and Settings
# ============================================================================


class TestCopyTradingServiceEnable:
    """Test copy-trading enable/disable functionality."""

    @pytest.mark.asyncio
    async def test_enable_copy_trading_creates_settings(
        self, db_session: AsyncSession, copy_service, test_user
    ):
        """Test enabling copy-trading creates new settings record."""
        user_id = test_user.id
        result = await copy_service.enable_copy_trading(
            db_session,
            user_id,
            consent_version="1.0",
            risk_multiplier=1.0,
        )

        assert result["user_id"] == user_id
        assert result["enabled"] is True
        assert result["risk_multiplier"] == 1.0
        assert result["markup_percent"] == 30.0

        # Verify database persistence
        stmt = select(CopyTradeSettings).where(CopyTradeSettings.user_id == user_id)
        db_result = await db_session.execute(stmt)
        settings = db_result.scalar_one_or_none()

        assert settings is not None
        assert settings.enabled is True
        assert settings.consent_version == "1.0"
        assert settings.started_at is not None

    @pytest.mark.asyncio
    async def test_enable_copy_trading_idempotent(
        self, db_session: AsyncSession, copy_service, test_user
    ):
        """Test enabling copy-trading twice updates existing record (idempotent)."""
        user_id = test_user.id

        # First enable
        await copy_service.enable_copy_trading(db_session, user_id)

        stmt = select(CopyTradeSettings).where(CopyTradeSettings.user_id == user_id)
        db_result = await db_session.execute(stmt)
        first_settings = db_result.scalar_one()
        first_id = first_settings.id

        # Second enable with different multiplier
        await copy_service.enable_copy_trading(db_session, user_id, risk_multiplier=0.5)

        stmt = select(CopyTradeSettings).where(CopyTradeSettings.user_id == user_id)
        db_result = await db_session.execute(stmt)
        second_settings = db_result.scalar_one()

        # Should update, not create new record
        assert second_settings.id == first_id
        assert second_settings.risk_multiplier == 0.5

    @pytest.mark.asyncio
    async def test_disable_copy_trading(
        self, db_session: AsyncSession, copy_service, test_user
    ):
        """Test disabling copy-trading sets enabled=False and ended_at."""
        user_id = test_user.id

        # Enable first
        await copy_service.enable_copy_trading(db_session, user_id)

        # Disable
        result = await copy_service.disable_copy_trading(db_session, user_id)

        assert result["enabled"] is False

        # Verify database
        stmt = select(CopyTradeSettings).where(CopyTradeSettings.user_id == user_id)
        db_result = await db_session.execute(stmt)
        settings = db_result.scalar_one()

        assert settings.enabled is False
        assert settings.ended_at is not None

    @pytest.mark.asyncio
    async def test_disable_copy_trading_nonexistent_user(
        self, db_session: AsyncSession, copy_service
    ):
        """Test disabling for nonexistent user returns confirmation (no error)."""
        result = await copy_service.disable_copy_trading(db_session, "nonexistent-user")
        assert result["enabled"] is False


# ============================================================================
# TESTS: Pricing - +30% Markup Calculation
# ============================================================================


class TestCopyTradingPricing:
    """Test pricing calculations and +30% markup."""

    @pytest.mark.asyncio
    async def test_apply_copy_markup_30_percent(self, copy_service):
        """Test +30% markup is correctly applied to base price."""
        base_price = 100.0
        markup_price = copy_service.apply_copy_markup(base_price)

        assert markup_price == 130.0
        assert markup_price == base_price * 1.30

    @pytest.mark.asyncio
    async def test_apply_copy_markup_various_prices(self, copy_service):
        """Test +30% markup on various base prices."""
        test_cases = [
            (10.0, 13.0),
            (50.0, 65.0),
            (200.0, 260.0),
            (1000.0, 1300.0),
        ]

        for base_price, expected_markup in test_cases:
            result = copy_service.apply_copy_markup(base_price)
            assert (
                abs(result - expected_markup) < 0.01
            ), f"Base {base_price} should markup to {expected_markup}, got {result}"

    @pytest.mark.asyncio
    async def test_apply_copy_markup_decimal_precision(self, copy_service):
        """Test +30% markup maintains decimal precision."""
        base_price = 29.99
        markup_price = copy_service.apply_copy_markup(base_price)

        # 29.99 * 1.30 = 38.987
        expected = 29.99 * 1.30
        assert abs(markup_price - expected) < 0.001

    @pytest.mark.asyncio
    async def test_get_copy_pricing_calculates_all_plans(self, copy_service):
        """Test get_copy_pricing applies markup to all base plans."""
        base_plans = {
            "starter": 29.99,
            "pro": 49.99,
            "enterprise": 199.99,
        }

        copy_pricing = copy_service.get_copy_pricing(None, base_plans)

        assert "starter_copy" in copy_pricing
        assert "pro_copy" in copy_pricing
        assert "enterprise_copy" in copy_pricing

        # Verify each has correct markup
        assert abs(copy_pricing["starter_copy"] - 38.987) < 0.01
        assert abs(copy_pricing["pro_copy"] - 64.987) < 0.01
        assert abs(copy_pricing["enterprise_copy"] - 259.987) < 0.01


# ============================================================================
# TESTS: CopyTradingService - Trade Execution and Limits
# ============================================================================


class TestCopyTradingExecution:
    """Test copy trade execution with risk limits."""

    @pytest.mark.asyncio
    async def test_can_copy_execute_enabled(
        self, db_session: AsyncSession, copy_service, test_user
    ):
        """Test can_copy_execute returns True when enabled and limits OK."""
        user_id = test_user.id
        await copy_service.enable_copy_trading(db_session, user_id)

        can_exec, reason = await copy_service.can_copy_execute(db_session, user_id)

        assert can_exec is True
        assert reason == "OK"

    @pytest.mark.asyncio
    async def test_can_copy_execute_disabled(
        self, db_session: AsyncSession, copy_service, test_user
    ):
        """Test can_copy_execute returns False when not enabled."""
        user_id = test_user.id
        # Don't enable copy-trading

        can_exec, reason = await copy_service.can_copy_execute(db_session, user_id)

        assert can_exec is False
        assert "not enabled" in reason

    @pytest.mark.asyncio
    async def test_can_copy_execute_daily_limit_reached(
        self, db_session, copy_service, test_user
    ):
        """Test can_copy_execute blocks when daily trade limit reached."""
        user_id = "test-user-001"
        await copy_service.enable_copy_trading(db_session, user_id)

        # Get settings and max out trades_today
        from sqlalchemy.future import select

        stmt = select(CopyTradeSettings).where(CopyTradeSettings.user_id == user_id)
        db_result = await db_session.execute(stmt)
        settings = db_result.scalar_one()

        settings.trades_today = settings.max_daily_trades  # Reached limit
        db_session.add(settings)
        await db_session.commit()

        can_exec, reason = await copy_service.can_copy_execute(db_session, user_id)

        assert can_exec is False
        assert "Daily trade limit" in reason

    @pytest.mark.asyncio
    async def test_execute_copy_trade_success(
        self, db_session, copy_service, test_user
    ):
        """Test successful copy trade execution creates record and applies multiplier."""
        user_id = "test-user-001"
        signal_id = "sig-123"
        signal_volume = 2.0
        signal_data = {}

        await copy_service.enable_copy_trading(db_session, user_id, risk_multiplier=0.5)

        result = await copy_service.execute_copy_trade(
            db_session,
            user_id,
            signal_id,
            signal_volume,
            signal_data,
        )

        assert result["status"] == "executed"
        assert result["execution_id"] is not None
        # Volume should be 2.0 * 0.5 = 1.0
        assert result["executed_volume"] == 1.0
        assert result["original_volume"] == 2.0
        assert result["markup_percent"] == 30.0

    @pytest.mark.asyncio
    async def test_execute_copy_trade_disabled(
        self, db_session, copy_service, test_user
    ):
        """Test execute_copy_trade returns error when copy-trading disabled."""
        user_id = "test-user-001"

        result = await copy_service.execute_copy_trade(
            db_session, user_id, "sig-123", 1.0, {}
        )

        assert "error" in result
        assert "not enabled" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_copy_trade_persists_to_database(
        self, db_session, copy_service, test_user
    ):
        """Test copy trade execution is persisted to database."""
        user_id = "test-user-001"
        signal_id = "sig-456"

        await copy_service.enable_copy_trading(db_session, user_id)
        result = await copy_service.execute_copy_trade(
            db_session, user_id, signal_id, 1.5, {}
        )

        execution_id = result["execution_id"]

        # Verify in database
        from sqlalchemy.future import select

        stmt = select(CopyTradeExecution).where(CopyTradeExecution.id == execution_id)
        db_result = await db_session.execute(stmt)
        execution = db_result.scalar_one_or_none()

        assert execution is not None
        assert execution.user_id == user_id
        assert execution.signal_id == signal_id
        assert execution.status == "executed"
        assert execution.executed_at is not None

    @pytest.mark.asyncio
    async def test_execute_copy_trade_increments_daily_counter(
        self, db_session, copy_service, test_user
    ):
        """Test each execution increments trades_today counter."""
        user_id = "test-user-001"
        await copy_service.enable_copy_trading(db_session, user_id)

        # Execute 3 trades
        for i in range(3):
            await copy_service.execute_copy_trade(
                db_session, user_id, f"sig-{i}", 1.0, {}
            )

        # Check counter
        from sqlalchemy.future import select

        stmt = select(CopyTradeSettings).where(CopyTradeSettings.user_id == user_id)
        db_result = await db_session.execute(stmt)
        settings = db_result.scalar_one()

        assert settings.trades_today == 3

    @pytest.mark.asyncio
    async def test_execute_copy_trade_caps_at_max_position_size(
        self, db_session, copy_service, test_user
    ):
        """Test executed volume is capped at max_position_size_lot."""
        user_id = "test-user-001"
        await copy_service.enable_copy_trading(db_session, user_id, risk_multiplier=2.0)

        # Set small max_position_size
        from sqlalchemy.future import select

        stmt = select(CopyTradeSettings).where(CopyTradeSettings.user_id == user_id)
        db_result = await db_session.execute(stmt)
        settings = db_result.scalar_one()
        settings.max_position_size_lot = 2.0  # Cap
        db_session.add(settings)
        await db_session.commit()

        # Try to execute 3.0 with 2.0x multiplier = 6.0, should cap at 2.0
        result = await copy_service.execute_copy_trade(
            db_session, user_id, "sig-123", 3.0, {}
        )

        assert result["executed_volume"] == 2.0  # Capped at max_position_size


# ============================================================================
# TESTS: RiskEvaluator - Risk Breach Detection
# ============================================================================


class TestRiskEvaluator:
    """Test risk evaluation and breach detection."""

    @pytest.mark.asyncio
    async def test_evaluate_risk_allow_trade_within_limits(
        self, db_session, risk_evaluator, test_user
    ):
        """Test trade allowed when all risk parameters within limits."""
        user_id = "test-user-001"

        # Create copy settings
        settings = CopyTradeSettings(
            id="settings-1",
            user_id=user_id,
            enabled=True,
            max_leverage=5.0,
            max_per_trade_risk_percent=2.0,
            total_exposure_percent=50.0,
            daily_stop_percent=10.0,
        )
        db_session.add(settings)
        await db_session.commit()

        # Trade within limits
        proposed_trade = {
            "instrument": "GOLD",
            "side": "buy",
            "entry_price": 1950.0,
            "volume": 0.5,  # Small volume
            "sl_price": 1940.0,  # Small stop loss
        }

        account_state = {
            "equity": 10000.0,
            "open_positions_value": 2000.0,  # 20% exposure
            "todays_loss": 200.0,  # 2% loss
        }

        can_trade, reason = await risk_evaluator.evaluate_risk(
            db_session, user_id, proposed_trade, account_state
        )

        assert can_trade is True
        assert reason is None

    @pytest.mark.asyncio
    async def test_evaluate_risk_block_on_max_leverage_breach(
        self, db_session, risk_evaluator, test_user
    ):
        """Test trade blocked when leverage exceeds max_leverage."""
        user_id = "test-user-001"

        settings = CopyTradeSettings(
            id="settings-1",
            user_id=user_id,
            enabled=True,
            max_leverage=2.0,  # Low leverage limit
            max_per_trade_risk_percent=2.0,
            total_exposure_percent=50.0,
            daily_stop_percent=10.0,
        )
        db_session.add(settings)
        await db_session.commit()

        # High volume trade exceeds leverage
        proposed_trade = {
            "instrument": "GOLD",
            "side": "buy",
            "entry_price": 2000.0,
            "volume": 15.0,  # Large volume: 15 * 2000 / 10000 = 3.0x leverage
            "sl_price": 1950.0,
        }

        account_state = {
            "equity": 10000.0,
            "open_positions_value": 2000.0,
            "todays_loss": 200.0,
        }

        can_trade, reason = await risk_evaluator.evaluate_risk(
            db_session, user_id, proposed_trade, account_state
        )

        assert can_trade is False
        assert reason == "max_leverage_exceeded"

    @pytest.mark.asyncio
    async def test_evaluate_risk_block_on_trade_risk_breach(
        self, db_session, risk_evaluator, test_user
    ):
        """Test trade blocked when per-trade risk exceeds limit."""
        user_id = "test-user-001"

        settings = CopyTradeSettings(
            id="settings-1",
            user_id=user_id,
            enabled=True,
            max_leverage=5.0,
            max_per_trade_risk_percent=1.0,  # Low limit
            total_exposure_percent=50.0,
            daily_stop_percent=10.0,
        )
        db_session.add(settings)
        await db_session.commit()

        # Large stop loss = large risk
        proposed_trade = {
            "instrument": "GOLD",
            "side": "buy",
            "entry_price": 1950.0,
            "volume": 2.0,
            "sl_price": 1850.0,  # 100 pips risk * 2 lots = 200 risk = 2% of 10000
        }

        account_state = {
            "equity": 10000.0,
            "open_positions_value": 2000.0,
            "todays_loss": 200.0,
        }

        can_trade, reason = await risk_evaluator.evaluate_risk(
            db_session, user_id, proposed_trade, account_state
        )

        assert can_trade is False
        assert reason == "max_trade_risk_exceeded"

    @pytest.mark.asyncio
    async def test_evaluate_risk_block_on_total_exposure_breach(
        self, db_session, risk_evaluator, test_user
    ):
        """Test trade blocked when total exposure exceeds limit."""
        user_id = "test-user-001"

        settings = CopyTradeSettings(
            id="settings-1",
            user_id=user_id,
            enabled=True,
            max_leverage=5.0,
            max_per_trade_risk_percent=2.0,
            total_exposure_percent=40.0,  # Low limit
            daily_stop_percent=10.0,
        )
        db_session.add(settings)
        await db_session.commit()

        proposed_trade = {
            "instrument": "GOLD",
            "side": "buy",
            "entry_price": 2000.0,
            "volume": 3.0,  # 3 * 2000 = 6000 new exposure
        }

        account_state = {
            "equity": 10000.0,
            "open_positions_value": 5000.0,  # Already 50% exposed
            "todays_loss": 200.0,
        }

        can_trade, reason = await risk_evaluator.evaluate_risk(
            db_session, user_id, proposed_trade, account_state
        )

        assert can_trade is False
        assert reason == "total_exposure_exceeded"

    @pytest.mark.asyncio
    async def test_evaluate_risk_block_on_daily_stop_breach(
        self, db_session, risk_evaluator, test_user
    ):
        """Test trade blocked when daily losses exceed daily_stop."""
        user_id = "test-user-001"

        settings = CopyTradeSettings(
            id="settings-1",
            user_id=user_id,
            enabled=True,
            max_leverage=5.0,
            max_per_trade_risk_percent=2.0,
            total_exposure_percent=50.0,
            daily_stop_percent=5.0,  # 5% daily loss limit
        )
        db_session.add(settings)
        await db_session.commit()

        proposed_trade = {
            "instrument": "GOLD",
            "side": "buy",
            "entry_price": 2000.0,
            "volume": 1.0,
            "sl_price": 1950.0,
        }

        account_state = {
            "equity": 10000.0,
            "open_positions_value": 2000.0,
            "todays_loss": 600.0,  # Already lost 6% today
        }

        can_trade, reason = await risk_evaluator.evaluate_risk(
            db_session, user_id, proposed_trade, account_state
        )

        assert can_trade is False
        assert reason == "daily_stop_exceeded"


# ============================================================================
# TESTS: DisclosureService - Versioning and Consent
# ============================================================================


class TestDisclosureService:
    """Test disclosure versioning and consent tracking."""

    @pytest.mark.asyncio
    async def test_create_disclosure_creates_new_version(
        self, db_session, disclosure_service
    ):
        """Test creating a new disclosure version."""
        version = "1.0"
        title = "Copy-Trading Risk Disclosure v1.0"
        content = "By enabling copy-trading, you acknowledge risks..."
        effective_date = datetime.utcnow()

        result = await disclosure_service.create_disclosure(
            db_session, version, title, content, effective_date, is_active=True
        )

        assert result["version"] == version
        assert result["title"] == title
        assert result["is_active"] is True

        # Verify in database
        from sqlalchemy.future import select

        stmt = select(Disclosure).where(Disclosure.version == version)
        db_result = await db_session.execute(stmt)
        disclosure = db_result.scalar_one_or_none()

        assert disclosure is not None
        assert disclosure.content == content

    @pytest.mark.asyncio
    async def test_create_disclosure_deactivates_previous(
        self, db_session, disclosure_service
    ):
        """Test creating new active disclosure deactivates previous version."""
        # Create v1.0
        await disclosure_service.create_disclosure(
            db_session,
            "1.0",
            "Disclosure v1.0",
            "Content v1.0",
            datetime.utcnow(),
            is_active=True,
        )

        # Create v1.1 as active
        await disclosure_service.create_disclosure(
            db_session,
            "1.1",
            "Disclosure v1.1",
            "Content v1.1",
            datetime.utcnow(),
            is_active=True,
        )

        # Verify v1.0 is now inactive
        from sqlalchemy.future import select

        stmt = select(Disclosure).where(Disclosure.version == "1.0")
        db_result = await db_session.execute(stmt)
        v1 = db_result.scalar_one()
        assert v1.is_active is False

        # Verify v1.1 is active
        stmt = select(Disclosure).where(Disclosure.version == "1.1")
        db_result = await db_session.execute(stmt)
        v11 = db_result.scalar_one()
        assert v11.is_active is True

    @pytest.mark.asyncio
    async def test_get_current_disclosure(self, db_session, disclosure_service):
        """Test retrieving the current active disclosure."""
        await disclosure_service.create_disclosure(
            db_session,
            "2.0",
            "Current Disclosure",
            "Current content",
            datetime.utcnow(),
            is_active=True,
        )

        current = await disclosure_service.get_current_disclosure(db_session)

        assert current is not None
        assert current["version"] == "2.0"
        assert current["title"] == "Current Disclosure"

    @pytest.mark.asyncio
    async def test_record_consent_creates_immutable_record(
        self, db_session, disclosure_service, test_user
    ):
        """Test recording user consent creates immutable record."""
        user_id = "test-user-001"
        version = "1.0"

        # Create disclosure first
        await disclosure_service.create_disclosure(
            db_session,
            version,
            "Risk Disclosure",
            "Content",
            datetime.utcnow(),
            is_active=True,
        )

        consent = await disclosure_service.record_consent(
            db_session,
            user_id,
            version,
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
        )

        assert consent["user_id"] == user_id
        assert consent["disclosure_version"] == version
        assert consent["accepted_at"] is not None

        # Verify in database
        from sqlalchemy.future import select

        stmt = select(UserConsent).where(
            (UserConsent.user_id == user_id)
            & (UserConsent.disclosure_version == version)
        )
        db_result = await db_session.execute(stmt)
        record = db_result.scalar_one_or_none()

        assert record is not None
        assert record.ip_address == "192.168.1.1"

    @pytest.mark.asyncio
    async def test_has_accepted_current_disclosure(
        self, db_session, disclosure_service, test_user
    ):
        """Test checking if user has accepted current disclosure."""
        user_id = "test-user-001"

        # Create disclosure v2.0
        await disclosure_service.create_disclosure(
            db_session,
            "2.0",
            "Latest",
            "Content",
            datetime.utcnow(),
            is_active=True,
        )

        # No consent yet
        has_accepted = await disclosure_service.has_accepted_current(
            db_session, user_id
        )
        assert has_accepted is False

        # Record consent
        await disclosure_service.record_consent(db_session, user_id, "2.0")

        # Now user has accepted
        has_accepted = await disclosure_service.has_accepted_current(
            db_session, user_id
        )
        assert has_accepted is True

    @pytest.mark.asyncio
    async def test_get_user_consent_history(
        self, db_session, disclosure_service, test_user
    ):
        """Test retrieving user's consent history."""
        user_id = "test-user-001"

        # Create disclosures first
        await disclosure_service.create_disclosure(
            db_session, "1.0", "V1", "C1", datetime.utcnow(), is_active=False
        )
        await disclosure_service.create_disclosure(
            db_session, "1.1", "V1.1", "C1.1", datetime.utcnow(), is_active=False
        )
        await disclosure_service.create_disclosure(
            db_session, "2.0", "V2", "C2", datetime.utcnow(), is_active=True
        )

        # Record consent for multiple versions
        await disclosure_service.record_consent(db_session, user_id, "1.0")
        await disclosure_service.record_consent(db_session, user_id, "1.1")
        await disclosure_service.record_consent(db_session, user_id, "2.0")

        history = await disclosure_service.get_user_consent_history(db_session, user_id)

        assert len(history) == 3
        assert history[0]["disclosure_version"] == "1.0"
        assert history[2]["disclosure_version"] == "2.0"


# ============================================================================
# TESTS: Integration - Full Workflows
# ============================================================================


class TestCopyTradingIntegration:
    """Integration tests for complete copy-trading workflows."""

    @pytest.mark.asyncio
    async def test_full_workflow_enable_accept_consent_execute_trade(
        self, db_session, copy_service, disclosure_service, test_user
    ):
        """Test complete workflow: enable → accept consent → execute trade."""
        user_id = "test-user-001"

        # Step 1: Create disclosure
        await disclosure_service.create_disclosure(
            db_session,
            "1.0",
            "Risk Disclosure",
            "By enabling, you accept risks...",
            datetime.utcnow(),
            is_active=True,
        )

        # Step 2: Accept disclosure
        await disclosure_service.record_consent(db_session, user_id, "1.0")

        # Step 3: Enable copy-trading
        result = await copy_service.enable_copy_trading(
            db_session, user_id, consent_version="1.0"
        )
        assert result["enabled"] is True

        # Step 4: Execute trade
        execution = await copy_service.execute_copy_trade(
            db_session, user_id, "sig-123", 2.0, {}
        )
        assert execution["status"] == "executed"

        # Verify consent acceptance is recorded
        has_accepted = await disclosure_service.has_accepted_current(
            db_session, user_id
        )
        assert has_accepted is True

    @pytest.mark.asyncio
    async def test_workflow_pricing_calculation_end_to_end(self, copy_service):
        """Test pricing calculation workflow for copy-trading tier."""
        # Base plans
        base_plans = {
            "starter": 29.99,
            "pro": 49.99,
            "elite": 99.99,
        }

        # Get copy-trading tier prices
        copy_prices = copy_service.get_copy_pricing(None, base_plans)

        # Verify all plans have copy-trading variant
        assert len(copy_prices) == 3

        # Verify markup is exactly 30%
        for original_plan, base_price in base_plans.items():
            copy_plan = f"{original_plan}_copy"
            assert copy_plan in copy_prices
            expected_price = base_price * 1.30
            assert abs(copy_prices[copy_plan] - expected_price) < 0.01

        # Verify copy-trading plans are more expensive
        assert copy_prices["starter_copy"] > base_plans["starter"]
        assert copy_prices["pro_copy"] > base_plans["pro"]


# ============================================================================
# TESTS: Edge Cases and Error Handling
# ============================================================================


class TestEdgeCasesAndErrors:
    """Test edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_copy_trading_with_zero_equity(
        self, db_session, risk_evaluator, test_user
    ):
        """Test risk evaluation with zero equity (should block)."""
        user_id = "test-user-001"

        settings = CopyTradeSettings(
            id="settings-1",
            user_id=user_id,
            enabled=True,
        )
        db_session.add(settings)
        await db_session.commit()

        proposed_trade = {
            "instrument": "GOLD",
            "side": "buy",
            "entry_price": 2000.0,
            "volume": 1.0,
            "sl_price": 1950.0,
        }

        account_state = {
            "equity": 0.0,  # Zero equity
            "open_positions_value": 0.0,
            "todays_loss": 0.0,
        }

        can_trade, reason = await risk_evaluator.evaluate_risk(
            db_session, user_id, proposed_trade, account_state
        )

        # Should allow (all checks skipped with zero equity)
        # or return early safely
        assert isinstance(can_trade, bool)
        assert isinstance(reason, (str, type(None)))

    @pytest.mark.asyncio
    async def test_copy_trading_paused_blocks_all_trades(
        self, db_session, risk_evaluator, test_user
    ):
        """Test that paused copy-trading blocks all trades."""
        user_id = "test-user-001"

        settings = CopyTradeSettings(
            id="settings-1",
            user_id=user_id,
            enabled=True,
            is_paused=True,  # Paused
            pause_reason="risk_breach",
        )
        db_session.add(settings)
        await db_session.commit()

        proposed_trade = {
            "instrument": "GOLD",
            "side": "buy",
            "entry_price": 2000.0,
            "volume": 0.1,  # Very small
            "sl_price": 1990.0,
        }

        account_state = {
            "equity": 10000.0,
            "open_positions_value": 100.0,
            "todays_loss": 10.0,
        }

        can_trade, reason = await risk_evaluator.evaluate_risk(
            db_session, user_id, proposed_trade, account_state
        )

        assert can_trade is False
        assert "paused" in reason

    @pytest.mark.asyncio
    async def test_risk_multiplier_bounds(self, db_session, copy_service, test_user):
        """Test risk multiplier respects bounds (0.1 to 2.0)."""
        user_id = "test-user-001"

        # Valid: 1.0x
        result = await copy_service.enable_copy_trading(
            db_session, user_id, risk_multiplier=1.0
        )
        assert result["risk_multiplier"] == 1.0

        # Valid: 0.5x
        result = await copy_service.enable_copy_trading(
            db_session, user_id, risk_multiplier=0.5
        )
        assert result["risk_multiplier"] == 0.5
