"""Request ID middleware for correlation tracking."""

import uuid
from collections.abc import Callable
from contextvars import ContextVar

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

# Context variable for request ID
request_id_var: ContextVar[str] = ContextVar("request_id", default="")


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware to add request ID to all requests."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and add request ID."""
        # Get or create request ID
        request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))

        # Store in context
        token = request_id_var.set(request_id)

        # Add to request
        request.state.request_id = request_id

        try:
            # Add to response headers
            response: Response = await call_next(request)
            response.headers["X-Request-Id"] = request_id
            return response
        finally:
            request_id_var.reset(token)


def get_request_id() -> str:
    """Get current request ID from context."""
    return request_id_var.get()
