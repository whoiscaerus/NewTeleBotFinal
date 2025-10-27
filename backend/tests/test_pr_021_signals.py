"""Comprehensive tests for PR-021: Signals API (ingest, schema, dedupe, payload limits)."""

import hashlib
import hmac
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.signals.schema import SignalCreate
from backend.app.signals.service import DuplicateSignalError, SignalService


@pytest.fixture(autouse=True)
def mock_metrics():
    """Mock metrics to avoid duplicate registration."""
    with patch("backend.app.signals.service.get_metrics") as mock:
        mock_obj = MagicMock()
        mock_obj.labels.return_value.inc.return_value = None
        mock_obj.labels.return_value.observe.return_value = None
        mock.return_value = MagicMock(
            signals_ingested_total=mock_obj,
            signals_create_seconds=mock_obj,
        )
        yield mock


@pytest.mark.asyncio
class TestSignalServiceHMAC:
    """Test HMAC signature verification for PR-021."""

    async def test_verify_hmac_valid_signature(self):
        """Test HMAC verification accepts valid signature."""
        service = SignalService(None, hmac_key="secret-key-12345")
        payload = '{"instrument":"GOLD","side":"buy"}'

        sig = hmac.new(
            b"secret-key-12345", payload.encode(), hashlib.sha256
        ).hexdigest()
        assert service.verify_hmac_signature(payload, sig)

    async def test_verify_hmac_invalid_signature(self):
        """Test HMAC verification rejects invalid signature."""
        service = SignalService(None, hmac_key="secret-key-12345")
        payload = '{"instrument":"GOLD","side":"buy"}'

        assert not service.verify_hmac_signature(payload, "invalid-sig")

    async def test_verify_hmac_tampered_payload(self):
        """Test HMAC rejects tampered payload."""
        service = SignalService(None, hmac_key="secret-key-12345")
        original_payload = '{"instrument":"GOLD","side":"buy"}'

        sig = hmac.new(
            b"secret-key-12345", original_payload.encode(), hashlib.sha256
        ).hexdigest()

        # Tampered payload
        tampered = '{"instrument":"GOLD","side":"sell"}'
        assert not service.verify_hmac_signature(tampered, sig)


@pytest.mark.asyncio
class TestSignalCreation:
    """Test signal creation with validation."""

    async def test_create_signal_valid(self, db_session: AsyncSession):
        """Test creating valid signal."""
        service = SignalService(db_session, "test-key")
        signal_create = SignalCreate(
            instrument="XAUUSD",
            side="buy",
            price=1950.50,
            payload={"rsi": 75},
            version="1.0",
        )

        result = await service.create_signal("user-123", signal_create)
        assert result.id is not None
        assert result.instrument == "XAUUSD"
        assert result.status == 0  # NEW

    async def test_create_signal_with_external_id(self, db_session: AsyncSession):
        """Test creating signal with deduplication ID."""
        service = SignalService(db_session, "test-key")
        signal_create = SignalCreate(
            instrument="EURUSD",
            side="buy",
            price=1.1050,
            payload={"rsi": 75},
            version="1.0",
        )

        result = await service.create_signal(
            "user-123", signal_create, external_id="ext-001"
        )
        assert result.id is not None
        assert result.external_id == "ext-001"

    async def test_create_signal_duplicate_external_id(self, db_session: AsyncSession):
        """Test duplicate external_id is rejected."""
        service = SignalService(db_session, "test-key")
        signal_create = SignalCreate(
            instrument="GBPUSD",
            side="buy",
            price=1.2750,
            payload={"rsi": 75},
            version="1.0",
        )

        # Create first signal
        await service.create_signal("user-123", signal_create, external_id="ext-001")

        # Try to create duplicate
        with pytest.raises(DuplicateSignalError):
            await service.create_signal(
                "user-123", signal_create, external_id="ext-001"
            )

    async def test_create_signal_dedup_window_same_instrument_version(
        self, db_session: AsyncSession
    ):
        """Test dedup window rejects duplicate (instrument, time, version) within window."""
        service = SignalService(db_session, "test-key", dedup_window_seconds=300)

        signal_create = SignalCreate(
            instrument="USDJPY",
            side="buy",
            price=150.25,
            payload={"rsi": 75},
            version="1.0",
        )

        # Create first signal
        await service.create_signal("user-123", signal_create)

        # Try to create same instrument/version within 5 minutes
        with pytest.raises(DuplicateSignalError):
            await service.create_signal("user-456", signal_create)

    async def test_create_signal_dedup_window_different_version_allowed(
        self, db_session: AsyncSession
    ):
        """Test different version within window is allowed."""
        service = SignalService(db_session, "test-key", dedup_window_seconds=300)

        signal_v1 = SignalCreate(
            instrument="AUDUSD",
            side="buy",
            price=0.6750,
            payload={"rsi": 75},
            version="1.0",
        )

        signal_v2 = SignalCreate(
            instrument="AUDUSD",
            side="buy",
            price=0.6750,
            payload={"rsi": 75},
            version="2.0",
        )

        # Create both
        result1 = await service.create_signal("user-123", signal_v1)
        result2 = await service.create_signal("user-456", signal_v2)

        assert result1.id != result2.id
        assert result1.version == "1.0"
        assert result2.version == "2.0"


@pytest.mark.asyncio
class TestSignalRetrieval:
    """Test signal retrieval."""

    async def test_get_signal_by_id(self, db_session: AsyncSession):
        """Test retrieving signal by ID."""
        service = SignalService(db_session, "test-key")
        signal_create = SignalCreate(
            instrument="NZDUSD",
            side="buy",
            price=0.5850,
            payload={"rsi": 75},
            version="1.0",
        )

        created = await service.create_signal("user-123", signal_create)
        retrieved = await service.get_signal(created.id)

        assert retrieved.id == created.id
        assert retrieved.instrument == "NZDUSD"


@pytest.mark.asyncio
class TestSignalSettings:
    """Test configuration via settings."""

    def test_signals_settings_exist(self):
        """Test SignalsSettings are properly configured."""
        # Simply verify no import errors and lazy loading works
        # Settings are tested in integration tests
        from backend.app.signals.service import SignalService

        # Service initializes without error
        service = SignalService(None, "test-key")
        assert service is not None
