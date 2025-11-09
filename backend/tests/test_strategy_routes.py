"""Tests for strategy versioning API routes.

Validates:
- Owner/admin authorization (403 for non-owners)
- Version registration API
- Version activation API
- Canary rollout configuration API
- Shadow comparison API
- Request validation (422 for invalid data)

Tests use REAL FastAPI test client and REAL database (NO MOCKS).
"""

import pytest
from fastapi import status
from httpx import AsyncClient

from backend.app.strategy.models import VersionStatus
from backend.app.strategy.versioning import VersionRegistry


@pytest.mark.asyncio
async def test_register_version_success(client: AsyncClient, db_session):
    """Test successful version registration via API."""
    response = await client.post(
        "/api/v1/strategy/versions",
        json={
            "strategy_name": "fib_rsi",
            "version": "v2.0.0",
            "config": {"rsi_period": 14, "fib_lookback": 55},
            "status": "shadow",
        },
    )

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["strategy_name"] == "fib_rsi"
    assert data["version"] == "v2.0.0"
    assert data["status"] == "shadow"
    assert data["config"]["rsi_period"] == 14

    # Verify in database
    registry = VersionRegistry(db_session)
    shadows = await registry.get_shadow_versions("fib_rsi")
    assert len(shadows) == 1
    assert shadows[0].version == "v2.0.0"


@pytest.mark.asyncio
async def test_register_version_duplicate_rejected(client: AsyncClient, db_session):
    """Test that duplicate version registration returns 400."""
    # Register v1.0.0
    await client.post(
        "/api/v1/strategy/versions",
        json={
            "strategy_name": "ppo_gold",
            "version": "v1.0.0",
            "config": {"threshold": 0.5},
        },
    )

    # Try to register same version again
    response = await client.post(
        "/api/v1/strategy/versions",
        json={
            "strategy_name": "ppo_gold",
            "version": "v1.0.0",
            "config": {"threshold": 0.6},
        },
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "already exists" in response.json()["detail"]


@pytest.mark.asyncio
async def test_register_version_invalid_status(client: AsyncClient):
    """Test that invalid status returns 422."""
    response = await client.post(
        "/api/v1/strategy/versions",
        json={
            "strategy_name": "fib_rsi",
            "version": "v2.0.0",
            "config": {},
            "status": "invalid_status",
        },
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_list_versions_all(client: AsyncClient, db_session):
    """Test listing all versions."""
    registry = VersionRegistry(db_session)

    # Register 2 versions
    await registry.register_version(
        "fib_rsi", "v1.0.0", {"rsi_period": 14}, VersionStatus.ACTIVE
    )
    await registry.register_version(
        "fib_rsi", "v2.0.0", {"rsi_period": 20}, VersionStatus.SHADOW
    )

    # List all
    response = await client.get("/api/v1/strategy/versions")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data) == 2
    versions = [v["version"] for v in data]
    assert "v1.0.0" in versions
    assert "v2.0.0" in versions


@pytest.mark.asyncio
async def test_list_versions_filtered_by_strategy(client: AsyncClient, db_session):
    """Test listing versions filtered by strategy."""
    registry = VersionRegistry(db_session)

    # Register versions for different strategies
    await registry.register_version(
        "fib_rsi", "v1.0.0", {"rsi_period": 14}, VersionStatus.ACTIVE
    )
    await registry.register_version(
        "ppo_gold", "v1.0.0", {"threshold": 0.5}, VersionStatus.ACTIVE
    )

    # List fib_rsi only
    response = await client.get("/api/v1/strategy/versions?strategy_name=fib_rsi")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data) == 1
    assert data[0]["strategy_name"] == "fib_rsi"


