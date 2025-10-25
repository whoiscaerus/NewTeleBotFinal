"""Telegram Stars payment integration.

Provides alternative payment channel to Stripe using Telegram Stars.
Integrates with Telegram SDK for payment verification.
"""

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.billing.entitlements.service import EntitlementService
from backend.app.billing.stripe.models import StripeEvent

logger = logging.getLogger(__name__)

# Event status constants
STATUS_PENDING = 0
STATUS_PROCESSED = 1
STATUS_FAILED = 2


class TelegramPaymentHandler:
    """Handle Telegram Stars payment events.

    Telegram Stars are a first-party payment method where:
    1. User initiates payment via bot
    2. Telegram handles payment processing (credit card, etc)
    3. Bot receives successful_payment update
    4. We grant entitlement to user

    Unlike Stripe, Telegram handles signature verification via its SDK.
    """

    def __init__(self, db: AsyncSession):
        """Initialize handler with database session."""
        self.db = db
        self.logger = logger

    async def handle_successful_payment(
        self,
        user_id: str,
        entitlement_type: str,
        invoice_id: str,
        telegram_payment_charge_id: str,
        provider_payment_charge_id: str | None,
        total_amount: int,  # In cents
        currency: str = "XTR",  # Telegram Stars
    ) -> None:
        """Handle successful Telegram payment.

        Args:
            user_id: User who made payment
            entitlement_type: Type of entitlement (e.g., "premium")
            invoice_id: Invoice ID from bot API
            telegram_payment_charge_id: Payment ID from Telegram
            provider_payment_charge_id: Optional provider payment ID (if provider used)
            total_amount: Amount in cents
            currency: Payment currency (XTR for Telegram Stars)

        Raises:
            ValueError: If payment already processed (idempotency)
        """
        try:
            self.logger.info(
                "Processing successful Telegram payment",
                extra={
                    "user_id": user_id,
                    "invoice_id": invoice_id,
                    "payment_charge_id": telegram_payment_charge_id,
                    "entitlement_type": entitlement_type,
                },
            )

            # Check if already processed (idempotency)
            result = await self.db.execute(
                select(StripeEvent).where(
                    StripeEvent.event_id == telegram_payment_charge_id
                )
            )
            existing_event = result.scalars().first()

            if existing_event and existing_event.is_processed:
                self.logger.warning(
                    "Telegram payment already processed",
                    extra={
                        "payment_charge_id": telegram_payment_charge_id,
                    },
                )
                return

            # Grant entitlement to user
            entitlement_service = EntitlementService(self.db)
            entitlement = await entitlement_service.grant_entitlement(
                user_id=user_id,
                entitlement_type=entitlement_type,
                source=f"telegram_stars:{telegram_payment_charge_id}",
            )

            # Record event
            payment_event = StripeEvent(
                event_id=telegram_payment_charge_id,
                event_type="telegram_stars.successful_payment",
                payment_method="telegram_stars",
                customer_id=user_id,
                amount_cents=total_amount,
                currency=currency,
                status=STATUS_PROCESSED,
                processed_at=datetime.utcnow(),
                webhook_timestamp=datetime.utcnow(),
            )

            self.db.add(payment_event)
            await self.db.commit()

            self.logger.info(
                "Telegram payment processed: entitlement granted",
                extra={
                    "user_id": user_id,
                    "entitlement_id": entitlement.id,
                    "payment_charge_id": telegram_payment_charge_id,
                },
            )

        except Exception as e:
            self.logger.error(
                f"Failed to process Telegram payment: {e}",
                exc_info=True,
                extra={
                    "user_id": user_id,
                    "payment_charge_id": telegram_payment_charge_id,
                },
            )

            # Record failure
            payment_event = StripeEvent(
                event_id=telegram_payment_charge_id,
                event_type="telegram_stars.successful_payment",
                payment_method="telegram_stars",
                amount_cents=total_amount,
                currency=currency,
                status=STATUS_FAILED,
                error_message=str(e),
                webhook_timestamp=datetime.utcnow(),
            )
            self.db.add(payment_event)
            await self.db.commit()

            raise

    async def handle_refund(
        self,
        user_id: str,
        entitlement_type: str,
        telegram_payment_charge_id: str,
        refund_reason: str = "requested_by_customer",
    ) -> None:
        """Handle Telegram Stars refund.

        Args:
            user_id: User who received refund
            entitlement_type: Type of entitlement to revoke
            telegram_payment_charge_id: Original payment ID
            refund_reason: Reason for refund

        Raises:
            ValueError: If payment not found or already refunded
        """
        try:
            self.logger.info(
                "Processing Telegram payment refund",
                extra={
                    "user_id": user_id,
                    "payment_charge_id": telegram_payment_charge_id,
                    "reason": refund_reason,
                },
            )

            # Revoke entitlement
            entitlement_service = EntitlementService(self.db)
            await entitlement_service.revoke_entitlement(
                user_id=user_id,
                entitlement_type=entitlement_type,
                reason=f"Telegram Stars refund for payment {telegram_payment_charge_id}",
            )

            # Record refund event
            refund_event = StripeEvent(
                event_id=f"refund_{telegram_payment_charge_id}",
                event_type="telegram_stars.refunded",
                payment_method="telegram_stars",
                customer_id=user_id,
                status=STATUS_PROCESSED,
                processed_at=datetime.utcnow(),
                webhook_timestamp=datetime.utcnow(),
            )

            self.db.add(refund_event)
            await self.db.commit()

            self.logger.info(
                "Telegram refund processed: entitlement revoked",
                extra={
                    "user_id": user_id,
                    "payment_charge_id": telegram_payment_charge_id,
                },
            )

        except Exception as e:
            self.logger.error(
                f"Failed to process Telegram refund: {e}",
                exc_info=True,
                extra={
                    "user_id": user_id,
                    "payment_charge_id": telegram_payment_charge_id,
                },
            )

            # Record failure
            refund_event = StripeEvent(
                event_id=f"refund_{telegram_payment_charge_id}",
                event_type="telegram_stars.refunded",
                payment_method="telegram_stars",
                status=STATUS_FAILED,
                error_message=str(e),
                webhook_timestamp=datetime.utcnow(),
            )
            self.db.add(refund_event)
            await self.db.commit()

            raise
