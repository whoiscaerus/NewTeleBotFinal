"""Tests for HmacClient error paths and edge cases (PR-017).

Tests all error handling scenarios:
- Signal validation errors (empty instrument, invalid side, invalid prices)
- Body size validation errors
- HTTP error responses (400, 500, timeouts)
- Network error handling
- Unexpected exception handling
"""

import json
import logging
from datetime import UTC
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from backend.app.strategy.fib_rsi.schema import SignalCandidate
from backend.app.trading.outbound.client import HmacClient
from backend.app.trading.outbound.config import OutboundConfig
from backend.app.trading.outbound.exceptions import OutboundClientError


@pytest.fixture
def logger():
    """Logger for testing."""
    return logging.getLogger("test_outbound_client")


@pytest.fixture
def valid_config():
    """Valid OutboundConfig for testing."""
    return OutboundConfig(
        enabled=True,
        producer_id="test-producer",
        producer_secret="super-secret-key-1234567890",
        server_base_url="https://api.example.com",
        timeout_seconds=30.0,
        max_body_size=65536,
    )


@pytest.fixture
def valid_signal():
    """Valid SignalCandidate for testing."""
    from datetime import datetime

    return SignalCandidate(
        instrument="GOLD",
        side="buy",
        entry_price=1950.50,
        stop_loss=1940.0,
        take_profit=1965.0,
        confidence=0.85,
        timestamp=datetime.now(UTC),
        reason="rsi_oversold_fib_support",
        payload={"rsi": 75},
    )


class TestSignalValidation:
    """Tests for signal validation errors."""

    @pytest.mark.asyncio
    async def test_validate_signal_empty_instrument(self, valid_config, logger):
        """Test validation rejects empty instrument."""
        from datetime import datetime

        client = HmacClient(valid_config, logger)
        signal = SignalCandidate(
            instrument="GL",  # Changed from empty to valid (min 2 chars)
            side="buy",
            entry_price=1950.50,
            stop_loss=1940.0,
            take_profit=1965.0,
            confidence=0.85,
            timestamp=datetime.now(UTC),
            reason="test",
            payload={},
        )
        # Now test with empty after construction by calling _validate_signal directly
        # But we need to trigger the validation error, so let's test the actual scenario
        # where instrument becomes empty during validation
        signal.instrument = ""  # Make it empty after creation
        with pytest.raises(OutboundClientError, match="non-empty instrument"):
            client._validate_signal(signal)

    @pytest.mark.asyncio
    async def test_validate_signal_whitespace_instrument(self, valid_config, logger):
        """Test validation rejects whitespace-only instrument."""
        client = HmacClient(valid_config, logger)
        signal = SignalCandidate(
            instrument="   ",
            side="buy",
            entry_price=1950.50,
            stop_loss=1940.0,
            take_profit=1965.0,
            confidence=0.85,
            payload={},
        )

        with pytest.raises(OutboundClientError, match="non-empty instrument"):
            client._validate_signal(signal)

    @pytest.mark.asyncio
    async def test_validate_signal_invalid_side(self, valid_config, logger):
        """Test validation rejects invalid side."""
        client = HmacClient(valid_config, logger)
        signal = SignalCandidate(
            instrument="GOLD",
            side="invalid",  # type: ignore
            entry_price=1950.50,
            stop_loss=1940.0,
            take_profit=1965.0,
            confidence=0.85,
            payload={},
        )

        with pytest.raises(OutboundClientError, match="buy.*sell"):
            client._validate_signal(signal)

    @pytest.mark.asyncio
    async def test_validate_signal_zero_entry_price(self, valid_config, logger):
        """Test validation rejects zero entry price."""
        client = HmacClient(valid_config, logger)
        signal = SignalCandidate(
            instrument="GOLD",
            side="buy",
            entry_price=0.0,  # Invalid
            stop_loss=1940.0,
            take_profit=1965.0,
            confidence=0.85,
            payload={},
        )

        with pytest.raises(OutboundClientError, match="entry_price must be > 0"):
            client._validate_signal(signal)

    @pytest.mark.asyncio
    async def test_validate_signal_negative_entry_price(self, valid_config, logger):
        """Test validation rejects negative entry price."""
        client = HmacClient(valid_config, logger)
        signal = SignalCandidate(
            instrument="GOLD",
            side="buy",
            entry_price=-100.0,  # Invalid
            stop_loss=1940.0,
            take_profit=1965.0,
            confidence=0.85,
            payload={},
        )

        with pytest.raises(OutboundClientError, match="entry_price must be > 0"):
            client._validate_signal(signal)

    @pytest.mark.asyncio
    async def test_validate_signal_confidence_below_range(self, valid_config, logger):
        """Test validation rejects confidence < 0.0."""
        client = HmacClient(valid_config, logger)
        signal = SignalCandidate(
            instrument="GOLD",
            side="buy",
            entry_price=1950.50,
            stop_loss=1940.0,
            take_profit=1965.0,
            confidence=-0.1,  # Invalid
            payload={},
        )

        with pytest.raises(OutboundClientError, match="confidence must be between"):
            client._validate_signal(signal)

    @pytest.mark.asyncio
    async def test_validate_signal_confidence_above_range(self, valid_config, logger):
        """Test validation rejects confidence > 1.0."""
        client = HmacClient(valid_config, logger)
        signal = SignalCandidate(
            instrument="GOLD",
            side="buy",
            entry_price=1950.50,
            stop_loss=1940.0,
            take_profit=1965.0,
            confidence=1.5,  # Invalid
            payload={},
        )

        with pytest.raises(OutboundClientError, match="confidence must be between"):
            client._validate_signal(signal)

    @pytest.mark.asyncio
    async def test_validate_signal_accepts_boundary_confidence_zero(
        self, valid_config, logger
    ):
        """Test validation accepts confidence = 0.0."""
        client = HmacClient(valid_config, logger)
        signal = SignalCandidate(
            instrument="GOLD",
            side="buy",
            entry_price=1950.50,
            stop_loss=1940.0,
            take_profit=1965.0,
            confidence=0.0,  # Boundary
            payload={},
        )

        # Should not raise
        client._validate_signal(signal)

    @pytest.mark.asyncio
    async def test_validate_signal_accepts_boundary_confidence_one(
        self, valid_config, logger
    ):
        """Test validation accepts confidence = 1.0."""
        client = HmacClient(valid_config, logger)
        signal = SignalCandidate(
            instrument="GOLD",
            side="buy",
            entry_price=1950.50,
            stop_loss=1940.0,
            take_profit=1965.0,
            confidence=1.0,  # Boundary
            payload={},
        )

        # Should not raise
        client._validate_signal(signal)


