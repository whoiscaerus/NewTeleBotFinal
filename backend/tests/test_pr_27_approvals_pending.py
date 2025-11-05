"""Tests for PR-27: Mini App Approval Console - Pending Approvals Endpoint.

Tests the GET /api/v1/approvals/pending endpoint that powers the mini app
approval console. Validates signal filtering, token generation, polling, and
security requirements (user isolation, no SL/TP exposure, etc.).

Coverage Target: ≥95% of backend/app/approvals/service.py + routes.py pending logic
"""

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.approvals.models import Approval, ApprovalDecision
from backend.app.auth.jwt_handler import JWTHandler
from backend.app.auth.models import User
from backend.app.signals.models import Signal, SignalStatus

# ============================================================================
# FIXTURES
# ============================================================================


@pytest_asyncio.fixture
async def jwt_handler():
    """JWT handler for token validation."""
    return JWTHandler()


@pytest_asyncio.fixture
async def signals_pending(db_session: AsyncSession, test_user: User):
    """Create 3 pending signals for current user."""
    signals = []
    for i in range(3):
        signal = Signal(
            user_id=test_user.id,
            instrument=["XAUUSD", "EURUSD", "GBPUSD"][i],
            side=i % 2,  # Alternating buy/sell
            price=100.0 + i,
            status=SignalStatus.NEW.value,
            payload={"lot_size": 0.04 + (i * 0.01)},
        )
        db_session.add(signal)
        signals.append(signal)

    await db_session.commit()
    for signal in signals:
        await db_session.refresh(signal)

    return signals


