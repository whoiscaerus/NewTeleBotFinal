"""Request/Response schemas for Stripe payments."""

from decimal import Decimal

from pydantic import BaseModel, Field


class CheckoutSessionIn(BaseModel):
    """Checkout session creation request."""

    tier_id: str = Field(..., description="Subscription tier ID (free, premium, pro)")
    success_url: str = Field(..., description="URL after successful payment")
    cancel_url: str = Field(..., description="URL if customer cancels")


class WebhookEventIn(BaseModel):
    """Stripe webhook event."""

    type: str = Field(..., description="Event type")
    data: dict = Field(..., description="Event data")
    signature: str = Field(..., description="Webhook signature")


class SubscriptionOut(BaseModel):
    """Subscription details response."""

    subscription_id: str
    user_id: str
    tier: str
    status: str
    amount: Decimal
