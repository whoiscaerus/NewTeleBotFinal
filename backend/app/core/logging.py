"""Structured JSON logging configuration."""

import json
import logging
import logging.config
import sys
from datetime import datetime
from typing import Any

from backend.app.core.settings import settings


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add request context if available
        if hasattr(record, "request_id"):
            log_data["request_id"] = record.request_id

        # Add extra fields
        if hasattr(record, "extra_fields"):
            log_data.update(record.extra_fields)

        # Add exception info
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


def configure_logging() -> None:
    """Configure structured JSON logging."""
    config = {
        "version": 1,
        "disable_existing_loggers": False,
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
            },
            "error": {
                "level": "ERROR",
                "class": "logging.StreamHandler",
                "formatter": "json" if settings.app.env == "production" else "standard",
                "stream": sys.stderr,
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
    return logging.LoggerAdapter(logger, {})


# Configure on import
configure_logging()
