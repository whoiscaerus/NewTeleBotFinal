"""MT5 session manager with resilience patterns."""

import asyncio
import logging
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import MetaTrader5 as mt5

from backend.app.trading.mt5.errors import (
    MT5AuthError,
    MT5CircuitBreakerOpen,
    MT5InitError,
)

logger = logging.getLogger(__name__)


class MT5SessionManager:
    """Manages MetaTrader5 session lifecycle with resilience.

    Handles initialization, authentication, reconnection, and graceful shutdown
    with exponential backoff and circuit breaker patterns.
    """

    def __init__(
        self,
        login: str,
        password: str,
        server: str,
        terminal_path: str | None = None,
        max_failures: int = 5,
        backoff_base_seconds: int = 300,
        backoff_max_seconds: int = 3600,
    ):
        """Initialize MT5SessionManager.

        Args:
            login: MT5 account login
            password: MT5 account password
            server: MT5 server (e.g., "MetaQuotes-Demo")
            terminal_path: Path to MT5 terminal executable
            max_failures: Max consecutive failures before circuit breaker opens
            backoff_base_seconds: Base backoff time (300s = 5min)
            backoff_max_seconds: Max backoff time (3600s = 1h)
        """
        self.login = login
        self.password = password
        self.server = server
        self.terminal_path = terminal_path
        self.max_failures = max_failures
        self.backoff_base_seconds = backoff_base_seconds
        self.backoff_max_seconds = backoff_max_seconds

        # State
        self._is_connected = False
        self._failure_count = 0
        self._circuit_breaker_open = False
        self._last_failure_time: float | None = None
        self._connect_time: float | None = None
        self._backoff_exponent = 0
        self._session_lock = asyncio.Lock()

    async def connect(self) -> bool:
        """Connect to MT5.

        Returns:
            True if connection successful, False otherwise

        Raises:
            MT5InitError: If MT5 initialization fails
            MT5AuthError: If login fails
            MT5CircuitBreakerOpen: If circuit breaker is open
        """
        async with self._session_lock:
            if self._circuit_breaker_open:
                # Check if backoff period has elapsed
                if self._last_failure_time:
                    elapsed = time.time() - self._last_failure_time
                    backoff = self._calculate_backoff()
                    if elapsed < backoff:
                        raise MT5CircuitBreakerOpen(
                            "Circuit breaker open due to repeated failures",
                            self._failure_count,
                            self.max_failures,
                            int(backoff - elapsed),
                        )
                    else:
                        # Reset after backoff period
                        logger.info(
                            "Circuit breaker backoff elapsed, attempting reconnect",
                            extra={"failure_count": self._failure_count},
                        )
                        self._backoff_exponent = 0
                        self._circuit_breaker_open = False
                else:
                    raise MT5CircuitBreakerOpen(
                        "Circuit breaker open",
                        self._failure_count,
                        self.max_failures,
                    )

            try:
                # Initialize MT5
                if not mt5.initialize(
                    path=self.terminal_path,
                ):
                    error_msg = mt5.last_error()
                    raise MT5InitError(
                        f"MT5 initialization failed: {error_msg}",
                        self.terminal_path,
                    )

                # Attempt login
                if not mt5.login(self.login, self.password, self.server):
                    error_msg = mt5.last_error()
                    mt5.shutdown()
                    raise MT5AuthError(
                        f"MT5 login failed: {error_msg}",
                        self.login,
                    )

                # Success: reset failure tracking
                self._is_connected = True
                self._failure_count = 0
                self._circuit_breaker_open = False
                self._backoff_exponent = 0
                self._connect_time = time.time()
                self._last_failure_time = None

                logger.info(
                    "MT5 connected successfully",
                    extra={
                        "login": self.login,
                        "server": self.server,
                        "connect_time": self._connect_time,
                    },
                )

                return True

            except (MT5InitError, MT5AuthError) as e:
                self._is_connected = False
                self._failure_count += 1
                self._last_failure_time = time.time()

                logger.error(
                    f"MT5 connection failed: {e.message}",
                    extra={
                        "failure_count": self._failure_count,
                        "max_failures": self.max_failures,
                        "error_type": type(e).__name__,
                    },
                )

                if self._failure_count >= self.max_failures:
                    self._circuit_breaker_open = True
                    logger.warning(
                        "MT5 circuit breaker opened",
                        extra={
                            "failure_count": self._failure_count,
                            "backoff_seconds": self._calculate_backoff(),
                        },
                    )

                raise

    async def ensure_connected(self) -> None:
        """Ensure MT5 is connected, reconnecting if needed.

        Raises:
            MT5CircuitBreakerOpen: If circuit breaker is open
            MT5InitError: If connection fails
            MT5AuthError: If authentication fails
        """
        if not self._is_connected:
            logger.info("MT5 not connected, attempting to reconnect")
            await self.connect()

    async def shutdown(self) -> None:
        """Cleanly shutdown MT5 session.

        Logs the shutdown and performs proper cleanup.
        """
        async with self._session_lock:
            try:
                if self._is_connected:
                    mt5.shutdown()
                    self._is_connected = False
                    uptime = None
                    if self._connect_time:
                        uptime = time.time() - self._connect_time
                    logger.info(
                        "MT5 shutdown complete",
                        extra={
                            "uptime_seconds": uptime,
                            "total_failures": self._failure_count,
                        },
                    )
            except Exception as e:
                logger.error(
                    f"Error during MT5 shutdown: {e}",
                    extra={"error_type": type(e).__name__},
                    exc_info=True,
                )

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[None, None]:
        """Context manager for MT5 session lifecycle.

        Usage:
            async with manager.session():
                # MT5 is connected here
                mt5.get_rates(...)

        Raises:
            MT5InitError: If connection fails
            MT5AuthError: If login fails
            MT5CircuitBreakerOpen: If circuit breaker is open
        """
        await self.ensure_connected()
        try:
            yield
        except Exception as e:
            logger.error(
                f"Error in MT5 session: {e}",
                extra={"error_type": type(e).__name__},
                exc_info=True,
            )
            raise
        finally:
            # Session stays connected for reuse
            # Only shutdown explicitly when done with manager
            pass

    def _calculate_backoff(self) -> int:
        """Calculate exponential backoff time.

        Returns:
            Backoff time in seconds, capped at backoff_max_seconds
        """
        if self._backoff_exponent == 0:
            self._backoff_exponent = 1
        else:
            self._backoff_exponent *= 2

        backoff = min(
            self.backoff_base_seconds * self._backoff_exponent,
            self.backoff_max_seconds,
        )
        return int(backoff)

    @property
    def is_healthy(self) -> bool:
        """Check if MT5 session is healthy.

        Returns:
            True if connected and circuit breaker not open
        """
        return self._is_connected and not self._circuit_breaker_open

    @property
    def connection_info(self) -> dict[str, Any]:
        """Get current connection info for metrics/logging.

        Returns:
            Dictionary with connection status information
        """
        uptime = None
        if self._connect_time:
            uptime = time.time() - self._connect_time

        return {
            "is_connected": self._is_connected,
            "is_healthy": self.is_healthy,
            "failure_count": self._failure_count,
            "circuit_breaker_open": self._circuit_breaker_open,
            "uptime_seconds": uptime,
            "server": self.server,
            "login": self.login,
        }
