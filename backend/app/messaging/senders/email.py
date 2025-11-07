"""Email Sender: SMTP-based email delivery with retry logic.

This module provides email sending functionality with:
- SMTP connection with TLS/SSL support
- Retry logic with exponential backoff
- Bounce handling (SMTPRecipientsRefused)
- Rate limiting (100 emails/minute)
- Comprehensive error logging
- Prometheus metrics integration

Configuration via environment variables:
- SMTP_HOST: SMTP server hostname (e.g., "smtp.gmail.com")
- SMTP_PORT: SMTP server port (e.g., 587 for TLS, 465 for SSL)
- SMTP_USER: SMTP username/email
- SMTP_PASSWORD: SMTP password/app-specific password
- SMTP_FROM: Sender email address
- SMTP_USE_TLS: Use TLS (True/False, default True)

Example:
    from backend.app.messaging.senders.email import send_email

    result = await send_email(
        to="user@example.com",
        subject="Trade Entry Failed",
        html="<html>...</html>",
        text="Trade entry failed..."
    )
    # Returns: {"status": "sent", "message_id": "...", "error": None}
"""

import asyncio
import logging
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from backend.app.core.settings import get_settings
from backend.app.observability.metrics import (
    message_fail_total,
    message_send_duration_seconds,
    messages_sent_total,
)

logger = logging.getLogger(__name__)
settings = get_settings()

# Rate limiting: 100 emails per minute (to prevent IP blacklist)
MAX_EMAILS_PER_MINUTE = 100
_email_timestamps: list[float] = []

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAYS = [1, 2, 4]  # seconds


async def send_email(
    to: str,
    subject: str,
    html: str,
    text: str,
    retry_count: int = 0,
) -> dict[str, Any]:
    """Send email via SMTP with retry logic.

    Args:
        to: Recipient email address
        subject: Email subject line
        html: HTML email body
        text: Plain text email body (fallback)
        retry_count: Current retry attempt (internal use)

    Returns:
        dict: {
            "status": "sent" | "failed" | "rate_limited",
            "message_id": str | None,
            "error": str | None
        }

    Raises:
        ValueError: If SMTP not configured or invalid recipient

    Example:
        result = await send_email(
            to="user@example.com",
            subject="⚠️ Manual Trade Entry Required - GOLD",
            html="<html><body>...</body></html>",
            text="Your trade entry failed..."
        )

        if result["status"] == "sent":
            logger.info(f"Email sent: {result['message_id']}")
        else:
            logger.error(f"Email failed: {result['error']}")
    """
    start_time = time.time()

    # Validate SMTP configuration
    if not all(
        [
            settings.smtp.host,
            settings.smtp.port,
            settings.smtp.user,
            settings.smtp.password,
            settings.smtp.from_email,
        ]
    ):
        logger.error("SMTP not configured - cannot send email")
        return {
            "status": "failed",
            "message_id": None,
            "error": "SMTP not configured",
        }

    # Validate recipient
    if not to or "@" not in to:
        logger.error(f"Invalid recipient email: {to}")
        return {"status": "failed", "message_id": None, "error": "Invalid recipient"}

    # Check rate limit
    if not _check_rate_limit():
        logger.warning(f"Rate limit exceeded - deferring email to {to}")
        message_fail_total.labels(reason="rate_limit", channel="email").inc()
        return {
            "status": "rate_limited",
            "message_id": None,
            "error": "Rate limit exceeded (100/minute)",
        }

    # Create message
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.smtp.from_email
    msg["To"] = to

    # Attach plain text and HTML parts
    part1 = MIMEText(text, "plain", "utf-8")
    part2 = MIMEText(html, "html", "utf-8")
    msg.attach(part1)
    msg.attach(part2)

    try:
        # Send email via SMTP
        await asyncio.to_thread(_send_smtp, msg, to)

        # Track success metrics
        duration = time.time() - start_time
        message_send_duration_seconds.labels(channel="email").observe(duration)
        messages_sent_total.labels(channel="email", type="alert").inc()

        # Record timestamp for rate limiting
        _email_timestamps.append(time.time())

        logger.info(
            f"Email sent successfully to {to}",
            extra={
                "recipient": to,
                "subject": subject,
                "duration_ms": int(duration * 1000),
            },
        )

        return {
            "status": "sent",
            "message_id": msg["Message-ID"] if "Message-ID" in msg else None,
            "error": None,
        }

    except smtplib.SMTPRecipientsRefused as e:
        # Recipient invalid or rejected (permanent failure)
        logger.error(
            f"Email recipient refused: {to}",
            exc_info=True,
            extra={"recipient": to, "error": str(e)},
        )
        message_fail_total.labels(reason="recipient_refused", channel="email").inc()
        return {
            "status": "failed",
            "message_id": None,
            "error": f"Recipient refused: {str(e)}",
        }

    except smtplib.SMTPAuthenticationError as e:
        # SMTP authentication failed (configuration error)
        logger.error(
            f"SMTP authentication failed: {e}",
            exc_info=True,
            extra={"smtp_user": settings.smtp.user},
        )
        message_fail_total.labels(reason="auth_error", channel="email").inc()
        return {
            "status": "failed",
            "message_id": None,
            "error": f"SMTP authentication failed: {str(e)}",
        }

    except (smtplib.SMTPException, OSError, TimeoutError) as e:
        # Temporary SMTP error - retry if attempts remain
        if retry_count < MAX_RETRIES:
            delay = RETRY_DELAYS[min(retry_count, len(RETRY_DELAYS) - 1)]
            logger.warning(
                f"SMTP error - retrying in {delay}s (attempt {retry_count + 1}/{MAX_RETRIES})",
                extra={"recipient": to, "error": str(e), "retry_delay": delay},
            )

            await asyncio.sleep(delay)

            return await send_email(
                to=to,
                subject=subject,
                html=html,
                text=text,
                retry_count=retry_count + 1,
            )

        # Max retries exceeded
        logger.error(
            f"Email failed after {MAX_RETRIES} retries: {e}",
            exc_info=True,
            extra={"recipient": to, "error": str(e)},
        )
        message_fail_total.labels(reason="max_retries", channel="email").inc()
        return {
            "status": "failed",
            "message_id": None,
            "error": f"Max retries exceeded: {str(e)}",
        }

    except Exception as e:
        # Unexpected error
        logger.error(
            f"Unexpected email error: {e}",
            exc_info=True,
            extra={"recipient": to},
        )
        message_fail_total.labels(reason="unexpected_error", channel="email").inc()
        return {
            "status": "failed",
            "message_id": None,
            "error": f"Unexpected error: {str(e)}",
        }


