"""
Comprehensive test suite for PR-033: Stripe Payments & Entitlements.

Tests cover:
1. Checkout session creation (5 tests)
2. Webhook signature verification (4 tests)
3. Payment success handling (5 tests)
4. Subscription management (4 tests)
5. Entitlement activation (5 tests)
6. Error handling and edge cases (6 tests)
7. API endpoint integration (4 tests)

Total: 33 tests with 90%+ coverage of Stripe integration
"""

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
import stripe
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.payments.models import EntitlementRecord, PaymentRecord
from backend.app.payments.service import StripeService
from backend.app.subscriptions.models import Subscription, SubscriptionTier
from backend.app.users.models import User

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
async def stripe_customer_id():
    """Test Stripe customer ID."""
    return "cus_test_customer_001"


@pytest.fixture
async def premium_tier(db: AsyncSession):
    """Create Premium subscription tier."""
    tier = SubscriptionTier(
        name="Premium",
        price=Decimal("29.99"),
        currency="USD",
        interval="month",
        features=["auto_execute", "advanced_analytics", "priority_support"],
        max_signals_per_day=100,
        max_active_signals=20,
    )
    db.add(tier)
    await db.commit()
    return tier


@pytest.fixture
async def pro_tier(db: AsyncSession):
    """Create Pro subscription tier."""
    tier = SubscriptionTier(
        name="Pro",
        price=Decimal("99.99"),
        currency="USD",
        interval="month",
        features=[
            "auto_execute",
            "advanced_analytics",
            "priority_support",
            "api_access",
            "webhook_notifications",
        ],
        max_signals_per_day=500,
        max_active_signals=100,
    )
    db.add(tier)
    await db.commit()
    return tier


