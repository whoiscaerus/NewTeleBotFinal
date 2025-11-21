"""
Integration tests for EA Ack Position Tracking (PR-104 Phase 3).

Tests verify that when EA acknowledges successful trade execution:
1. OpenPosition record is created with all required fields
2. Hidden owner_sl and owner_tp are extracted from Signal.owner_only
3. Position is NOT created for failed executions
4. All foreign keys are correctly linked
5. Fallback behavior when owner_only is missing
"""

from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.approvals.models import Approval, ApprovalDecision
from backend.app.auth.models import User
from backend.app.clients.devices.models import Device
from backend.app.ea.models import Execution, ExecutionStatus
from backend.app.signals.encryption import encrypt_owner_only
from backend.app.signals.models import Signal
from backend.app.trading.positions.models import OpenPosition, PositionStatus


@pytest.mark.asyncio
async def test_ack_successful_placement_creates_open_position(
    client, db_session: AsyncSession, test_user, test_device
):
    """Test: EA ack with status=placed creates OpenPosition with hidden levels."""

    # Create signal with owner_only (hidden SL/TP)
    owner_data = {
        "stop_loss": 2645.50,
        "take_profit": 2670.00,
        "strategy": "breakout",
    }
    encrypted_owner_only = encrypt_owner_only(owner_data)

    signal = Signal(
        id=str(uuid4()),
        user_id=test_user.id,
        instrument="XAUUSD",
        side=0,  # buy
        price=2655.50,
        status=0,
        payload={
            "instrument": "XAUUSD",
            "entry_price": 2655.50,
            "volume": 0.1,
        },
        owner_only=encrypted_owner_only,
    )
    db_session.add(signal)
    await db_session.flush()

    # Create approval
    approval = Approval(
        id=str(uuid4()),
        signal_id=signal.id,
        user_id=test_user.id,
        decision=ApprovalDecision.APPROVED.value,
        client_id=test_device.client_id,
    )
    db_session.add(approval)

    await db_session.commit()

    # Action: EA acknowledges successful placement
    ack_payload = {
        "approval_id": approval.id,
        "status": "placed",
        "broker_ticket": "MT5_987654321",
        "error": None,
    }

    response = await client.post(
        "/api/v1/client/ack",
        json=ack_payload,
        headers={
            "X-Device-Id": test_device.id,
            "X-Nonce": "test_nonce_" + str(uuid4()),
            "X-Timestamp": datetime.utcnow().isoformat() + "Z",
            "X-Signature": "mock_signature",
        },
    )

    # Verify: Response is successful
    if response.status_code != 201:
        print(f"Response status: {response.status_code}")
        print(f"Response body: {response.text}")
    assert response.status_code == 201
    data = response.json()
    assert data["approval_id"] == approval.id
    assert data["status"] == "placed"

    # Verify: OpenPosition was created
    position_stmt = select(OpenPosition).where(OpenPosition.approval_id == approval.id)
    position_result = await db_session.execute(position_stmt)
    position = position_result.scalar_one_or_none()

    assert (
        position is not None
    ), "OpenPosition should be created for successful placement"

    # Verify: All foreign keys are correct
    assert position.signal_id == signal.id
    assert position.approval_id == approval.id
    assert position.user_id == test_user.id
    assert position.device_id == test_device.id

    # Verify: Trade details are correct
    assert position.instrument == "XAUUSD"
    assert position.side == 0  # buy
    assert position.entry_price == 2655.50
    assert position.volume == 0.1
    assert position.broker_ticket == "MT5_987654321"

    # Verify: Hidden levels are extracted from owner_only
    assert position.owner_sl == 2645.50, "owner_sl should be decrypted from owner_only"
    assert position.owner_tp == 2670.00, "owner_tp should be decrypted from owner_only"

    # Verify: Position status is OPEN
    assert position.status == PositionStatus.OPEN.value
    assert position.opened_at is not None
    assert position.closed_at is None


