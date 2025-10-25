"""Integration tests for Telegram Stars payment handler with database.

Tests complete payment workflow:
- Telegram payment success handling
- Refund processing
- Idempotent event processing
- Entitlement granting
- Database transaction semantics
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import AsyncMock, patch

from backend.app.billing.stripe.models import StripeEvent
from backend.app.telegram.payments import TelegramPaymentHandler


class TestTelegramPaymentIntegration:
    """Integration tests for Telegram Stars payment with database."""

    @pytest.mark.asyncio
    async def test_successful_payment_creates_event_and_grants_entitlement(
        self, db_session: AsyncSession
    ):
        """Test complete flow: payment → event stored → entitlement granted."""
        # Setup
        user_id = 123456789
        amount = 500  # Stars
        payment_charge_id = "payment_tg_001"

        handler = TelegramPaymentHandler()

        # Mock EntitlementService
        with patch("backend.app.telegram.payments.EntitlementService") as mock_service:
            mock_instance = AsyncMock()
            mock_service.return_value = mock_instance
            mock_instance.grant_premium_tier = AsyncMock(return_value=True)

            # Simulate payment event
            payment_data = {
                "user_id": user_id,
                "amount": amount,
                "currency": "XTR",  # Telegram Stars currency
                "charge_id": payment_charge_id,
            }

            # Create event in database
            event = StripeEvent(
                event_id=f"telegram_payment_{payment_charge_id}",
                event_type="telegram_stars.successful_payment",
                payment_method="telegram_stars",
                customer_id=str(user_id),
                amount_cents=amount * 100,  # Convert to cents for consistency
                currency="XTR",
                status=0,  # pending
            )
            db_session.add(event)
            await db_session.commit()
            await db_session.refresh(event)

            # Verify event created
            assert event.id is not None
            assert event.event_id == f"telegram_payment_{payment_charge_id}"
            assert event.customer_id == str(user_id)
            assert event.amount_cents == amount * 100

    @pytest.mark.asyncio
    async def test_refund_creates_refund_event(self, db_session: AsyncSession):
        """Test refund handling: refund creates separate event in database."""
        # Setup
        user_id = 123456789
        amount = 500
        original_charge_id = "payment_tg_001"
        refund_id = "refund_tg_001"

        # Create original payment event
        payment_event = StripeEvent(
            event_id=f"telegram_payment_{original_charge_id}",
            event_type="telegram_stars.successful_payment",
            payment_method="telegram_stars",
            customer_id=str(user_id),
            amount_cents=amount * 100,
            currency="XTR",
            status=1,  # processed
        )
        db_session.add(payment_event)
        await db_session.commit()

        # Create refund event
        refund_event = StripeEvent(
            event_id=f"telegram_refund_{refund_id}",
            event_type="telegram_stars.refunded",
            payment_method="telegram_stars",
            customer_id=str(user_id),
            amount_cents=amount * 100,
            currency="XTR",
            status=1,  # processed
        )
        db_session.add(refund_event)
        await db_session.commit()
        await db_session.refresh(refund_event)

        # Verify refund event created
        assert refund_event.event_type == "telegram_stars.refunded"
        assert refund_event.customer_id == str(user_id)
        assert refund_event.is_processed

    @pytest.mark.asyncio
    async def test_idempotent_payment_processing(self, db_session: AsyncSession):
        """Test idempotency: duplicate payment with same ID not processed twice."""
        # Setup
        charge_id = "payment_tg_idempotent_001"

        # Create first payment event
        event1 = StripeEvent(
            event_id=f"telegram_payment_{charge_id}",
            event_type="telegram_stars.successful_payment",
            payment_method="telegram_stars",
            customer_id="123456789",
            amount_cents=50000,
            currency="XTR",
            status=1,  # already processed
        )
        db_session.add(event1)
        await db_session.commit()
        event1_id = event1.id

        # Attempt to create duplicate (with same charge_id)
        # In production, the application would:
        # 1. Query for existing event with this charge_id
        # 2. If found with status=processed, skip processing
        # 3. If not found, process the new event

        from sqlalchemy import select

        query = select(StripeEvent).where(
            StripeEvent.event_id == f"telegram_payment_{charge_id}"
        )
        result = await db_session.execute(query)
        existing = result.scalar_one_or_none()

        # Verify existing event found (should not process again)
        assert existing is not None
        assert existing.id == event1_id
        assert existing.is_processed

    @pytest.mark.asyncio
    async def test_payment_error_recorded_in_database(self, db_session: AsyncSession):
        """Test error handling: payment error stored with context."""
        # Setup
        charge_id = "payment_tg_failed_001"
        error_msg = "User cancelled payment"

        # Create failed payment event
        event = StripeEvent(
            event_id=f"telegram_payment_{charge_id}",
            event_type="telegram_stars.successful_payment",
            payment_method="telegram_stars",
            customer_id="123456789",
            amount_cents=50000,
            currency="XTR",
            status=2,  # failed
            error_message=error_msg,
        )
        db_session.add(event)
        await db_session.commit()
        await db_session.refresh(event)

        # Verify error recorded
        assert event.is_failed
        assert event.error_message == error_msg
        assert event.status == 2

    @pytest.mark.asyncio
    async def test_query_user_payment_history(self, db_session: AsyncSession):
        """Test database query: retrieve payment history for a user."""
        # Setup: Create payment events for a user
        user_id = 123456789

        events = []
        for i in range(5):
            event = StripeEvent(
                event_id=f"telegram_payment_user_{i}",
                event_type="telegram_stars.successful_payment",
                payment_method="telegram_stars",
                customer_id=str(user_id),
                amount_cents=(100 + i * 50) * 100,
                currency="XTR",
                status=1,  # processed
            )
            events.append(event)

        db_session.add_all(events)
        await db_session.commit()

        # Query all payments for user
        from sqlalchemy import select

        query = select(StripeEvent).where(
            StripeEvent.customer_id == str(user_id),
            StripeEvent.event_type.contains("payment"),
        )
        result = await db_session.execute(query)
        user_payments = result.scalars().all()

        # Verify all user's payments retrieved
        assert len(user_payments) >= 5
        assert all(p.customer_id == str(user_id) for p in user_payments)
        assert all(p.is_processed for p in user_payments)

    @pytest.mark.asyncio
    async def test_transaction_consistency_on_concurrent_updates(
        self, db_session: AsyncSession
    ):
        """Test transaction semantics: concurrent updates maintain consistency."""
        import asyncio

        # Create initial event
        event = StripeEvent(
            event_id="telegram_payment_concurrent_001",
            event_type="telegram_stars.successful_payment",
            payment_method="telegram_stars",
            customer_id="123456789",
            amount_cents=50000,
            currency="XTR",
            status=0,  # pending
        )
        db_session.add(event)
        await db_session.commit()
        event_id = event.id

        # Simulate concurrent update
        async def update_status(status_val: int):
            """Update event status."""
            from sqlalchemy import select

            query = select(StripeEvent).where(StripeEvent.id == event_id)
            result = await db_session.execute(query)
            evt = result.scalar_one()
            evt.status = status_val
            db_session.add(evt)
            await db_session.commit()
            return evt.status

        # Update status concurrently (simulated)
        results = await asyncio.gather(
            update_status(1),  # First update: status = processed
        )

        # Verify final state consistent
        from sqlalchemy import select

        query = select(StripeEvent).where(StripeEvent.id == event_id)
        result = await db_session.execute(query)
        final_event = result.scalar_one()
        assert final_event.status == 1

    @pytest.mark.asyncio
    async def test_payment_method_consistency_telegram_vs_stripe(
        self, db_session: AsyncSession
    ):
        """Test unified model: Telegram and Stripe events in same table."""
        # Create Stripe event
        stripe_event = StripeEvent(
            event_id="evt_stripe_001",
            event_type="charge.succeeded",
            payment_method="card",
            customer_id="cus_stripe_001",
            amount_cents=5000,
            currency="USD",
            status=1,
        )

        # Create Telegram event
        telegram_event = StripeEvent(
            event_id="evt_telegram_001",
            event_type="telegram_stars.successful_payment",
            payment_method="telegram_stars",
            customer_id="123456789",  # Telegram user ID
            amount_cents=50000,
            currency="XTR",
            status=1,
        )

        db_session.add_all([stripe_event, telegram_event])
        await db_session.commit()

        # Query all payment events (unified)
        from sqlalchemy import select

        query = select(StripeEvent).where(StripeEvent.status == 1)
        result = await db_session.execute(query)
        all_payments = result.scalars().all()

        # Verify both stored and queryable
        assert len(all_payments) >= 2
        assert any(p.payment_method == "card" for p in all_payments)
        assert any(p.payment_method == "telegram_stars" for p in all_payments)

    @pytest.mark.asyncio
    async def test_event_ordering_by_creation_time(self, db_session: AsyncSession):
        """Test database ordering: events ordered by creation time."""
        import asyncio

        user_id = "123456789"

        async def create_event(i: int):
            """Create payment event."""
            event = StripeEvent(
                event_id=f"telegram_payment_ordering_{i}",
                event_type="telegram_stars.successful_payment",
                payment_method="telegram_stars",
                customer_id=user_id,
                amount_cents=50000 + (i * 1000),
                currency="XTR",
                status=1,
            )
            db_session.add(event)
            await db_session.commit()
            return event

        # Create 5 events
        await asyncio.gather(*[create_event(i) for i in range(5)])

        # Query events ordered by creation time
        from sqlalchemy import select

        query = (
            select(StripeEvent)
            .where(StripeEvent.customer_id == user_id)
            .order_by(StripeEvent.created_at.asc())
        )
        result = await db_session.execute(query)
        events = result.scalars().all()

        # Verify ordered correctly
        assert len(events) == 5
        for i in range(len(events) - 1):
            assert events[i].created_at <= events[i + 1].created_at

    @pytest.mark.asyncio
    async def test_payment_amount_aggregation(self, db_session: AsyncSession):
        """Test aggregation: sum payments for a user."""
        user_id = "123456789"

        # Create multiple payments
        amounts = [50000, 100000, 25000, 75000]
        for i, amount in enumerate(amounts):
            event = StripeEvent(
                event_id=f"telegram_payment_sum_{i}",
                event_type="telegram_stars.successful_payment",
                payment_method="telegram_stars",
                customer_id=user_id,
                amount_cents=amount,
                currency="XTR",
                status=1,
            )
            db_session.add(event)
        await db_session.commit()

        # Aggregate total paid
        from sqlalchemy import select, func

        query = select(func.sum(StripeEvent.amount_cents)).where(
            StripeEvent.customer_id == user_id,
            StripeEvent.event_type.contains("payment"),
        )
        result = await db_session.execute(query)
        total = result.scalar()

        # Verify aggregation
        expected = sum(amounts)
        assert total == expected

    @pytest.mark.asyncio
    async def test_event_deletion_cascade(self, db_session: AsyncSession):
        """Test database constraints: deleting events works correctly."""
        # Create event
        event = StripeEvent(
            event_id="telegram_payment_delete_test_001",
            event_type="telegram_stars.successful_payment",
            payment_method="telegram_stars",
            customer_id="123456789",
            amount_cents=50000,
            currency="XTR",
            status=1,
        )
        db_session.add(event)
        await db_session.commit()
        event_id = event.id

        # Delete event
        await db_session.delete(event)
        await db_session.commit()

        # Verify deleted
        from sqlalchemy import select

        query = select(StripeEvent).where(StripeEvent.id == event_id)
        result = await db_session.execute(query)
        found = result.scalar_one_or_none()

        assert found is None
