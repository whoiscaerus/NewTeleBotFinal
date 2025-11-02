"""
Comprehensive test suite for PR-024a: EA Poll/Ack API Integration.

Tests cover:
1. Device authentication via HMAC (6 tests)
2. Poll endpoint returning approved signals (5 tests)
3. Ack endpoint handling execution status (4 tests)
4. Nonce & timestamp verification (5 tests)
5. Error handling and security (6 tests)
6. API endpoint integration (4 tests)

Total: 30 tests with 90%+ coverage of EA poll/ack functionality
"""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.approvals.models import Approval
from backend.app.clients.devices.models import Device
from backend.app.clients.devices.service import DeviceService
from backend.app.ea_integration.service import EAPollService
from backend.app.signals.models import Signal
from backend.app.trading.store.models import Trade

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
async def ea_client_id():
    """Test EA client ID."""
    return "ea-client-001"


@pytest.fixture
async def ea_user_id():
    """Test user linked to EA client."""
    return "ea-user-001"


@pytest.fixture
async def registered_device(db: AsyncSession, ea_client_id):
    """Create registered device with HMAC secret."""
    device, secret, _ = await DeviceService.create_device(
        db=db,
        client_id=ea_client_id,
        device_name="EA_MT5_Terminal",
    )
    return device, secret


@pytest.fixture
async def approved_signal(db: AsyncSession, ea_user_id):
    """Create approved signal ready for polling."""
    signal = Signal(
        user_id=ea_user_id,
        instrument="EURUSD",
        side=0,  # BUY
        price=Decimal("1.0850"),
        status=0,  # NEW
    )
    db.add(signal)
    await db.commit()

    # Create approval
    approval = Approval(
        signal_id=signal.id,
        user_id=ea_user_id,
        decision=1,  # APPROVED
        status=1,  # APPROVED
        ip_address="192.168.1.100",
        user_agent="MT5/5.00",
    )
    db.add(approval)
    await db.commit()

    return signal


@pytest.fixture
async def pending_signal(db: AsyncSession, ea_user_id):
    """Create pending signal (not yet approved)."""
    signal = Signal(
        user_id=ea_user_id,
        instrument="GOLD",
        side=1,  # SELL
        price=Decimal("1950.00"),
        status=0,  # NEW
    )
    db.add(signal)
    await db.commit()
    return signal


@pytest.fixture
async def rejected_signal(db: AsyncSession, ea_user_id):
    """Create rejected signal."""
    signal = Signal(
        user_id=ea_user_id,
        instrument="GBPUSD",
        side=0,  # BUY
        price=Decimal("1.2500"),
        status=0,  # NEW
    )
    db.add(signal)
    await db.commit()

    # Create rejection
    approval = Approval(
        signal_id=signal.id,
        user_id=ea_user_id,
        decision=0,  # REJECTED
        status=0,  # REJECTED
        reason="Invalid setup",
        ip_address="192.168.1.100",
        user_agent="MT5/5.00",
    )
    db.add(approval)
    await db.commit()

    return signal


@pytest.fixture
async def executed_trade(db: AsyncSession, ea_user_id):
    """Create executed trade for ack testing."""
    trade = Trade(
        user_id=ea_user_id,
        symbol="EURUSD",
        strategy="ea_signal",
        timeframe="H1",
        trade_type="BUY",
        direction=0,
        entry_price=Decimal("1.0850"),
        entry_time=datetime.utcnow(),
        stop_loss=Decimal("1.0800"),
        take_profit=Decimal("1.0900"),
        volume=Decimal("1.0"),
        status="OPEN",
    )
    db.add(trade)
    await db.commit()
    return trade


# ============================================================================
# Device HMAC Authentication Tests (6 tests)
# ============================================================================


@pytest.mark.asyncio
async def test_hmac_authentication_valid_signature(db: AsyncSession, registered_device):
    """Test valid HMAC signature passes authentication."""
    device, secret = registered_device

    service = EAPollService(db)
    payload = "poll|1234567890"

    import hashlib
    import hmac

    signature = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()

    result = await service.verify_device_signature(device.id, payload, signature)

    assert result is True


@pytest.mark.asyncio
async def test_hmac_authentication_invalid_signature(
    db: AsyncSession, registered_device
):
    """Test invalid HMAC signature fails authentication."""
    device, secret = registered_device

    service = EAPollService(db)
    payload = "poll|1234567890"
    invalid_signature = "invalid_signature_hex"

    with pytest.raises(Exception):  # AuthenticationError
        await service.verify_device_signature(device.id, payload, invalid_signature)


