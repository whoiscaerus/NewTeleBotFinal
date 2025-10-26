"""Tests for PR-033, PR-034, PR-035: Payment flows and Mini App bootstrap."""

import hashlib
import hmac
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.models import User
from backend.app.billing.stripe.checkout import (
    CheckoutSessionRequest,
    StripeCheckoutService,
)
from backend.app.billing.stripe.models import StripeEvent
from backend.app.core.settings import get_settings

# ============================================================================
# PR-033: Stripe Payments Tests
# ============================================================================


@pytest.mark.asyncio
class TestStripeCheckout:
    """Test Stripe checkout session creation."""

    async def test_create_checkout_session_valid(
        self,
        db_session: AsyncSession,
        sample_user: User,
    ):
        """Test creating a valid checkout session."""
        service = StripeCheckoutService(db_session)

        request = CheckoutSessionRequest(
            plan_id="premium_monthly",
            user_email="user@example.com",
            success_url="https://app.com/success",
            cancel_url="https://app.com/cancel",
        )

        with patch("stripe.checkout.Session.create") as mock_create:
            mock_session = MagicMock()
            mock_session.id = "cs_test_123"
            mock_session.url = "https://checkout.stripe.com/..."
            mock_create.return_value = mock_session

            response = await service.create_checkout_session(
                request=request,
                user_id=sample_user.id,
            )

            assert response.session_id == "cs_test_123"
            assert response.url == "https://checkout.stripe.com/..."
            mock_create.assert_called_once()

    async def test_create_checkout_session_invalid_plan(
        self,
        db_session: AsyncSession,
        sample_user: User,
    ):
        """Test checkout rejects invalid plan."""
        service = StripeCheckoutService(db_session)

        request = CheckoutSessionRequest(
            plan_id="invalid_plan",
            user_email="user@example.com",
            success_url="https://app.com/success",
            cancel_url="https://app.com/cancel",
        )

        with pytest.raises(ValueError, match="Unknown plan"):
            await service.create_checkout_session(
                request=request,
                user_id=sample_user.id,
            )

    async def test_create_portal_session_valid(
        self,
        db_session: AsyncSession,
    ):
        """Test creating a valid portal session."""
        service = StripeCheckoutService(db_session)

        with patch("stripe.billing.portal.Session.create") as mock_create:
            mock_session = MagicMock()
            mock_session.id = "bps_test_123"
            mock_session.url = "https://billing.stripe.com/..."
            mock_create.return_value = mock_session

            response = await service.create_portal_session(
                customer_id="cus_test_123",
                return_url="https://app.com/billing",
            )

            assert response.url == "https://billing.stripe.com/..."
            mock_create.assert_called_once()

    async def test_get_or_create_customer(
        self,
        db_session: AsyncSession,
        sample_user: User,
    ):
        """Test getting or creating Stripe customer."""
        service = StripeCheckoutService(db_session)

        with patch("stripe.Customer.create") as mock_create:
            mock_customer = MagicMock()
            mock_customer.id = "cus_test_123"
            mock_create.return_value = mock_customer

            customer_id = await service.get_or_create_customer(
                user_id=sample_user.id,
                email="user@example.com",
                name="Test User",
            )

            assert customer_id == "cus_test_123"
            mock_create.assert_called_once()


