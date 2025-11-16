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
from unittest.mock import AsyncMock, MagicMock

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
        # Use model_construct to bypass Pydantic validation
        signal = SignalCandidate.model_construct(
            instrument="",  # Empty - bypasses Pydantic
            side="buy",
            entry_price=1950.50,
            stop_loss=1940.0,
            take_profit=1965.0,
            confidence=0.85,
            timestamp=datetime.now(UTC),
            reason="test_empty_instrument",
            payload={},
        )
        with pytest.raises(OutboundClientError, match="non-empty instrument"):
            client._validate_signal(signal)

    @pytest.mark.asyncio
    async def test_validate_signal_whitespace_instrument(self, valid_config, logger):
        """Test validation rejects whitespace-only instrument."""
        from datetime import datetime

        client = HmacClient(valid_config, logger)
        # Use model_construct to bypass Pydantic validation
        signal = SignalCandidate.model_construct(
            instrument="   ",  # Whitespace - bypasses Pydantic
            side="buy",
            entry_price=1950.50,
            stop_loss=1940.0,
            take_profit=1965.0,
            confidence=0.85,
            timestamp=datetime.now(UTC),
            reason="test_whitespace",
            payload={},
        )
        with pytest.raises(OutboundClientError, match="non-empty instrument"):
            client._validate_signal(signal)

    @pytest.mark.asyncio
    async def test_validate_signal_invalid_side(self, valid_config, logger):
        """Test validation rejects invalid side."""
        from datetime import datetime

        client = HmacClient(valid_config, logger)
        # Use model_construct to bypass Pydantic validation
        signal = SignalCandidate.model_construct(
            instrument="GOLD",
            side="invalid",  # Invalid value bypasses Pydantic
            entry_price=1950.50,
            stop_loss=1940.0,
            take_profit=1965.0,
            confidence=0.85,
            timestamp=datetime.now(UTC),
            reason="test_invalid_side",
            payload={},
        )
        with pytest.raises(OutboundClientError, match="buy.*sell"):
            client._validate_signal(signal)

    @pytest.mark.asyncio
    async def test_validate_signal_zero_entry_price(self, valid_config, logger):
        """Test validation rejects zero entry price."""
        from datetime import datetime

        client = HmacClient(valid_config, logger)
        # Use model_construct to bypass Pydantic validation
        signal = SignalCandidate.model_construct(
            instrument="GOLD",
            side="buy",
            entry_price=0.0,  # Zero - bypasses Pydantic
            stop_loss=1940.0,
            take_profit=1965.0,
            confidence=0.85,
            timestamp=datetime.now(UTC),
            reason="test_zero_price",
            payload={},
        )
        with pytest.raises(OutboundClientError, match="entry_price must be > 0"):
            client._validate_signal(signal)

    @pytest.mark.asyncio
    async def test_validate_signal_negative_entry_price(self, valid_config, logger):
        """Test validation rejects negative entry price."""
        from datetime import datetime

        client = HmacClient(valid_config, logger)
        # Use model_construct to bypass Pydantic validation
        signal = SignalCandidate.model_construct(
            instrument="GOLD",
            side="buy",
            entry_price=-100.0,  # Negative - bypasses Pydantic
            stop_loss=1940.0,
            take_profit=1965.0,
            confidence=0.85,
            timestamp=datetime.now(UTC),
            reason="test_negative_price",
            payload={},
        )
        with pytest.raises(OutboundClientError, match="entry_price must be > 0"):
            client._validate_signal(signal)

    @pytest.mark.asyncio
    async def test_validate_signal_confidence_below_range(self, valid_config, logger):
        """Test validation rejects confidence < 0.0."""
        from datetime import datetime

        client = HmacClient(valid_config, logger)
        # Use model_construct to bypass Pydantic validation
        signal = SignalCandidate.model_construct(
            instrument="GOLD",
            side="buy",
            entry_price=1950.50,
            stop_loss=1940.0,
            take_profit=1965.0,
            confidence=-0.1,  # Below range - bypasses Pydantic
            timestamp=datetime.now(UTC),
            reason="test_confidence_below",
            payload={},
        )
        with pytest.raises(OutboundClientError, match="confidence must be between"):
            client._validate_signal(signal)

    @pytest.mark.asyncio
    async def test_validate_signal_confidence_above_range(self, valid_config, logger):
        """Test validation rejects confidence > 1.0."""
        from datetime import datetime

        client = HmacClient(valid_config, logger)
        # Use model_construct to bypass Pydantic validation
        signal = SignalCandidate.model_construct(
            instrument="GOLD",
            side="buy",
            entry_price=1950.50,
            stop_loss=1940.0,
            take_profit=1965.0,
            confidence=1.5,  # Above range - bypasses Pydantic
            timestamp=datetime.now(UTC),
            reason="test_confidence_above",
            payload={},
        )
        with pytest.raises(OutboundClientError, match="confidence must be between"):
            client._validate_signal(signal)

    @pytest.mark.asyncio
    async def test_validate_signal_accepts_boundary_confidence_zero(
        self, valid_config, logger
    ):
        """Test validation accepts confidence = 0.0."""
        from datetime import datetime

        client = HmacClient(valid_config, logger)
        signal = SignalCandidate(
            instrument="GOLD",
            side="buy",
            entry_price=1950.50,
            stop_loss=1940.0,
            take_profit=1965.0,
            confidence=0.0,  # Boundary
            timestamp=datetime.now(UTC),
            reason="test_boundary_zero",
            payload={},
        )

        # Should not raise
        client._validate_signal(signal)

    @pytest.mark.asyncio
    async def test_validate_signal_accepts_boundary_confidence_one(
        self, valid_config, logger
    ):
        """Test validation accepts confidence = 1.0."""
        from datetime import datetime

        client = HmacClient(valid_config, logger)
        signal = SignalCandidate(
            instrument="GOLD",
            side="buy",
            entry_price=1950.50,
            stop_loss=1940.0,
            take_profit=1965.0,
            confidence=1.0,  # Boundary
            timestamp=datetime.now(UTC),
            reason="test_boundary_one",
            payload={},
        )

        # Should not raise
        client._validate_signal(signal)


