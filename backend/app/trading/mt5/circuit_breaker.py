"""Circuit breaker pattern implementation for MT5 trading operations.

This module implements the circuit breaker pattern to protect the trading system
from cascading failures when the MT5 service becomes unavailable.

States:
    CLOSED: Normal operation, all requests pass through
    OPEN: Too many failures, all requests immediately fail
    HALF_OPEN: Recovery test mode, limited requests allowed

Example:
    >>> cb = CircuitBreaker(failure_threshold=3, timeout_seconds=60)
    >>> try:
    ...     result = await cb.call(some_async_function)
    ... except MT5CircuitBreakerOpen:
    ...     print("Service temporarily unavailable")
"""

import time
from collections.abc import Awaitable, Callable
from enum import Enum
from typing import Any, TypeVar

from backend.app.trading.mt5.errors import MT5CircuitBreakerOpen

T = TypeVar("T")


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Too many failures, rejecting requests
    HALF_OPEN = "half_open"  # Testing recovery


class CircuitBreaker:
    """Circuit breaker for MT5 operations.

    Protects the system from cascading failures by tracking failures
    and temporarily rejecting requests when failure threshold is exceeded.

    Attributes:
        failure_threshold: Number of failures before opening circuit
        timeout_seconds: Seconds to wait before attempting recovery
        half_open_max_calls: Max calls allowed in HALF_OPEN state
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        timeout_seconds: int = 60,
        half_open_max_calls: int = 1,
    ):
        """Initialize circuit breaker.

        Args:
            failure_threshold: Failures before OPEN (default: 3)
            timeout_seconds: Seconds before recovery attempt (default: 60)
            half_open_max_calls: Max calls in HALF_OPEN (default: 1)
        """
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.half_open_max_calls = half_open_max_calls

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = 0.0
        self._half_open_calls = 0

    @property
    def state(self) -> CircuitState:
        """Get current circuit state.

        Returns:
            CircuitState: Current state of the circuit breaker
        """
        return self._state

    @property
    def is_closed(self) -> bool:
        """Check if circuit is CLOSED (normal operation).

        Returns:
            bool: True if circuit is CLOSED
        """
        return self._state == CircuitState.CLOSED

    @property
    def is_open(self) -> bool:
        """Check if circuit is OPEN (rejecting requests).

        Returns:
            bool: True if circuit is OPEN
        """
        return self._state == CircuitState.OPEN

    @property
    def is_half_open(self) -> bool:
        """Check if circuit is HALF_OPEN (testing recovery).

        Returns:
            bool: True if circuit is HALF_OPEN
        """
        return self._state == CircuitState.HALF_OPEN

    @property
    def failure_count(self) -> int:
        """Get current failure count.

        Returns:
            int: Number of consecutive failures
        """
        return self._failure_count

    async def call(
        self,
        func: Callable[..., Awaitable[T]],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """Execute function through circuit breaker.

        Args:
            func: Async function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            T: Function result

        Raises:
            MT5CircuitBreakerOpen: If circuit is OPEN
            Exception: Any exception raised by func (propagated)

        Example:
            >>> result = await cb.call(manager.get_price, "EURUSD")
        """
        # Check if we should transition from OPEN to HALF_OPEN
        if self.is_open:
            if time.time() - self._last_failure_time > self.timeout_seconds:
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
            else:
                raise MT5CircuitBreakerOpen(
                    f"Circuit breaker is open. Retry in "
                    f"{self.timeout_seconds - (time.time() - self._last_failure_time):.0f}s"
                )

        # If HALF_OPEN, limit calls
        if self.is_half_open:
            if self._half_open_calls >= self.half_open_max_calls:
                raise MT5CircuitBreakerOpen(
                    "Circuit breaker is testing recovery. Please wait."
                )
            self._half_open_calls += 1

        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except Exception:
            self._on_failure()
            raise

    def _on_success(self) -> None:
        """Handle successful call."""
        self._failure_count = 0

        if self.is_half_open:
            # Successful call in HALF_OPEN, close circuit
            self._state = CircuitState.CLOSED
            self._success_count += 1

    def _on_failure(self) -> None:
        """Handle failed call."""
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self.is_closed:
            if self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN

        elif self.is_half_open:
            # Failure in HALF_OPEN, reopen circuit
            self._state = CircuitState.OPEN

    def reset(self) -> None:
        """Reset circuit to CLOSED state.

        Useful for manual recovery if service is confirmed recovered.
        """
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        self._last_failure_time = 0.0

    def __repr__(self) -> str:
        """String representation of circuit breaker."""
        return (
            f"<CircuitBreaker state={self._state.value} "
            f"failures={self._failure_count}/{self.failure_threshold}>"
        )
