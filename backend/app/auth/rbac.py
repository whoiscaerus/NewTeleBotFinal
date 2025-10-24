"""RBAC (Role-Based Access Control) utilities."""

from collections.abc import Callable
from functools import wraps

from backend.app.auth.models import UserRole


def require_roles(*roles: UserRole) -> Callable:
    """Decorator to require specific roles."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_user = kwargs.get("current_user")
            if not current_user:
                raise PermissionError("User not authenticated")

            if current_user.role not in roles:
                raise PermissionError(f"User role {current_user.role} not in {roles}")

            return await func(*args, **kwargs)

        return wrapper

    return decorator


def has_role(user_role: UserRole, required_roles: list[UserRole]) -> bool:
    """Check if user has one of required roles."""
    return user_role in required_roles


def is_owner(user_role: UserRole) -> bool:
    """Check if user is owner."""
    return user_role == UserRole.OWNER


def is_admin(user_role: UserRole) -> bool:
    """Check if user is admin or owner."""
    return bool(user_role in [UserRole.ADMIN, UserRole.OWNER])
