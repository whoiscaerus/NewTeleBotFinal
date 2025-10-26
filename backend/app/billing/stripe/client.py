"""Stripe API client wrapper."""

import logging

import stripe
from pydantic import BaseModel, Field

from backend.app.core.settings import get_settings

logger = logging.getLogger(__name__)


class StripePaymentIntent(BaseModel):
    """Stripe payment intent response."""

    intent_id: str = Field(..., alias="id")
    client_secret: str
    amount_cents: int
    currency: str = "usd"
    status: str


class StripeCharge(BaseModel):
    """Stripe charge object."""

    charge_id: str = Field(..., alias="id")
    amount_cents: int
    currency: str
    status: str  # succeeded, failed, refunded
    customer_id: str | None = None
    receipt_email: str | None = None


class StripeCustomer(BaseModel):
    """Stripe customer object."""

    customer_id: str = Field(..., alias="id")
    email: str | None = None
    name: str | None = None
    metadata: dict = {}


class StripeClient:
    """Wrapper around Stripe API client.

    Handles:
    - Payment intent creation
    - Charge retrieval and status checking
    - Customer management
    - Error translation to domain errors
    """

    def __init__(self):
        """Initialize Stripe client with API key."""
        settings = get_settings()
        if not settings.stripe_secret_key:
            raise ValueError("STRIPE_SECRET_KEY not configured")

        stripe.api_key = settings.stripe_secret_key
        self.logger = logger

    async def create_payment_intent(
        self,
        amount_cents: int,
        currency: str = "usd",
        customer_id: str | None = None,
        metadata: dict | None = None,
    ) -> StripePaymentIntent:
        """Create a Stripe payment intent.

        Args:
            amount_cents: Amount in cents (e.g., 2000 for $20.00)
            currency: Currency code (default: usd)
            customer_id: Optional Stripe customer ID
            metadata: Optional metadata dict

        Returns:
            StripePaymentIntent with client_secret for frontend

        Raises:
            stripe.error.CardError: Card declined
            stripe.error.RateLimitError: Rate limit exceeded
            stripe.error.AuthenticationError: Invalid API key
        """
        try:
            intent_data = {
                "amount": amount_cents,
                "currency": currency,
                "payment_method_types": ["card"],
            }

            if customer_id:
                intent_data["customer"] = customer_id

            if metadata:
                intent_data["metadata"] = metadata

            intent = stripe.PaymentIntent.create(**intent_data)

            self.logger.info(
                f"Created payment intent: {intent.id}",
                extra={
                    "intent_id": intent.id,
                    "amount_cents": amount_cents,
                    "currency": currency,
                },
            )

            return StripePaymentIntent(
                id=intent.id,
                client_secret=intent.client_secret,
                amount_cents=intent.amount,
                currency=intent.currency,
                status=intent.status,
            )

        except stripe.StripeError as e:
            self.logger.error(
                f"Failed to create payment intent: {e.user_message}",
                exc_info=True,
            )
            raise

    async def retrieve_charge(self, charge_id: str) -> StripeCharge:
        """Retrieve charge details from Stripe.

        Args:
            charge_id: Stripe charge ID

        Returns:
            StripeCharge with current status

        Raises:
            stripe.error.InvalidRequestError: Charge not found
        """
        try:
            charge = stripe.Charge.retrieve(charge_id)

            self.logger.info(
                f"Retrieved charge: {charge.id}",
                extra={"charge_id": charge.id, "status": charge.status},
            )

            return StripeCharge(
                id=charge.id,
                amount_cents=charge.amount,
                currency=charge.currency,
                status=charge.status,
                customer_id=charge.customer,
                receipt_email=charge.receipt_email,
            )

        except stripe.StripeError as e:
            self.logger.error(
                f"Failed to retrieve charge {charge_id}: {e.user_message}",
                exc_info=True,
            )
            raise

    async def retrieve_customer(self, customer_id: str) -> StripeCustomer:
        """Retrieve customer details from Stripe.

        Args:
            customer_id: Stripe customer ID

        Returns:
            StripeCustomer with customer info

        Raises:
            stripe.error.InvalidRequestError: Customer not found
        """
        try:
            customer = stripe.Customer.retrieve(customer_id)

            return StripeCustomer(
                id=customer.id,
                email=customer.email,
                name=customer.name,
                metadata=customer.metadata or {},
            )

        except stripe.StripeError as e:
            self.logger.error(
                f"Failed to retrieve customer {customer_id}: {e.user_message}",
                exc_info=True,
            )
            raise

    async def create_refund(
        self, charge_id: str, reason: str = "requested_by_customer"
    ) -> dict:
        """Create a refund for a charge.

        Args:
            charge_id: Stripe charge ID to refund
            reason: Reason for refund

        Returns:
            Refund object

        Raises:
            stripe.error.InvalidRequestError: Charge not found or already refunded
        """
        try:
            refund = stripe.Refund.create(charge=charge_id, reason=reason)

            self.logger.info(
                f"Created refund for charge {charge_id}",
                extra={"refund_id": refund.id, "charge_id": charge_id},
            )

            return {
                "refund_id": refund.id,
                "amount_cents": refund.amount,
                "status": refund.status,
            }

        except stripe.StripeError as e:
            self.logger.error(
                f"Failed to refund charge {charge_id}: {e.user_message}",
                exc_info=True,
            )
            raise