@pytest.mark.asyncio
async def test_ack_failed_execution_does_not_create_position(
    client, db_session: AsyncSession, test_user, test_device
):
    """Test: EA ack with status=failed does NOT create OpenPosition."""

    # Setup: Create user, device, signal, approval
    user = User(
        id=str(uuid4()),
        email="test_user_2@example.com",
        password_hash="hashed_password",
    )
    db_session.add(user)
    await db_session.flush()

    # Create Client for the device
    from backend.app.clients.models import Client

    client_obj = Client(id=str(uuid4()), email=user.email, telegram_id=None)
    db_session.add(client_obj)
    await db_session.flush()

    device = Device(
        id=str(uuid4()),
        client_id=client_obj.id,
        device_name="TestDevice2",
        hmac_key_hash="test_hmac_key_hash_67890",
    )
    db_session.add(device)
    await db_session.flush()

    signal = Signal(
        id=str(uuid4()),
        user_id=user.id,
        instrument="EURUSD",
        side=1,  # sell
        price=1.0850,
        payload={
            "instrument": "EURUSD",
            "entry_price": 1.0850,
            "volume": 0.5,
        },
    )
    db_session.add(signal)
    await db_session.flush()

    approval = Approval(
        id=str(uuid4()),
        signal_id=signal.id,
        user_id=user.id,
        decision=ApprovalDecision.APPROVED.value,
        client_id=device.client_id,
    )
    db_session.add(approval)

    await db_session.commit()

    # Action: EA acknowledges FAILED execution
    ack_payload = {
        "approval_id": approval.id,
        "status": "failed",
        "broker_ticket": None,
        "error": "Insufficient margin",
    }

    response = await client.post(
        "/api/v1/client/ack",
        json=ack_payload,
        headers={
            "X-Device-Id": device.id,
            "X-Nonce": "test_nonce_" + str(uuid4()),
            "X-Timestamp": datetime.utcnow().isoformat() + "Z",
            "X-Signature": "mock_signature",
        },
    )

    # Verify: Response is successful
    assert response.status_code == 201
    assert response.json()["status"] == "failed"

    # Verify: NO OpenPosition was created
    position_stmt = select(OpenPosition).where(OpenPosition.approval_id == approval.id)
    position_result = await db_session.execute(position_stmt)
    position = position_result.scalar_one_or_none()

    assert position is None, "OpenPosition should NOT be created for failed execution"

    # Verify: Execution record still created
    execution_stmt = select(Execution).where(Execution.approval_id == approval.id)
    execution_result = await db_session.execute(execution_stmt)
    execution = execution_result.scalar_one_or_none()

    assert execution is not None
    assert execution.status == ExecutionStatus.FAILED.value


@pytest.mark.asyncio
async def test_ack_without_owner_only_still_creates_position(
    client, db_session: AsyncSession, test_user, test_device
):
    """Test: Signal without owner_only still creates OpenPosition (fallback)."""

    # Setup: Create signal WITHOUT owner_only
    user = test_user
    device = test_device

    signal = Signal(
        id=str(uuid4()),
        user_id=user.id,
        instrument="GBPUSD",
        side=0,  # buy
        price=1.2650,
        payload={
            "instrument": "GBPUSD",
            "entry_price": 1.2650,
            "volume": 0.2,
        },
        owner_only=None,  # No hidden levels
    )
    db_session.add(signal)
    await db_session.flush()

    approval = Approval(
        id=str(uuid4()),
        signal_id=signal.id,
        user_id=user.id,
        decision=ApprovalDecision.APPROVED.value,
        client_id=test_device.client_id,
    )
    db_session.add(approval)

    await db_session.commit()

    # Action: EA acknowledges successful placement
    ack_payload = {
        "approval_id": approval.id,
        "status": "placed",
        "broker_ticket": "MT5_111222333",
        "error": None,
    }

    response = await client.post(
        "/api/v1/client/ack",
        json=ack_payload,
        headers={
            "X-Device-Id": device.id,
            "X-Nonce": "test_nonce_" + str(uuid4()),
            "X-Timestamp": datetime.utcnow().isoformat() + "Z",
            "X-Signature": "mock_signature",
        },
    )

    # Verify: Response is successful
    assert response.status_code == 201

    # Verify: OpenPosition still created (without hidden levels)
    position_stmt = select(OpenPosition).where(OpenPosition.approval_id == approval.id)
    position_result = await db_session.execute(position_stmt)
    position = position_result.scalar_one_or_none()

    assert (
        position is not None
    ), "OpenPosition should be created even without owner_only"

    # Verify: Hidden levels are None (fallback)
    assert position.owner_sl is None, "owner_sl should be None when no owner_only"
    assert position.owner_tp is None, "owner_tp should be None when no owner_only"

    # Verify: Other fields are correct
    assert position.instrument == "GBPUSD"
    assert position.entry_price == 1.2650
    assert position.status == PositionStatus.OPEN.value


