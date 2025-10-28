"""Stripe webhook handlers: Process payment events and update entitlements.

This module handles incoming Stripe webhooks, verifies signatures,
and updates user entitlements when payments succeed.

SECURITY: Implements replay attack prevention (PR-040)
- Signature verification with timestamp validation
- Idempotency via Redis caching (prevents duplicate processing)
- Replay protection with TTL window (600 seconds)
- RFC7807 error responses for failed verification

Example:
    >>> from backend.app.billing.webhooks import StripeWebhookHandler
    >>>
    >>> handler = StripeWebhookHandler(
    ...     stripe_handler=stripe_handler,
    ...     db_session=db,
    ...     redis_client=redis,
    ...     webhook_secret="whsec_..."
    ... )
    >>> result = await handler.process_webhook(payload, signature)
"""

import logging
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

import redis
from stripe.error import SignatureVerificationError

from backend.app.audit.models import AuditLog
from backend.app.billing.entitlements.models import EntitlementType, UserEntitlement
from backend.app.billing.security import WebhookSecurityValidator
from backend.app.billing.stripe.models import StripeEvent
from backend.app.observability.metrics import metrics

logger = logging.getLogger(__name__)


class StripeWebhookHandler:
    """Handler for Stripe webhook events with replay attack prevention."""

    def __init__(
        self,
        stripe_handler: Any,  # StripePaymentHandler
        db_session: Any,  # AsyncSession
        redis_client: redis.Redis,  # PR-040: For replay protection
        webhook_secret: str,  # PR-040: Stripe webhook secret
    ):
        """Initialize webhook handler with security.

        Args:
            stripe_handler: StripePaymentHandler instance.
            db_session: Database session for persisting payment data.
            redis_client: Redis client for replay protection and idempotency.
            webhook_secret: Stripe webhook secret for signature verification.

        Example:
            >>> handler = StripeWebhookHandler(
            ...     stripe_handler=payment_handler,
            ...     db_session=db,
            ...     redis_client=redis_client,
            ...     webhook_secret="whsec_..."
            ... )
        """
        self.stripe_handler = stripe_handler
        self.db_session = db_session
        self.logger = logger
        # PR-040: Initialize security validator
        self.security = WebhookSecurityValidator(redis_client, webhook_secret)

    async def process_webhook(
        self,
        payload: bytes,
        signature: str,
    ) -> dict[str, Any]:
        """Process incoming Stripe webhook with security validation (PR-040).

        Security layers:
        1. Signature verification (prevents tampering)
        2. Timestamp validation (prevents replays older than 10 min)
        3. Idempotency check (prevents duplicate processing via Redis)
        4. Event dispatch to appropriate handler

        Args:
            payload: Raw webhook payload bytes.
            signature: Stripe signature header (t=timestamp,v1=hash).

        Returns:
            Result dict with processing status.

        Example:
            >>> result = await handler.process_webhook(payload, signature)
            >>> if result["status"] == "success":
            ...     print("Webhook processed")
        """
        try:
            # Parse event to get ID (needed for replay check)
            import json

            try:
                event_data = json.loads(payload.decode("utf-8"))
                event_id = event_data.get("id")
            except (json.JSONDecodeError, KeyError):
                self.logger.error("Invalid webhook payload format")
                return {"status": "error", "reason": "invalid_payload"}

            # PR-040: Multi-layer security validation
            is_valid, cached_result = self.security.validate_webhook(
                payload=payload,
                signature=signature,
                event_id=event_id,
            )

            if not is_valid:
                self.logger.warning("Webhook failed security validation")
                metrics.record_billing_webhook_invalid_sig()
                return {"status": "error", "reason": "security_validation_failed"}

            # If replayed event, return cached result (idempotency)
            if cached_result is not None:
                self.logger.info(
                    f"Returning cached result for replayed event {event_id}"
                )
                # Record idempotent hit metric
                event_type = event_data.get("type", "unknown")
                metrics.record_idempotent_hit(event_type)
                return cached_result

            # Parse verified event
            event = event_data
            self.logger.info(
                "Processing webhook event",
                extra={"event_type": event["type"], "event_id": event["id"]},
            )

            # Dispatch to appropriate handler
            event_type = event["type"]

            if event_type == "checkout.session.completed":
                result = await self._handle_checkout_session_completed(event)
            elif event_type == "invoice.payment_succeeded":
                result = await self._handle_invoice_payment_succeeded(event)
            elif event_type == "invoice.payment_failed":
                result = await self._handle_invoice_payment_failed(event)
            elif event_type == "customer.subscription.deleted":
                result = await self._handle_subscription_deleted(event)
            else:
                self.logger.debug(
                    "Unhandled webhook event type", extra={"event_type": event_type}
                )
                result = {
                    "status": "ignored",
                    "reason": f"Unhandled event: {event_type}",
                }

            # PR-040: Cache result for idempotency
            if result["status"] in ("success", "ignored"):
                self.security.replay_protection.mark_idempotent_result(event_id, result)

            return result

        except SignatureVerificationError:
            self.logger.warning("Invalid webhook signature - rejecting")
            metrics.record_billing_webhook_invalid_sig()
            return {"status": "error", "reason": "invalid_signature"}

        except Exception as e:
            self.logger.error(
                "Error processing webhook", extra={"error": str(e)}, exc_info=True
            )
            return {"status": "error", "reason": str(e)}

    async def _handle_checkout_session_completed(
        self,
        event: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle checkout.session.completed event.

        Args:
            event: Stripe webhook event.

        Returns:
            Result dict.
        """
        try:
            result = await self.stripe_handler.handle_checkout_completed(event)

            if result["status"] == "success":
                user_id = result.get("user_id")
                plan_code = result.get("plan_code")
                customer_id = result.get("customer_id")

                # Update entitlements (call to PR-028)
                await self._activate_entitlements(user_id, plan_code)

                # Log to database
                await self._log_payment_event(
                    user_id=user_id,
                    event_type="checkout_completed",
                    plan_code=plan_code,
                    customer_id=customer_id,
                    metadata=result,
                )

                self.logger.info(
                    "Checkout session completed - entitlements activated",
                    extra={"user_id": user_id, "plan_code": plan_code},
                )

            return result

        except Exception as e:
            self.logger.error(
                "Error handling checkout session completed",
                extra={"error": str(e)},
                exc_info=True,
            )
            return {"status": "error", "reason": str(e)}

    async def _handle_invoice_payment_succeeded(
        self,
        event: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle invoice.payment_succeeded event.

        Args:
            event: Stripe webhook event.

        Returns:
            Result dict.
        """
        try:
            result = await self.stripe_handler.handle_invoice_payment_succeeded(event)

            if result["status"] == "success":
                customer_id = result.get("customer_id")
                invoice_id = result.get("invoice_id")
                amount = result.get("amount")

                # Log to database
                await self._log_payment_event(
                    user_id=None,  # Could look up from customer_id in real impl
                    event_type="invoice_payment_succeeded",
                    customer_id=customer_id,
                    invoice_id=invoice_id,
                    amount=amount,
                    metadata=result,
                )

                self.logger.info(
                    "Invoice payment succeeded",
                    extra={
                        "invoice_id": invoice_id,
                        "customer_id": customer_id,
                        "amount": amount,
                    },
                )

            return result

        except Exception as e:
            self.logger.error(
                "Error handling invoice payment succeeded",
                extra={"error": str(e)},
                exc_info=True,
            )
            return {"status": "error", "reason": str(e)}

    async def _handle_invoice_payment_failed(
        self,
        event: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle invoice.payment_failed event.

        Args:
            event: Stripe webhook event.

        Returns:
            Result dict.
        """
        try:
            result = await self.stripe_handler.handle_invoice_payment_failed(event)

            if result["status"] == "payment_failed":
                customer_id = result.get("customer_id")
                invoice_id = result.get("invoice_id")

                # Log to database
                await self._log_payment_event(
                    user_id=None,
                    event_type="invoice_payment_failed",
                    customer_id=customer_id,
                    invoice_id=invoice_id,
                    metadata=result,
                )

                # Send alert (in real implementation)
                self.logger.warning(
                    "Invoice payment failed - user should be notified",
                    extra={
                        "invoice_id": invoice_id,
                        "customer_id": customer_id,
                    },
                )

            return result

        except Exception as e:
            self.logger.error(
                "Error handling invoice payment failed",
                extra={"error": str(e)},
                exc_info=True,
            )
            return {"status": "error", "reason": str(e)}

    async def _handle_subscription_deleted(
        self,
        event: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle customer.subscription.deleted event.

        Args:
            event: Stripe webhook event.

        Returns:
            Result dict.
        """
        try:
            subscription = event["data"]["object"]
            customer_id = subscription.get("customer")

            self.logger.warning(
                "Subscription deleted",
                extra={
                    "subscription_id": subscription["id"],
                    "customer_id": customer_id,
                },
            )

            # Log to database
            await self._log_payment_event(
                user_id=None,
                event_type="subscription_deleted",
                customer_id=customer_id,
                subscription_id=subscription["id"],
                metadata={"subscription": subscription["id"]},
            )

            return {
                "status": "success",
                "event_type": "subscription_deleted",
                "subscription_id": subscription["id"],
            }

        except Exception as e:
            self.logger.error(
                "Error handling subscription deleted",
                extra={"error": str(e)},
                exc_info=True,
            )
            return {"status": "error", "reason": str(e)}

    async def _activate_entitlements(
        self,
        user_id: str,
        plan_code: str,
    ) -> None:
        """Activate entitlements for a user after successful payment.

        Maps plan codes to entitlements and creates UserEntitlement records.
        Sets expiry dates based on subscription term.

        Args:
            user_id: User ID.
            plan_code: Plan code that was purchased (e.g., 'premium', 'vip').

        Raises:
            Exception: If entitlement activation fails.

        Example:
            >>> await handler._activate_entitlements("user_123", "premium")
            >>> # User now has access to premium features
        """
        try:
            # Map plan codes to entitlements
            # This should match PR-028 catalog definitions
            plan_entitlements_map = {
                "free": ["signals_basic"],
                "premium": ["signals_basic", "signals_premium", "advanced_analytics"],
                "vip": [
                    "signals_basic",
                    "signals_premium",
                    "vip_support",
                    "advanced_analytics",
                    "copy_trading",
                ],
                "enterprise": [
                    "signals_basic",
                    "signals_premium",
                    "vip_support",
                    "advanced_analytics",
                    "copy_trading",
                ],
            }

            entitlements = plan_entitlements_map.get(plan_code, [])
            if not entitlements:
                self.logger.warning(
                    f"Unknown plan code: {plan_code}", extra={"user_id": user_id}
                )
                return

            # Determine subscription term (1 month default, can vary by plan)
            expiry_date = datetime.utcnow() + timedelta(days=30)

            # Create/update entitlements for this user
            for entitlement_name in entitlements:
                try:
                    # Look up entitlement type
                    entitlement_type = (
                        await self.db_session.query(EntitlementType)
                        .filter_by(name=entitlement_name)
                        .first()
                    )

                    if not entitlement_type:
                        self.logger.warning(
                            f"Entitlement type not found: {entitlement_name}",
                            extra={"user_id": user_id, "plan_code": plan_code},
                        )
                        continue

                    # Create user entitlement
                    user_entitlement = UserEntitlement(
                        id=str(uuid4()),
                        user_id=user_id,
                        entitlement_type_id=entitlement_type.id,
                        granted_at=datetime.utcnow(),
                        expires_at=expiry_date,
                        is_active=1,
                        created_at=datetime.utcnow(),
                    )

                    self.db_session.add(user_entitlement)

                    self.logger.info(
                        "Entitlement granted",
                        extra={
                            "user_id": user_id,
                            "entitlement": entitlement_name,
                            "expires_at": str(expiry_date),
                        },
                    )

                except Exception as e:
                    self.logger.error(
                        f"Error creating entitlement: {e}",
                        extra={"user_id": user_id, "entitlement": entitlement_name},
                        exc_info=True,
                    )
                    continue

            # Commit all entitlements
            await self.db_session.commit()

            self.logger.info(
                "Entitlements activated",
                extra={
                    "user_id": user_id,
                    "plan_code": plan_code,
                    "count": len(entitlements),
                },
            )

        except Exception as e:
            self.logger.error(
                "Error activating entitlements",
                extra={"user_id": user_id, "plan_code": plan_code, "error": str(e)},
                exc_info=True,
            )
            raise

    async def _log_payment_event(
        self,
        user_id: str | None,
        event_type: str,
        plan_code: str | None = None,
        customer_id: str | None = None,
        invoice_id: str | None = None,
        subscription_id: str | None = None,
        amount: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Log payment event to database for audit trail and compliance.

        Creates:
        1. StripeEvent record (tracking webhook events)
        2. AuditLog entry (for compliance audit trail)

        Args:
            user_id: User ID (may be None for system events).
            event_type: Type of event (e.g., "checkout_completed", "payment_succeeded").
            plan_code: Plan code (if applicable).
            customer_id: Stripe customer ID.
            invoice_id: Stripe invoice ID.
            subscription_id: Stripe subscription ID.
            amount: Amount in cents.
            metadata: Additional metadata.

        Example:
            >>> await handler._log_payment_event(
            ...     user_id="user_123",
            ...     event_type="checkout_completed",
            ...     plan_code="premium",
            ...     customer_id="cus_123",
            ...     amount=2999,  # £29.99
            ... )
        """
        try:
            # Create StripeEvent record for idempotent processing
            stripe_event = StripeEvent(
                id=str(uuid4()),
                event_id=metadata.get("stripe_event_id") if metadata else None,
                event_type=event_type,
                payment_method="stripe",
                customer_id=customer_id,
                amount_cents=amount,
                currency="GBP",  # Default to GBP for UK business
                status=1,  # 1 = processed successfully
                idempotency_key=metadata.get("idempotency_key") if metadata else None,
                processed_at=datetime.utcnow(),
                webhook_timestamp=datetime.utcnow(),
                received_at=datetime.utcnow(),
                created_at=datetime.utcnow(),
            )

            self.db_session.add(stripe_event)

            # Create AuditLog entry for compliance
            audit_log = AuditLog(
                id=str(uuid4()),
                timestamp=datetime.utcnow(),
                actor_id=user_id or "system",
                actor_role="SYSTEM" if user_id is None else "USER",
                action="payment.completed",
                target="payment",
                target_id=invoice_id or customer_id,
                meta={
                    "event_type": event_type,
                    "plan_code": plan_code,
                    "amount_cents": amount,
                    "currency": "GBP",
                    "subscription_id": subscription_id,
                    "metadata": metadata or {},
                },
                status="success",
            )

            self.db_session.add(audit_log)

            # Commit both records
            await self.db_session.commit()

            self.logger.info(
                "Payment event logged",
                extra={
                    "event_type": event_type,
                    "user_id": user_id,
                    "customer_id": customer_id,
                    "amount": amount,
                    "plan_code": plan_code,
                },
            )

        except Exception as e:
            self.logger.error(
                f"Error logging payment event: {e}",
                extra={
                    "event_type": event_type,
                    "user_id": user_id,
                    "customer_id": customer_id,
                },
                exc_info=True,
            )
            raise

        # Note: Unreachable except block removed - see first except above
