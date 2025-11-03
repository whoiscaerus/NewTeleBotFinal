"""Comprehensive tests for signals service business logic.

Tests cover:
- Signal creation with full validation
- Deduplication (external_id and time window)
- HMAC signature verification
- Payload size limits
- Status tracking and updates
- Error handling and transactions
- Metrics recording
- Database operations
"""

import hashlib
import hmac
import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.signals.models import Signal, SignalStatus
from backend.app.signals.schema import SignalCreate, SignalOut
from backend.app.signals.service import (
    DuplicateSignalError,
    SignalNotFoundError,
    SignalService,
)


@pytest.fixture
def hmac_key():
    """HMAC secret key for testing."""
    return "test-secret-key-12345"


@pytest.fixture
def signal_service(db_session, hmac_key):
    """Create signal service for testing."""
    return SignalService(db_session, hmac_key=hmac_key, dedup_window_seconds=300)


@pytest.fixture
def valid_signal_create():
    """Valid signal creation request."""
    return SignalCreate(
        instrument="XAUUSD",
        side="buy",
        price=1950.50,
        payload={"rsi": 75.5, "confidence": 0.85},
        version="1.0",
    )


@pytest.fixture
def valid_signal_create_sell():
    """Valid sell signal."""
    return SignalCreate(
        instrument="EURUSD",
        side="sell",
        price=1.0850,
        payload={"macd": -0.002},
        version="1.0",
    )


class TestSignalCreationBasic:
    """Test basic signal creation workflow."""

    @pytest.mark.asyncio
    async def test_create_signal_valid(self, signal_service, valid_signal_create):
        """Test creating valid signal returns correct structure."""
        signal = await signal_service.create_signal(
            user_id="user_123",
            signal_create=valid_signal_create,
            external_id="ext_001",
        )

        assert signal.id is not None
        assert signal.instrument == "XAUUSD"
        assert signal.side == 0  # buy
        assert signal.price == 1950.50
        assert signal.payload == {"rsi": 75.5, "confidence": 0.85}
        assert signal.status == 0  # new
        assert signal.external_id == "ext_001"
        assert signal.version == "1.0"
        assert signal.created_at is not None
        assert signal.updated_at is not None

    @pytest.mark.asyncio
    async def test_create_signal_sell_direction(
        self, signal_service, valid_signal_create_sell
    ):
        """Test sell signal stored as side=1."""
        signal = await signal_service.create_signal(
            user_id="user_456",
            signal_create=valid_signal_create_sell,
        )

        assert signal.side == 1  # sell
        assert signal.instrument == "EURUSD"
        assert signal.price == 1.0850

    @pytest.mark.asyncio
    async def test_create_signal_without_external_id(
        self, signal_service, valid_signal_create
    ):
        """Test creating signal without external_id."""
        signal = await signal_service.create_signal(
            user_id="user_789",
            signal_create=valid_signal_create,
            external_id=None,
        )

        assert signal.id is not None
        assert signal.external_id is None

    @pytest.mark.asyncio
    async def test_create_signal_persisted_in_db(
        self, db_session, signal_service, valid_signal_create
    ):
        """Test signal is actually saved to database."""
        signal = await signal_service.create_signal(
            user_id="user_db_test",
            signal_create=valid_signal_create,
            external_id="ext_db_001",
        )

        # Query database directly
        result = await db_session.execute(
            select(Signal).where(Signal.id == signal.id)
        )
        db_signal = result.scalar()

        assert db_signal is not None
        assert db_signal.id == signal.id
        assert db_signal.user_id == "user_db_test"
        assert db_signal.instrument == "XAUUSD"

    @pytest.mark.asyncio
    async def test_create_signal_empty_payload(self, signal_service):
        """Test signal creation with empty payload."""
        signal_create = SignalCreate(
            instrument="XAUUSD",
            side="buy",
            price=1950.50,
            payload={},
            version="1.0",
        )

        signal = await signal_service.create_signal(
            user_id="user_empty_payload",
            signal_create=signal_create,
        )

        assert signal.payload == {}

    @pytest.mark.asyncio
    async def test_create_signal_no_payload_field(self, signal_service):
        """Test signal with payload defaulting to empty dict."""
        signal_create = SignalCreate(
            instrument="GBPUSD",
            side="buy",
            price=1.2850,
            version="1.0",
        )

        signal = await signal_service.create_signal(
            user_id="user_no_payload",
            signal_create=signal_create,
        )

        assert signal.payload == {}

    @pytest.mark.asyncio
    async def test_create_signal_multiple_users_different_instruments(
        self, signal_service
    ):
        """Test signals from different users with different instruments don't conflict."""
        signal_create_a = SignalCreate(
            instrument="XAUUSD",
            side="buy",
            price=1950.50,
            version="1.0",
        )
        signal_create_b = SignalCreate(
            instrument="EURUSD",  # Different instrument
            side="buy",
            price=1.0850,
            version="1.0",
        )

        signal1 = await signal_service.create_signal(
            user_id="user_a",
            signal_create=signal_create_a,
        )
        signal2 = await signal_service.create_signal(
            user_id="user_b",
            signal_create=signal_create_b,
        )

        assert signal1.id != signal2.id
        assert signal1.instrument == "XAUUSD"
        assert signal2.instrument == "EURUSD"


