"""Billing API routes for checkout and portal access."""

import logging
from typing import cast

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.dependencies import get_current_user
from backend.app.auth.models import User
from backend.app.billing.stripe.checkout import (
    CheckoutSessionRequest,
    CheckoutSessionResponse,
    StripeCheckoutService,
)
from backend.app.core.db import get_db
from backend.app.observability.metrics import get_metrics

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/billing", tags=["billing"])


@router.post("/checkout", response_model=CheckoutSessionResponse, status_code=201)
async def create_checkout_session(
    request: CheckoutSessionRequest,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> CheckoutSessionResponse:
    """Create a Stripe checkout session for subscription purchase.

    Query params:
    - success_url: URL to redirect after successful payment
    - cancel_url: URL to redirect if user cancels

    Returns:
        CheckoutSessionResponse with checkout URL

    Raises:
        HTTPException: 400 if plan invalid, 500 if Stripe error

    Example:
        >>> response = requests.post(
        ...     "http://localhost:8000/api/v1/billing/checkout",
        ...     json={
        ...         "plan_id": "premium_monthly",
        ...         "user_email": "user@example.com",
        ...         "success_url": "https://app.com/success",
        ...         "cancel_url": "https://app.com/cancel"
        ...     },
        ...     headers={"Authorization": f"Bearer {jwt_token}"}
        ... )
        >>> response.status_code
        201
        >>> response.json()["url"]  # Stripe checkout URL
        'https://checkout.stripe.com/...'
    """
    try:
        service = StripeCheckoutService(db)
        response = await service.create_checkout_session(
            request=request,
            user_id=current_user.id,
        )

        logger.info(
            "Checkout session created",
            extra={
                "user_id": str(current_user.id),
                "plan_id": request.plan_id,
                "session_id": response.session_id,
            },
        )

        # Record telemetry metric
        metrics = get_metrics()
        metrics.record_miniapp_checkout_start(plan=request.plan_id)

        return response

    except ValueError as e:
        logger.warning(
            f"Checkout validation failed: {e}",
            extra={"user_id": str(current_user.id)},
        )
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        logger.error(
            f"Checkout creation failed: {e}",
            exc_info=True,
            extra={"user_id": str(current_user.id)},
        )
        raise HTTPException(status_code=500, detail="Failed to create checkout session")


@router.get("/checkout/success", status_code=200)
async def checkout_success(
    session_id: str,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> dict[str, str]:
    """Callback after successful Stripe checkout.

    Stripe redirects here after user completes payment.
    Database should already be updated via webhook, but verify here.

    Query params:
    - session_id: Stripe session ID

    Returns:
        Success confirmation message

    Example:
        >>> response = requests.get(
        ...     "http://localhost:8000/api/v1/billing/checkout/success",
        ...     params={"session_id": "cs_test_..."},
        ...     headers={"Authorization": f"Bearer {jwt_token}"}
        ... )
        >>> response.json()
        {"status": "success", "message": "Payment received!"}
    """
    logger.info(
        "Checkout success callback",
        extra={
            "user_id": str(current_user.id),
            "session_id": session_id,
        },
    )

    return {
        "status": "success",
        "message": "Payment received! Your subscription is now active.",
    }


@router.get("/checkout/cancel", status_code=200)
async def checkout_cancel(
    session_id: str,
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> dict[str, str]:
    """Callback if user cancels Stripe checkout.

    Query params:
    - session_id: Stripe session ID

    Returns:
        Cancel confirmation message

    Example:
        >>> response = requests.get(
        ...     "http://localhost:8000/api/v1/billing/checkout/cancel",
        ...     params={"session_id": "cs_test_..."},
        ...     headers={"Authorization": f"Bearer {jwt_token}"}
        ... )
        >>> response.json()
        {"status": "cancelled", "message": "Checkout cancelled."}
    """
    logger.info(
        "Checkout cancelled",
        extra={
            "user_id": str(current_user.id),
            "session_id": session_id,
        },
    )

    return {
        "status": "cancelled",
        "message": "Checkout cancelled. Feel free to try again anytime.",
    }


@router.get("/subscription", response_model=dict, status_code=200)
async def get_subscription_miniapp(
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> dict:
    """Get current subscription for mini app.

    Returns subscription status, tier, renewal date, and current price.
    Used by mini app billing page to display plan information.

    Returns:
        dict with tier, status, renewal date, price

    Example:
        >>> response = requests.get(
        ...     "http://localhost:8000/api/v1/billing/subscription",
        ...     headers={"Authorization": f"Bearer {jwt_token}"}
        ... )
        >>> response.json()
        {
            "tier": "premium",
            "status": "active",
            "current_period_start": "2024-10-01T00:00:00Z",
            "current_period_end": "2024-11-01T00:00:00Z",
            "price_usd_monthly": 29
        }
    """
    try:
        service = StripeCheckoutService(db)
        subscription = await service.get_user_subscription(current_user.id)

        if not subscription:
            return {
                "tier": "free",
                "status": "inactive",
                "current_period_start": None,
                "current_period_end": None,
                "price_usd_monthly": 0,
            }

        logger.info(
            "Subscription retrieved for mini app",
            extra={
                "user_id": str(current_user.id),
                "tier": subscription.get("tier"),
            },
        )

        return cast(dict, subscription)

    except Exception as e:
        logger.error(
            f"Failed to get subscription: {e}",
            exc_info=True,
            extra={"user_id": str(current_user.id)},
        )
        raise HTTPException(status_code=500, detail="Failed to retrieve subscription")


@router.get("/invoices", response_model=list[dict], status_code=200)
async def get_invoices(
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> list[dict]:
    """Get invoice history for the current user.

    Returns list of paid, pending, and past due invoices with download links.
    Used by mini app invoice history page to display payment records.

    Returns:
        list[dict] with invoice details (id, amount, status, date, pdf_url)

    Status values:
        - "paid": Invoice paid and settled
        - "past_due": Invoice unpaid and overdue
        - "canceled": Invoice cancelled by user
        - "draft": Invoice not yet finalized

    Example:
        >>> response = requests.get(
        ...     "http://localhost:8000/api/v1/billing/invoices",
        ...     headers={"Authorization": f"Bearer {jwt_token}"}
        ... )
        >>> response.json()
        [
            {
                "id": "in_1234567890",
                "amount_paid": 2999,  # in cents
                "status": "paid",
                "created": "2024-10-01T12:00:00Z",
                "pdf_url": "https://invoice.stripe.com/...",
                "description": "Premium Plan - Monthly"
            },
            {
                "id": "in_0987654321",
                "amount_paid": 2999,
                "status": "past_due",
                "created": "2024-09-01T12:00:00Z",
                "pdf_url": "https://invoice.stripe.com/...",
                "description": "Premium Plan - Monthly"
            }
        ]
    """
    try:
        service = StripeCheckoutService(db)

        # Get or create Stripe customer
        customer_id = await service.get_or_create_customer(
            user_id=current_user.id,
            email=current_user.email,
            name=getattr(current_user, "name", None),  # Optional name field
        )

        # Fetch invoices from Stripe API
        invoices = await service.get_invoices(customer_id=customer_id)

        logger.info(
            "Invoices retrieved",
            extra={
                "user_id": str(current_user.id),
                "invoice_count": len(invoices),
            },
        )

        return cast(list[dict], invoices)

    except Exception as e:
        logger.error(
            f"Failed to retrieve invoices: {e}",
            exc_info=True,
            extra={"user_id": str(current_user.id)},
        )
        raise HTTPException(status_code=500, detail="Failed to retrieve invoices")


@router.post("/portal", response_model=dict, status_code=201)
async def create_portal_session_miniapp(
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> dict:
    """Create Stripe Customer Portal session for mini app.

    Portal opens in external browser (security best practice for mini app).
    Users can manage payment methods, view invoices, modify subscriptions.

    Returns:
        dict with portal URL

    Example:
        >>> response = requests.post(
        ...     "http://localhost:8000/api/v1/billing/portal",
        ...     headers={"Authorization": f"Bearer {jwt_token}"}
        ... )
        >>> response.json()
        {"url": "https://billing.stripe.com/..."}
    """
    try:
        service = StripeCheckoutService(db)

        # Get or create Stripe customer
        customer_id = await service.get_or_create_customer(
            user_id=current_user.id,
            email=current_user.email,
            name=getattr(current_user, "name", None),  # Optional name field
        )

        # Create portal session with mini app return URL
        return_url = "https://t.me/YourBot/miniapp"  # Deep link to mini app
        portal_response = await service.create_portal_session(
            customer_id=customer_id,
            return_url=return_url,
        )

        logger.info(
            "Portal session created for mini app",
            extra={
                "user_id": str(current_user.id),
                "customer_id": customer_id,
            },
        )

        # Record telemetry metric
        metrics = get_metrics()
        metrics.record_miniapp_portal_open()

        return {"url": portal_response.url}

    except Exception as e:
        logger.error(
            f"Portal creation failed: {e}",
            exc_info=True,
            extra={"user_id": str(current_user.id)},
        )
        raise HTTPException(status_code=500, detail="Failed to create portal session")
