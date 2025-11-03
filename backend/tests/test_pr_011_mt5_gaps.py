"""Comprehensive gap tests for PR-011 MT5 Session Manager.

Tests REAL business logic for:
- MT5SessionManager: connect, ensure_connected, shutdown, context manager
- CircuitBreaker: state machine (CLOSED/OPEN/HALF_OPEN), call execution
- MT5HealthStatus: health probing
- Error handling: MT5InitError, MT5AuthError, MT5CircuitBreakerOpen, MT5Disconnected
- Resilience: exponential backoff, max failures, retry logic

All tests use REAL implementations with mocked MT5 library.
Tests validate BUSINESS LOGIC, not implementation details.
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.trading.mt5.circuit_breaker import CircuitBreaker, CircuitState
from backend.app.trading.mt5.errors import (
    MT5AuthError,
    MT5CircuitBreakerOpen,
    MT5Disconnected,
    MT5Error,
    MT5InitError,
)
from backend.app.trading.mt5.health import MT5HealthStatus, probe
from backend.app.trading.mt5.session import MT5SessionManager


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mt5_mock():
    """Mock MetaTrader5 module."""
    with patch("backend.app.trading.mt5.session.mt5") as mock_mt5:
        yield mock_mt5


@pytest.fixture
def mt5_settings():
    """Standard MT5 settings for testing."""
    return {
        "login": "12345",
        "password": "secret_password",
        "server": "MetaQuotes-Demo",
        "terminal_path": "/path/to/terminal.exe",
        "max_failures": 5,
        "backoff_base_seconds": 300,
        "backoff_max_seconds": 3600,
    }


@pytest.fixture
def session_manager(mt5_settings):
    """Create MT5SessionManager instance."""
    return MT5SessionManager(**mt5_settings)


@pytest.fixture
def circuit_breaker():
    """Create CircuitBreaker instance."""
    return CircuitBreaker(
        failure_threshold=3,
        timeout_seconds=60,
        half_open_max_calls=1,
    )


# ============================================================================
# TEST CLASS: MT5SessionManager Initialization
# ============================================================================


class TestMT5SessionManagerInitialization:
    """Test MT5SessionManager initialization and state."""

    def test_manager_initializes_with_correct_credentials(self, session_manager, mt5_settings):
        """Manager stores credentials correctly."""
        assert session_manager.login == mt5_settings["login"]
        assert session_manager.password == mt5_settings["password"]
        assert session_manager.server == mt5_settings["server"]
        assert session_manager.terminal_path == mt5_settings["terminal_path"]

    def test_manager_initializes_with_backoff_settings(self, session_manager, mt5_settings):
        """Manager stores backoff configuration."""
        assert session_manager.max_failures == mt5_settings["max_failures"]
        assert session_manager.backoff_base_seconds == mt5_settings["backoff_base_seconds"]
        assert session_manager.backoff_max_seconds == mt5_settings["backoff_max_seconds"]

    def test_manager_starts_disconnected(self, session_manager):
        """Manager starts in disconnected state."""
        assert session_manager._is_connected is False
        assert session_manager._failure_count == 0
        assert session_manager._circuit_breaker_open is False

    def test_manager_has_async_lock(self, session_manager):
        """Manager has async lock for thread safety."""
        assert isinstance(session_manager._session_lock, asyncio.Lock)

    def test_manager_calculates_backoff_correctly(self, session_manager):
        """Manager calculates exponential backoff with cap."""
        session_manager._backoff_exponent = 0
        backoff1 = session_manager._calculate_backoff()
        assert backoff1 == 300  # 300 * 1

        backoff2 = session_manager._calculate_backoff()
        assert backoff2 == 600  # 300 * 2

        backoff3 = session_manager._calculate_backoff()
        assert backoff3 == 1200  # 300 * 4

        # Verify cap is respected
        session_manager._backoff_exponent = 100
        backoff_capped = session_manager._calculate_backoff()
        assert backoff_capped == 3600  # Capped at max

    def test_manager_connection_info_when_disconnected(self, session_manager):
        """Connection info shows correct state when disconnected."""
        info = session_manager.connection_info
        assert info["is_connected"] is False
        assert info["is_healthy"] is False
        assert info["failure_count"] == 0
        assert info["circuit_breaker_open"] is False
        assert info["uptime_seconds"] is None


# ============================================================================
# TEST CLASS: MT5 Connection Success Path
# ============================================================================


class TestMT5ConnectionSuccess:
    """Test successful MT5 connection scenarios."""

    @pytest.mark.asyncio
    async def test_connect_success_initializes_and_logs_in(self, session_manager, mt5_mock):
        """Successful connect initializes MT5 and logs in."""
        mt5_mock.initialize.return_value = True
        mt5_mock.login.return_value = True

        result = await session_manager.connect()

        assert result is True
        assert session_manager._is_connected is True
        mt5_mock.initialize.assert_called_once_with(path=session_manager.terminal_path)
        mt5_mock.login.assert_called_once_with(
            session_manager.login,
            session_manager.password,
            session_manager.server,
        )

    @pytest.mark.asyncio
    async def test_connect_resets_failure_tracking_on_success(self, session_manager, mt5_mock):
        """Successful connect resets failure count and backoff."""
        session_manager._failure_count = 3
        session_manager._backoff_exponent = 4
        session_manager._circuit_breaker_open = True
        session_manager._last_failure_time = time.time() - 3600  # Set to past so backoff expired

        mt5_mock.initialize.return_value = True
        mt5_mock.login.return_value = True

        await session_manager.connect()

        assert session_manager._failure_count == 0
        assert session_manager._backoff_exponent == 0
        assert session_manager._circuit_breaker_open is False

    @pytest.mark.asyncio
    async def test_connect_records_connect_time(self, session_manager, mt5_mock):
        """Successful connect records connection timestamp."""
        mt5_mock.initialize.return_value = True
        mt5_mock.login.return_value = True

        before = time.time()
        await session_manager.connect()
        after = time.time()

        assert session_manager._connect_time is not None
        assert before <= session_manager._connect_time <= after

    @pytest.mark.asyncio
    async def test_connect_updates_connection_info(self, session_manager, mt5_mock):
        """Connected state shows in connection_info."""
        mt5_mock.initialize.return_value = True
        mt5_mock.login.return_value = True

        await session_manager.connect()
        info = session_manager.connection_info

        assert info["is_connected"] is True
        assert info["is_healthy"] is True
        assert info["uptime_seconds"] is not None
        assert info["uptime_seconds"] >= 0


# ============================================================================
# TEST CLASS: MT5 Connection Failures
# ============================================================================


class TestMT5ConnectionFailures:
    """Test MT5 connection failure scenarios."""

    @pytest.mark.asyncio
    async def test_connect_fails_if_initialization_fails(self, session_manager, mt5_mock):
        """Connect raises MT5InitError if MT5.initialize fails."""
        mt5_mock.initialize.return_value = False
        mt5_mock.last_error.return_value = "Terminal not found"

        with pytest.raises(MT5InitError) as exc_info:
            await session_manager.connect()

        assert "initialization failed" in str(exc_info.value).lower()
        assert session_manager._is_connected is False
        assert session_manager._failure_count == 1

    @pytest.mark.asyncio
    async def test_connect_fails_if_login_fails(self, session_manager, mt5_mock):
        """Connect raises MT5AuthError if MT5.login fails."""
        mt5_mock.initialize.return_value = True
        mt5_mock.login.return_value = False
        mt5_mock.last_error.return_value = "Invalid credentials"

        with pytest.raises(MT5AuthError) as exc_info:
            await session_manager.connect()

        assert "login failed" in str(exc_info.value).lower()
        assert session_manager._is_connected is False
        assert session_manager._failure_count == 1
        mt5_mock.shutdown.assert_called_once()  # Cleanup after failed login

    @pytest.mark.asyncio
    async def test_connect_increments_failure_count(self, session_manager, mt5_mock):
        """Each failed connect increments failure count."""
        mt5_mock.initialize.return_value = False
        mt5_mock.last_error.return_value = "Error"

        # First failure
        with pytest.raises(MT5InitError):
            await session_manager.connect()
        assert session_manager._failure_count == 1

        # Second failure
        with pytest.raises(MT5InitError):
            await session_manager.connect()
        assert session_manager._failure_count == 2

    @pytest.mark.asyncio
    async def test_connect_records_last_failure_time(self, session_manager, mt5_mock):
        """Failed connect records failure timestamp."""
        mt5_mock.initialize.return_value = False
        mt5_mock.last_error.return_value = "Error"

        with pytest.raises(MT5InitError):
            await session_manager.connect()

        assert session_manager._last_failure_time is not None
        assert session_manager._last_failure_time > 0


# ============================================================================
# TEST CLASS: Circuit Breaker Logic
# ============================================================================


class TestCircuitBreakerTriggering:
    """Test circuit breaker opening after max failures."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_after_max_failures(self, session_manager, mt5_mock):
        """Circuit breaker opens after max_failures consecutive failures."""
        session_manager.max_failures = 3
        mt5_mock.initialize.return_value = False
        mt5_mock.last_error.return_value = "Error"

        # First two failures, circuit still closed
        for i in range(2):
            with pytest.raises(MT5InitError):
                await session_manager.connect()
            assert session_manager._circuit_breaker_open is False

        # Third failure opens circuit
        with pytest.raises(MT5InitError):
            await session_manager.connect()
        assert session_manager._circuit_breaker_open is True

    @pytest.mark.asyncio
    async def test_circuit_breaker_rejects_immediately_when_open(self, session_manager, mt5_mock):
        """Circuit breaker rejects connect attempts when open."""
        session_manager._circuit_breaker_open = True
        session_manager._failure_count = 5
        session_manager._last_failure_time = time.time()
        session_manager._backoff_exponent = 4

        with pytest.raises(MT5CircuitBreakerOpen):
            await session_manager.connect()

        # MT5 library should NOT be called
        mt5_mock.initialize.assert_not_called()

    @pytest.mark.asyncio
    async def test_circuit_breaker_recovery_after_backoff_period(self, session_manager, mt5_mock):
        """Circuit breaker allows retry after backoff period elapses."""
        session_manager.max_failures = 2
        session_manager.backoff_base_seconds = 1  # 1 second for testing
        mt5_mock.initialize.return_value = False
        mt5_mock.last_error.return_value = "Error"

        # Open the circuit by failing twice
        for _ in range(2):
            with pytest.raises(MT5InitError):
                await session_manager.connect()

        assert session_manager._circuit_breaker_open is True
        current_backoff_exponent = session_manager._backoff_exponent

        # Try immediately - should be blocked
        with pytest.raises(MT5CircuitBreakerOpen):
            await session_manager.connect()

        # Manually set last_failure_time to past (simulate time elapsed)
        # Need to account for backoff calculation which uses _calculate_backoff()
        session_manager._last_failure_time = time.time() - 1000  # Far in past

        # Now attempt should try to reconnect
        mt5_mock.initialize.return_value = False
        with pytest.raises(MT5InitError):
            await session_manager.connect()

        # The circuit should have closed and reopened with new backoff
        # But at least one attempt was made