class TestSignalDeduplication:
    """Test deduplication logic."""

    @pytest.mark.asyncio
    async def test_duplicate_external_id_rejected(
        self, signal_service, valid_signal_create
    ):
        """Test duplicate external_id is rejected."""
        external_id = "ext_unique_001"

        # Create first signal
        signal1 = await signal_service.create_signal(
            user_id="user_dedup",
            signal_create=valid_signal_create,
            external_id=external_id,
        )

        assert signal1.external_id == external_id

        # Attempt to create duplicate
        with pytest.raises(DuplicateSignalError):
            await signal_service.create_signal(
                user_id="user_dedup",
                signal_create=valid_signal_create,
                external_id=external_id,
            )

    @pytest.mark.asyncio
    async def test_duplicate_instrument_time_version_rejected(
        self, signal_service, valid_signal_create
    ):
        """Test duplicate (instrument, time, version) within window is rejected."""
        # Create first signal
        signal1 = await signal_service.create_signal(
            user_id="user_dedup_window",
            signal_create=valid_signal_create,
        )

        # Attempt to create another signal with same instrument/version within window
        signal_create_2 = SignalCreate(
            instrument="XAUUSD",  # Same
            side="sell",
            price=1950.50,
            version="1.0",  # Same
        )

        with pytest.raises(DuplicateSignalError):
            await signal_service.create_signal(
                user_id="user_dedup_window",
                signal_create=signal_create_2,
            )

    @pytest.mark.asyncio
    async def test_different_version_not_duplicate(
        self, signal_service, valid_signal_create
    ):
        """Test different version not considered duplicate."""
        # Create signal v1.0
        signal1 = await signal_service.create_signal(
            user_id="user_versions",
            signal_create=valid_signal_create,
        )

        # Create signal v2.0 same instrument
        signal_create_v2 = SignalCreate(
            instrument="XAUUSD",
            side="buy",
            price=1950.50,
            version="2.0",
        )

        signal2 = await signal_service.create_signal(
            user_id="user_versions",
            signal_create=signal_create_v2,
        )

        # Both should exist
        assert signal1.id != signal2.id
        assert signal1.version == "1.0"
        assert signal2.version == "2.0"

    @pytest.mark.asyncio
    async def test_different_instrument_not_duplicate(
        self, signal_service, valid_signal_create
    ):
        """Test different instrument not considered duplicate."""
        signal1 = await signal_service.create_signal(
            user_id="user_instruments",
            signal_create=valid_signal_create,  # XAUUSD
        )

        signal_create_eurusd = SignalCreate(
            instrument="EURUSD",  # Different
            side="buy",
            price=1.0850,
            version="1.0",
        )

        signal2 = await signal_service.create_signal(
            user_id="user_instruments",
            signal_create=signal_create_eurusd,
        )

        assert signal1.id != signal2.id
        assert signal1.instrument == "XAUUSD"
        assert signal2.instrument == "EURUSD"

    @pytest.mark.asyncio
    async def test_duplicate_allowed_outside_window(
        self, db_session, hmac_key, valid_signal_create
    ):
        """Test duplicate allowed after dedup window expires."""
        # Create service with 1 second window for testing
        service_short_window = SignalService(
            db_session,
            hmac_key=hmac_key,
            dedup_window_seconds=1,
        )

        # Create first signal
        signal1 = await service_short_window.create_signal(
            user_id="user_window_test",
            signal_create=valid_signal_create,
        )

        # Wait for window to expire
        import asyncio

        await asyncio.sleep(1.5)

        # Should now be allowed
        signal2 = await service_short_window.create_signal(
            user_id="user_window_test",
            signal_create=valid_signal_create,
        )

        assert signal1.id != signal2.id


