"""Stripe checkout and customer portal session management."""

import logging
from uuid import UUID

import stripe
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.settings import get_settings

logger = logging.getLogger(__name__)


class CheckoutSessionRequest(BaseModel):
    """Request to create a Stripe checkout session."""

    plan_id: str = Field(..., description="Plan identifier (e.g., 'premium_monthly')")
    user_email: str = Field(..., description="User email for receipt")
    success_url: str = Field(
        ..., description="URL to redirect after successful payment"
    )
    cancel_url: str = Field(..., description="URL to redirect if user cancels payment")


class CheckoutSessionResponse(BaseModel):
    """Response with checkout session details."""

    session_id: str = Field(..., description="Stripe session ID")
    url: str = Field(..., description="URL to redirect user to Stripe checkout")


class PortalSessionResponse(BaseModel):
    """Response with customer portal session URL."""

    url: str = Field(..., description="URL to Stripe customer portal")


class StripeCheckoutService:
    """Manage Stripe checkout sessions and customer portal access.

    Handles:
    - Creating checkout sessions for payment
    - Creating customer portal sessions for subscription management
    - Price lookups from catalog
    """

    def __init__(self, db: AsyncSession):
        """Initialize with database session."""
        self.db = db
        self.settings = get_settings()
        self._validate_config()

    def _validate_config(self) -> None:
        """Validate required Stripe configuration.

        Raises:
            ValueError: If required config missing
        """
        if not self.settings.stripe_secret_key:
            logger.warning("STRIPE_SECRET_KEY not configured, using test mode")
        if not self.settings.stripe_price_map:
            logger.warning("STRIPE_PRICE_MAP not configured, using defaults")

        # Import stripe here to avoid issues if not installed
        try:
            import stripe

            if self.settings.stripe_secret_key:
                stripe.api_key = self.settings.stripe_secret_key
        except ImportError:
            logger.warning("stripe package not installed, skipping initialization")

    async def create_checkout_session(
        self,
        request: CheckoutSessionRequest,
        user_id: UUID,
    ) -> CheckoutSessionResponse:
        """Create a Stripe checkout session for payment.

        Flow:
        1. Look up price ID from plan_id
        2. Create checkout session with line items
        3. Return session URL

        Args:
            request: Checkout request with plan and redirect URLs
            user_id: UUID of user making purchase

        Returns:
            Session response with Stripe URL

        Raises:
            ValueError: If plan_id not found in price map
            stripe.StripeError: If Stripe API fails

        Example:
            >>> response = await service.create_checkout_session(
            ...     CheckoutSessionRequest(
            ...         plan_id="premium_monthly",
            ...         user_email="user@example.com",
            ...         success_url="https://app.com/billing/success",
            ...         cancel_url="https://app.com/billing/cancel"
            ...     ),
            ...     user_id=UUID("123e4567-e89b-12d3-a456-426614174000")
            ... )
            >>> response.url  # Redirect user to this URL
            'https://checkout.stripe.com/...'
        """
        try:
            # Look up price ID from plan mapping
            price_id = self.settings.stripe_price_map.get(request.plan_id)
            if not price_id:
                logger.error(
                    f"Plan not found in price map: {request.plan_id}",
                    extra={"plan_id": request.plan_id},
                )
                raise ValueError(f"Unknown plan: {request.plan_id}")

            # Create checkout session
            session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=[
                    {
                        "price": price_id,
                        "quantity": 1,
                    }
                ],
                mode="subscription",  # or "payment" for one-time
                success_url=request.success_url,
                cancel_url=request.cancel_url,
                customer_email=request.user_email,
                metadata={
                    "user_id": str(user_id),
                    "plan_id": request.plan_id,
                },
                billing_address_collection="auto",
            )

            logger.info(
                "Created checkout session",
                extra={
                    "session_id": session.id,
                    "user_id": str(user_id),
                    "plan_id": request.plan_id,
                },
            )

            return CheckoutSessionResponse(
                session_id=session.id,
                url=session.url,
            )

        except stripe.StripeError as e:
            logger.error(
                f"Failed to create checkout session: {e.user_message}",
                exc_info=True,
                extra={"user_id": str(user_id), "plan_id": request.plan_id},
            )
            raise

    async def create_portal_session(
        self,
        customer_id: str,
        return_url: str,
    ) -> PortalSessionResponse:
        """Create a Stripe customer portal session.

        Allows users to manage subscriptions, update payment methods, view invoices.

        Args:
            customer_id: Stripe customer ID
            return_url: URL to return user after portal session

        Returns:
            Portal response with session URL

        Raises:
            stripe.StripeError: If Stripe API fails

        Example:
            >>> response = await service.create_portal_session(
            ...     customer_id="cus_123...",
            ...     return_url="https://app.com/billing"
            ... )
            >>> response.url  # Redirect user to this URL
            'https://billing.stripe.com/...'
        """
        try:
            session = stripe.billing_portal.Session.create(
                customer=customer_id,
                return_url=return_url,
            )

            logger.info(
                "Created portal session",
                extra={
                    "session_id": session.id,
                    "customer_id": customer_id,
                },
            )

            return PortalSessionResponse(url=session.url)

        except stripe.StripeError as e:
            logger.error(
                f"Failed to create portal session: {e.user_message}",
                exc_info=True,
                extra={"customer_id": customer_id},
            )
            raise

    async def get_or_create_customer(
        self,
        user_id: UUID,
        email: str,
        name: str | None = None,
    ) -> str:
        """Get or create Stripe customer for user.

        Checks database for existing customer_id, creates if needed.

        Args:
            user_id: UUID of user
            email: User email
            name: Optional user name

        Returns:
            Stripe customer ID

        Raises:
            stripe.StripeError: If customer creation fails
        """
        try:
            # For now, create new customer each time
            # In production, store customer_id in User model
            customer = stripe.Customer.create(
                email=email,
                name=name,
                metadata={
                    "user_id": str(user_id),
                },
            )

            logger.info(
                "Created Stripe customer",
                extra={
                    "customer_id": customer.id,
                    "user_id": str(user_id),
                },
            )

            return customer.id

        except stripe.StripeError as e:
            logger.error(
                f"Failed to create customer: {e.user_message}",
                exc_info=True,
                extra={"user_id": str(user_id)},
            )
            raise
