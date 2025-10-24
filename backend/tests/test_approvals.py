"""Approval domain tests."""

import pytest
from datetime import datetime
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.approvals.schemas import ApprovalRequest
from backend.app.approvals.service import create_approval, get_approval
from backend.app.signals.models import Signal
from backend.app.approvals.models import Approval


@pytest.mark.asyncio
async def test_create_approval_valid(db_session: AsyncSession):
    """Test creating an approval for an existing signal."""
    # Setup: Create a signal
    signal = Signal(
        id="sig-test-001",
        instrument="XAUUSD",
        side=0,
        time=datetime.utcnow(),
        status=0,
    )
    db_session.add(signal)
    await db_session.commit()

    # Act: Create approval
    request = ApprovalRequest(
        signal_id="sig-test-001",
        decision=0,
        device_id="device-001",
        consent_version="2024-01-15",
        ip="192.168.1.1",
        ua="Mozilla/5.0",
    )
    approval = await create_approval(db_session, "user-001", request)

    # Assert
    assert approval.id is not None
    assert approval.signal_id == "sig-test-001"
    assert approval.user_id == "user-001"
    assert approval.decision == 0
    assert approval.created_at is not None


@pytest.mark.asyncio
async def test_create_approval_nonexistent_signal(db_session: AsyncSession):
    """Test approval creation rejects nonexistent signal."""
    request = ApprovalRequest(
        signal_id="sig-nonexistent",
        decision=0,
        consent_version="2024-01-15",
    )

    with pytest.raises(ValueError, match="Signal.*not found"):
        await create_approval(db_session, "user-001", request)


@pytest.mark.asyncio
async def test_create_approval_duplicate(db_session: AsyncSession):
    """Test duplicate approval returns error."""
    # Setup: Create signal and approval
    signal = Signal(
        id="sig-test-002",
        instrument="GOLD",
        side=1,
        time=datetime.utcnow(),
        status=0,
    )
    db_session.add(signal)
    await db_session.commit()

    request = ApprovalRequest(
        signal_id="sig-test-002",
        decision=0,
        consent_version="2024-01-15",
    )
    await create_approval(db_session, "user-002", request)

    # Act: Try to create duplicate
    with pytest.raises(ValueError, match="already approved"):
        await create_approval(db_session, "user-002", request)


@pytest.mark.asyncio
async def test_create_approval_different_decisions(db_session: AsyncSession):
    """Test same user can't change decision via re-approval."""
    # Setup: Create signal
    signal = Signal(
        id="sig-test-003",
        instrument="EUR/USD",
        side=0,
        time=datetime.utcnow(),
        status=0,
    )
    db_session.add(signal)
    await db_session.commit()

    # Act: Approve (decision=0)
    request_approve = ApprovalRequest(
        signal_id="sig-test-003",
        decision=0,
        consent_version="2024-01-15",
    )
    approval1 = await create_approval(db_session, "user-003", request_approve)
    assert approval1.decision == 0

    # Try to reject (decision=1) - should fail with duplicate error
    request_reject = ApprovalRequest(
        signal_id="sig-test-003",
        decision=1,
        consent_version="2024-01-15",
    )
    with pytest.raises(ValueError):
        await create_approval(db_session, "user-003", request_reject)


@pytest.mark.asyncio
async def test_create_approval_multiple_users(db_session: AsyncSession):
    """Test multiple users can approve same signal."""
    # Setup: Create signal
    signal = Signal(
        id="sig-test-004",
        instrument="BTC/USD",
        side=0,
        time=datetime.utcnow(),
        status=0,
    )
    db_session.add(signal)
    await db_session.commit()

    # Act: User 1 approves
    request = ApprovalRequest(
        signal_id="sig-test-004",
        decision=0,
        consent_version="2024-01-15",
    )
    approval1 = await create_approval(db_session, "user-004a", request)

    # Act: User 2 approves
    approval2 = await create_approval(db_session, "user-004b", request)

    # Assert: Both approvals exist with different users
    assert approval1.user_id == "user-004a"
    assert approval2.user_id == "user-004b"
    assert approval1.id != approval2.id


