"""
Integration tests for EA poll SL/TP redaction (PR-104 Phase 2).

CRITICAL TESTS:
These tests verify that clients NEVER see stop_loss or take_profit
in the poll response, ensuring anti-reselling protection works.

Tests:
    - Poll response has NO stop_loss field
    - Poll response has NO take_profit field
    - Poll response includes only: entry_price, volume, ttl_minutes
    - Signal with owner_only is decrypted server-side but not sent
    - Signal without owner_only still returns redacted params
"""

import json
import os
from datetime import datetime
from uuid import uuid4

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet

from backend.app.approvals.models import Approval, ApprovalDecision
from backend.app.auth.models import User
from backend.app.clients.devices.models import Device
from backend.app.clients.models import Client
from backend.app.ea.auth import HMACBuilder
from backend.app.signals.encryption import encrypt_owner_only
from backend.app.signals.models import Signal

# Set encryption key for tests
os.environ["OWNER_ONLY_ENCRYPTION_KEY"] = Fernet.generate_key().decode()


def generate_device_auth_headers(
    device: Device, method: str, path: str, body_dict: dict = None
) -> dict:
    """
    Generate HMAC authentication headers for EA endpoints.

    Args:
        device: Device fixture with hmac_key_hash
        method: HTTP method (GET, POST, etc.)
        path: Request path (e.g., /api/v1/client/poll)
        body_dict: Request body as dict (None for GET requests)

    Returns:
        Dict of authentication headers
    """
    nonce = str(uuid4())
    timestamp = datetime.utcnow().isoformat() + "Z"
    body_str = json.dumps(body_dict, separators=(",", ":")) if body_dict else ""

    # Build canonical string
    canonical = HMACBuilder.build_canonical_string(
        method=method,
        path=path,
        body=body_str,
        device_id=device.id,
        nonce=nonce,
        timestamp=timestamp,
    )

    # Sign with device's HMAC key
    signature = HMACBuilder.sign(canonical, device.hmac_key_hash.encode())

    return {
        "X-Device-Id": device.id,
        "X-Nonce": nonce,
        "X-Timestamp": timestamp,
        "X-Signature": signature,
    }


