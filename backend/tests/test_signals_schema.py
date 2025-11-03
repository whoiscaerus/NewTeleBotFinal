"""Comprehensive tests for signals schema validation.

Tests cover:
- SignalCreate validation (instrument, side, price, payload, version)
- SignalOut serialization
- Schema transformations (side conversion, status labels)
- Field constraints and boundaries
- Error messages
"""

import pytest
from datetime import datetime
from pydantic import ValidationError

from backend.app.signals.schema import SignalCreate, SignalOut
from backend.app.signals.models import SignalStatus


def _create_signal_out(**kwargs):
    """Helper to create SignalOut with default datetimes."""
    defaults = {
        "id": "sig_test",
        "instrument": "XAUUSD",
        "side": 0,
        "price": 1950.50,
        "status": 0,
        "payload": {},
        "version": "1.0",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    defaults.update(kwargs)
    return SignalOut(**defaults)


class TestSignalCreateValidation:
    """Test SignalCreate schema validation."""

    def test_signal_create_valid_all_fields(self):
        """Test valid signal creation with all fields."""
        signal = SignalCreate(
            instrument="XAUUSD",
            side="buy",
            price=1950.50,
            payload={"rsi": 75.5},
            version="1.0",
        )

        assert signal.instrument == "XAUUSD"
        assert signal.side == "buy"
        assert signal.price == 1950.50
        assert signal.payload == {"rsi": 75.5}
        assert signal.version == "1.0"

    def test_signal_create_valid_minimal_fields(self):
        """Test valid signal creation with minimal fields."""
        signal = SignalCreate(
            instrument="XAUUSD",
            side="sell",
            price=1.0850,
            version="1.0",
        )

        assert signal.instrument == "XAUUSD"
        assert signal.side == "sell"
        assert signal.price == 1.0850
        assert signal.payload == {}  # Default empty
        assert signal.version == "1.0"

    def test_signal_create_instrument_whitelist_valid(self):
        """Test all valid instruments are accepted."""
        valid_instruments = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY"]

        for instrument in valid_instruments:
            signal = SignalCreate(
                instrument=instrument,
                side="buy",
                price=1950.50,
                version="1.0",
            )
            assert signal.instrument == instrument

    def test_signal_create_instrument_invalid_rejected(self):
        """Test invalid instrument is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SignalCreate(
                instrument="INVALID_XYZ",
                side="buy",
                price=1950.50,
                version="1.0",
            )

        assert "instrument" in str(exc_info.value).lower()

    def test_signal_create_instrument_lowercase_rejected(self):
        """Test lowercase instrument is rejected (must be uppercase)."""
        with pytest.raises(ValidationError):
            SignalCreate(
                instrument="xauusd",
                side="buy",
                price=1950.50,
                version="1.0",
            )

    def test_signal_create_instrument_too_short_rejected(self):
        """Test instrument < 2 chars is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SignalCreate(
                instrument="X",
                side="buy",
                price=1950.50,
                version="1.0",
            )

        assert "instrument" in str(exc_info.value).lower()

    def test_signal_create_instrument_too_long_rejected(self):
        """Test instrument > 20 chars is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SignalCreate(
                instrument="X" * 21,
                side="buy",
                price=1950.50,
                version="1.0",
            )

        assert "instrument" in str(exc_info.value).lower()

    def test_signal_create_side_buy_valid(self):
        """Test 'buy' side is valid."""
        signal = SignalCreate(
            instrument="XAUUSD",
            side="buy",
            price=1950.50,
            version="1.0",
        )

        assert signal.side == "buy"

    def test_signal_create_side_sell_valid(self):
        """Test 'sell' side is valid."""
        signal = SignalCreate(
            instrument="XAUUSD",
            side="sell",
            price=1950.50,
            version="1.0",
        )

        assert signal.side == "sell"

    def test_signal_create_side_invalid_rejected(self):
        """Test invalid side is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SignalCreate(
                instrument="XAUUSD",
                side="INVALID",
                price=1950.50,
                version="1.0",
            )

        assert "side" in str(exc_info.value).lower()

    def test_signal_create_side_case_sensitive(self):
        """Test side is case-sensitive."""
        with pytest.raises(ValidationError):
            SignalCreate(
                instrument="XAUUSD",
                side="BUY",  # Must be lowercase
                price=1950.50,
                version="1.0",
            )

    def test_signal_create_price_positive(self):
        """Test price must be positive."""
        signal = SignalCreate(
            instrument="XAUUSD",
            side="buy",
            price=0.01,
            version="1.0",
        )

        assert signal.price == 0.01

    def test_signal_create_price_zero_rejected(self):
        """Test zero price is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SignalCreate(
                instrument="XAUUSD",
                side="buy",
                price=0.0,
                version="1.0",
            )

        assert "price" in str(exc_info.value).lower()

    def test_signal_create_price_negative_rejected(self):
        """Test negative price is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SignalCreate(
                instrument="XAUUSD",
                side="buy",
                price=-100.0,
                version="1.0",
            )

        assert "price" in str(exc_info.value).lower()

    def test_signal_create_price_maximum_valid(self):
        """Test maximum valid price."""
        signal = SignalCreate(
            instrument="XAUUSD",
            side="buy",
            price=999999.99,
            version="1.0",
        )

        assert signal.price == 999999.99

    def test_signal_create_price_exceeds_maximum_rejected(self):
        """Test price exceeding maximum is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SignalCreate(
                instrument="XAUUSD",
                side="buy",
                price=1_000_000.0,
                version="1.0",
            )

        assert "price" in str(exc_info.value).lower()

    def test_signal_create_price_precision(self):
        """Test price with high precision."""
        signal = SignalCreate(
            instrument="XAUUSD",
            side="buy",
            price=1950.123456,
            version="1.0",
        )

        assert signal.price == 1950.123456

    def test_signal_create_payload_empty_dict(self):
        """Test empty payload is valid."""
        signal = SignalCreate(
            instrument="XAUUSD",
            side="buy",
            price=1950.50,
            payload={},
            version="1.0",
        )

        assert signal.payload == {}

    def test_signal_create_payload_complex_nested(self):
        """Test complex nested payload."""
        payload = {
            "indicators": {
                "rsi": 75.5,
                "macd": -0.002,
                "bollinger": {"upper": 100, "lower": 50},
            },
            "confidence": 0.85,
            "signals": ["strong_buy", "sell"],
        }

        signal = SignalCreate(
            instrument="XAUUSD",
            side="buy",
            price=1950.50,
            payload=payload,
            version="1.0",
        )

        assert signal.payload == payload
        assert signal.payload["indicators"]["bollinger"]["upper"] == 100

    def test_signal_create_payload_with_unicode(self):
        """Test payload with unicode characters."""
        payload = {
            "note": "Trade signal for 日本 market 🚀",
            "symbol": "€ 💱",
        }

        signal = SignalCreate(
            instrument="XAUUSD",
            side="buy",
            price=1950.50,
            payload=payload,
            version="1.0",
        )

        assert "日本" in signal.payload["note"]
        assert "💱" in signal.payload["symbol"]

    def test_signal_create_payload_size_limit(self):
        """Test payload size limit (max 1024 bytes)."""
        # Create payload that's less than 1024 bytes
        payload = {"data": "x" * 800}

        signal = SignalCreate(
            instrument="XAUUSD",
            side="buy",
            price=1950.50,
            payload=payload,
            version="1.0",
        )

        # Should be valid
        assert len(str(signal.payload)) < 1024

    def test_signal_create_payload_exceeds_size_limit_rejected(self):
        """Test oversized payload is rejected."""
        # Create payload > 1024 bytes
        payload = {"data": "x" * 2000}

        with pytest.raises(ValidationError) as exc_info:
            SignalCreate(
                instrument="XAUUSD",
                side="buy",
                price=1950.50,
                payload=payload,
                version="1.0",
            )

        assert "payload" in str(exc_info.value).lower()

    def test_signal_create_version_valid_formats(self):
        """Test valid version formats."""
        valid_versions = ["1.0", "2.1", "1.0.0", "3.14.159"]

        for version in valid_versions:
            signal = SignalCreate(
                instrument="XAUUSD",
                side="buy",
                price=1950.50,
                version=version,
            )
            assert signal.version == version

    def test_signal_create_version_invalid_format_rejected(self):
        """Test invalid version format is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SignalCreate(
                instrument="XAUUSD",
                side="buy",
                price=1950.50,
                version="invalid-version",
            )

        assert "version" in str(exc_info.value).lower()

    def test_signal_create_version_single_number_allowed(self):
        """Test version with single number is allowed."""
        signal = SignalCreate(
            instrument="XAUUSD",
            side="buy",
            price=1950.50,
            version="1",
        )
        assert signal.version == "1"

    def test_signal_create_missing_instrument_rejected(self):
        """Test missing instrument field is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SignalCreate(
                # Missing instrument
                side="buy",
                price=1950.50,
                version="1.0",
            )

        assert "instrument" in str(exc_info.value).lower()

    def test_signal_create_missing_side_rejected(self):
        """Test missing side field is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SignalCreate(
                instrument="XAUUSD",
                # Missing side
                price=1950.50,
                version="1.0",
            )

        assert "side" in str(exc_info.value).lower()

    def test_signal_create_missing_price_rejected(self):
        """Test missing price field is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SignalCreate(
                instrument="XAUUSD",
                side="buy",
                # Missing price
                version="1.0",
            )

        assert "price" in str(exc_info.value).lower()

    def test_signal_create_missing_version_defaults_to_1_0(self):
        """Test missing version field defaults to '1.0'."""
        signal = SignalCreate(
            instrument="XAUUSD",
            side="buy",
            price=1950.50,
            # Version omitted
        )

        assert signal.version == "1.0"


class TestSignalOutSchema:
    """Test SignalOut schema and serialization."""

    def test_signal_out_side_label_buy(self):
        """Test side_label property for buy."""
        signal_out = SignalOut(
            id="sig_123",
            instrument="XAUUSD",
            side=0,  # buy
            price=1950.50,
            status=0,
            payload={},
            version="1.0",
        )

        assert signal_out.side_label == "buy"

    def test_signal_out_side_label_sell(self):
        """Test side_label property for sell."""
        signal_out = SignalOut(
            id="sig_123",
            instrument="XAUUSD",
            side=1,  # sell
            price=1950.50,
            status=0,
            payload={},
            version="1.0",
        )

        assert signal_out.side_label == "sell"

    def test_signal_out_status_label_new(self):
        """Test status_label property for new."""
        signal_out = SignalOut(
            id="sig_123",
            instrument="XAUUSD",
            side=0,
            price=1950.50,
            status=SignalStatus.NEW.value,
            payload={},
            version="1.0",
        )

        assert signal_out.status_label == "new"

    def test_signal_out_status_label_approved(self):
        """Test status_label property for approved."""
        signal_out = SignalOut(
            id="sig_123",
            instrument="XAUUSD",
            side=0,
            price=1950.50,
            status=SignalStatus.APPROVED.value,
            payload={},
            version="1.0",
        )

        assert signal_out.status_label == "approved"

    def test_signal_out_all_status_labels(self):
        """Test all status labels."""
        expected_labels = {
            SignalStatus.NEW.value: "new",
            SignalStatus.APPROVED.value: "approved",
            SignalStatus.REJECTED.value: "rejected",
            SignalStatus.EXECUTED.value: "executed",
            SignalStatus.CLOSED.value: "closed",
            SignalStatus.CANCELLED.value: "cancelled",
        }

        for status_value, expected_label in expected_labels.items():
            signal_out = SignalOut(
                id="sig_123",
                instrument="XAUUSD",
                side=0,
                price=1950.50,
                status=status_value,
                payload={},
                version="1.0",
            )

            assert signal_out.status_label == expected_label

    def test_signal_out_serialization_json(self):
        """Test SignalOut serialization to JSON."""
        signal_out = SignalOut(
            id="sig_123",
            instrument="XAUUSD",
            side=0,
            price=1950.50,
            status=0,
            payload={"rsi": 75.5},
            version="1.0",
        )

        json_data = signal_out.model_dump_json()

        assert "sig_123" in json_data
        assert "XAUUSD" in json_data
        assert "1950.5" in json_data


class TestSignalSchemaEdgeCases:
    """Test edge cases and special scenarios."""

    def test_signal_create_boundary_price_0_01(self):
        """Test minimum acceptable price."""
        signal = SignalCreate(
            instrument="XAUUSD",
            side="buy",
            price=0.01,
            version="1.0",
        )

        assert signal.price == 0.01

    def test_signal_create_boundary_price_999999_99(self):
        """Test maximum acceptable price."""
        signal = SignalCreate(
            instrument="XAUUSD",
            side="buy",
            price=999999.99,
            version="1.0",
        )

        assert signal.price == 999999.99

    def test_signal_create_scientific_notation_price(self):
        """Test price in scientific notation."""
        signal = SignalCreate(
            instrument="XAUUSD",
            side="buy",
            price=1.950e3,  # 1950.0
            version="1.0",
        )

        assert signal.price == 1950.0

    def test_signal_create_very_small_price(self):
        """Test very small price."""
        signal = SignalCreate(
            instrument="XAUUSD",
            side="buy",
            price=0.00001,
            version="1.0",
        )

        assert signal.price == 0.00001

    def test_signal_create_very_large_price(self):
        """Test very large price (below limit)."""
        signal = SignalCreate(
            instrument="XAUUSD",
            side="buy",
            price=999999.99999,
            version="1.0",
        )

        assert signal.price == 999999.99999

    def test_signal_create_payload_none_defaults_to_empty(self):
        """Test None payload defaults to empty dict."""
        signal = SignalCreate(
            instrument="XAUUSD",
            side="buy",
            price=1950.50,
            payload=None,
            version="1.0",
        )

        assert signal.payload == {}

    def test_signal_create_whitespace_in_fields_trimmed(self):
        """Test whitespace handling in string fields."""
        # Instrument should not trim (validation happens before)
        with pytest.raises(ValidationError):
            SignalCreate(
                instrument=" XAUUSD ",  # Has spaces
                side="buy",
                price=1950.50,
                version="1.0",
            )

    def test_signal_create_all_valid_instrument_list(self):
        """Test complete list of valid instruments."""
        # From PR-021 spec
        valid_instruments = [
            "XAUUSD",
            "EURUSD",
            "GBPUSD",
            "USDJPY",
            "USDCHF",
            "USDCAD",
            "AUDUSD",
            "NZDUSD",
        ]

        for instrument in valid_instruments:
            signal = SignalCreate(
                instrument=instrument,
                side="buy",
                price=1950.50,
                version="1.0",
            )
            assert signal.instrument == instrument
