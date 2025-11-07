"""Telegram Sender: Bot API message delivery with rate limiting.

This module provides Telegram message sending functionality with:
- Bot API integration with aiohttp
- Rate limiting (20 messages/second - Telegram API allows 30/s, we use 20/s for safety)
- Retry logic with exponential backoff
- MarkdownV2 parse mode support
- Error handling (user blocked bot, chat not found, etc.)
- Prometheus metrics integration

Configuration via environment variables:
- TELEGRAM_BOT_TOKEN: Bot token from @BotFather

Example:
    from backend.app.messaging.senders.telegram import send_telegram

    result = await send_telegram(
        chat_id="123456789",
        text="⚠️ *Manual Action Required*\\n\\nYour trade entry failed\\.",
        parse_mode="MarkdownV2"
    )
    # Returns: {"status": "sent", "message_id": 123, "error": None}
"""

import asyncio
import logging
import time
from typing import Any

import aiohttp

from backend.app.core.settings import get_settings
from backend.app.observability.metrics import (
    message_fail_total,
    message_send_duration_seconds,
    messages_sent_total,
)

logger = logging.getLogger(__name__)
settings = get_settings()

# Rate limiting: 20 messages per second (Telegram API allows 30/s)
MAX_MESSAGES_PER_SECOND = 20
_telegram_timestamps: list[float] = []

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAYS = [1, 2, 4]  # seconds

# Telegram Bot API URL
TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/{method}"


async def send_telegram(
    chat_id: str,
    text: str,
    parse_mode: str = "MarkdownV2",
    retry_count: int = 0,
) -> dict[str, Any]:
    """Send Telegram message via Bot API.

    Args:
        chat_id: Telegram chat ID (user ID or group ID)
        text: Message text (with MarkdownV2 formatting if parse_mode="MarkdownV2")
        parse_mode: Parse mode ("MarkdownV2", "HTML", or None)
        retry_count: Current retry attempt (internal use)

    Returns:
        dict: {
            "status": "sent" | "failed" | "rate_limited",
            "message_id": int | None,
            "error": str | None
        }

    Raises:
        ValueError: If bot token not configured

    Example:
        result = await send_telegram(
            chat_id="123456789",
            text="⚠️ *Manual Action Required*\\n\\nTrade entry failed\\.",
            parse_mode="MarkdownV2"
        )

        if result["status"] == "sent":
            logger.info(f"Message sent: {result['message_id']}")
        else:
            logger.error(f"Message failed: {result['error']}")
    """
    start_time = time.time()

    # Validate bot token
    if not settings.telegram.bot_token:
        logger.error("Telegram bot token not configured")
        return {
            "status": "failed",
            "message_id": None,
            "error": "Bot token not configured",
        }

    # Validate chat_id
    if not chat_id:
        logger.error("Invalid chat_id: empty")
        return {"status": "failed", "message_id": None, "error": "Invalid chat_id"}

    # Check rate limit
    if not _check_rate_limit():
        logger.warning(f"Rate limit exceeded - deferring message to {chat_id}")
        message_fail_total.labels(reason="rate_limit", channel="telegram").inc()
        return {
            "status": "rate_limited",
            "message_id": None,
            "error": "Rate limit exceeded (20/second)",
        }

    # Prepare API request
    url = TELEGRAM_API_URL.format(
        token=settings.telegram.bot_token, method="sendMessage"
    )
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload, timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                response_data = await response.json()

                if response.status == 200 and response_data.get("ok"):
                    # Success
                    message_id = response_data["result"]["message_id"]

                    # Track success metrics
                    duration = time.time() - start_time
                    message_send_duration_seconds.labels(channel="telegram").observe(
                        duration
                    )
                    messages_sent_total.labels(channel="telegram", type="alert").inc()

                    # Record timestamp for rate limiting
                    _telegram_timestamps.append(time.time())

                    logger.info(
                        f"Telegram message sent to {chat_id}",
                        extra={
                            "chat_id": chat_id,
                            "message_id": message_id,
                            "duration_ms": int(duration * 1000),
                        },
                    )

                    return {"status": "sent", "message_id": message_id, "error": None}

                else:
                    # API error
                    error_code = response_data.get("error_code")
                    error_description = response_data.get(
                        "description", "Unknown error"
                    )

                    # Handle specific errors
                    if error_code == 403:
                        # User blocked bot or chat not found
                        logger.warning(
                            f"Telegram user blocked bot or chat not found: {chat_id}",
                            extra={"chat_id": chat_id, "error": error_description},
                        )
                        message_fail_total.labels(
                            reason="user_blocked", channel="telegram"
                        ).inc()
                        return {
                            "status": "failed",
                            "message_id": None,
                            "error": f"User blocked bot or chat not found: {error_description}",
                        }

                    elif error_code == 400:
                        # Bad request (invalid chat_id, parse error, etc.)
                        logger.error(
                            f"Telegram bad request: {error_description}",
                            extra={"chat_id": chat_id, "error": error_description},
                        )
                        message_fail_total.labels(
                            reason="bad_request", channel="telegram"
                        ).inc()
                        return {
                            "status": "failed",
                            "message_id": None,
                            "error": f"Bad request: {error_description}",
                        }

                    elif error_code == 429:
                        # Too many requests (rate limit from Telegram)
                        retry_after = response_data.get("parameters", {}).get(
                            "retry_after", 1
                        )
                        logger.warning(
                            f"Telegram rate limit hit - retry after {retry_after}s",
                            extra={"chat_id": chat_id, "retry_after": retry_after},
                        )
                        message_fail_total.labels(
                            reason="telegram_rate_limit", channel="telegram"
                        ).inc()

                        # Wait and retry if attempts remain
                        if retry_count < MAX_RETRIES:
                            await asyncio.sleep(retry_after)
                            return await send_telegram(
                                chat_id=chat_id,
                                text=text,
                                parse_mode=parse_mode,
                                retry_count=retry_count + 1,
                            )

                        return {
                            "status": "failed",
                            "message_id": None,
                            "error": f"Rate limit exceeded, retry after {retry_after}s",
                        }

                    else:
                        # Other API error - retry if temporary
                        if retry_count < MAX_RETRIES:
                            delay = RETRY_DELAYS[
                                min(retry_count, len(RETRY_DELAYS) - 1)
                            ]
                            logger.warning(
                                f"Telegram API error - retrying in {delay}s (attempt {retry_count + 1}/{MAX_RETRIES})",
                                extra={
                                    "chat_id": chat_id,
                                    "error": error_description,
                                    "retry_delay": delay,
                                },
                            )

                            await asyncio.sleep(delay)

                            return await send_telegram(
                                chat_id=chat_id,
                                text=text,
                                parse_mode=parse_mode,
                                retry_count=retry_count + 1,
                            )

                        # Max retries exceeded
                        logger.error(
                            f"Telegram message failed after {MAX_RETRIES} retries",
                            extra={
                                "chat_id": chat_id,
                                "error_code": error_code,
                                "error": error_description,
                            },
                        )
                        message_fail_total.labels(
                            reason="max_retries", channel="telegram"
                        ).inc()
                        return {
                            "status": "failed",
                            "message_id": None,
                            "error": f"Max retries exceeded: {error_description}",
                        }

    except aiohttp.ClientError as e:
        # Network error - retry if attempts remain
        if retry_count < MAX_RETRIES:
            delay = RETRY_DELAYS[min(retry_count, len(RETRY_DELAYS) - 1)]
            logger.warning(
                f"Telegram network error - retrying in {delay}s (attempt {retry_count + 1}/{MAX_RETRIES})",
                extra={"chat_id": chat_id, "error": str(e), "retry_delay": delay},
            )

            await asyncio.sleep(delay)

            return await send_telegram(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
                retry_count=retry_count + 1,
            )

        # Max retries exceeded
        logger.error(
            f"Telegram network error after {MAX_RETRIES} retries: {e}",
            exc_info=True,
            extra={"chat_id": chat_id},
        )
        message_fail_total.labels(reason="network_error", channel="telegram").inc()
        return {
            "status": "failed",
            "message_id": None,
            "error": f"Network error: {str(e)}",
        }

    except Exception as e:
        # Unexpected error
        logger.error(
            f"Unexpected Telegram error: {e}",
            exc_info=True,
            extra={"chat_id": chat_id},
        )
        message_fail_total.labels(reason="unexpected_error", channel="telegram").inc()
        return {
            "status": "failed",
            "message_id": None,
            "error": f"Unexpected error: {str(e)}",
        }


