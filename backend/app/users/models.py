"""User models - DEPRECATED: Use backend.app.auth.models.User instead.

This module is kept for backward compatibility only.
All imports are now redirected to the single canonical User model in auth.models.
"""

# Re-export from canonical location to avoid duplicate table definitions
from backend.app.auth.models import User  # noqa: F401

__all__ = ["User"]
