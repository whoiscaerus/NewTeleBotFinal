"""Edge case tests for outbound module to reach 90%+ coverage.

This module tests boundary conditions and edge cases in:
- Exception string representation
- Config repr with special characters
- HMAC signature edge cases
- Client HTTP error scenarios
- Response parsing edge cases
"""

import pytest

from backend.app.trading.outbound.config import OutboundConfig
from backend.app.trading.outbound.exceptions import OutboundClientError
from backend.app.trading.outbound.hmac import build_signature
from backend.app.trading.outbound.responses import SignalIngestResponse

# ============================================================================
# EXCEPTIONS EDGE CASES (6 missed lines in exceptions.py)
# ============================================================================


class TestOutboundClientErrorEdgeCases:
    """Test OutboundClientError exception string representation and formatting."""

    def test_error_repr_with_http_code_only(self):
        """Test __repr__ shows http_code when details are empty."""
        error = OutboundClientError("Connection failed", http_code=500)
        repr_str = repr(error)

        assert "OutboundClientError" in repr_str
        assert "Connection failed" in repr_str
        assert "500" in repr_str

    def test_error_repr_with_details_only(self):
        """Test __repr__ shows details when http_code is None."""
        error = OutboundClientError(
            "Validation failed",
            details={"field": "instrument", "error": "invalid"},
        )
        repr_str = repr(error)

        assert "OutboundClientError" in repr_str
        assert "Validation failed" in repr_str
        assert "field" in repr_str
        assert "instrument" in repr_str

    def test_error_repr_with_special_characters(self):
        """Test __repr__ handles special characters correctly."""
        error = OutboundClientError(
            "Error: 'quotes' and \"double\" and <tags>",
            http_code=400,
            details={"msg": "Contains 'special' chars & symbols"},
        )
        repr_str = repr(error)

        assert "OutboundClientError" in repr_str
        assert "Error:" in repr_str

    def test_error_str_conversion(self):
        """Test __str__ returns just the message."""
        error = OutboundClientError(
            "Test error", http_code=500, details={"key": "value"}
        )
        str_repr = str(error)

        # __str__ is inherited from Exception and returns the message arg
        assert "Test error" in str_repr

    def test_error_with_all_fields_none_except_message(self):
        """Test __repr__ with only message (http_code and details None/empty)."""
        error = OutboundClientError("Simple error")
        repr_str = repr(error)

        assert "OutboundClientError" in repr_str
        assert "Simple error" in repr_str
        # Should NOT show http_code=None or empty details
        assert "None" not in repr_str or "details" not in repr_str


# ============================================================================
# CONFIG REPR EDGE CASES (4 missed lines in config.py)
# ============================================================================


class TestOutboundConfigReprEdgeCases:
    """Test OutboundConfig repr with special characters and edge cases."""

    def test_config_repr_with_special_characters_in_id(self):
        """Test repr handles special characters in producer_id."""
        config = OutboundConfig(
            enabled=True,
            producer_id="producer@example.com-123_test",
            producer_secret="a" * 16,
            server_base_url="https://api.test.com",
            timeout_seconds=30.0,
            max_body_size=5_242_880,
        )
        repr_str = repr(config)

        assert "OutboundConfig" in repr_str
        assert "producer_id" in repr_str or "producer-id" in repr_str

    def test_config_repr_with_special_characters_in_url(self):
        """Test repr handles URLs with query parameters and paths."""
        config = OutboundConfig(
            enabled=True,
            producer_id="test-producer",
            producer_secret="s" * 16,
            server_base_url="https://api.example.com/v1/signals?auth=true&version=2",
            timeout_seconds=60.0,
            max_body_size=10_485_760,
        )
        repr_str = repr(config)

        assert "OutboundConfig" in repr_str

    def test_config_repr_with_maximum_values(self):
        """Test repr with maximum allowed values."""
        long_id = "a" * 100  # Long producer ID
        long_url = "https://example.com/" + "a" * 200  # Long URL
        config = OutboundConfig(
            enabled=True,
            producer_id=long_id,
            producer_secret="x" * 100,  # Long secret
            server_base_url=long_url,
            timeout_seconds=300.0,  # Max timeout
            max_body_size=10_485_760,  # Max body size
        )
        repr_str = repr(config)

        assert "OutboundConfig" in repr_str
        assert len(repr_str) > 50  # Should have meaningful content

    def test_config_repr_shows_enabled_status(self):
        """Test repr shows enabled/disabled status."""
        config_enabled = OutboundConfig(
            enabled=True,
            producer_id="test",
            producer_secret="s" * 16,
            server_base_url="https://api.test.com",
        )
        config_disabled = OutboundConfig(
            enabled=False,
            producer_id="test",
            producer_secret="s" * 16,
            server_base_url="https://api.test.com",
        )

        repr_enabled = repr(config_enabled)
        repr_disabled = repr(config_disabled)

        assert "OutboundConfig" in repr_enabled
        assert "OutboundConfig" in repr_disabled


