"""Integration tests for outbound signal delivery with HMAC signing.

Tests verify that actual HMAC signatures are computed and sent in headers,
not just mocked or hardcoded. This is critical for server-side signature
verification and overall signal security.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from backend.app.strategy.fib_rsi.schema import SignalCandidate
from backend.app.trading.outbound.client import HmacClient
from backend.app.trading.outbound.config import OutboundConfig
from backend.app.trading.outbound.exceptions import OutboundClientError
from backend.app.trading.outbound.hmac import build_signature, verify_signature


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


class TestHmacSignatureIntegration:
    """Test that HMAC signatures are actually computed and sent."""

    @pytest.mark.asyncio
    async def test_post_signal_signature_is_real_not_mocked(
        self, config, logger, signal
    ) -> None:
        """Test actual HMAC signature is computed and sent in X-Signature header.

        This is a CRITICAL test: if it passes, the server can verify the signature.
        If it fails or is skipped, signals would not authenticate on server.

        The test:
        1. Calls client.post_signal()
        2. Captures the HTTP request that would be sent
        3. Extracts X-Signature header
        4. Re-computes expected signature using build_signature()
        5. Verifies they match - proving actual HMAC was computed
        """
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
            }
            mock_session.post.return_value = mock_response

            await client._ensure_session()
            response = await client.post_signal(signal)

            # Verify response was parsed correctly
            assert response.signal_id == "sig-abc123"
            assert response.status == "pending_approval"

            # Now verify the actual request was correct
            mock_session.post.assert_called_once()
            call_args = mock_session.post.call_args

            # Extract what was actually sent
            actual_headers = call_args.kwargs["headers"]
            actual_body = call_args.kwargs["content"]
            actual_timestamp = actual_headers["X-Timestamp"]
            actual_signature = actual_headers["X-Signature"]

            # Verify required headers present
            assert "X-Producer-Id" in actual_headers
            assert "X-Timestamp" in actual_headers
            assert "X-Signature" in actual_headers
            assert "X-Idempotency-Key" in actual_headers

            # ✅ CRITICAL: Verify signature is CORRECT by re-computing it
            # This proves actual HMAC-SHA256 was computed, not mocked
            expected_signature = build_signature(
                secret=config.producer_secret.encode("utf-8"),
                body=actual_body,
                timestamp=actual_timestamp,
                producer_id=config.producer_id,
            )

            # If this assertion fails, the signature is not being computed correctly
            assert (
                actual_signature == expected_signature
            ), "Signature mismatch - HMAC not computed correctly!"

    @pytest.mark.asyncio
    async def test_post_signal_signature_changes_with_body(
        self, config, logger
    ) -> None:
        """Test that signature changes when signal body changes.

        This verifies the signature actually depends on the request body,
        not just the timestamp or producer_id.
        """
        client = HmacClient(config, logger)

        signal1 = SignalCandidate(
            instrument="GOLD",
            side="buy",
            entry_price=1950.50,
            stop_loss=1945.00,
            take_profit=1960.00,
            confidence=0.85,
            reason="signal_1",
            timestamp=datetime(2025, 10, 25, 14, 30, 45, 0),
            payload={"rsi": 35},
        )

        signal2 = SignalCandidate(
            instrument="GOLD",
            side="sell",  # Different side
            entry_price=1950.50,
            stop_loss=1945.00,
            take_profit=1960.00,
            confidence=0.85,
            reason="signal_1",
            timestamp=datetime(2025, 10, 25, 14, 30, 45, 0),
            payload={"rsi": 35},
        )

        signatures = []

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_session = AsyncMock()
            mock_client_class.return_value = mock_session

            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = {
                "signal_id": "sig-test",
                "status": "pending_approval",
                "server_timestamp": "2025-10-25T14:30:45.123456Z",
            }
            mock_session.post.return_value = mock_response

            await client._ensure_session()

            # Post signal 1
            await client.post_signal(signal1)
            call1_args = mock_session.post.call_args_list[0]
            sig1 = call1_args.kwargs["headers"]["X-Signature"]
            signatures.append(sig1)

            # Post signal 2
            await client.post_signal(signal2)
            call2_args = mock_session.post.call_args_list[1]
            sig2 = call2_args.kwargs["headers"]["X-Signature"]
            signatures.append(sig2)

        # Signatures should be different (body changed)
        assert (
            signatures[0] != signatures[1]
        ), "Signatures should differ when signal body differs!"

    @pytest.mark.asyncio
    async def test_post_signal_signature_deterministic(
        self, config, logger, signal
    ) -> None:
        """Test that posting the same signal with same timestamp produces same signature.

        This verifies serialization is canonical and deterministic.
        Note: Since timestamp changes between POST calls, we verify body serialization
        is deterministic by checking the actual body bytes.
        """
        client = HmacClient(config, logger)

        bodies = []

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_session = AsyncMock()
            mock_client_class.return_value = mock_session

            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = {
                "signal_id": "sig-test",
                "status": "pending_approval",
                "server_timestamp": "2025-10-25T14:30:45.123456Z",
            }
            mock_session.post.return_value = mock_response

            await client._ensure_session()

            # Post same signal twice
            await client.post_signal(signal)
            call1_args = mock_session.post.call_args_list[0]
            body1 = call1_args.kwargs["content"]
            bodies.append(body1)

            await client.post_signal(signal)
            call2_args = mock_session.post.call_args_list[1]
            body2 = call2_args.kwargs["content"]
            bodies.append(body2)

        # Bodies should be identical (canonical serialization)
        assert bodies[0] == bodies[1], "Signal body serialization should be canonical!"


class TestNetworkErrorHandling:
    """Test graceful handling of network errors."""

    @pytest.mark.asyncio
    async def test_timeout_error_is_raised(self, config, logger, signal) -> None:
        """Test that network timeout is caught and raised as TimeoutError."""
        client = HmacClient(config, logger)

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_session = AsyncMock()
            mock_client_class.return_value = mock_session

            # Simulate timeout
            mock_session.post.side_effect = httpx.TimeoutException("Read timeout")

            await client._ensure_session()

            with pytest.raises(TimeoutError):
                await client.post_signal(signal)

    @pytest.mark.asyncio
    async def test_connection_refused_error_is_raised(
        self, config, logger, signal
    ) -> None:
        """Test that connection refused is caught and raised as OutboundClientError."""
        client = HmacClient(config, logger)

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_session = AsyncMock()
            mock_client_class.return_value = mock_session

            # Simulate connection refused
            mock_session.post.side_effect = ConnectionRefusedError("Connection refused")

            await client._ensure_session()

            with pytest.raises(OutboundClientError):
                await client.post_signal(signal)

    @pytest.mark.asyncio
    async def test_connection_error_is_raised(self, config, logger, signal) -> None:
        """Test that generic connection error is caught and raised."""
        client = HmacClient(config, logger)

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_session = AsyncMock()
            mock_client_class.return_value = mock_session

            # Simulate connection error
            mock_session.post.side_effect = OSError("Connection error")

            await client._ensure_session()

            with pytest.raises(OutboundClientError):
                await client.post_signal(signal)

    @pytest.mark.asyncio
    async def test_json_decode_error_is_raised(self, config, logger, signal) -> None:
        """Test that malformed JSON response is caught."""
        client = HmacClient(config, logger)

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_session = AsyncMock()
            mock_client_class.return_value = mock_session

            mock_response = MagicMock()
            mock_response.status_code = 200  # Success status
            mock_response.json.side_effect = ValueError("Invalid JSON")
            mock_session.post.return_value = mock_response

            await client._ensure_session()

            with pytest.raises(OutboundClientError):
                await client.post_signal(signal)


class TestSignatureServerVerification:
    """Test that computed signatures can be verified using standard crypto."""

    def test_client_signature_can_be_verified_by_server(
        self, config, logger, signal
    ) -> None:
        """Test that client-computed signature can be verified by server.

        This simulates server-side verification: server receives the signature
        in X-Signature header and body, and verifies it using the shared secret.
        """
        client = HmacClient(config, logger)

        # Client serializes and signs
        body_dict = client._serialize_signal(signal)
        import json

        body_bytes = json.dumps(
            body_dict, separators=(",", ":"), sort_keys=True
        ).encode()

        # Simulate getting timestamp from client headers
        from backend.app.trading.outbound.client import _get_rfc3339_timestamp

        timestamp = _get_rfc3339_timestamp()

        # Client computes signature
        client_signature = build_signature(
            secret=config.producer_secret.encode("utf-8"),
            body=body_bytes,
            timestamp=timestamp,
            producer_id=config.producer_id,
        )

        # Server verifies using shared secret
        is_valid = verify_signature(
            secret=config.producer_secret.encode("utf-8"),
            body=body_bytes,
            timestamp=timestamp,
            producer_id=config.producer_id,
            provided_signature=client_signature,
        )

        # ✅ Verification must succeed
        assert (
            is_valid is True
        ), "Server verification failed - signature algorithm mismatch!"


class TestSignalSerializationCanonical:
    """Test that signal serialization is canonical for signature consistency."""

    def test_signal_serializes_to_canonical_json(self, config, logger, signal) -> None:
        """Test that signal serializes consistently to canonical JSON.

        Canonical JSON has:
        1. Keys in alphabetical order
        2. No spaces after separators
        3. Consistent type coercion (e.g., Decimal → float)
        4. Same serialization every time
        """
        client = HmacClient(config, logger)

        # Serialize multiple times
        bodies = []
        for _ in range(3):
            body_dict = client._serialize_signal(signal)
            import json

            body_json = json.dumps(body_dict, separators=(",", ":"), sort_keys=True)
            bodies.append(body_json)

        # All three serializations should be identical
        assert bodies[0] == bodies[1] == bodies[2], "Serialization not canonical!"

    def test_serialization_field_order_is_alphabetical(
        self, config, logger, signal
    ) -> None:
        """Test that serialized fields are in alphabetical order."""
        client = HmacClient(config, logger)

        body_dict = client._serialize_signal(signal)

        keys = list(body_dict.keys())
        sorted_keys = sorted(keys)

        assert keys == sorted_keys, f"Keys not alphabetical: {keys} vs {sorted_keys}"

    def test_serialization_includes_all_required_fields(
        self, config, logger, signal
    ) -> None:
        """Test that all required fields are included in serialization."""
        client = HmacClient(config, logger)

        body_dict = client._serialize_signal(signal)

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
            assert (
                field in body_dict
            ), f"Required field '{field}' missing from serialization"
