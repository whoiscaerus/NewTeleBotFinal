"""PR-022 Approvals API tests."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.models import User
from backend.app.auth.utils import create_access_token, hash_password
from backend.app.signals.schema import SignalCreate
from backend.app.signals.service import SignalService


class TestApprovalCreation:
    """Test approval creation endpoints."""

    @pytest.mark.asyncio
    async def test_create_approval_valid(
        self, client: AsyncClient, db_session: AsyncSession, hmac_secret: str
    ):
        """Test creating a valid approval."""
        # Create user
        user = User(email="test@example.com", password_hash=hash_password("pass123"))
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        # Create token
        token = create_access_token(subject=str(user.id), role="USER")

        # Create signal
        signal_service = SignalService(db_session, hmac_key=hmac_secret)
        signal = await signal_service.create_signal(
            user_id=str(user.id),
            signal_create=SignalCreate(
                instrument="XAUUSD",
                side="buy",
                price=1950.0,
                payload={"test": "data"},
                version="1.0",
            ),
            external_id="test_ext_123",
        )

        # Create approval
        response = await client.post(
            "/api/v1/approvals",
            json={
                "signal_id": signal.id,
                "decision": "approved",
                "reason": None,
                "consent_version": 1,
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["signal_id"] == signal.id
        assert data["decision"] == "approved"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_approval_rejection(
        self, client: AsyncClient, db_session: AsyncSession, hmac_secret: str
    ):
        """Test rejecting a signal."""
        # Create user
        user = User(email="test2@example.com", password_hash=hash_password("pass123"))
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        token = create_access_token(subject=str(user.id), role="USER")

        # Create signal
        signal_service = SignalService(db_session, hmac_key=hmac_secret)
        signal = await signal_service.create_signal(
            user_id=str(user.id),
            signal_create=SignalCreate(
                instrument="EURUSD",
                side="sell",
                price=1.05,
                payload={},
                version="1.0",
            ),
            external_id="test_ext_reject",
        )

        response = await client.post(
            "/api/v1/approvals",
            json={
                "signal_id": signal.id,
                "decision": "rejected",
                "reason": "Risk too high",
                "consent_version": 1,
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["decision"] == "rejected"
        assert data["reason"] == "Risk too high"

    @pytest.mark.asyncio
    async def test_create_approval_no_jwt_401(self, client: AsyncClient):
        """Test approval without JWT returns 401."""
        response = await client.post(
            "/api/v1/approvals",
            json={
                "signal_id": "nonexistent",
                "decision": "approved",
                "reason": None,
                "consent_version": 1,
            },
        )

        assert response.status_code == 401  # 401 Unauthorized when no JWT token


class TestApprovalRetrieval:
    """Test approval retrieval endpoints."""

    @pytest.mark.asyncio
    async def test_list_approvals_empty(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test listing empty approvals."""
        # Create user
        user = User(email="test3@example.com", password_hash=hash_password("pass123"))
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        token = create_access_token(subject=str(user.id), role="USER")

        response = await client.get(
            "/api/v1/approvals",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 0


class TestApprovalSecurity:
    """Test security aspects of approvals."""

    @pytest.mark.asyncio
    async def test_create_approval_duplicate_409(
        self, client: AsyncClient, db_session: AsyncSession, hmac_secret: str
    ):
        """Test duplicate approval returns 409."""
        # Create user
        user = User(email="test4@example.com", password_hash=hash_password("pass123"))
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        token = create_access_token(subject=str(user.id), role="USER")

        # Create signal
        signal_service = SignalService(db_session, hmac_key=hmac_secret)
        signal = await signal_service.create_signal(
            user_id=str(user.id),
            signal_create=SignalCreate(
                instrument="XAUUSD",
                side="buy",
                price=1950.0,
                payload={},
                version="1.0",
            ),
            external_id="test_ext_dup",
        )

        # First approval
        response1 = await client.post(
            "/api/v1/approvals",
            json={
                "signal_id": signal.id,
                "decision": "approved",
                "reason": None,
                "consent_version": 1,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response1.status_code == 201

        # Second approval (duplicate)
        response2 = await client.post(
            "/api/v1/approvals",
            json={
                "signal_id": signal.id,
                "decision": "approved",
                "reason": None,
                "consent_version": 1,
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response2.status_code == 409

    @pytest.mark.asyncio
    async def test_create_approval_not_owner_403(
        self, client: AsyncClient, db_session: AsyncSession, hmac_secret: str, clear_auth_override
    ):
        """Test approval by non-owner returns 403."""
        # Create two users
        user1 = User(email="user1@example.com", password_hash=hash_password("pass123"))
        user2 = User(email="user2@example.com", password_hash=hash_password("pass123"))
        db_session.add(user1)
        db_session.add(user2)
        await db_session.commit()
        await db_session.refresh(user1)
        await db_session.refresh(user2)

        token2 = create_access_token(subject=str(user2.id), role="USER")

        # Create signal as user1
        signal_service = SignalService(db_session, hmac_key=hmac_secret)
        signal = await signal_service.create_signal(
            user_id=str(user1.id),
            signal_create=SignalCreate(
                instrument="XAUUSD",
                side="buy",
                price=1950.0,
                payload={},
                version="1.0",
            ),
            external_id="test_ext_403",
        )

        # Try to approve as user2
        response = await client.post(
            "/api/v1/approvals",
            json={
                "signal_id": signal.id,
                "decision": "approved",
                "reason": None,
                "consent_version": 1,
            },
            headers={"Authorization": f"Bearer {token2}"},
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_create_approval_signal_not_found_404(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test approval for non-existent signal returns 404."""
        # Create user
        user = User(email="test5@example.com", password_hash=hash_password("pass123"))
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        token = create_access_token(subject=str(user.id), role="USER")

        response = await client.post(
            "/api/v1/approvals",
            json={
                "signal_id": "nonexistent",
                "decision": "approved",
                "reason": None,
                "consent_version": 1,
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 404