@pytest.mark.asyncio
class TestStripeWebhook:
    """Test Stripe webhook handling."""

    async def test_webhook_signature_verification_valid(
        self,
        db_session: AsyncSession,
    ):
        """Test valid webhook signature is accepted."""
        from backend.app.billing.stripe.webhooks import verify_stripe_signature

        secret = "whsec_test"
        timestamp = "1234567890"
        body = '{"id":"evt_123"}'

        # Compute correct signature
        signed_content = f"{timestamp}.{body}".encode()
        correct_sig = hmac.new(
            secret.encode("utf-8"),
            signed_content,
            hashlib.sha256,
        ).hexdigest()

        sig_header = f"t={timestamp},v1={correct_sig}"

        result = verify_stripe_signature(body, sig_header, secret)
        assert result is True

    async def test_webhook_signature_verification_invalid(
        self,
        db_session: AsyncSession,
    ):
        """Test invalid webhook signature is rejected."""
        from backend.app.billing.stripe.webhooks import verify_stripe_signature

        secret = "whsec_test"
        sig_header = "t=1234567890,v1=invalid_signature"
        body = '{"id":"evt_123"}'

        result = verify_stripe_signature(body, sig_header, secret)
        assert result is False

    async def test_webhook_charge_succeeded_handler(
        self,
        db_session: AsyncSession,
        sample_user: User,
    ):
        """Test charge.succeeded webhook handler."""
        from backend.app.billing.stripe.handlers import StripeEventHandler

        handler = StripeEventHandler(db_session)

        event = {
            "id": "evt_test_123",
            "type": "charge.succeeded",
            "data": {
                "object": {
                    "id": "ch_test_123",
                    "amount": 2000,
                    "currency": "usd",
                    "customer": "cus_test_123",
                    "metadata": {
                        "user_id": str(sample_user.id),
                        "entitlement_type": "premium",
                    },
                }
            },
        }

        with patch.object(
            handler, "_handle_charge_succeeded", new_callable=AsyncMock
        ) as mock_handler:
            await handler.handle(event)
            mock_handler.assert_called_once_with(event)

    async def test_webhook_charge_failed_handler(
        self,
        db_session: AsyncSession,
    ):
        """Test charge.failed webhook handler."""
        from backend.app.billing.stripe.handlers import StripeEventHandler

        handler = StripeEventHandler(db_session)

        event = {
            "id": "evt_test_456",
            "type": "charge.failed",
            "data": {
                "object": {
                    "id": "ch_test_456",
                    "amount": 2000,
                    "currency": "usd",
                    "failure_message": "Card declined",
                }
            },
        }

        with patch.object(
            handler, "_handle_charge_failed", new_callable=AsyncMock
        ) as mock_handler:
            await handler.handle(event)
            mock_handler.assert_called_once_with(event)


@pytest.mark.asyncio
class TestCheckoutRoutes:
    """Test checkout API routes."""

    async def test_post_checkout_creates_session(
        self,
        client: AsyncClient,
        sample_user: User,
        auth_headers: dict,
    ):
        """Test POST /api/v1/billing/checkout."""
        with patch("stripe.checkout.Session.create") as mock_create:
            mock_session = MagicMock()
            mock_session.id = "cs_test_123"
            mock_session.url = "https://checkout.stripe.com/..."
            mock_create.return_value = mock_session

            response = await client.post(
                "/api/v1/billing/checkout",
                json={
                    "plan_id": "premium_monthly",
                    "user_email": "user@example.com",
                    "success_url": "https://app.com/success",
                    "cancel_url": "https://app.com/cancel",
                },
                headers=auth_headers,
            )

            assert response.status_code == 201
            data = response.json()
            assert data["session_id"] == "cs_test_123"
            assert "url" in data

    async def test_post_checkout_requires_auth(
        self,
        client: AsyncClient,
    ):
        """Test checkout requires authentication."""
        response = await client.post(
            "/api/v1/billing/checkout",
            json={
                "plan_id": "premium_monthly",
                "user_email": "user@example.com",
                "success_url": "https://app.com/success",
                "cancel_url": "https://app.com/cancel",
            },
        )

        assert response.status_code == 401


# ============================================================================
# PR-034: Telegram Native Payments Tests
# ============================================================================


