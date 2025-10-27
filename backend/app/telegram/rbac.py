"""Role-based access control for Telegram commands."""

import logging
from typing import Optional

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import select

from backend.app.core.db import get_db
from backend.app.telegram.commands import UserRole
from backend.app.telegram.models import TelegramUser

logger = logging.getLogger(__name__)


async def get_user_role(user_id: str, db: AsyncSession) -> Optional[UserRole]:
    """Get user's role from database.

    Looks up user in database and returns their assigned role.

    Args:
        user_id: Telegram user ID
        db: Database session

    Returns:
        UserRole enum value or None if user not found

    Raises:
        Exception: On database error (logged but not re-raised)

    Example:
        >>> role = await get_user_role("12345", db)
        >>> assert role == UserRole.OWNER
    """
    try:
        query = select(TelegramUser).where(TelegramUser.id == user_id)
        result = await db.execute(query)
        user = result.scalars().first()

        if not user:
            logger.debug(f"User not found: {user_id}")
            return None

        # Map user role to UserRole enum
        role_map = {
            0: UserRole.PUBLIC,
            1: UserRole.SUBSCRIBER,
            2: UserRole.ADMIN,
            3: UserRole.OWNER,
        }

        user_role = role_map.get(user.role, UserRole.PUBLIC)
        logger.debug(f"User role retrieved: {user_id} -> {user_role}")

        return user_role

    except Exception as e:
        logger.error(f"Error getting user role: {e}", exc_info=True)
        return None


async def ensure_public(user_id: str, db: AsyncSession) -> bool:
    """Verify user exists (minimum public requirement).

    Args:
        user_id: Telegram user ID
        db: Database session

    Returns:
        True if user exists (is public)

    Raises:
        HTTPException(403): If user doesn't exist
    """
    role = await get_user_role(user_id, db)
    if role is None:
        logger.warning(f"Public access denied: user not found: {user_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User not found. Please start with /start.",
        )
    return True


async def ensure_subscriber(user_id: str, db: AsyncSession) -> bool:
    """Verify user is subscriber or higher.

    Args:
        user_id: Telegram user ID
        db: Database session

    Returns:
        True if user is subscriber+

    Raises:
        HTTPException(403): If user doesn't have subscriber role
    """
    role = await get_user_role(user_id, db)

    if role is None:
        logger.warning(f"Subscriber access denied: user not found: {user_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User not found.",
        )

    if role not in (UserRole.SUBSCRIBER, UserRole.ADMIN, UserRole.OWNER):
        logger.warning(f"Subscriber access denied: user has {role}: {user_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This feature requires a premium subscription.",
        )

    return True


