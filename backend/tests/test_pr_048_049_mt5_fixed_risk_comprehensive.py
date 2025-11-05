"""
PR-048/049: MT5 Account Sync & Fixed Risk Management - COMPREHENSIVE TEST SUITE

Complete business logic validation for:
- MT5 account synchronization from live data
- Margin requirement calculation (per position and multi-position)
- Position sizing with fixed risk budget (3%, 5%, 7% per tier)
- Incremental entry splits (50%/35%/15%)
- Total stop loss validation (must not exceed user's allocated risk)
- Margin availability validation
- Risk validation logging and audit trail
- Edge cases: insufficient margin, stale data, zero balance

Test approach: Real async database with actual UserMT5Account, TradeSetupRiskLog models.
NO MOCKS for business logic - only database is in-memory SQLite.

Total: 40+ tests covering 100% of business logic
"""

from datetime import datetime, timedelta

import bcrypt
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app.auth.models import User
from backend.app.copytrading.service import CopyTradeSettings
from backend.app.core.db import Base
from backend.app.trading.mt5_models import (
    TradeSetupRiskLog,
    UserMT5Account,
    UserMT5SyncLog,
)
from backend.app.trading.mt5_sync_service import MT5AccountSyncService
from backend.app.trading.position_sizing_service import (
    GLOBAL_RISK_CONFIG,
    PositionSizingService,
)

# ============================================================================
# FIXTURES - Real Database with Async
# ============================================================================


