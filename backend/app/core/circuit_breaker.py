"""
Circuit Breaker implementation using Redis for distributed state.
Prevents cascading failures when external services are down.
"""

import enum
import time
from typing import Any, TypeVar
from collections.abc import Callable

from redis.asyncio import Redis

from backend.app.core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class CircuitState(str, enum.Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpenException(Exception):
    """Raised when circuit is open and calls are rejected."""

    pass


class CircuitBreaker:
    """
    Distributed Circuit Breaker using Redis.

    States:
    - CLOSED: Normal operation. Failures count towards threshold.
    - OPEN: Fails fast. No calls executed.
    - HALF_OPEN: Allows one test request. Success -> CLOSED, Failure -> OPEN.
    """

    def __init__(
        self,
        name: str,
        redis: Redis,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
    ):
        """
        Initialize Circuit Breaker.

        Args:
            name: Unique name for the circuit (e.g., "telegram_api")
            redis: Redis client instance
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds to wait before trying Half-Open
        """
        self.name = name
        self.redis = redis
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout

        # Redis keys
        self._state_key = f"circuit:{name}:state"
        self._failure_key = f"circuit:{name}:failures"
        self._last_failure_key = f"circuit:{name}:last_failure"

    async def call(self, func: Callable[..., Any], *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection.

        Raises:
            CircuitBreakerOpenException: If circuit is open
            Exception: If the wrapped function fails
        """
        state = await self._get_state()

        if state == CircuitState.OPEN:
            # Check if recovery timeout has passed
            last_failure = await self.redis.get(self._last_failure_key)
            if last_failure:
                elapsed = time.time() - float(last_failure)
                if elapsed > self.recovery_timeout:
                    # Transition to HALF_OPEN
                    await self._set_state(CircuitState.HALF_OPEN)
                    logger.info(f"Circuit {self.name} entering HALF_OPEN state")
                else:
                    raise CircuitBreakerOpenException(f"Circuit {self.name} is OPEN")
            else:
                # Should not happen if state is OPEN, but safe fallback
                await self._set_state(CircuitState.CLOSED)

        if state == CircuitState.HALF_OPEN:
            # In distributed system, multiple requests might race here.
            # We allow them, but first failure sends back to OPEN.
            pass

        try:
            result = await func(*args, **kwargs)
            await self._record_success()
            return result
        except Exception as e:
            await self._record_failure()
            raise e

    async def _get_state(self) -> CircuitState:
        """Get current state from Redis."""
        state = await self.redis.get(self._state_key)
        if not state:
            return CircuitState.CLOSED
        return CircuitState(state.decode("utf-8"))

    async def _set_state(self, state: CircuitState):
        """Set state in Redis."""
        await self.redis.set(self._state_key, state.value)

    async def _record_success(self):
        """Handle successful execution."""
        state = await self._get_state()
        if state == CircuitState.HALF_OPEN:
            await self._set_state(CircuitState.CLOSED)
            await self.redis.delete(self._failure_key)
            logger.info(f"Circuit {self.name} recovered (CLOSED)")
        elif state == CircuitState.CLOSED:
            # Optional: Reset failure count on success?
            # Usually we reset only if it was non-zero, or let them expire.
            # For simplicity, we reset failures on success in CLOSED state too
            # to represent "consecutive" failures.
            await self.redis.delete(self._failure_key)

    async def _record_failure(self):
        """Handle failed execution."""
        state = await self._get_state()

        # Update last failure time
        await self.redis.set(self._last_failure_key, time.time())

        if state == CircuitState.HALF_OPEN:
            await self._set_state(CircuitState.OPEN)
            logger.warning(f"Circuit {self.name} probe failed -> OPEN")
            return

        if state == CircuitState.CLOSED:
            failures = await self.redis.incr(self._failure_key)
            if failures >= self.failure_threshold:
                await self._set_state(CircuitState.OPEN)
                logger.error(
                    f"Circuit {self.name} threshold reached ({failures}) -> OPEN"
                )
