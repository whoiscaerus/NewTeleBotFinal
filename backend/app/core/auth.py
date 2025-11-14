"""Backward-compatibility auth module for core namespace.

This module re-exports auth functions from backend.app.auth.dependencies
to maintain compatibility with imports from backend.app.core.auth.
"""

from backend.app.auth.dependencies import (
    get_current_user,
    get_current_user_from_websocket,
    require_owner,
)

__all__ = [
    "get_current_user",
    "get_current_user_from_websocket",
    "require_owner",
]
