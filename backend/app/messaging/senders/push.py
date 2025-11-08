"""Push Notification Sender: PWA push notifications with subscription management.

This module provides PWA push notification functionality with:
- Web Push Protocol integration with pywebpush
- VAPID authentication (Voluntary Application Server Identification)
- Subscription management (store/delete subscriptions)
- Automatic fallback to email/telegram on expired subscriptions
- Error handling (410 Gone → delete subscription)
- Prometheus metrics integration

Configuration via environment variables:
- PUSH_VAPID_PRIVATE_KEY: VAPID private key (PEM format)
- PUSH_VAPID_PUBLIC_KEY: VAPID public key (uncompressed base64)
- PUSH_VAPID_EMAIL: Admin email for push notifications

Example:
    from backend.app.messaging.senders.push import send_push

    result = await send_push(
        user_id="user-uuid",
        title="Manual Action Required",
        body="Your trade entry failed",
        icon="/icons/warning.png",
        url="/dashboard/approvals/123"
    )
    # Returns: {"status": "sent", "message_id": "push-123", "error": None}
"""

import asyncio
import json
import logging
import time
from typing import Any

from pywebpush import WebPushException, webpush
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.settings import get_settings
from backend.app.observability.metrics import (
    message_fail_total,
    message_send_duration_seconds,
    messages_sent_total,
)

logger = logging.getLogger(__name__)
settings = get_settings()

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAYS = [1, 2, 4]  # seconds


async def send_push(
    db: AsyncSession,
    user_id: str,
    title: str,
    body: str,
    icon: str = "/icons/logo.png",
    badge: str = "/icons/badge.png",
    url: str | None = None,
    data: dict[str, Any] | None = None,
    retry_count: int = 0,
) -> dict[str, Any]:
    """Send PWA push notification to user.

    Args:
        db: Database session (to fetch/delete subscriptions)
        user_id: User ID
        title: Notification title
        body: Notification body text
        icon: Icon URL (default: /icons/logo.png)
        badge: Badge URL for Android (default: /icons/badge.png)
        url: URL to open on click (optional)
        data: Additional data payload (optional)
        retry_count: Current retry attempt (internal use)

    Returns:
        dict: {
            "status": "sent" | "failed" | "no_subscription",
            "message_id": str | None,
            "error": str | None
        }

    Raises:
        ValueError: If VAPID keys not configured

    Example:
        result = await send_push(
            db=db_session,
            user_id="user-123",
            title="Manual Action Required",
            body="Your XAUUSD buy entry failed. Manual execution required.",
            icon="/icons/warning.png",
            url="/dashboard/approvals/approval-456"
        )

        if result["status"] == "sent":
            logger.info(f"Push sent: {result['message_id']}")
        elif result["status"] == "no_subscription":
            # Fallback to email/telegram
            await send_email(...)
    """
    start_time = time.time()

    # Validate VAPID configuration
    if not settings.push.vapid_private_key or not settings.push.vapid_public_key:
        logger.error("VAPID keys not configured")
        return {
            "status": "failed",
            "message_id": None,
            "error": "VAPID keys not configured",
        }

    # Fetch user's push subscription from database
    subscription_info = await _get_push_subscription(db, user_id)

    if not subscription_info:
        # User hasn't subscribed to push notifications
        logger.info(
            f"No push subscription for user {user_id}",
            extra={"user_id": user_id},
        )
        return {
            "status": "no_subscription",
            "message_id": None,
            "error": "User has no push subscription",
        }

    # Prepare push payload
    payload: dict[str, Any] = {
        "title": title,
        "body": body,
        "icon": icon,
        "badge": badge,
    }

    # Build data dict separately
    data_dict: dict[str, Any] = {}
    if url:
        data_dict["url"] = url
    if data:
        data_dict = data_dict | data
    if data_dict:
        payload["data"] = data_dict

    try:
        # Send push notification via pywebpush
        await asyncio.to_thread(
            webpush,
            subscription_info=subscription_info,
            data=json.dumps(payload),
            vapid_private_key=settings.push.vapid_private_key,
            vapid_claims={
                "sub": f"mailto:{settings.push.vapid_email}",
                "aud": subscription_info["endpoint"],
            },
            timeout=10,
        )

        # Success
        message_id = f"push-{int(time.time() * 1000)}"

        # Track success metrics
        duration = time.time() - start_time
        message_send_duration_seconds.labels(channel="push").observe(duration)
        messages_sent_total.labels(channel="push", type="alert").inc()

        logger.info(
            f"Push notification sent to user {user_id}",
            extra={
                "user_id": user_id,
                "message_id": message_id,
                "duration_ms": int(duration * 1000),
            },
        )

        return {"status": "sent", "message_id": message_id, "error": None}

    except WebPushException as e:
        # Handle specific push errors
        if e.response and e.response.status_code == 410:
            # 410 Gone: Subscription expired or invalid
            logger.warning(
                f"Push subscription expired for user {user_id} - deleting",
                extra={"user_id": user_id},
            )

            # Delete expired subscription from database
            await _delete_push_subscription(db, user_id)

            message_fail_total.labels(
                reason="subscription_expired", channel="push"
            ).inc()
            return {
                "status": "failed",
                "message_id": None,
                "error": "Subscription expired (410 Gone)",
            }

        elif e.response and e.response.status_code in (400, 404, 413):
            # 400 Bad Request, 404 Not Found, 413 Payload Too Large
            # These are permanent failures - don't retry
            logger.error(
                f"Push notification permanent failure: {e.response.status_code}",
                extra={"user_id": user_id, "status_code": e.response.status_code},
            )
            message_fail_total.labels(reason="permanent_error", channel="push").inc()
            return {
                "status": "failed",
                "message_id": None,
                "error": f"Permanent error: {e.response.status_code}",
            }

        else:
            # Temporary error - retry if attempts remain
            if retry_count < MAX_RETRIES:
                delay = RETRY_DELAYS[min(retry_count, len(RETRY_DELAYS) - 1)]
                logger.warning(
                    f"Push notification error - retrying in {delay}s (attempt {retry_count + 1}/{MAX_RETRIES})",
                    extra={
                        "user_id": user_id,
                        "error": str(e),
                        "retry_delay": delay,
                    },
                )

                await asyncio.sleep(delay)

                return await send_push(
                    db=db,
                    user_id=user_id,
                    title=title,
                    body=body,
                    icon=icon,
                    badge=badge,
                    url=url,
                    data=data,
                    retry_count=retry_count + 1,
                )

            # Max retries exceeded
            logger.error(
                f"Push notification failed after {MAX_RETRIES} retries: {e}",
                exc_info=True,
                extra={"user_id": user_id},
            )
            message_fail_total.labels(reason="max_retries", channel="push").inc()
            return {
                "status": "failed",
                "message_id": None,
                "error": f"Max retries exceeded: {str(e)}",
            }

    except Exception as e:
        # Unexpected error
        logger.error(
            f"Unexpected push notification error: {e}",
            exc_info=True,
            extra={"user_id": user_id},
        )
        message_fail_total.labels(reason="unexpected_error", channel="push").inc()
        return {
            "status": "failed",
            "message_id": None,
            "error": f"Unexpected error: {str(e)}",
        }