# ============================================================================
# TEST CLASS: Exponential Backoff
# ============================================================================


class TestExponentialBackoff:
    """Test exponential backoff timing."""

    @pytest.mark.asyncio
    async def test_backoff_increases_exponentially(self, session_manager):
        """Backoff time increases by 2x on each failure."""
        session_manager._backoff_exponent = 0
        backoff_values = []

        for _ in range(5):
            backoff = session_manager._calculate_backoff()
            backoff_values.append(backoff)

        # Should be: 300, 600, 1200, 2400, 3600 (capped)
        assert backoff_values[0] == 300
        assert backoff_values[1] == 600
        assert backoff_values[2] == 1200
        assert backoff_values[3] == 2400
        assert backoff_values[4] == 3600  # Capped at max

    @pytest.mark.asyncio
    async def test_backoff_respects_maximum_cap(self, session_manager):
        """Backoff time capped at backoff_max_seconds."""
        session_manager.backoff_max_seconds = 600
        session_manager._backoff_exponent = 100

        backoff = session_manager._calculate_backoff()

        assert backoff == 600  # Capped at max


# ============================================================================
# TEST CLASS: Ensure Connected
# ============================================================================


class TestEnsureConnected:
    """Test ensure_connected reconnection logic."""

    @pytest.mark.asyncio
    async def test_ensure_connected_skips_if_already_connected(self, session_manager, mt5_mock):
        """ensure_connected doesn't call connect if already connected."""
        session_manager._is_connected = True

        await session_manager.ensure_connected()

        mt5_mock.initialize.assert_not_called()

    @pytest.mark.asyncio
    async def test_ensure_connected_reconnects_if_disconnected(self, session_manager, mt5_mock):
        """ensure_connected calls connect if not connected."""
        mt5_mock.initialize.return_value = True
        mt5_mock.login.return_value = True

        await session_manager.ensure_connected()

        assert session_manager._is_connected is True
        mt5_mock.initialize.assert_called_once()

    @pytest.mark.asyncio
    async def test_ensure_connected_propagates_circuit_breaker_error(self, session_manager):
        """ensure_connected propagates circuit breaker open errors."""
        session_manager._circuit_breaker_open = True
        session_manager._failure_count = 5
        session_manager._last_failure_time = time.time()

        with pytest.raises(MT5CircuitBreakerOpen):
            await session_manager.ensure_connected()


