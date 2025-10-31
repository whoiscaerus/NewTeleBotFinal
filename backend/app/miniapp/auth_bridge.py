"""Telegram Mini App authentication bridge.

Exchanges Telegram initData for short-lived JWT token.
"""

import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timedelta
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.jwt_handler import JWTHandler
from backend.app.auth.models import User
from backend.app.core.db import get_db
from backend.app.core.settings import get_settings
from backend.app.observability.metrics import get_metrics

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/miniapp", tags=["miniapp"])


class InitDataExchangeRequest(BaseModel):
    """Request to exchange Telegram initData for JWT."""

    init_data: str = Field(..., description="Telegram initData string")


class InitDataExchangeResponse(BaseModel):
    """Response with JWT token for Mini App."""

    access_token: str = Field(..., description="Short-lived JWT token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiry in seconds")


def verify_telegram_init_data(
    init_data: str,
    telegram_bot_token: str,
) -> dict:
    """Verify Telegram Mini App initData signature.

    Telegram signs initData with HMAC-SHA256 using bot token.
    This prevents tampering and confirms data came from Telegram.

    Args:
        init_data: Telegram initData string (URL-encoded)
        telegram_bot_token: Bot token from Telegram BotFather

    Returns:
        Parsed and verified data as dict

    Raises:
        ValueError: If signature invalid or data malformed

    Example:
        >>> data = verify_telegram_init_data(
        ...     init_data="user=%7B%22id%22%3A123%7D&...",
        ...     telegram_bot_token="123:ABC..."
        ... )
        >>> data["user"]["id"]
        123
    """
    try:
        # Parse query string
        data_check_string_parts = []
        parsed = parse_qs(init_data)

        # Extract hash and other fields
        provided_hash = parsed.get("hash", [""])[0]
        if not provided_hash:
            raise ValueError("Missing hash in initData")

        # Build data check string (exclude hash field)
        for key in sorted(parsed.keys()):
            if key != "hash":
                # Get first value from list (parse_qs returns lists)
                value = parsed[key][0] if parsed[key] else ""
                data_check_string_parts.append(f"{key}={value}")

        data_check_string = "\n".join(data_check_string_parts)

        # Compute expected hash: HMAC-SHA256 using bot token as key
        secret_key = hashlib.sha256(telegram_bot_token.encode()).digest()
        computed_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256,
        ).hexdigest()

        # Constant-time comparison (prevent timing attacks)
        if not hmac.compare_digest(computed_hash, provided_hash):
            logger.warning("Telegram initData signature verification failed")
            raise ValueError("Signature verification failed")

        # Parse user data
        result = {}
        for key, values in parsed.items():
            value = values[0] if values else None
            if key == "user" and value:
                result[key] = json.loads(value)
            elif value:
                try:
                    result[key] = int(value)
                except (ValueError, TypeError):
                    result[key] = value

        # Verify data is not too old (15 min tolerance)
        auth_date = result.get("auth_date", 0)
        if isinstance(auth_date, str):
            auth_date = int(auth_date)

        now = int(datetime.utcnow().timestamp())
        if now - auth_date > 15 * 60:
            logger.warning(
                "Telegram initData too old",
                extra={"auth_date": auth_date, "now": now},
            )
            raise ValueError("initData too old (> 15 minutes)")

        logger.info(
            "Telegram initData verified",
            extra={"user_id": result.get("user", {}).get("id")},
        )

        return result

    except Exception as e:
        logger.error(
            f"Failed to verify Telegram initData: {e}",
            exc_info=True,
        )
        raise


@router.post(
    "/exchange-initdata",
    response_model=InitDataExchangeResponse,
    status_code=200,
)
async def exchange_initdata(
    request: InitDataExchangeRequest,
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> InitDataExchangeResponse:
    """Exchange Telegram initData for JWT token.

    Flow:
    1. Verify initData signature using bot token
    2. Extract user info
    3. Get or create user in database
    4. Generate short-lived JWT (15 minutes)
    5. Return token to Mini App

    Args:
        request: initData to verify
        db: Database session

    Returns:
        JWT token valid for 15 minutes

    Raises:
        HTTPException: 401 if signature invalid, 500 if error

    Example:
        >>> response = requests.post(
        ...     "http://localhost:8000/api/v1/miniapp/exchange-initdata",
        ...     json={"init_data": "user=%7B%22id%22%3A123%7D&auth_date=1693...&hash=abc..."}
        ... )
        >>> response.json()
        {
            "access_token": "eyJhbGc...",
            "token_type": "bearer",
            "expires_in": 900
        }
    """
    settings = get_settings()
    start_time = time.time()

    try:
        # Verify initData signature
        verified_data = verify_telegram_init_data(
            init_data=request.init_data,
            telegram_bot_token=settings.telegram_bot_token,
        )

        # Extract user info from initData
        user_info = verified_data.get("user", {})
        telegram_user_id = user_info.get("id")
        user_email = (
            user_info.get("username") or f"tg_{telegram_user_id}@telegram.local"
        )
        user_name = user_info.get("first_name", "User")

        if not telegram_user_id:
            raise ValueError("No user ID in Telegram data")

        # Get or create user in database
        # For Mini App: always use Telegram user ID
        user = await _get_or_create_user(
            db=db,
            telegram_user_id=str(telegram_user_id),
            email=user_email,
            name=user_name,
        )

        # Generate JWT with short expiry (15 minutes)
        jwt_handler = JWTHandler()
        expiry = datetime.utcnow() + timedelta(minutes=15)

        token = jwt_handler.create_token(
            user_id=str(user.id),
            telegram_user_id=str(telegram_user_id),
            audience="miniapp",
            expires_at=expiry,
        )

        logger.info(
            "Mini App JWT exchanged",
            extra={
                "user_id": str(user.id),
                "telegram_user_id": str(telegram_user_id),
            },
        )

        # Record metrics (PR-035)
        duration_seconds = time.time() - start_time
        get_metrics().record_miniapp_session_created()
        get_metrics().record_miniapp_exchange_latency(duration_seconds)

        return InitDataExchangeResponse(
            access_token=token,
            token_type="bearer",
            expires_in=900,  # 15 minutes in seconds
        )

    except ValueError as e:
        logger.warning(f"initData exchange failed: {e}")
        raise HTTPException(status_code=401, detail=str(e))

    except Exception as e:
        logger.error(
            f"Unexpected error during initData exchange: {e}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Failed to exchange initData")


async def _get_or_create_user(
    db: AsyncSession,
    telegram_user_id: str,
    email: str,
    name: str,
) -> User:
    """Get or create user for Mini App.

    For now, creates new user each time.
    In production, would check User model for existing telegram_user_id.

    Args:
        db: Database session
        telegram_user_id: Telegram user ID
        email: User email
        name: User name

    Returns:
        User object

    Raises:
        Exception: If database error
    """
    from sqlalchemy import select

    from backend.app.auth.models import User

    # Check if user exists by email
    result = await db.execute(select(User).where(User.email == email))
    existing_user = result.scalars().first()

    if existing_user:
        logger.info(
            "Mini App user exists",
            extra={
                "user_id": str(existing_user.id),
                "telegram_user_id": telegram_user_id,
            },
        )
        return existing_user

    # Create new user
    new_user = User(
        email=email,
        password_hash="",  # Mini App users auth via Telegram
    )

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    logger.info(
        "Mini App user created",
        extra={
            "user_id": str(new_user.id),
            "telegram_user_id": telegram_user_id,
        },
    )

    return new_user
