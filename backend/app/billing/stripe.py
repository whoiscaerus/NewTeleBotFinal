"""Stripe payment integration: Checkout sessions, webhooks, and Customer Portal.

This module handles end-to-end Stripe billing: creating checkout sessions,
verifying webhooks, and generating customer portal links for subscription management.

Example:
    >>> from backend.app.billing.stripe import StripePaymentHandler
    >>> from backend.app.billing.schemas import CheckoutRequest
    >>>
    >>> handler = StripePaymentHandler(secret_key="sk_test_...", webhook_secret="whsec_...")
    >>> session = await handler.create_checkout_session(
    ...     user_id="user_123",
    ...     plan_code="premium",
    ...     success_url="https://example.com/success",
    ...     cancel_url="https://example.com/cancel",
    ... )
    >>> print(f"Checkout URL: {session.url}")
"""

import logging
from typing import Any
from uuid import uuid4

import stripe
from stripe.error import SignatureVerificationError

from backend.app.observability.metrics import metrics

logger = logging.getLogger(__name__)


class StripePaymentHandler:
    """Handler for Stripe payment operations."""

    # Default price mapping (can be overridden via env)
    DEFAULT_PRICES = {
        "free": {"amount": 0, "currency": "gbp", "interval": "month"},
        "basic": {"amount": 1499, "currency": "gbp", "interval": "month"},  # £14.99
        "premium": {"amount": 2999, "currency": "gbp", "interval": "month"},  # £29.99
        "pro": {"amount": 4999, "currency": "gbp", "interval": "month"},  # £49.99
    }

    def __init__(
        self,
        secret_key: str,
        webhook_secret: str,
        price_map: dict[str, int] | None = None,
    ):
        """Initialize Stripe payment handler.

        Args:
            secret_key: Stripe API secret key.
            webhook_secret: Stripe webhook signing secret.
            price_map: Optional mapping of plan codes to Stripe price IDs.

        Example:
            >>> handler = StripePaymentHandler(
            ...     secret_key="sk_test_123",
            ...     webhook_secret="whsec_456",
            ... )
        """
        stripe.api_key = secret_key
        self.webhook_secret = webhook_secret
        self.price_map = price_map or {}
        self.logger = logger

    async def create_checkout_session(
        self,
        user_id: str,
        plan_code: str,
        success_url: str,
        cancel_url: str,
        metadata: dict[str, Any] | None = None,
    ) -> stripe.checkout.Session:
        """Create a Stripe checkout session for subscription.

        Args:
            user_id: User ID (stored in metadata).
            plan_code: Plan code (e.g., "premium").
            success_url: URL to redirect on success.
            cancel_url: URL to redirect on cancel.
            metadata: Optional additional metadata.

        Returns:
            Stripe checkout session object.

        Raises:
            ValueError: If plan code is invalid.
            stripe.error.StripeError: If API call fails.

        Example:
            >>> session = await handler.create_checkout_session(
            ...     user_id="user_123",
            ...     plan_code="premium",
            ...     success_url="https://example.com/success",
            ...     cancel_url="https://example.com/cancel",
            ... )
            >>> print(session.url)
        """
        try:
            # Validate plan code
            if plan_code not in self.DEFAULT_PRICES:
                raise ValueError(f"Invalid plan code: {plan_code}")

            plan_info = self.DEFAULT_PRICES[plan_code]

            # Build metadata
            session_metadata = {
                "user_id": user_id,
                "plan_code": plan_code,
                **(metadata or {}),
            }

            # Get Stripe price ID from map or use default
            price_id = self.price_map.get(plan_code)

            # If no price ID in map, create line items with explicit amount
            if price_id:
                line_items = [{"price": price_id, "quantity": 1}]
            else:
                # Use direct price configuration
                line_items = [
                    {
                        "price_data": {
                            "currency": plan_info["currency"],
                            "product_data": {
                                "name": f"Plan: {plan_code}",
                                "description": f"Subscription for {plan_code} plan",
                            },
                            "unit_amount": plan_info["amount"],
                            "recurring": {
                                "interval": plan_info["interval"],
                                "interval_count": 1,
                            },
                        },
                        "quantity": 1,
                    }
                ]

            # Create session
            session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=line_items,
                mode="subscription",
                success_url=success_url,
                cancel_url=cancel_url,
                customer_email=None,  # Will be populated from user in real implementation
                metadata=session_metadata,
                idempotency_key=f"checkout_{user_id}_{plan_code}_{uuid4()}",
            )

            self.logger.info(
                "Checkout session created",
                extra={
                    "session_id": session.id,
                    "user_id": user_id,
                    "plan_code": plan_code,
                },
            )

            # Record telemetry
            metrics.billing_checkout_started_total.labels(plan=plan_code).inc()

            return session

        except ValueError as e:
            self.logger.error(
                "Invalid checkout request",
                extra={"user_id": user_id, "plan_code": plan_code, "error": str(e)},
            )
            raise

        except stripe.error.StripeError as e:
            self.logger.error(
                "Stripe API error creating checkout session",
                extra={
                    "user_id": user_id,
                    "plan_code": plan_code,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise

        except Exception as e:
            self.logger.error(
                "Unexpected error creating checkout session",
                extra={
                    "user_id": user_id,
                    "plan_code": plan_code,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise

    async def create_portal_session(
        self,
        customer_id: str,
        return_url: str,
    ) -> str:
        """Create a Stripe Customer Portal session URL.

        Args:
            customer_id: Stripe customer ID.
            return_url: URL to return to after portal session.

        Returns:
            Portal session URL.

        Raises:
            stripe.error.StripeError: If API call fails.

        Example:
            >>> portal_url = await handler.create_portal_session(
            ...     customer_id="cus_123",
            ...     return_url="https://example.com/billing",
            ... )
        """
        try:
            session = stripe.billing.portal.Session.create(
                customer=customer_id,
                return_url=return_url,
            )

            self.logger.info(
                "Portal session created",
                extra={
                    "customer_id": customer_id,
                    "session_url": session.url,
                },
            )

            return session.url

        except stripe.error.StripeError as e:
            self.logger.error(
                "Stripe API error creating portal session",
                extra={"customer_id": customer_id, "error": str(e)},
                exc_info=True,
            )
            raise

        except Exception as e:
            self.logger.error(
                "Unexpected error creating portal session",
                extra={"customer_id": customer_id, "error": str(e)},
                exc_info=True,
            )
            raise

    def verify_webhook_signature(
        self,
        payload: bytes,
        signature: str,
    ) -> dict[str, Any]:
        """Verify and parse Stripe webhook signature.

        Args:
            payload: Raw webhook payload bytes.
            signature: Stripe signature header.

        Returns:
            Parsed webhook event dict.

        Raises:
            SignatureVerificationError: If signature is invalid.

        Example:
            >>> event = handler.verify_webhook_signature(payload, signature)
            >>> event_type = event["type"]
        """
        try:
            event = stripe.Webhook.construct_event(
                payload,
                signature,
                self.webhook_secret,
            )

            self.logger.info(
                "Webhook signature verified", extra={"event_type": event["type"]}
            )

            return event

        except SignatureVerificationError as e:
            self.logger.warning("Invalid webhook signature", extra={"error": str(e)})
            raise

        except Exception as e:
            self.logger.error(
                "Error verifying webhook signature",
                extra={"error": str(e)},
                exc_info=True,
            )
            raise

    async def handle_checkout_completed(
        self,
        event: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle checkout.session.completed webhook event.

        Args:
            event: Stripe webhook event.

        Returns:
            Result dict with status and details.

        Example:
            >>> result = await handler.handle_checkout_completed(event)
            >>> if result["status"] == "success":
            ...     user_id = result["user_id"]
        """
        try:
            session = event["data"]["object"]
            user_id = session.get("metadata", {}).get("user_id")
            plan_code = session.get("metadata", {}).get("plan_code")

            if not user_id:
                self.logger.error("No user_id in checkout session metadata")
                return {"status": "error", "reason": "missing_user_id"}

            self.logger.info(
                "Checkout completed",
                extra={
                    "session_id": session["id"],
                    "user_id": user_id,
                    "plan_code": plan_code,
                    "customer_id": session.get("customer"),
                },
            )

            # Record telemetry
            metrics.billing_payments_total.labels(status="completed").inc()

            return {
                "status": "success",
                "user_id": user_id,
                "plan_code": plan_code,
                "customer_id": session.get("customer"),
                "session_id": session["id"],
            }

        except Exception as e:
            self.logger.error(
                "Error handling checkout completed event",
                extra={"error": str(e)},
                exc_info=True,
            )
            metrics.billing_payments_total.labels(status="failed").inc()
            return {"status": "error", "reason": str(e)}

    async def handle_invoice_payment_succeeded(
        self,
        event: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle invoice.payment_succeeded webhook event.

        Args:
            event: Stripe webhook event.

        Returns:
            Result dict with status and details.

        Example:
            >>> result = await handler.handle_invoice_payment_succeeded(event)
        """
        try:
            invoice = event["data"]["object"]
            customer_id = invoice.get("customer")

            self.logger.info(
                "Invoice payment succeeded",
                extra={
                    "invoice_id": invoice["id"],
                    "customer_id": customer_id,
                    "amount": invoice["amount_paid"],
                },
            )

            # Record telemetry
            metrics.billing_payments_total.labels(status="succeeded").inc()

            return {
                "status": "success",
                "invoice_id": invoice["id"],
                "customer_id": customer_id,
                "amount": invoice["amount_paid"],
            }

        except Exception as e:
            self.logger.error(
                "Error handling invoice payment succeeded event",
                extra={"error": str(e)},
                exc_info=True,
            )
            return {"status": "error", "reason": str(e)}

    async def handle_invoice_payment_failed(
        self,
        event: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle invoice.payment_failed webhook event.

        Args:
            event: Stripe webhook event.

        Returns:
            Result dict with status and details.

        Example:
            >>> result = await handler.handle_invoice_payment_failed(event)
        """
        try:
            invoice = event["data"]["object"]
            customer_id = invoice.get("customer")

            self.logger.warning(
                "Invoice payment failed",
                extra={
                    "invoice_id": invoice["id"],
                    "customer_id": customer_id,
                    "error": invoice.get("last_finalization_error", {}).get("message"),
                },
            )

            # Record telemetry
            metrics.billing_payments_total.labels(status="failed").inc()

            return {
                "status": "payment_failed",
                "invoice_id": invoice["id"],
                "customer_id": customer_id,
            }

        except Exception as e:
            self.logger.error(
                "Error handling invoice payment failed event",
                extra={"error": str(e)},
                exc_info=True,
            )
            return {"status": "error", "reason": str(e)}

    async def get_customer(
        self,
        customer_id: str,
    ) -> stripe.Customer:
        """Get Stripe customer by ID.

        Args:
            customer_id: Stripe customer ID.

        Returns:
            Stripe customer object.

        Raises:
            stripe.error.StripeError: If API call fails.

        Example:
            >>> customer = await handler.get_customer(customer_id="cus_123")
            >>> print(customer.email)
        """
        try:
            customer = stripe.Customer.retrieve(customer_id)
            return customer

        except stripe.error.StripeError as e:
            self.logger.error(
                "Error retrieving customer",
                extra={"customer_id": customer_id, "error": str(e)},
            )
            raise

    async def get_subscriptions(
        self,
        customer_id: str,
    ) -> list:
        """Get all subscriptions for a customer.

        Args:
            customer_id: Stripe customer ID.

        Returns:
            List of subscription objects.

        Example:
            >>> subs = await handler.get_subscriptions(customer_id="cus_123")
            >>> for sub in subs:
            ...     print(f"Status: {sub.status}")
        """
        try:
            subscriptions = stripe.Subscription.list(customer=customer_id)
            return subscriptions.get("data", [])

        except stripe.error.StripeError as e:
            self.logger.error(
                "Error retrieving subscriptions",
                extra={"customer_id": customer_id, "error": str(e)},
            )
            raise