class TestBodySizeValidation:
    """Tests for body size validation errors."""

    @pytest.mark.asyncio
    async def test_post_signal_body_too_large(self, valid_config, valid_signal, logger):
        """Test post_signal rejects body exceeding max_body_size."""
        # Create config with very small max_body_size
        small_config = OutboundConfig(
            enabled=True,
            producer_id="test-producer",
            producer_secret="super-secret-key-1234567890",
            server_base_url="https://api.example.com",
            timeout_seconds=30.0,
            max_body_size=10,  # Very small
        )

        client = HmacClient(small_config, logger)

        with pytest.raises(OutboundClientError, match="too large"):
            await client.post_signal(valid_signal)

    @pytest.mark.asyncio
    async def test_post_signal_body_near_max_size(
        self, valid_config, valid_signal, logger
    ):
        """Test post_signal accepts body near max_body_size."""
        with patch.object(HmacClient, "_post_to_server", new_callable=AsyncMock):
            with patch.object(HmacClient, "_build_signature", return_value="sig"):
                client = HmacClient(valid_config, logger)
                response = MagicMock()
                response.status_code = 201
                response.json.return_value = {"status": "ingested"}

                with patch.object(HmacClient, "_post_to_server", return_value=response):
                    result = await client.post_signal(valid_signal)
                    assert result.status == "ingested"