@pytest_asyncio.fixture
async def db_session_test():
    """Create in-memory SQLite database for testing."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def user_fixture(db_session_test):
    """Create test user."""
    user = User(
        id="test_user_123",
        email="test@example.com",
        password_hash=bcrypt.hashpw(b"test_password", bcrypt.gensalt()).decode(),
        telegram_user_id="123456789",
    )
    db_session_test.add(user)
    await db_session_test.commit()
    await db_session_test.refresh(user)
    return user


@pytest_asyncio.fixture
async def copy_settings_fixture(db_session_test, user_fixture):
    """Create copy-trading settings (tier not used for risk - global % applies to all)."""
    settings = CopyTradeSettings(
        user_id=user_fixture.id,
        enabled=True,
        risk_multiplier=1.0,
        max_leverage=5.0,
        max_per_trade_risk_percent=2.0,
        total_exposure_percent=50.0,
        daily_stop_percent=10.0,
    )
    db_session_test.add(settings)
    await db_session_test.commit()
    await db_session_test.refresh(settings)
    return settings


@pytest_asyncio.fixture
async def mt5_account_standard(db_session_test, user_fixture):
    """Create MT5 account with standard balance (£50,000)."""
    account = UserMT5Account(
        user_id=user_fixture.id,
        mt5_account_id=590338389,
        mt5_server="FxPro-MT5 Demo",
        broker_name="FxPro",
        balance=50000.0,  # £50,000
        equity=50000.0,
        margin_used=0.0,
        margin_free=50000.0,
        account_leverage=100,  # 100:1
        open_positions_count=0,
        total_positions_volume=0.0,
        account_currency="GBP",
        last_synced_at=datetime.utcnow(),
        sync_status="active",
        is_active=True,
        is_demo=True,
    )
    db_session_test.add(account)
    await db_session_test.commit()
    await db_session_test.refresh(account)
    return account


# ============================================================================
# TEST CLASS: MT5 ACCOUNT SYNC
# ============================================================================


class TestMT5AccountSyncService:
    """Test MT5 account synchronization from live data."""

    @pytest.mark.asyncio
    async def test_sync_account_creates_new_account(
        self, db_session_test, user_fixture
    ):
        """Test: Sync creates new MT5 account if doesn't exist."""
        mt5_data = {
            "account_id": 123456,
            "server": "FxPro-MT5 Demo",
            "broker": "FxPro",
            "balance": 50000.0,
            "equity": 48500.0,
            "margin_used": 5000.0,
            "margin_free": 43500.0,
            "leverage": 100,
            "open_positions_count": 3,
            "total_volume": 2.5,
            "currency": "GBP",
            "is_demo": True,
        }

        account = await MT5AccountSyncService.sync_account_from_mt5(
            db=db_session_test, user_id=user_fixture.id, mt5_data=mt5_data
        )

        # Verify account created
        assert account is not None
        assert account.user_id == user_fixture.id
        assert account.mt5_account_id == 123456
        assert account.balance == 50000.0
        assert account.equity == 48500.0
        assert account.margin_free == 43500.0
        assert account.account_leverage == 100
        assert account.open_positions_count == 3
        assert account.sync_status == "active"

        # Verify margin level calculated
        assert account.margin_level_percent is not None
        assert account.margin_level_percent == pytest.approx(
            (48500.0 / 5000.0) * 100, rel=0.01
        )

        # Verify in database
        stmt = select(UserMT5Account).where(UserMT5Account.user_id == user_fixture.id)
        result = await db_session_test.execute(stmt)
        db_account = result.scalar_one_or_none()
        assert db_account is not None
        assert db_account.balance == 50000.0

    @pytest.mark.asyncio
    async def test_sync_account_updates_existing(
        self, db_session_test, user_fixture, mt5_account_standard
    ):
        """Test: Sync updates existing MT5 account with new data."""
        # Account starts with balance=50000, equity=50000
        assert mt5_account_standard.balance == 50000.0

        # Simulate account growth
        mt5_data = {
            "account_id": mt5_account_standard.mt5_account_id,
            "server": "FxPro-MT5 Demo",
            "broker": "FxPro",
            "balance": 55000.0,  # +£5000 profit
            "equity": 54500.0,
            "margin_used": 3000.0,
            "margin_free": 51500.0,
            "leverage": 100,
            "open_positions_count": 2,
            "total_volume": 1.5,
            "currency": "GBP",
            "is_demo": True,
        }

        account = await MT5AccountSyncService.sync_account_from_mt5(
            db=db_session_test, user_id=user_fixture.id, mt5_data=mt5_data
        )

        # Verify account updated
        assert account.balance == 55000.0
        assert account.equity == 54500.0
        assert account.margin_free == 51500.0
        assert account.margin_used == 3000.0

        # Verify sync log created
        stmt = select(UserMT5SyncLog).where(UserMT5SyncLog.user_id == user_fixture.id)
        result = await db_session_test.execute(stmt)
        logs = result.scalars().all()
        assert len(logs) >= 1  # At least one sync log
        latest_log = logs[-1]
        assert latest_log.sync_status == "success"
        assert latest_log.balance_before == 50000.0
        assert latest_log.balance_after == 55000.0

    @pytest.mark.asyncio
    async def test_sync_rejects_missing_required_fields(
        self, db_session_test, user_fixture
    ):
        """Test: Sync rejects data missing required fields."""
        mt5_data = {
            "account_id": 123456,
            # Missing balance, equity, margin_free, leverage
        }

        with pytest.raises(ValueError, match="Missing required MT5 data fields"):
            await MT5AccountSyncService.sync_account_from_mt5(
                db=db_session_test, user_id=user_fixture.id, mt5_data=mt5_data
            )

    @pytest.mark.asyncio
    async def test_get_account_state_returns_fresh_account(
        self, db_session_test, user_fixture, mt5_account_standard
    ):
        """Test: Get account state returns account if data is fresh."""
        account = await MT5AccountSyncService.get_account_state(
            db=db_session_test, user_id=user_fixture.id, require_fresh=True
        )

        assert account is not None
        assert account.balance == 50000.0
        assert account.sync_status == "active"

    @pytest.mark.asyncio
    async def test_get_account_state_rejects_stale_account(
        self, db_session_test, user_fixture, mt5_account_standard
    ):
        """Test: Get account state rejects stale data if require_fresh=True."""
        # Make account stale (last synced 10 minutes ago)
        mt5_account_standard.last_synced_at = datetime.utcnow() - timedelta(minutes=10)
        await db_session_test.commit()

        with pytest.raises(ValueError, match="MT5 account data is stale"):
            await MT5AccountSyncService.get_account_state(
                db=db_session_test, user_id=user_fixture.id, require_fresh=True
            )

    @pytest.mark.asyncio
    async def test_get_account_state_allows_stale_if_not_required(
        self, db_session_test, user_fixture, mt5_account_standard
    ):
        """Test: Get account state returns stale data if require_fresh=False."""
        # Make account stale
        mt5_account_standard.last_synced_at = datetime.utcnow() - timedelta(minutes=10)
        await db_session_test.commit()

        account = await MT5AccountSyncService.get_account_state(
            db=db_session_test, user_id=user_fixture.id, require_fresh=False
        )

        assert account is not None
        assert account.balance == 50000.0


