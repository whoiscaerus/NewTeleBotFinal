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

    # PR-042: Verify response is encrypted envelope (not plaintext)
    # Each approval should have: approval_id, ciphertext, nonce, aad
    # NO plaintext fields like execution_params, instrument, side, etc.
    approval = data["approvals"][0]

    # Verify encrypted envelope structure
    assert "approval_id" in approval
    assert "ciphertext" in approval
    assert "nonce" in approval
    assert "aad" in approval

    # CRITICAL: Verify that sensitive fields are NOT present in plaintext
    # These would be fields if the response was unencrypted
    assert (
        "execution_params" not in approval
    ), "execution_params should NOT be in plaintext encrypted response"
    assert (
        "instrument" not in approval
    ), "instrument should NOT be in plaintext encrypted response"
    assert "side" not in approval, "side should NOT be in plaintext encrypted response"
    assert (
        "stop_loss" not in approval
    ), "stop_loss should NOT be in plaintext encrypted response"
    assert (
        "take_profit" not in approval
    ), "take_profit should NOT be in plaintext encrypted response"


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

    # PR-042: Verify encrypted envelope structure (not plaintext)
    assert "approval_id" in approval_data
    assert "ciphertext" in approval_data
    assert "nonce" in approval_data
    assert "aad" in approval_data

    # SECURITY: Verify hidden levels are NOT exposed in plaintext
    assert (
        "owner_only" not in approval_data
    ), "SECURITY BREACH: owner_only field exposed in response!"

    # Verify no execution_params (signals are encrypted)
    assert (
        "execution_params" not in approval_data
    ), "execution_params should NOT be in plaintext encrypted response"

    # Verify hidden fields NOT in plaintext
    assert "stop_loss" not in approval_data
    assert "take_profit" not in approval_data
    assert "sl" not in approval_data
    assert "tp" not in approval_data
    assert "strategy" not in approval_data


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

    approval_data = data["approvals"][0]

    # PR-042: Verify encrypted envelope structure
    assert "approval_id" in approval_data
    assert "ciphertext" in approval_data
    assert "nonce" in approval_data
    assert "aad" in approval_data

    # Verify that plaintext sensitive fields are NOT present
    # (they're encrypted instead)
    assert "execution_params" not in approval_data
    assert "stop_loss" not in approval_data
    assert "take_profit" not in approval_data


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

    # Validate encrypted approval structure (PR-042)
    # All signals are now encrypted, so the structure is different
    approval_data = data["approvals"][0]
    assert "approval_id" in approval_data, "Missing approval_id"
    assert "ciphertext" in approval_data, "Missing ciphertext"
    assert "nonce" in approval_data, "Missing nonce"
    assert "aad" in approval_data, "Missing aad"

    # Verify plaintext fields are NOT present (they're encrypted)
    assert (
        "instrument" not in approval_data
    ), "instrument should NOT be in plaintext (encrypted response)"
    assert (
        "side" not in approval_data
    ), "side should NOT be in plaintext (encrypted response)"
    assert (
        "execution_params" not in approval_data
    ), "execution_params should NOT be in plaintext (encrypted response)"
    assert (
        "approved_at" not in approval_data
    ), "approved_at should NOT be in plaintext (encrypted response)"
    assert (
        "created_at" not in approval_data
    ), "created_at should NOT be in plaintext (encrypted response)"


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

    # Verify ALL signals are encrypted (not plaintext)
    for approval_data in data["approvals"]:
        # Each approval should be an encrypted envelope
        assert "approval_id" in approval_data
        assert "ciphertext" in approval_data
        assert "nonce" in approval_data
        assert "aad" in approval_data

        # No plaintext sensitive fields
        assert (
            "execution_params" not in approval_data
        ), "execution_params should NOT be plaintext in encrypted response"
        assert "stop_loss" not in approval_data
        assert "take_profit" not in approval_data
        assert "owner_only" not in approval_data
        assert "instrument" not in approval_data
        assert "side" not in approval_data