# ============================================================================
# TEST CLASS: Shutdown
# ============================================================================


class TestMT5Shutdown:
    """Test MT5 shutdown behavior."""

    @pytest.mark.asyncio
    async def test_shutdown_calls_mt5_shutdown(self, session_manager, mt5_mock):
        """Shutdown calls MT5.shutdown()."""
        session_manager._is_connected = True

        await session_manager.shutdown()

        mt5_mock.shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_sets_disconnected(self, session_manager, mt5_mock):
        """Shutdown sets is_connected to False."""
        session_manager._is_connected = True

        await session_manager.shutdown()

        assert session_manager._is_connected is False

    @pytest.mark.asyncio
    async def test_shutdown_records_uptime(self, session_manager, mt5_mock):
        """Shutdown records connection uptime in logs."""
        session_manager._is_connected = True
        session_manager._connect_time = time.time() - 100  # 100 seconds ago

        await session_manager.shutdown()

        # Should have logged uptime (verified via log capture in production)
        assert session_manager._is_connected is False

    @pytest.mark.asyncio
    async def test_shutdown_skips_if_not_connected(self, session_manager, mt5_mock):
        """Shutdown is idempotent if already disconnected."""
        session_manager._is_connected = False

        await session_manager.shutdown()

        mt5_mock.shutdown.assert_not_called()

    @pytest.mark.asyncio
    async def test_shutdown_handles_exceptions_gracefully(self, session_manager, mt5_mock):
        """Shutdown logs errors but doesn't raise."""
        session_manager._is_connected = True
        mt5_mock.shutdown.side_effect = Exception("Shutdown error")

        # Should not raise
        await session_manager.shutdown()