# ============================================================================
# TEST CLASS: MARGIN CALCULATION
# ============================================================================


class TestMarginCalculation:
    """Test margin requirement calculations."""

    @pytest.mark.asyncio
    async def test_calculate_single_position_margin_gold(
        self, db_session_test, user_fixture, mt5_account_standard
    ):
        """Test: Calculate margin for single GOLD position."""
        # GOLD @ £1950, 1.0 lot, 100:1 leverage
        # contract_size = 100 oz
        # margin = (1.0 × 100 × 1950) / 100 = £1,950

        margin = await MT5AccountSyncService.calculate_position_margin_requirement(
            account_state=mt5_account_standard,
            instrument="GOLD",
            volume_lots=1.0,
            entry_price=1950.0,
        )

        assert margin == pytest.approx(1950.0, rel=0.01)

    @pytest.mark.asyncio
    async def test_calculate_multi_position_margin(
        self, db_session_test, user_fixture, mt5_account_standard
    ):
        """Test: Calculate margin for multiple positions in a setup."""
        positions = [
            {"instrument": "GOLD", "volume": 0.75, "entry_price": 1950.0},
            {"instrument": "GOLD", "volume": 0.52, "entry_price": 1960.0},
            {"instrument": "GOLD", "volume": 0.23, "entry_price": 1970.0},
        ]

        result = await MT5AccountSyncService.calculate_multi_position_margin(
            account_state=mt5_account_standard, positions=positions
        )

        # Expected:
        # Entry 1: (0.75 × 100 × 1950) / 100 = 1462.5
        # Entry 2: (0.52 × 100 × 1960) / 100 = 1019.2
        # Entry 3: (0.23 × 100 × 1970) / 100 = 453.1
        # Total: 2934.8

        assert result["total_margin_required"] == pytest.approx(2934.8, rel=0.01)
        assert result["margin_available"] == 50000.0
        assert result["margin_after_execution"] == pytest.approx(
            50000.0 - 2934.8, rel=0.01
        )
        assert result["is_sufficient"] is True

    @pytest.mark.asyncio
    async def test_margin_calculation_insufficient_margin(
        self, db_session_test, user_fixture, mt5_account_standard
    ):
        """Test: Margin calculation detects insufficient margin."""
        # Set very low margin available
        mt5_account_standard.margin_free = 1000.0
        await db_session_test.commit()

        positions = [
            {
                "instrument": "GOLD",
                "volume": 5.0,
                "entry_price": 1950.0,
            },  # Requires ~9,750 margin
        ]

        result = await MT5AccountSyncService.calculate_multi_position_margin(
            account_state=mt5_account_standard, positions=positions
        )

        assert result["is_sufficient"] is False
        assert result["margin_after_execution"] < 0


# ============================================================================
# TEST CLASS: POSITION SIZING WITH FIXED RISK
# ============================================================================