@pytest.mark.asyncio
class TestTelegramPayments:
    """Test Telegram Stars payment handling."""

    async def test_handle_telegram_successful_payment(
        self,
        db_session: AsyncSession,
        sample_user: User,
    ):
        """Test successful Telegram Stars payment."""
        from backend.app.telegram.payments import TelegramPaymentHandler

        handler = TelegramPaymentHandler(db_session)

        with patch(
            "backend.app.billing.entitlements.service.EntitlementService.grant_entitlement",
            new_callable=AsyncMock,
        ) as mock_grant:
            mock_entitlement = MagicMock()
            mock_entitlement.id = str(uuid4())
            mock_grant.return_value = mock_entitlement

            await handler.handle_successful_payment(
                user_id=str(sample_user.id),
                entitlement_type="premium",
                invoice_id="inv_123",
                telegram_payment_charge_id="tg_charge_123",
                provider_payment_charge_id="provider_charge_456",
                total_amount=500,
            )

            mock_grant.assert_called_once()

    async def test_telegram_payment_idempotency(
        self,
        db_session: AsyncSession,
        sample_user: User,
    ):
        """Test duplicate Telegram payment is idempotent."""
        from backend.app.telegram.payments import TelegramPaymentHandler

        handler = TelegramPaymentHandler(db_session)

        # Add existing event
        existing_event = StripeEvent(
            event_id="tg_charge_123",
            event_type="telegram_stars.successful_payment",
            payment_method="telegram_stars",
            customer_id=str(sample_user.id),
            amount_cents=500,
            currency="XTR",
            status=1,  # processed
        )
        db_session.add(existing_event)
        await db_session.commit()

        with patch(
            "backend.app.billing.entitlements.service.EntitlementService.grant_entitlement",
            new_callable=AsyncMock,
        ) as mock_grant:
            await handler.handle_successful_payment(
                user_id=str(sample_user.id),
                entitlement_type="premium",
                invoice_id="inv_123",
                telegram_payment_charge_id="tg_charge_123",
                provider_payment_charge_id="provider_charge_456",
                total_amount=500,
            )

            # Should not grant again (idempotent)
            mock_grant.assert_not_called()

    async def test_telegram_payment_refund(
        self,
        db_session: AsyncSession,
        sample_user: User,
    ):
        """Test Telegram Stars refund handling."""
        from backend.app.telegram.payments import TelegramPaymentHandler

        handler = TelegramPaymentHandler(db_session)

        with patch(
            "backend.app.billing.entitlements.service.EntitlementService.revoke_entitlement",
            new_callable=AsyncMock,
        ) as mock_revoke:
            await handler.handle_refund(
                user_id=str(sample_user.id),
                entitlement_type="premium",
                telegram_payment_charge_id="tg_charge_123",
            )

            mock_revoke.assert_called_once()


# ============================================================================
# PR-035: Mini App Bootstrap Tests
# ============================================================================