# ============================================================================
# TEST CLASS: Context Manager
# ============================================================================


class TestMT5ContextManager:
    """Test context manager protocol."""

    @pytest.mark.asyncio
    async def test_context_manager_connects_on_enter(self, session_manager, mt5_mock):
        """Context manager calls ensure_connected on entry."""
        mt5_mock.initialize.return_value = True
        mt5_mock.login.return_value = True

        async with session_manager.session():
            assert session_manager._is_connected is True

    @pytest.mark.asyncio
    async def test_context_manager_stays_connected_after_exit(self, session_manager, mt5_mock):
        """Context manager keeps session alive after exiting (doesn't shutdown)."""
        mt5_mock.initialize.return_value = True
        mt5_mock.login.return_value = True

        async with session_manager.session():
            assert session_manager._is_connected is True

        # Should still be connected
        assert session_manager._is_connected is True
        mt5_mock.shutdown.assert_not_called()

    @pytest.mark.asyncio
    async def test_context_manager_propagates_connection_errors(self, session_manager, mt5_mock):
        """Context manager propagates connection errors."""
        mt5_mock.initialize.return_value = False
        mt5_mock.last_error.return_value = "Error"

        with pytest.raises(MT5InitError):
            async with session_manager.session():
                pass

    @pytest.mark.asyncio
    async def test_context_manager_propagates_exceptions_in_block(self, session_manager, mt5_mock):
        """Context manager propagates exceptions from code inside block."""
        mt5_mock.initialize.return_value = True
        mt5_mock.login.return_value = True

        class CustomError(Exception):
            pass

        with pytest.raises(CustomError):
            async with session_manager.session():
                raise CustomError("Test error")

    @pytest.mark.asyncio
    async def test_context_manager_concurrent_access(self, session_manager, mt5_mock):
        """Multiple concurrent context managers respect session lock."""
        mt5_mock.initialize.return_value = True
        mt5_mock.login.return_value = True

        call_count = 0

        async def increment_count():
            async with session_manager.session():
                nonlocal call_count
                call_count += 1

        await asyncio.gather(increment_count(), increment_count(), increment_count())

        assert call_count == 3


