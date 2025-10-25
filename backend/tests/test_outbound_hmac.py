"""Unit tests for HMAC signature generation and verification."""

import pytest

from backend.app.trading.outbound.exceptions import OutboundSignatureError
from backend.app.trading.outbound.hmac import build_signature, verify_signature


class TestHmacSignatureGeneration:
    """Test HMAC-SHA256 signature generation."""

    def test_build_signature_happy_path(self) -> None:
        """Test correct signature generation with valid inputs."""
        signature = build_signature(
            secret=b"my-secret-key-min-16-bytes",
            body=b'{"instrument":"GOLD","side":"buy"}',
            timestamp="2025-10-25T14:30:45.123456Z",
            producer_id="mt5-trader-1",
        )

        # Signature should be non-empty base64 string
        assert isinstance(signature, str)
        assert len(signature) > 0
        # Base64 strings are alphanumeric + = + / +
        assert all(c.isalnum() or c in "=+/" for c in signature)

    def test_build_signature_deterministic(self) -> None:
        """Test that same inputs always produce same signature."""
        sig1 = build_signature(
            secret=b"my-secret-key-min-16-bytes",
            body=b'{"instrument":"GOLD","side":"buy"}',
            timestamp="2025-10-25T14:30:45.123456Z",
            producer_id="mt5-trader-1",
        )

        sig2 = build_signature(
            secret=b"my-secret-key-min-16-bytes",
            body=b'{"instrument":"GOLD","side":"buy"}',
            timestamp="2025-10-25T14:30:45.123456Z",
            producer_id="mt5-trader-1",
        )

        assert sig1 == sig2

    def test_build_signature_sensitive_to_body(self) -> None:
        """Test that different body produces different signature."""
        sig1 = build_signature(
            secret=b"my-secret-key-min-16-bytes",
            body=b'{"instrument":"GOLD","side":"buy"}',
            timestamp="2025-10-25T14:30:45.123456Z",
            producer_id="mt5-trader-1",
        )

        sig2 = build_signature(
            secret=b"my-secret-key-min-16-bytes",
            body=b'{"instrument":"GOLD","side":"sell"}',  # Different body
            timestamp="2025-10-25T14:30:45.123456Z",
            producer_id="mt5-trader-1",
        )

        assert sig1 != sig2

    def test_build_signature_sensitive_to_timestamp(self) -> None:
        """Test that different timestamp produces different signature."""
        sig1 = build_signature(
            secret=b"my-secret-key-min-16-bytes",
            body=b'{"instrument":"GOLD","side":"buy"}',
            timestamp="2025-10-25T14:30:45.123456Z",
            producer_id="mt5-trader-1",
        )

        sig2 = build_signature(
            secret=b"my-secret-key-min-16-bytes",
            body=b'{"instrument":"GOLD","side":"buy"}',
            timestamp="2025-10-25T14:30:46.123456Z",  # Different timestamp
            producer_id="mt5-trader-1",
        )

        assert sig1 != sig2

    def test_build_signature_sensitive_to_producer_id(self) -> None:
        """Test that different producer_id produces different signature."""
        sig1 = build_signature(
            secret=b"my-secret-key-min-16-bytes",
            body=b'{"instrument":"GOLD","side":"buy"}',
            timestamp="2025-10-25T14:30:45.123456Z",
            producer_id="mt5-trader-1",
        )

        sig2 = build_signature(
            secret=b"my-secret-key-min-16-bytes",
            body=b'{"instrument":"GOLD","side":"buy"}',
            timestamp="2025-10-25T14:30:45.123456Z",
            producer_id="mt5-trader-2",  # Different producer
        )

        assert sig1 != sig2


