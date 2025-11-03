"""Tests for Approvals service business logic (PR-022).

CRITICAL TESTS ONLY:
✓ Approve signal → creates approval record + updates signal status
✓ Reject signal → creates approval record + updates signal status  
✓ Duplicate detection → (signal_id, user_id) unique constraint
✓ Signal not found → raises ValueError
✓ IP/UA capture → fields stored in DB
✓ Consent version → tracked correctly
✓ is_approved() → returns correct boolean

ALL tests use REAL AsyncSession database - NO MOCKS of business logic.
"""

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import uuid4

from backend.app.approvals.models import Approval, ApprovalDecision
from backend.app.approvals.service import ApprovalService
from backend.app.signals.models import Signal, SignalStatus
from backend.app.auth.models import User


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession):
    """Create test user."""
    user = User(
        id=str(uuid4()),
        email="test@example.com",
        password_hash="test",
        role="user",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_signal(db_session: AsyncSession, test_user: User):
    """Create test signal."""
    signal = Signal(
        id=str(uuid4()),
        user_id=test_user.id,
        instrument="XAUUSD",
        side=0,
        price=1950.50,
        status=SignalStatus.NEW.value,
    )
    db_session.add(signal)
    await db_session.commit()
    await db_session.refresh(signal)
    return signal


# ============================================================
# APPROVAL WORKFLOW TESTS
# ============================================================

@pytest.mark.asyncio
async def test_approve_signal_creates_record(
    db_session: AsyncSession, test_user: User, test_signal: Signal
):
    """Test: Approving signal creates approval record."""
    service = ApprovalService(db_session)

    approval = await service.approve_signal(
        signal_id=test_signal.id,
        user_id=test_user.id,
        decision="approved",
    )

    assert approval.id is not None
    assert approval.decision == ApprovalDecision.APPROVED.value


@pytest.mark.asyncio
async def test_approve_signal_updates_signal_status(
    db_session: AsyncSession, test_user: User, test_signal: Signal
):
    """Test: Approving signal updates signal status to APPROVED."""
    assert test_signal.status == SignalStatus.NEW.value
    service = ApprovalService(db_session)

    await service.approve_signal(
        signal_id=test_signal.id,
        user_id=test_user.id,
        decision="approved",
    )

    await db_session.refresh(test_signal)
    assert test_signal.status == SignalStatus.APPROVED.value


@pytest.mark.asyncio
async def test_reject_signal_creates_record(
    db_session: AsyncSession, test_user: User, test_signal: Signal
):
    """Test: Rejecting signal creates approval record."""
    service = ApprovalService(db_session)

    approval = await service.approve_signal(
        signal_id=test_signal.id,
        user_id=test_user.id,
        decision="rejected",
        reason="Risk too high",
    )

    assert approval.id is not None
    assert approval.decision == ApprovalDecision.REJECTED.value
    assert approval.reason == "Risk too high"


@pytest.mark.asyncio
async def test_reject_signal_updates_signal_status(
    db_session: AsyncSession, test_user: User, test_signal: Signal
):
    """Test: Rejecting signal updates signal status to REJECTED."""
    assert test_signal.status == SignalStatus.NEW.value
    service = ApprovalService(db_session)

    await service.approve_signal(
        signal_id=test_signal.id,
        user_id=test_user.id,
        decision="rejected",
    )

    await db_session.refresh(test_signal)
    assert test_signal.status == SignalStatus.REJECTED.value


# ============================================================
# DUPLICATE DETECTION TESTS (CRITICAL)
# ============================================================

@pytest.mark.asyncio
async def test_duplicate_approval_raises_error(
    db_session: AsyncSession, test_user: User, test_signal: Signal
):
    """Test: Duplicate approval (signal_id, user_id) raises error.
    
    CRITICAL BUSINESS RULE: Only ONE approval per signal per user.
    Enforced by unique constraint (signal_id, user_id).
    """
    service = ApprovalService(db_session)

    # First approval succeeds
    await service.approve_signal(
        signal_id=test_signal.id,
        user_id=test_user.id,
        decision="approved",
    )

    # Second attempt should fail
    with pytest.raises(Exception):  # IntegrityError
        await service.approve_signal(
            signal_id=test_signal.id,
            user_id=test_user.id,
            decision="rejected",
        )


# ============================================================
# ERROR HANDLING TESTS
# ============================================================

@pytest.mark.asyncio
async def test_approve_nonexistent_signal_raises_error(
    db_session: AsyncSession, test_user: User
):
    """Test: Approving non-existent signal raises error."""
    service = ApprovalService(db_session)

    with pytest.raises((ValueError, Exception)):  # Service may raise ValueError or APIException
        await service.approve_signal(
            signal_id="nonexistent",
            user_id=test_user.id,
            decision="approved",
        )


# ============================================================
# CONTEXT CAPTURE TESTS
# ============================================================

@pytest.mark.asyncio
async def test_ip_captured(
    db_session: AsyncSession, test_user: User, test_signal: Signal
):
    """Test: IP address captured in approval."""
    service = ApprovalService(db_session)

    approval = await service.approve_signal(
        signal_id=test_signal.id,
        user_id=test_user.id,
        decision="approved",
        ip="192.168.1.1",
    )

    assert approval.ip == "192.168.1.1"


@pytest.mark.asyncio
async def test_ua_captured(
    db_session: AsyncSession, test_user: User, test_signal: Signal
):
    """Test: User-Agent captured in approval."""
    service = ApprovalService(db_session)

    approval = await service.approve_signal(
        signal_id=test_signal.id,
        user_id=test_user.id,
        decision="approved",
        ua="TestClient/1.0",
    )

    assert approval.ua == "TestClient/1.0"


# ============================================================
# CONSENT VERSION TESTS
# ============================================================

@pytest.mark.asyncio
async def test_consent_version_default_1(
    db_session: AsyncSession, test_user: User, test_signal: Signal
):
    """Test: consent_version defaults to 1."""
    service = ApprovalService(db_session)

    approval = await service.approve_signal(
        signal_id=test_signal.id,
        user_id=test_user.id,
        decision="approved",
    )

    assert approval.consent_version == 1


@pytest.mark.asyncio
async def test_consent_version_can_override(
    db_session: AsyncSession, test_user: User, test_signal: Signal
):
    """Test: consent_version can be overridden."""
    service = ApprovalService(db_session)

    approval = await service.approve_signal(
        signal_id=test_signal.id,
        user_id=test_user.id,
        decision="approved",
        consent_version=3,
    )

    assert approval.consent_version == 3


# ============================================================
# MODEL METHOD TESTS
# ============================================================

@pytest.mark.asyncio
async def test_is_approved_true(
    db_session: AsyncSession, test_user: User, test_signal: Signal
):
    """Test: is_approved() returns True for approved."""
    service = ApprovalService(db_session)

    approval = await service.approve_signal(
        signal_id=test_signal.id,
        user_id=test_user.id,
        decision="approved",
    )

    assert approval.is_approved() is True


@pytest.mark.asyncio
async def test_is_approved_false(
    db_session: AsyncSession, test_user: User, test_signal: Signal
):
    """Test: is_approved() returns False for rejected."""
    service = ApprovalService(db_session)

    approval = await service.approve_signal(
        signal_id=test_signal.id,
        user_id=test_user.id,
        decision="rejected",
    )

    assert approval.is_approved() is False


# ============================================================
# DATABASE PERSISTENCE TESTS
# ============================================================

@pytest.mark.asyncio
async def test_approval_persisted_to_database(
    db_session: AsyncSession, test_user: User, test_signal: Signal
):
    """Test: Approval persisted to database and retrievable."""
    service = ApprovalService(db_session)

    approval = await service.approve_signal(
        signal_id=test_signal.id,
        user_id=test_user.id,
        decision="approved",
    )

    # Query DB directly
    result = await db_session.execute(
        select(Approval).where(Approval.id == approval.id)
    )
    retrieved = result.scalar()

    assert retrieved is not None
    assert retrieved.id == approval.id
    assert retrieved.signal_id == test_signal.id
    assert retrieved.user_id == test_user.id
    assert retrieved.decision == ApprovalDecision.APPROVED.value