def _check_rate_limit() -> bool:
    """Check if rate limit allows sending another message.

    Returns:
        bool: True if allowed, False if rate limited

    Implementation:
        - Cleans up timestamps older than 1 second
        - Checks if less than MAX_MESSAGES_PER_SECOND in last 1 second
    """
    now = time.time()

    # Remove timestamps older than 1 second
    cutoff = now - 1.0
    global _telegram_timestamps
    _telegram_timestamps = [ts for ts in _telegram_timestamps if ts > cutoff]

    # Check if under limit
    return len(_telegram_timestamps) < MAX_MESSAGES_PER_SECOND


async def send_batch_telegram(
    messages: list[dict[str, str]],
    batch_size: int = 20,
    delay_between_batches: float = 1.0,
) -> dict[str, int]:
    """Send multiple Telegram messages in batches (utility function).

    Args:
        messages: List of message dicts with keys: chat_id, text, parse_mode
        batch_size: Number of messages to send concurrently (max 20)
        delay_between_batches: Delay in seconds between batches

    Returns:
        dict: {"sent": 10, "failed": 2, "rate_limited": 1}

    Example:
        messages = [
            {"chat_id": "123", "text": "Message 1", "parse_mode": "MarkdownV2"},
            {"chat_id": "456", "text": "Message 2", "parse_mode": "MarkdownV2"},
        ]
        result = await send_batch_telegram(messages, batch_size=10)
        print(f"Sent: {result['sent']}, Failed: {result['failed']}")
    """
    sent = 0
    failed = 0
    rate_limited = 0

    for i in range(0, len(messages), batch_size):
        batch = messages[i : i + batch_size]

        # Send batch concurrently
        tasks = [
            send_telegram(
                chat_id=msg["chat_id"],
                text=msg["text"],
                parse_mode=msg.get("parse_mode", "MarkdownV2"),
            )
            for msg in batch
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Count results
        for result in results:
            if isinstance(result, Exception):
                failed += 1
            elif result["status"] == "sent":
                sent += 1
            elif result["status"] == "rate_limited":
                rate_limited += 1
            else:
                failed += 1

        # Delay between batches
        if i + batch_size < len(messages):
            await asyncio.sleep(delay_between_batches)

    logger.info(
        f"Batch Telegram complete: {sent} sent, {failed} failed, {rate_limited} rate limited",
        extra={"total": len(messages), "sent": sent, "failed": failed},
    )

    return {"sent": sent, "failed": failed, "rate_limited": rate_limited}
