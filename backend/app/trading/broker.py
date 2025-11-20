"""
Broker Client Wrapper with Circuit Breaker.
Provides a unified way to wrap broker API calls with circuit breaker protection.
"""

from typing import Optional, TypeVar
from collections.abc import Callable

from backend.app.core.circuit_breaker import CircuitBreaker
from backend.app.core.logging import get_logger
from backend.app.core.redis_cache import _redis_client

logger = get_logger(__name__)

T = TypeVar("T")


class BrokerClient:
    """
    Base client for broker interactions with Circuit Breaker protection.
    """

    def __init__(self, name: str):
        """
        Initialize Broker Client.

        Args:
            name: Unique name for the broker (e.g., "mt5", "binance")
        """
        self.name = name
        self._circuit_breaker: Optional[CircuitBreaker] = None

    @property
    def circuit_breaker(self) -> Optional[CircuitBreaker]:
        """Lazy load circuit breaker."""
        if self._circuit_breaker is None and _redis_client:
            self._circuit_breaker = CircuitBreaker(
                name=f"broker_{self.name}",
                redis=_redis_client,
                failure_threshold=3,  # Stricter threshold for financial ops
                recovery_timeout=30,
            )
        return self._circuit_breaker

    async def execute_with_protection(
        self, func: Callable[..., T], *args, **kwargs
    ) -> T:
        """
        Execute a broker function with circuit breaker protection.

        Args:
            func: Async function to execute
            *args: Arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            Result of func

        Raises:
            CircuitBreakerOpenException: If circuit is open
            Exception: If func fails
        """
        cb = self.circuit_breaker
        if cb:
            return await cb.call(func, *args, **kwargs)

        # Fallback if Redis not available
        return await func(*args, **kwargs)
