"""
PR-099: RBAC Middleware for Admin Portal

Role-based access control dependencies for owner and admin routes.
"""

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.dependencies import get_current_user
from backend.app.auth.models import User
from backend.app.core.db import get_db


async def require_owner(
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> User:
    """
    Dependency that requires the current user to have owner role.

    Args:
        current_user: Authenticated user from JWT
        db: Database session

    Returns:
        User: The authenticated owner user

    Raises:
        HTTPException: 403 if user is not an owner

    Example:
        >>> @router.get("/admin/sensitive")
        >>> async def sensitive_endpoint(user: User = Depends(require_owner)):
        ...     return {"data": "only owners see this"}
    """
    if not current_user.is_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner access required",
        )
    return current_user


async def require_admin(
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> User:
    """
    Dependency that requires the current user to have admin or owner role.

    Args:
        current_user: Authenticated user from JWT
        db: Database session

    Returns:
        User: The authenticated admin/owner user

    Raises:
        HTTPException: 403 if user is not an admin or owner

    Example:
        >>> @router.get("/admin/users")
        >>> async def list_users(user: User = Depends(require_admin)):
        ...     return {"users": [...]}
    """
    if not (current_user.is_admin or current_user.is_owner):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user