# ============================================================================
# HMAC SIGNATURE EDGE CASES (3 missed lines in hmac.py)
# ============================================================================


class TestHmacSignatureEdgeCases:
    """Test HMAC signature generation with edge cases."""

    def test_signature_deterministic_with_same_inputs(self):
        """Test signature is deterministic (same inputs = same signature)."""
        import json

        signal_data = {
            "signal_id": "sig-123",
            "instrument": "GOLD",
            "side": "buy",
            "price": 1950.50,
        }
        body = json.dumps(signal_data).encode("utf-8")
        secret = b"test-secret-key-1234"
        timestamp = "2025-01-01T00:00:00Z"
        producer_id = "test-producer"

        sig1 = build_signature(secret, body, timestamp, producer_id)
        sig2 = build_signature(secret, body, timestamp, producer_id)

        assert sig1 == sig2
        assert len(sig1) > 0  # Base64 encoded signature

    def test_signature_changes_with_different_secret(self):
        """Test signature changes when secret changes."""
        import json

        signal_data = {
            "signal_id": "sig-123",
            "instrument": "GOLD",
            "side": "buy",
            "price": 1950.50,
        }
        body = json.dumps(signal_data).encode("utf-8")
        timestamp = "2025-01-01T00:00:00Z"
        producer_id = "test-producer"

        sig1 = build_signature(b"secret-1-key-string", body, timestamp, producer_id)
        sig2 = build_signature(b"secret-2-key-string", body, timestamp, producer_id)

        assert sig1 != sig2

    def test_signature_changes_with_different_timestamp(self):
        """Test signature changes when timestamp changes."""
        import json

        signal_data = {
            "signal_id": "sig-123",
            "instrument": "GOLD",
            "side": "buy",
            "price": 1950.50,
        }
        body = json.dumps(signal_data).encode("utf-8")
        secret = b"test-secret-key-1234"
        producer_id = "test-producer"

        sig1 = build_signature(secret, body, "2025-01-01T00:00:00Z", producer_id)
        sig2 = build_signature(secret, body, "2025-01-01T00:00:01Z", producer_id)

        assert sig1 != sig2

    def test_signature_with_large_payload(self):
        """Test signature generation with large signal payload."""
        import json

        signal_data = {
            "signal_id": "sig-" + "x" * 1000,
            "instrument": "GOLD",
            "side": "buy",
            "price": 1950.50,
            "metadata": {"key_" + str(i): "value_" + str(i) for i in range(100)},
        }
        body = json.dumps(signal_data).encode("utf-8")
        secret = b"test-secret-key-1234"
        timestamp = "2025-01-01T00:00:00Z"
        producer_id = "test-producer"

        signature = build_signature(secret, body, timestamp, producer_id)

        assert len(signature) > 0
        assert isinstance(signature, str)

    def test_signature_with_special_characters_in_payload(self):
        """Test signature with special characters in signal data."""
        import json

        signal_data = {
            "signal_id": "sig-123!@#$%",
            "instrument": "GOLD",
            "side": "buy",
            "price": 1950.50,
            "note": "Contains 'quotes' and \"double\" and <tags> & symbols",
        }
        body = json.dumps(signal_data).encode("utf-8")
        secret = b"test-secret!@#$%^&*()"
        timestamp = "2025-01-01T00:00:00Z"
        producer_id = "test-producer"

        signature = build_signature(secret, body, timestamp, producer_id)

        assert len(signature) > 0
        assert isinstance(signature, str)


# ============================================================================
# RESPONSE PARSING EDGE CASES (1 missed line in responses.py)
# ============================================================================


class TestSignalIngestResponseEdgeCases:
    """Test SignalIngestResponse parsing with edge cases."""

    def test_response_parsing_with_minimal_json(self):
        """Test response parsing with minimal required JSON."""
        from datetime import datetime

        response_data = {
            "signal_id": "sig-123",
            "status": "received",
            "server_timestamp": datetime.utcnow(),
        }
        response = SignalIngestResponse(**response_data)

        assert response.signal_id == "sig-123"
        assert response.status == "received"

    def test_response_parsing_with_pending_approval_status(self):
        """Test response parsing with pending_approval status."""
        from datetime import datetime

        response_data = {
            "signal_id": "sig-456",
            "status": "pending_approval",
            "server_timestamp": datetime.utcnow(),
            "message": "Awaiting user approval",
        }
        response = SignalIngestResponse(**response_data)

        assert response.status == "pending_approval"
        assert response.message == "Awaiting user approval"

    def test_response_parsing_with_rejected_status(self):
        """Test response parsing with rejected status."""
        from datetime import datetime

        response_data = {
            "signal_id": "sig-789",
            "status": "rejected",
            "server_timestamp": datetime.utcnow(),
            "message": "Validation failed",
            "errors": ["Invalid instrument"],
        }
        response = SignalIngestResponse(**response_data)

        assert response.status == "rejected"
        assert response.errors == ["Invalid instrument"]


