"""Resilient retry logic with exponential backoff and jitter.

This module provides decorators and utilities for implementing production-grade
retry logic with exponential backoff and jitter. Suitable for transient failures
in HTTP requests, database operations, and external API calls.

Examples:
    Use as a decorator for async functions:
        @with_retry(max_retries=5, base_delay=2.0)
        async def post_signal(signal: SignalCandidate) -> Response:
            return await client.post(signal)

    Use directly with async coroutines:
        result = await retry_async(
            post_signal(signal),
            max_retries=5,
            base_delay=2.0
        )
"""

import asyncio
import functools
import logging
import random
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any, TypeVar

__all__ = [
    "with_retry",
    "retry_async",
    "calculate_backoff_delay",
    "RetryError",
    "RetryExhaustedError",
]

T = TypeVar("T")
logger = logging.getLogger(__name__)


# ============================================================================
# Exceptions
# ============================================================================


class RetryError(Exception):
    """Base exception for retry operations."""

    pass


class RetryExhaustedError(RetryError):
    """Raised when all retry attempts have been exhausted.

    Attributes:
        attempts: Number of attempts made before failure
        last_error: The last exception that occurred
        operation: Name of the operation that was retried
        message: Human-readable error message
    """

    def __init__(
        self,
        message: str,
        attempts: int,
        last_error: Exception,
        operation: str = "unknown",
    ) -> None:
        """Initialize RetryExhaustedError.

        Args:
            message: Error message describing the failure
            attempts: Total number of attempts made
            last_error: The final exception that caused exhaustion
            operation: Name of the operation being retried (for logging)
        """
        self.attempts = attempts
        self.last_error = last_error
        self.operation = operation
        super().__init__(message)


# ============================================================================
# Retry Utilities
# ============================================================================


def calculate_backoff_delay(
    attempt: int,
    base_delay: float = 5.0,
    multiplier: float = 2.0,
    max_delay: float = 120.0,
    jitter: bool = True,
) -> float:
    """Calculate backoff delay for a given attempt number.

    Uses exponential backoff: delay = base_delay * (multiplier ^ attempt)
    with optional jitter (±10%) to prevent thundering herd.

    Args:
        attempt: Attempt number (0-based). Attempt 0 = first retry
        base_delay: Base delay in seconds (default: 5.0)
        multiplier: Exponential multiplier (default: 2.0)
        max_delay: Maximum delay cap in seconds (default: 120.0)
        jitter: Add random jitter ±10% to delay (default: True)

    Returns:
        Calculated delay in seconds

    Examples:
        >>> calculate_backoff_delay(0)  # First retry
        5.0
        >>> calculate_backoff_delay(1)  # Second retry
        10.0
        >>> calculate_backoff_delay(2)  # Third retry
        20.0
    """
    if attempt < 0:
        raise ValueError("attempt must be >= 0")
    if base_delay < 0:
        raise ValueError("base_delay must be >= 0")
    if multiplier < 1:
        raise ValueError("multiplier must be >= 1")

    # Calculate exponential delay: base * (multiplier ^ attempt)
    delay = base_delay * (multiplier**attempt)

    # Cap at maximum
    delay = min(delay, max_delay)

    # Add jitter (±10% randomness)
    if jitter:
        jitter_amount = delay * 0.1 * random.uniform(-1, 1)
        delay = max(0, delay + jitter_amount)

    return delay


# ============================================================================
# Retry Decorators & Functions
# ============================================================================


