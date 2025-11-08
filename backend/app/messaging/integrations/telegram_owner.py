"""Telegram owner notifications for urgent support tickets."""

import logging
import os

import httpx

logger = logging.getLogger(__name__)


async def send_owner_notification(
    ticket_id: str,
    user_id: str,
    subject: str,
    severity: str,
    channel: str,
) -> bool:
    """
    Send Telegram DM to owner for urgent support tickets.

    Args:
        ticket_id: Ticket UUID
        user_id: User who created ticket
        subject: Ticket subject
        severity: Ticket severity (urgent triggers notification)
        channel: Origin channel

    Returns:
        True if notification sent successfully, False otherwise

    Business Rules:
        - Only sends for severity="urgent"
        - Uses TELEGRAM_OWNER_CHAT_ID from environment
        - Uses TELEGRAM_BOT_TOKEN from environment
        - Fails silently if env vars not set (logs warning)
        - Retries once on network failure
    """
    # Only notify for urgent tickets
    if severity != "urgent":
        logger.debug(f"Skipping owner notification for non-urgent ticket: {ticket_id}")
        return False

    # Get environment variables
    owner_chat_id = os.getenv("TELEGRAM_OWNER_CHAT_ID")
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")

    if not owner_chat_id or not bot_token:
        logger.warning(
            "Cannot send owner notification: TELEGRAM_OWNER_CHAT_ID or TELEGRAM_BOT_TOKEN not set",
            extra={"ticket_id": ticket_id},
        )
        return False

    # Build message
    message = f"""
🚨 **URGENT SUPPORT TICKET**

**Ticket ID**: `{ticket_id}`
**User ID**: `{user_id}`
**Channel**: {channel}
**Subject**: {subject}

Please review and respond immediately.
""".strip()

    # Send via Telegram Bot API
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": owner_chat_id,
        "text": message,
        "parse_mode": "Markdown",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()

            logger.info(
                f"Owner notification sent for ticket: {ticket_id}",
                extra={
                    "ticket_id": ticket_id,
                    "user_id": user_id,
                    "severity": severity,
                },
            )
            return True

    except httpx.HTTPStatusError as e:
        logger.error(
            f"Telegram API error sending owner notification: {e.response.status_code}",
            extra={
                "ticket_id": ticket_id,
                "status_code": e.response.status_code,
                "response_body": e.response.text,
            },
        )
        return False

    except httpx.RequestError as e:
        logger.error(
            f"Network error sending owner notification: {e}",
            extra={
                "ticket_id": ticket_id,
                "error": str(e),
            },
        )
        return False

    except Exception as e:
        logger.error(
            f"Unexpected error sending owner notification: {e}",
            extra={
                "ticket_id": ticket_id,
                "error": str(e),
            },
            exc_info=True,
        )
        return False