class TestBodySizeValidation:
    """Tests for body size validation errors."""

    @pytest.mark.asyncio
    async def test_post_signal_body_too_large(self, valid_config, valid_signal, logger):
        """Test post_signal rejects body exceeding max_body_size."""
        from datetime import datetime

        # Create config with small max_body_size (but >= 1024 minimum)
        # Signal body will be larger than this limit
        small_config = OutboundConfig(
            enabled=True,
            producer_id="test-producer",
            producer_secret="super-secret-key-1234567890",
            server_base_url="https://api.example.com",
            timeout_seconds=30.0,
            max_body_size=1024,  # Minimum allowed, but signal will exceed it
        )

        client = HmacClient(small_config, logger)

        # Signal with large payload to exceed 1024 bytes (need ~400+ chars to exceed)
        large_signal = SignalCandidate(
            instrument="GOLD",
            side="buy",
            entry_price=1950.50,
            stop_loss=1940.0,
            take_profit=1965.0,
            confidence=0.85,
            timestamp=datetime.now(UTC),
            reason="test",
            payload={"x": "y" * 1000},  # Large payload - ~1000 chars
        )

        # Pre-initialize session with mock to bypass network operations
        client._session = MagicMock()

        with pytest.raises(OutboundClientError, match="too large"):
            await client.post_signal(large_signal)

    @pytest.mark.asyncio
    async def test_post_signal_body_near_max_size(
        self, valid_config, valid_signal, logger
    ):
        """Test post_signal accepts body near max_body_size."""
        from datetime import datetime

        client = HmacClient(valid_config, logger)

        # Mock the session to bypass network call
        mock_response = AsyncMock()
        mock_response.status_code = 201
        mock_response.json = MagicMock(
            return_value={
                "signal_id": "sig-123",
                "status": "received",
                "server_timestamp": datetime.utcnow().isoformat(),
            }
        )

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        client._session = mock_session

        result = await client.post_signal(valid_signal)
        assert result.status == "received"


