"""RBAC (Role-Based Access Control) utilities."""

from collections.abc import Callable
from functools import wraps

from backend.app.auth.models import UserRole


def require_roles(*roles: str | UserRole) -> Callable:
    """Decorator to require specific roles.

    Args:
        *roles: Acceptable roles (can be strings or UserRole enums)
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_user = kwargs.get("current_user")
            if not current_user:
                raise PermissionError("User not authenticated")

            # Convert all roles to lowercase strings for comparison
            allowed_roles = {
                role.value.lower() if isinstance(role, UserRole) else str(role).lower()
                for role in roles
            }
            user_role = (
                current_user.role.value.lower()
                if isinstance(current_user.role, UserRole)
                else str(current_user.role).lower()
            )

            if user_role not in allowed_roles:
                raise PermissionError(f"User role {current_user.role} not in {roles}")

            return await func(*args, **kwargs)

        return wrapper

    return decorator


def has_role(user_role: UserRole, required_roles: list[UserRole]) -> bool:
    """Check if user has one of required roles."""
    return user_role in required_roles


def is_owner(user_role: UserRole) -> bool:
    """Check if user is owner."""
    return bool(user_role == UserRole.OWNER)


def is_admin(user_role: UserRole) -> bool:
    """Check if user is admin or owner."""
    return bool(user_role in [UserRole.ADMIN, UserRole.OWNER])
