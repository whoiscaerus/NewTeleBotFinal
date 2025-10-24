"""Core application module (configuration, logging, middleware, database)."""

from backend.app.core.db import Base, get_db
from backend.app.core.env import load_env
from backend.app.core.logging import configure_logging, get_logger
from backend.app.core.middleware import RequestIDMiddleware, get_request_id, request_id_var
from backend.app.core.settings import get_settings

__all__ = [
    "Base",
    "get_db",
    "load_env",
    "configure_logging",
    "get_logger",
    "RequestIDMiddleware",
    "get_request_id",
    "request_id_var",
    "get_settings",
]
