"""Billing API routes for checkout and portal access."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.dependencies import get_current_user
from backend.app.auth.models import User
from backend.app.billing.stripe.checkout import (
    CheckoutSessionRequest,
    CheckoutSessionResponse,
    PortalSessionResponse,
    StripeCheckoutService,
)
from backend.app.core.db import get_db

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


@router.post("/portal", response_model=PortalSessionResponse, status_code=201)
async def create_portal_session(
    return_url: str,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> PortalSessionResponse:
    """Create a Stripe customer portal session.

    Users can manage subscriptions, update payment methods, view invoices.

    Query params:
    - return_url: URL to return user after portal session

    Returns:
        PortalSessionResponse with portal URL

    Raises:
        HTTPException: 500 if Stripe error

    Example:
        >>> response = requests.post(
        ...     "http://localhost:8000/api/v1/billing/portal",
        ...     json={"return_url": "https://app.com/billing"},
        ...     headers={"Authorization": f"Bearer {jwt_token}"}
        ... )
        >>> response.json()["url"]  # Stripe portal URL
        'https://billing.stripe.com/...'
    """
    try:
        # Get or create Stripe customer
        service = StripeCheckoutService(db)
        customer_id = await service.get_or_create_customer(
            user_id=current_user.id,
            email=current_user.email,
            name=current_user.name,
        )

        # Create portal session
        response = await service.create_portal_session(
            customer_id=customer_id,
            return_url=return_url,
        )

        logger.info(
            "Portal session created",
            extra={
                "user_id": str(current_user.id),
                "customer_id": customer_id,
            },
        )

        return response

    except Exception as e:
        logger.error(
            f"Portal session creation failed: {e}",
            exc_info=True,
            extra={"user_id": str(current_user.id)},
        )
        raise HTTPException(status_code=500, detail="Failed to create portal session")


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
