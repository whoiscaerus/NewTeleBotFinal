"""Request ID middleware for correlation tracking."""

import json
import logging
import uuid
from collections.abc import Callable
from contextvars import ContextVar
from typing import cast

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.datastructures import MutableHeaders
from starlette.middleware.base import BaseHTTPMiddleware

from backend.app.core.idempotency import RedisIdempotencyStorage
from backend.app.core.redis import get_redis

# Context variable for request ID
request_id_var: ContextVar[str] = ContextVar("request_id", default="")

logger = logging.getLogger(__name__)


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


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """
    Middleware to ensure idempotency for POST/PATCH requests.
    Uses Redis to store response for a given Idempotency-Key.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        key = request.headers.get("Idempotency-Key")
        if not key:
            return cast(Response, await call_next(request))

        # Only idempotent methods usually, but PR spec says "generic middleware"
        # We usually only want this for POST/PATCH. GET is naturally idempotent.
        if request.method not in ["POST", "PATCH", "PUT", "DELETE"]:
            return cast(Response, await call_next(request))

        try:
            redis_client = await get_redis()
            storage = RedisIdempotencyStorage(redis_client)

            # 1. Check cache
            cached = await storage.get(key)
            if cached:
                logger.info(f"Idempotency hit for key: {key}")
                headers = MutableHeaders(headers=cached.get("headers", {}))
                headers["X-Idempotency-Hit"] = "true"
                return JSONResponse(
                    content=cached.get("body"),
                    status_code=cached.get("status_code", 200),
                    headers=headers,
                )

            # 2. Acquire lock
            # TTL: 60s for processing lock
            if not await storage.lock(key, ttl=60):
                logger.warning(f"Idempotency conflict for key: {key}")
                return JSONResponse(
                    content={"detail": "Request already in progress"}, status_code=409
                )

            # 3. Process request
            try:
                response = cast(Response, await call_next(request))

                # We can only cache successful responses or specific errors?
                # Usually we cache everything to ensure idempotency.
                # But we need to read the body.

                response_body = b""
                async for chunk in response.body_iterator:  # type: ignore
                    response_body += chunk

                # Reconstruct response for return
                new_response = Response(
                    content=response_body,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.media_type,
                )

                # 4. Cache response (if 2xx/3xx/4xx?)
                # We cache the result so retries get the same result.
                # TTL: 24h (86400s)

                # Parse body if JSON, otherwise store as string/bytes?
                # RedisIdempotencyStorage expects dict for response.
                # We need to serialize the body.

                try:
                    body_json = json.loads(response_body)
                except Exception:
                    body_json = response_body.decode("utf-8")

                cache_data = {
                    "body": body_json,
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                }

                await storage.set(key, cache_data, ttl=86400)

                return new_response

            finally:
                # 5. Release lock
                await storage.unlock(key)

        except Exception as e:
            logger.error(f"Idempotency middleware error: {e}", exc_info=True)
            # Fallback to normal processing if redis fails?
            # Or fail safe?
            # If we can't check idempotency, we might duplicate.
            # Safer to fail or proceed?
            # Proceeding risks duplication. Failing risks availability.
            # Let's proceed but log error.
            return cast(Response, await call_next(request))
