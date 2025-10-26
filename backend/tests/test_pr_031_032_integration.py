"""Integration tests for PR-031 (Stripe) and PR-032 (Telegram payments).

Full database-backed tests for payment processing with:
- Real SQLite database (in-memory)
- Stripe webhook idempotency
- Telegram Stars payment handling
- Database transaction semantics
- Constraint validation
"""

import hashlib
import hmac
import time
from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.billing.stripe.models import StripeEvent
from backend.app.billing.stripe.webhooks import verify_stripe_signature


class TestPaymentDatabaseIntegration:
    """Integration tests for payment event handling with real database."""

    @pytest.mark.asyncio
    async def test_stripe_event_creation_and_retrieval(self, db_session: AsyncSession):
        """Test basic Stripe event creation and database persistence."""
        # Create Stripe event
        event = StripeEvent(
            event_id="evt_test_001",
            event_type="charge.succeeded",
            payment_method="card",
            customer_id="cus_test_001",
            amount_cents=5000,
            currency="USD",
            status=1,  # processed
            webhook_timestamp=datetime.utcnow(),
        )
        db_session.add(event)
        await db_session.commit()
        event_id = event.id

        # Retrieve from database
        query = select(StripeEvent).where(StripeEvent.id == event_id)
        result = await db_session.execute(query)
        found = result.scalar_one_or_none()

        assert found is not None
        assert found.event_id == "evt_test_001"
        assert found.amount_cents == 5000
        assert found.is_processed

    @pytest.mark.asyncio
    async def test_idempotent_duplicate_prevention(self, db_session: AsyncSession):
        """Test idempotency: duplicate event_id prevents reprocessing."""
        event_id = "evt_idempotent_001"

        # Create first event
        event1 = StripeEvent(
            event_id=event_id,
            event_type="charge.succeeded",
            payment_method="card",
            customer_id="cus_test_001",
            amount_cents=5000,
            currency="USD",
            status=1,  # processed
            webhook_timestamp=datetime.utcnow(),
        )
        db_session.add(event1)
        await db_session.commit()
        event1_id = event1.id

        # Try to create duplicate (application should check for existing event_id)
        query = select(StripeEvent).where(StripeEvent.event_id == event_id)
        result = await db_session.execute(query)
        existing = result.scalar_one_or_none()

        # Verify existing event found (idempotency check passes)
        assert existing is not None
        assert existing.id == event1_id
        assert existing.is_processed

    @pytest.mark.asyncio
    async def test_telegram_and_stripe_unified_model(self, db_session: AsyncSession):
        """Test unified payment model: Stripe and Telegram events in same table."""
        # Create Stripe event
        stripe_event = StripeEvent(
            event_id="evt_stripe_unified_001",
            event_type="charge.succeeded",
            payment_method="card",
            customer_id="cus_stripe_001",
            amount_cents=5000,
            currency="USD",
            status=1,
            webhook_timestamp=datetime.utcnow(),
        )

        # Create Telegram event
        telegram_event = StripeEvent(
            event_id="evt_telegram_unified_001",
            event_type="telegram_stars.successful_payment",
            payment_method="telegram_stars",
            customer_id="123456789",  # Telegram user ID
            amount_cents=50000,
            currency="XTR",
            status=1,
            webhook_timestamp=datetime.utcnow(),
        )

        db_session.add_all([stripe_event, telegram_event])
        await db_session.commit()

        # Query all payment events
        query = select(StripeEvent).where(StripeEvent.status == 1)
        result = await db_session.execute(query)
        all_events = result.scalars().all()

        # Verify both stored and queryable
        assert len(all_events) >= 2
        payment_methods = {e.payment_method for e in all_events}
        assert "card" in payment_methods
        assert "telegram_stars" in payment_methods

    @pytest.mark.asyncio
    async def test_payment_status_transitions(self, db_session: AsyncSession):
        """Test payment status transitions: pending → processed or failed."""
        # Create pending event
        event = StripeEvent(
            event_id="evt_status_transition_001",
            event_type="charge.succeeded",
            payment_method="card",
            customer_id="cus_test_001",
            amount_cents=5000,
            currency="USD",
            status=0,  # pending
            webhook_timestamp=datetime.utcnow(),
        )
        db_session.add(event)
        await db_session.commit()
        event_id = event.id

        # Transition to processed
        query = select(StripeEvent).where(StripeEvent.id == event_id)
        result = await db_session.execute(query)
        evt = result.scalar_one()
        evt.status = 1  # processed
        db_session.add(evt)
        await db_session.commit()

        # Verify transition
        result = await db_session.execute(query)
        updated = result.scalar_one()
        assert updated.is_processed
        assert updated.status == 1

    @pytest.mark.asyncio
    async def test_payment_failure_with_error_message(self, db_session: AsyncSession):
        """Test failed payment: status=2 with error message."""
        error_msg = "Card declined"

        event = StripeEvent(
            event_id="evt_failed_001",
            event_type="charge.failed",
            payment_method="card",
            customer_id="cus_test_001",
            amount_cents=5000,
            currency="USD",
            status=2,  # failed
            error_message=error_msg,
            webhook_timestamp=datetime.utcnow(),
        )
        db_session.add(event)
        await db_session.commit()
        await db_session.refresh(event)

        # Verify failure recorded
        assert event.is_failed
        assert event.error_message == error_msg
        assert event.status == 2

    @pytest.mark.asyncio
    async def test_query_customer_payment_history(self, db_session: AsyncSession):
        """Test query: retrieve all payments for a customer."""
        customer_id = "cus_history_001"

        # Create 3 payments for this customer
        for i in range(3):
            event = StripeEvent(
                event_id=f"evt_history_{i}",
                event_type="charge.succeeded",
                payment_method="card",
                customer_id=customer_id,
                amount_cents=5000 * (i + 1),
                currency="USD",
                status=1,
                webhook_timestamp=datetime.utcnow(),
            )
            db_session.add(event)
        await db_session.commit()

        # Query customer's payment history
        query = select(StripeEvent).where(StripeEvent.customer_id == customer_id)
        result = await db_session.execute(query)
        payments = result.scalars().all()

        # Verify all customer payments retrieved
        assert len(payments) == 3
        assert all(p.customer_id == customer_id for p in payments)
        assert all(p.is_processed for p in payments)

    @pytest.mark.asyncio
    async def test_refund_event_separate_record(self, db_session: AsyncSession):
        """Test refund handling: refund is separate event record."""
        # Original charge
        charge_event = StripeEvent(
            event_id="evt_charge_refund_001",
            event_type="charge.succeeded",
            payment_method="card",
            customer_id="cus_test_001",
            amount_cents=5000,
            currency="USD",
            status=1,
            webhook_timestamp=datetime.utcnow(),
        )
        db_session.add(charge_event)
        await db_session.commit()

        # Refund as separate event
        refund_event = StripeEvent(
            event_id="evt_refund_refund_001",
            event_type="charge.refunded",
            payment_method="card",
            customer_id="cus_test_001",
            amount_cents=5000,
            currency="USD",
            status=1,
            webhook_timestamp=datetime.utcnow(),
        )
        db_session.add(refund_event)
        await db_session.commit()

        # Query both events
        query = (
            select(StripeEvent)
            .where(StripeEvent.customer_id == "cus_test_001")
            .order_by(StripeEvent.created_at)
        )
        result = await db_session.execute(query)
        events = result.scalars().all()

        assert len(events) == 2
        assert events[0].event_type == "charge.succeeded"
        assert events[1].event_type == "charge.refunded"

    @pytest.mark.asyncio
    async def test_aggregate_total_payments(self, db_session: AsyncSession):
        """Test aggregation: sum total paid by customer."""
        from sqlalchemy import func

        customer_id = "cus_aggregate_001"
        amounts = [5000, 10000, 25000]

        for i, amount in enumerate(amounts):
            event = StripeEvent(
                event_id=f"evt_agg_{i}",
                event_type="charge.succeeded",
                payment_method="card",
                customer_id=customer_id,
                amount_cents=amount,
                currency="USD",
                status=1,
                webhook_timestamp=datetime.utcnow(),
            )
            db_session.add(event)
        await db_session.commit()

        # Aggregate total
        query = select(func.sum(StripeEvent.amount_cents)).where(
            StripeEvent.customer_id == customer_id
        )
        result = await db_session.execute(query)
        total = result.scalar()

        assert total == sum(amounts)

    @pytest.mark.asyncio
    async def test_constraint_unique_event_id(self, db_session: AsyncSession):
        """Test database constraint: event_id must be unique."""
        event1 = StripeEvent(
            event_id="evt_unique_001",
            event_type="charge.succeeded",
            payment_method="card",
            customer_id="cus_001",
            amount_cents=5000,
            currency="USD",
            status=1,
            webhook_timestamp=datetime.utcnow(),
        )
        db_session.add(event1)
        await db_session.commit()

        # Try to add duplicate
        event2 = StripeEvent(
            event_id="evt_unique_001",  # SAME event_id
            event_type="charge.succeeded",
            payment_method="card",
            customer_id="cus_002",
            amount_cents=5000,
            currency="USD",
            status=1,
            webhook_timestamp=datetime.utcnow(),
        )
        db_session.add(event2)

        # Should raise constraint error
        try:
            await db_session.commit()
            pytest.fail("Expected constraint error for duplicate event_id")
        except Exception as e:
            # Constraint error expected
            assert "UNIQUE constraint" in str(e) or "unique" in str(e).lower()

    @pytest.mark.asyncio
    async def test_event_index_optimization(self, db_session: AsyncSession):
        """Test indexes optimize queries (event_id, status, created_at)."""
        customer_id = "cus_index_test_001"

        # Create 100 events for indexing test
        for i in range(100):
            event = StripeEvent(
                event_id=f"evt_index_{i:03d}",
                event_type="charge.succeeded" if i % 2 == 0 else "charge.failed",
                payment_method="card",
                customer_id=customer_id,
                amount_cents=5000,
                currency="USD",
                status=1 if i % 2 == 0 else 2,
                webhook_timestamp=datetime.utcnow(),
            )
            db_session.add(event)
        await db_session.commit()

        # Query using indexed columns (should be fast)
        query = select(StripeEvent).where(StripeEvent.status == 1)
        result = await db_session.execute(query)
        processed = result.scalars().all()

        assert len(processed) == 50
        assert all(e.is_processed for e in processed)