async def ensure_admin(user_id: str, db: AsyncSession) -> bool:
    """Verify user is admin or owner.

    Args:
        user_id: Telegram user ID
        db: Database session

    Returns:
        True if user is admin+

    Raises:
        HTTPException(403): If user doesn't have admin role
    """
    role = await get_user_role(user_id, db)

    if role is None:
        logger.warning(f"Admin access denied: user not found: {user_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User not found.",
        )

    if role not in (UserRole.ADMIN, UserRole.OWNER):
        logger.warning(f"Admin access denied: user has {role}: {user_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )

    logger.info(f"Admin access granted: {user_id}")
    return True


async def ensure_owner(user_id: str, db: AsyncSession) -> bool:
    """Verify user is owner.

    Args:
        user_id: Telegram user ID
        db: Database session

    Returns:
        True if user is owner

    Raises:
        HTTPException(403): If user is not owner
    """
    role = await get_user_role(user_id, db)

    if role is None:
        logger.warning(f"Owner access denied: user not found: {user_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User not found.",
        )

    if role != UserRole.OWNER:
        logger.warning(f"Owner access denied: user has {role}: {user_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner access required.",
        )

    logger.info(f"Owner access granted: {user_id}")
    return True


async def require_role(user_id: str, required_role: UserRole, db: AsyncSession) -> bool:
    """Generic role checker for any UserRole.

    Args:
        user_id: Telegram user ID
        required_role: Required UserRole
        db: Database session

    Returns:
        True if user has required role

    Raises:
        HTTPException(403): If user doesn't have required role
    """
    user_role = await get_user_role(user_id, db)

    if user_role is None:
        logger.warning(f"Access denied: user not found: {user_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User not found.",
        )

    # Check role hierarchy
    role_hierarchy = {
        UserRole.OWNER: 4,
        UserRole.ADMIN: 3,
        UserRole.SUBSCRIBER: 2,
        UserRole.PUBLIC: 1,
    }

    required_level = role_hierarchy.get(required_role, 0)
    user_level = role_hierarchy.get(user_role, 0)

    if user_level < required_level:
        logger.warning(
            f"Access denied: insufficient role. User={user_id}, has={user_role}, required={required_role}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"This command requires {required_role.value} access.",
        )

    logger.debug(
        f"Role check passed: {user_id} has {user_role} (required: {required_role})"
    )
    return True


class RoleMiddleware:
    """Middleware for automatic role checking in Telegram handlers.

    Automatically checks user role and raises HTTPException if insufficient.

    Example:
        >>> async def handle_admin(update: TelegramUpdate, db: AsyncSession):
        ...     user_id = update.message.from_user.id
        ...     middleware = RoleMiddleware(user_id, UserRole.ADMIN, db)
        ...     await middleware.verify()  # Raises if not admin
        ...     # ... handle admin command ...
    """

    def __init__(self, user_id: str, required_role: UserRole, db: AsyncSession):
        """Initialize middleware.

        Args:
            user_id: Telegram user ID
            required_role: Required UserRole
            db: Database session
        """
        self.user_id = user_id
        self.required_role = required_role
        self.db = db

    async def verify(self) -> UserRole:
        """Verify user has required role.

        Returns:
            User's actual role

        Raises:
            HTTPException(403): If insufficient privileges
        """
        user_role = await get_user_role(self.user_id, self.db)

        if user_role is None:
            logger.warning(f"Role verification failed: user not found: {self.user_id}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User not found.",
            )

        # Check hierarchy
        role_hierarchy = {
            UserRole.OWNER: 4,
            UserRole.ADMIN: 3,
            UserRole.SUBSCRIBER: 2,
            UserRole.PUBLIC: 1,
        }

        required_level = role_hierarchy.get(self.required_role, 0)
        user_level = role_hierarchy.get(user_role, 0)

        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient privileges. Required: {self.required_role.value}",
            )

        return user_role

    async def get_user(self) -> Optional["TelegramUser"]:
        """Get user object after role verification.

        Returns:
            TelegramUser object

        Raises:
            HTTPException(403): If user not found or insufficient role
        """
        await self.verify()

        query = select(TelegramUser).where(TelegramUser.id == self.user_id)
        result = await self.db.execute(query)
        return result.scalars().first()


# Dependency functions for FastAPI integration


async def get_public_user(
    user_id: str, db: AsyncSession = Depends(get_db)
) -> Optional[TelegramUser]:
    """FastAPI dependency to verify public user access.

    Args:
        user_id: Telegram user ID
        db: Database session (injected)

    Returns:
        TelegramUser object

    Raises:
        HTTPException(403): If user doesn't exist
    """
    await ensure_public(user_id, db)
    query = select(TelegramUser).where(TelegramUser.id == user_id)
    result = await db.execute(query)
    return result.scalars().first()


async def get_subscriber_user(
    user_id: str, db: AsyncSession = Depends(get_db)
) -> Optional[TelegramUser]:
    """FastAPI dependency to verify subscriber access.

    Args:
        user_id: Telegram user ID
        db: Database session (injected)

    Returns:
        TelegramUser object

    Raises:
        HTTPException(403): If user is not subscriber+
    """
    await ensure_subscriber(user_id, db)
    query = select(TelegramUser).where(TelegramUser.id == user_id)
    result = await db.execute(query)
    return result.scalars().first()


async def get_admin_user(
    user_id: str, db: AsyncSession = Depends(get_db)
) -> Optional[TelegramUser]:
    """FastAPI dependency to verify admin access.

    Args:
        user_id: Telegram user ID
        db: Database session (injected)

    Returns:
        TelegramUser object

    Raises:
        HTTPException(403): If user is not admin+
    """
    await ensure_admin(user_id, db)
    query = select(TelegramUser).where(TelegramUser.id == user_id)
    result = await db.execute(query)
    return result.scalars().first()


async def get_owner_user(
    user_id: str, db: AsyncSession = Depends(get_db)
) -> Optional[TelegramUser]:
    """FastAPI dependency to verify owner access.

    Args:
        user_id: Telegram user ID
        db: Database session (injected)

    Returns:
        TelegramUser object

    Raises:
        HTTPException(403): If user is not owner
    """
    await ensure_owner(user_id, db)
    query = select(TelegramUser).where(TelegramUser.id == user_id)
    result = await db.execute(query)
    return result.scalars().first()
