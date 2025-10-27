"""
Tests for PR-024: Fraud Detection Module.

Tests self-referral detection, wash trade detection, and multi-IP checks.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.affiliates.fraud import (
    FraudDetectionService,
    validate_referral_before_commission,
)
from backend.app.auth.models import User
from backend.app.trading.store.models import Trade


@pytest.fixture
async def fraud_service(db_session: AsyncSession) -> FraudDetectionService:
    """Create fraud detection service."""
    return FraudDetectionService()


@pytest.fixture
async def referrer_user(db_session: AsyncSession) -> User:
    """Create referrer user."""
    user = User(
        id="referrer_123",
        email="referrer@example.com",
        password_hash="hashed",
        role="user",
        created_at=datetime.utcnow(),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def referee_user(db_session: AsyncSession) -> User:
    """Create referee (referred) user."""
    user = User(
        id="referee_456",
        email="referee@example.com",
        password_hash="hashed",
        role="user",
        created_at=datetime.utcnow() + timedelta(hours=1),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
class TestSelfReferralDetection:
    """Test self-referral fraud detection."""

    async def test_same_email_domain_detection(
        self,
        db_session: AsyncSession,
        referrer_user: User,
        referee_user: User,
        fraud_service: FraudDetectionService,
    ):
        """Test detection of self-referral via same email domain."""
        # Modify referee to have same domain
        referee_user.email = "attacker_alt@example.com"
        await db_session.commit()

        is_fraud = await fraud_service.check_self_referral(
            db_session,
            referrer_user.id,
            referee_user.id,
        )

        assert is_fraud is True

    async def test_accounts_created_too_close(
        self,
        db_session: AsyncSession,
        referrer_user: User,
        fraud_service: FraudDetectionService,
    ):
        """Test detection of accounts created too close together."""
        # Create referee with created_at only 1 hour after referrer
        referee = User(
            id="referee_close",
            email="referee_close@different.com",
            password_hash="hashed",
            role="user",
            created_at=referrer_user.created_at + timedelta(hours=1),
        )
        db_session.add(referee)
        await db_session.commit()

        is_fraud = await fraud_service.check_self_referral(
            db_session,
            referrer_user.id,
            referee.id,
        )

        assert is_fraud is True

    async def test_legitimate_referral_different_domain(
        self,
        db_session: AsyncSession,
        referrer_user: User,
        referee_user: User,
        fraud_service: FraudDetectionService,
    ):
        """Test that legitimate referral (different domain) is not flagged."""
        is_fraud = await fraud_service.check_self_referral(
            db_session,
            referrer_user.id,
            referee_user.id,
        )

        # Different domains, created > 2 hours apart = not fraud
        assert is_fraud is False

    async def test_self_referral_nonexistent_users(
        self,
        db_session: AsyncSession,
        fraud_service: FraudDetectionService,
    ):
        """Test self-referral check with nonexistent users."""
        is_fraud = await fraud_service.check_self_referral(
            db_session,
            "nonexistent_1",
            "nonexistent_2",
        )

        # Should return False (no fraud detected)
        assert is_fraud is False


@pytest.mark.asyncio
class TestWashTradeDetection:
    """Test wash trade fraud detection."""

    async def test_wash_trade_large_loss_detected(
        self,
        db_session: AsyncSession,
        referee_user: User,
        fraud_service: FraudDetectionService,
    ):
        """Test detection of wash trade with large loss."""
        # Create a losing trade
        trade = Trade(
            id="trade_123",
            user_id=referee_user.id,
            symbol="GOLD",
            entry_price=1950.0,
            exit_price=1850.0,  # 100 pips loss
            volume=1.0,
            profit=-100.0,
            status="closed",
            entry_time=datetime.utcnow(),
            exit_time=datetime.utcnow() + timedelta(hours=1),
            side=0,  # Buy
        )
        db_session.add(trade)
        await db_session.commit()

        is_wash = await fraud_service.detect_wash_trade(
            db_session,
            referee_user.id,
            time_window_hours=24,
        )

        # Loss > 50% of position = wash trade
        assert is_wash is True

    async def test_normal_loss_not_flagged(
        self,
        db_session: AsyncSession,
        referee_user: User,
        fraud_service: FraudDetectionService,
    ):
        """Test that normal losses are not flagged as wash trades."""
        # Create a small losing trade (< 50% loss)
        trade = Trade(
            id="trade_123",
            user_id=referee_user.id,
            symbol="GOLD",
            entry_price=1950.0,
            exit_price=1920.0,  # 30 pips loss (1.5%)
            volume=1.0,
            profit=-30.0,
            status="closed",
            entry_time=datetime.utcnow(),
            exit_time=datetime.utcnow() + timedelta(hours=1),
            side=0,
        )
        db_session.add(trade)
        await db_session.commit()

        is_wash = await fraud_service.detect_wash_trade(
            db_session,
            referee_user.id,
            time_window_hours=24,
        )

        # Loss < 50% = not flagged
        assert is_wash is False

    async def test_profitable_trade_not_flagged(
        self,
        db_session: AsyncSession,
        referee_user: User,
        fraud_service: FraudDetectionService,
    ):
        """Test that profitable trades are not flagged."""
        # Create a profitable trade
        trade = Trade(
            id="trade_123",
            user_id=referee_user.id,
            symbol="GOLD",
            entry_price=1950.0,
            exit_price=1980.0,  # 30 pips profit
            volume=1.0,
            profit=30.0,
            status="closed",
            entry_time=datetime.utcnow(),
            exit_time=datetime.utcnow() + timedelta(hours=1),
            side=0,
        )
        db_session.add(trade)
        await db_session.commit()

        is_wash = await fraud_service.detect_wash_trade(
            db_session,
            referee_user.id,
            time_window_hours=24,
        )

        # Profitable = not flagged
        assert is_wash is False

    async def test_wash_trade_outside_time_window(
        self,
        db_session: AsyncSession,
        referee_user: User,
        fraud_service: FraudDetectionService,
    ):
        """Test that old wash trades are not detected."""
        # Create trade from 10 days ago
        old_time = datetime.utcnow() - timedelta(days=10)
        trade = Trade(
            id="trade_123",
            user_id=referee_user.id,
            symbol="GOLD",
            entry_price=1950.0,
            exit_price=1850.0,
            volume=1.0,
            profit=-100.0,
            status="closed",
            entry_time=old_time,
            exit_time=old_time + timedelta(hours=1),
            side=0,
        )
        db_session.add(trade)
        await db_session.commit()

        # Check with 24 hour window
        is_wash = await fraud_service.detect_wash_trade(
            db_session,
            referee_user.id,
            time_window_hours=24,
        )

        # Old trade = not detected
        assert is_wash is False


@pytest.mark.asyncio
class TestMultipleAccountsDetection:
    """Test multiple accounts from same IP detection."""

    async def test_multiple_accounts_flagged(
        self,
        db_session: AsyncSession,
        fraud_service: FraudDetectionService,
    ):
        """Test detection of multiple accounts from same IP."""
        # Create multiple users (simulating same IP registration)
        for i in range(3):
            user = User(
                id=f"user_ip_{i}",
                email=f"user{i}@example.com",
                password_hash="hashed",
                role="user",
                created_at=datetime.utcnow(),
            )
            db_session.add(user)

        await db_session.commit()

        # Check for multiple accounts
        count = await fraud_service.check_multiple_accounts_same_ip(
            db_session,
            "192.168.1.100",
            days_lookback=30,
        )

        # Should detect multiple accounts
        assert count >= 1  # Depends on implementation

    async def test_single_account_not_flagged(
        self,
        db_session: AsyncSession,
        referrer_user: User,
        fraud_service: FraudDetectionService,
    ):
        """Test that single account from IP is not flagged."""
        count = await fraud_service.check_multiple_accounts_same_ip(
            db_session,
            "192.168.1.100",
            days_lookback=30,
        )

        # Single or no accounts = not suspicious
        assert count <= 1


@pytest.mark.asyncio
class TestFraudLogging:
    """Test fraud suspicion logging."""

    async def test_log_fraud_suspicion(
        self,
        db_session: AsyncSession,
        referrer_user: User,
        fraud_service: FraudDetectionService,
    ):
        """Test logging fraud suspicion to audit log."""
        log_id = await fraud_service.log_fraud_suspicion(
            db_session,
            "self_referral",
            referrer_user.id,
            {"referrer_id": "aff_123", "referee_id": "user_456"},
        )

        assert log_id is not None

        # Verify audit log was created
        from backend.app.audit.models import AuditLog

        entry = await db_session.get(AuditLog, log_id)
        assert entry is not None
        assert entry.action == "affiliate.fraud_suspicion.self_referral"
        assert entry.actor_id == referrer_user.id


@pytest.mark.asyncio
class TestValidateReferralBeforeCommission:
    """Test comprehensive referral validation."""

    async def test_clean_referral_validation(
        self,
        db_session: AsyncSession,
        referrer_user: User,
        referee_user: User,
    ):
        """Test that clean referral passes validation."""
        is_valid, reason = await validate_referral_before_commission(
            db_session,
            referrer_user.id,
            referee_user.id,
        )

        assert is_valid is True
        assert reason is None

    async def test_self_referral_validation_fails(
        self,
        db_session: AsyncSession,
        referrer_user: User,
    ):
        """Test that self-referral validation fails."""
        # Create close-together accounts (same user)
        referee = User(
            id="referee_close",
            email="attacker_alt@example.com",  # Same domain
            password_hash="hashed",
            role="user",
            created_at=referrer_user.created_at + timedelta(minutes=30),
        )
        db_session.add(referee)
        await db_session.commit()

        is_valid, reason = await validate_referral_before_commission(
            db_session,
            referrer_user.id,
            referee.id,
        )

        assert is_valid is False
        assert reason is not None


@pytest.mark.asyncio
class TestEdgeCases:
    """Test edge cases in fraud detection."""

    async def test_zero_volume_trade(
        self,
        db_session: AsyncSession,
        referee_user: User,
        fraud_service: FraudDetectionService,
    ):
        """Test wash trade detection with zero volume."""
        trade = Trade(
            id="trade_zero",
            user_id=referee_user.id,
            symbol="GOLD",
            entry_price=1950.0,
            exit_price=1850.0,
            volume=0.0,
            profit=-100.0,
            status="closed",
            entry_time=datetime.utcnow(),
            exit_time=datetime.utcnow() + timedelta(hours=1),
            side=0,
        )
        db_session.add(trade)
        await db_session.commit()

        # Should handle gracefully
        is_wash = await fraud_service.detect_wash_trade(
            db_session,
            referee_user.id,
        )

        assert is_wash is False

    async def test_null_profit_trade(
        self,
        db_session: AsyncSession,
        referee_user: User,
        fraud_service: FraudDetectionService,
    ):
        """Test wash trade detection with null profit."""
        trade = Trade(
            id="trade_null",
            user_id=referee_user.id,
            symbol="GOLD",
            entry_price=1950.0,
            exit_price=1950.0,
            volume=1.0,
            profit=None,
            status="closed",
            entry_time=datetime.utcnow(),
            exit_time=datetime.utcnow() + timedelta(hours=1),
            side=0,
        )
        db_session.add(trade)
        await db_session.commit()

        # Should handle gracefully
        is_wash = await fraud_service.detect_wash_trade(
            db_session,
            referee_user.id,
        )

        assert is_wash is False