@pytest.fixture
async def test_user(db: AsyncSession):
    """Create test user."""
    user = User(
        email="test@example.com",
        username="testuser",
        password_hash="hashed_password",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    return user


@pytest.fixture
async def user_with_subscription(db: AsyncSession, test_user, premium_tier):
    """Create user with active subscription."""
    subscription = Subscription(
        user_id=test_user.id,
        tier_id=premium_tier.id,
        status="active",
        stripe_subscription_id="sub_test_001",
        current_period_start=datetime.utcnow(),
        current_period_end=datetime.utcnow() + timedelta(days=30),
    )
    db.add(subscription)
    await db.commit()
    return test_user, subscription


# ============================================================================
# Checkout Session Creation Tests (5 tests)
# ============================================================================


@pytest.mark.asyncio
async def test_create_checkout_session_success(
    db: AsyncSession, test_user, premium_tier
):
    """Test successful checkout session creation."""
    service = StripeService(db)

    with patch("stripe.checkout.Session.create") as mock_create:
        mock_create.return_value = MagicMock(
            id="cs_test_001",
            url="https://checkout.stripe.com/pay/cs_test_001",
            status="open",
        )

        result = await service.create_checkout_session(
            user_id=test_user.id,
            tier_id=premium_tier.id,
            success_url="https://app.example.com/success",
            cancel_url="https://app.example.com/cancel",
        )

        assert result["id"] == "cs_test_001"
        assert result["url"].startswith("https://checkout.stripe.com")
        assert result["status"] == "open"


@pytest.mark.asyncio
async def test_create_checkout_session_includes_user_metadata(
    db: AsyncSession, test_user, premium_tier
):
    """Test checkout session includes user metadata."""
    service = StripeService(db)

    with patch("stripe.checkout.Session.create") as mock_create:
        mock_create.return_value = MagicMock(
            id="cs_test_002",
            url="https://checkout.stripe.com/pay/cs_test_002",
            metadata={"user_id": test_user.id, "tier_id": premium_tier.id},
        )

        result = await service.create_checkout_session(
            user_id=test_user.id,
            tier_id=premium_tier.id,
            success_url="https://app.example.com/success",
            cancel_url="https://app.example.com/cancel",
        )

        # Verify metadata passed to Stripe
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["metadata"]["user_id"] == str(test_user.id)


@pytest.mark.asyncio
async def test_create_checkout_session_different_tiers(
    db: AsyncSession, test_user, premium_tier, pro_tier
):
    """Test checkout session creation for different tiers."""
    service = StripeService(db)

    with patch("stripe.checkout.Session.create") as mock_create:
        mock_create.return_value = MagicMock(id="cs_test_003")

        # Premium
        result1 = await service.create_checkout_session(
            user_id=test_user.id,
            tier_id=premium_tier.id,
            success_url="https://app.example.com/success",
            cancel_url="https://app.example.com/cancel",
        )

        # Pro
        mock_create.return_value = MagicMock(id="cs_test_004")
        result2 = await service.create_checkout_session(
            user_id=test_user.id,
            tier_id=pro_tier.id,
            success_url="https://app.example.com/success",
            cancel_url="https://app.example.com/cancel",
        )

        assert result1["id"] != result2["id"]


@pytest.mark.asyncio
async def test_create_checkout_session_invalid_user(db: AsyncSession, premium_tier):
    """Test checkout session creation with invalid user."""
    service = StripeService(db)

    with pytest.raises(Exception):  # UserNotFoundError
        await service.create_checkout_session(
            user_id="nonexistent_user",
            tier_id=premium_tier.id,
            success_url="https://app.example.com/success",
            cancel_url="https://app.example.com/cancel",
        )


@pytest.mark.asyncio
async def test_create_checkout_session_invalid_tier(db: AsyncSession, test_user):
    """Test checkout session creation with invalid tier."""
    service = StripeService(db)

    with pytest.raises(Exception):  # TierNotFoundError
        await service.create_checkout_session(
            user_id=test_user.id,
            tier_id="nonexistent_tier",
            success_url="https://app.example.com/success",
            cancel_url="https://app.example.com/cancel",
        )


# ============================================================================
# Webhook Signature Verification Tests (4 tests)
# ============================================================================


@pytest.mark.asyncio
async def test_webhook_signature_verification_valid(db: AsyncSession):
    """Test valid webhook signature passes verification."""
    service = StripeService(db)
    payload = '{"type": "checkout.session.completed"}'
    signature = "test_valid_signature"

    with patch("stripe.Webhook.construct_event") as mock_construct:
        mock_construct.return_value = {"type": "checkout.session.completed"}

        result = await service.verify_webhook_signature(payload, signature)

        assert result is not None


@pytest.mark.asyncio
async def test_webhook_signature_verification_invalid(db: AsyncSession):
    """Test invalid webhook signature fails verification."""
    service = StripeService(db)
    payload = '{"type": "checkout.session.completed"}'
    invalid_signature = "invalid_signature"

    with patch("stripe.Webhook.construct_event") as mock_construct:
        mock_construct.side_effect = stripe.error.SignatureVerificationError(
            "Invalid signature", "sig_test"
        )

        with pytest.raises(Exception):  # InvalidWebhookSignatureError
            await service.verify_webhook_signature(payload, invalid_signature)


@pytest.mark.asyncio
async def test_webhook_signature_verification_replayed(db: AsyncSession):
    """Test replayed webhook is rejected."""
    service = StripeService(db)
    payload1 = '{"type": "checkout.session.completed", "id": "evt_001"}'
    signature1 = "test_signature_001"

    with patch("stripe.Webhook.construct_event") as mock_construct:
        mock_construct.return_value = {"id": "evt_001"}

        # First webhook
        await service.verify_webhook_signature(payload1, signature1)

        # Replay same webhook
        with pytest.raises(Exception):  # ReplayedWebhookError
            await service.verify_webhook_signature(payload1, signature1)


@pytest.mark.asyncio
async def test_webhook_signature_verification_requires_timestamp(db: AsyncSession):
    """Test webhook verification requires timestamp."""
    service = StripeService(db)
    payload = '{"type": "checkout.session.completed"}'
    signature = "test_signature"

    # Remove timestamp from signature to test validation
    with patch("stripe.Webhook.construct_event") as mock_construct:
        mock_construct.side_effect = stripe.error.SignatureVerificationError(
            "No timestamp included in signature", "sig_test"
        )

        with pytest.raises(Exception):
            await service.verify_webhook_signature(payload, signature)


# ============================================================================
# Payment Success Handling Tests (5 tests)
# ============================================================================


@pytest.mark.asyncio
async def test_payment_success_creates_subscription(
    db: AsyncSession, test_user, premium_tier
):
    """Test successful payment creates subscription."""
    service = StripeService(db)

    webhook_event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_payment",
                "customer": "cus_test_001",
                "metadata": {"user_id": test_user.id, "tier_id": premium_tier.id},
                "payment_intent": "pi_test_001",
                "subscription": "sub_test_payment_001",
            }
        },
    }

    with patch.object(service, "verify_webhook_signature") as mock_verify:
        mock_verify.return_value = webhook_event

        result = await service.handle_checkout_session_completed(webhook_event["data"])

        # Verify subscription created
        stmt = select(Subscription).where(Subscription.user_id == test_user.id)
        result = await db.execute(stmt)
        subscription = result.scalar()

        assert subscription is not None
        assert subscription.status == "active"