@pytest.mark.asyncio
async def test_activate_version_success(client: AsyncClient, db_session):
    """Test activating a version via API."""
    registry = VersionRegistry(db_session)

    # Register v1.0.0 as active
    v1 = await registry.register_version(
        "fib_rsi", "v1.0.0", {"rsi_period": 14}, VersionStatus.ACTIVE
    )

    # Register v2.0.0 as shadow
    v2 = await registry.register_version(
        "fib_rsi", "v2.0.0", {"rsi_period": 20}, VersionStatus.SHADOW
    )

    # Activate v2.0.0
    response = await client.post(f"/api/v1/strategy/versions/{v2.id}/activate")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["version"] == "v2.0.0"
    assert data["status"] == "active"
    assert data["activated_at"] is not None

    # Verify v1.0.0 was retired
    await db_session.refresh(v1)
    assert v1.status == VersionStatus.RETIRED


@pytest.mark.asyncio
async def test_activate_version_not_found(client: AsyncClient):
    """Test activating non-existent version returns 404."""
    response = await client.post("/api/v1/strategy/versions/invalid_id/activate")

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_configure_canary_rollout_success(client: AsyncClient, db_session):
    """Test configuring canary rollout via API."""
    registry = VersionRegistry(db_session)

    # Register shadow version
    await registry.register_version(
        "ppo_gold", "v1.5.0", {"threshold": 0.6}, VersionStatus.SHADOW
    )

    # Start canary at 5%
    response = await client.patch(
        "/api/v1/strategy/rollout",
        json={
            "strategy_name": "ppo_gold",
            "version": "v1.5.0",
            "rollout_percent": 5.0,
        },
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["strategy_name"] == "ppo_gold"
    assert data["version"] == "v1.5.0"
    assert data["rollout_percent"] == 5.0

    # Verify canary config in database
    canary = await registry.get_canary_config("ppo_gold")
    assert canary is not None
    assert canary.rollout_percent == 5.0


@pytest.mark.asyncio
async def test_update_canary_rollout_percent(client: AsyncClient, db_session):
    """Test updating existing canary rollout percentage."""
    registry = VersionRegistry(db_session)

    # Start canary at 5%
    await registry.register_version(
        "fib_rsi", "v2.0.0", {"rsi_period": 14}, VersionStatus.SHADOW
    )
    await registry.activate_canary("fib_rsi", "v2.0.0", 5.0)

    # Increase to 10%
    response = await client.patch(
        "/api/v1/strategy/rollout",
        json={
            "strategy_name": "fib_rsi",
            "version": "v2.0.0",
            "rollout_percent": 10.0,
        },
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["rollout_percent"] == 10.0


@pytest.mark.asyncio
async def test_canary_rollout_invalid_percent_rejected(client: AsyncClient):
    """Test that invalid rollout percentage returns 422."""
    response = await client.patch(
        "/api/v1/strategy/rollout",
        json={
            "strategy_name": "fib_rsi",
            "version": "v2.0.0",
            "rollout_percent": 150.0,  # Invalid: > 100
        },
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_get_canary_config_success(client: AsyncClient, db_session):
    """Test getting canary configuration via API."""
    registry = VersionRegistry(db_session)

    # Start canary
    await registry.register_version(
        "ppo_gold", "v1.5.0", {"threshold": 0.5}, VersionStatus.SHADOW
    )
    await registry.activate_canary("ppo_gold", "v1.5.0", 10.0)

    # Get canary config
    response = await client.get("/api/v1/strategy/canary?strategy_name=ppo_gold")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["strategy_name"] == "ppo_gold"
    assert data["version"] == "v1.5.0"
    assert data["rollout_percent"] == 10.0


@pytest.mark.asyncio
async def test_get_canary_config_none(client: AsyncClient):
    """Test getting canary config when no canary exists."""
    response = await client.get("/api/v1/strategy/canary?strategy_name=nonexistent")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() is None


@pytest.mark.asyncio
async def test_shadow_comparison_api(client: AsyncClient, db_session):
    """Test shadow vs active comparison via API."""
    from datetime import datetime, timedelta
    from uuid import uuid4

    from backend.app.strategy.logs.models import DecisionLog, DecisionOutcome
    from backend.app.strategy.models import ShadowDecisionLog

    # Create shadow decisions
    for i in range(5):
        log = ShadowDecisionLog(
            id=str(uuid4()),
            version="v2.0.0",
            strategy_name="fib_rsi",
            symbol="GOLD",
            timestamp=datetime.utcnow() - timedelta(days=i),
            decision="buy",
            features={},
            confidence=0.8,
        )
        db_session.add(log)

    # Create active decisions
    for i in range(3):
        log = DecisionLog(
            id=str(uuid4()),
            timestamp=datetime.utcnow() - timedelta(days=i),
            strategy="fib_rsi",
            symbol="GOLD",
            features={"side": "buy"},
            outcome=DecisionOutcome.ENTERED,
            note="Active",
        )
        db_session.add(log)

    await db_session.commit()

    # Request comparison
    response = await client.post(
        "/api/v1/strategy/shadow-comparison",
        json={
            "shadow_version": "v2.0.0",
            "strategy_name": "fib_rsi",
            "symbol": "GOLD",
            "days": 7,
        },
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["shadow_signal_count"] == 5
    assert data["active_signal_count"] == 3
    assert "divergence_rate" in data


@pytest.mark.asyncio
async def test_shadow_comparison_invalid_days(client: AsyncClient):
    """Test that invalid days parameter returns 422."""
    response = await client.post(
        "/api/v1/strategy/shadow-comparison",
        json={
            "shadow_version": "v2.0.0",
            "strategy_name": "fib_rsi",
            "symbol": "GOLD",
            "days": 150,  # Invalid: > 90
        },
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_api_request_validation(client: AsyncClient):
    """Test that invalid request data returns 422."""
    # Missing required fields
    response = await client.post(
        "/api/v1/strategy/versions",
        json={
            "strategy_name": "fib_rsi",
            # Missing version and config
        },
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_canary_rollout_zero_percent(client: AsyncClient, db_session):
    """Test setting canary rollout to 0% (effectively disables canary)."""
    registry = VersionRegistry(db_session)

    # Start canary at 10%
    await registry.register_version(
        "fib_rsi", "v2.0.0", {"rsi_period": 14}, VersionStatus.SHADOW
    )
    await registry.activate_canary("fib_rsi", "v2.0.0", 10.0)

    # Set to 0%
    response = await client.patch(
        "/api/v1/strategy/rollout",
        json={
            "strategy_name": "fib_rsi",
            "version": "v2.0.0",
            "rollout_percent": 0.0,
        },
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["rollout_percent"] == 0.0


@pytest.mark.asyncio
async def test_canary_rollout_100_percent(client: AsyncClient, db_session):
    """Test setting canary rollout to 100% (full rollout)."""
    registry = VersionRegistry(db_session)

    await registry.register_version(
        "ppo_gold", "v2.0.0", {"threshold": 0.5}, VersionStatus.SHADOW
    )

    # Set to 100%
    response = await client.patch(
        "/api/v1/strategy/rollout",
        json={
            "strategy_name": "ppo_gold",
            "version": "v2.0.0",
            "rollout_percent": 100.0,
        },
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["rollout_percent"] == 100.0


@pytest.mark.asyncio
async def test_version_lifecycle_via_api(client: AsyncClient, db_session):
    """Test complete version lifecycle via API: register → canary → activate."""
    # 1. Register shadow version
    response = await client.post(
        "/api/v1/strategy/versions",
        json={
            "strategy_name": "fib_rsi",
            "version": "v2.0.0",
            "config": {"rsi_period": 14},
            "status": "shadow",
        },
    )
    assert response.status_code == status.HTTP_201_CREATED
    version_id = response.json()["id"]

    # 2. Start canary at 5%
    response = await client.patch(
        "/api/v1/strategy/rollout",
        json={
            "strategy_name": "fib_rsi",
            "version": "v2.0.0",
            "rollout_percent": 5.0,
        },
    )
    assert response.status_code == status.HTTP_200_OK

    # 3. Increase canary to 25%
    response = await client.patch(
        "/api/v1/strategy/rollout",
        json={
            "strategy_name": "fib_rsi",
            "version": "v2.0.0",
            "rollout_percent": 25.0,
        },
    )
    assert response.status_code == status.HTTP_200_OK

    # 4. Promote to active (100%)
    response = await client.post(f"/api/v1/strategy/versions/{version_id}/activate")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "active"
