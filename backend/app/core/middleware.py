"""Middleware for request tracking and context management.

RequestID middleware ensures every request has a unique identifier for tracing.
"""

import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from backend.app.core.logging import get_logger, set_request_id
from backend.app.core.settings import settings

logger = get_logger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware to add request IDs and correlation tracking."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and add X-Request-Id header."""
        # Get or generate request ID
        request_id = request.headers.get(
            settings.APP_REQUEST_ID_HEADER, str(uuid.uuid4())
        )

        # Store in context for logging
        set_request_id(request_id)

        # Process request
        response = await call_next(request)

        # Add request ID to response headers
        response.headers[settings.APP_REQUEST_ID_HEADER] = request_id

        return response
