"""Authentication module."""

from backend.app.auth.models import User, UserRole
from backend.app.auth.routes import get_current_user, router
from backend.app.auth.utils import create_access_token, hash_password, verify_password

__all__ = [
    "User",
    "UserRole",
    "router",
    "create_access_token",
    "hash_password",
    "verify_password",
    "get_current_user",
]