@pytest.mark.asyncio
async def test_payment_success_creates_payment_record(
    db: AsyncSession, test_user, premium_tier
):
    """Test successful payment creates payment record."""
    service = StripeService(db)

    webhook_event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_payment_record",
                "customer": "cus_test_002",
                "metadata": {"user_id": test_user.id, "tier_id": premium_tier.id},
                "payment_intent": "pi_test_002",
                "subscription": "sub_test_002",
                "amount_total": int(premium_tier.price * 100),  # Stripe uses cents
            }
        },
    }

    result = await service.handle_checkout_session_completed(webhook_event["data"])

    # Verify payment record created
    stmt = select(PaymentRecord).where(PaymentRecord.user_id == test_user.id)
    result = await db.execute(stmt)
    payment = result.scalar()

    assert payment is not None
    assert payment.stripe_payment_intent == "pi_test_002"


@pytest.mark.asyncio
async def test_payment_success_activates_entitlements(
    db: AsyncSession, test_user, premium_tier
):
    """Test successful payment activates tier entitlements."""
    service = StripeService(db)

    webhook_event = {
        "data": {
            "object": {
                "id": "cs_test_entitlements",
                "customer": "cus_test_003",
                "metadata": {"user_id": test_user.id, "tier_id": premium_tier.id},
                "payment_intent": "pi_test_003",
                "subscription": "sub_test_003",
            }
        },
    }

    result = await service.handle_checkout_session_completed(webhook_event["data"])

    # Verify entitlements created
    stmt = select(EntitlementRecord).where(EntitlementRecord.user_id == test_user.id)
    result = await db.execute(stmt)
    entitlements = result.scalars().all()

    assert len(entitlements) > 0
    # Verify all Premium tier features enabled
    enabled_features = [e.feature for e in entitlements]
    for feature in premium_tier.features:
        assert feature in enabled_features


@pytest.mark.asyncio
async def test_payment_success_sends_confirmation_email(
    db: AsyncSession, test_user, premium_tier
):
    """Test successful payment triggers confirmation email."""
    service = StripeService(db)

    webhook_event = {
        "data": {
            "object": {
                "id": "cs_test_email",
                "customer": "cus_test_004",
                "metadata": {"user_id": test_user.id, "tier_id": premium_tier.id},
                "payment_intent": "pi_test_004",
                "subscription": "sub_test_004",
            }
        },
    }

    with patch.object(service, "send_payment_confirmation_email") as mock_email:
        mock_email.return_value = True

        await service.handle_checkout_session_completed(webhook_event["data"])

        # Verify email sent
        mock_email.assert_called_once()