@pytest.mark.asyncio
async def test_ack_with_corrupt_owner_only_creates_position_without_levels(
    client, db_session: AsyncSession, test_user, test_device
):
    """Test: Signal with corrupt owner_only still creates position (graceful degradation)."""

    # Setup: Create signal with CORRUPT owner_only
    user = test_user
    device = test_device

    signal = Signal(
        id=str(uuid4()),
        user_id=user.id,
        instrument="USDJPY",
        side=1,  # sell
        price=149.50,
        payload={
            "instrument": "USDJPY",
            "entry_price": 149.50,
            "volume": 0.3,
        },
        owner_only="CORRUPT_ENCRYPTED_DATA_INVALID",  # Invalid encryption
    )
    db_session.add(signal)
    await db_session.flush()

    approval = Approval(
        id=str(uuid4()),
        signal_id=signal.id,
        user_id=user.id,
        decision=ApprovalDecision.APPROVED.value,
        client_id=test_device.client_id,
    )
    db_session.add(approval)

    await db_session.commit()

    # Action: EA acknowledges successful placement
    ack_payload = {
        "approval_id": approval.id,
        "status": "placed",
        "broker_ticket": "MT5_444555666",
        "error": None,
    }

    response = await client.post(
        "/api/v1/client/ack",
        json=ack_payload,
        headers={
            "X-Device-Id": device.id,
            "X-Nonce": "test_nonce_" + str(uuid4()),
            "X-Timestamp": datetime.utcnow().isoformat() + "Z",
            "X-Signature": "mock_signature",
        },
    )

    # Verify: Response is STILL successful (graceful degradation)
    assert response.status_code == 201

    # Verify: OpenPosition created despite decryption failure
    position_stmt = select(OpenPosition).where(OpenPosition.approval_id == approval.id)
    position_result = await db_session.execute(position_stmt)
    position = position_result.scalar_one_or_none()

    assert position is not None, "Position should be created even if decryption fails"

    # Verify: Hidden levels are None (decryption failed)
    assert position.owner_sl is None
    assert position.owner_tp is None

    # Verify: Trade still tracked
    assert position.instrument == "USDJPY"
    assert position.entry_price == 149.50
    assert position.status == PositionStatus.OPEN.value


@pytest.mark.asyncio
async def test_ack_all_foreign_keys_linked_correctly(
    client, db_session: AsyncSession, test_user, test_device
):
    """Test: Verify all foreign keys in OpenPosition are correctly linked."""

    # Setup: Create complete relationship chain
    user = test_user
    device = test_device

    signal = Signal(
        id=str(uuid4()),
        user_id=user.id,
        instrument="BTCUSD",
        side=0,
        price=45000.00,
        payload={"instrument": "BTCUSD", "entry_price": 45000.00, "volume": 0.01},
    )
    db_session.add(signal)
    await db_session.flush()

    approval = Approval(
        id=str(uuid4()),
        signal_id=signal.id,
        user_id=user.id,
        decision=ApprovalDecision.APPROVED.value,
        client_id=test_device.client_id,
    )
    db_session.add(approval)

    await db_session.commit()

    # Action: EA acknowledges
    ack_payload = {
        "approval_id": approval.id,
        "status": "placed",
        "broker_ticket": "MT5_777888999",
        "error": None,
    }

    response = await client.post(
        "/api/v1/client/ack",
        json=ack_payload,
        headers={
            "X-Device-Id": device.id,
            "X-Nonce": "test_nonce_" + str(uuid4()),
            "X-Timestamp": datetime.utcnow().isoformat() + "Z",
            "X-Signature": "mock_signature",
        },
    )

    assert response.status_code == 201

    # Verify: Load OpenPosition with relationships
    position_stmt = select(OpenPosition).where(OpenPosition.approval_id == approval.id)
    position_result = await db_session.execute(position_stmt)
    position = position_result.scalar_one_or_none()

    assert position is not None

    # Verify: All IDs match the relationship chain
    assert position.signal_id == signal.id
    assert position.approval_id == approval.id
    assert position.user_id == user.id
    assert position.device_id == device.id

    # Verify: Execution ID is valid (execution was created)
    assert position.execution_id is not None

    execution_stmt = select(Execution).where(Execution.id == position.execution_id)
    execution_result = await db_session.execute(execution_stmt)
    execution = execution_result.scalar_one_or_none()

    assert execution is not None
    assert execution.approval_id == approval.id
    assert execution.status == ExecutionStatus.PLACED.value