class TestHmacSignatureVerification:
    """Test HMAC-SHA256 signature verification."""

    def test_verify_signature_valid(self) -> None:
        """Test that valid signature passes verification."""
        secret = b"my-secret-key-min-16-bytes"
        body = b'{"instrument":"GOLD","side":"buy"}'
        timestamp = "2025-10-25T14:30:45.123456Z"
        producer_id = "mt5-trader-1"

        sig = build_signature(secret, body, timestamp, producer_id)

        assert verify_signature(secret, body, timestamp, producer_id, sig) is True

    def test_verify_signature_invalid_signature(self) -> None:
        """Test that invalid signature fails verification."""
        secret = b"my-secret-key-min-16-bytes"
        body = b'{"instrument":"GOLD","side":"buy"}'
        timestamp = "2025-10-25T14:30:45.123456Z"
        producer_id = "mt5-trader-1"

        assert (
            verify_signature(
                secret, body, timestamp, producer_id, "invalid_signature_base64=="
            )
            is False
        )

    def test_verify_signature_invalid_body(self) -> None:
        """Test that modified body fails verification."""
        secret = b"my-secret-key-min-16-bytes"
        body = b'{"instrument":"GOLD","side":"buy"}'
        timestamp = "2025-10-25T14:30:45.123456Z"
        producer_id = "mt5-trader-1"

        sig = build_signature(secret, body, timestamp, producer_id)

        # Different body should fail
        assert (
            verify_signature(
                secret,
                b'{"instrument":"GOLD","side":"sell"}',
                timestamp,
                producer_id,
                sig,
            )
            is False
        )

    def test_verify_signature_invalid_timestamp(self) -> None:
        """Test that modified timestamp fails verification."""
        secret = b"my-secret-key-min-16-bytes"
        body = b'{"instrument":"GOLD","side":"buy"}'
        timestamp = "2025-10-25T14:30:45.123456Z"
        producer_id = "mt5-trader-1"

        sig = build_signature(secret, body, timestamp, producer_id)

        # Different timestamp should fail
        assert (
            verify_signature(
                secret,
                body,
                "2025-10-25T14:30:46.123456Z",
                producer_id,
                sig,
            )
            is False
        )


class TestHmacSignatureErrorHandling:
    """Test error handling in HMAC signature generation."""

    def test_build_signature_empty_secret_raises(self) -> None:
        """Test that empty secret raises OutboundSignatureError."""
        with pytest.raises(OutboundSignatureError, match="secret must not be empty"):
            build_signature(
                secret=b"",
                body=b'{"test":"data"}',
                timestamp="2025-10-25T14:30:45.123456Z",
                producer_id="mt5-trader-1",
            )

    def test_build_signature_empty_body_raises(self) -> None:
        """Test that empty body raises OutboundSignatureError."""
        with pytest.raises(OutboundSignatureError, match="body must not be empty"):
            build_signature(
                secret=b"my-secret-key-min-16-bytes",
                body=b"",
                timestamp="2025-10-25T14:30:45.123456Z",
                producer_id="mt5-trader-1",
            )

    def test_build_signature_empty_timestamp_raises(self) -> None:
        """Test that empty timestamp raises OutboundSignatureError."""
        with pytest.raises(OutboundSignatureError, match="timestamp must not be empty"):
            build_signature(
                secret=b"my-secret-key-min-16-bytes",
                body=b'{"test":"data"}',
                timestamp="",
                producer_id="mt5-trader-1",
            )

    def test_build_signature_empty_producer_id_raises(self) -> None:
        """Test that empty producer_id raises OutboundSignatureError."""
        with pytest.raises(
            OutboundSignatureError, match="producer_id must not be empty"
        ):
            build_signature(
                secret=b"my-secret-key-min-16-bytes",
                body=b'{"test":"data"}',
                timestamp="2025-10-25T14:30:45.123456Z",
                producer_id="",
            )

    def test_build_signature_invalid_timestamp_format_raises(self) -> None:
        """Test that invalid timestamp format raises OutboundSignatureError."""
        with pytest.raises(
            OutboundSignatureError, match="timestamp must be RFC3339 format"
        ):
            build_signature(
                secret=b"my-secret-key-min-16-bytes",
                body=b'{"test":"data"}',
                timestamp="not-a-timestamp",
                producer_id="mt5-trader-1",
            )

    def test_build_signature_malformed_rfc3339_raises(self) -> None:
        """Test that malformed RFC3339 timestamp raises error."""
        with pytest.raises(
            OutboundSignatureError, match="timestamp must be RFC3339 format"
        ):
            build_signature(
                secret=b"my-secret-key-min-16-bytes",
                body=b'{"test":"data"}',
                timestamp="2025-10-25",  # Missing time part
                producer_id="mt5-trader-1",
            )

    def test_build_signature_large_body_handled(self) -> None:
        """Test that large body is handled correctly."""
        # Create a large body (1 MB)
        large_body = b"x" * (1024 * 1024)

        # Should not raise
        signature = build_signature(
            secret=b"my-secret-key-min-16-bytes",
            body=large_body,
            timestamp="2025-10-25T14:30:45.123456Z",
            producer_id="mt5-trader-1",
        )

        assert len(signature) > 0

    def test_verify_signature_invalid_timestamp_in_verification(self) -> None:
        """Test that verify_signature raises on invalid timestamp."""
        with pytest.raises(
            OutboundSignatureError, match="timestamp must be RFC3339 format"
        ):
            verify_signature(
                secret=b"my-secret-key-min-16-bytes",
                body=b'{"test":"data"}',
                timestamp="invalid-timestamp",
                producer_id="mt5-trader-1",
                provided_signature="sig123",
            )