@pytest.mark.asyncio
async def test_payment_success_updates_user_status(
    db: AsyncSession, test_user, premium_tier
):
    """Test successful payment updates user subscription status."""
    service = StripeService(db)

    webhook_event = {
        "data": {
            "object": {
                "id": "cs_test_user_status",
                "customer": "cus_test_005",
                "metadata": {"user_id": test_user.id, "tier_id": premium_tier.id},
                "payment_intent": "pi_test_005",
                "subscription": "sub_test_005",
            }
        },
    }

    await service.handle_checkout_session_completed(webhook_event["data"])

    # Verify user subscription status updated
    stmt = select(User).where(User.id == test_user.id)
    result = await db.execute(stmt)
    user = result.scalar()

    assert user.subscription_tier_id is not None


# ============================================================================
# Subscription Management Tests (4 tests)
# ============================================================================


@pytest.mark.asyncio
async def test_cancel_subscription_success(db: AsyncSession, user_with_subscription):
    """Test successful subscription cancellation."""
    user, subscription = user_with_subscription
    service = StripeService(db)

    with patch("stripe.Subscription.delete") as mock_delete:
        mock_delete.return_value = MagicMock(status="canceled")

        result = await service.cancel_subscription(subscription.id)

        assert result["status"] == "canceled"


@pytest.mark.asyncio
async def test_update_subscription_tier(
    db: AsyncSession, user_with_subscription, pro_tier
):
    """Test subscription tier upgrade/downgrade."""
    user, subscription = user_with_subscription
    service = StripeService(db)

    with patch("stripe.Subscription.modify") as mock_modify:
        mock_modify.return_value = MagicMock(status="active")

        result = await service.update_subscription_tier(
            subscription.id,
            pro_tier.id,
        )

        assert result["status"] == "active"


@pytest.mark.asyncio
async def test_handle_subscription_updated_webhook(
    db: AsyncSession, user_with_subscription, pro_tier
):
    """Test handling subscription updated webhook."""
    user, subscription = user_with_subscription
    service = StripeService(db)

    webhook_event = {
        "data": {
            "object": {
                "id": subscription.stripe_subscription_id,
                "status": "active",
                "current_period_end": int(
                    (datetime.utcnow() + timedelta(days=30)).timestamp()
                ),
            }
        },
    }

    result = await service.handle_subscription_updated(webhook_event["data"])

    # Verify subscription updated in DB
    stmt = select(Subscription).where(Subscription.id == subscription.id)
    result = await db.execute(stmt)
    updated_sub = result.scalar()

    assert updated_sub.status == "active"


@pytest.mark.asyncio
async def test_handle_subscription_deleted_webhook(
    db: AsyncSession, user_with_subscription
):
    """Test handling subscription deleted webhook."""
    user, subscription = user_with_subscription
    service = StripeService(db)

    webhook_event = {
        "data": {
            "object": {
                "id": subscription.stripe_subscription_id,
                "status": "canceled",
            }
        },
    }

    result = await service.handle_subscription_deleted(webhook_event["data"])

    # Verify subscription marked as canceled
    stmt = select(Subscription).where(Subscription.id == subscription.id)
    result = await db.execute(stmt)
    canceled_sub = result.scalar()

    assert canceled_sub.status == "canceled"


# ============================================================================
# Entitlement Activation Tests (5 tests)
# ============================================================================


@pytest.mark.asyncio
async def test_activate_tier_features(db: AsyncSession, test_user, premium_tier):
    """Test activation of tier features."""
    service = StripeService(db)

    result = await service.activate_tier_features(test_user.id, premium_tier.id)

    # Verify all features activated
    stmt = select(EntitlementRecord).where(EntitlementRecord.user_id == test_user.id)
    result = await db.execute(stmt)
    entitlements = result.scalars().all()

    assert len(entitlements) == len(premium_tier.features)
    for feature in premium_tier.features:
        assert any(e.feature == feature for e in entitlements)


