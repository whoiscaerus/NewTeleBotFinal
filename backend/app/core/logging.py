"""Structured JSON logging configuration.

All logs are formatted as JSON for easy parsing and correlation tracking.
Request IDs are included in every log entry for distributed tracing.
"""

import json
import logging
import sys
from contextvars import ContextVar
from typing import Any

from backend.app.core.settings import settings

# Context variable for storing request ID
_request_id_context: ContextVar[str] = ContextVar("request_id", default="unknown")


class JSONFormatter(logging.Formatter):
    """Custom formatter that outputs JSON-structured logs."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_obj = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "lvl": record.levelname,
            "msg": record.getMessage(),
            "module": record.module,
            "func": record.funcName,
            "line": record.lineno,
            "request_id": _request_id_context.get(),
        }

        # Add exception info if present
        if record.exc_info:
            log_obj["exc_info"] = self.formatException(record.exc_info)

        # Add extra fields from the record
        if hasattr(record, "extra_fields"):
            log_obj.update(record.extra_fields)

        return json.dumps(log_obj, default=str)


def setup_logging() -> None:
    """Configure JSON logging for the application."""
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(settings.APP_LOG_LEVEL)

    # Remove any existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create stdout handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(settings.APP_LOG_LEVEL)

    # Set JSON formatter
    formatter = JSONFormatter()
    handler.setFormatter(formatter)

    # Add handler to root logger
    root_logger.addHandler(handler)

    # Configure uvicorn access logs
    uvicorn_logger = logging.getLogger("uvicorn.access")
    uvicorn_logger.handlers = [handler]
    uvicorn_logger.propagate = False

    # Disable debug logs for other packages
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance."""
    return logging.getLogger(name)


def set_request_id(request_id: str) -> None:
    """Set the current request ID in context."""
    _request_id_context.set(request_id)


def get_request_id() -> str:
    """Get the current request ID from context."""
    return _request_id_context.get()


class StructuredLogger:
    """Helper class for structured logging with extra fields."""

    def __init__(self, logger: logging.Logger):
        """Initialize structured logger."""
        self._logger = logger

    def _log(self, level: int, msg: str, **kwargs: Any) -> None:
        """Internal method to log with extra fields."""
        record = self._logger.makeRecord(
            self._logger.name,
            level,
            "(unknown file)",
            0,
            msg,
            (),
            None,
        )
        record.extra_fields = kwargs
        self._logger.handle(record)

    def debug(self, msg: str, **kwargs: Any) -> None:
        """Log at DEBUG level."""
        self._log(logging.DEBUG, msg, **kwargs)

    def info(self, msg: str, **kwargs: Any) -> None:
        """Log at INFO level."""
        self._log(logging.INFO, msg, **kwargs)

    def warning(self, msg: str, **kwargs: Any) -> None:
        """Log at WARNING level."""
        self._log(logging.WARNING, msg, **kwargs)

    def error(self, msg: str, **kwargs: Any) -> None:
        """Log at ERROR level."""
        self._log(logging.ERROR, msg, **kwargs)

    def critical(self, msg: str, **kwargs: Any) -> None:
        """Log at CRITICAL level."""
        self._log(logging.CRITICAL, msg, **kwargs)
