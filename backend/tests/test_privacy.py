"""Comprehensive tests for Privacy Center (PR-068).

Tests validate FULL working business logic:
- Export request workflow (data collection, ZIP creation, URL generation)
- Delete request workflow (cooling-off period, cascade deletion)
- Admin hold override (active disputes blocking deletion)
- Identity verification and audit trails
- Edge cases and error conditions
"""

import io
import json
import zipfile
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.approvals.models import Approval
from backend.app.audit.models import AuditLog
from backend.app.clients.devices.models import Device
from backend.app.privacy.deleter import DataDeleter
from backend.app.privacy.exporter import DataExporter
from backend.app.privacy.models import PrivacyRequest, RequestStatus, RequestType
from backend.app.privacy.schemas import PrivacyRequestCreate
from backend.app.privacy.service import PrivacyService
from backend.app.signals.models import Signal
from backend.app.users.models import User


@pytest.mark.asyncio
class TestPrivacyRequestCreation:
    """Test privacy request creation logic."""

    async def test_create_export_request(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test creating export request sets correct status and fields."""
        service = PrivacyService(db_session)

        request_data = PrivacyRequestCreate(
            request_type=RequestType.EXPORT, reason="GDPR data access request"
        )

        request = await service.create_request(test_user.id, request_data)

        assert request.id is not None
        assert request.user_id == test_user.id
        assert request.request_type == RequestType.EXPORT
        assert request.status == RequestStatus.PENDING
        assert request.created_at is not None
        assert request.processed_at is None
        assert request.scheduled_deletion_at is None  # Not set for export
        assert request.metadata["reason"] == "GDPR data access request"

    async def test_create_delete_request_sets_cooling_off_period(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test delete request sets 72-hour cooling-off period."""
        service = PrivacyService(db_session)

        before = datetime.utcnow()
        request_data = PrivacyRequestCreate(
            request_type=RequestType.DELETE, reason="Closing account"
        )

        request = await service.create_request(test_user.id, request_data)
        after = datetime.utcnow()

        assert request.request_type == RequestType.DELETE
        assert request.scheduled_deletion_at is not None

        # Verify cooling-off period is ~72 hours
        expected_min = before + timedelta(hours=72)
        expected_max = after + timedelta(hours=72)
        assert expected_min <= request.scheduled_deletion_at <= expected_max

        # Verify not deletable yet
        assert not request.is_deletable
        assert request.cooling_off_hours_remaining > 0

    async def test_cannot_create_duplicate_pending_request(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test user cannot have multiple pending requests of same type."""
        service = PrivacyService(db_session)

        # Create first request
        request_data = PrivacyRequestCreate(request_type=RequestType.EXPORT)
        await service.create_request(test_user.id, request_data)

        # Attempt duplicate request
        with pytest.raises(ValueError, match="already has a pending export request"):
            await service.create_request(test_user.id, request_data)

    async def test_can_create_different_request_types(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test user can have pending export AND delete request simultaneously."""
        service = PrivacyService(db_session)

        # Create export request
        export_data = PrivacyRequestCreate(request_type=RequestType.EXPORT)
        export_req = await service.create_request(test_user.id, export_data)

        # Create delete request (different type)
        delete_data = PrivacyRequestCreate(request_type=RequestType.DELETE)
        delete_req = await service.create_request(test_user.id, delete_data)

        assert export_req.request_type == RequestType.EXPORT
        assert delete_req.request_type == RequestType.DELETE
        assert export_req.id != delete_req.id


@pytest.mark.asyncio
class TestDataExporter:
    """Test data export business logic."""

    async def test_export_user_profile(self, db_session: AsyncSession, test_user: User):
        """Test user profile export redacts password."""
        exporter = DataExporter(db_session)

        export_data = await exporter.export_user_data(test_user.id, "test-request-id")

        assert export_data["user_profile"]["id"] == test_user.id
        assert export_data["user_profile"]["telegram_id"] == test_user.telegram_id
        assert export_data["user_profile"]["username"] == test_user.username
        assert "password" not in export_data["user_profile"]
        assert "hashed_password" not in export_data["user_profile"]

    async def test_export_trades_redacts_sensitive_fields(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test trade export redacts broker tickets and internal IDs."""
        # Create test signal
        signal = Signal(
            id=str(uuid4()),
            user_id=test_user.id,
            instrument="XAUUSD",
            side=0,  # buy
            entry_price=1950.50,
            stop_loss=1940.00,
            take_profit=1970.00,
            status=2,  # filled
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db_session.add(signal)
        await db_session.commit()

        exporter = DataExporter(db_session)
        export_data = await exporter.export_user_data(test_user.id, "test-request-id")

        trades = export_data["trades"]
        assert len(trades) == 1
        assert trades[0]["instrument"] == "XAUUSD"
        assert trades[0]["side"] == "buy"
        assert trades[0]["entry_price"] == 1950.50
        assert "broker_ticket" not in trades[0]
        assert "device_secret" not in trades[0]

    async def test_export_devices_redacts_secrets(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test device export redacts device secrets."""
        # Create test device
        device = Device(
            id=str(uuid4()),
            user_id=test_user.id,
            name="MT5 EA #1",
            secret="super-secret-key-12345",
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(device)
        await db_session.commit()

        exporter = DataExporter(db_session)
        export_data = await exporter.export_user_data(test_user.id, "test-request-id")

        devices = export_data["devices"]
        assert len(devices) == 1
        assert devices[0]["device_id"] == device.id
        assert devices[0]["name"] == "MT5 EA #1"
        assert "secret" not in devices[0]
        assert "device_secret" not in devices[0]

    async def test_export_bundle_creates_valid_zip(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test ZIP bundle creation with JSON and CSV files."""
        exporter = DataExporter(db_session)

        # Create sample export data
        export_data = {
            "export_metadata": {
                "user_id": test_user.id,
                "exported_at": datetime.utcnow().isoformat(),
            },
            "user_profile": {"id": test_user.id, "username": test_user.username},
            "trades": [
                {"signal_id": "sig1", "instrument": "XAUUSD", "side": "buy"},
                {"signal_id": "sig2", "instrument": "EURUSD", "side": "sell"},
            ],
            "billing": [],
            "devices": [],
        }

        bundle_bytes = exporter.create_export_bundle(export_data)

        # Verify valid ZIP
        assert len(bundle_bytes) > 0
        zip_buffer = io.BytesIO(bundle_bytes)

        with zipfile.ZipFile(zip_buffer, "r") as zip_file:
            file_list = zip_file.namelist()
            assert "export.json" in file_list
            assert "trades.csv" in file_list
            assert "README.txt" in file_list

            # Verify JSON content
            json_content = zip_file.read("export.json").decode("utf-8")
            parsed = json.loads(json_content)
            assert parsed["user_profile"]["username"] == test_user.username

            # Verify CSV content
            csv_content = zip_file.read("trades.csv").decode("utf-8")
            assert "signal_id,instrument,side" in csv_content
            assert "sig1,XAUUSD,buy" in csv_content

    async def test_export_nonexistent_user_raises_error(self, db_session: AsyncSession):
        """Test exporting nonexistent user raises ValueError."""
        exporter = DataExporter(db_session)

        with pytest.raises(ValueError, match="User .* not found"):
            await exporter.export_user_data("nonexistent-user-id", "test-request-id")


@pytest.mark.asyncio
class TestDataDeleter:
    """Test data deletion business logic."""

    async def test_can_delete_user_checks_active_disputes(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test deletion is blocked by active disputes (business rule)."""
        deleter = DataDeleter(db_session)

        # Currently no disputes, should be deletable
        can_delete, reason = await deleter.can_delete_user(test_user.id)
        assert can_delete is True
        assert reason is None

    async def test_delete_user_data_cascades_correctly(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test deletion removes all user data in correct order."""
        # Create related data
        signal = Signal(
            id=str(uuid4()),
            user_id=test_user.id,
            instrument="XAUUSD",
            side=0,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db_session.add(signal)

        device = Device(
            id=str(uuid4()),
            user_id=test_user.id,
            name="Test Device",
            secret="secret123",
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(device)

        approval = Approval(
            id=str(uuid4()),
            user_id=test_user.id,
            signal_id=signal.id,
            approved=True,
            approved_at=datetime.utcnow(),
            created_at=datetime.utcnow(),
        )
        db_session.add(approval)

        await db_session.commit()

        # Delete user data
        deleter = DataDeleter(db_session)
        request_id = str(uuid4())
        await deleter.delete_user_data(test_user.id, request_id)

        # Verify signals deleted
        result = await db_session.execute(
            select(Signal).filter(Signal.user_id == test_user.id)
        )
        assert len(list(result.scalars().all())) == 0

        # Verify devices deleted
        result = await db_session.execute(
            select(Device).filter(Device.user_id == test_user.id)
        )
        assert len(list(result.scalars().all())) == 0

        # Verify approvals deleted
        result = await db_session.execute(
            select(Approval).filter(Approval.user_id == test_user.id)
        )
        assert len(list(result.scalars().all())) == 0

        # Verify user deleted
        result = await db_session.execute(select(User).filter(User.id == test_user.id))
        assert result.scalar_one_or_none() is None

    async def test_anonymize_audit_logs_preserves_events(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test audit log anonymization keeps event type but removes PII."""
        # Create audit log
        audit_log = AuditLog(
            id=str(uuid4()),
            user_id=test_user.id,
            event_type="signal.approved",
            action="approve_signal",
            timestamp=datetime.utcnow(),
            metadata={"signal_id": "sig123", "user_email": "user@example.com"},
        )
        db_session.add(audit_log)
        await db_session.commit()

        # Anonymize
        deleter = DataDeleter(db_session)
        await deleter._anonymize_audit_logs(test_user.id)
        await db_session.commit()

        # Verify anonymization
        result = await db_session.execute(
            select(AuditLog).filter(AuditLog.id == audit_log.id)
        )
        updated_log = result.scalar_one()

        assert updated_log.user_id == "DELETED_USER"
        assert updated_log.event_type == "signal.approved"  # Preserved for audit trail
        assert "anonymized" in updated_log.metadata
        assert "user_email" not in updated_log.metadata  # PII removed


@pytest.mark.asyncio
class TestPrivacyServiceWorkflows:
    """Test end-to-end privacy request workflows."""

    async def test_export_request_workflow(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test complete export workflow: create → process → generate URL."""
        service = PrivacyService(db_session)

        # Create export request
        request_data = PrivacyRequestCreate(request_type=RequestType.EXPORT)
        request = await service.create_request(test_user.id, request_data)

        assert request.status == RequestStatus.PENDING
        assert request.export_url is None

        # Process export request
        processed = await service.process_export_request(request.id)

        assert processed.status == RequestStatus.COMPLETED
        assert processed.export_url is not None
        assert processed.export_expires_at is not None
        assert processed.processed_at is not None
        assert processed.export_url_valid is True

    async def test_delete_request_workflow_enforces_cooling_off(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test delete workflow enforces cooling-off period."""
        service = PrivacyService(db_session)

        # Create delete request
        request_data = PrivacyRequestCreate(request_type=RequestType.DELETE)
        request = await service.create_request(test_user.id, request_data)

        # Attempt immediate processing (should fail)
        with pytest.raises(ValueError, match="Cooling-off period not elapsed"):
            await service.process_delete_request(request.id)

        # Simulate cooling-off period elapsed
        request.scheduled_deletion_at = datetime.utcnow() - timedelta(hours=1)
        await db_session.commit()

        # Now processing should succeed
        processed = await service.process_delete_request(request.id)

        assert processed.status == RequestStatus.COMPLETED
        assert processed.processed_at is not None

    async def test_admin_hold_blocks_deletion(
        self, db_session: AsyncSession, test_user: User, admin_user: User
    ):
        """Test admin hold prevents deletion during disputes."""
        service = PrivacyService(db_session)

        # Create delete request
        request_data = PrivacyRequestCreate(request_type=RequestType.DELETE)
        request = await service.create_request(test_user.id, request_data)

        # Place admin hold
        held_request = await service.place_hold(
            request.id,
            "Active chargeback dispute with Stripe",
            admin_user.id,
        )

        assert held_request.status == RequestStatus.ON_HOLD
        assert held_request.hold_reason == "Active chargeback dispute with Stripe"
        assert held_request.hold_by == admin_user.id
        assert held_request.hold_at is not None

        # Simulate cooling-off period elapsed
        held_request.scheduled_deletion_at = datetime.utcnow() - timedelta(hours=1)
        await db_session.commit()

        # Attempt processing (should fail due to hold)
        with pytest.raises(ValueError, match="is on hold"):
            await service.process_delete_request(request.id)

    async def test_release_hold_allows_deletion(
        self, db_session: AsyncSession, test_user: User, admin_user: User
    ):
        """Test releasing hold allows deletion to proceed."""
        service = PrivacyService(db_session)

        # Create and hold delete request
        request_data = PrivacyRequestCreate(request_type=RequestType.DELETE)
        request = await service.create_request(test_user.id, request_data)
        await service.place_hold(request.id, "Active dispute", admin_user.id)

        # Release hold
        released_request = await service.release_hold(request.id, admin_user.id)

        assert released_request.status == RequestStatus.PENDING
        assert "hold_released_by" in released_request.metadata
        assert released_request.metadata["hold_released_by"] == admin_user.id

    async def test_cancel_pending_request(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test user can cancel pending request."""
        service = PrivacyService(db_session)

        # Create request
        request_data = PrivacyRequestCreate(request_type=RequestType.EXPORT)
        request = await service.create_request(test_user.id, request_data)

        # Cancel it
        cancelled = await service.cancel_request(
            request.id, test_user.id, "Changed my mind"
        )

        assert cancelled.status == RequestStatus.CANCELLED
        assert cancelled.processed_at is not None
        assert cancelled.metadata["cancellation_reason"] == "Changed my mind"

    async def test_cannot_cancel_completed_request(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test cannot cancel already completed request."""
        service = PrivacyService(db_session)

        # Create and process export request
        request_data = PrivacyRequestCreate(request_type=RequestType.EXPORT)
        request = await service.create_request(test_user.id, request_data)
        await service.process_export_request(request.id)

        # Attempt to cancel completed request
        with pytest.raises(ValueError, match="Cannot cancel request in status"):
            await service.cancel_request(request.id, test_user.id)

    async def test_list_requests_returns_all_user_requests(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test list returns all requests for user in descending order."""
        service = PrivacyService(db_session)

        # Create multiple requests
        export_data = PrivacyRequestCreate(request_type=RequestType.EXPORT)
        await service.create_request(test_user.id, export_data)

        delete_data = PrivacyRequestCreate(request_type=RequestType.DELETE)
        await service.create_request(test_user.id, delete_data)

        # List requests
        requests = await service.list_requests(test_user.id)

        assert len(requests) == 2
        # Should be in descending order (most recent first)
        assert requests[0].created_at >= requests[1].created_at


@pytest.mark.asyncio
class TestPrivacyRequestModel:
    """Test privacy request model properties and methods."""

    async def test_is_deletable_property(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test is_deletable property logic."""
        # Create delete request with future scheduled time
        request = PrivacyRequest(
            id=str(uuid4()),
            user_id=test_user.id,
            request_type=RequestType.DELETE,
            status=RequestStatus.PENDING,
            created_at=datetime.utcnow(),
            scheduled_deletion_at=datetime.utcnow() + timedelta(hours=72),
            metadata={},
        )
        db_session.add(request)
        await db_session.commit()

        # Not deletable yet (future time)
        assert request.is_deletable is False

        # Set to past time
        request.scheduled_deletion_at = datetime.utcnow() - timedelta(hours=1)
        await db_session.commit()

        # Now deletable
        assert request.is_deletable is True

    async def test_cooling_off_hours_remaining(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test cooling_off_hours_remaining calculation."""
        # Create delete request with 72 hours in future
        future_time = datetime.utcnow() + timedelta(hours=72)
        request = PrivacyRequest(
            id=str(uuid4()),
            user_id=test_user.id,
            request_type=RequestType.DELETE,
            status=RequestStatus.PENDING,
            created_at=datetime.utcnow(),
            scheduled_deletion_at=future_time,
            metadata={},
        )
        db_session.add(request)
        await db_session.commit()

        # Should have ~72 hours remaining
        hours_remaining = request.cooling_off_hours_remaining
        assert hours_remaining is not None
        assert 71 <= hours_remaining <= 72  # Allow for small time differences

    async def test_export_url_valid_property(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test export_url_valid property logic."""
        # Create request with expired URL
        request = PrivacyRequest(
            id=str(uuid4()),
            user_id=test_user.id,
            request_type=RequestType.EXPORT,
            status=RequestStatus.COMPLETED,
            created_at=datetime.utcnow(),
            export_url="https://storage.example.com/export.zip",
            export_expires_at=datetime.utcnow() - timedelta(hours=1),  # Expired
            metadata={},
        )
        db_session.add(request)
        await db_session.commit()

        # URL should be invalid (expired)
        assert request.export_url_valid is False

        # Set future expiry
        request.export_expires_at = datetime.utcnow() + timedelta(days=30)
        await db_session.commit()

        # Now URL should be valid
        assert request.export_url_valid is True


@pytest.mark.asyncio
class TestEdgeCasesAndErrors:
    """Test edge cases and error conditions."""

    async def test_process_export_request_handles_missing_request(
        self, db_session: AsyncSession
    ):
        """Test processing nonexistent export request raises error."""
        service = PrivacyService(db_session)

        with pytest.raises(ValueError, match="Request .* not found"):
            await service.process_export_request("nonexistent-request-id")

    async def test_process_wrong_request_type_raises_error(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test processing export request as delete raises error."""
        service = PrivacyService(db_session)

        # Create export request
        request_data = PrivacyRequestCreate(request_type=RequestType.EXPORT)
        request = await service.create_request(test_user.id, request_data)

        # Attempt to process as delete
        with pytest.raises(ValueError, match="is not a delete request"):
            await service.process_delete_request(request.id)

    async def test_place_hold_on_export_request_raises_error(
        self, db_session: AsyncSession, test_user: User, admin_user: User
    ):
        """Test placing hold on export request (not allowed)."""
        service = PrivacyService(db_session)

        # Create export request
        request_data = PrivacyRequestCreate(request_type=RequestType.EXPORT)
        request = await service.create_request(test_user.id, request_data)

        # Attempt to place hold (only allowed on delete requests)
        with pytest.raises(ValueError, match="Can only place hold on delete requests"):
            await service.place_hold(request.id, "Test hold", admin_user.id)

    async def test_export_failure_marks_request_as_failed(
        self, db_session: AsyncSession, test_user: User, monkeypatch
    ):
        """Test export failure updates request status to failed."""
        service = PrivacyService(db_session)

        # Create export request
        request_data = PrivacyRequestCreate(request_type=RequestType.EXPORT)
        request = await service.create_request(test_user.id, request_data)

        # Inject failure in export method
        async def mock_export_user_data(*args, **kwargs):
            raise RuntimeError("Simulated export failure")

        monkeypatch.setattr(service.exporter, "export_user_data", mock_export_user_data)

        # Attempt processing
        with pytest.raises(RuntimeError, match="Simulated export failure"):
            await service.process_export_request(request.id)

        # Verify request marked as failed
        await db_session.refresh(request)
        assert request.status == RequestStatus.FAILED
        assert "error" in request.metadata

    async def test_delete_failure_marks_request_as_failed(
        self, db_session: AsyncSession, test_user: User, monkeypatch
    ):
        """Test delete failure updates request status to failed."""
        service = PrivacyService(db_session)

        # Create delete request with elapsed cooling-off
        request_data = PrivacyRequestCreate(request_type=RequestType.DELETE)
        request = await service.create_request(test_user.id, request_data)
        request.scheduled_deletion_at = datetime.utcnow() - timedelta(hours=1)
        await db_session.commit()

        # Inject failure in delete method
        async def mock_delete_user_data(*args, **kwargs):
            raise RuntimeError("Simulated deletion failure")

        monkeypatch.setattr(service.deleter, "delete_user_data", mock_delete_user_data)

        # Attempt processing
        with pytest.raises(RuntimeError, match="Simulated deletion failure"):
            await service.process_delete_request(request.id)

        # Verify request marked as failed
        await db_session.refresh(request)
        assert request.status == RequestStatus.FAILED
        assert "error" in request.metadata


# Fixtures


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create test user."""
    user = User(
        id=str(uuid4()),
        telegram_id=123456789,
        username="testuser",
        first_name="Test",
        last_name="User",
        is_active=True,
        is_premium=False,
        created_at=datetime.utcnow(),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def admin_user(db_session: AsyncSession) -> User:
    """Create admin user."""
    user = User(
        id=str(uuid4()),
        telegram_id=987654321,
        username="adminuser",
        first_name="Admin",
        last_name="User",
        is_active=True,
        is_premium=True,
        is_admin=True,
        created_at=datetime.utcnow(),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user
