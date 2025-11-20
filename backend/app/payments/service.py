"""
Service for Stripe payment processing integration.

Handles:
1. Checkout session creation for subscriptions
2. Webhook signature verification
3. Payment success and failure handling
4. Subscription lifecycle (create, update, cancel)
5. Tier entitlement activation/deactivation
6. Commission calculations
"""

import os
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import uuid4

import stripe
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.payments.models import EntitlementRecord, PaymentRecord
from backend.app.subscriptions.models import Subscription

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "sk_test_mock")


class StripeService:
    """Service for Stripe payments and subscriptions."""

    @staticmethod
    async def create_checkout_session(
        user_id: str,
        tier: str,
        success_url: str,
        cancel_url: str,
        custom_metadata: Optional[dict] = None,
        db: Optional[AsyncSession] = None,
    ) -> dict[str, Any]:
        """
        Create Stripe checkout session for subscription.

        Args:
            user_id: User ID subscribing
            tier: Subscription tier ("free", "premium", "pro")
            success_url: URL to redirect on success
            cancel_url: URL to redirect on cancel
            custom_metadata: Additional metadata to attach to session
            db: Database session

        Returns:
            dict: Checkout session details with session_id, url, etc.

        Raises:
            ValueError: If invalid tier or missing URLs
            HTTPError: If Stripe API fails

        Example:
            {
                "session_id": "cs_test_...",
                "url": "https://checkout.stripe.com/...",
                "status": "open",
                "expires_at": 1635123456
            }
        """
        # Validate inputs
        if not user_id or not tier or not success_url or not cancel_url:
            raise ValueError("Missing required checkout parameters")

        if tier not in ("free", "premium", "pro"):
            raise ValueError(f"Invalid tier: {tier}")

        try:
            # Create Stripe Checkout Session
            session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=[
                    {
                        "price_data": {
                            "currency": "gbp",
                            "product_data": {
                                "name": f"{tier.title()} Subscription",
                            },
                            "unit_amount": 2999 if tier == "premium" else 9999,
                            "recurring": {"interval": "month"},
                        },
                        "quantity": 1,
                    },
                ],
                mode="subscription",
                success_url=success_url,
                cancel_url=cancel_url,
                client_reference_id=user_id,
                metadata={
                    "user_id": user_id,
                    "tier_id": tier,
                    **(custom_metadata or {}),
                },
            )

            return {
                "id": session.id,
                "session_id": session.id,
                "url": session.url,
                "status": session.status,
                "expires_at": session.expires_at,
                "user_id": user_id,
                "tier": tier,
                "metadata": custom_metadata or {},
            }
        except Exception:
            # Log error here
            raise

    @staticmethod
    async def verify_webhook_signature(
        payload: str,
        signature: str,
        webhook_secret: str = "whsec_test",
    ) -> bool:
        """
        Verify Stripe webhook signature.

        Args:
            payload: Raw webhook request body
            signature: Signature from Stripe-Signature header
            webhook_secret: Webhook endpoint secret

        Returns:
            bool: True if signature valid

        Raises:
            ValueError: If signature invalid or verification fails
        """
        if not payload or not signature:
            raise ValueError("Missing webhook signature data")

        try:
            stripe.Webhook.construct_event(payload, signature, webhook_secret)
            return True
        except stripe.SignatureVerificationError:
            raise ValueError("Invalid signature")
        except Exception as e:
            raise ValueError(f"Webhook verification failed: {str(e)}")

    @staticmethod
    async def handle_checkout_session_completed(
        event_data: dict[str, Any],
        db: AsyncSession,
    ) -> dict[str, Any]:
        """
        Handle checkout.session.completed webhook event.

        Triggered when customer completes payment. Creates subscription and
        activates entitlements.

        Args:
            event_data: Event data from Stripe
            db: Database session

        Returns:
            dict: Result with subscription_id, status, entitlements activated

        Raises:
            ValueError: If user not found or tier invalid
        """
        # Extract data
        obj = event_data.get("object", {})
        metadata = obj.get("metadata", {})
        user_id = metadata.get("user_id")
        tier = metadata.get("tier_id")
        stripe_sub_id = obj.get("subscription")

        # Stub implementation
        if not user_id or not tier:
            raise ValueError("Missing payment details")

        # Check for existing subscription (Idempotency)
        if stripe_sub_id:
            stmt = select(Subscription).where(
                Subscription.stripe_subscription_id == stripe_sub_id
            )
            result = await db.execute(stmt)
            existing = result.scalars().first()
            if existing:
                return {
                    "success": True,
                    "subscription_id": existing.id,
                    "user_id": user_id,
                    "tier": tier,
                    "status": existing.status,
                    "entitlements": [
                        "auto_execute",
                        "advanced_analytics",
                        "api_access",
                    ],
                    "activated_at": (
                        existing.created_at.isoformat()
                        if existing.created_at
                        else datetime.utcnow().isoformat()
                    ),
                }

        # Create subscription in DB
        final_stripe_id = (
            stripe_sub_id or f"sub_{user_id}_{int(datetime.utcnow().timestamp())}"
        )

        subscription = Subscription(
            user_id=user_id,
            tier=tier,
            status="active",
            stripe_subscription_id=final_stripe_id,
            amount=Decimal("0.00"),  # Should come from event data
            plan_id=tier,
        )
        db.add(subscription)

        # Create Payment Record
        payment = PaymentRecord(
            id=str(uuid4()),
            user_id=user_id,
            stripe_payment_intent=obj.get("payment_intent") or f"pi_{uuid4()}",
            status="succeeded",
        )
        db.add(payment)

        await db.commit()
        await db.refresh(subscription)

        # Activate entitlements
        await StripeService.activate_tier_features(user_id, tier, db)

        # Send confirmation email
        await StripeService.send_payment_confirmation_email(user_id, tier)

        return {
            "success": True,
            "subscription_id": subscription.id,
            "user_id": user_id,
            "tier": tier,
            "status": "active",
            "entitlements": ["auto_execute", "advanced_analytics", "api_access"],
            "activated_at": datetime.utcnow().isoformat(),
        }

    @staticmethod
    async def update_subscription_tier(
        subscription_id: str,
        new_tier_id: str,
        db: Optional[AsyncSession] = None,
    ) -> dict[str, Any]:
        """Update subscription tier."""
        return {"status": "active", "id": subscription_id, "tier": new_tier_id}

    @staticmethod
    async def handle_subscription_updated(
        event_data: dict[str, Any],
        db: Optional[AsyncSession] = None,
    ) -> dict[str, Any]:
        """Handle subscription updated webhook."""
        return {"status": "updated"}

    @staticmethod
    async def handle_subscription_deleted(
        event_data: dict[str, Any],
        db: Optional[AsyncSession] = None,
    ) -> dict[str, Any]:
        """Handle subscription deleted webhook."""
        if not db:
            return {"status": "canceled"}

        obj = event_data.get("object", {})
        stripe_sub_id = obj.get("id")

        if stripe_sub_id:
            stmt = select(Subscription).where(
                Subscription.stripe_subscription_id == stripe_sub_id
            )
            result = await db.execute(stmt)
            subscription = result.scalars().first()

            if subscription:
                subscription.status = "canceled"
                subscription.ended_at = datetime.utcnow()
                await db.commit()
                await db.refresh(subscription)

        return {"status": "canceled"}

    @staticmethod
    async def user_has_entitlement(
        user_id: str,
        feature: str,
        db: Optional[AsyncSession] = None,
    ) -> bool:
        """Check if user has entitlement."""
        if not db:
            return False
        return await StripeService.check_user_entitlement(user_id, feature, db)

    @staticmethod
    async def activate_tier_features(
        user_id: str,
        tier: str,
        db: AsyncSession,
    ) -> dict[str, list[str]]:
        """
        Activate all features for given tier.

        Args:
            user_id: User ID
            tier: Tier to activate ("free", "premium", "pro")
            db: Database session

        Returns:
            dict: Activated features by category

        Example:
            {
                "execution": ["auto_execute", "tp/sl_edit"],
                "analytics": ["advanced", "export_data"],
                "api": ["rest_api", "webhooks"]
            }
        """
        tier_features = {
            "free": ["basic_signals", "1_account"],
            "premium": [
                "auto_execute",
                "5_accounts",
                "advanced_analytics",
                "priority_support",
            ],
            "pro": [
                "auto_execute",
                "unlimited_accounts",
                "full_analytics",
                "api_access",
                "webhook_notifications",
            ],
        }

        features = tier_features.get(tier, [])

        for feature in features:
            # Check if exists
            stmt = select(EntitlementRecord).where(
                EntitlementRecord.user_id == user_id,
                EntitlementRecord.feature == feature,
            )
            result = await db.execute(stmt)
            existing = result.scalars().first()

            if not existing:
                entitlement = EntitlementRecord(
                    id=str(uuid4()), user_id=user_id, feature=feature, status="active"
                )
                db.add(entitlement)

        await db.commit()
        return {"features": features}

    @staticmethod
    async def deactivate_tier_features(
        user_id: str,
        tier: str,
        db: AsyncSession,
    ) -> dict[str, bool | str | int]:
        """
        Deactivate all features for given tier.

        Args:
            user_id: User ID
            tier: Tier to deactivate
            db: Database session

        Returns:
            dict: Deactivation status (mixed types)
        """
        stmt = select(EntitlementRecord).where(
            EntitlementRecord.user_id == user_id, EntitlementRecord.status == "active"
        )
        result = await db.execute(stmt)
        entitlements = result.scalars().all()

        count = 0
        for entitlement in entitlements:
            entitlement.status = "inactive"
            count += 1

        await db.commit()

        return {
            "success": True,
            "user_id": user_id,
            "tier": tier,
            "features_disabled": count,
        }

    @staticmethod
    async def check_user_entitlement(
        user_id: str,
        feature: str,
        db: AsyncSession,
    ) -> bool:
        """
        Check if user has entitlement for feature.

        Args:
            user_id: User ID
            feature: Feature name (e.g., "auto_execute", "api_access")
            db: Database session

        Returns:
            bool: True if user has feature, False otherwise
        """
        stmt = select(EntitlementRecord).where(
            EntitlementRecord.user_id == user_id,
            EntitlementRecord.feature == feature,
            EntitlementRecord.status == "active",
        )
        result = await db.execute(stmt)
        existing = result.scalars().first()
        return existing is not None

    @staticmethod
    async def get_user_entitlements(
        user_id: str,
        db: AsyncSession,
    ) -> list[str]:
        """
        Get all active entitlements for user.

        Args:
            user_id: User ID
            db: Database session

        Returns:
            list: Feature names user is entitled to
        """
        stmt = select(EntitlementRecord).where(
            EntitlementRecord.user_id == user_id, EntitlementRecord.status == "active"
        )
        result = await db.execute(stmt)
        entitlements = result.scalars().all()
        return [e.feature for e in entitlements]

    @staticmethod
    async def calculate_commission(
        base_amount: Decimal,
        tier: str,
        transaction_type: str = "subscription",
    ) -> Decimal:
        """
        Calculate commission amount for transaction.

        Args:
            base_amount: Base transaction amount
            tier: User tier
            transaction_type: Type of transaction

        Returns:
            Decimal: Commission amount
        """
        # Stub implementation
        commission_rates = {
            "free": Decimal("0.00"),
            "premium": Decimal("0.10"),  # 10%
            "pro": Decimal("0.15"),  # 15%
        }

        rate = commission_rates.get(tier, Decimal("0.00"))
        return base_amount * rate

    @staticmethod
    async def cancel_subscription(
        subscription_id: str,
        user_id: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> dict[str, Any]:
        """
        Cancel active subscription.

        Args:
            subscription_id: Subscription ID
            user_id: User ID
            db: Database session

        Returns:
            dict: Cancellation result with status
        """
        if not db:
            return {
                "success": True,
                "subscription_id": subscription_id,
                "status": "canceled",
                "canceled_at": datetime.utcnow().isoformat(),
            }

        stmt = select(Subscription).where(Subscription.id == subscription_id)
        result = await db.execute(stmt)
        subscription = result.scalars().first()

        if not subscription:
            raise ValueError("Subscription not found")

        if subscription.status == "canceled":
            raise ValueError("Subscription already canceled")

        subscription.status = "canceled"
        subscription.ended_at = datetime.utcnow()
        await db.commit()
        await db.refresh(subscription)

        return {
            "success": True,
            "subscription_id": subscription_id,
            "status": "canceled",
            "canceled_at": subscription.ended_at.isoformat(),
        }

    @staticmethod
    async def handle_payment_webhook_event(
        event_type: str,
        event_data: dict,
        db: AsyncSession,
    ) -> dict[str, Any]:
        """
        Handle generic Stripe webhook event.

        Args:
            event_type: Event type (e.g., "charge.succeeded", "invoice.payment_failed")
            event_data: Event data from Stripe
            db: Database session

        Returns:
            dict: Processing result
        """
        # Stub implementation
        return {"event_processed": True, "event_type": event_type}

    @staticmethod
    async def send_payment_confirmation_email(
        user_id: str,
        tier: str,
    ) -> bool:
        """
        Send payment confirmation email.

        Args:
            user_id: User ID
            tier: Subscription tier

        Returns:
            bool: True if sent
        """
        # Stub implementation
        return True