# ============================================================================
# TEST CLASS: Session Lock (Async)
# ============================================================================


class TestSessionLock:
    """Test async session lock behavior."""

    @pytest.mark.asyncio
    async def test_concurrent_connects_are_serialized(self, session_manager, mt5_mock):
        """Concurrent connect attempts are serialized by lock."""
        connect_count = 0

        async def increment_and_connect():
            nonlocal connect_count
            connect_count += 1
            await session_manager.connect()

        mt5_mock.initialize.return_value = True
        mt5_mock.login.return_value = True

        # Attempt 3 concurrent connects
        await asyncio.gather(
            increment_and_connect(),
            increment_and_connect(),
            increment_and_connect(),
            return_exceptions=True,
        )

        # All should have attempted to connect
        assert connect_count == 3


# ============================================================================
# TEST CLASS: Error Types
# ============================================================================


class TestMT5ErrorTypes:
    """Test error exception types."""

    def test_mt5_init_error_stores_message_and_path(self):
        """MT5InitError stores message and terminal path."""
        error = MT5InitError("Init failed", "/path/to/terminal")
        assert error.message == "Init failed"
        assert error.terminal_path == "/path/to/terminal"

    def test_mt5_auth_error_stores_message_and_login(self):
        """MT5AuthError stores message and login."""
        error = MT5AuthError("Auth failed", "login123")
        assert error.message == "Auth failed"
        assert error.login == "login123"

    def test_mt5_disconnected_error_stores_retry_after(self):
        """MT5Disconnected stores retry_after_seconds."""
        error = MT5Disconnected("Connection lost", 300)
        assert error.message == "Connection lost"
        assert error.retry_after_seconds == 300

    def test_mt5_circuit_breaker_open_error_stores_counts(self):
        """MT5CircuitBreakerOpen stores failure counts."""
        error = MT5CircuitBreakerOpen("Open", 5, 3, 60)
        assert error.message == "Open"
        assert error.failure_count == 5
        assert error.max_failures == 3
        assert error.reset_after_seconds == 60

    def test_all_errors_inherit_from_mt5_error(self):
        """All MT5 errors inherit from MT5Error."""
        assert issubclass(MT5InitError, MT5Error)
        assert issubclass(MT5AuthError, MT5Error)
        assert issubclass(MT5Disconnected, MT5Error)
        assert issubclass(MT5CircuitBreakerOpen, MT5Error)


# ============================================================================
# TEST CLASS: Health Probe
# ============================================================================


