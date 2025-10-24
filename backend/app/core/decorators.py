"""FastAPI decorators for rate limiting and access control."""

import functools
import logging
from typing import Callable, Optional

from fastapi import HTTPException, Request
from starlette.responses import JSONResponse

from backend.app.core.rate_limit import get_rate_limiter

logger = logging.getLogger(__name__)


def rate_limit(
    max_tokens: int = 60,
    refill_rate: int = 1,
    window_seconds: int = 60,
    by: str = "ip",
):
    """Decorator to rate limit an endpoint.
    
    Args:
        max_tokens: Maximum requests in window (default 60)
        refill_rate: Tokens added per second (default 1 = 60/min)
        window_seconds: Time window in seconds (default 60)
        by: Rate limit key source - "ip" (client IP) or "user" (current user ID)
    
    Returns:
        Callable: Decorator function
    
    Raises:
        HTTPException: 429 Too Many Requests if rate limited
    
    Example:
        @router.post("/login")
        @rate_limit(max_tokens=10, refill_rate=0.17, window_seconds=60)  # 10/min
        async def login(request: LoginRequest, request: Request):
            ...
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract request from kwargs or args (FastAPI dependency injection)
            request: Optional[Request] = kwargs.get("request")
            if not request and len(args) > 0:
                # Try to find Request in args
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

            if not request:
                # Fallback: create dummy request (shouldn't happen in FastAPI)
                logger.warning("Could not extract Request from decorated function")
                return await func(*args, **kwargs)

            # Determine rate limit key
            if by == "user":
                # Try to get current user ID from request state
                current_user = getattr(request.state, "current_user", None)
                if current_user:
                    key = f"rate_limit:user:{current_user.id}"
                else:
                    # Fallback to IP if no user
                    key = f"rate_limit:ip:{request.client.host}"
            else:  # by == "ip"
                key = f"rate_limit:ip:{request.client.host}"

            # Check rate limit
            limiter = await get_rate_limiter()
            is_allowed = await limiter.is_allowed(
                key,
                max_tokens=max_tokens,
                refill_rate=refill_rate,
                window_seconds=window_seconds,
            )

            if not is_allowed:
                logger.warning(f"Rate limit exceeded: {key}", extra={"key": key})
                raise HTTPException(
                    status_code=429,
                    detail="Too many requests. Please try again later.",
                )

            # Get remaining tokens for response headers
            remaining = await limiter.get_remaining(
                key,
                max_tokens=max_tokens,
                refill_rate=refill_rate,
                window_seconds=window_seconds,
            )

            # Call wrapped function
            response = await func(*args, **kwargs)

            # Add rate limit headers to response
            if hasattr(response, "headers"):
                response.headers["X-RateLimit-Limit"] = str(max_tokens)
                response.headers["X-RateLimit-Remaining"] = str(remaining)
                response.headers["X-RateLimit-Reset"] = str(int(window_seconds))

            return response

        return wrapper

    return decorator


def abuse_throttle(
    max_failures: int = 5,
    lockout_seconds: int = 300,
    by: str = "ip",
):
    """Decorator to throttle endpoints after repeated failures (e.g., login).
    
    Args:
        max_failures: Number of failures before lockout
        lockout_seconds: Duration of lockout in seconds (default 300 = 5 min)
        by: Throttle key source - "ip" (client IP) or "user" (email/username)
    
    Returns:
        Callable: Decorator function
    
    Raises:
        HTTPException: 429 Too Many Requests if locked out
    
    Example:
        @router.post("/login")
        @abuse_throttle(max_failures=5, lockout_seconds=300)  # 5 failures = 5 min lockout
        async def login(request: LoginRequest, request: Request):
            ...
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract request from kwargs or args
            request: Optional[Request] = kwargs.get("request")
            if not request and len(args) > 0:
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

            if not request:
                logger.warning("Could not extract Request from decorated function")
                return await func(*args, **kwargs)

            # Determine throttle key
            if by == "user":
                # Extract email from request body (for login endpoints)
                key = f"abuse_throttle:user:unknown"  # Will be updated after function call
            else:  # by == "ip"
                key = f"abuse_throttle:ip:{request.client.host}"

            # Check if currently locked out
            limiter = await get_rate_limiter()
            if not limiter._initialized or limiter.redis_client is None:
                logger.debug("Redis not available for abuse throttling")
                return await func(*args, **kwargs)

            # Get failure count
            try:
                failure_count = await limiter.redis_client.get(f"{key}:failures")
                failure_count = int(failure_count or 0)

                if failure_count >= max_failures:
                    logger.warning(
                        f"Abuse throttle lockout: {key}",
                        extra={"key": key, "failures": failure_count},
                    )
                    raise HTTPException(
                        status_code=429,
                        detail=f"Too many failed attempts. Try again in {lockout_seconds} seconds.",
                    )

            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Abuse throttle check error: {e}")
                return await func(*args, **kwargs)

            # Call wrapped function - if it raises 401/403, increment failure counter
            try:
                response = await func(*args, **kwargs)
                # Reset failure count on success
                await limiter.redis_client.delete(f"{key}:failures")
                return response

            except HTTPException as e:
                # On auth failure (401/403), increment failure counter
                if e.status_code in (401, 403):
                    try:
                        await limiter.redis_client.incr(f"{key}:failures")
                        await limiter.redis_client.expire(
                            f"{key}:failures", lockout_seconds
                        )
                        logger.warning(
                            f"Abuse attempt recorded: {key}",
                            extra={"key": key, "status": e.status_code},
                        )
                    except Exception as err:
                        logger.error(f"Failed to record abuse attempt: {err}")

                raise

        return wrapper

    return decorator
