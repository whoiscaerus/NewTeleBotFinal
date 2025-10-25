"""Tests for MT5 session manager."""

import asyncio
from unittest.mock import patch

import pytest

from backend.app.trading.mt5.errors import (
    MT5AuthError,
    MT5CircuitBreakerOpen,
    MT5InitError,
)
from backend.app.trading.mt5.health import probe
from backend.app.trading.mt5.session import MT5SessionManager


@pytest.fixture
def mt5_manager():
    """Create MT5SessionManager for testing."""
    return MT5SessionManager(
        login="12345678",
        password="testpass",
        server="MetaQuotes-Demo",
        terminal_path="/opt/mt5",
        max_failures=3,
        backoff_base_seconds=60,
        backoff_max_seconds=600,
    )


class TestMT5SessionManagerInit:
    """Test MT5SessionManager initialization."""

    def test_init_creates_manager(self, mt5_manager):
        """Test manager initializes with correct attributes."""
        assert mt5_manager.login == "12345678"
        assert mt5_manager.password == "testpass"
        assert mt5_manager.server == "MetaQuotes-Demo"
        assert mt5_manager.terminal_path == "/opt/mt5"
        assert mt5_manager.max_failures == 3
        assert mt5_manager._is_connected is False
        assert mt5_manager._failure_count == 0
        assert mt5_manager._circuit_breaker_open is False

    def test_connection_info_returns_dict(self, mt5_manager):
        """Test connection_info property returns correct structure."""
        info = mt5_manager.connection_info
        assert isinstance(info, dict)
        assert "is_connected" in info
        assert "is_healthy" in info
        assert "failure_count" in info
        assert "circuit_breaker_open" in info
        assert "uptime_seconds" in info
        assert "server" in info
        assert "login" in info

    def test_is_healthy_when_disconnected(self, mt5_manager):
        """Test is_healthy returns False when disconnected."""
        assert mt5_manager.is_healthy is False

    def test_is_healthy_when_connected(self, mt5_manager):
        """Test is_healthy returns True when connected."""
        mt5_manager._is_connected = True
        mt5_manager._circuit_breaker_open = False
        assert mt5_manager.is_healthy is True

    def test_is_healthy_when_breaker_open(self, mt5_manager):
        """Test is_healthy returns False when circuit breaker open."""
        mt5_manager._is_connected = True
        mt5_manager._circuit_breaker_open = True
        assert mt5_manager.is_healthy is False


class TestMT5Connect:
    """Test MT5SessionManager.connect() method."""

    @pytest.mark.asyncio
    async def test_connect_success(self, mt5_manager):
        """Test successful connection to MT5."""
        with patch("backend.app.trading.mt5.session.mt5") as mock_mt5:
            mock_mt5.initialize.return_value = True
            mock_mt5.login.return_value = True

            success = await mt5_manager.connect()

            assert success is True
            assert mt5_manager._is_connected is True
            assert mt5_manager._failure_count == 0
            assert mt5_manager._circuit_breaker_open is False
            mock_mt5.initialize.assert_called_once()
            mock_mt5.login.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_init_failure(self, mt5_manager):
        """Test connection fails on MT5 initialization error."""
        with patch("backend.app.trading.mt5.session.mt5") as mock_mt5:
            mock_mt5.initialize.return_value = False
            mock_mt5.last_error.return_value = "Terminal not found"

            with pytest.raises(MT5InitError) as exc_info:
                await mt5_manager.connect()

            assert mt5_manager._is_connected is False
            assert mt5_manager._failure_count == 1
            assert "Terminal not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_connect_auth_failure(self, mt5_manager):
        """Test connection fails on authentication error."""
        with patch("backend.app.trading.mt5.session.mt5") as mock_mt5:
            mock_mt5.initialize.return_value = True
            mock_mt5.login.return_value = False
            mock_mt5.last_error.return_value = "Invalid login"

            with pytest.raises(MT5AuthError) as exc_info:
                await mt5_manager.connect()

            assert mt5_manager._is_connected is False
            assert mt5_manager._failure_count == 1
            assert "Invalid login" in str(exc_info.value)
            mock_mt5.shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_circuit_breaker_opens_after_max_failures(self, mt5_manager):
        """Test circuit breaker opens after max failures."""
        with patch("backend.app.trading.mt5.session.mt5") as mock_mt5:
            mock_mt5.initialize.return_value = False
            mock_mt5.last_error.return_value = "Error"

            # Attempt connections until circuit breaker opens
            for i in range(mt5_manager.max_failures):
                with pytest.raises(MT5InitError):
                    await mt5_manager.connect()
                assert mt5_manager._failure_count == i + 1

            # Next attempt should raise CircuitBreakerOpen
            with pytest.raises(MT5CircuitBreakerOpen):
                await mt5_manager.connect()

            assert mt5_manager._circuit_breaker_open is True

    @pytest.mark.asyncio
    async def test_connect_resets_failure_on_success(self, mt5_manager):
        """Test failures reset to 0 on successful connection."""
        with patch("backend.app.trading.mt5.session.mt5") as mock_mt5:
            # First attempt fails
            mock_mt5.initialize.return_value = False
            mock_mt5.last_error.return_value = "Error"
            with pytest.raises(MT5InitError):
                await mt5_manager.connect()

            assert mt5_manager._failure_count == 1

            # Second attempt succeeds
            mock_mt5.initialize.return_value = True
            mock_mt5.login.return_value = True
            success = await mt5_manager.connect()

            assert success is True
            assert mt5_manager._failure_count == 0