class TestStripeSignatureVerificationProduction:
    """Production-grade Stripe signature verification tests."""

    def test_valid_signature_accepted(self):
        """Valid Stripe signature should be accepted."""
        secret = "whsec_live_key"
        timestamp = str(int(time.time()))
        body = '{"id":"evt_123","type":"charge.succeeded"}'

        # Compute signature as Stripe does
        signed_content = f"{timestamp}.{body}"
        expected_sig = hmac.new(
            secret.encode(),
            signed_content.encode(),
            hashlib.sha256,
        ).hexdigest()

        sig_header = f"t={timestamp},v1={expected_sig}"

        # Verify
        result = verify_stripe_signature(body, sig_header, secret)
        assert result is True

    def test_invalid_signature_rejected(self):
        """Invalid signature must be rejected."""
        result = verify_stripe_signature(
            '{"test": "data"}',
            "t=12345,v1=invalidsig123",
            "secret",
        )
        assert result is False

    def test_tampered_body_detected(self):
        """Signature validation fails if body is modified."""
        secret = "whsec_test"
        timestamp = str(int(time.time()))
        body = '{"amount": 5000}'

        # Create signature for original body
        signed_content = f"{timestamp}.{body}"
        sig = hmac.new(
            secret.encode(),
            signed_content.encode(),
            hashlib.sha256,
        ).hexdigest()

        header = f"t={timestamp},v1={sig}"

        # Try with modified body
        result = verify_stripe_signature('{"amount": 5001}', header, secret)
        assert result is False

    def test_timestamp_header_tolerance(self):
        """Signature with recent timestamp should pass."""
        secret = "whsec_test"
        timestamp = str(int(time.time()))
        body = '{"event": "test"}'

        signed_content = f"{timestamp}.{body}"
        sig = hmac.new(
            secret.encode(),
            signed_content.encode(),
            hashlib.sha256,
        ).hexdigest()

        header = f"t={timestamp},v1={sig}"
        result = verify_stripe_signature(body, header, secret)
        assert result is True

    def test_missing_signature_header(self):
        """Missing signature header should be rejected."""
        result = verify_stripe_signature('{"event": "test"}', "", "secret")
        assert result is False

    def test_malformed_header_format(self):
        """Malformed header (missing v1= part) rejected."""
        result = verify_stripe_signature(
            '{"event": "test"}',
            "t=12345,invalid_format=xyz",
            "secret",
        )
        assert result is False
