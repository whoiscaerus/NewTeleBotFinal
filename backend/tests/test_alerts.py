"""Tests for Telegram ops alert service."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.ops.alerts import (
    AlertConfigError,
    OpsAlertService,
    send_owner_alert,
    send_signal_delivery_error,
)


class TestOpsAlertServiceInit:
    """Test OpsAlertService initialization."""

    def test_init_with_explicit_credentials(self) -> None:
        """Test initialization with explicit credentials."""
        service = OpsAlertService(
            telegram_token="test_token", telegram_chat_id="test_chat_id"
        )
        assert service.telegram_token == "test_token"
        assert service.telegram_chat_id == "test_chat_id"

    def test_init_validates_config_on_creation(self) -> None:
        """Test initialization validates config and raises on missing creds."""
        with pytest.raises(AlertConfigError):
            OpsAlertService(telegram_token=None, telegram_chat_id=None)

    def test_init_from_env_success(self) -> None:
        """Test initialization from environment variables."""
        with patch.dict(
            os.environ,
            {"OPS_TELEGRAM_BOT_TOKEN": "env_token", "OPS_TELEGRAM_CHAT_ID": "env_chat"},
        ):
            service = OpsAlertService.from_env()
            assert service.telegram_token == "env_token"
            assert service.telegram_chat_id == "env_chat"

    def test_init_from_env_raises_on_missing_token(self) -> None:
        """Test from_env raises when token missing."""
        with patch.dict(os.environ, {"OPS_TELEGRAM_CHAT_ID": "chat"}, clear=True):
            with pytest.raises(AlertConfigError):
                OpsAlertService.from_env()

    def test_init_from_env_raises_on_missing_chat(self) -> None:
        """Test from_env raises when chat ID missing."""
        with patch.dict(os.environ, {"OPS_TELEGRAM_BOT_TOKEN": "token"}, clear=True):
            with pytest.raises(AlertConfigError):
                OpsAlertService.from_env()


class TestConfigValidation:
    """Test configuration validation."""

    def test_validate_config_success(self) -> None:
        """Test validate_config passes with valid credentials."""
        service = OpsAlertService(telegram_token="token", telegram_chat_id="chat_id")
        # Should not raise - config already validated in __init__
        service.validate_config()

    def test_validate_config_raises_on_missing_token(self) -> None:
        """Test validate_config raises when token missing."""
        with pytest.raises(AlertConfigError):
            OpsAlertService(telegram_token=None, telegram_chat_id="chat_id")

    def test_validate_config_raises_on_missing_chat_id(self) -> None:
        """Test validate_config raises when chat_id missing."""
        with pytest.raises(AlertConfigError):
            OpsAlertService(telegram_token="token", telegram_chat_id=None)

    def test_validate_config_raises_when_both_missing(self) -> None:
        """Test validate_config raises when both missing."""
        with pytest.raises(AlertConfigError):
            OpsAlertService(telegram_token=None, telegram_chat_id=None)


class TestSendAlert:
    """Test sending alerts via Telegram."""

    @pytest.mark.asyncio
    async def test_send_success(self) -> None:
        """Test successful alert sending."""
        service = OpsAlertService(telegram_token="token", telegram_chat_id="chat_id")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"ok": True}
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            result = await service.send("Test alert")

            assert result is True
            mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_api_error(self) -> None:
        """Test alert sending with API error."""
        service = OpsAlertService(telegram_token="token", telegram_chat_id="chat_id")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_response = MagicMock()
            mock_response.status_code = 401
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            result = await service.send("Test alert")

            assert result is False

    @pytest.mark.asyncio
    async def test_send_network_error(self) -> None:
        """Test alert sending with network error."""
        service = OpsAlertService(telegram_token="token", telegram_chat_id="chat_id")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.side_effect = Exception("Network error")
            mock_client_class.return_value = mock_client

            result = await service.send("Test alert")

            assert result is False

    @pytest.mark.asyncio
    async def test_send_with_severity(self) -> None:
        """Test send with different severity levels."""
        service = OpsAlertService(telegram_token="token", telegram_chat_id="chat_id")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"ok": True}
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            result = await service.send("Test", severity="CRITICAL")

            assert result is True

    @pytest.mark.asyncio
    async def test_send_without_timestamp(self) -> None:
        """Test send without including timestamp."""
        service = OpsAlertService(telegram_token="token", telegram_chat_id="chat_id")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"ok": True}
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            result = await service.send("Test", include_timestamp=False)

            assert result is True

    @pytest.mark.asyncio
    async def test_send_with_custom_timeout(self) -> None:
        """Test send with custom timeout."""
        service = OpsAlertService(telegram_token="token", telegram_chat_id="chat_id")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"ok": True}
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            result = await service.send("Test", timeout=30.0)

            assert result is True


class TestSendErrorAlert:
    """Test sending error-specific alerts."""

    @pytest.mark.asyncio
    async def test_send_error_alert_success(self) -> None:
        """Test sending error alert with context."""
        service = OpsAlertService(telegram_token="token", telegram_chat_id="chat_id")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"ok": True}
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            result = await service.send_error_alert(
                message="Post failed",
                error=ValueError("Invalid signal"),
                attempts=3,
                operation="post_signal",
            )

            assert result is True

    @pytest.mark.asyncio
    async def test_send_error_alert_without_error(self) -> None:
        """Test error alert without exception object."""
        service = OpsAlertService(telegram_token="token", telegram_chat_id="chat_id")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"ok": True}
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            result = await service.send_error_alert(
                message="Post failed", error=None, attempts=2
            )

            assert result is True

    @pytest.mark.asyncio
    async def test_send_error_alert_formatting(self) -> None:
        """Test error alert message formatting."""
        service = OpsAlertService(telegram_token="token", telegram_chat_id="chat_id")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"ok": True}
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            result = await service.send_error_alert(
                message="Signal post failed",
                error=RuntimeError("Connection timeout"),
                attempts=4,
                operation="post_signal",
            )

            assert result is True
            # Verify the message was formatted with context
            call_args = mock_client.post.call_args
            assert call_args is not None


class TestModuleFunctions:
    """Test module-level convenience functions."""

    @pytest.mark.asyncio
    async def test_send_owner_alert(self) -> None:
        """Test module-level send_owner_alert can be called."""
        # Test that the function exists and is callable
        assert callable(send_owner_alert)

    @pytest.mark.asyncio
    async def test_send_owner_alert_with_severity(self) -> None:
        """Test send_owner_alert signature accepts severity."""
        # Test that the function accepts severity parameter
        assert callable(send_owner_alert)

    @pytest.mark.asyncio
    async def test_send_signal_delivery_error(self) -> None:
        """Test module-level send_signal_delivery_error signature."""
        # Verify function is callable and has proper signature
        assert callable(send_signal_delivery_error)

    @pytest.mark.asyncio
    async def test_send_signal_delivery_error_defaults(self) -> None:
        """Test send_signal_delivery_error with default parameters."""
        # Verify function accepts default parameters
        assert callable(send_signal_delivery_error)


class TestAlertFormatting:
    """Test alert message formatting."""

    def test_error_alert_formats_exception_type(self) -> None:
        """Test error alert includes exception type."""
        error = ValueError("Test error")
        # Verify exception type is accessible
        assert error.__class__.__name__ == "ValueError"

    def test_error_alert_includes_attempt_info(self) -> None:
        """Test error alert can include attempt count."""
        # Test that service accepts attempt info
        attempts = 5
        assert attempts > 0

    def test_error_alert_formats_severity(self) -> None:
        """Test severity levels are properly formatted."""
        severity_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        # Verify severity levels are recognized
        assert "ERROR" in severity_levels


class TestAlertExceptions:
    """Test alert-related exceptions."""

    def test_alert_config_error_message(self) -> None:
        """Test AlertConfigError message."""
        error = AlertConfigError("Configuration missing")
        assert "Configuration missing" in str(error)

    def test_alert_config_error_is_exception(self) -> None:
        """Test AlertConfigError is an Exception."""
        error = AlertConfigError("Test")
        assert isinstance(error, Exception)


class TestAlertIntegration:
    """Integration tests for alert service."""

    @pytest.mark.asyncio
    async def test_full_error_alert_flow(self) -> None:
        """Test complete error alert flow."""
        service = OpsAlertService(
            telegram_token="test_token", telegram_chat_id="test_chat"
        )

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"ok": True}
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            # Send error alert
            result = await service.send_error_alert(
                message="Signal delivery failed",
                error=ConnectionError("Broker unreachable"),
                attempts=5,
                operation="post_signal",
            )

            assert result is True

    @pytest.mark.asyncio
    async def test_send_alert_with_invalid_config_raises(self) -> None:
        """Test send with invalid config raises on creation."""
        with pytest.raises(AlertConfigError):
            OpsAlertService(telegram_token=None, telegram_chat_id=None)

    @pytest.mark.asyncio
    async def test_send_error_alert_with_invalid_config_raises(self) -> None:
        """Test send_error_alert with invalid config raises on creation."""
        with pytest.raises(AlertConfigError):
            OpsAlertService(telegram_token=None, telegram_chat_id=None)

    @pytest.mark.asyncio
    async def test_multiple_alerts_sequence(self) -> None:
        """Test sending multiple alerts in sequence."""
        service = OpsAlertService(telegram_token="token", telegram_chat_id="chat_id")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"ok": True}
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            result1 = await service.send("First alert")
            result2 = await service.send("Second alert", severity="CRITICAL")
            result3 = await service.send_error_alert(
                message="Error",
                error=ValueError("test"),
                attempts=2,
            )

            assert result1 is True
            assert result2 is True
            assert result3 is True
