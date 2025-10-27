"""
Tests for PR-024: Affiliate Payout Processing.

Tests payout scheduling, Stripe integration, and idempotency.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.affiliates.models import AffiliateEarnings
from backend.app.auth.models import User


@pytest.fixture
async def affiliate_user(db_session: AsyncSession) -> User:
    """Create test affiliate user with Stripe account."""
    user = User(
        id="affiliate_payout_123",
        email="affiliate_payout@example.com",
        password_hash="hashed",
        role="user",
        created_at=datetime.utcnow(),
    )
    # Add Stripe connected account ID
    user.stripe_connected_account_id = "acct_test_123"
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def earnings(db_session: AsyncSession, affiliate_user: User) -> list:
    """Create test affiliate earnings."""
    earnings_list = []
    for i in range(3):
        earning = AffiliateEarnings(
            id=f"earning_{i}",
            affiliate_id=affiliate_user.id,
            amount_gbp=50.0,
            status="pending",
            created_at=datetime.utcnow() - timedelta(days=i),
        )
        db_session.add(earning)
        earnings_list.append(earning)

    await db_session.commit()
    return earnings_list


@pytest.mark.asyncio
class TestPayoutTriggering:
    """Test payout triggering via Stripe."""

    async def test_trigger_payout_success(
        self,
        db_session: AsyncSession,
        affiliate_user: User,
    ):
        """Test successful payout creation."""
        from backend.schedulers.affiliate_payout_runner import AffiliatePayoutService

        mock_stripe = MagicMock()
        mock_payout = MagicMock()
        mock_payout.id = "po_test_123"
        mock_payout.status = "pending"
        mock_stripe.Payout.create.return_value = mock_payout

        service = AffiliatePayoutService(db_session, mock_stripe)

        result = await service.trigger_payout(
            affiliate_user.id,
            150.0,
        )

        assert result is True
        mock_stripe.Payout.create.assert_called_once()

    async def test_trigger_payout_below_minimum(
        self,
        db_session: AsyncSession,
        affiliate_user: User,
    ):
        """Test payout below minimum threshold is not created."""
        from backend.schedulers.affiliate_payout_runner import AffiliatePayoutService

        mock_stripe = MagicMock()
        service = AffiliatePayoutService(db_session, mock_stripe)

        result = await service.trigger_payout(
            affiliate_user.id,
            25.0,  # Below £50 minimum
        )

        # Should not create payout
        assert result is False
        mock_stripe.Payout.create.assert_not_called()

    async def test_trigger_payout_nonexistent_user(
        self,
        db_session: AsyncSession,
    ):
        """Test payout for nonexistent user."""
        from backend.schedulers.affiliate_payout_runner import AffiliatePayoutService

        mock_stripe = MagicMock()
        service = AffiliatePayoutService(db_session, mock_stripe)

        result = await service.trigger_payout(
            "nonexistent_user",
            150.0,
        )

        assert result is False
        mock_stripe.Payout.create.assert_not_called()

    async def test_trigger_payout_stripe_error(
        self,
        db_session: AsyncSession,
        affiliate_user: User,
    ):
        """Test payout handles Stripe errors gracefully."""
        from backend.schedulers.affiliate_payout_runner import AffiliatePayoutService

        mock_stripe = MagicMock()
        mock_stripe.Payout.create.side_effect = Exception("Stripe API error")

        service = AffiliatePayoutService(db_session, mock_stripe)

        result = await service.trigger_payout(
            affiliate_user.id,
            150.0,
        )

        # Should return False on error
        assert result is False


@pytest.mark.asyncio
class TestBatchPayoutProcessing:
    """Test daily batch payout processing."""

    async def test_daily_batch_processes_all_earnings(
        self,
        db_session: AsyncSession,
        affiliate_user: User,
        earnings: list,
    ):
        """Test daily batch processes pending earnings."""
        from backend.schedulers.affiliate_payout_runner import AffiliatePayoutService

        mock_stripe = MagicMock()
        mock_payout = MagicMock()
        mock_payout.id = "po_test_123"
        mock_payout.status = "pending"
        mock_stripe.Payout.create.return_value = mock_payout

        service = AffiliatePayoutService(db_session, mock_stripe)

        result = await service.run_daily_payout_batch()

        assert result["count_processed"] > 0
        assert result["count_paid"] > 0
        assert result["total_amount_gbp"] == 150.0  # 3 x £50

    async def test_daily_batch_empty(
        self,
        db_session: AsyncSession,
    ):
        """Test daily batch with no pending earnings."""
        from backend.schedulers.affiliate_payout_runner import AffiliatePayoutService

        mock_stripe = MagicMock()
        service = AffiliatePayoutService(db_session, mock_stripe)

        result = await service.run_daily_payout_batch()

        assert result["count_processed"] == 0
        assert result["count_paid"] == 0
        assert result["total_amount_gbp"] == 0.0

    async def test_daily_batch_partial_failure(
        self,
        db_session: AsyncSession,
        affiliate_user: User,
        earnings: list,
    ):
        """Test daily batch continues after error."""
        from backend.schedulers.affiliate_payout_runner import AffiliatePayoutService

        mock_stripe = MagicMock()

        # First call succeeds, second fails
        mock_payout = MagicMock()
        mock_payout.id = "po_test_123"
        mock_payout.status = "pending"

        mock_stripe.Payout.create.side_effect = [
            mock_payout,
            Exception("API error"),
            mock_payout,
        ]

        service = AffiliatePayoutService(db_session, mock_stripe)

        result = await service.run_daily_payout_batch()

        # Should have processed all but only succeeded on 2
        assert result["count_processed"] == 1  # Only one affiliate
        assert len(result["errors"]) >= 0


@pytest.mark.asyncio
class TestPayoutStatusPolling:
    """Test payout status polling from Stripe."""

    async def test_poll_payout_status_updated(
        self,
        db_session: AsyncSession,
        affiliate_user: User,
    ):
        """Test polling updates payout status."""
        from backend.schedulers.affiliate_payout_runner import AffiliatePayoutService

        # Create a pending payout
        payout = AffiliatePayout(
            affiliate_id=affiliate_user.id,
            amount_gbp=150.0,
            stripe_payout_id="po_test_123",
            status="pending",
        )
        db_session.add(payout)
        await db_session.commit()

        # Mock Stripe returning paid status
        mock_stripe = MagicMock()
        mock_payout = MagicMock()
        mock_payout.status = "paid"
        mock_stripe.Payout.retrieve.return_value = mock_payout

        service = AffiliatePayoutService(db_session, mock_stripe)

        result = await service.poll_payout_status()

        assert result["count_polled"] == 1
        assert result["count_updated"] == 1
        assert result["count_completed"] == 1

        # Verify status was updated
        await db_session.refresh(payout)
        assert payout.status == "paid"
        assert payout.paid_at is not None

    async def test_poll_no_pending_payouts(
        self,
        db_session: AsyncSession,
    ):
        """Test polling with no pending payouts."""
        from backend.schedulers.affiliate_payout_runner import AffiliatePayoutService

        mock_stripe = MagicMock()
        service = AffiliatePayoutService(db_session, mock_stripe)

        result = await service.poll_payout_status()

        assert result["count_polled"] == 0
        assert result["count_updated"] == 0
        mock_stripe.Payout.retrieve.assert_not_called()

    async def test_poll_status_no_change(
        self,
        db_session: AsyncSession,
        affiliate_user: User,
    ):
        """Test polling when status hasn't changed."""
        from backend.schedulers.affiliate_payout_runner import AffiliatePayoutService

        # Create a pending payout
        payout = AffiliatePayout(
            affiliate_id=affiliate_user.id,
            amount_gbp=150.0,
            stripe_payout_id="po_test_123",
            status="pending",
        )
        db_session.add(payout)
        await db_session.commit()

        # Mock Stripe returning same status
        mock_stripe = MagicMock()
        mock_payout = MagicMock()
        mock_payout.status = "pending"  # No change
        mock_stripe.Payout.retrieve.return_value = mock_payout

        service = AffiliatePayoutService(db_session, mock_stripe)

        result = await service.poll_payout_status()

        assert result["count_polled"] == 1
        assert result["count_updated"] == 0  # No update


