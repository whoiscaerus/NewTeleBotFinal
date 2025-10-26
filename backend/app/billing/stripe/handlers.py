"""Stripe event handlers for charge and refund processing."""

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.billing.entitlements.service import EntitlementService
from backend.app.billing.stripe.models import StripeEvent

logger = logging.getLogger(__name__)

# Event status constants
STATUS_PENDING = 0
STATUS_PROCESSED = 1
STATUS_FAILED = 2


class StripeEventHandler:
    """Process Stripe webhook events.

    Handles:
    - charge.succeeded: Grant entitlement to user
    - charge.failed: Log failure, send alert
    - charge.refunded: Revoke entitlement
    """

    def __init__(self, db: AsyncSession):
        """Initialize handler with database session."""
        self.db = db
        self.logger = logger

    async def handle(self, event: dict[str, Any]) -> None:
        """Route event to appropriate handler based on type.

        Args:
            event: Stripe webhook event object

        Raises:
            ValueError: Unknown event type
        """
        event_id = event.get("id")
        event_type = event.get("type")

        self.logger.info(
            f"Routing Stripe event: {event_type}", extra={"event_id": event_id}
        )

        # Check for duplicate event (idempotency)
        existing_event = await self.db.scalar(
            select(StripeEvent).where(StripeEvent.event_id == event_id)
        )
        if existing_event:
            self.logger.info(
                "Event already processed, skipping",
                extra={"event_id": event_id, "event_type": event_type},
            )
            return

        if event_type == "charge.succeeded":
            await self._handle_charge_succeeded(event)
        elif event_type == "charge.failed":
            await self._handle_charge_failed(event)
        elif event_type == "charge.refunded":
            await self._handle_charge_refunded(event)
        else:
            self.logger.warning(f"Unhandled event type: {event_type}")

    async def _handle_charge_succeeded(self, event: dict[str, Any]) -> None:
        """Handle successful charge: grant entitlement to user.

        Args:
            event: Stripe charge.succeeded event

        Expected event structure:
            {
                "id": "evt_1234567890",
                "type": "charge.succeeded",
                "data": {
                    "object": {
                        "id": "ch_1234567890",
                        "amount": 2000,
                        "currency": "usd",
                        "customer": "cus_1234567890",
                        "metadata": {
                            "user_id": "user-uuid-here",
                            "entitlement_type": "premium"
                        }
                    }
                }
            }
        """
        try:
            event_id = event.get("id")
            charge = event.get("data", {}).get("object", {})
            charge_id = charge.get("id")
            amount_cents = charge.get("amount")
            currency = charge.get("currency", "usd")
            metadata = charge.get("metadata", {})

            user_id = metadata.get("user_id")
            entitlement_type = metadata.get("entitlement_type", "premium")

            if not user_id:
                raise ValueError("Missing user_id in charge metadata")

            self.logger.info(
                "Processing successful charge",
                extra={
                    "event_id": event_id,
                    "charge_id": charge_id,
                    "user_id": user_id,
                    "entitlement_type": entitlement_type,
                },
            )

            # Create Stripe event record
            stripe_event = StripeEvent(
                event_id=event_id,
                event_type="charge.succeeded",
                payment_method="stripe",
                customer_id=charge.get("customer"),
                amount_cents=amount_cents,
                currency=currency.upper(),
                status=STATUS_PENDING,
                webhook_timestamp=datetime.fromtimestamp(event.get("created", 0)),
            )

            # Grant entitlement
            entitlement_service = EntitlementService(self.db)
            entitlement = await entitlement_service.grant_entitlement(
                user_id=user_id,
                entitlement_type=entitlement_type,
                source=f"stripe:{charge_id}",
            )

            # Mark event as processed
            stripe_event.status = STATUS_PROCESSED
            stripe_event.processed_at = datetime.utcnow()

            self.db.add(stripe_event)
            await self.db.commit()

            self.logger.info(
                "Charge succeeded: entitlement granted",
                extra={
                    "event_id": event_id,
                    "user_id": user_id,
                    "entitlement_id": entitlement.id,
                },
            )

        except Exception as e:
            self.logger.error(
                f"Failed to handle charge succeeded: {e}",
                exc_info=True,
                extra={"event_id": event.get("id")},
            )

            # Record failure
            stripe_event = StripeEvent(
                event_id=event.get("id"),
                event_type="charge.succeeded",
                payment_method="stripe",
                amount_cents=event.get("data", {}).get("object", {}).get("amount"),
                currency=event.get("data", {}).get("object", {}).get("currency", "USD"),
                status=STATUS_FAILED,
                error_message=str(e),
                webhook_timestamp=datetime.fromtimestamp(event.get("created", 0)),
            )
            self.db.add(stripe_event)
            await self.db.commit()

            raise

    async def _handle_charge_failed(self, event: dict[str, Any]) -> None:
        """Handle failed charge: log and alert user.

        Args:
            event: Stripe charge.failed event
        """
        try:
            event_id = event.get("id")
            charge = event.get("data", {}).get("object", {})
            charge_id = charge.get("id")
            amount_cents = charge.get("amount")
            failure_message = charge.get("failure_message")

            self.logger.warning(
                f"Charge failed: {failure_message}",
                extra={
                    "event_id": event_id,
                    "charge_id": charge_id,
                    "failure_message": failure_message,
                },
            )

            # Record failure event
            stripe_event = StripeEvent(
                event_id=event_id,
                event_type="charge.failed",
                payment_method="stripe",
                amount_cents=amount_cents,
                currency=charge.get("currency", "USD"),
                status=STATUS_PROCESSED,
                error_message=failure_message,
                webhook_timestamp=datetime.fromtimestamp(event.get("created", 0)),
            )

            self.db.add(stripe_event)
            await self.db.commit()

            # TODO: Send alert to user (PR-018 alerts framework)

        except Exception as e:
            self.logger.error(
                f"Failed to handle charge failed event: {e}",
                exc_info=True,
                extra={"event_id": event.get("id")},
            )

    async def _handle_charge_refunded(self, event: dict[str, Any]) -> None:
        """Handle refunded charge: revoke entitlement.

        Args:
            event: Stripe charge.refunded event
        """
        try:
            event_id = event.get("id")
            charge = event.get("data", {}).get("object", {})
            charge_id = charge.get("id")
            refund_amount = charge.get("refunded")
            metadata = charge.get("metadata", {})

            user_id = metadata.get("user_id")
            entitlement_type = metadata.get("entitlement_type", "premium")

            if not user_id:
                raise ValueError("Missing user_id in refunded charge metadata")

            self.logger.info(
                "Processing charge refund",
                extra={
                    "event_id": event_id,
                    "charge_id": charge_id,
                    "user_id": user_id,
                },
            )

            # Revoke entitlement
            entitlement_service = EntitlementService(self.db)
            await entitlement_service.revoke_entitlement(
                user_id=user_id,
                entitlement_type=entitlement_type,
                reason=f"Refund processed for charge {charge_id}",
            )

            # Record event
            stripe_event = StripeEvent(
                event_id=event_id,
                event_type="charge.refunded",
                payment_method="stripe",
                amount_cents=refund_amount,
                currency=charge.get("currency", "USD"),
                status=STATUS_PROCESSED,
                processed_at=datetime.utcnow(),
                webhook_timestamp=datetime.fromtimestamp(event.get("created", 0)),
            )

            self.db.add(stripe_event)
            await self.db.commit()

            self.logger.info(
                "Charge refunded: entitlement revoked",
                extra={
                    "event_id": event_id,
                    "user_id": user_id,
                },
            )

        except Exception as e:
            self.logger.error(
                f"Failed to handle charge refunded: {e}",
                exc_info=True,
                extra={"event_id": event.get("id")},
            )

            # Record failure
            stripe_event = StripeEvent(
                event_id=event.get("id"),
                event_type="charge.refunded",
                payment_method="stripe",
                amount_cents=event.get("data", {}).get("object", {}).get("refunded"),
                currency=event.get("data", {}).get("object", {}).get("currency", "USD"),
                status=STATUS_FAILED,
                error_message=str(e),
                webhook_timestamp=datetime.fromtimestamp(event.get("created", 0)),
            )
            self.db.add(stripe_event)
            await self.db.commit()

            raise
