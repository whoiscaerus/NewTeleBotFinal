"""Structured JSON logging configuration."""

import contextvars
import json
import logging
import logging.config
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Optional

from backend.app.core.settings import settings

# contextvar that holds current request id for the running context
_request_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "_request_id", default=None
)


@contextmanager
def _request_id_context(request_id: Optional[str] = None):
    """
    Context manager to set a request id for the current context.
    Tests import this name directly, so keep it available as a private symbol.
    If request_id is None, a new uuid4 will be generated.
    Usage:
        with _request_id_context("abc-123"):
            ...
    """
    token = None
    if request_id is None:
        request_id = str(uuid.uuid4())
    # set and keep token to restore later
    token = _request_id_var.set(request_id)
    try:
        yield request_id
    finally:
        # restore previous value
        _request_id_var.reset(token)


class RequestIdFilter(logging.Filter):
    """Attach request_id from contextvar to LogRecord if present."""

    def filter(self, record: logging.LogRecord) -> bool:
        request_id = _request_id_var.get()
        if request_id:
            # add attribute expected by formatters/tests
            setattr(record, "request_id", request_id)
        return True


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data: dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add request context if available
        if hasattr(record, "request_id") and record.request_id is not None:
            log_data["request_id"] = record.request_id

        # Add extra fields
        if hasattr(record, "extra_fields"):
            log_data.update(record.extra_fields)  # type: ignore[attr-defined]

        # Add exception info
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


def configure_logging() -> None:
    """Configure structured JSON logging."""
    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            # instantiate the RequestIdFilter for dictConfig
            "request_id": {"()": RequestIdFilter},
        },
        "formatters": {
            "json": {
                "()": JSONFormatter,
            },
            "standard": {
                "format": "[%(asctime)s] %(levelname)-8s %(name)s - %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "default": {
                "level": settings.app.log_level,
                "class": "logging.StreamHandler",
                "formatter": "json" if settings.app.env == "production" else "standard",
                "stream": sys.stdout,
                "filters": ["request_id"],
            },
            "error": {
                "level": "ERROR",
                "class": "logging.StreamHandler",
                "formatter": "json" if settings.app.env == "production" else "standard",
                "stream": sys.stderr,
                "filters": ["request_id"],
            },
        },
        "root": {
            "level": settings.app.log_level,
            "handlers": ["default"],
        },
        "loggers": {
            "backend": {
                "level": settings.app.log_level,
                "handlers": ["default"],
                "propagate": False,
            },
            "uvicorn": {
                "level": settings.app.log_level,
                "handlers": ["default"],
                "propagate": False,
            },
            "uvicorn.access": {
                "level": settings.app.log_level,
                "handlers": ["default"],
                "propagate": False,
            },
        },
    }

    logging.config.dictConfig(config)


def get_logger(name: str) -> logging.LoggerAdapter:
    """Get logger with extra fields support."""
    logger = logging.getLogger(name)
    # return a LoggerAdapter (tests expect an adapter). The adapter's 'extra' dict can be
    # used by upstream code to pass additional fields; RequestIdFilter provides request_id.
    return logging.LoggerAdapter(logger, {})


# Configure on import
configure_logging()

# Expose symbol for tests that import it directly
__all__ = [
    "JSONFormatter",
    "configure_logging",
    "get_logger",
    "_request_id_context",
]