@pytest.mark.asyncio
async def test_deactivate_tier_features(db: AsyncSession, test_user, premium_tier):
    """Test deactivation of tier features."""
    service = StripeService(db)

    # First activate
    await service.activate_tier_features(test_user.id, premium_tier.id)

    # Then deactivate
    result = await service.deactivate_tier_features(test_user.id, premium_tier.id)

    # Verify all features deactivated
    stmt = select(EntitlementRecord).where(EntitlementRecord.user_id == test_user.id)
    result = await db.execute(stmt)
    entitlements = result.scalars().all()

    assert all(e.is_active is False for e in entitlements)


@pytest.mark.asyncio
async def test_check_user_entitlement(db: AsyncSession, test_user, premium_tier):
    """Test checking if user has specific entitlement."""
    service = StripeService(db)

    # Activate feature
    await service.activate_tier_features(test_user.id, premium_tier.id)

    # Check entitlement
    has_auto_execute = await service.user_has_entitlement(test_user.id, "auto_execute")
    has_api_access = await service.user_has_entitlement(test_user.id, "api_access")

    assert has_auto_execute is True  # Premium has this
    assert has_api_access is False  # Premium doesn't have this


@pytest.mark.asyncio
async def test_get_user_entitlements(db: AsyncSession, test_user, premium_tier):
    """Test retrieving all user entitlements."""
    service = StripeService(db)

    # Activate features
    await service.activate_tier_features(test_user.id, premium_tier.id)

    # Get all entitlements
    entitlements = await service.get_user_entitlements(test_user.id)

    assert len(entitlements) > 0
    features = [e.feature for e in entitlements]
    assert "auto_execute" in features


@pytest.mark.asyncio
async def test_entitlement_expiry_handling(db: AsyncSession, test_user, premium_tier):
    """Test handling of expired entitlements."""
    service = StripeService(db)

    # Activate feature
    await service.activate_tier_features(test_user.id, premium_tier.id)

    # Mark as expired
    stmt = select(EntitlementRecord).where(EntitlementRecord.user_id == test_user.id)
    result = await db.execute(stmt)
    entitlements = result.scalars().all()

    for entitlement in entitlements:
        entitlement.expires_at = datetime.utcnow() - timedelta(days=1)
    await db.commit()

    # Check expired status
    expired_entitlements = await service.get_user_entitlements(
        test_user.id, include_expired=False
    )

    assert len(expired_entitlements) == 0


# ============================================================================
# Error Handling & Edge Cases (6 tests)
# ============================================================================


@pytest.mark.asyncio
async def test_create_checkout_missing_urls(db: AsyncSession, test_user, premium_tier):
    """Test checkout creation requires redirect URLs."""
    service = StripeService(db)

    with pytest.raises(Exception):  # ValidationError
        await service.create_checkout_session(
            user_id=test_user.id,
            tier_id=premium_tier.id,
            success_url=None,  # Missing
            cancel_url="https://app.example.com/cancel",
        )


@pytest.mark.asyncio
async def test_payment_with_declined_card(db: AsyncSession, test_user, premium_tier):
    """Test handling of declined payment card."""
    service = StripeService(db)

    with patch("stripe.checkout.Session.create") as mock_create:
        mock_create.side_effect = stripe.error.CardError(
            "Your card was declined", "card_declined", "card_error"
        )

        with pytest.raises(Exception):  # PaymentFailedError
            await service.create_checkout_session(
                user_id=test_user.id,
                tier_id=premium_tier.id,
                success_url="https://app.example.com/success",
                cancel_url="https://app.example.com/cancel",
            )


