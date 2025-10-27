"""Telegram webhook endpoint and signature verification."""

import hashlib
import hmac
import json
import logging
import time
from uuid import uuid4

from fastapi import APIRouter, Depends, Request, status
from prometheus_client import Counter, Histogram
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.db import get_db
from backend.app.core.rate_limit import RateLimiter
from backend.app.core.settings import settings
from backend.app.telegram.models import TelegramWebhook
from backend.app.telegram.router import CommandRouter
from backend.app.telegram.schema import TelegramUpdate
from backend.app.telegram.verify import should_reject_webhook, verify_webhook_request

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["telegram"])

# Metrics
telegram_updates_total = Counter(
    "telegram_updates_total",
    "Total Telegram updates received",
    ["status"],  # success, rejected, invalid
)

telegram_updates_processing_time = Histogram(
    "telegram_updates_processing_seconds",
    "Time to process Telegram update",
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0),
)

telegram_verification_failures = Counter(
    "telegram_verification_failures_total",
    "Telegram webhook verification failures",
    ["reason"],  # ip_blocked, secret_invalid, signature_invalid, rate_limited
)

telegram_commands_total = Counter(
    "telegram_commands_total",
    "Telegram commands executed",
    ["command", "status"],  # status: success, permission_denied, error
)


def verify_telegram_signature(body: bytes, signature: str) -> bool:
    """Verify Telegram webhook signature.

    Args:
        body: Raw request body
        signature: X-Telegram-Bot-Api-Secret-Token header value

    Returns:
        True if signature is valid, False otherwise
    """
    try:
        computed = hmac.new(
            settings.TELEGRAM_BOT_API_SECRET_TOKEN.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()
        return computed == signature
    except Exception as e:
        logger.error(f"Signature verification error: {e}")
        return False


@router.post("/telegram/webhook", status_code=status.HTTP_200_OK)
async def telegram_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Receive and process Telegram webhook updates.

    Verifies:
    - HMAC signature (X-Telegram-Bot-Api-Secret-Token)
    - IP allowlist (if configured)
    - Secret header (if configured)
    - Rate limiting per bot

    Then parses update, logs event, routes to handler.

    Args:
        request: FastAPI request object
        db: Database session (injected via dependency)

    Returns:
        {"ok": true} on success (always return 200 to acknowledge)

    Note:
        Returns 200 OK to Telegram for all requests (including rejected ones)
        to avoid retry loops. Security rejections are logged but not visible
        to caller.

    Metrics:
        telegram_updates_total: Count of updates by status
        telegram_updates_processing_seconds: Histogram of processing time
        telegram_verification_failures: Count of verification failures
        telegram_commands_total: Count of commands executed
    """
    start_time = time.time()
    client_ip = request.client.host if request.client else "unknown"
    webhook_status = "success"  # Default, updated if needed

    try:

        # 1. Verify IP allowlist and secret header
        is_rejected = await should_reject_webhook(request)
        if is_rejected:
            verification = await verify_webhook_request(request)
            if not verification["ip_verified"]:
                telegram_verification_failures.labels(reason="ip_blocked").inc()
                logger.warning(f"Webhook rejected: IP not allowed: {client_ip}")
            elif not verification["secret_verified"]:
                telegram_verification_failures.labels(reason="secret_invalid").inc()
                logger.warning("Webhook rejected: Secret verification failed")

            webhook_status = "rejected"
            telegram_updates_total.labels(status="rejected").inc()
            return {"ok": True}  # Return 200 anyway (don't leak security info)

        # 2. Apply rate limiting per bot (if Redis enabled)
        try:
            rate_limiter = RateLimiter()
            await rate_limiter.initialize()

            if rate_limiter._initialized:
                # Rate limit: 1000 updates per minute per bot
                bot_id = settings.TELEGRAM_BOT_TOKEN.split(":")[0]
                rate_key = f"telegram:webhook:{bot_id}"

                is_allowed = await rate_limiter.is_allowed(
                    rate_key, max_tokens=1000, refill_rate=16.67  # ~1000/min
                )

                if not is_allowed:
                    telegram_verification_failures.labels(reason="rate_limited").inc()
                    logger.warning(f"Webhook rate limited: {bot_id}")
                    webhook_status = "rejected"
                    telegram_updates_total.labels(status="rejected").inc()
                    return {"ok": True}

        except Exception as e:
            logger.warning(f"Rate limiting check failed: {e}")
            # Continue anyway - don't fail if rate limiter unavailable

        # 3. Verify HMAC signature
        body = await request.body()
        signature = request.headers.get("X-Telegram-Bot-Api-Secret-Token")

        if not signature or not verify_telegram_signature(body, signature):
            telegram_verification_failures.labels(reason="signature_invalid").inc()
            logger.warning(
                f"Telegram webhook signature verification failed: IP={client_ip}"
            )
            webhook_status = "invalid"
            telegram_updates_total.labels(status="invalid").inc()
            return {"ok": True}  # Return 200 anyway (Telegram will retry)

        # 4. Parse update
        data = json.loads(body)
        update = TelegramUpdate.model_validate(data)

        # 5. Extract user and command info
        user_id = None
        message_id = None
        chat_id = None
        command = None

        if update.message:
            user_id = str(update.message.from_user.id)
            message_id = update.message.message_id
            chat_id = update.message.chat.id

            # Extract command from text
            if update.message.text and update.message.text.startswith("/"):
                command = update.message.text.split()[0][1:]  # Remove leading /

        elif update.callback_query:
            user_id = str(update.callback_query.from_user.id)
            message_id = update.callback_query.id
            chat_id = (
                update.callback_query.message.chat.id
                if update.callback_query.message
                else None
            )
            command = "callback"

        # 6. Log webhook event
        webhook_event = TelegramWebhook(
            id=str(uuid4()),
            user_id=user_id,
            message_id=message_id,
            chat_id=chat_id or 0,
            command=command,
            text=update.message.text if update.message else None,
            status=0,
        )

        db.add(webhook_event)
        await db.commit()

        # 7. Route to handler
        router_instance = CommandRouter(db)
        await router_instance.route(update)

        # 8. Update event status
        elapsed_ms = int((time.time() - start_time) * 1000)
        webhook_event.status = 2  # success
        webhook_event.handler_response_time_ms = elapsed_ms

        db.add(webhook_event)
        await db.commit()

        logger.info(
            f"Webhook processed successfully in {elapsed_ms}ms",
            extra={
                "user_id": user_id,
                "command": command,
                "message_id": message_id,
                "ip": client_ip,
                "processing_ms": elapsed_ms,
            },
        )

        # Record metrics
        if command:
            telegram_commands_total.labels(command=command, status="success").inc()

    except ValueError as e:
        logger.error(f"Webhook parsing error: {e}", exc_info=True)
        webhook_status = "invalid"
        telegram_updates_total.labels(status="invalid").inc()

    except Exception as e:
        logger.error(f"Webhook processing error: {e}", exc_info=True)
        webhook_status = "error"
        telegram_updates_total.labels(status="error").inc()

    # Record overall metrics
    elapsed_ms = int((time.time() - start_time) * 1000)
    telegram_updates_processing_time.observe(elapsed_ms / 1000.0)  # Convert to seconds

    if webhook_status == "success":
        telegram_updates_total.labels(status="success").inc()

    # Always return 200 to acknowledge receipt to Telegram
    return {"ok": True}
