"""Stripe webhook handler with signature verification."""

import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.billing.stripe.handlers import StripeEventHandler
from backend.app.billing.stripe.models import StripeEvent
from backend.app.core.db import get_db
from backend.app.core.settings import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["billing"])


def verify_stripe_signature(
    body: str,
    sig_header: str,
    secret: str,
) -> bool:
    """Verify Stripe webhook signature using HMAC-SHA256.

    Args:
        body: Raw request body (must be exact bytes)
        sig_header: t=<timestamp>,v1=<signature> from header
        secret: Webhook signing secret from Stripe dashboard

    Returns:
        True if signature valid, False otherwise

    Example:
        >>> body = '{"id":"evt_123"}'
        >>> sig_header = "t=1614556800,v1=abc123def456..."
        >>> secret = "whsec_..."
        >>> verify_stripe_signature(body, sig_header, secret)
        True
    """
    try:
        # Parse signature header: "t=timestamp,v1=signature"
        timestamp, signature = None, None
        for item in sig_header.split(","):
            if item.startswith("t="):
                timestamp = item[2:]
            elif item.startswith("v1="):
                signature = item[3:]

        if not timestamp or not signature:
            logger.warning("Invalid signature header format")
            return False

        # Compute expected signature: HMAC-SHA256(timestamp.body, secret)
        signed_content = f"{timestamp}.{body}".encode()
        expected_sig = hmac.new(
            secret.encode("utf-8"),
            signed_content,
            hashlib.sha256,
        ).hexdigest()

        # Compare using constant-time comparison (prevent timing attacks)
        return hmac.compare_digest(expected_sig, signature)

    except Exception as e:
        logger.error(f"Signature verification failed: {e}", exc_info=True)
        return False


@router.post("/stripe/webhook")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> dict[str, str]:
    """Handle incoming Stripe webhook events.

    Flow:
    1. Verify webhook signature (prevent spoofing)
    2. Check if event already processed (idempotency)
    3. Route to appropriate handler (charge.succeeded, etc)
    4. Mark as processed

    Args:
        request: FastAPI request object
        db: Database session

    Returns:
        Webhook receipt: {"status": "received"}

    Raises:
        HTTPException: 401 if signature invalid, 400 if malformed
    """
    settings = get_settings()

    try:
        # Get raw body for signature verification
        body = await request.body()
        body_str = body.decode("utf-8")

        # Get signature header
        sig_header = request.headers.get("stripe-signature")
        if not sig_header:
            logger.error("Missing stripe-signature header")
            raise HTTPException(status_code=401, detail="Missing signature")

        # Verify signature
        if not verify_stripe_signature(
            body_str,
            sig_header,
            settings.stripe_webhook_secret,
        ):
            logger.error("Invalid Stripe webhook signature")
            raise HTTPException(status_code=401, detail="Invalid signature")

        # Parse JSON event
        try:
            event = json.loads(body_str)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in webhook: {e}")
            raise HTTPException(status_code=400, detail="Invalid JSON") from e

        event_id = event.get("id")
        event_type = event.get("type")

        if not event_id or not event_type:
            logger.error("Missing event id or type")
            raise HTTPException(status_code=400, detail="Missing event fields")

        logger.info(
            "Received Stripe webhook",
            extra={
                "event_id": event_id,
                "event_type": event_type,
            },
        )

        # Check if already processed (idempotency)
        result = await db.execute(
            select(StripeEvent).where(StripeEvent.event_id == event_id)
        )
        existing_event = result.scalars().first()

        if existing_event and existing_event.is_processed:
            logger.info(
                f"Webhook already processed: {event_id}",
                extra={"event_id": event_id},
            )
            return {"status": "received"}

        # Route to handler
        handler = StripeEventHandler(db=db)
        await handler.handle(event)

        logger.info(
            "Webhook processed successfully",
            extra={
                "event_id": event_id,
                "event_type": event_type,
            },
        )

        return {"status": "received"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Webhook processing failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e