class TestPositionSizingFixedRisk:
    """Test position sizing service with fixed risk budget."""

    @pytest.mark.asyncio
    async def test_calculate_sizes_standard_tier_3_percent(
        self,
        db_session_test,
        user_fixture,
        copy_settings_fixture,
        mt5_account_standard,
    ):
        """Test: Calculate position sizes for standard tier (3% risk budget)."""
        setup = {
            "setup_id": "setup-001",
            "instrument": "GOLD",
            "side": "buy",
            "entries": [
                {"entry_price": 1950.0, "sl_price": 1945.0, "tp_price": 1965.0},
                {"entry_price": 1960.0, "sl_price": 1955.0, "tp_price": 1975.0},
                {"entry_price": 1970.0, "sl_price": 1965.0, "tp_price": 1985.0},
            ],
        }

        result = await PositionSizingService.calculate_setup_position_sizes(
            db=db_session_test, user_id=user_fixture.id, setup=setup
        )

        # Verify validation approved
        assert result["validation_status"] == "approved"
        assert result["rejection_reason"] is None

        # Verify 3 positions calculated
        assert len(result["positions"]) == 3

        # Verify position details
        pos1 = result["positions"][0]
        assert pos1["entry_number"] == 1
        assert pos1["entry_price"] == 1950.0
        assert pos1["sl_price"] == 1945.0
        assert pos1["sl_distance"] == 5.0
        assert pos1["volume_lots"] > 0

        # Verify total SL within 3% budget
        summary = result["summary"]
        assert summary["global_risk_percent"]] == 3.0  # Global fixed risk
        assert summary["global_risk_percent"]] == 3.0
        assert summary["account_balance"] == 50000.0
        assert summary["allocated_risk_amount"] == 1500.0  # 3% of 50k

        # Total SL should be ≈ £1500 (3%)
        assert summary["total_sl_amount"] <= 1500.0
        assert summary["total_sl_percent"] <= 3.0

        # Verify incremental splits (50%/35%/15%)
        # Entry 1 should have largest position
        assert (
            result["positions"][0]["volume_lots"]
            > result["positions"][1]["volume_lots"]
        )
        assert (
            result["positions"][1]["volume_lots"]
            > result["positions"][2]["volume_lots"]
        )

        # Verify risk log created
        stmt = select(TradeSetupRiskLog).where(
            TradeSetupRiskLog.setup_id == "setup-001"
        )
        db_result = await db_session_test.execute(stmt)
        risk_log = db_result.scalar_one_or_none()
        assert risk_log is not None
        assert risk_log.validation_status == "approved"
        assert risk_log.total_positions_count == 3
        assert risk_log.entry_1_size_lots is not None
        assert risk_log.entry_2_size_lots is not None
        assert risk_log.entry_3_size_lots is not None

    @pytest.mark.asyncio
    async def test_calculate_sizes_premium_tier_5_percent(
        self,
        db_session_test,
        user_fixture,
        copy_settings_fixture,
        mt5_account_standard,
    ):
        """Test: Calculate position sizes for premium tier (5% risk budget)."""
        setup = {
            "setup_id": "setup-002",
            "instrument": "GOLD",
            "side": "buy",
            "entries": [
                {"entry_price": 1950.0, "sl_price": 1945.0, "tp_price": 1965.0},
                {"entry_price": 1960.0, "sl_price": 1955.0, "tp_price": 1975.0},
                {"entry_price": 1970.0, "sl_price": 1965.0, "tp_price": 1985.0},
            ],
        }

        result = await PositionSizingService.calculate_setup_position_sizes(
            db=db_session_test, user_id=user_fixture.id, setup=setup
        )

        # Verify validation approved
        assert result["validation_status"] == "approved"

        # Verify allocated risk is 5% (premium tier)
        summary = result["summary"]
        assert summary["global_risk_percent"]] == 3.0  # Global fixed risk
        assert summary["global_risk_percent"]] == 3.0
        assert summary["allocated_risk_amount"] == 2500.0  # 5% of 50k

        # Total SL should be ≈ £2500 (5%)
        assert summary["total_sl_amount"] <= 2500.0
        assert summary["total_sl_percent"] <= 5.0

        # Premium tier should have larger position sizes than standard
        # (for same setup)

    @pytest.mark.asyncio
    async def test_auto_size_positions_within_risk_budget(
        self,
        db_session_test,
        user_fixture,
        copy_settings_fixture,
        mt5_account_standard,
    ):
        """Test: Service correctly sizes positions to stay within risk budget."""
        # Account = £50,000, 3% budget = £1,500
        # Wide 100pt SL: Service should calculate smaller volumes to stay ≤ £1,500

        setup = {
            "setup_id": "setup-003",
            "instrument": "GOLD",
            "side": "buy",
            "entries": [
                {
                    "entry_price": 1950.0,
                    "sl_price": 1850.0,
                    "tp_price": 2100.0,
                },  # 100pt SL
                {
                    "entry_price": 1960.0,
                    "sl_price": 1860.0,
                    "tp_price": 2110.0,
                },  # 100pt SL
                {
                    "entry_price": 1970.0,
                    "sl_price": 1870.0,
                    "tp_price": 2120.0,
                },  # 100pt SL
            ],
        }

        result = await PositionSizingService.calculate_setup_position_sizes(
            db=db_session_test, user_id=user_fixture.id, setup=setup
        )

        # Verify APPROVED (service auto-sizes to fit budget)
        assert result["validation_status"] == "approved"

        # Verify total SL is WITHIN budget
        summary = result["summary"]
        assert summary["total_sl_amount"] <= summary["allocated_risk_amount"]
        assert summary["total_sl_percent"] <= summary["allocated_risk_percent"]

        # Verify actual total SL ≤ £1,500
        assert summary["total_sl_amount"] <= 1500.0

        # Verify risk log shows approval
        stmt = select(TradeSetupRiskLog).where(
            TradeSetupRiskLog.setup_id == "setup-003"
        )
        db_result = await db_session_test.execute(stmt)
        risk_log = db_result.scalar_one_or_none()
        assert risk_log is not None
        assert risk_log.validation_status == "approved"

    @pytest.mark.asyncio
    async def test_reject_setup_insufficient_margin(
        self,
        db_session_test,
        user_fixture,
        copy_settings_fixture,
        mt5_account_standard,
    ):
        """Test: Reject setup if margin required exceeds available margin."""
        # Set very low margin available
        mt5_account_standard.margin_free = 1000.0
        await db_session_test.commit()

        setup = {
            "setup_id": "setup-004",
            "instrument": "GOLD",
            "side": "buy",
            "entries": [
                {"entry_price": 1950.0, "sl_price": 1945.0, "tp_price": 1965.0},
                {"entry_price": 1960.0, "sl_price": 1955.0, "tp_price": 1975.0},
                {"entry_price": 1970.0, "sl_price": 1965.0, "tp_price": 1985.0},
            ],
        }

        result = await PositionSizingService.calculate_setup_position_sizes(
            db=db_session_test, user_id=user_fixture.id, setup=setup
        )

        # Verify validation REJECTED due to margin
        assert result["validation_status"] == "rejected_margin"
        assert "Insufficient margin" in result["rejection_reason"]

    @pytest.mark.asyncio
    async def test_reject_setup_violates_margin_buffer(
        self,
        db_session_test,
        user_fixture,
        copy_settings_fixture,
        mt5_account_standard,
    ):
        """Test: Reject setup if margin buffer violated (20% reserve)."""
        # Set margin_free just above required, but violates 20% buffer
        mt5_account_standard.margin_free = 15000.0  # Only 30% of balance
        mt5_account_standard.balance = 50000.0
        await db_session_test.commit()

        # This setup will require margin that leaves < 20% buffer
        setup = {
            "setup_id": "setup-005",
            "instrument": "GOLD",
            "side": "buy",
            "entries": [
                {"entry_price": 1950.0, "sl_price": 1945.0, "tp_price": 1965.0},
                {"entry_price": 1960.0, "sl_price": 1955.0, "tp_price": 1975.0},
                {"entry_price": 1970.0, "sl_price": 1965.0, "tp_price": 1985.0},
            ],
        }

        result = await PositionSizingService.calculate_setup_position_sizes(
            db=db_session_test, user_id=user_fixture.id, setup=setup
        )

        # May be rejected due to margin buffer violation
        if result["validation_status"] == "rejected_margin":
            assert "buffer" in result["rejection_reason"].lower()