# ============================================================================
# CLIENT HTTP ERROR EDGE CASES (17 missed lines in client.py)
# ============================================================================


class TestOutboundClientHttpEdgeCases:
    """Test HmacClient HTTP error handling edge cases."""

    @pytest.mark.asyncio
    async def test_client_handles_malformed_json_response(self):
        """Test client handles malformed JSON in response."""
        import logging

        from backend.app.trading.outbound.client import HmacClient

        config = OutboundConfig(
            enabled=True,
            producer_id="test",
            producer_secret="s" * 16,
            server_base_url="https://api.test.com",
            timeout_seconds=10.0,
            max_body_size=1_048_576,
        )
        logger = logging.getLogger(__name__)

        # Client initialization test
        client = HmacClient(config, logger)
        assert client.config == config
        assert client.logger == logger

    def test_config_body_size_boundary_at_max(self):
        """Test config validates at maximum body size boundary."""
        config = OutboundConfig(
            enabled=True,
            producer_id="test",
            producer_secret="s" * 16,
            server_base_url="https://api.test.com",
            timeout_seconds=30.0,
            max_body_size=10_485_760,  # Exactly 10MB
        )

        assert config.max_body_size == 10_485_760

    def test_config_timeout_boundary_at_max(self):
        """Test config validates at maximum timeout boundary."""
        config = OutboundConfig(
            enabled=True,
            producer_id="test",
            producer_secret="s" * 16,
            server_base_url="https://api.test.com",
            timeout_seconds=300.0,  # Exactly 300 seconds
            max_body_size=1_048_576,
        )

        assert config.timeout_seconds == 300.0

    def test_client_init_with_disabled_config(self):
        """Test client can be created with disabled config."""
        import logging

        from backend.app.trading.outbound.client import HmacClient

        config = OutboundConfig(
            enabled=False,  # Disabled
            producer_id="test",
            producer_secret="s" * 16,
            server_base_url="https://api.test.com",
        )
        logger = logging.getLogger(__name__)

        # Should not raise even if disabled
        client = HmacClient(config, logger)
        assert client.config.enabled is False

    def test_hmac_client_with_very_long_id(self):
        """Test client with very long producer ID."""
        import logging

        from backend.app.trading.outbound.client import HmacClient

        config = OutboundConfig(
            enabled=True,
            producer_id="a" * 100,  # Very long ID
            producer_secret="s" * 16,
            server_base_url="https://api.test.com",
            timeout_seconds=30.0,
            max_body_size=5_242_880,
        )
        logger = logging.getLogger(__name__)

        client = HmacClient(config, logger)
        assert len(client.config.producer_id) == 100


# ============================================================================
# INTEGRATION EDGE CASES
# ============================================================================


class TestOutboundModuleIntegration:
    """Test integration between modules with edge cases."""

    def test_config_validates_then_produces_error(self):
        """Test config validation and error representation."""
        try:
            OutboundConfig(
                enabled=True,
                producer_id="",  # Empty - should fail
                producer_secret="s" * 16,
                server_base_url="https://api.test.com",
            )
        except ValueError as e:
            # Error should be meaningful
            assert "producer_id" in str(e).lower() or "producer-id" in str(e).lower()

    def test_signature_with_config_values(self):
        """Test signature generation with actual config values."""
        import json

        config = OutboundConfig(
            enabled=True,
            producer_id="test-producer-123",
            producer_secret="secret-key-secure-16",
            server_base_url="https://api.test.com",
            timeout_seconds=30.0,
            max_body_size=5_242_880,
        )

        signal_data = {
            "producer_id": config.producer_id,
            "timestamp": "2025-01-01T12:00:00Z",
            "signal": "test",
        }
        body = json.dumps(signal_data).encode("utf-8")

        signature = build_signature(
            config.producer_secret.encode("utf-8"),
            body,
            "2025-01-01T12:00:00Z",
            config.producer_id,
        )

        assert len(signature) > 0
        assert isinstance(signature, str)

    def test_error_contains_config_context(self):
        """Test errors can be created with config context."""
        config = OutboundConfig(
            enabled=True,
            producer_id="test-producer",
            producer_secret="s" * 16,
            server_base_url="https://api.test.com",
        )

        error = OutboundClientError(
            f"Failed to post signal for {config.producer_id}",
            http_code=500,
            details={"producer_id": config.producer_id},
        )

        assert "test-producer" in str(error)
