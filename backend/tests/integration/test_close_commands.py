"""Tests for Close Commands API (PR-104 Phase 5).

Tests the /close-commands poll endpoint and /close-ack endpoint
that enable server-initiated position closes.
"""

import json
from datetime import datetime
from uuid import uuid4

import pytest
import pytest_asyncio

from backend.app.auth.models import User
from backend.app.clients.devices.models import Device
from backend.app.clients.models import Client
from backend.app.ea.auth import HMACBuilder
from backend.app.trading.positions.close_commands import (
    CloseCommandStatus,
    create_close_command,
)
from backend.app.trading.positions.models import OpenPosition, PositionStatus


@pytest_asyncio.fixture
async def test_user(db_session):
    """Create a test user for tests."""
    user = User(
        id=str(uuid4()),
        email="test@example.com",
        password_hash="dummy_hash",
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest_asyncio.fixture
async def test_device(db_session, test_user):
    """Create a test device with HMAC key for tests."""
    # Create client first (Client is linked to User via email, not user_id)
    client = Client(
        id=str(uuid4()),
        email=test_user.email,
        telegram_id=None,
    )
    db_session.add(client)
    await db_session.flush()

    # Create device
    device = Device(
        id=str(uuid4()),
        client_id=client.id,
        device_name="Test MT5",
        hmac_key_hash="test_hmac_secret_key_12345",
    )
    db_session.add(device)
    await db_session.commit()
    return device


def generate_device_auth_headers(
    device: Device, method: str, path: str, body_dict: dict = None
) -> dict:
    """Generate HMAC authentication headers for EA endpoints."""
    nonce = str(uuid4())
    timestamp = datetime.utcnow().isoformat() + "Z"
    body_str = json.dumps(body_dict, separators=(",", ":")) if body_dict else ""

    canonical = HMACBuilder.build_canonical_string(
        method=method,
        path=path,
        body=body_str,
        device_id=device.id,
        nonce=nonce,
        timestamp=timestamp,
    )

    signature = HMACBuilder.sign(canonical, device.hmac_key_hash.encode())

    return {
        "X-Device-Id": device.id,
        "X-Nonce": nonce,
        "X-Timestamp": timestamp,
        "X-Signature": signature,
    }


@pytest.mark.asyncio
async def test_poll_close_commands_no_pending(
    client, db_session, test_user, test_device
):
    """Test polling when no close commands are pending.

    EA polls /close-commands → receives empty list.
    """
    # Poll for close commands (none pending)
    headers = generate_device_auth_headers(
        device=test_device,
        method="GET",
        path="/api/v1/client/close-commands",
        body_dict=None,
    )

    response = await client.get("/api/v1/client/close-commands", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 0
    assert data["commands"] == []


@pytest.mark.asyncio
async def test_poll_close_commands_with_pending(
    client, db_session, test_user, test_device
):
    """Test polling when close commands are pending.

    Workflow:
        1. Create an open position
        2. Monitor detects breach → creates CloseCommand
        3. EA polls /close-commands → receives command
    """
    # Create open position
    position = OpenPosition(
        id=str(uuid4()),
        execution_id=str(uuid4()),
        signal_id=str(uuid4()),
        approval_id=str(uuid4()),
        user_id=test_user.id,
        device_id=test_device.id,
        instrument="XAUUSD",
        side=0,
        entry_price=2655.00,
        volume=0.1,
        owner_sl=2645.00,
        owner_tp=2670.00,
        status=PositionStatus.OPEN.value,
    )
    db_session.add(position)
    await db_session.commit()

    # Monitor detects breach → creates close command
    close_cmd = await create_close_command(
        db_session,
        position_id=position.id,
        device_id=test_device.id,
        reason="sl_hit",
        expected_price=2643.50,
    )

    # EA polls for close commands
    headers = generate_device_auth_headers(
        device=test_device,
        method="GET",
        path="/api/v1/client/close-commands",
        body_dict=None,
    )

    response = await client.get("/api/v1/client/close-commands", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert len(data["commands"]) == 1

    command = data["commands"][0]
    assert command["id"] == close_cmd.id
    assert command["position_id"] == position.id
    assert command["reason"] == "sl_hit"
    assert command["expected_price"] == 2643.50


@pytest.mark.asyncio
async def test_poll_close_commands_multiple_pending(
    client, db_session, test_user, test_device
):
    """Test polling with multiple pending close commands.

    EA should receive all pending commands for its device.
    Commands should be ordered by created_at (oldest first).
    """
    # Create 3 open positions
    positions = []
    for i in range(3):
        position = OpenPosition(
            id=str(uuid4()),
            execution_id=str(uuid4()),
            signal_id=str(uuid4()),
            approval_id=str(uuid4()),
            user_id=test_user.id,
            device_id=test_device.id,
            instrument="XAUUSD",
            side=0,
            entry_price=2655.00 + i,
            volume=0.1,
            owner_sl=2645.00,
            owner_tp=2670.00,
            status=PositionStatus.OPEN.value,
        )
        db_session.add(position)
        positions.append(position)

    await db_session.commit()

    # Create close commands for all 3 positions
    for position in positions:
        await create_close_command(
            db_session,
            position_id=position.id,
            device_id=test_device.id,
            reason="tp_hit",
            expected_price=2672.00,
        )

    # EA polls for close commands
    headers = generate_device_auth_headers(
        device=test_device,
        method="GET",
        path="/api/v1/client/close-commands",
        body_dict=None,
    )

    response = await client.get("/api/v1/client/close-commands", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 3
    assert len(data["commands"]) == 3

    # All commands should have correct reason
    for command in data["commands"]:
        assert command["reason"] == "tp_hit"
        assert command["expected_price"] == 2672.00


@pytest.mark.asyncio
async def test_close_ack_success(client, db_session, test_user, test_device):
    """Test acknowledging successful close execution.

    Workflow:
        1. Create position + close command
        2. EA polls → receives command
        3. EA executes close successfully
        4. EA sends ack with status=executed
        5. Verify CloseCommand and OpenPosition updated
    """
    # Create open position
    position = OpenPosition(
        id=str(uuid4()),
        execution_id=str(uuid4()),
        signal_id=str(uuid4()),
        approval_id=str(uuid4()),
        user_id=test_user.id,
        device_id=test_device.id,
        instrument="XAUUSD",
        side=0,
        entry_price=2655.00,
        volume=0.1,
        owner_sl=2645.00,
        owner_tp=2670.00,
        status=PositionStatus.OPEN.value,
    )
    db_session.add(position)
    await db_session.commit()

    # Create close command
    close_cmd = await create_close_command(
        db_session,
        position_id=position.id,
        device_id=test_device.id,
        reason="sl_hit",
        expected_price=2643.50,
    )

    # EA acknowledges successful close
    ack_request = {
        "command_id": close_cmd.id,
        "status": "executed",
        "actual_close_price": 2643.75,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

    headers = generate_device_auth_headers(
        device=test_device,
        method="POST",
        path="/api/v1/client/close-ack",
        body_dict=ack_request,
    )

    response = await client.post(
        "/api/v1/client/close-ack",
        json=ack_request,
        headers=headers,
    )

    assert response.status_code == 201
    data = response.json()
    assert data["command_id"] == close_cmd.id
    assert data["position_id"] == position.id
    assert data["status"] == "executed"

    # Verify CloseCommand updated
    await db_session.refresh(close_cmd)
    assert close_cmd.status == CloseCommandStatus.EXECUTED.value
    assert close_cmd.actual_close_price == 2643.75
    assert close_cmd.executed_at is not None

    # Verify OpenPosition updated
    await db_session.refresh(position)
    assert position.status == PositionStatus.CLOSED_SL.value
    assert position.close_price == 2643.75
    assert position.close_reason == "sl_hit"
    assert position.closed_at is not None


@pytest.mark.asyncio
async def test_close_ack_failure(client, db_session, test_user, test_device):
    """Test acknowledging failed close execution.

    Workflow:
        1. Create position + close command
        2. EA attempts close but fails
        3. EA sends ack with status=failed + error message
        4. Verify CloseCommand updated, position still OPEN
    """
    # Create open position
    position = OpenPosition(
        id=str(uuid4()),
        execution_id=str(uuid4()),
        signal_id=str(uuid4()),
        approval_id=str(uuid4()),
        user_id=test_user.id,
        device_id=test_device.id,
        instrument="XAUUSD",
        side=0,
        entry_price=2655.00,
        volume=0.1,
        owner_sl=2645.00,
        owner_tp=2670.00,
        status=PositionStatus.OPEN.value,
    )
    db_session.add(position)
    await db_session.commit()

    # Create close command
    close_cmd = await create_close_command(
        db_session,
        position_id=position.id,
        device_id=test_device.id,
        reason="tp_hit",
        expected_price=2672.00,
    )

    # EA acknowledges failed close
    ack_request = {
        "command_id": close_cmd.id,
        "status": "failed",
        "error_message": "MT5 connection timeout",
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

    headers = generate_device_auth_headers(
        device=test_device,
        method="POST",
        path="/api/v1/client/close-ack",
        body_dict=ack_request,
    )

    response = await client.post(
        "/api/v1/client/close-ack",
        json=ack_request,
        headers=headers,
    )

    assert response.status_code == 201
    data = response.json()
    assert data["command_id"] == close_cmd.id
    assert data["status"] == "failed"

    # Verify CloseCommand updated
    await db_session.refresh(close_cmd)
    assert close_cmd.status == CloseCommandStatus.FAILED.value
    assert close_cmd.error_message == "MT5 connection timeout"
    assert close_cmd.executed_at is not None

    # Verify OpenPosition updated to error status
    await db_session.refresh(position)
    assert position.status == PositionStatus.CLOSED_ERROR.value


@pytest.mark.asyncio
async def test_close_ack_invalid_status(client, db_session, test_user, test_device):
    """Test ack with invalid status value.

    Should return 400 Bad Request.
    """
    position = OpenPosition(
        id=str(uuid4()),
        execution_id=str(uuid4()),
        signal_id=str(uuid4()),
        approval_id=str(uuid4()),
        user_id=test_user.id,
        device_id=test_device.id,
        instrument="XAUUSD",
        side=0,
        entry_price=2655.00,
        volume=0.1,
        status=PositionStatus.OPEN.value,
    )
    db_session.add(position)
    await db_session.commit()

    close_cmd = await create_close_command(
        db_session,
        position_id=position.id,
        device_id=test_device.id,
        reason="sl_hit",
        expected_price=2643.50,
    )

    # Invalid status
    ack_request = {
        "command_id": close_cmd.id,
        "status": "invalid_status",  # Invalid!
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

    headers = generate_device_auth_headers(
        device=test_device,
        method="POST",
        path="/api/v1/client/close-ack",
        body_dict=ack_request,
    )

    response = await client.post(
        "/api/v1/client/close-ack",
        json=ack_request,
        headers=headers,
    )

    # Pydantic validation returns 422 for invalid enum/pattern values
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_close_ack_missing_close_price(
    client, db_session, test_user, test_device
):
    """Test ack with status=executed but missing actual_close_price.

    Should return 400 Bad Request.
    """
    position = OpenPosition(
        id=str(uuid4()),
        execution_id=str(uuid4()),
        signal_id=str(uuid4()),
        approval_id=str(uuid4()),
        user_id=test_user.id,
        device_id=test_device.id,
        instrument="XAUUSD",
        side=0,
        entry_price=2655.00,
        volume=0.1,
        status=PositionStatus.OPEN.value,
    )
    db_session.add(position)
    await db_session.commit()

    close_cmd = await create_close_command(
        db_session,
        position_id=position.id,
        device_id=test_device.id,
        reason="tp_hit",
        expected_price=2672.00,
    )

    # Missing actual_close_price
    ack_request = {
        "command_id": close_cmd.id,
        "status": "executed",
        # Missing: "actual_close_price": 2672.50,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

    headers = generate_device_auth_headers(
        device=test_device,
        method="POST",
        path="/api/v1/client/close-ack",
        body_dict=ack_request,
    )

    response = await client.post(
        "/api/v1/client/close-ack",
        json=ack_request,
        headers=headers,
    )

    assert response.status_code == 400
    assert "actual_close_price required" in response.json()["detail"].lower()