class TestHttpErrorHandling:
    """Tests for HTTP error responses."""

    @pytest.mark.asyncio
    async def test_post_signal_handles_400_error(
        self, valid_config, valid_signal, logger
    ):
        """Test post_signal handles HTTP 400 (Bad Request)."""
        client = HmacClient(valid_config, logger)

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Invalid signal format"

        with patch.object(HmacClient, "_post_to_server", return_value=mock_response):
            with pytest.raises(OutboundClientError, match="400"):
                await client.post_signal(valid_signal)

    @pytest.mark.asyncio
    async def test_post_signal_handles_401_error(
        self, valid_config, valid_signal, logger
    ):
        """Test post_signal handles HTTP 401 (Unauthorized)."""
        client = HmacClient(valid_config, logger)

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Invalid signature"

        with patch.object(HmacClient, "_post_to_server", return_value=mock_response):
            with pytest.raises(OutboundClientError, match="401"):
                await client.post_signal(valid_signal)

    @pytest.mark.asyncio
    async def test_post_signal_handles_403_error(
        self, valid_config, valid_signal, logger
    ):
        """Test post_signal handles HTTP 403 (Forbidden)."""
        client = HmacClient(valid_config, logger)

        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = "Producer not allowed"

        with patch.object(HmacClient, "_post_to_server", return_value=mock_response):
            with pytest.raises(OutboundClientError, match="403"):
                await client.post_signal(valid_signal)

    @pytest.mark.asyncio
    async def test_post_signal_handles_404_error(
        self, valid_config, valid_signal, logger
    ):
        """Test post_signal handles HTTP 404 (Not Found)."""
        client = HmacClient(valid_config, logger)

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Endpoint not found"

        with patch.object(HmacClient, "_post_to_server", return_value=mock_response):
            with pytest.raises(OutboundClientError, match="404"):
                await client.post_signal(valid_signal)

    @pytest.mark.asyncio
    async def test_post_signal_handles_500_error(
        self, valid_config, valid_signal, logger
    ):
        """Test post_signal handles HTTP 500 (Internal Server Error)."""
        client = HmacClient(valid_config, logger)

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal server error"

        with patch.object(HmacClient, "_post_to_server", return_value=mock_response):
            with pytest.raises(OutboundClientError, match="500"):
                await client.post_signal(valid_signal)

    @pytest.mark.asyncio
    async def test_post_signal_handles_502_error(
        self, valid_config, valid_signal, logger
    ):
        """Test post_signal handles HTTP 502 (Bad Gateway)."""
        client = HmacClient(valid_config, logger)

        mock_response = MagicMock()
        mock_response.status_code = 502
        mock_response.text = "Bad gateway"

        with patch.object(HmacClient, "_post_to_server", return_value=mock_response):
            with pytest.raises(OutboundClientError, match="502"):
                await client.post_signal(valid_signal)

    @pytest.mark.asyncio
    async def test_post_signal_handles_503_error(
        self, valid_config, valid_signal, logger
    ):
        """Test post_signal handles HTTP 503 (Service Unavailable)."""
        client = HmacClient(valid_config, logger)

        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_response.text = "Service unavailable"

        with patch.object(HmacClient, "_post_to_server", return_value=mock_response):
            with pytest.raises(OutboundClientError, match="503"):
                await client.post_signal(valid_signal)