class TestHMACSignatureVerification:
    """Test HMAC signature verification."""

    @pytest.mark.asyncio
    async def test_verify_hmac_valid_signature(self, signal_service, hmac_key):
        """Test valid HMAC signature is verified."""
        payload = '{"instrument": "XAUUSD", "side": "buy"}'

        expected_sig = hmac.new(
            hmac_key.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()

        is_valid = signal_service.verify_hmac_signature(payload, expected_sig)

        assert is_valid is True

    @pytest.mark.asyncio
    async def test_verify_hmac_invalid_signature(self, signal_service, hmac_key):
        """Test invalid HMAC signature is rejected."""
        payload = '{"instrument": "XAUUSD", "side": "buy"}'
        invalid_sig = "0" * 64  # Wrong signature

        is_valid = signal_service.verify_hmac_signature(payload, invalid_sig)

        assert is_valid is False

    @pytest.mark.asyncio
    async def test_verify_hmac_modified_payload(self, signal_service, hmac_key):
        """Test HMAC fails if payload is modified."""
        payload = '{"instrument": "XAUUSD", "side": "buy"}'

        # Create signature for original payload
        original_sig = hmac.new(
            hmac_key.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()

        # Modify payload
        modified_payload = '{"instrument": "EURUSD", "side": "buy"}'

        is_valid = signal_service.verify_hmac_signature(modified_payload, original_sig)

        assert is_valid is False

    @pytest.mark.asyncio
    async def test_verify_hmac_wrong_key(self, signal_service):
        """Test HMAC fails with wrong key."""
        payload = '{"instrument": "XAUUSD", "side": "buy"}'
        wrong_key = "wrong-secret-key"

        # Create signature with wrong key
        wrong_sig = hmac.new(
            wrong_key.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()

        is_valid = signal_service.verify_hmac_signature(payload, wrong_sig)

        assert is_valid is False

    @pytest.mark.asyncio
    async def test_verify_hmac_empty_signature(self, signal_service):
        """Test empty HMAC signature is invalid."""
        payload = '{"instrument": "XAUUSD", "side": "buy"}'

        is_valid = signal_service.verify_hmac_signature(payload, "")

        assert is_valid is False


class TestSignalRetrieval:
    """Test signal retrieval operations."""

    @pytest.mark.asyncio
    async def test_get_signal_success(self, signal_service, valid_signal_create):
        """Test retrieving signal by ID."""
        created = await signal_service.create_signal(
            user_id="user_get",
            signal_create=valid_signal_create,
        )

        retrieved = await signal_service.get_signal(created.id)

        assert retrieved.id == created.id
        assert retrieved.instrument == "XAUUSD"
        assert retrieved.side == 0

    @pytest.mark.asyncio
    async def test_get_signal_not_found(self, signal_service):
        """Test retrieving non-existent signal raises error."""
        with pytest.raises(SignalNotFoundError):
            await signal_service.get_signal("nonexistent_id")

    @pytest.mark.asyncio
    async def test_list_signals_empty(self, signal_service):
        """Test listing signals for user with no signals."""
        signals, total = await signal_service.list_signals(user_id="user_no_signals")

        assert signals == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_list_signals_multiple(self, signal_service):
        """Test listing multiple signals."""
        signal_create_1 = SignalCreate(
            instrument="XAUUSD", side="buy", price=1950.50, version="1.0"
        )
        signal_create_2 = SignalCreate(
            instrument="EURUSD", side="sell", price=1.0850, version="1.0"
        )

        await signal_service.create_signal(
            user_id="user_list",
            signal_create=signal_create_1,
        )
        await signal_service.create_signal(
            user_id="user_list",
            signal_create=signal_create_2,
        )

        signals, total = await signal_service.list_signals(user_id="user_list")

        assert len(signals) == 2
        assert total == 2

    @pytest.mark.asyncio
    async def test_list_signals_pagination(self, signal_service):
        """Test pagination in list_signals."""
        # Create 5 signals with different versions to avoid dedup
        for i in range(5):
            signal_create = SignalCreate(
                instrument="XAUUSD",
                side="buy",
                price=1950.50 + i,
                version=f"1.{i}",  # Different version each time
            )
            await signal_service.create_signal(
                user_id="user_pagination",
                signal_create=signal_create,
            )

        # Get page 1 with page_size=2
        page1, total = await signal_service.list_signals(
            user_id="user_pagination",
            page=1,
            page_size=2,
        )

        assert len(page1) == 2
        assert total == 5

        # Get page 2
        page2, total = await signal_service.list_signals(
            user_id="user_pagination",
            page=2,
            page_size=2,
        )

        assert len(page2) == 2

    @pytest.mark.asyncio
    async def test_list_signals_filter_by_status(self, signal_service):
        """Test filtering signals by status."""
        signal_create = SignalCreate(
            instrument="XAUUSD", side="buy", price=1950.50, version="1.0"
        )

        signal1 = await signal_service.create_signal(
            user_id="user_status_filter",
            signal_create=signal_create,
        )

        # Update status to approved
        await signal_service.update_signal_status(
            signal1.id, SignalStatus.APPROVED
        )

        # List only new signals
        new_signals, _ = await signal_service.list_signals(
            user_id="user_status_filter",
            status=SignalStatus.NEW.value,
        )

        assert len(new_signals) == 0  # No new signals

        # List approved signals
        approved_signals, _ = await signal_service.list_signals(
            user_id="user_status_filter",
            status=SignalStatus.APPROVED.value,
        )

        assert len(approved_signals) == 1
        assert approved_signals[0].status == SignalStatus.APPROVED.value

    @pytest.mark.asyncio
    async def test_list_signals_filter_by_instrument(self, signal_service):
        """Test filtering signals by instrument."""
        # Create XAUUSD signal
        signal_create_gold = SignalCreate(
            instrument="XAUUSD", side="buy", price=1950.50, version="1.0"
        )
        await signal_service.create_signal(
            user_id="user_instrument_filter",
            signal_create=signal_create_gold,
        )

        # Create EURUSD signal
        signal_create_eur = SignalCreate(
            instrument="EURUSD", side="sell", price=1.0850, version="1.0"
        )
        await signal_service.create_signal(
            user_id="user_instrument_filter",
            signal_create=signal_create_eur,
        )

        # Filter by XAUUSD
        gold_signals, _ = await signal_service.list_signals(
            user_id="user_instrument_filter",
            instrument="XAUUSD",
        )

        assert len(gold_signals) == 1
        assert gold_signals[0].instrument == "XAUUSD"


class TestSignalStatusUpdate:
    """Test signal status update operations."""

    @pytest.mark.asyncio
    async def test_update_signal_status_success(
        self, signal_service, valid_signal_create
    ):
        """Test updating signal status."""
        signal = await signal_service.create_signal(
            user_id="user_status_update",
            signal_create=valid_signal_create,
        )

        assert signal.status == SignalStatus.NEW.value

        updated = await signal_service.update_signal_status(
            signal.id, SignalStatus.APPROVED
        )

        assert updated.status == SignalStatus.APPROVED.value
        assert updated.id == signal.id

    @pytest.mark.asyncio
    async def test_update_signal_status_progression(
        self, signal_service, valid_signal_create
    ):
        """Test progressing through signal statuses."""
        signal = await signal_service.create_signal(
            user_id="user_status_progression",
            signal_create=valid_signal_create,
        )

        # NEW → APPROVED
        signal = await signal_service.update_signal_status(
            signal.id, SignalStatus.APPROVED
        )
        assert signal.status == SignalStatus.APPROVED.value

        # APPROVED → EXECUTED
        signal = await signal_service.update_signal_status(
            signal.id, SignalStatus.EXECUTED
        )
        assert signal.status == SignalStatus.EXECUTED.value

        # EXECUTED → CLOSED
        signal = await signal_service.update_signal_status(signal.id, SignalStatus.CLOSED)
        assert signal.status == SignalStatus.CLOSED.value

    @pytest.mark.asyncio
    async def test_update_signal_status_not_found(self, signal_service):
        """Test updating non-existent signal raises error."""
        with pytest.raises(SignalNotFoundError):
            await signal_service.update_signal_status(
                "nonexistent_id", SignalStatus.APPROVED
            )

    @pytest.mark.asyncio
    async def test_update_signal_timestamp(
        self, signal_service, valid_signal_create
    ):
        """Test signal updated_at changes when status updated."""
        signal = await signal_service.create_signal(
            user_id="user_timestamp",
            signal_create=valid_signal_create,
        )

        original_updated_at = signal.updated_at

        import asyncio

        await asyncio.sleep(0.1)

        updated = await signal_service.update_signal_status(
            signal.id, SignalStatus.APPROVED
        )

        assert updated.updated_at > original_updated_at


class TestSignalErrorHandling:
    """Test error handling and edge cases."""

    @pytest.mark.asyncio
    async def test_create_signal_zero_price_rejected(self, signal_service):
        """Test signal with zero price is rejected."""
        with pytest.raises(ValueError):
            SignalCreate(
                instrument="XAUUSD",
                side="buy",
                price=0.0,
                version="1.0",
            )

    @pytest.mark.asyncio
    async def test_create_signal_negative_price_rejected(self, signal_service):
        """Test signal with negative price is rejected."""
        with pytest.raises(ValueError):
            SignalCreate(
                instrument="XAUUSD",
                side="buy",
                price=-100.0,
                version="1.0",
            )

    @pytest.mark.asyncio
    async def test_create_signal_invalid_instrument_rejected(self, signal_service):
        """Test signal with invalid instrument is rejected."""
        with pytest.raises(ValueError):
            SignalCreate(
                instrument="INVALID_XYZ",
                side="buy",
                price=1950.50,
                version="1.0",
            )

    @pytest.mark.asyncio
    async def test_create_signal_invalid_side_rejected(self, signal_service):
        """Test signal with invalid side is rejected."""
        with pytest.raises(ValueError):
            SignalCreate(
                instrument="XAUUSD",
                side="INVALID",
                price=1950.50,
                version="1.0",
            )

    @pytest.mark.asyncio
    async def test_create_signal_payload_too_large_rejected(self, signal_service):
        """Test signal with oversized payload is rejected."""
        large_payload = {"data": "x" * 2000}  # Exceeds 1KB limit

        with pytest.raises(ValueError):
            SignalCreate(
                instrument="XAUUSD",
                side="buy",
                price=1950.50,
                payload=large_payload,
                version="1.0",
            )

    @pytest.mark.asyncio
    async def test_create_signal_invalid_version_rejected(self, signal_service):
        """Test signal with invalid version format is rejected."""
        with pytest.raises(ValueError):
            SignalCreate(
                instrument="XAUUSD",
                side="buy",
                price=1950.50,
                version="invalid-version",
            )

    @pytest.mark.asyncio
    async def test_create_signal_missing_required_fields(self, signal_service):
        """Test signal creation fails with missing required fields."""
        with pytest.raises(ValueError):
            SignalCreate(
                instrument="XAUUSD",
                # Missing side
                price=1950.50,
                version="1.0",
            )

    @pytest.mark.asyncio
    async def test_create_signal_database_rollback_on_error(
        self, db_session, signal_service
    ):
        """Test transaction rollback on error."""
        signal_create = SignalCreate(
            instrument="XAUUSD",
            side="buy",
            price=1950.50,
            version="1.0",
        )

        # Create first signal
        signal1 = await signal_service.create_signal(
            user_id="user_rollback",
            signal_create=signal_create,
            external_id="ext_rollback_001",
        )

        # Try to create duplicate (should fail and rollback)
        try:
            await signal_service.create_signal(
                user_id="user_rollback",
                signal_create=signal_create,
                external_id="ext_rollback_001",
            )
        except DuplicateSignalError:
            pass

        # Verify database is clean (no partial state)
        result = await db_session.execute(
            select(Signal).where(Signal.external_id == "ext_rollback_001")
        )
        signals = result.scalars().all()

        assert len(signals) == 1  # Only the original signal


class TestSignalMetrics:
    """Test metrics recording."""

    @pytest.mark.asyncio
    async def test_create_signal_records_metrics(self, signal_service):
        """Test signal creation records metrics (best-effort)."""
        signal_create = SignalCreate(
            instrument="XAUUSD",
            side="buy",
            price=1950.50,
            version="1.0",
        )

        # Should not raise even if metrics fails
        signal = await signal_service.create_signal(
            user_id="user_metrics",
            signal_create=signal_create,
        )

        assert signal.id is not None


class TestSignalOutSchema:
    """Test SignalOut schema serialization."""

    @pytest.mark.asyncio
    async def test_signal_out_side_label(
        self, signal_service, valid_signal_create
    ):
        """Test side_label property."""
        signal = await signal_service.create_signal(
            user_id="user_schema",
            signal_create=valid_signal_create,
        )

        assert signal.side_label == "buy"

    @pytest.mark.asyncio
    async def test_signal_out_status_label(
        self, signal_service, valid_signal_create
    ):
        """Test status_label property."""
        signal = await signal_service.create_signal(
            user_id="user_status_label",
            signal_create=valid_signal_create,
        )

        assert signal.status_label == "new"

        updated = await signal_service.update_signal_status(
            signal.id, SignalStatus.APPROVED
        )

        assert updated.status_label == "approved"