def _send_smtp(msg: MIMEMultipart, to: str) -> None:
    """Send email via SMTP (synchronous, called via asyncio.to_thread).

    Args:
        msg: MIME message to send
        to: Recipient email address

    Raises:
        SMTPException: If SMTP operation fails
    """
    if settings.smtp.use_tls:
        # TLS connection (port 587)
        with smtplib.SMTP(settings.smtp.host, settings.smtp.port, timeout=30) as server:
            server.starttls()
            server.login(settings.smtp.user, settings.smtp.password)
            server.send_message(msg)
    else:
        # SSL connection (port 465) or plain (not recommended)
        with smtplib.SMTP_SSL(
            settings.smtp.host, settings.smtp.port, timeout=30
        ) as server:
            server.login(settings.smtp.user, settings.smtp.password)
            server.send_message(msg)


def _check_rate_limit() -> bool:
    """Check if rate limit allows sending another email.

    Returns:
        bool: True if allowed, False if rate limited

    Implementation:
        - Cleans up timestamps older than 60 seconds
        - Checks if less than MAX_EMAILS_PER_MINUTE in last 60 seconds
    """
    now = time.time()

    # Remove timestamps older than 60 seconds
    cutoff = now - 60
    global _email_timestamps
    _email_timestamps = [ts for ts in _email_timestamps if ts > cutoff]

    # Check if under limit
    return len(_email_timestamps) < MAX_EMAILS_PER_MINUTE


async def send_batch_emails(
    emails: list[dict[str, str]],
    batch_size: int = 10,
    delay_between_batches: float = 1.0,
) -> dict[str, int]:
    """Send multiple emails in batches (utility function).

    Args:
        emails: List of email dicts with keys: to, subject, html, text
        batch_size: Number of emails to send concurrently
        delay_between_batches: Delay in seconds between batches

    Returns:
        dict: {"sent": 10, "failed": 2, "rate_limited": 1}

    Example:
        emails = [
            {"to": "user1@example.com", "subject": "...", "html": "...", "text": "..."},
            {"to": "user2@example.com", "subject": "...", "html": "...", "text": "..."},
        ]
        result = await send_batch_emails(emails, batch_size=5)
        print(f"Sent: {result['sent']}, Failed: {result['failed']}")
    """
    sent = 0
    failed = 0
    rate_limited = 0

    for i in range(0, len(emails), batch_size):
        batch = emails[i : i + batch_size]

        # Send batch concurrently
        tasks = [
            send_email(
                to=email["to"],
                subject=email["subject"],
                html=email["html"],
                text=email["text"],
            )
            for email in batch
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
        if i + batch_size < len(emails):
            await asyncio.sleep(delay_between_batches)

    logger.info(
        f"Batch email complete: {sent} sent, {failed} failed, {rate_limited} rate limited",
        extra={"total": len(emails), "sent": sent, "failed": failed},
    )

    return {"sent": sent, "failed": failed, "rate_limited": rate_limited}