def with_retry(
    func: Callable[..., Awaitable[T]] | None = None,
    *,
    max_retries: int = 5,
    base_delay: float = 5.0,
    backoff_multiplier: float = 2.0,
    jitter: bool = True,
    max_delay: float = 120.0,
    logger_: logging.Logger | None = None,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Decorator for adding retry logic with exponential backoff.

    Retries on any exception. On exhaustion, raises RetryExhaustedError
    with context about the failure.

    Args:
        func: Async function to wrap (when used without parens: @with_retry)
        max_retries: Maximum retry attempts (default: 5)
        base_delay: Base delay between retries in seconds (default: 5.0)
        backoff_multiplier: Multiplier for exponential backoff (default: 2.0)
        jitter: Add random jitter to delays (default: True)
        max_delay: Maximum delay cap in seconds (default: 120.0)
        logger_: Optional logger for retry attempts (default: module logger)

    Returns:
        Decorated async function that retries on failure

    Raises:
        RetryExhaustedError: After max_retries failed attempts

    Examples:
        Basic usage with defaults (5 retries):
            @with_retry
            async def fetch_data():
                return await api.get("/data")

        Custom retry configuration:
            @with_retry(max_retries=3, base_delay=2.0)
            async def post_signal(signal):
                return await client.post_signal(signal)
    """
    # Support both @with_retry and @with_retry() syntax
    if func is None:
        # Called with arguments: @with_retry(max_retries=3)
        def decorator(
            f: Callable[..., Awaitable[T]],
        ) -> Callable[..., Awaitable[T]]:
            return with_retry(
                f,
                max_retries=max_retries,
                base_delay=base_delay,
                backoff_multiplier=backoff_multiplier,
                jitter=jitter,
                max_delay=max_delay,
                logger_=logger_,
            )

        return decorator

    # Called without arguments: @with_retry
    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> T:
        _logger = logger_ or logger
        operation_name = func.__name__

        for attempt in range(max_retries + 1):
            try:
                result = await func(*args, **kwargs)
                if attempt > 0:
                    _logger.info(
                        f"Operation '{operation_name}' succeeded after {attempt} retries"
                    )
                return result

            except Exception as e:
                if attempt >= max_retries:
                    # Exhausted retries, raise with context
                    error_msg = (
                        f"Operation '{operation_name}' failed after {max_retries + 1} attempts. "
                        f"Last error: {type(e).__name__}: {str(e)}"
                    )
                    _logger.error(error_msg, exc_info=True)
                    raise RetryExhaustedError(
                        message=error_msg,
                        attempts=max_retries + 1,
                        last_error=e,
                        operation=operation_name,
                    ) from e

                # Calculate delay for next attempt
                delay = calculate_backoff_delay(
                    attempt=attempt,
                    base_delay=base_delay,
                    multiplier=backoff_multiplier,
                    max_delay=max_delay,
                    jitter=jitter,
                )

                _logger.warning(
                    f"Operation '{operation_name}' failed (attempt {attempt + 1}/{max_retries + 1}). "
                    f"Error: {type(e).__name__}: {str(e)}. "
                    f"Retrying in {delay:.2f}s...",
                    extra={
                        "attempt": attempt + 1,
                        "max_attempts": max_retries + 1,
                        "delay_seconds": delay,
                    },
                )

                await asyncio.sleep(delay)

    return wrapper


async def retry_async(
    coro: Coroutine[Any, Any, T],
    *,
    max_retries: int = 5,
    base_delay: float = 5.0,
    backoff_multiplier: float = 2.0,
    jitter: bool = True,
    max_delay: float = 120.0,
    logger_: logging.Logger | None = None,
) -> T:
    """Retry an async coroutine with exponential backoff.

    Retries on any exception. On exhaustion, raises RetryExhaustedError.

    Args:
        coro: Async coroutine to execute with retries
        max_retries: Maximum retry attempts (default: 5)
        base_delay: Base delay between retries in seconds (default: 5.0)
        backoff_multiplier: Multiplier for exponential backoff (default: 2.0)
        jitter: Add random jitter to delays (default: True)
        max_delay: Maximum delay cap in seconds (default: 120.0)
        logger_: Optional logger for retry attempts (default: module logger)

    Returns:
        Result from successful coroutine execution

    Raises:
        RetryExhaustedError: After max_retries failed attempts

    Examples:
        >>> result = await retry_async(
        ...     post_signal(signal),
        ...     max_retries=3,
        ...     base_delay=2.0
        ... )
    """
    _logger = logger_ or logger
    operation_name = getattr(coro, "__name__", "coroutine")

    for attempt in range(max_retries + 1):
        try:
            result = await coro
            if attempt > 0:
                _logger.info(f"Coroutine succeeded after {attempt} retries")
            return result

        except Exception as e:
            if attempt >= max_retries:
                error_msg = (
                    f"Coroutine failed after {max_retries + 1} attempts. "
                    f"Last error: {type(e).__name__}: {str(e)}"
                )
                _logger.error(error_msg, exc_info=True)
                raise RetryExhaustedError(
                    message=error_msg,
                    attempts=max_retries + 1,
                    last_error=e,
                    operation=operation_name,
                ) from e

            # Calculate delay for next attempt
            delay = calculate_backoff_delay(
                attempt=attempt,
                base_delay=base_delay,
                multiplier=backoff_multiplier,
                max_delay=max_delay,
                jitter=jitter,
            )

            _logger.warning(
                f"Coroutine failed (attempt {attempt + 1}/{max_retries + 1}). "
                f"Error: {type(e).__name__}. Retrying in {delay:.2f}s...",
                extra={"attempt": attempt + 1, "max_attempts": max_retries + 1},
            )

            await asyncio.sleep(delay)
            # Recreate coroutine for next attempt (coroutines are single-use)
            coro = (
                coro.__class__(*coro.cr_frame.f_locals.values())
                if hasattr(coro, "cr_frame")
                else coro
            )

    # Should not reach here
    raise RetryExhaustedError(
        message="Retry logic error: exhaustion not properly detected",
        attempts=max_retries + 1,
        last_error=RuntimeError("Internal retry error"),
        operation=operation_name,
    )