class TestMiniAppAuthBridge:
    """Test Mini App authentication bridge."""

    def test_verify_telegram_initdata_valid(self):
        """Test valid Telegram initData signature verification."""
        from datetime import datetime

        from backend.app.miniapp.auth_bridge import verify_telegram_init_data

        # Mock bot token
        bot_token = "123:ABC"

        # Create valid initData with CURRENT timestamp (must be within 15 minutes)
        user_data = {"id": 123, "first_name": "Test", "is_bot": False}
        auth_date = int(datetime.utcnow().timestamp())
        data_parts = [
            f"auth_date={auth_date}",
            f"user={json.dumps(user_data)}",
        ]
        data_check_string = "\n".join(data_parts)

        # Compute hash
        secret_key = hashlib.sha256(bot_token.encode()).digest()
        hash_value = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256,
        ).hexdigest()

        # Create full initData string
        init_data = (
            f"auth_date={auth_date}&user={json.dumps(user_data)}&hash={hash_value}"
        )

        # Should verify successfully
        result = verify_telegram_init_data(init_data, bot_token)
        assert result["user"]["id"] == 123

    def test_verify_telegram_initdata_invalid_signature(self):
        """Test invalid Telegram initData signature is rejected."""
        from backend.app.miniapp.auth_bridge import verify_telegram_init_data

        bot_token = "123:ABC"
        init_data = "auth_date=1693000000&hash=invalid_signature"

        with pytest.raises(ValueError, match="Signature verification failed"):
            verify_telegram_init_data(init_data, bot_token)

    def test_verify_telegram_initdata_too_old(self):
        """Test old Telegram initData is rejected."""
        from backend.app.miniapp.auth_bridge import verify_telegram_init_data

        bot_token = "123:ABC"

        # Create initData with very old timestamp (1 hour ago)
        old_auth_date = int(datetime.utcnow().timestamp()) - 3600
        user_data = {"id": 123, "first_name": "Test"}
        data_parts = [
            f"auth_date={old_auth_date}",
            f"user={json.dumps(user_data)}",
        ]
        data_check_string = "\n".join(data_parts)

        secret_key = hashlib.sha256(bot_token.encode()).digest()
        hash_value = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256,
        ).hexdigest()

        init_data = (
            f"auth_date={old_auth_date}&user={json.dumps(user_data)}&hash={hash_value}"
        )

        with pytest.raises(ValueError, match="initData too old"):
            verify_telegram_init_data(init_data, bot_token)

    @pytest.mark.asyncio
    async def test_exchange_initdata_endpoint(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test POST /api/v1/miniapp/exchange-initdata."""

        # Create valid initData
        bot_token = get_settings().telegram_bot_token
        user_data = {"id": 123, "first_name": "Test", "is_bot": False}
        auth_date = int(datetime.utcnow().timestamp())
        data_parts = [
            f"auth_date={auth_date}",
            f"user={json.dumps(user_data)}",
        ]
        data_check_string = "\n".join(data_parts)

        secret_key = hashlib.sha256(bot_token.encode()).digest()
        hash_value = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256,
        ).hexdigest()

        init_data = (
            f"auth_date={auth_date}&user={json.dumps(user_data)}&hash={hash_value}"
        )

        response = await client.post(
            "/api/v1/miniapp/exchange-initdata",
            json={"init_data": init_data},
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] == 900

    @pytest.mark.asyncio
    async def test_exchange_initdata_invalid_signature(
        self,
        client: AsyncClient,
    ):
        """Test invalid initData rejected on exchange."""
        response = await client.post(
            "/api/v1/miniapp/exchange-initdata",
            json={"init_data": "invalid_data&hash=wrong"},
        )

        assert response.status_code == 401


# ============================================================================
# Integration Tests
# ============================================================================


@pytest.mark.asyncio
class TestPaymentIntegration:
    """Integration tests for payment flow."""

    async def test_checkout_to_entitlement_flow(
        self,
        client: AsyncClient,
        sample_user: User,
        auth_headers: dict,
        db_session: AsyncSession,
    ):
        """Test complete flow: checkout → webhook → entitlement."""
        # Step 1: Create checkout session
        with patch("stripe.checkout.Session.create") as mock_checkout:
            mock_session = MagicMock()
            mock_session.id = "cs_test_flow"
            mock_session.url = "https://checkout.stripe.com/..."
            mock_checkout.return_value = mock_session

            response = await client.post(
                "/api/v1/billing/checkout",
                json={
                    "plan_id": "premium_monthly",
                    "user_email": "user@example.com",
                    "success_url": "https://app.com/success",
                    "cancel_url": "https://app.com/cancel",
                },
                headers=auth_headers,
            )

            assert response.status_code == 201
            checkout_data = response.json()
            assert checkout_data["session_id"]  # Verify session created

            # Step 2: Simulate webhook callback
            from backend.app.billing.stripe.handlers import StripeEventHandler

            event = {
                "id": "evt_test_flow",
                "type": "charge.succeeded",
                "data": {
                    "object": {
                        "id": "ch_test_flow",
                        "amount": 2000,
                        "currency": "usd",
                        "customer": "cus_test_flow",
                        "metadata": {
                            "user_id": str(sample_user.id),
                            "entitlement_type": "premium",
                        },
                    }
                },
            }

            handler = StripeEventHandler(db_session)

            with patch(
                "backend.app.billing.entitlements.service.EntitlementService.grant_entitlement",
                new_callable=AsyncMock,
            ) as mock_grant:
                mock_entitlement = MagicMock()
                mock_entitlement.id = str(uuid4())
                mock_grant.return_value = mock_entitlement

                await handler._handle_charge_succeeded(event)
                mock_grant.assert_called_once()


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
async def sample_user(db_session: AsyncSession) -> User:
    """Create a sample user for tests."""
    user = User(
        email="test@example.com",
        name="Test User",
        hashed_password="hashed_password_here",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers(sample_user: User) -> dict:
    """Create auth headers with valid JWT."""
    from backend.app.auth.jwt_handler import JWTHandler

    jwt_handler = JWTHandler()
    token = jwt_handler.create_token(user_id=str(sample_user.id))
    return {"Authorization": f"Bearer {token}"}