@pytest_asyncio.fixture
async def test_user(db_session):
    """Create test user for EA poll tests."""
    user = Client(
        id=str(uuid4()),
        telegram_id="123456789",
        email="test@example.com",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_device(db_session, test_user):
    """Create test device for EA poll tests."""
    device = Device(
        id=str(uuid4()),
        client_id=test_user.id,
        device_name="TestDevice",
        hmac_key_hash="test_hmac_key_hash_for_testing",
        is_active=True,
    )
    db_session.add(device)
    await db_session.commit()
    await db_session.refresh(device)
    return device


@pytest_asyncio.fixture
async def test_signal(db_session, test_user):
    """Create test signal with owner_only data."""
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
    await db_session.commit()
    await db_session.refresh(signal)
    return signal


@pytest.mark.asyncio
async def test_poll_response_has_no_stop_loss_field(
    client,
    db_session,
    test_user: User,
    test_device: Device,
    test_signal: Signal,
):
    """
    CRITICAL TEST: Verify poll response does NOT contain stop_loss field.

    This is the core of anti-reselling protection. If this test fails,
    clients can see your complete trading strategy.
    """
    # Create approval for signal
    approval = Approval(
        id=str(uuid4()),
        signal_id=test_signal.id,
        client_id=test_user.id,
        user_id=test_user.id,
        decision=ApprovalDecision.APPROVED.value,
        consent_version=1,
        created_at=datetime.utcnow(),
    )
    db_session.add(approval)
    await db_session.commit()

    # Poll as device
    headers = generate_device_auth_headers(
        device=test_device,
        method="GET",
        path="/api/v1/client/poll",
        body_dict=None,
    )
    response = await client.get(
        "/api/v1/client/poll",
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()

    exec_params = data["approvals"][0]["execution_params"]

    # Verify ONLY allowed fields are present
    allowed_fields = {"entry_price", "volume", "ttl_minutes"}
    actual_fields = set(exec_params.keys())

    assert actual_fields == allowed_fields, (
        f"Execution params contain unexpected fields. "
        f"Expected: {allowed_fields}, Got: {actual_fields}"
    )


@pytest.mark.asyncio
async def test_poll_with_owner_only_encrypted_data_not_exposed(
    client,
    db_session,
    test_user: User,
    test_device: Device,
):
    """
    Test that signals with owner_only field (encrypted SL/TP) are handled
    correctly: server decrypts internally but does NOT send to client.
    """
    # Create signal with owner_only encrypted data
    owner_data = {
        "sl": 2645.50,  # Hidden stop loss
        "tp": 2670.00,  # Hidden take profit
        "strategy": "fib_rsi_confluence",
    }
    encrypted_owner_only = encrypt_owner_only(owner_data)

    signal = Signal(
        id=str(uuid4()),
        user_id=test_user.id,  # Required field
        instrument="XAUUSD",
        side=0,  # buy
        price=2655.00,
        status=0,  # new
        payload={"entry_price": 2655.00, "volume": 0.1, "ttl_minutes": 240},
        owner_only=encrypted_owner_only,  # ENCRYPTED hidden levels
    )
    db_session.add(signal)

    # Create approval
    approval = Approval(
        id=str(uuid4()),
        signal_id=signal.id,
        client_id=test_user.id,
        user_id=test_user.id,
        decision=ApprovalDecision.APPROVED.value,
        consent_version=1,
        created_at=datetime.utcnow(),
    )
    db_session.add(approval)
    await db_session.commit()

    # Poll as device
    headers = generate_device_auth_headers(
        device=test_device,
        method="GET",
        path="/api/v1/client/poll",
        body_dict=None,
    )
    response = await client.get(
        "/api/v1/client/poll",
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()

    approval_data = data["approvals"][0]

    # Verify owner_only is NOT in response
    assert (
        "owner_only" not in approval_data
    ), "SECURITY BREACH: owner_only field exposed in response!"

    exec_params = approval_data["execution_params"]

    # Verify hidden levels are NOT in execution params
    assert "stop_loss" not in exec_params
    assert "take_profit" not in exec_params
    assert "sl" not in exec_params
    assert "tp" not in exec_params
    assert "strategy" not in exec_params

    # Verify only entry + volume + ttl
    assert exec_params["entry_price"] == 2655.00
    assert exec_params["volume"] == 0.1
    assert exec_params["ttl_minutes"] == 240


@pytest.mark.asyncio
async def test_poll_without_owner_only_still_redacted(
    client,
    db_session,
    test_user: User,
    test_device: Device,
):
    """
    Test that even signals without owner_only field return redacted params.

    This ensures backward compatibility: old signals without owner_only
    still don't expose SL/TP to clients.
    """
    # Create signal WITHOUT owner_only (old-style signal)
    signal = Signal(
        id=str(uuid4()),
        user_id=test_user.id,  # Required field
        instrument="XAUUSD",
        side=0,
        price=2655.00,
        status=0,
        payload={
            "entry_price": 2655.00,
            "stop_loss": 2640.00,  # In payload but should NOT be sent
            "take_profit": 2670.00,  # In payload but should NOT be sent
            "volume": 0.1,
            "ttl_minutes": 240,
        },
        owner_only=None,  # No encrypted data
    )
    db_session.add(signal)

    # Create approval
    approval = Approval(
        id=str(uuid4()),
        signal_id=signal.id,
        client_id=test_user.id,
        user_id=test_user.id,
        decision=ApprovalDecision.APPROVED.value,
        consent_version=1,
        created_at=datetime.utcnow(),
    )
    db_session.add(approval)
    await db_session.commit()

    # Poll as device
    headers = generate_device_auth_headers(
        device=test_device,
        method="GET",
        path="/api/v1/client/poll",
        body_dict=None,
    )
    response = await client.get(
        "/api/v1/client/poll",
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()

    exec_params = data["approvals"][0]["execution_params"]

    # Even though payload has stop_loss/take_profit, they should NOT be sent
    assert "stop_loss" not in exec_params
    assert "take_profit" not in exec_params

    # Only redacted params present
    assert exec_params["entry_price"] == 2655.00
    assert exec_params["volume"] == 0.1
    assert exec_params["ttl_minutes"] == 240


@pytest.mark.asyncio
async def test_poll_json_schema_validation(
    client,
    db_session,
    test_user: User,
    test_device: Device,
    test_signal: Signal,
):
    """
    Test that poll response validates against expected JSON schema.

    This ensures API contract stability: clients can rely on the
    redacted schema structure.
    """
    # Create approval
    approval = Approval(
        id=str(uuid4()),
        signal_id=test_signal.id,
        client_id=test_user.id,
        user_id=test_user.id,
        decision=ApprovalDecision.APPROVED.value,
        consent_version=1,
        created_at=datetime.utcnow(),
    )
    db_session.add(approval)
    await db_session.commit()

    # Poll as device
    headers = generate_device_auth_headers(
        device=test_device,
        method="GET",
        path="/api/v1/client/poll",
        body_dict=None,
    )
    response = await client.get(
        "/api/v1/client/poll",
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()

    # Validate top-level structure
    assert "approvals" in data
    assert "count" in data
    assert "polled_at" in data
    assert "next_poll_seconds" in data

    # Validate approval structure
    approval_data = data["approvals"][0]
    assert "approval_id" in approval_data
    assert "instrument" in approval_data
    assert "side" in approval_data
    assert "execution_params" in approval_data
    assert "approved_at" in approval_data
    assert "created_at" in approval_data

    # Validate execution_params structure (REDACTED)
    exec_params = approval_data["execution_params"]
    required_fields = ["entry_price", "volume", "ttl_minutes"]
    for field in required_fields:
        assert field in exec_params, f"Missing required field: {field}"

    # Validate types
    assert isinstance(exec_params["entry_price"], (int, float))
    assert isinstance(exec_params["volume"], (int, float))
    assert isinstance(exec_params["ttl_minutes"], int)

    # Validate no extra fields
    assert (
        len(exec_params) == 3
    ), f"Expected exactly 3 fields in execution_params, got {len(exec_params)}"


@pytest.mark.asyncio
async def test_multiple_signals_all_redacted(
    client,
    db_session,
    test_user: User,
    test_device: Device,
):
    """
    Test that when multiple signals are approved, ALL are redacted correctly.
    """
    # Create 3 signals with different configurations
    signals = []
    for i in range(3):
        owner_data = {
            "sl": 2640.00 + i,
            "tp": 2670.00 + i,
            "strategy": f"strategy_{i}",
        }
        signal = Signal(
            id=str(uuid4()),
            user_id=test_user.id,  # Required field
            instrument="XAUUSD",
            side=0,
            price=2655.00 + i,
            status=0,
            payload={"entry_price": 2655.00 + i, "volume": 0.1, "ttl_minutes": 240},
            owner_only=encrypt_owner_only(owner_data),
        )
        db_session.add(signal)
        signals.append(signal)

        # Create approval for each
        approval = Approval(
            id=str(uuid4()),
            signal_id=signal.id,
            client_id=test_user.id,
            user_id=test_user.id,
            decision=ApprovalDecision.APPROVED.value,
            consent_version=1,
            created_at=datetime.utcnow(),
        )
        db_session.add(approval)

    await db_session.commit()

    # Poll as device
    headers = generate_device_auth_headers(
        device=test_device,
        method="GET",
        path="/api/v1/client/poll",
        body_dict=None,
    )
    response = await client.get(
        "/api/v1/client/poll",
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()

    assert len(data["approvals"]) == 3

    # Verify ALL signals are redacted
    for approval_data in data["approvals"]:
        exec_params = approval_data["execution_params"]

        # No hidden fields
        assert "stop_loss" not in exec_params
        assert "take_profit" not in exec_params
        assert "owner_only" not in approval_data

        # Only redacted fields
        assert set(exec_params.keys()) == {"entry_price", "volume", "ttl_minutes"}