class TestHmacSignatureEdgeCases:
    """Test edge cases in HMAC signature generation."""

    def test_build_signature_with_special_characters_in_producer_id(self) -> None:
        """Test signature generation with special characters in producer_id."""
        producer_id = "mt5-trader-1_test.prod-v2"
        sig = build_signature(
            secret=b"my-secret-key-min-16-bytes",
            body=b'{"test":"data"}',
            timestamp="2025-10-25T14:30:45.123456Z",
            producer_id=producer_id,
        )

        assert len(sig) > 0

    def test_build_signature_with_unicode_in_body(self) -> None:
        """Test signature generation with unicode characters in body."""
        # JSON with unicode (comment field)
        body = '{"comment":"Signal α-beta ✓","side":"buy"}'.encode()

        sig = build_signature(
            secret=b"my-secret-key-min-16-bytes",
            body=body,
            timestamp="2025-10-25T14:30:45.123456Z",
            producer_id="mt5-trader-1",
        )

        assert len(sig) > 0

    def test_build_signature_with_microseconds(self) -> None:
        """Test timestamp with microseconds."""
        timestamp = "2025-10-25T14:30:45.123456Z"
        sig1 = build_signature(
            secret=b"my-secret-key-min-16-bytes",
            body=b'{"test":"data"}',
            timestamp=timestamp,
            producer_id="mt5-trader-1",
        )

        # Without microseconds (different timestamp)
        timestamp2 = "2025-10-25T14:30:45Z"
        sig2 = build_signature(
            secret=b"my-secret-key-min-16-bytes",
            body=b'{"test":"data"}',
            timestamp=timestamp2,
            producer_id="mt5-trader-1",
        )

        assert sig1 != sig2

    def test_build_signature_with_timezone_offset(self) -> None:
        """Test timestamp with timezone offset instead of Z."""
        timestamp = "2025-10-25T14:30:45.123456+00:00"
        sig = build_signature(
            secret=b"my-secret-key-min-16-bytes",
            body=b'{"test":"data"}',
            timestamp=timestamp,
            producer_id="mt5-trader-1",
        )

        assert len(sig) > 0

    def test_build_signature_deterministic_across_calls(self) -> None:
        """Test that signature is deterministic across multiple calls."""
        signatures = []
        for _ in range(5):
            sig = build_signature(
                secret=b"my-secret-key-min-16-bytes",
                body=b'{"instrument":"GOLD","side":"buy"}',
                timestamp="2025-10-25T14:30:45.123456Z",
                producer_id="mt5-trader-1",
            )
            signatures.append(sig)

        # All signatures should be identical
        assert all(s == signatures[0] for s in signatures)
