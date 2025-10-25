"""Integration tests for HmacClient."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.strategy.fib_rsi.schema import SignalCandidate
from backend.app.trading.outbound.client import HmacClient, _get_rfc3339_timestamp
from backend.app.trading.outbound.config import OutboundConfig
from backend.app.trading.outbound.exceptions import OutboundClientError
from backend.app.trading.outbound.responses import SignalIngestResponse


@pytest.fixture
def config() -> OutboundConfig:
    """Create test configuration."""
    return OutboundConfig(
        producer_id="test-producer",
        producer_secret="test-secret-key-min-16-bytes-long",
        server_base_url="https://api.example.com",
        enabled=True,
        timeout_seconds=30.0,
        max_body_size=65536,
    )


@pytest.fixture
def logger():
    """Create mock logger."""
    return MagicMock()


@pytest.fixture
def signal() -> SignalCandidate:
    """Create test signal."""
    return SignalCandidate(
        instrument="GOLD",
        side="buy",
        entry_price=1950.50,
        stop_loss=1945.00,
        take_profit=1960.00,
        confidence=0.85,
        reason="test_signal",
        timestamp=datetime(2025, 10, 25, 14, 30, 45, 123456),
        payload={"rsi": 35, "atr": 5.5},
    )


class TestHmacClientInitialization:
    """Test HmacClient initialization."""

    def test_hmac_client_init(self, config, logger) -> None:
        """Test client initializes with valid config."""
        client = HmacClient(config, logger)

        assert client.config == config
        assert client.logger == logger
        assert client._session is None

    def test_hmac_client_init_invalid_config(self, logger) -> None:
        """Test client raises on invalid config."""
        with pytest.raises(ValueError, match="producer_secret must be at least 16"):
            OutboundConfig(
                producer_id="test",
                producer_secret="short",  # Too short
                server_base_url="https://api.example.com",
            )

    def test_hmac_client_repr(self, config, logger) -> None:
        """Test client string representation."""
        client = HmacClient(config, logger)
        repr_str = repr(client)

        assert "HmacClient" in repr_str
        assert "test-producer" in repr_str
        assert "https://api.example.com" in repr_str


class TestHmacClientContextManager:
    """Test HmacClient context manager."""

    @pytest.mark.asyncio
    async def test_client_context_manager(self, config, logger) -> None:
        """Test client works as async context manager."""
        async with HmacClient(config, logger) as client:
            assert client._session is not None

    @pytest.mark.asyncio
    async def test_client_closes_session(self, config, logger) -> None:
        """Test client closes session properly."""
        client = HmacClient(config, logger)
        await client._ensure_session()

        assert client._session is not None
        await client.close()
        assert client._session is None


class TestHmacClientPostSignal:
    """Test HmacClient.post_signal method."""

    @pytest.mark.asyncio
    async def test_post_signal_success(self, config, logger, signal) -> None:
        """Test successful signal posting."""
        client = HmacClient(config, logger)

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_session = AsyncMock()
            mock_client_class.return_value = mock_session

            # Mock successful response
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = {
                "signal_id": "sig-abc123",
                "status": "pending_approval",
                "server_timestamp": "2025-10-25T14:30:45.123456Z",
                "message": "Signal received",
                "errors": None,
            }
            mock_session.post.return_value = mock_response

            await client._ensure_session()
            response = await client.post_signal(signal)

            assert isinstance(response, SignalIngestResponse)
            assert response.signal_id == "sig-abc123"
            assert response.status == "pending_approval"

    @pytest.mark.asyncio
    async def test_post_signal_validates_empty_instrument(self, config, logger) -> None:
        """Test that empty instrument is rejected by Pydantic."""
        from pydantic_core import ValidationError

        # SignalCandidate validates at creation time
        with pytest.raises(ValidationError, match="String should have at least 2"):
            SignalCandidate(
                instrument="",  # Empty - rejected by Pydantic
                side="buy",
                entry_price=1950.50,
                stop_loss=1945.00,
                take_profit=1960.00,
                confidence=0.85,
                reason="test",
                timestamp=datetime(2025, 10, 25, 14, 30, 45, 123456),
                payload={},
            )

    @pytest.mark.asyncio
    async def test_post_signal_validates_invalid_side(self, config, logger) -> None:
        """Test that invalid side is rejected by Pydantic."""
        from pydantic_core import ValidationError

        # SignalCandidate validates at creation time
        with pytest.raises(ValidationError, match="String should match pattern"):
            SignalCandidate(
                instrument="GOLD",
                side="invalid",  # Invalid - rejected by Pydantic
                entry_price=1950.50,
                stop_loss=1945.00,
                take_profit=1960.00,
                confidence=0.85,
                reason="test",
                timestamp=datetime(2025, 10, 25, 14, 30, 45, 123456),
                payload={},
            )

    @pytest.mark.asyncio
    async def test_post_signal_validates_negative_price(self, config, logger) -> None:
        """Test that negative price is rejected by Pydantic."""
        from pydantic_core import ValidationError

        # SignalCandidate validates at creation time
        with pytest.raises(ValidationError, match="Input should be greater than 0"):
            SignalCandidate(
                instrument="GOLD",
                side="buy",
                entry_price=-100.0,  # Negative - rejected by Pydantic
                stop_loss=1945.00,
                take_profit=1960.00,
                confidence=0.85,
                reason="test",
                timestamp=datetime(2025, 10, 25, 14, 30, 45, 123456),
                payload={},
            )

    @pytest.mark.asyncio
    async def test_post_signal_validates_body_size(
        self, config, logger, signal
    ) -> None:
        """Test that config rejects oversized body config."""
        # Config validation happens at creation time
        with pytest.raises(ValueError, match="max_body_size must be"):
            OutboundConfig(
                producer_id="test-producer",
                producer_secret="test-secret-key-min-16-bytes-long",
                server_base_url="https://api.example.com",
                max_body_size=100,  # Very small - rejected by validation
            )

    @pytest.mark.asyncio
    async def test_post_signal_handles_http_400(self, config, logger, signal) -> None:
        """Test handling of HTTP 400 error."""
        client = HmacClient(config, logger)

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_session = AsyncMock()
            mock_client_class.return_value = mock_session

            mock_response = MagicMock()
            mock_response.status_code = 400
            mock_response.json.return_value = {"errors": ["Invalid instrument"]}
            mock_session.post.return_value = mock_response

            await client._ensure_session()

            with pytest.raises(OutboundClientError, match="rejected"):
                await client.post_signal(signal)

    @pytest.mark.asyncio
    async def test_post_signal_handles_http_500(self, config, logger, signal) -> None:
        """Test handling of HTTP 500 error."""
        client = HmacClient(config, logger)

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_session = AsyncMock()
            mock_client_class.return_value = mock_session

            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.text = "Internal server error"
            mock_session.post.return_value = mock_response

            await client._ensure_session()

            with pytest.raises(OutboundClientError, match="Server error"):
                await client.post_signal(signal)

    @pytest.mark.asyncio
    async def test_post_signal_handles_timeout(self, config, logger, signal) -> None:
        """Test handling of timeout."""
        client = HmacClient(config, logger)

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_session = AsyncMock()
            mock_client_class.return_value = mock_session

            import httpx

            mock_session.post.side_effect = httpx.TimeoutException("Request timeout")

            await client._ensure_session()

            with pytest.raises(TimeoutError):
                await client.post_signal(signal)

    @pytest.mark.asyncio
    async def test_post_signal_headers_include_signature(
        self, config, logger, signal
    ) -> None:
        """Test that headers include HMAC signature."""
        client = HmacClient(config, logger)

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_session = AsyncMock()
            mock_client_class.return_value = mock_session

            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = {
                "signal_id": "sig-abc123",
                "status": "pending_approval",
                "server_timestamp": "2025-10-25T14:30:45.123456Z",
            }
            mock_session.post.return_value = mock_response

            await client._ensure_session()
            await client.post_signal(signal)

            # Verify POST was called
            mock_session.post.assert_called_once()

            # Get the call args
            call_args = mock_session.post.call_args
            headers = call_args.kwargs["headers"]

            # Verify headers contain required fields
            assert "X-Producer-Id" in headers
            assert "X-Timestamp" in headers
            assert "X-Signature" in headers
            assert "X-Idempotency-Key" in headers
            assert headers["X-Producer-Id"] == "test-producer"


class TestHmacClientSerialization:
    """Test signal serialization."""

    def test_serialize_signal_canonical_order(self, config, logger, signal) -> None:
        """Test that signal fields are serialized in canonical order."""
        client = HmacClient(config, logger)

        data = client._serialize_signal(signal)

        # Keys should be in alphabetical order
        keys = list(data.keys())
        assert keys == sorted(keys)

    def test_serialize_signal_includes_all_fields(self, config, logger, signal) -> None:
        """Test that all signal fields are included."""
        client = HmacClient(config, logger)

        data = client._serialize_signal(signal)

        required_fields = [
            "confidence",
            "entry_price",
            "instrument",
            "payload",
            "reason",
            "side",
            "stop_loss",
            "take_profit",
            "timestamp",
            "version",
        ]

        for field in required_fields:
            assert field in data

    def test_serialize_signal_converts_decimals_to_floats(
        self, config, logger, signal
    ) -> None:
        """Test that Decimal values are converted to floats."""
        client = HmacClient(config, logger)

        data = client._serialize_signal(signal)

        assert isinstance(data["entry_price"], float)
        assert isinstance(data["stop_loss"], float)
        assert isinstance(data["take_profit"], float)


class TestRFC3339Timestamp:
    """Test RFC3339 timestamp generation."""

    def test_get_rfc3339_timestamp_format(self) -> None:
        """Test RFC3339 timestamp has correct format."""
        timestamp = _get_rfc3339_timestamp()

        # Should contain T separator and Z timezone
        assert "T" in timestamp
        assert "Z" in timestamp

        # Should have microseconds
        assert "." in timestamp

    def test_get_rfc3339_timestamp_valid_format(self) -> None:
        """Test RFC3339 timestamp can be parsed."""
        timestamp = _get_rfc3339_timestamp()

        # Should be parseable as ISO format
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

        assert isinstance(parsed, datetime)


class TestHmacClientErrorMessages:
    """Test error message clarity."""

    def test_pydantic_validation_provides_clear_errors(self) -> None:
        """Test that Pydantic validation errors are clear for invalid signals."""
        from pydantic_core import ValidationError

        # Test that Pydantic gives clear error messages
        with pytest.raises(ValidationError) as exc_info:
            SignalCandidate(
                instrument="",  # Empty instrument
                side="buy",
                entry_price=1950.50,
                stop_loss=1945.00,
                take_profit=1960.00,
                confidence=0.85,
                reason="test",
                timestamp=datetime(2025, 10, 25, 14, 30, 45, 123456),
                payload={},
            )

        # Pydantic error should mention the validation issue
        error_str = str(exc_info.value)
        assert "String should have at least 2 characters" in error_str