@pytest.mark.asyncio
async def test_ack_position_opened_at_timestamp(
    client, db_session: AsyncSession, test_user, test_device
):
    """Test: Verify opened_at timestamp is set correctly."""

    # Setup
    user = test_user
    device = test_device

    signal = Signal(
        id=str(uuid4()),
        user_id=user.id,
        instrument="AUDCAD",
        side=1,
        price=0.9050,
        payload={"instrument": "AUDCAD", "entry_price": 0.9050, "volume": 0.5},
    )
    db_session.add(signal)
    await db_session.flush()

    approval = Approval(
        id=str(uuid4()),
        signal_id=signal.id,
        user_id=user.id,
        decision=ApprovalDecision.APPROVED.value,
        client_id=test_device.client_id,
    )
    db_session.add(approval)

    await db_session.commit()

    # Capture time before ack
    before_ack = datetime.utcnow()

    # Action: EA acknowledges
    ack_payload = {
        "approval_id": approval.id,
        "status": "placed",
        "broker_ticket": "MT5_123123123",
        "error": None,
    }

    response = await client.post(
        "/api/v1/client/ack",
        json=ack_payload,
        headers={
            "X-Device-Id": device.id,
            "X-Nonce": "test_nonce_" + str(uuid4()),
            "X-Timestamp": datetime.utcnow().isoformat() + "Z",
            "X-Signature": "mock_signature",
        },
    )

    assert response.status_code == 201

    # Capture time after ack
    after_ack = datetime.utcnow()

    # Verify: Position opened_at is within window
    position_stmt = select(OpenPosition).where(OpenPosition.approval_id == approval.id)
    position_result = await db_session.execute(position_stmt)
    position = position_result.scalar_one_or_none()

    assert position is not None
    assert position.opened_at is not None
    assert before_ack <= position.opened_at <= after_ack
    assert position.closed_at is None  # Not closed yet


@pytest.mark.asyncio
async def test_ack_position_broker_ticket_stored(
    client, db_session: AsyncSession, test_user, test_device
):
    """Test: Verify broker_ticket from ack is stored in OpenPosition."""

    # Setup
    user = test_user
    device = test_device

    signal = Signal(
        id=str(uuid4()),
        user_id=user.id,
        instrument="NZDUSD",
        side=0,
        price=0.6150,
        payload={"instrument": "NZDUSD", "entry_price": 0.6150, "volume": 1.0},
    )
    db_session.add(signal)
    await db_session.flush()

    approval = Approval(
        id=str(uuid4()),
        signal_id=signal.id,
        user_id=user.id,
        decision=ApprovalDecision.APPROVED.value,
        client_id=test_device.client_id,
    )
    db_session.add(approval)

    await db_session.commit()

    # Action: EA acknowledges with specific broker ticket
    broker_ticket = "MT5_SPECIAL_TICKET_999"
    ack_payload = {
        "approval_id": approval.id,
        "status": "placed",
        "broker_ticket": broker_ticket,
        "error": None,
    }

    response = await client.post(
        "/api/v1/client/ack",
        json=ack_payload,
        headers={
            "X-Device-Id": device.id,
            "X-Nonce": "test_nonce_" + str(uuid4()),
            "X-Timestamp": datetime.utcnow().isoformat() + "Z",
            "X-Signature": "mock_signature",
        },
    )

    assert response.status_code == 201

    # Verify: Broker ticket stored correctly
    position_stmt = select(OpenPosition).where(OpenPosition.approval_id == approval.id)
    position_result = await db_session.execute(position_stmt)
    position = position_result.scalar_one_or_none()

    assert position is not None
    assert position.broker_ticket == broker_ticket
