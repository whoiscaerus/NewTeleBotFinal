"""Messaging API Routes: Test endpoint for manual message delivery.

This module provides owner-only testing endpoints for the messaging system.
Allows manual testing of message delivery across all channels (email, telegram, push).

Routes:
    POST /api/v1/messaging/test - Send test message (owner-only)

Security:
    - All routes require authentication (JWT token)
    - Testing endpoint restricted to owners only (require_owner dependency)

Example:
    POST /api/v1/messaging/test
    {
        "user_id": "user-uuid",
        "channel": "email",
        "template_name": "position_failure_entry",
        "template_vars": {
            "instrument": "XAUUSD",
            "side": "buy",
            "entry_price": 1950.50,
            "volume": 0.1,
            "error_reason": "Insufficient margin",
            "approval_id": "approval-uuid"
        }
    }

    Response:
    {
        "status": "sent",
        "message_id": "msg-123",
        "delivery_time_ms": 234,
        "error": null
    }
"""

import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.dependencies import require_owner
from backend.app.auth.models import User
from backend.app.core.db import get_db
from backend.app.messaging.senders import send_email, send_push, send_telegram
from backend.app.messaging.templates import render_email, render_push, render_telegram

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/messaging", tags=["messaging"])


class TestMessageRequest(BaseModel):
    """Request schema for test message endpoint."""

    user_id: str = Field(..., description="User ID to send message to")
    channel: str = Field(..., description="Delivery channel: email, telegram, push")
    template_name: str = Field(
        ..., description="Template name (e.g., position_failure_entry)"
    )
    template_vars: dict[str, Any] = Field(..., description="Template variables")

    @field_validator("channel")
    @classmethod
    def validate_channel(cls, v: str) -> str:
        """Validate channel is supported."""
        if v not in ("email", "telegram", "push"):
            raise ValueError(f"Invalid channel: {v}. Must be email, telegram, or push.")
        return v

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "user_id": "user-uuid-123",
                    "channel": "email",
                    "template_name": "position_failure_entry",
                    "template_vars": {
                        "instrument": "XAUUSD",
                        "side": "buy",
                        "entry_price": 1950.50,
                        "volume": 0.1,
                        "error_reason": "Insufficient margin",
                        "approval_id": "approval-uuid-456",
                    },
                }
            ]
        }
    }


class TestMessageResponse(BaseModel):
    """Response schema for test message endpoint."""

    status: str = Field(
        ..., description="Delivery status: sent, failed, rate_limited, no_subscription"
    )
    message_id: str | int | None = Field(
        None, description="Message ID from delivery service"
    )
    delivery_time_ms: int = Field(
        ..., description="Time taken to deliver message (milliseconds)"
    )
    error: str | None = Field(None, description="Error message if failed")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "sent",
                    "message_id": "msg-123",
                    "delivery_time_ms": 234,
                    "error": None,
                }
            ]
        }
    }


@router.post(
    "/test", status_code=status.HTTP_202_ACCEPTED, response_model=TestMessageResponse
)
async def test_message(
    request: TestMessageRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_owner),
) -> TestMessageResponse:
    """Send test message to user (owner-only endpoint).

    This endpoint allows owners to manually test message delivery without going through
    the queue. Useful for testing templates, sender configuration, and integration.

    Args:
        request: Test message request (user_id, channel, template_name, template_vars)
        db: Database session
        current_user: Authenticated owner user

    Returns:
        TestMessageResponse: Delivery status, message ID, delivery time, error

    Raises:
        HTTPException 400: Invalid template name or missing required vars
        HTTPException 401: Unauthorized (not authenticated)
        HTTPException 403: Forbidden (not owner)
        HTTPException 404: User not found
        HTTPException 500: Delivery failed

    Example:
        curl -X POST http://localhost:8000/api/v1/messaging/test \\
            -H "Authorization: Bearer <owner-token>" \\
            -H "Content-Type: application/json" \\
            -d '{
                "user_id": "user-123",
                "channel": "telegram",
                "template_name": "position_failure_sl",
                "template_vars": {
                    "instrument": "XAUUSD",
                    "side": "sell",
                    "entry_price": 1950.50,
                    "current_price": 1940.20,
                    "loss_amount": 103.00,
                    "broker_ticket": "12345678"
                }
            }'

        Response:
        {
            "status": "sent",
            "message_id": 98765,
            "delivery_time_ms": 156,
            "error": null
        }
    """
    start_time = time.time()

    logger.info(
        f"Test message requested by owner {current_user.id}",
        extra={
            "owner_id": current_user.id,
            "user_id": request.user_id,
            "channel": request.channel,
            "template_name": request.template_name,
        },
    )

    # Fetch target user
    from sqlalchemy import select

    result = await db.execute(select(User).where(User.id == request.user_id))
    user = result.scalar_one_or_none()

    if not user:
        logger.warning(
            f"Test message failed: User {request.user_id} not found",
            extra={"user_id": request.user_id},
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {request.user_id} not found",
        )

    try:
        # Render template
        if request.channel == "email":
            # Render email template
            rendered = render_email(request.template_name, request.template_vars)

            # Validate user has email
            if not user.email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"User {user.id} has no email address",
                )

            # Send email
            result_data = await send_email(
                to=user.email,
                subject=rendered["subject"],
                html=rendered["html"],
                text=rendered["text"],
            )

        elif request.channel == "telegram":
            # Validate user has telegram_user_id FIRST
            if not user.telegram_user_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"User {user.id} has no Telegram chat ID",
                )

            # Render telegram template
            text = render_telegram(request.template_name, request.template_vars)

            # Send telegram message
            result_data = await send_telegram(
                chat_id=str(user.telegram_user_id), text=text, parse_mode="MarkdownV2"
            )

        elif request.channel == "push":
            # Render push template
            push_data = render_push(request.template_name, request.template_vars)

            # Send push notification
            result_data = await send_push(
                db=db,
                user_id=user.id,
                title=push_data["title"],
                body=push_data["body"],
                icon=push_data.get("icon", "/icons/logo.png"),
                badge=push_data.get("badge", "/icons/badge.png"),
                url=push_data.get("data", {}).get("url"),
                data=push_data.get("data"),
            )

        else:
            # Should never happen (validator catches this)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid channel: {request.channel}",
            )

        # Calculate delivery time
        delivery_time_ms = int((time.time() - start_time) * 1000)

        # Log result
        logger.info(
            f"Test message {'sent' if result_data['status'] == 'sent' else 'failed'}",
            extra={
                "user_id": request.user_id,
                "channel": request.channel,
                "status": result_data["status"],
                "message_id": result_data["message_id"],
                "delivery_time_ms": delivery_time_ms,
            },
        )

        return TestMessageResponse(
            status=result_data["status"],
            message_id=result_data["message_id"],
            delivery_time_ms=delivery_time_ms,
            error=result_data.get("error"),
        )

    except ValueError as e:
        # Template rendering error (invalid template name or missing vars)
        logger.error(
            f"Test message template error: {e}",
            exc_info=True,
            extra={
                "user_id": request.user_id,
                "channel": request.channel,
                "template_name": request.template_name,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Template error: {str(e)}",
        )

    except Exception as e:
        # Unexpected error
        logger.error(
            f"Test message unexpected error: {e}",
            exc_info=True,
            extra={
                "user_id": request.user_id,
                "channel": request.channel,
                "template_name": request.template_name,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}",
        )