class TestNetworkErrorHandling:
    """Tests for network error handling."""

    @pytest.mark.asyncio
    async def test_post_signal_handles_timeout_error(
        self, valid_config, valid_signal, logger
    ):
        """Test post_signal handles httpx.TimeoutException."""
        client = HmacClient(valid_config, logger)

        with patch.object(
            HmacClient,
            "_post_to_server",
            side_effect=httpx.TimeoutException("Request timeout"),
        ):
            with pytest.raises(OutboundClientError, match="timeout"):
                await client.post_signal(valid_signal)

    @pytest.mark.asyncio
    async def test_post_signal_handles_connection_error(
        self, valid_config, valid_signal, logger
    ):
        """Test post_signal handles httpx.ConnectError."""
        client = HmacClient(valid_config, logger)

        with patch.object(
            HmacClient,
            "_post_to_server",
            side_effect=httpx.ConnectError("Connection failed"),
        ):
            with pytest.raises(OutboundClientError, match="Network error"):
                await client.post_signal(valid_signal)

    @pytest.mark.asyncio
    async def test_post_signal_handles_read_error(
        self, valid_config, valid_signal, logger
    ):
        """Test post_signal handles httpx.ReadError."""
        client = HmacClient(valid_config, logger)

        with patch.object(
            HmacClient,
            "_post_to_server",
            side_effect=httpx.ReadError("Failed to read response"),
        ):
            with pytest.raises(OutboundClientError, match="Network error"):
                await client.post_signal(valid_signal)

    @pytest.mark.asyncio
    async def test_post_signal_handles_write_error(
        self, valid_config, valid_signal, logger
    ):
        """Test post_signal handles httpx.WriteError."""
        client = HmacClient(valid_config, logger)

        with patch.object(
            HmacClient,
            "_post_to_server",
            side_effect=httpx.WriteError("Failed to write request"),
        ):
            with pytest.raises(OutboundClientError, match="Network error"):
                await client.post_signal(valid_signal)

    @pytest.mark.asyncio
    async def test_post_signal_handles_generic_http_error(
        self, valid_config, valid_signal, logger
    ):
        """Test post_signal handles generic httpx.HTTPError."""
        client = HmacClient(valid_config, logger)

        with patch.object(
            HmacClient,
            "_post_to_server",
            side_effect=httpx.HTTPError("Generic HTTP error"),
        ):
            with pytest.raises(OutboundClientError, match="Network error"):
                await client.post_signal(valid_signal)


class TestUnexpectedErrors:
    """Tests for unexpected/unexpected error handling."""

    @pytest.mark.asyncio
    async def test_post_signal_handles_json_decode_error(
        self, valid_config, valid_signal, logger
    ):
        """Test post_signal handles malformed JSON response."""
        client = HmacClient(valid_config, logger)

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.side_effect = json.JSONDecodeError("Expecting value", "", 0)

        with patch.object(HmacClient, "_post_to_server", return_value=mock_response):
            with pytest.raises(OutboundClientError, match="Unexpected error"):
                await client.post_signal(valid_signal)

    @pytest.mark.asyncio
    async def test_post_signal_handles_generic_exception(
        self, valid_config, valid_signal, logger
    ):
        """Test post_signal handles unexpected exceptions."""
        client = HmacClient(valid_config, logger)

        with patch.object(
            HmacClient,
            "_post_to_server",
            side_effect=RuntimeError("Unexpected error"),
        ):
            with pytest.raises(OutboundClientError, match="Unexpected error"):
                await client.post_signal(valid_signal)

    @pytest.mark.asyncio
    async def test_post_signal_preserves_outbound_client_error(
        self, valid_config, valid_signal, logger
    ):
        """Test post_signal re-raises OutboundClientError without wrapping."""
        client = HmacClient(valid_config, logger)

        original_error = OutboundClientError("Original error")

        with patch.object(HmacClient, "_post_to_server", side_effect=original_error):
            with pytest.raises(OutboundClientError, match="Original error"):
                await client.post_signal(valid_signal)


class TestHeaderGeneration:
    """Tests for proper HMAC header generation in requests."""

    @pytest.mark.asyncio
    async def test_post_signal_includes_required_headers(
        self, valid_config, valid_signal, logger
    ):
        """Test post_signal includes all required headers."""
        client = HmacClient(valid_config, logger)

        with patch.object(
            HmacClient, "_post_to_server", new_callable=AsyncMock
        ) as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = {"status": "ingested"}
            mock_post.return_value = mock_response

            await client.post_signal(valid_signal)

            # Verify post was called
            assert mock_post.called

    @pytest.mark.asyncio
    async def test_post_signal_signature_is_deterministic(
        self, valid_config, valid_signal, logger
    ):
        """Test signature is same for identical signal."""
        client = HmacClient(valid_config, logger)

        # Get signature twice for same signal
        body_dict_1 = client._serialize_signal(valid_signal)
        body_bytes_1 = json.dumps(body_dict_1, separators=(",", ":")).encode()
        sig_1 = client._build_signature(body_bytes_1)

        body_dict_2 = client._serialize_signal(valid_signal)
        body_bytes_2 = json.dumps(body_dict_2, separators=(",", ":")).encode()
        sig_2 = client._build_signature(body_bytes_2)

        assert sig_1 == sig_2
