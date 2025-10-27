"""
Tests for PR-024: Affiliate & Referral System.

Tests affiliate registration, referral tracking, commission calculation, and payouts.
Covers both happy path and edge cases.
"""

from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.affiliates.service import AffiliateService
from backend.app.auth.models import User


@pytest.fixture
async def affiliate_service(db_session: AsyncSession) -> AffiliateService:
    """Create affiliate service instance."""
    return AffiliateService(db_session)


@pytest.fixture
async def test_affiliate(db_session: AsyncSession) -> User:
    """Create test affiliate user."""
    user = User(
        id="affiliate_123",
        email="affiliate@example.com",
        password_hash="hashed",
        role="user",
        created_at=datetime.utcnow(),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def test_referred_user(db_session: AsyncSession) -> User:
    """Create test referred user."""
    user = User(
        id="user_456",
        email="referred@example.com",
        password_hash="hashed",
        role="user",
        created_at=datetime.utcnow(),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
class TestAffiliateRegistration:
    """Test affiliate registration and link generation."""

    async def test_register_affiliate_success(
        self,
        db_session: AsyncSession,
        test_affiliate: User,
        affiliate_service: AffiliateService,
    ):
        """Test successful affiliate registration."""
        # Register user as affiliate
        affiliate = await affiliate_service.register_affiliate(test_affiliate.id)

        assert affiliate is not None
        assert affiliate.user_id == test_affiliate.id
        assert affiliate.referral_code is not None
        assert len(affiliate.referral_code) > 0
        assert affiliate.tier == "standard"
        assert affiliate.created_at is not None

    async def test_generate_referral_link(
        self,
        db_session: AsyncSession,
        test_affiliate: User,
        affiliate_service: AffiliateService,
    ):
        """Test referral link generation."""
        affiliate = await affiliate_service.register_affiliate(test_affiliate.id)

        # Generate link
        link = await affiliate_service.generate_referral_link(affiliate.id)

        assert link is not None
        assert "ref=" in link
        assert affiliate.referral_code in link

    async def test_register_affiliate_duplicate(
        self,
        db_session: AsyncSession,
        test_affiliate: User,
        affiliate_service: AffiliateService,
    ):
        """Test registering same user twice returns existing."""
        affiliate1 = await affiliate_service.register_affiliate(test_affiliate.id)
        affiliate2 = await affiliate_service.register_affiliate(test_affiliate.id)

        assert affiliate1.id == affiliate2.id
        assert affiliate1.referral_code == affiliate2.referral_code

    async def test_affiliate_unique_code(
        self,
        db_session: AsyncSession,
        test_affiliate: User,
        affiliate_service: AffiliateService,
    ):
        """Test that different affiliates get different codes."""
        aff1 = await affiliate_service.register_affiliate("user_1")
        aff2 = await affiliate_service.register_affiliate("user_2")

        assert aff1.referral_code != aff2.referral_code


@pytest.mark.asyncio
class TestReferralTracking:
    """Test referral event tracking."""

    async def test_track_signup_event(
        self,
        db_session: AsyncSession,
        test_affiliate: User,
        test_referred_user: User,
        affiliate_service: AffiliateService,
    ):
        """Test tracking signup event."""
        affiliate = await affiliate_service.register_affiliate(test_affiliate.id)

        # Track signup
        event = await affiliate_service.track_signup(
            referral_code=affiliate.referral_code,
            new_user_id=test_referred_user.id,
        )

        assert event is not None
        assert event.referral_code == affiliate.referral_code
        assert event.event_type == "signup"
        assert event.user_id == test_referred_user.id

    async def test_track_subscription_created(
        self,
        db_session: AsyncSession,
        test_affiliate: User,
        test_referred_user: User,
        affiliate_service: AffiliateService,
    ):
        """Test tracking subscription creation."""
        affiliate = await affiliate_service.register_affiliate(test_affiliate.id)
        await affiliate_service.track_signup(
            affiliate.referral_code,
            test_referred_user.id,
        )

        # Track subscription
        event = await affiliate_service.track_subscription(
            referral_code=affiliate.referral_code,
            user_id=test_referred_user.id,
            subscription_price=99.99,
        )

        assert event is not None
        assert event.event_type == "subscription_created"
        assert event.meta.get("subscription_price") == 99.99

    async def test_track_first_trade(
        self,
        db_session: AsyncSession,
        test_affiliate: User,
        test_referred_user: User,
        affiliate_service: AffiliateService,
    ):
        """Test tracking first trade."""
        affiliate = await affiliate_service.register_affiliate(test_affiliate.id)
        await affiliate_service.track_signup(
            affiliate.referral_code,
            test_referred_user.id,
        )

        # Track first trade
        event = await affiliate_service.track_first_trade(
            referral_code=affiliate.referral_code,
            user_id=test_referred_user.id,
        )

        assert event is not None
        assert event.event_type == "first_trade"


@pytest.mark.asyncio
class TestCommissionCalculation:
    """Test commission calculation logic."""

    async def test_commission_tier1_first_month(
        self,
        db_session: AsyncSession,
        affiliate_service: AffiliateService,
    ):
        """Test tier 1 commission (30%) for first month."""
        subscription_price = 100.0

        # First month commission = 30%
        commission = await affiliate_service.calculate_commission(
            subscription_price=subscription_price,
            month=1,
        )

        assert commission == 30.0

    async def test_commission_tier2_subsequent_months(
        self,
        db_session: AsyncSession,
        affiliate_service: AffiliateService,
    ):
        """Test tier 2 commission (15%) for months 2+."""
        subscription_price = 100.0

        # Month 2+ commission = 15%
        commission = await affiliate_service.calculate_commission(
            subscription_price=subscription_price,
            month=2,
        )

        assert commission == 15.0

    async def test_commission_performance_bonus(
        self,
        db_session: AsyncSession,
        affiliate_service: AffiliateService,
    ):
        """Test performance bonus (5%) for 3+ months."""
        subscription_price = 100.0

        # Performance bonus = 5%
        commission = await affiliate_service.calculate_commission(
            subscription_price=subscription_price,
            month=3,
            performance_bonus=True,
        )

        # 15% + 5% bonus
        assert commission == 20.0

    async def test_record_commission(
        self,
        db_session: AsyncSession,
        test_affiliate: User,
        affiliate_service: AffiliateService,
    ):
        """Test recording commission in DB."""
        commission_amount = 30.0

        earning = await affiliate_service.record_commission(
            affiliate_id=test_affiliate.id,
            referee_id="user_456",
            amount_gbp=commission_amount,
            tier="tier_1",
        )

        assert earning is not None
        assert earning.affiliate_id == test_affiliate.id
        assert earning.amount_gbp == commission_amount
        assert earning.status == "pending"


@pytest.mark.asyncio
class TestAffiliateStats:
    """Test affiliate statistics and dashboard."""

    async def test_get_affiliate_stats(
        self,
        db_session: AsyncSession,
        test_affiliate: User,
        affiliate_service: AffiliateService,
    ):
        """Test retrieving affiliate statistics."""
        affiliate = await affiliate_service.register_affiliate(test_affiliate.id)

        # Add some events
        await affiliate_service.track_signup(affiliate.referral_code, "user_1")
        await affiliate_service.track_signup(affiliate.referral_code, "user_2")
        await affiliate_service.track_subscription(
            affiliate.referral_code,
            "user_1",
            99.99,
        )

        # Get stats
        stats = await affiliate_service.get_stats(affiliate.id)

        assert stats is not None
        assert stats["total_clicks"] == 2
        assert stats["total_signups"] == 2
        assert stats["total_subscriptions"] == 1
        assert stats["conversion_rate"] == pytest.approx(0.5)

    async def test_affiliate_earnings_summary(
        self,
        db_session: AsyncSession,
        test_affiliate: User,
        affiliate_service: AffiliateService,
    ):
        """Test affiliate earnings summary."""
        # Add earnings
        await affiliate_service.record_commission(
            test_affiliate.id,
            "user_1",
            30.0,
            "tier_1",
        )
        await affiliate_service.record_commission(
            test_affiliate.id,
            "user_2",
            15.0,
            "tier_2",
        )

        # Get summary
        summary = await affiliate_service.get_earnings_summary(test_affiliate.id)

        assert summary["total_earnings"] == 45.0
        assert summary["pending_earnings"] == 45.0
        assert summary["paid_earnings"] == 0.0


@pytest.mark.asyncio
class TestPayoutRequests:
    """Test payout request handling."""

    async def test_request_payout(
        self,
        db_session: AsyncSession,
        test_affiliate: User,
        affiliate_service: AffiliateService,
    ):
        """Test requesting payout."""
        # Add earnings first
        await affiliate_service.record_commission(
            test_affiliate.id,
            "user_1",
            100.0,
            "tier_1",
        )

        # Request payout
        payout = await affiliate_service.request_payout(
            affiliate_id=test_affiliate.id,
        )

        assert payout is not None
        assert payout.amount_gbp == 100.0
        assert payout.status == "pending"

    async def test_payout_below_minimum(
        self,
        db_session: AsyncSession,
        test_affiliate: User,
        affiliate_service: AffiliateService,
    ):
        """Test payout request below minimum threshold."""
        # Add small earnings (< £50)
        await affiliate_service.record_commission(
            test_affiliate.id,
            "user_1",
            25.0,
            "tier_1",
        )

        # Request payout should fail or return None
        with pytest.raises(ValueError, match="minimum"):
            await affiliate_service.request_payout(test_affiliate.id)

    async def test_payout_idempotency(
        self,
        db_session: AsyncSession,
        test_affiliate: User,
        affiliate_service: AffiliateService,
    ):
        """Test that same payout request is idempotent."""
        # Add earnings
        await affiliate_service.record_commission(
            test_affiliate.id,
            "user_1",
            100.0,
            "tier_1",
        )

        # Request twice
        payout1 = await affiliate_service.request_payout(test_affiliate.id)
        payout2 = await affiliate_service.request_payout(test_affiliate.id)

        # Should be same payout
        assert payout1.id == payout2.id


@pytest.mark.asyncio
class TestEdgeCases:
    """Test edge cases and error handling."""

    async def test_referral_with_nonexistent_user(
        self,
        db_session: AsyncSession,
        affiliate_service: AffiliateService,
    ):
        """Test tracking referral for nonexistent user."""
        with pytest.raises(ValueError):
            await affiliate_service.track_signup("invalid_code", "user_123")

    async def test_get_stats_for_nonexistent_affiliate(
        self,
        db_session: AsyncSession,
        affiliate_service: AffiliateService,
    ):
        """Test getting stats for nonexistent affiliate."""
        stats = await affiliate_service.get_stats("nonexistent_id")
        assert stats is None

    async def test_commission_calculation_zero_price(
        self,
        db_session: AsyncSession,
        affiliate_service: AffiliateService,
    ):
        """Test commission calculation with zero price."""
        commission = await affiliate_service.calculate_commission(
            subscription_price=0.0,
            month=1,
        )
        assert commission == 0.0

    async def test_commission_calculation_large_price(
        self,
        db_session: AsyncSession,
        affiliate_service: AffiliateService,
    ):
        """Test commission calculation with large price."""
        commission = await affiliate_service.calculate_commission(
            subscription_price=10000.0,
            month=1,
        )
        assert commission == 3000.0  # 30% of 10000


@pytest.mark.asyncio
class TestIntegration:
    """Integration tests for full affiliate workflow."""

    async def test_full_affiliate_workflow(
        self,
        db_session: AsyncSession,
        test_affiliate: User,
        test_referred_user: User,
        affiliate_service: AffiliateService,
    ):
        """Test complete affiliate workflow: register → refer → track → earn."""
        # Step 1: Register as affiliate
        affiliate = await affiliate_service.register_affiliate(test_affiliate.id)
        assert affiliate is not None

        # Step 2: Generate referral link
        link = await affiliate_service.generate_referral_link(affiliate.id)
        assert link is not None

        # Step 3: New user signs up with referral code
        signup_event = await affiliate_service.track_signup(
            affiliate.referral_code,
            test_referred_user.id,
        )
        assert signup_event is not None

        # Step 4: New user subscribes
        sub_event = await affiliate_service.track_subscription(
            affiliate.referral_code,
            test_referred_user.id,
            99.99,
        )
        assert sub_event is not None

        # Step 5: Verify commission recorded
        stats = await affiliate_service.get_stats(affiliate.id)
        assert stats["total_signups"] == 1
        assert stats["total_subscriptions"] == 1

        # Step 6: Commission should be recorded
        earnings = await affiliate_service.get_earnings_summary(affiliate.id)
        assert earnings["pending_earnings"] > 0

        # Step 7: Request payout
        payout = await affiliate_service.request_payout(affiliate.id)
        assert payout is not None
        assert payout.status == "pending"
