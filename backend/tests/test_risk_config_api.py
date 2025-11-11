"""
Comprehensive API route tests for PR-105 (Risk Configuration Management).

Tests all API endpoints:
- GET /api/v1/risk/config
- POST /api/v1/risk/config

Validates:
- Authentication requirements
- Owner-only authorization (POST endpoint)
- Input validation (0.1% - 50% range)
- Response schemas
- Error handling (400, 403, 500)
- Business logic correctness
- Database persistence
- In-memory config updates
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.models import User
from backend.app.trading.mt5_models import RiskConfiguration
from backend.app.trading.position_sizing_service import GLOBAL_RISK_CONFIG

pytestmark = pytest.mark.asyncio


class TestRiskConfigGetEndpoint:
    """Test GET /api/v1/risk/config endpoint."""

    async def test_get_config_requires_auth(self, client: AsyncClient):
        """Test GET endpoint requires JWT authentication."""
        response = await client.get("/api/v1/risk/config")

        assert response.status_code == 401
        assert "detail" in response.json()

    async def test_get_config_returns_default_values(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ):
        """Test GET endpoint returns default configuration values."""
        # Create default config in DB
        config = RiskConfiguration(
            id=1,
            fixed_risk_percent=3.0,
            entry_1_percent=0.50,
            entry_2_percent=0.35,
            entry_3_percent=0.15,
            margin_buffer_percent=20.0,
        )
        db_session.add(config)
        await db_session.commit()

        response = await client.get("/api/v1/risk/config", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["fixed_risk_percent"] == 3.0
        assert data["entry_splits"]["entry_1_percent"] == 0.50
        assert data["entry_splits"]["entry_2_percent"] == 0.35
        assert data["entry_splits"]["entry_3_percent"] == 0.15
        assert data["margin_buffer_percent"] == 20.0

    async def test_get_config_returns_updated_values(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ):
        """Test GET endpoint returns updated configuration after changes."""
        # Create config with updated risk %
        config = RiskConfiguration(
            id=1,
            fixed_risk_percent=2.5,
            entry_1_percent=0.50,
            entry_2_percent=0.35,
            entry_3_percent=0.15,
            margin_buffer_percent=20.0,
            updated_by=test_user.id,
        )
        db_session.add(config)
        await db_session.commit()

        response = await client.get("/api/v1/risk/config", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["fixed_risk_percent"] == 2.5


class TestRiskConfigPostEndpoint:
    """Test POST /api/v1/risk/config endpoint."""

    async def test_post_config_requires_auth(self, client: AsyncClient):
        """Test POST endpoint requires JWT authentication."""
        response = await client.post("/api/v1/risk/config?new_risk_percent=2.0")

        assert response.status_code == 401
        assert "detail" in response.json()

    async def test_post_config_requires_owner_role(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ):
        """Test POST endpoint rejects non-owner users (403 Forbidden)."""
        # test_user has role=USER (not OWNER)
        response = await client.post(
            "/api/v1/risk/config?new_risk_percent=2.0", headers=auth_headers
        )

        assert response.status_code == 403
        data = response.json()
        assert "detail" in data
        assert "owner" in data["detail"].lower()

    async def test_post_config_updates_successfully(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        owner_user: User,
    ):
        """Test POST endpoint updates risk % successfully for owner."""
        from backend.app.auth.utils import create_access_token

        # Create owner auth headers
        token = create_access_token(
            subject=owner_user.id, role=owner_user.role, expires_delta=None
        )
        owner_headers = {"Authorization": f"Bearer {token}"}

        # Create initial config
        config = RiskConfiguration(
            id=1,
            fixed_risk_percent=3.0,
            entry_1_percent=0.50,
            entry_2_percent=0.35,
            entry_3_percent=0.15,
            margin_buffer_percent=20.0,
        )
        db_session.add(config)
        await db_session.commit()

        # Update to 2.5%
        response = await client.post(
            "/api/v1/risk/config?new_risk_percent=2.5", headers=owner_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["previous_risk_percent"] == 3.0
        assert data["new_risk_percent"] == 2.5
        assert data["updated_by"] == owner_user.id

    async def test_post_config_persists_to_database(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        owner_user: User,
    ):
        """Test POST endpoint persists changes to database."""
        from backend.app.auth.utils import create_access_token

        token = create_access_token(
            subject=owner_user.id, role=owner_user.role, expires_delta=None
        )
        owner_headers = {"Authorization": f"Bearer {token}"}

        # Create initial config
        config = RiskConfiguration(
            id=1,
            fixed_risk_percent=3.0,
            entry_1_percent=0.50,
            entry_2_percent=0.35,
            entry_3_percent=0.15,
            margin_buffer_percent=20.0,
        )
        db_session.add(config)
        await db_session.commit()

        # Update to 4.0%
        await client.post(
            "/api/v1/risk/config?new_risk_percent=4.0", headers=owner_headers
        )

        # Verify database was updated
        result = await db_session.execute(
            select(RiskConfiguration).where(RiskConfiguration.id == 1)
        )
        updated_config = result.scalars().first()
        assert updated_config is not None
        assert updated_config.fixed_risk_percent == 4.0
        assert updated_config.updated_by == owner_user.id

    async def test_post_config_updates_in_memory_global_config(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        owner_user: User,
    ):
        """Test POST endpoint updates in-memory GLOBAL_RISK_CONFIG dict."""
        from backend.app.auth.utils import create_access_token

        token = create_access_token(
            subject=owner_user.id, role=owner_user.role, expires_delta=None
        )
        owner_headers = {"Authorization": f"Bearer {token}"}

        # Create initial config
        config = RiskConfiguration(
            id=1,
            fixed_risk_percent=3.0,
            entry_1_percent=0.50,
            entry_2_percent=0.35,
            entry_3_percent=0.15,
            margin_buffer_percent=20.0,
        )
        db_session.add(config)
        await db_session.commit()

        # Update to 5.0%
        await client.post(
            "/api/v1/risk/config?new_risk_percent=5.0", headers=owner_headers
        )

        # Verify in-memory config was updated
        assert GLOBAL_RISK_CONFIG["fixed_risk_percent"] == 5.0

    async def test_post_config_rejects_risk_below_minimum(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        owner_user: User,
    ):
        """Test POST endpoint rejects risk % below 0.1% (400 Bad Request)."""
        from backend.app.auth.utils import create_access_token

        token = create_access_token(
            subject=owner_user.id, role=owner_user.role, expires_delta=None
        )
        owner_headers = {"Authorization": f"Bearer {token}"}

        # Create initial config
        config = RiskConfiguration(
            id=1,
            fixed_risk_percent=3.0,
            entry_1_percent=0.50,
            entry_2_percent=0.35,
            entry_3_percent=0.15,
            margin_buffer_percent=20.0,
        )
        db_session.add(config)
        await db_session.commit()

        # Try to set 0.05% (below minimum)
        response = await client.post(
            "/api/v1/risk/config?new_risk_percent=0.05", headers=owner_headers
        )

        assert response.status_code == 422  # FastAPI validation error

    async def test_post_config_rejects_risk_above_maximum(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        owner_user: User,
    ):
        """Test POST endpoint rejects risk % above 50% (400 Bad Request)."""
        from backend.app.auth.utils import create_access_token

        token = create_access_token(
            subject=owner_user.id, role=owner_user.role, expires_delta=None
        )
        owner_headers = {"Authorization": f"Bearer {token}"}

        # Create initial config
        config = RiskConfiguration(
            id=1,
            fixed_risk_percent=3.0,
            entry_1_percent=0.50,
            entry_2_percent=0.35,
            entry_3_percent=0.15,
            margin_buffer_percent=20.0,
        )
        db_session.add(config)
        await db_session.commit()

        # Try to set 60% (above maximum)
        response = await client.post(
            "/api/v1/risk/config?new_risk_percent=60.0", headers=owner_headers
        )

        assert response.status_code == 422  # FastAPI validation error

    async def test_post_config_accepts_boundary_values(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        owner_user: User,
    ):
        """Test POST endpoint accepts minimum (0.1%) and maximum (50%) boundary values."""
        from backend.app.auth.utils import create_access_token

        token = create_access_token(
            subject=owner_user.id, role=owner_user.role, expires_delta=None
        )
        owner_headers = {"Authorization": f"Bearer {token}"}

        # Create initial config
        config = RiskConfiguration(
            id=1,
            fixed_risk_percent=3.0,
            entry_1_percent=0.50,
            entry_2_percent=0.35,
            entry_3_percent=0.15,
            margin_buffer_percent=20.0,
        )
        db_session.add(config)
        await db_session.commit()

        # Test minimum boundary (0.1%)
        response = await client.post(
            "/api/v1/risk/config?new_risk_percent=0.1", headers=owner_headers
        )
        assert response.status_code == 200
        assert response.json()["new_risk_percent"] == 0.1

        # Test maximum boundary (50%)
        response = await client.post(
            "/api/v1/risk/config?new_risk_percent=50.0", headers=owner_headers
        )
        assert response.status_code == 200
        assert response.json()["new_risk_percent"] == 50.0

    async def test_post_config_multiple_updates_create_audit_trail(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        owner_user: User,
    ):
        """Test POST endpoint creates audit trail with previous values."""
        from backend.app.auth.utils import create_access_token

        token = create_access_token(
            subject=owner_user.id, role=owner_user.role, expires_delta=None
        )
        owner_headers = {"Authorization": f"Bearer {token}"}

        # Reset GLOBAL_RISK_CONFIG to default (previous tests may have modified it)
        GLOBAL_RISK_CONFIG["fixed_risk_percent"] = 3.0

        # Create initial config
        config = RiskConfiguration(
            id=1,
            fixed_risk_percent=3.0,
            entry_1_percent=0.50,
            entry_2_percent=0.35,
            entry_3_percent=0.15,
            margin_buffer_percent=20.0,
        )
        db_session.add(config)
        await db_session.commit()

        # Update 1: 3.0% -> 2.0%
        response1 = await client.post(
            "/api/v1/risk/config?new_risk_percent=2.0", headers=owner_headers
        )
        assert response1.json()["previous_risk_percent"] == 3.0
        assert response1.json()["new_risk_percent"] == 2.0

        # Update 2: 2.0% -> 5.0%
        response2 = await client.post(
            "/api/v1/risk/config?new_risk_percent=5.0", headers=owner_headers
        )
        assert response2.json()["previous_risk_percent"] == 2.0
        assert response2.json()["new_risk_percent"] == 5.0

        # Update 3: 5.0% -> 1.5%
        response3 = await client.post(
            "/api/v1/risk/config?new_risk_percent=1.5", headers=owner_headers
        )
        assert response3.json()["previous_risk_percent"] == 5.0
        assert response3.json()["new_risk_percent"] == 1.5