class TestMT5EnsureConnected:
    """Test MT5SessionManager.ensure_connected() method."""

    @pytest.mark.asyncio
    async def test_ensure_connected_when_already_connected(self, mt5_manager):
        """Test ensure_connected does nothing when already connected."""
        mt5_manager._is_connected = True

        with patch("backend.app.trading.mt5.session.mt5") as mock_mt5:
            await mt5_manager.ensure_connected()
            # Should not call mt5 methods
            mock_mt5.initialize.assert_not_called()

    @pytest.mark.asyncio
    async def test_ensure_connected_reconnects_when_disconnected(self, mt5_manager):
        """Test ensure_connected reconnects when disconnected."""
        with patch("backend.app.trading.mt5.session.mt5") as mock_mt5:
            mock_mt5.initialize.return_value = True
            mock_mt5.login.return_value = True

            await mt5_manager.ensure_connected()

            assert mt5_manager._is_connected is True
            mock_mt5.initialize.assert_called_once()


class TestMT5Shutdown:
    """Test MT5SessionManager.shutdown() method."""

    @pytest.mark.asyncio
    async def test_shutdown_when_connected(self, mt5_manager):
        """Test shutdown properly closes connection."""
        mt5_manager._is_connected = True
        mt5_manager._connect_time = asyncio.get_event_loop().time()

        with patch("backend.app.trading.mt5.session.mt5") as mock_mt5:
            await mt5_manager.shutdown()

            assert mt5_manager._is_connected is False
            mock_mt5.shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_when_disconnected(self, mt5_manager):
        """Test shutdown when already disconnected."""
        mt5_manager._is_connected = False

        with patch("backend.app.trading.mt5.session.mt5") as mock_mt5:
            await mt5_manager.shutdown()

            # Should not call mt5.shutdown()
            mock_mt5.shutdown.assert_not_called()

    @pytest.mark.asyncio
    async def test_shutdown_handles_errors(self, mt5_manager):
        """Test shutdown handles errors gracefully."""
        mt5_manager._is_connected = True

        with patch("backend.app.trading.mt5.session.mt5") as mock_mt5:
            mock_mt5.shutdown.side_effect = RuntimeError("Shutdown error")

            # Should not raise
            await mt5_manager.shutdown()


class TestMT5SessionContext:
    """Test MT5SessionManager.session() context manager."""

    @pytest.mark.asyncio
    async def test_session_context_manages_lifecycle(self, mt5_manager):
        """Test session context manager ensures connection."""
        with patch("backend.app.trading.mt5.session.mt5") as mock_mt5:
            mock_mt5.initialize.return_value = True
            mock_mt5.login.return_value = True

            async with mt5_manager.session():
                assert mt5_manager._is_connected is True

            # Session still connected after exit
            assert mt5_manager._is_connected is True

    @pytest.mark.asyncio
    async def test_session_context_propagates_errors(self, mt5_manager):
        """Test session context propagates exceptions."""
        with patch("backend.app.trading.mt5.session.mt5") as mock_mt5:
            mock_mt5.initialize.return_value = True
            mock_mt5.login.return_value = True

            with pytest.raises(RuntimeError):
                async with mt5_manager.session():
                    raise RuntimeError("Test error")


class TestMT5Backoff:
    """Test MT5SessionManager exponential backoff."""

    def test_backoff_calculation(self, mt5_manager):
        """Test exponential backoff calculation."""
        assert mt5_manager._calculate_backoff() == 60  # base * 1
        assert mt5_manager._calculate_backoff() == 120  # base * 2
        assert mt5_manager._calculate_backoff() == 240  # base * 4
        assert mt5_manager._calculate_backoff() == 480  # base * 8

    def test_backoff_max_cap(self, mt5_manager):
        """Test backoff respects maximum."""
        # Set backoff very high to test cap
        mt5_manager._backoff_exponent = 100
        backoff = mt5_manager._calculate_backoff()
        assert backoff <= mt5_manager.backoff_max_seconds


class TestMT5HealthProbe:
    """Test MT5 health probe."""

    @pytest.mark.asyncio
    async def test_probe_when_healthy(self, mt5_manager):
        """Test health probe when connection is healthy."""
        mt5_manager._is_connected = True
        mt5_manager._circuit_breaker_open = False
        mt5_manager._failure_count = 0
        mt5_manager._connect_time = asyncio.get_event_loop().time()

        status = await probe(mt5_manager)

        assert status.is_healthy is True
        assert status.is_connected is True
        assert status.circuit_breaker_open is False
        assert status.failure_count == 0
        assert status.uptime_seconds is not None

    @pytest.mark.asyncio
    async def test_probe_when_unhealthy(self, mt5_manager):
        """Test health probe when connection is unhealthy."""
        mt5_manager._is_connected = False
        mt5_manager._circuit_breaker_open = True
        mt5_manager._failure_count = 3

        status = await probe(mt5_manager)

        assert status.is_healthy is False
        assert status.is_connected is False
        assert status.circuit_breaker_open is True
        assert status.failure_count == 3