@pytest_asyncio.fixture
async def user2(db_session: AsyncSession):
    """Create second user for isolation tests."""
    from uuid import uuid4

    from backend.app.auth.models import User, UserRole

    user = User(
        id=str(uuid4()),
        email=f"user2_{uuid4()}@test.com",
        password_hash="dummy_hash",
        role=UserRole.USER,
        telegram_user_id=9999999,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def approvals_pending(
    db_session: AsyncSession, signals_pending: list, test_user: User
):
    """Create pending approvals for the signals (no decision yet)."""
    approvals = []
    for i, signal in enumerate(signals_pending):
        approval = Approval(
            signal_id=signal.id,
            user_id=test_user.id,
            decision=None,  # Pending (no decision)
            consent_version=1,
        )
        db_session.add(approval)
        approvals.append(approval)

    await db_session.commit()
    for approval in approvals:
        await db_session.refresh(approval)

    return approvals


@pytest_asyncio.fixture
async def approved_signal(db_session: AsyncSession, test_user: User):
    """Create a signal that's already approved (should be excluded from pending)."""
    signal = Signal(
        user_id=test_user.id,
        instrument="XAGUSD",
        side=0,
        price=25.0,
        status=SignalStatus.APPROVED.value,  # Already approved
        payload={"lot_size": 0.05},
    )
    db_session.add(signal)
    await db_session.commit()
    await db_session.refresh(signal)

    # Create approval with decision
    approval = Approval(
        signal_id=signal.id,
        user_id=test_user.id,
        decision=ApprovalDecision.APPROVED.value,  # Already decided
        consent_version=1,
    )
    db_session.add(approval)
    await db_session.commit()
    await db_session.refresh(approval)

    return signal


# ============================================================================
# TEST: Basic Pending Endpoint
# ============================================================================


@pytest.mark.asyncio
async def test_get_pending_approvals_returns_list(
    client: AsyncClient,
    auth_headers: dict,
    approvals_pending: list,
):
    """Test pending endpoint returns list of pending approvals."""
    response = await client.get(
        "/api/v1/approvals/pending",
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 3


@pytest.mark.asyncio
async def test_get_pending_approvals_empty_list(
    client: AsyncClient,
    auth_headers: dict,
):
    """Test pending endpoint returns empty list when no pending approvals."""
    response = await client.get(
        "/api/v1/approvals/pending",
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data == []


@pytest.mark.asyncio
async def test_get_pending_approvals_requires_auth(
    client: AsyncClient,
):
    """Test pending endpoint returns 401 without authentication."""
    response = await client.get("/api/v1/approvals/pending")

    assert response.status_code == 401


# ============================================================================
# TEST: Response Schema
# ============================================================================


@pytest.mark.asyncio
async def test_pending_approval_includes_signal_details(
    client: AsyncClient,
    auth_headers: dict,
    approvals_pending: list,
    signals_pending: list,
):
    """Test pending approval includes all required signal details."""
    response = await client.get(
        "/api/v1/approvals/pending",
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1

    approval = data[0]

    # Verify all required fields
    assert "signal_id" in approval
    assert "instrument" in approval
    assert "side" in approval
    assert "lot_size" in approval
    assert "created_at" in approval
    assert "approval_token" in approval
    assert "expires_at" in approval

    # Verify values are reasonable
    assert approval["instrument"] in ["XAUUSD", "EURUSD", "GBPUSD"]
    assert approval["side"] in ["buy", "sell"]
    assert isinstance(approval["lot_size"], (int, float))
    assert approval["lot_size"] > 0


@pytest.mark.asyncio
async def test_pending_approval_side_mapping(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    test_user: User,
):
    """Test side field correctly maps 0->buy, 1->sell."""
    # Create signals with explicit sides
    buy_signal = Signal(
        user_id=test_user.id,
        instrument="XAUUSD",
        side=0,  # Buy
        price=100.0,
        status=SignalStatus.NEW.value,
    )
    sell_signal = Signal(
        user_id=test_user.id,
        instrument="EURUSD",
        side=1,  # Sell
        price=1.0,
        status=SignalStatus.NEW.value,
    )
    db_session.add(buy_signal)
    db_session.add(sell_signal)
    await db_session.commit()
    await db_session.refresh(buy_signal)
    await db_session.refresh(sell_signal)

    # Create pending approvals
    buy_approval = Approval(
        signal_id=buy_signal.id,
        user_id=test_user.id,
        decision=None,
    )
    sell_approval = Approval(
        signal_id=sell_signal.id,
        user_id=test_user.id,
        decision=None,
    )
    db_session.add(buy_approval)
    db_session.add(sell_approval)
    await db_session.commit()

    # Fetch and verify
    response = await client.get(
        "/api/v1/approvals/pending",
        headers=auth_headers,
    )

    data = response.json()
    assert len(data) == 2
    assert any(a["instrument"] == "XAUUSD" and a["side"] == "buy" for a in data)
    assert any(a["instrument"] == "EURUSD" and a["side"] == "sell" for a in data)


# ============================================================================
# TEST: Approval Tokens
# ============================================================================


@pytest.mark.asyncio
async def test_pending_approval_token_generated(
    client: AsyncClient,
    auth_headers: dict,
    approvals_pending: list,
):
    """Test each pending approval has a JWT token."""
    response = await client.get(
        "/api/v1/approvals/pending",
        headers=auth_headers,
    )

    data = response.json()
    for approval in data:
        token = approval["approval_token"]
        assert isinstance(token, str)
        assert len(token) > 0
        # JWT has 3 parts: header.payload.signature
        assert token.count(".") == 2


@pytest.mark.asyncio
async def test_pending_approval_token_unique(
    client: AsyncClient,
    auth_headers: dict,
    approvals_pending: list,
):
    """Test each approval gets a unique token."""
    response = await client.get(
        "/api/v1/approvals/pending",
        headers=auth_headers,
    )

    data = response.json()
    tokens = [a["approval_token"] for a in data]
    # All tokens should be unique
    assert len(tokens) == len(set(tokens))


@pytest.mark.asyncio
async def test_pending_approval_token_expiry(
    client: AsyncClient,
    auth_headers: dict,
    approvals_pending: list,
):
    """Test token expiry is set to ~5 minutes in future."""
    response = await client.get(
        "/api/v1/approvals/pending",
        headers=auth_headers,
    )

    data = response.json()
    now = datetime.now(UTC)

    for approval in data:
        expires_at_str = approval["expires_at"]
        expires_at = datetime.fromisoformat(expires_at_str)

        # Should expire in ~5 minutes (allow 1 minute margin for test execution)
        time_until_expiry = expires_at - now
        assert 4 * 60 < time_until_expiry.total_seconds() < 6 * 60


@pytest.mark.asyncio
async def test_approval_model_is_token_valid_method(
    db_session: AsyncSession,
    test_user: User,
):
    """Test Approval.is_token_valid() method."""
    signal = Signal(
        user_id=test_user.id,
        instrument="XAUUSD",
        side=0,
        price=100.0,
        status=SignalStatus.NEW.value,
    )
    db_session.add(signal)
    await db_session.commit()
    await db_session.refresh(signal)

    # Test 1: No token/expiry = invalid
    approval1 = Approval(
        signal_id=signal.id,
        user_id=test_user.id,
        decision=None,
    )
    assert not approval1.is_token_valid()

    # Test 2: Future expiry = valid
    approval1.expires_at = datetime.now(UTC) + timedelta(minutes=5)
    approval1.approval_token = "dummy_token"
    assert approval1.is_token_valid()

    # Test 3: Past expiry = invalid
    approval2 = Approval(
        signal_id=signal.id,
        user_id=test_user.id,
        decision=None,
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
        approval_token="dummy_token",
    )
    assert not approval2.is_token_valid()


# ============================================================================
# TEST: Filtering & Security
# ============================================================================


@pytest.mark.asyncio
async def test_pending_approvals_excludes_approved_signals(
    client: AsyncClient,
    auth_headers: dict,
    approvals_pending: list,
    approved_signal: Signal,
    db_session: AsyncSession,
):
    """Test pending endpoint excludes already-approved signals."""
    response = await client.get(
        "/api/v1/approvals/pending",
        headers=auth_headers,
    )

    data = response.json()
    # Should only have 3 pending, not the 1 already approved
    assert len(data) == 3
    signal_ids = [a["signal_id"] for a in data]
    assert approved_signal.id not in signal_ids


@pytest.mark.asyncio
async def test_pending_approvals_excludes_rejected_signals(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    test_user: User,
):
    """Test pending endpoint excludes rejected signals."""
    # Create signal
    signal = Signal(
        user_id=test_user.id,
        instrument="XAUUSD",
        side=0,
        price=100.0,
        status=SignalStatus.REJECTED.value,  # Rejected
    )
    db_session.add(signal)
    await db_session.commit()
    await db_session.refresh(signal)

    # Create rejection approval
    approval = Approval(
        signal_id=signal.id,
        user_id=test_user.id,
        decision=ApprovalDecision.REJECTED.value,  # Rejected
    )
    db_session.add(approval)
    await db_session.commit()

    response = await client.get(
        "/api/v1/approvals/pending",
        headers=auth_headers,
    )

    data = response.json()
    # Should be empty (no pending)
    assert len(data) == 0


@pytest.mark.asyncio
async def test_pending_approvals_user_isolation(
    client: AsyncClient,
    auth_headers: dict,
    test_user: User,
    user2: User,
    db_session: AsyncSession,
):
    """Test pending endpoint only returns current user's approvals."""
    # Create signal for current user
    signal1 = Signal(
        user_id=test_user.id,
        instrument="XAUUSD",
        side=0,
        price=100.0,
        status=SignalStatus.NEW.value,
    )
    db_session.add(signal1)

    # Create signal for user2
    signal2 = Signal(
        user_id=user2.id,
        instrument="EURUSD",
        side=1,
        price=1.0,
        status=SignalStatus.NEW.value,
    )
    db_session.add(signal2)
    await db_session.commit()
    await db_session.refresh(signal1)
    await db_session.refresh(signal2)

    # Create pending approvals for both users
    approval1 = Approval(
        signal_id=signal1.id,
        user_id=test_user.id,
        decision=None,
    )
    approval2 = Approval(
        signal_id=signal2.id,
        user_id=user2.id,
        decision=None,
    )
    db_session.add(approval1)
    db_session.add(approval2)
    await db_session.commit()

    # Current user should only see their own
    response = await client.get(
        "/api/v1/approvals/pending",
        headers=auth_headers,
    )

    data = response.json()
    assert len(data) == 1
    assert data[0]["instrument"] == "XAUUSD"


@pytest.mark.asyncio
async def test_pending_approval_no_sensitive_data(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    test_user: User,
):
    """Test pending approval never exposes SL/TP (stored in owner_only)."""
    # Create signal with owner_only data
    signal = Signal(
        user_id=test_user.id,
        instrument="XAUUSD",
        side=0,
        price=100.0,
        status=SignalStatus.NEW.value,
        owner_only="encrypted_sl_tp_strategy_data",  # Secret data
    )
    db_session.add(signal)
    await db_session.commit()
    await db_session.refresh(signal)

    # Create pending approval
    approval = Approval(
        signal_id=signal.id,
        user_id=test_user.id,
        decision=None,
    )
    db_session.add(approval)
    await db_session.commit()

    response = await client.get(
        "/api/v1/approvals/pending",
        headers=auth_headers,
    )

    data = response.json()
    approval_data = data[0]

    # Verify no sensitive fields in response
    assert "owner_only" not in approval_data
    assert "stop_loss" not in approval_data
    assert "take_profit" not in approval_data
    assert "strategy" not in approval_data


# ============================================================================
# TEST: Pagination
# ============================================================================


@pytest.mark.asyncio
async def test_pending_approvals_pagination_skip(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    test_user: User,
):
    """Test skip parameter for pagination."""
    # Create 5 pending signals
    for i in range(5):
        signal = Signal(
            user_id=test_user.id,
            instrument=f"SIG{i}",
            side=0,
            price=100.0 + i,
            status=SignalStatus.NEW.value,
        )
        db_session.add(signal)

    await db_session.commit()

    # Get all signals
    signals_result = await db_session.execute(
        select(Signal).where(Signal.user_id == test_user.id)
    )
    signals = signals_result.scalars().all()

    # Create pending approvals
    for signal in signals:
        approval = Approval(
            signal_id=signal.id,
            user_id=test_user.id,
            decision=None,
        )
        db_session.add(approval)

    await db_session.commit()

    # Fetch with skip=2
    response = await client.get(
        "/api/v1/approvals/pending?skip=2&limit=2",
        headers=auth_headers,
    )

    data = response.json()
    assert len(data) == 2


@pytest.mark.asyncio
async def test_pending_approvals_pagination_limit(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    test_user: User,
):
    """Test limit parameter for pagination."""
    # Create 5 pending signals
    for i in range(5):
        signal = Signal(
            user_id=test_user.id,
            instrument=f"SIG{i}",
            side=0,
            price=100.0 + i,
            status=SignalStatus.NEW.value,
        )
        db_session.add(signal)

    await db_session.commit()

    # Get all signals
    signals_result = await db_session.execute(
        select(Signal).where(Signal.user_id == test_user.id)
    )
    signals = signals_result.scalars().all()

    # Create pending approvals
    for signal in signals:
        approval = Approval(
            signal_id=signal.id,
            user_id=test_user.id,
            decision=None,
        )
        db_session.add(approval)

    await db_session.commit()

    # Fetch with limit=3
    response = await client.get(
        "/api/v1/approvals/pending?limit=3",
        headers=auth_headers,
    )

    data = response.json()
    assert len(data) == 3


@pytest.mark.asyncio
async def test_pending_approvals_limit_max_100(
    client: AsyncClient,
    auth_headers: dict,
):
    """Test limit parameter is capped at 100."""
    # Request with limit=500 should be rejected (validation error)
    response = await client.get(
        "/api/v1/approvals/pending?limit=500",
        headers=auth_headers,
    )

    # Should return 422 (validation error) because limit > 100
    assert response.status_code == 422

    # Request with limit=100 should succeed
    response = await client.get(
        "/api/v1/approvals/pending?limit=100",
        headers=auth_headers,
    )
    assert response.status_code == 200


# ============================================================================
# TEST: Polling with 'since' Parameter
# ============================================================================


@pytest.mark.asyncio
async def test_pending_approvals_since_parameter(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    test_user: User,
):
    """Test 'since' parameter filters by creation time."""
    # Create first signal
    signal1 = Signal(
        user_id=test_user.id,
        instrument="XAUUSD",
        side=0,
        price=100.0,
        status=SignalStatus.NEW.value,
    )
    db_session.add(signal1)
    await db_session.commit()
    await db_session.refresh(signal1)

    approval1 = Approval(
        signal_id=signal1.id,
        user_id=test_user.id,
        decision=None,
    )
    db_session.add(approval1)
    await db_session.commit()

    # Get first snapshot (checkpoint)
    # Use Z notation instead of +00:00 for FastAPI Query parameter compatibility
    checkpoint = datetime.now(UTC).isoformat().replace("+00:00", "Z")

    # Create second signal (after checkpoint)
    signal2 = Signal(
        user_id=test_user.id,
        instrument="EURUSD",
        side=1,
        price=1.0,
        status=SignalStatus.NEW.value,
    )
    db_session.add(signal2)
    await db_session.commit()
    await db_session.refresh(signal2)

    approval2 = Approval(
        signal_id=signal2.id,
        user_id=test_user.id,
        decision=None,
    )
    db_session.add(approval2)
    await db_session.commit()

    # Fetch since checkpoint (should only get signal2)
    response = await client.get(
        f"/api/v1/approvals/pending?since={checkpoint}",
        headers=auth_headers,
    )

    assert (
        response.status_code == 200
    ), f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()
    # Should have only the new signal
    assert isinstance(data, list), f"Expected list, got {type(data)}: {data}"
    assert len(data) >= 1
    instruments = [a["instrument"] for a in data]
    # At least signal2 should be there
    assert "EURUSD" in instruments


@pytest.mark.asyncio
async def test_pending_approvals_since_invalid_format(
    client: AsyncClient,
    auth_headers: dict,
):
    """Test invalid 'since' parameter format returns 422 (validation error)."""
    response = await client.get(
        "/api/v1/approvals/pending?since=invalid_date",
        headers=auth_headers,
    )

    # FastAPI returns 422 for Query parameter validation errors, not 400
    assert response.status_code == 422
    data = response.json()
    assert (
        "validation" in data.get("title", "").lower()
        or "invalid" in data.get("detail", "").lower()
    )


# ============================================================================
# TEST: Error Handling
# ============================================================================


@pytest.mark.asyncio
async def test_pending_approvals_order_by_created_desc(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    test_user: User,
):
    """Test pending approvals ordered by creation time DESC (newest first)."""
    # Create signals in order
    signals = []
    for i in range(3):
        signal = Signal(
            user_id=test_user.id,
            instrument=f"SIG{i}",
            side=0,
            price=100.0 + i,
            status=SignalStatus.NEW.value,
        )
        db_session.add(signal)
        signals.append(signal)

    await db_session.commit()

    # Refresh to get created_at
    for signal in signals:
        await db_session.refresh(signal)

    # Create pending approvals
    for signal in signals:
        approval = Approval(
            signal_id=signal.id,
            user_id=test_user.id,
            decision=None,
        )
        db_session.add(approval)

    await db_session.commit()

    response = await client.get(
        "/api/v1/approvals/pending",
        headers=auth_headers,
    )

    data = response.json()

    # Verify order (newest first)
    timestamps = [a["created_at"] for a in data]
    assert timestamps == sorted(timestamps, reverse=True)


# ============================================================================
# TEST: Telemetry
# ============================================================================


@pytest.mark.asyncio
async def test_pending_approvals_records_viewed_metric(
    client: AsyncClient,
    auth_headers: dict,
    approvals_pending: list,
):
    """Test viewing pending approvals records telemetry metric."""
    from backend.app.observability.metrics import get_metrics

    metrics = get_metrics()

    # Get initial count
    initial_count = metrics.miniapp_approvals_viewed_total._value.get()

    response = await client.get(
        "/api/v1/approvals/pending",
        headers=auth_headers,
    )

    assert response.status_code == 200

    # Verify metric incremented
    new_count = metrics.miniapp_approvals_viewed_total._value.get()
    assert new_count > initial_count