class TestHttpErrorHandling:
    """Tests for HTTP error responses."""

    @pytest.mark.asyncio
    async def test_post_signal_handles_400_error(
        self, valid_config, valid_signal, logger
    ):
        """Test post_signal handles HTTP 400 (Bad Request)."""
        client = HmacClient(valid_config, logger)

        mock_response = AsyncMock()
        mock_response.status_code = 400
        mock_response.text = "Invalid signal format"

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        client._session = mock_session

        with pytest.raises(OutboundClientError, match="400"):
            await client.post_signal(valid_signal)

    @pytest.mark.asyncio
    async def test_post_signal_handles_401_error(
        self, valid_config, valid_signal, logger
    ):
        """Test post_signal handles HTTP 401 (Unauthorized)."""
        client = HmacClient(valid_config, logger)

        mock_response = AsyncMock()
        mock_response.status_code = 401
        mock_response.text = "Invalid signature"

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        client._session = mock_session

        with pytest.raises(OutboundClientError, match="401"):
            await client.post_signal(valid_signal)

    @pytest.mark.asyncio
    async def test_post_signal_handles_403_error(
        self, valid_config, valid_signal, logger
    ):
        """Test post_signal handles HTTP 403 (Forbidden)."""
        client = HmacClient(valid_config, logger)

        mock_response = AsyncMock()
        mock_response.status_code = 403
        mock_response.text = "Producer not allowed"

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        client._session = mock_session

        with pytest.raises(OutboundClientError, match="403"):
            await client.post_signal(valid_signal)

    @pytest.mark.asyncio
    async def test_post_signal_handles_404_error(
        self, valid_config, valid_signal, logger
    ):
        """Test post_signal handles HTTP 404 (Not Found)."""
        client = HmacClient(valid_config, logger)

        mock_response = AsyncMock()
        mock_response.status_code = 404
        mock_response.text = "Endpoint not found"

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        client._session = mock_session

        with pytest.raises(OutboundClientError, match="404"):
            await client.post_signal(valid_signal)

    @pytest.mark.asyncio
    async def test_post_signal_handles_500_error(
        self, valid_config, valid_signal, logger
    ):
        """Test post_signal handles HTTP 500 (Internal Server Error)."""
        client = HmacClient(valid_config, logger)

        mock_response = AsyncMock()
        mock_response.status_code = 500
        mock_response.text = "Internal server error"

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        client._session = mock_session

        with pytest.raises(OutboundClientError, match="500"):
            await client.post_signal(valid_signal)

    @pytest.mark.asyncio
    async def test_post_signal_handles_502_error(
        self, valid_config, valid_signal, logger
    ):
        """Test post_signal handles HTTP 502 (Bad Gateway)."""
        client = HmacClient(valid_config, logger)

        mock_response = AsyncMock()
        mock_response.status_code = 502
        mock_response.text = "Bad gateway"

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        client._session = mock_session

        with pytest.raises(OutboundClientError, match="502"):
            await client.post_signal(valid_signal)

    @pytest.mark.asyncio
    async def test_post_signal_handles_503_error(
        self, valid_config, valid_signal, logger
    ):
        """Test post_signal handles HTTP 503 (Service Unavailable)."""
        client = HmacClient(valid_config, logger)

        mock_response = AsyncMock()
        mock_response.status_code = 503
        mock_response.text = "Service unavailable"

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        client._session = mock_session

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

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(
            side_effect=httpx.TimeoutException("Request timeout")
        )
        client._session = mock_session

        # Timeout errors raise TimeoutError, not OutboundClientError
        with pytest.raises(TimeoutError, match="timeout"):
            await client.post_signal(valid_signal)

    @pytest.mark.asyncio
    async def test_post_signal_handles_connection_error(
        self, valid_config, valid_signal, logger
    ):
        """Test post_signal handles httpx.ConnectError."""
        client = HmacClient(valid_config, logger)

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(
            side_effect=httpx.ConnectError("Connection failed")
        )
        client._session = mock_session

        with pytest.raises(OutboundClientError, match="Network error"):
            await client.post_signal(valid_signal)

    @pytest.mark.asyncio
    async def test_post_signal_handles_read_error(
        self, valid_config, valid_signal, logger
    ):
        """Test post_signal handles httpx.ReadError."""
        client = HmacClient(valid_config, logger)

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(
            side_effect=httpx.ReadError("Failed to read response")
        )
        client._session = mock_session

        with pytest.raises(OutboundClientError, match="Network error"):
            await client.post_signal(valid_signal)

    @pytest.mark.asyncio
    async def test_post_signal_handles_write_error(
        self, valid_config, valid_signal, logger
    ):
        """Test post_signal handles httpx.WriteError."""
        client = HmacClient(valid_config, logger)

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(
            side_effect=httpx.WriteError("Failed to write request")
        )
        client._session = mock_session

        with pytest.raises(OutboundClientError, match="Network error"):
            await client.post_signal(valid_signal)

    @pytest.mark.asyncio
    async def test_post_signal_handles_generic_http_error(
        self, valid_config, valid_signal, logger
    ):
        """Test post_signal handles generic httpx.HTTPError."""
        client = HmacClient(valid_config, logger)

        # Use a subclass of RequestError that httpx uses for general errors
        mock_session = AsyncMock()
        mock_session.post = AsyncMock(
            side_effect=httpx.RequestError("Generic HTTP error")
        )
        client._session = mock_session

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

        mock_response = AsyncMock()
        mock_response.status_code = 201
        mock_response.json.side_effect = json.JSONDecodeError("Expecting value", "", 0)

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        client._session = mock_session

        with pytest.raises(OutboundClientError, match="Unexpected error"):
            await client.post_signal(valid_signal)

    @pytest.mark.asyncio
    async def test_post_signal_handles_generic_exception(
        self, valid_config, valid_signal, logger
    ):
        """Test post_signal handles unexpected exceptions."""
        client = HmacClient(valid_config, logger)

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(side_effect=RuntimeError("Unexpected error"))
        client._session = mock_session

        with pytest.raises(OutboundClientError, match="Unexpected error"):
            await client.post_signal(valid_signal)

    @pytest.mark.asyncio
    async def test_post_signal_preserves_outbound_client_error(
        self, valid_config, valid_signal, logger
    ):
        """Test post_signal re-raises OutboundClientError without wrapping."""
        client = HmacClient(valid_config, logger)

        original_error = OutboundClientError("Original error")

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(side_effect=original_error)
        client._session = mock_session

        with pytest.raises(OutboundClientError, match="Original error"):
            await client.post_signal(valid_signal)