async def _get_push_subscription(
    db: AsyncSession, user_id: str
) -> dict[str, Any] | None:
    """Fetch user's push subscription from database.

    Args:
        db: Database session
        user_id: User ID

    Returns:
        dict | None: Subscription info (endpoint, keys) or None if not subscribed

    Example:
        {
            "endpoint": "https://fcm.googleapis.com/...",
            "keys": {
                "p256dh": "BKJ...",
                "auth": "ABC..."
            }
        }
    """
    # TODO: Implement database query when push_subscriptions table exists (PR-106)
    # For now, return None (no subscriptions)
    # This will cause send_push() to return "no_subscription" status

    # from backend.app.users.models import PushSubscription
    # result = await db.execute(
    #     select(PushSubscription).where(PushSubscription.user_id == user_id)
    # )
    # subscription = result.scalar_one_or_none()
    #
    # if not subscription:
    #     return None
    #
    # return {
    #     "endpoint": subscription.endpoint,
    #     "keys": {
    #         "p256dh": subscription.p256dh_key,
    #         "auth": subscription.auth_key,
    #     }
    # }

    logger.debug(
        "Push subscriptions not yet implemented - returning None (PR-106)",
        extra={"user_id": user_id},
    )
    return None


async def _delete_push_subscription(db: AsyncSession, user_id: str) -> None:
    """Delete expired push subscription from database.

    Args:
        db: Database session
        user_id: User ID
    """
    # TODO: Implement database delete when push_subscriptions table exists (PR-106)
    # For now, this is a no-op

    # from backend.app.users.models import PushSubscription
    # await db.execute(
    #     delete(PushSubscription).where(PushSubscription.user_id == user_id)
    # )
    # await db.commit()

    logger.debug(
        "Push subscription deletion not yet implemented (PR-106)",
        extra={"user_id": user_id},
    )


async def send_batch_push(
    db: AsyncSession,
    notifications: list[dict[str, Any]],
    batch_size: int = 10,
    delay_between_batches: float = 0.5,
) -> dict[str, int]:
    """Send multiple push notifications in batches (utility function).

    Args:
        db: Database session
        notifications: List of notification dicts with keys: user_id, title, body, icon, url, data
        batch_size: Number of notifications to send concurrently (max 10)
        delay_between_batches: Delay in seconds between batches

    Returns:
        dict: {"sent": 10, "failed": 2, "no_subscription": 5}

    Example:
        notifications = [
            {
                "user_id": "user-123",
                "title": "Alert",
                "body": "Your SL was hit",
                "url": "/dashboard/positions"
            },
            {
                "user_id": "user-456",
                "title": "Alert",
                "body": "Your TP was hit",
                "url": "/dashboard/positions"
            },
        ]
        result = await send_batch_push(db, notifications, batch_size=5)
        print(f"Sent: {result['sent']}, Failed: {result['failed']}")
    """
    sent = 0
    failed = 0
    no_subscription = 0

    for i in range(0, len(notifications), batch_size):
        batch = notifications[i : i + batch_size]

        # Send batch concurrently
        tasks = [
            send_push(
                db=db,
                user_id=notif["user_id"],
                title=notif["title"],
                body=notif["body"],
                icon=notif.get("icon", "/icons/logo.png"),
                badge=notif.get("badge", "/icons/badge.png"),
                url=notif.get("url"),
                data=notif.get("data"),
            )
            for notif in batch
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Count results
        for result in results:
            if isinstance(result, Exception):
                failed += 1
            elif isinstance(result, dict):
                if result["status"] == "sent":
                    sent += 1
                elif result["status"] == "no_subscription":
                    no_subscription += 1
                else:
                    failed += 1
            else:
                failed += 1

        # Delay between batches
        if i + batch_size < len(notifications):
            await asyncio.sleep(delay_between_batches)

    logger.info(
        f"Batch push complete: {sent} sent, {failed} failed, {no_subscription} no subscription",
        extra={
            "total": len(notifications),
            "sent": sent,
            "failed": failed,
            "no_subscription": no_subscription,
        },
    )

    return {"sent": sent, "failed": failed, "no_subscription": no_subscription}