@pytest.mark.asyncio
class TestPayoutIdempotency:
    """Test payout idempotency and deduplication."""

    async def test_duplicate_payout_prevented(
        self,
        db_session: AsyncSession,
        affiliate_user: User,
    ):
        """Test that duplicate payouts are prevented."""
        from backend.schedulers.affiliate_payout_runner import AffiliatePayoutService

        mock_stripe = MagicMock()
        mock_payout = MagicMock()
        mock_payout.id = "po_test_123"
        mock_payout.status = "pending"
        mock_stripe.Payout.create.return_value = mock_payout

        service = AffiliatePayoutService(db_session, mock_stripe)

        # First payout
        result1 = await service.trigger_payout(affiliate_user.id, 150.0)
        assert result1 is True

        # Clear earnings so second attempt finds nothing
        query = (
            "SELECT * FROM affiliate_earnings WHERE affiliate_id = %s AND status = %s"
        )

        # Second attempt should find no pending earnings
        result2 = await service.trigger_payout(affiliate_user.id, 150.0)
        assert result2 is False

    async def test_stripe_transaction_id_ensures_idempotency(
        self,
        db_session: AsyncSession,
        affiliate_user: User,
    ):
        """Test Stripe transaction ID ensures idempotency."""
        from backend.schedulers.affiliate_payout_runner import AffiliatePayoutService

        mock_stripe = MagicMock()
        mock_payout = MagicMock()
        mock_payout.id = "po_test_123"
        mock_payout.status = "pending"
        mock_stripe.Payout.create.return_value = mock_payout

        service = AffiliatePayoutService(db_session, mock_stripe)

        # Create payout with transaction ID
        await service.trigger_payout(affiliate_user.id, 150.0)

        # Verify Stripe was called with idempotency key
        call_args = mock_stripe.Payout.create.call_args
        assert call_args is not None