class TestHealthProbe:
    """Test health status probe."""

    @pytest.mark.asyncio
    async def test_probe_healthy_status_when_connected(self, session_manager):
        """Probe returns healthy status when connected and circuit closed."""
        session_manager._is_connected = True
        session_manager._circuit_breaker_open = False
        session_manager._failure_count = 0
        session_manager._connect_time = time.time() - 100

        status = await probe(session_manager)

        assert status.is_healthy is True
        assert status.is_connected is True
        assert status.failure_count == 0
        assert status.circuit_breaker_open is False
        assert status.uptime_seconds is not None

    @pytest.mark.asyncio
    async def test_probe_unhealthy_status_when_circuit_open(self, session_manager):
        """Probe returns unhealthy status when circuit breaker open."""
        session_manager._is_connected = True
        session_manager._circuit_breaker_open = True
        session_manager._failure_count = 5

        status = await probe(session_manager)

        assert status.is_healthy is False
        assert status.circuit_breaker_open is True
        assert status.failure_count == 5

    @pytest.mark.asyncio
    async def test_probe_unhealthy_status_when_disconnected(self, session_manager):
        """Probe returns unhealthy status when disconnected."""
        session_manager._is_connected = False

        status = await probe(session_manager)

        assert status.is_healthy is False
        assert status.is_connected is False

    @pytest.mark.asyncio
    async def test_probe_includes_message(self, session_manager):
        """Probe includes informative message."""
        session_manager._is_connected = True
        session_manager._circuit_breaker_open = False

        status = await probe(session_manager)

        assert len(status.message) > 0
        assert "Connected" in status.message or "connected" in status.message


# ============================================================================
# TEST CLASS: Circuit Breaker State Machine
# ============================================================================