class TestHeaderGeneration:
    """Tests for proper HMAC header generation in requests."""

    @pytest.mark.asyncio
    async def test_post_signal_includes_required_headers(
        self, valid_config, valid_signal, logger
    ):
        """Test post_signal includes all required headers."""
        from datetime import datetime

        client = HmacClient(valid_config, logger)

        mock_response = AsyncMock()
        mock_response.status_code = 201
        mock_response.json = MagicMock(
            return_value={
                "signal_id": "sig-123",
                "status": "received",
                "server_timestamp": datetime.utcnow().isoformat(),
            }
        )

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        client._session = mock_session

        await client.post_signal(valid_signal)

        # Verify post was called with headers
        assert mock_session.post.called
        call_kwargs = mock_session.post.call_args[1]
        assert "headers" in call_kwargs
        headers = call_kwargs["headers"]
        assert "X-Producer-Id" in headers
        assert "X-Timestamp" in headers
        assert "X-Signature" in headers
        assert "X-Idempotency-Key" in headers
        assert "Content-Type" in headers

    @pytest.mark.asyncio
    async def test_post_signal_signature_is_deterministic(
        self, valid_config, valid_signal, logger
    ):
        """Test signature is same for identical signal."""
        from backend.app.trading.outbound.hmac import build_signature

        client = HmacClient(valid_config, logger)

        # Get signature twice for same signal
        body_dict_1 = client._serialize_signal(valid_signal)
        body_bytes_1 = json.dumps(body_dict_1, separators=(",", ":")).encode()
        timestamp = "2025-01-01T12:00:00Z"
        sig_1 = build_signature(
            secret=valid_config.producer_secret.encode(),
            body=body_bytes_1,
            timestamp=timestamp,
            producer_id=valid_config.producer_id,
        )

        body_dict_2 = client._serialize_signal(valid_signal)
        body_bytes_2 = json.dumps(body_dict_2, separators=(",", ":")).encode()
        sig_2 = build_signature(
            secret=valid_config.producer_secret.encode(),
            body=body_bytes_2,
            timestamp=timestamp,
            producer_id=valid_config.producer_id,
        )

        # Same inputs should produce same signature
        assert sig_1 == sig_2

        assert sig_1 == sig_2