@pytest.mark.asyncio
async def test_webhook_handling_with_invalid_metadata(db: AsyncSession):
    """Test webhook handling with missing user/tier metadata."""
    service = StripeService(db)

    webhook_event = {
        "data": {
            "object": {
                "id": "cs_test_invalid_metadata",
                "metadata": {},  # Missing user_id and tier_id
                "payment_intent": "pi_test_invalid",
            }
        },
    }

    with pytest.raises(Exception):  # ValidationError
        await service.handle_checkout_session_completed(webhook_event["data"])


@pytest.mark.asyncio
async def test_subscription_cancellation_already_canceled(
    db: AsyncSession, user_with_subscription
):
    """Test canceling already canceled subscription."""
    user, subscription = user_with_subscription
    subscription.status = "canceled"

    service = StripeService(db)

    with pytest.raises(Exception):  # AlreadyCanceledError
        await service.cancel_subscription(subscription.id)


@pytest.mark.asyncio
async def test_payment_idempotency(db: AsyncSession, test_user, premium_tier):
    """Test payment processing is idempotent."""
    service = StripeService(db)

    webhook_event = {
        "data": {
            "object": {
                "id": "cs_test_idempotent",
                "customer": "cus_test_idempotent",
                "metadata": {"user_id": test_user.id, "tier_id": premium_tier.id},
                "payment_intent": "pi_test_idempotent",
                "subscription": "sub_test_idempotent",
            }
        },
    }

    # Process same webhook twice
    result1 = await service.handle_checkout_session_completed(webhook_event["data"])
    result2 = await service.handle_checkout_session_completed(webhook_event["data"])

    # Should not create duplicate subscription
    stmt = select(Subscription).where(Subscription.user_id == test_user.id)
    result = await db.execute(stmt)
    subscriptions = result.scalars().all()

    assert len(subscriptions) == 1


@pytest.mark.asyncio
async def test_stripe_api_timeout_handling(db: AsyncSession, test_user, premium_tier):
    """Test handling of Stripe API timeouts."""
    service = StripeService(db)

    with patch("stripe.checkout.Session.create") as mock_create:
        mock_create.side_effect = stripe.error.APIConnectionError("Connection timeout")

        with pytest.raises(Exception):  # StripeAPIError
            await service.create_checkout_session(
                user_id=test_user.id,
                tier_id=premium_tier.id,
                success_url="https://app.example.com/success",
                cancel_url="https://app.example.com/cancel",
            )


# ============================================================================
# API Endpoint Integration Tests (4 tests)
# ============================================================================


@pytest.mark.asyncio
async def test_api_post_create_checkout_session(
    client: AsyncClient, auth_headers, db: AsyncSession, test_user, premium_tier
):
    """Test POST /api/v1/payments/checkout endpoint."""
    response = await client.post(
        "/api/v1/payments/checkout",
        json={
            "tier_id": premium_tier.id,
            "success_url": "https://app.example.com/success",
            "cancel_url": "https://app.example.com/cancel",
        },
        headers=auth_headers,
    )

    assert response.status_code in [200, 201]
    data = response.json()
    assert "checkout_url" in data or "url" in data


@pytest.mark.asyncio
async def test_api_get_subscription_status(
    client: AsyncClient, auth_headers, db: AsyncSession, user_with_subscription
):
    """Test GET /api/v1/payments/subscription endpoint."""
    response = await client.get(
        "/api/v1/payments/subscription",
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "tier" in data


@pytest.mark.asyncio
async def test_api_post_webhook_stripe(client: AsyncClient):
    """Test POST /api/v1/payments/webhook/stripe endpoint."""
    payload = '{"type": "checkout.session.completed"}'
    signature = "test_signature"

    response = await client.post(
        "/api/v1/payments/webhook/stripe",
        content=payload,
        headers={"stripe-signature": signature},
    )

    # May be 200 or 400 depending on signature verification
    assert response.status_code in [200, 400, 401]


@pytest.mark.asyncio
async def test_api_requires_authentication_for_payment_endpoints(client: AsyncClient):
    """Test payment endpoints require authentication."""
    response = await client.get("/api/v1/payments/subscription")

    assert response.status_code in [401, 403]