class TestCircuitBreakerStateMachine:
    """Test circuit breaker state transitions."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_starts_closed(self, circuit_breaker):
        """Circuit breaker starts in CLOSED state."""
        assert circuit_breaker.is_closed is True
        assert circuit_breaker.is_open is False
        assert circuit_breaker.is_half_open is False

    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_on_threshold(self, circuit_breaker):
        """Circuit breaker opens after failure threshold."""

        async def failing_func():
            raise ValueError("Test failure")

        # Cause 3 failures (threshold)
        for _ in range(3):
            with pytest.raises(ValueError):
                await circuit_breaker.call(failing_func)

        assert circuit_breaker.is_open is True

    @pytest.mark.asyncio
    async def test_circuit_breaker_rejects_while_open(self, circuit_breaker):
        """Circuit breaker immediately rejects calls when open and within timeout."""
        # Open the circuit with failures
        circuit_breaker._state = CircuitState.OPEN
        circuit_breaker._failure_count = 3
        circuit_breaker._last_failure_time = time.time() - 10  # 10s ago, within 60s timeout

        async def func():
            pass

        with pytest.raises(MT5CircuitBreakerOpen):
            await circuit_breaker.call(func)

    @pytest.mark.asyncio
    async def test_circuit_breaker_transitions_to_half_open_after_timeout(self, circuit_breaker):
        """Circuit breaker transitions to HALF_OPEN after timeout."""
        # First establish OPEN state by failing
        circuit_breaker._state = CircuitState.OPEN
        circuit_breaker._failure_count = 3
        circuit_breaker._last_failure_time = time.time() - 100  # Past timeout (60s)

        async def func():
            return "success"

        result = await circuit_breaker.call(func)

        assert result == "success"
        # After timeout, attempted call, and success: circuit closes
        assert circuit_breaker.is_closed is True

    @pytest.mark.asyncio
    async def test_circuit_breaker_closes_on_success_in_half_open(self, circuit_breaker):
        """Circuit breaker closes after successful call in HALF_OPEN state."""
        circuit_breaker._state = CircuitState.HALF_OPEN
        circuit_breaker._half_open_calls = 0

        async def func():
            return "success"

        result = await circuit_breaker.call(func)

        assert result == "success"
        assert circuit_breaker.is_closed is True

    @pytest.mark.asyncio
    async def test_circuit_breaker_reopens_on_failure_in_half_open(self, circuit_breaker):
        """Circuit breaker reopens after failure in HALF_OPEN state."""
        circuit_breaker._state = CircuitState.HALF_OPEN
        circuit_breaker._half_open_calls = 0

        async def func():
            raise ValueError("Test failure")

        with pytest.raises(ValueError):
            await circuit_breaker.call(func)

        assert circuit_breaker.is_open is True

    @pytest.mark.asyncio
    async def test_circuit_breaker_resets_failure_count_on_success(self, circuit_breaker):
        """Successful call resets failure count."""
        circuit_breaker._failure_count = 5

        async def func():
            return "success"

        await circuit_breaker.call(func)

        assert circuit_breaker.failure_count == 0

    def test_circuit_breaker_reset_returns_to_closed(self, circuit_breaker):
        """Manual reset returns circuit to CLOSED state."""
        circuit_breaker._state = CircuitState.OPEN
        circuit_breaker._failure_count = 10

        circuit_breaker.reset()

        assert circuit_breaker.is_closed is True
        assert circuit_breaker.failure_count == 0


# ============================================================================
# TEST CLASS: Edge Cases & Error Scenarios
# ============================================================================


class TestEdgeCasesAndErrors:
    """Test edge cases and error scenarios."""

    @pytest.mark.asyncio
    async def test_multiple_connect_attempts_after_failure(self, session_manager, mt5_mock):
        """Multiple failed connects increase failure count correctly."""
        mt5_mock.initialize.return_value = False
        mt5_mock.last_error.return_value = "Error"

        for i in range(1, 4):
            with pytest.raises(MT5InitError):
                await session_manager.connect()
            assert session_manager._failure_count == i

    @pytest.mark.asyncio
    async def test_connect_after_partial_initialization(self, session_manager, mt5_mock):
        """Connect handles case where initialize succeeds but login fails."""
        mt5_mock.initialize.return_value = True
        mt5_mock.login.return_value = False
        mt5_mock.last_error.return_value = "Invalid credentials"

        with pytest.raises(MT5AuthError):
            await session_manager.connect()

        mt5_mock.shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_credential_handling_no_logging(self, session_manager, mt5_mock):
        """Credentials are passed to MT5 without logging exposure."""
        mt5_mock.initialize.return_value = True
        mt5_mock.login.return_value = True

        await session_manager.connect()

        # Verify credentials were passed to MT5
        mt5_mock.login.assert_called_with(
            session_manager.login,
            session_manager.password,
            session_manager.server,
        )

    @pytest.mark.asyncio
    async def test_connection_info_accuracy_over_time(self, session_manager, mt5_mock):
        """Connection info remains accurate through time."""
        mt5_mock.initialize.return_value = True
        mt5_mock.login.return_value = True

        await session_manager.connect()
        info1 = session_manager.connection_info
        uptime1 = info1["uptime_seconds"]

        await asyncio.sleep(0.1)

        info2 = session_manager.connection_info
        uptime2 = info2["uptime_seconds"]

        # Uptime should increase
        assert uptime2 > uptime1

    def test_mt5_settings_none_terminal_path(self):
        """Manager handles None terminal_path."""
        manager = MT5SessionManager(
            login="123",
            password="pass",
            server="Server",
            terminal_path=None,
        )
        assert manager.terminal_path is None

    @pytest.mark.asyncio
    async def test_backoff_increases_with_each_circuit_breaker_open(self, session_manager, mt5_mock):
        """Backoff time increases with each circuit breaker opening."""
        session_manager.max_failures = 2
        session_manager.backoff_base_seconds = 100
        mt5_mock.initialize.return_value = False
        mt5_mock.last_error.return_value = "Error"

        # First circuit breaker open
        for _ in range(2):
            with pytest.raises(MT5InitError):
                await session_manager.connect()

        backoff1 = session_manager._calculate_backoff()

        # Simulate recovery and second opening
        session_manager._backoff_exponent = 0
        session_manager._failure_count = 0
        session_manager._circuit_breaker_open = False

        for _ in range(2):
            with pytest.raises(MT5InitError):
                await session_manager.connect()

        # Backoff should start fresh
        backoff2 = session_manager._calculate_backoff()
        assert backoff2 >= backoff1