@pytest.mark.asyncio
async def test_get_approval_exists(db_session: AsyncSession):
    """Test retrieving existing approval."""
    # Setup
    signal = Signal(
        id="sig-test-005",
        instrument="SPY",
        side=0,
        time=datetime.utcnow(),
        status=0,
    )
    db_session.add(signal)
    await db_session.commit()

    request = ApprovalRequest(
        signal_id="sig-test-005",
        decision=1,
        consent_version="2024-01-15",
    )
    created = await create_approval(db_session, "user-005", request)

    # Act
    retrieved = await get_approval(db_session, created.id)

    # Assert
    assert retrieved is not None
    assert retrieved.id == created.id
    assert retrieved.decision == 1


@pytest.mark.asyncio
async def test_get_approval_not_found(db_session: AsyncSession):
    """Test retrieving nonexistent approval."""
    result = await get_approval(db_session, "apr-nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_post_approval_endpoint_valid(client: AsyncClient, db_session: AsyncSession):
    """Test POST /api/v1/approvals endpoint with valid data."""
    # Setup: Create signal
    signal = Signal(
        id="sig-test-006",
        instrument="TSLA",
        side=0,
        time=datetime.utcnow(),
        status=0,
    )
    db_session.add(signal)
    await db_session.commit()

    # Act
    response = await client.post(
        "/api/v1/approvals",
        json={
            "signal_id": "sig-test-006",
            "decision": 0,
            "consent_version": "2024-01-15",
            "ip": "192.168.1.1",
            "ua": "Mozilla/5.0",
        },
        headers={"X-User-Id": "user-006"},
    )

    # Assert
    assert response.status_code == 201
    data = response.json()
    assert data["signal_id"] == "sig-test-006"
    assert data["user_id"] == "user-006"
    assert data["decision"] == 0


@pytest.mark.asyncio
async def test_post_approval_missing_user_id(client: AsyncClient, db_session: AsyncSession):
    """Test POST /api/v1/approvals requires X-User-Id header."""
    # Setup: Create signal
    signal = Signal(
        id="sig-test-007",
        instrument="AAPL",
        side=1,
        time=datetime.utcnow(),
        status=0,
    )
    db_session.add(signal)
    await db_session.commit()

    # Act: POST without X-User-Id header
    response = await client.post(
        "/api/v1/approvals",
        json={
            "signal_id": "sig-test-007",
            "decision": 0,
            "consent_version": "2024-01-15",
        },
    )

    # Assert
    assert response.status_code == 401
    assert "X-User-Id" in response.json()["detail"]


@pytest.mark.asyncio
async def test_post_approval_nonexistent_signal(client: AsyncClient):
    """Test POST /api/v1/approvals returns 400 for nonexistent signal."""
    response = await client.post(
        "/api/v1/approvals",
        json={
            "signal_id": "sig-does-not-exist",
            "decision": 0,
            "consent_version": "2024-01-15",
        },
        headers={"X-User-Id": "user-007"},
    )

    assert response.status_code == 400
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_post_approval_invalid_decision(client: AsyncClient, db_session: AsyncSession):
    """Test POST /api/v1/approvals validates decision field."""
    # Setup: Create signal
    signal = Signal(
        id="sig-test-008",
        instrument="MSFT",
        side=0,
        time=datetime.utcnow(),
        status=0,
    )
    db_session.add(signal)
    await db_session.commit()

    # Act: Invalid decision (only 0 or 1 allowed)
    response = await client.post(
        "/api/v1/approvals",
        json={
            "signal_id": "sig-test-008",
            "decision": 99,  # Invalid
            "consent_version": "2024-01-15",
        },
        headers={"X-User-Id": "user-008"},
    )

    # Assert
    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_post_approval_duplicate(client: AsyncClient, db_session: AsyncSession):
    """Test POST /api/v1/approvals prevents duplicate approvals."""
    # Setup: Create signal and first approval
    signal = Signal(
        id="sig-test-009",
        instrument="NVDA",
        side=1,
        time=datetime.utcnow(),
        status=0,
    )
    db_session.add(signal)
    await db_session.commit()

    response1 = await client.post(
        "/api/v1/approvals",
        json={
            "signal_id": "sig-test-009",
            "decision": 0,
            "consent_version": "2024-01-15",
        },
        headers={"X-User-Id": "user-009"},
    )
    assert response1.status_code == 201

    # Act: Try duplicate
    response2 = await client.post(
        "/api/v1/approvals",
        json={
            "signal_id": "sig-test-009",
            "decision": 1,  # Try different decision
            "consent_version": "2024-01-15",
        },
        headers={"X-User-Id": "user-009"},
    )

    # Assert
    assert response2.status_code == 400
    assert "already approved" in response2.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_approval_endpoint(client: AsyncClient, db_session: AsyncSession):
    """Test GET /api/v1/approvals/{id} endpoint."""
    # Setup: Create signal and approval
    signal = Signal(
        id="sig-test-010",
        instrument="GOOGL",
        side=0,
        time=datetime.utcnow(),
        status=0,
    )
    db_session.add(signal)
    await db_session.commit()

    response_create = await client.post(
        "/api/v1/approvals",
        json={
            "signal_id": "sig-test-010",
            "decision": 0,
            "consent_version": "2024-01-15",
        },
        headers={"X-User-Id": "user-010"},
    )
    approval_id = response_create.json()["id"]

    # Act
    response = await client.get(
        f"/api/v1/approvals/{approval_id}",
        headers={"X-User-Id": "user-010"},
    )

    # Assert
    assert response.status_code == 200
    assert response.json()["id"] == approval_id


@pytest.mark.asyncio
async def test_get_my_approvals_endpoint(client: AsyncClient, db_session: AsyncSession):
    """Test GET /api/v1/approvals/user/me endpoint."""
    # Setup: Create 3 signals and approvals
    for i in range(3):
        signal = Signal(
            id=f"sig-test-011-{i}",
            instrument="ETH",
            side=i % 2,
            time=datetime.utcnow(),
            status=0,
        )
        db_session.add(signal)
    await db_session.commit()

    # Create 3 approvals for user
    for i in range(3):
        await client.post(
            "/api/v1/approvals",
            json={
                "signal_id": f"sig-test-011-{i}",
                "decision": 0,
                "consent_version": "2024-01-15",
            },
            headers={"X-User-Id": "user-011"},
        )

    # Act
    response = await client.get(
        "/api/v1/approvals/user/me",
        headers={"X-User-Id": "user-011"},
    )

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 3
    assert len(data["approvals"]) == 3


@pytest.mark.asyncio
async def test_get_signal_approvals_endpoint(client: AsyncClient, db_session: AsyncSession):
    """Test GET /api/v1/approvals/signal/{id} endpoint."""
    # Setup: Create signal with 2 approvals from different users
    signal = Signal(
        id="sig-test-012",
        instrument="ADA",
        side=0,
        time=datetime.utcnow(),
        status=0,
    )
    db_session.add(signal)
    await db_session.commit()

    # Create 2 approvals
    await client.post(
        "/api/v1/approvals",
        json={
            "signal_id": "sig-test-012",
            "decision": 0,
            "consent_version": "2024-01-15",
        },
        headers={"X-User-Id": "user-012a"},
    )
    await client.post(
        "/api/v1/approvals",
        json={
            "signal_id": "sig-test-012",
            "decision": 0,
            "consent_version": "2024-01-15",
        },
        headers={"X-User-Id": "user-012b"},
    )

    # Act
    response = await client.get(
        "/api/v1/approvals/signal/sig-test-012",
        headers={"X-User-Id": "user-012a"},
    )

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2
    assert len(data["approvals"]) == 2
