"""FastAPI dependency functions for authentication."""

import logging
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Query, WebSocket, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.models import User, UserRole
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


async def require_owner(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Verify current user has owner role.

    Args:
        current_user: Current authenticated user

    Returns:
        User: Current user if owner

    Raises:
        HTTPException: 403 if user is not owner

    Example:
        >>> user = await require_owner(current_user=owner_user)
        >>> assert user.role == UserRole.OWNER
    """
    if current_user.role != UserRole.OWNER:
        raise HTTPException(
            status_code=403,
            detail="This operation requires owner privileges",
        )
    return current_user


async def get_current_user_from_websocket(
    websocket: WebSocket,
    token: str = Query(..., description="JWT authentication token"),
) -> User:
    """Extract and validate JWT token from WebSocket query parameter.

    Used for WebSocket authentication where Authorization headers are not
    easily accessible from browser WebSocket clients.

    Args:
        websocket: WebSocket connection
        token: JWT token from query parameter

    Returns:
        User: Current authenticated user

    Raises:
        WebSocketException: Closes connection with 1008 (policy violation) if auth fails

    Example:
        ```javascript
        const ws = new WebSocket('ws://localhost:8000/ws?token=eyJ...');
        ```

    Business Logic:
        - Extract token from query parameter (?token=...)
        - Decode and validate JWT token
        - Fetch user from database
        - Close connection if authentication fails
    """
    log = get_logger(__name__)

    try:
        # Decode token
        payload = decode_token(token)
        user_id = payload.get("sub")
        if not user_id:
            log.warning("Invalid token: missing user_id")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            raise HTTPException(status_code=401, detail="Invalid token")

        # Fetch user from database
        async for db in get_db():
            stmt = select(User).where(User.id == user_id)
            result = await db.execute(stmt)
            user = result.scalar_one_or_none()

            if not user:
                log.warning("User not found", extra={"user_id": user_id})
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                raise HTTPException(status_code=401, detail="User not found")

            return user

    except ValueError as e:
        log.warning("Token validation failed", extra={"error": str(e)})
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        raise HTTPException(status_code=401, detail="Invalid token") from e


# Export for use in other modules
__all__ = [
    "get_current_user",
    "get_bearer_token",
    "require_owner",
    "get_current_user_from_websocket",
]
