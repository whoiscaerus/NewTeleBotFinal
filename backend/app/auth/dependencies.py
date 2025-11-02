"""FastAPI dependency functions for authentication."""

import logging
from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.models import User
from backend.app.auth.utils import decode_token
from backend.app.core.db import get_db
from backend.app.core.logging import get_logger

logger = logging.getLogger(__name__)


async def get_bearer_token(
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    """Extract bearer token from Authorization header.

    Args:
        authorization: Authorization header value

    Returns:
        str: Bearer token without "Bearer " prefix

    Raises:
        HTTPException: 401 if header missing or malformed
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=401, detail="Invalid Authorization header format"
        )

    return parts[1]


async def get_current_user(
    token: Annotated[str, Depends(get_bearer_token)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Extract and validate JWT token, return current user.

    Args:
        token: Bearer token from Authorization header
        db: Database session

    Returns:
        User: Current authenticated user

    Raises:
        HTTPException: 401 if token invalid or user not found

    Example:
        >>> user = await get_current_user(token="eyJ...", db=session)
        >>> assert user.id == "user_123"
        >>> assert user.role.value == "USER"
    """
    log = get_logger(__name__)

    try:
        payload = decode_token(token)
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")

        # Fetch user with eager-loaded relationships
        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            log.warning("User not found", extra={"user_id": user_id})
            raise HTTPException(status_code=401, detail="User not found")

        return user

    except ValueError as e:
        log.warning("Token validation failed", extra={"error": str(e)})
        raise HTTPException(status_code=401, detail="Invalid token") from e


# Export for use in other modules
__all__ = ["get_current_user", "get_bearer_token"]