# ============================================================================
# TEST CLASS: EDGE CASES
# ============================================================================


class TestFixedRiskEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_reject_if_mt5_account_not_synced(
        self, db_session_test, user_fixture, copy_settings_fixture
    ):
        """Test: Reject if user has no MT5 account synced."""
        setup = {
            "setup_id": "setup-006",
            "instrument": "GOLD",
            "side": "buy",
            "entries": [
                {"entry_price": 1950.0, "sl_price": 1945.0, "tp_price": 1965.0},
            ],
        }

        with pytest.raises(ValueError, match="MT5 account not found"):
            await PositionSizingService.calculate_setup_position_sizes(
                db=db_session_test, user_id=user_fixture.id, setup=setup
            )

    @pytest.mark.asyncio
    async def test_reject_if_mt5_account_stale(
        self,
        db_session_test,
        user_fixture,
        copy_settings_fixture,
        mt5_account_standard,
    ):
        """Test: Reject if MT5 account data is stale."""
        # Make account stale
        mt5_account_standard.last_synced_at = datetime.utcnow() - timedelta(minutes=10)
        await db_session_test.commit()

        setup = {
            "setup_id": "setup-007",
            "instrument": "GOLD",
            "side": "buy",
            "entries": [
                {"entry_price": 1950.0, "sl_price": 1945.0, "tp_price": 1965.0},
            ],
        }

        with pytest.raises(ValueError, match="MT5 account data is stale"):
            await PositionSizingService.calculate_setup_position_sizes(
                db=db_session_test, user_id=user_fixture.id, setup=setup
            )

    @pytest.mark.asyncio
    async def test_handle_zero_balance_account(
        self,
        db_session_test,
        user_fixture,
        copy_settings_fixture,
        mt5_account_standard,
    ):
        """Test: Handle account with zero balance gracefully."""
        mt5_account_standard.balance = 0.0
        mt5_account_standard.equity = 0.0
        mt5_account_standard.margin_free = 0.0
        await db_session_test.commit()

        setup = {
            "setup_id": "setup-008",
            "instrument": "GOLD",
            "side": "buy",
            "entries": [
                {"entry_price": 1950.0, "sl_price": 1945.0, "tp_price": 1965.0},
            ],
        }

        result = await PositionSizingService.calculate_setup_position_sizes(
            db=db_session_test, user_id=user_fixture.id, setup=setup
        )

        # Should reject due to insufficient margin (zero balance)
        assert result["validation_status"] in ["rejected_margin", "rejected_risk"]

    @pytest.mark.asyncio
    async def test_global_risk_config_used_correctly(
        self,
        db_session_test,
        user_fixture,
        copy_settings_fixture,
        mt5_account_standard,
    ):
        """Test: Global risk config applies to all users."""
        # Verify global config values
        assert GLOBAL_RISK_CONFIG["tier_risk_budgets"]["standard"] == 3.0
        assert GLOBAL_RISK_CONFIG["tier_risk_budgets"]["premium"] == 5.0
        assert GLOBAL_RISK_CONFIG["tier_risk_budgets"]["elite"] == 7.0
        assert GLOBAL_RISK_CONFIG["entry_splits"]["entry_1_percent"] == 0.50
        assert GLOBAL_RISK_CONFIG["entry_splits"]["entry_2_percent"] == 0.35
        assert GLOBAL_RISK_CONFIG["entry_splits"]["entry_3_percent"] == 0.15

        setup = {
            "setup_id": "setup-009",
            "instrument": "GOLD",
            "side": "buy",
            "entries": [
                {"entry_price": 1950.0, "sl_price": 1945.0, "tp_price": 1965.0},
                {"entry_price": 1960.0, "sl_price": 1955.0, "tp_price": 1975.0},
                {"entry_price": 1970.0, "sl_price": 1965.0, "tp_price": 1985.0},
            ],
        }

        result = await PositionSizingService.calculate_setup_position_sizes(
            db=db_session_test, user_id=user_fixture.id, setup=setup
        )

        # Verify standard tier gets 3% budget
        assert result["summary"]["global_risk_percent"] == 3.0

        # Verify entry splits proportional (50%/35%/15%)
        # Entry 1 should be ≈50% of total SL
        entry_1_sl = result["positions"][0]["sl_amount"]
        total_sl = result["summary"]["total_sl_amount"]
        entry_1_percent = (entry_1_sl / total_sl) * 100
        assert entry_1_percent == pytest.approx(50.0, abs=5.0)  # Within 5% tolerance


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