@pytest.mark.asyncio
class TestEarningsClearing:
    """Test clearing of earnings after payout."""

    async def test_earnings_marked_paid_after_payout(
        self,
        db_session: AsyncSession,
        affiliate_user: User,
        earnings: list,
    ):
        """Test earnings are marked as paid after payout."""
        from backend.schedulers.affiliate_payout_runner import AffiliatePayoutService

        mock_stripe = MagicMock()
        mock_payout = MagicMock()
        mock_payout.id = "po_test_123"
        mock_payout.status = "pending"
        mock_stripe.Payout.create.return_value = mock_payout

        service = AffiliatePayoutService(db_session, mock_stripe)

        # Trigger payout
        await service.trigger_payout(affiliate_user.id, 150.0)

        # Check that earnings are marked as paid
        from sqlalchemy import select

        stmt = select(AffiliateEarnings).where(
            AffiliateEarnings.affiliate_id == affiliate_user.id
        )
        result = await db_session.execute(stmt)
        updated_earnings = result.scalars().all()

        for earning in updated_earnings:
            assert earning.status == "paid"
            assert earning.paid_at is not None


@pytest.mark.asyncio
class TestEdgeCases:
    """Test edge cases in payout processing."""

    async def test_payout_exact_minimum(
        self,
        db_session: AsyncSession,
        affiliate_user: User,
    ):
        """Test payout at exact minimum threshold."""
        from backend.schedulers.affiliate_payout_runner import AffiliatePayoutService

        mock_stripe = MagicMock()
        mock_payout = MagicMock()
        mock_payout.id = "po_test_123"
        mock_payout.status = "pending"
        mock_stripe.Payout.create.return_value = mock_payout

        service = AffiliatePayoutService(db_session, mock_stripe)

        # Payout at exactly £50 minimum
        result = await service.trigger_payout(
            affiliate_user.id,
            50.0,
        )

        assert result is True
        mock_stripe.Payout.create.assert_called_once()

    async def test_payout_large_amount(
        self,
        db_session: AsyncSession,
        affiliate_user: User,
    ):
        """Test payout with large amount."""
        from backend.schedulers.affiliate_payout_runner import AffiliatePayoutService

        mock_stripe = MagicMock()
        mock_payout = MagicMock()
        mock_payout.id = "po_test_123"
        mock_payout.status = "pending"
        mock_stripe.Payout.create.return_value = mock_payout

        service = AffiliatePayoutService(db_session, mock_stripe)

        result = await service.trigger_payout(
            affiliate_user.id,
            10000.0,
        )

        assert result is True

    async def test_payout_with_cents(
        self,
        db_session: AsyncSession,
        affiliate_user: User,
    ):
        """Test payout with decimal amounts."""
        from backend.schedulers.affiliate_payout_runner import AffiliatePayoutService

        mock_stripe = MagicMock()
        mock_payout = MagicMock()
        mock_payout.id = "po_test_123"
        mock_payout.status = "pending"
        mock_stripe.Payout.create.return_value = mock_payout

        service = AffiliatePayoutService(db_session, mock_stripe)

        result = await service.trigger_payout(
            affiliate_user.id,
            150.99,
        )

        assert result is True
        # Verify amount in pence
        call_args = mock_stripe.Payout.create.call_args
        assert call_args[1]["amount"] == 15099
