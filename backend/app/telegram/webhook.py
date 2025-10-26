"""Telegram webhook endpoint and signature verification."""

import hashlib
import hmac
import json
import logging
import time
from uuid import uuid4

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.db import get_db
from backend.app.core.settings import settings
from backend.app.telegram.models import TelegramWebhook
from backend.app.telegram.router import CommandRouter
from backend.app.telegram.schema import TelegramUpdate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["telegram"])


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

    Verifies HMAC signature, parses update, logs event, routes to handler.

    Args:
        request: FastAPI request object
        db: Database session (injected via dependency)

    Returns:
        {"ok": true} on success (always return 200 to acknowledge)
    """
    start_time = time.time()

    try:

        # 1. Verify signature
        body = await request.body()
        signature = request.headers.get("X-Telegram-Bot-Api-Secret-Token")

        if not signature or not verify_telegram_signature(body, signature):
            logger.warning("Telegram webhook signature verification failed")
            return {"ok": True}  # Return 200 anyway (Telegram will retry)

        # 2. Parse update
        data = json.loads(body)
        update = TelegramUpdate.model_validate(data)

        # 3. Extract user and command info
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

        # 4. Log webhook event
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

        # 5. Route to handler
        router_instance = CommandRouter(db)
        await router_instance.route(update)

        # 6. Update event status
        elapsed_ms = int((time.time() - start_time) * 1000)
        webhook_event.status = 2  # success
        webhook_event.handler_response_time_ms = elapsed_ms

        db.add(webhook_event)
        await db.commit()

        logger.info(
            f"Webhook processed successfully in {elapsed_ms}ms",
            extra={"user_id": user_id, "command": command, "message_id": message_id},
        )

    except Exception as e:
        logger.error(f"Webhook processing error: {e}", exc_info=True)

    # Always return 200 to acknowledge receipt to Telegram
    return {"ok": True}