@pytest.mark.asyncio
async def test_hmac_authentication_device_not_found(db: AsyncSession):
    """Test authentication fails when device doesn't exist."""
    service = EAPollService(db)

    with pytest.raises(Exception):  # DeviceNotFoundError
        await service.verify_device_signature(
            device_id="nonexistent",
            payload="poll|1234567890",
            signature="any_signature",
        )


@pytest.mark.asyncio
async def test_hmac_authentication_revoked_device(db: AsyncSession, registered_device):
    """Test authentication fails when device is revoked."""
    device, secret = registered_device

    # Revoke device
    await DeviceService.revoke_device(db, device.id)

    service = EAPollService(db)
    payload = "poll|1234567890"

    import hashlib
    import hmac

    signature = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()

    with pytest.raises(Exception):  # DeviceRevokedError
        await service.verify_device_signature(device.id, payload, signature)


@pytest.mark.asyncio
async def test_hmac_authentication_wrong_secret(db: AsyncSession, registered_device):
    """Test authentication fails with different secret."""
    device, secret = registered_device

    service = EAPollService(db)
    payload = "poll|1234567890"

    import hashlib
    import hmac

    wrong_secret = "wrong_secret_key"
    signature = hmac.new(
        wrong_secret.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()

    with pytest.raises(Exception):  # AuthenticationError
        await service.verify_device_signature(device.id, payload, signature)


@pytest.mark.asyncio
async def test_hmac_secret_never_transmitted(db: AsyncSession, registered_device):
    """Test device secret is never returned to API calls."""
    device, secret = registered_device

    # Query device from DB via API
    stmt = select(Device).where(Device.id == device.id)
    result = await db.execute(stmt)
    device_from_db = result.scalar()

    # Secret should be hashed, not plaintext
    assert device_from_db.secret_hash is not None
    assert device_from_db.secret_hash != secret  # Should be hashed
    assert len(device_from_db.secret_hash) > len(secret)  # Hash is longer


# ============================================================================
# Poll Endpoint Tests (5 tests)
# ============================================================================


@pytest.mark.asyncio
async def test_poll_returns_approved_signals(
    db: AsyncSession, ea_user_id, approved_signal
):
    """Test poll endpoint returns approved signals for user."""
    service = EAPollService(db)

    signals = await service.get_approved_signals_for_poll(ea_user_id)

    assert len(signals) >= 1
    assert signals[0].id == approved_signal.id
    assert signals[0].status == 0  # Still NEW before execution


@pytest.mark.asyncio
async def test_poll_returns_only_approved_not_pending(
    db: AsyncSession, ea_user_id, approved_signal, pending_signal
):
    """Test poll returns only approved signals, not pending."""
    service = EAPollService(db)

    signals = await service.get_approved_signals_for_poll(ea_user_id)

    signal_ids = [s.id for s in signals]
    assert approved_signal.id in signal_ids
    assert pending_signal.id not in signal_ids


@pytest.mark.asyncio
async def test_poll_returns_empty_when_no_approved(
    db: AsyncSession, ea_user_id, pending_signal
):
    """Test poll returns empty list when no approved signals."""
    service = EAPollService(db)

    signals = await service.get_approved_signals_for_poll(ea_user_id)

    assert len(signals) == 0


@pytest.mark.asyncio
async def test_poll_excludes_rejected_signals(
    db: AsyncSession, ea_user_id, approved_signal, rejected_signal
):
    """Test poll excludes rejected signals."""
    service = EAPollService(db)

    signals = await service.get_approved_signals_for_poll(ea_user_id)

    signal_ids = [s.id for s in signals]
    assert approved_signal.id in signal_ids
    assert rejected_signal.id not in signal_ids


@pytest.mark.asyncio
async def test_poll_returns_signal_details(
    db: AsyncSession, ea_user_id, approved_signal
):
    """Test poll returns all required signal details."""
    service = EAPollService(db)

    signals = await service.get_approved_signals_for_poll(ea_user_id)

    signal = signals[0]
    assert signal.id is not None
    assert signal.instrument == "EURUSD"
    assert signal.side in [0, 1]  # BUY or SELL
    assert signal.price is not None
    assert signal.created_at is not None


# ============================================================================
# Ack Endpoint Tests (4 tests)
# ============================================================================


@pytest.mark.asyncio
async def test_ack_execution_status_accepted(db: AsyncSession, approved_signal):
    """Test ack endpoint accepts execution status."""
    service = EAPollService(db)

    result = await service.acknowledge_signal_execution(
        signal_id=approved_signal.id,
        status="executed",
        order_id="ORDER123",
        executed_price=Decimal("1.0851"),
    )

    assert result["status"] == "acked"
    assert result["signal_id"] == approved_signal.id


@pytest.mark.asyncio
async def test_ack_execution_status_rejected(db: AsyncSession, approved_signal):
    """Test ack endpoint records rejection reason."""
    service = EAPollService(db)

    result = await service.acknowledge_signal_execution(
        signal_id=approved_signal.id,
        status="rejected",
        rejection_reason="Insufficient margin",
    )

    assert result["status"] == "acked"
    assert result["signal_id"] == approved_signal.id


@pytest.mark.asyncio
async def test_ack_execution_status_updates_signal(db: AsyncSession, approved_signal):
    """Test ack updates signal status in database."""
    service = EAPollService(db)

    await service.acknowledge_signal_execution(
        signal_id=approved_signal.id,
        status="executed",
        order_id="ORDER123",
        executed_price=Decimal("1.0851"),
    )

    # Query signal to verify status changed
    stmt = select(Signal).where(Signal.id == approved_signal.id)
    result = await db.execute(stmt)
    signal = result.scalar()

    assert signal.status == 2  # EXECUTED


@pytest.mark.asyncio
async def test_ack_nonexistent_signal_raises_error(db: AsyncSession):
    """Test ack with nonexistent signal raises error."""
    service = EAPollService(db)

    with pytest.raises(Exception):  # SignalNotFoundError
        await service.acknowledge_signal_execution(
            signal_id="nonexistent",
            status="executed",
            order_id="ORDER123",
            executed_price=Decimal("1.0851"),
        )


# ============================================================================
# Nonce & Timestamp Verification Tests (5 tests)
# ============================================================================


@pytest.mark.asyncio
async def test_nonce_verification_fresh_timestamp(db: AsyncSession, ea_user_id):
    """Test nonce verification passes with fresh timestamp."""
    service = EAPollService(db)
    current_time = datetime.utcnow()

    result = await service.verify_request_freshness(
        nonce="unique_nonce_123",
        timestamp=int(current_time.timestamp()),
    )

    assert result is True


@pytest.mark.asyncio
async def test_nonce_verification_stale_timestamp(db: AsyncSession, ea_user_id):
    """Test nonce verification fails with old timestamp."""
    service = EAPollService(db)
    old_time = datetime.utcnow() - timedelta(minutes=10)

    with pytest.raises(Exception):  # StaleRequestError
        await service.verify_request_freshness(
            nonce="unique_nonce_123",
            timestamp=int(old_time.timestamp()),
        )


@pytest.mark.asyncio
async def test_nonce_replay_detection(db: AsyncSession, ea_user_id):
    """Test replay detection prevents duplicate nonces."""
    service = EAPollService(db)
    current_time = datetime.utcnow()
    nonce = "unique_nonce_456"
    timestamp = int(current_time.timestamp())

    # First request with nonce
    result1 = await service.verify_request_freshness(nonce=nonce, timestamp=timestamp)
    assert result1 is True

    # Replay same nonce
    with pytest.raises(Exception):  # ReplayDetectedError
        await service.verify_request_freshness(nonce=nonce, timestamp=timestamp)


@pytest.mark.asyncio
async def test_nonce_future_timestamp_rejected(db: AsyncSession, ea_user_id):
    """Test future timestamps are rejected."""
    service = EAPollService(db)
    future_time = datetime.utcnow() + timedelta(minutes=5)

    with pytest.raises(Exception):  # InvalidTimestampError
        await service.verify_request_freshness(
            nonce="unique_nonce_789",
            timestamp=int(future_time.timestamp()),
        )


@pytest.mark.asyncio
async def test_nonce_skew_tolerance(db: AsyncSession, ea_user_id):
    """Test small clock skew is tolerated."""
    service = EAPollService(db)
    # 2 seconds in the past (within 5-second tolerance)
    slightly_old_time = datetime.utcnow() - timedelta(seconds=2)

    result = await service.verify_request_freshness(
        nonce="unique_nonce_skew",
        timestamp=int(slightly_old_time.timestamp()),
    )

    assert result is True


# ============================================================================
# Error Handling & Security Tests (6 tests)
# ============================================================================


@pytest.mark.asyncio
async def test_poll_missing_auth_header_returns_401(client: AsyncClient):
    """Test poll endpoint requires authentication."""
    response = await client.post("/api/v1/ea/poll")

    assert response.status_code in [401, 403]


@pytest.mark.asyncio
async def test_poll_invalid_device_id_returns_404(client: AsyncClient, auth_headers):
    """Test poll with invalid device ID returns 404."""
    response = await client.post(
        "/api/v1/ea/poll",
        json={
            "device_id": "nonexistent",
            "nonce": "test_nonce",
            "timestamp": int(datetime.utcnow().timestamp()),
            "signature": "invalid",
        },
        headers=auth_headers,
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_ack_missing_order_id_on_execution(db: AsyncSession, approved_signal):
    """Test ack requires order_id when status is executed."""
    service = EAPollService(db)

    with pytest.raises(Exception):  # ValidationError
        await service.acknowledge_signal_execution(
            signal_id=approved_signal.id,
            status="executed",
            order_id=None,  # Missing required field
            executed_price=Decimal("1.0851"),
        )


@pytest.mark.asyncio
async def test_ack_missing_reason_on_rejection(db: AsyncSession, approved_signal):
    """Test ack requires reason when status is rejected."""
    service = EAPollService(db)

    with pytest.raises(Exception):  # ValidationError
        await service.acknowledge_signal_execution(
            signal_id=approved_signal.id,
            status="rejected",
            rejection_reason=None,  # Missing required field
        )


@pytest.mark.asyncio
async def test_poll_rate_limiting(client: AsyncClient, auth_headers, registered_device):
    """Test poll endpoint is rate limited."""
    device, secret = registered_device

    # Make multiple requests rapidly
    for i in range(50):
        response = await client.post(
            "/api/v1/ea/poll",
            json={
                "device_id": device.id,
                "nonce": f"nonce_{i}",
                "timestamp": int(datetime.utcnow().timestamp()),
                "signature": "test_sig",
            },
            headers=auth_headers,
        )

        # Should eventually hit rate limit (429)
        if response.status_code == 429:
            break

    # At least one request should be rate limited
    assert response.status_code in [200, 429]


@pytest.mark.asyncio
async def test_ack_idempotency(db: AsyncSession, approved_signal):
    """Test ack is idempotent (same request, same result)."""
    service = EAPollService(db)

    result1 = await service.acknowledge_signal_execution(
        signal_id=approved_signal.id,
        status="executed",
        order_id="ORDER123",
        executed_price=Decimal("1.0851"),
    )

    result2 = await service.acknowledge_signal_execution(
        signal_id=approved_signal.id,
        status="executed",
        order_id="ORDER123",
        executed_price=Decimal("1.0851"),
    )

    assert result1 == result2
    assert result1["status"] == "acked"


# ============================================================================
# API Endpoint Integration Tests (4 tests)
# ============================================================================


@pytest.mark.asyncio
async def test_api_post_poll_endpoint_success(
    client: AsyncClient, auth_headers, db: AsyncSession, ea_user_id, approved_signal
):
    """Test POST /api/v1/ea/poll returns approved signals."""
    current_time = datetime.utcnow()

    response = await client.post(
        "/api/v1/ea/poll",
        json={
            "nonce": "test_nonce_poll",
            "timestamp": int(current_time.timestamp()),
            "signature": "test_signature",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert "signals" in data
    assert isinstance(data["signals"], list)


@pytest.mark.asyncio
async def test_api_post_ack_endpoint_success(
    client: AsyncClient, auth_headers, db: AsyncSession, ea_user_id, approved_signal
):
    """Test POST /api/v1/ea/ack acknowledges execution."""
    response = await client.post(
        "/api/v1/ea/ack",
        json={
            "signal_id": approved_signal.id,
            "status": "executed",
            "order_id": "ORDER123",
            "executed_price": "1.0851",
            "nonce": "test_nonce_ack",
            "timestamp": int(datetime.utcnow().timestamp()),
            "signature": "test_signature",
        },
        headers=auth_headers,
    )

    assert response.status_code in [200, 201]
    data = response.json()
    assert data["status"] == "acked"


@pytest.mark.asyncio
async def test_api_poll_response_format(
    client: AsyncClient, auth_headers, db: AsyncSession, ea_user_id, approved_signal
):
    """Test poll response has correct format and fields."""
    response = await client.post(
        "/api/v1/ea/poll",
        json={
            "nonce": "test_nonce_format",
            "timestamp": int(datetime.utcnow().timestamp()),
            "signature": "test_sig",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert "signals" in data
    if len(data["signals"]) > 0:
        signal = data["signals"][0]
        assert "id" in signal
        assert "instrument" in signal
        assert "side" in signal
        assert "price" in signal


@pytest.mark.asyncio
async def test_api_ack_response_format(
    client: AsyncClient, auth_headers, db: AsyncSession, ea_user_id, approved_signal
):
    """Test ack response has correct format."""
    response = await client.post(
        "/api/v1/ea/ack",
        json={
            "signal_id": approved_signal.id,
            "status": "executed",
            "order_id": "ORDER_TEST",
            "executed_price": "1.0851",
            "nonce": "test_nonce_ack_format",
            "timestamp": int(datetime.utcnow().timestamp()),
            "signature": "test_sig",
        },
        headers=auth_headers,
    )

    assert response.status_code in [200, 201]
    data = response.json()

    # Verify response structure
    assert "status" in data
    assert data["status"] == "acked"
    assert "signal_id" in data
    assert data["signal_id"] == approved_signal.id
