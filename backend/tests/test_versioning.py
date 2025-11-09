"""Tests for strategy versioning system.

Validates:
- Version registration (create shadow, active, canary versions)
- Version lifecycle (shadow → canary → active → retired)
- User routing (deterministic hash-based canary assignment)
- Version transitions (atomic active version switches)
- Business rules (only one active per strategy, multiple shadows allowed)

Tests use REAL database (PostgreSQL) and REAL implementations (NO MOCKS).
"""

import pytest
from sqlalchemy import select

from backend.app.strategy.models import StrategyVersion, VersionStatus
from backend.app.strategy.versioning import VersionRegistry


@pytest.mark.asyncio
async def test_register_version_shadow(db_session):
    """Test registering a new version in SHADOW status."""
    registry = VersionRegistry(db_session)

    version = await registry.register_version(
        strategy_name="fib_rsi",
        version="v2.0.0",
        config={"rsi_period": 14, "fib_lookback": 55},
        status=VersionStatus.SHADOW,
    )

    assert version.id is not None
    assert version.strategy_name == "fib_rsi"
    assert version.version == "v2.0.0"
    assert version.status == VersionStatus.SHADOW
    assert version.config["rsi_period"] == 14
    assert version.created_at is not None

    # Verify in database
    result = await db_session.execute(
        select(StrategyVersion).where(StrategyVersion.id == version.id)
    )
    db_version = result.scalar_one()
    assert db_version.version == "v2.0.0"


@pytest.mark.asyncio
async def test_register_version_active(db_session):
    """Test registering a new version as ACTIVE."""
    registry = VersionRegistry(db_session)

    version = await registry.register_version(
        strategy_name="ppo_gold",
        version="v1.0.0",
        config={"fast_period": 12, "slow_period": 26},
        status=VersionStatus.ACTIVE,
    )

    assert version.status == VersionStatus.ACTIVE
    assert version.activated_at is not None


@pytest.mark.asyncio
async def test_register_duplicate_version_rejected(db_session):
    """Test that duplicate version registration is rejected."""
    registry = VersionRegistry(db_session)

    # Register v1.0.0
    await registry.register_version(
        strategy_name="fib_rsi",
        version="v1.0.0",
        config={"rsi_period": 14},
    )

    # Try to register same version again
    with pytest.raises(ValueError, match="already exists"):
        await registry.register_version(
            strategy_name="fib_rsi",
            version="v1.0.0",
            config={"rsi_period": 20},
        )


@pytest.mark.asyncio
async def test_register_second_active_rejected(db_session):
    """Test that registering second ACTIVE version is rejected."""
    registry = VersionRegistry(db_session)

    # Register v1.0.0 as active
    await registry.register_version(
        strategy_name="fib_rsi",
        version="v1.0.0",
        config={"rsi_period": 14},
        status=VersionStatus.ACTIVE,
    )

    # Try to register v2.0.0 as active (should fail)
    with pytest.raises(ValueError, match="already active"):
        await registry.register_version(
            strategy_name="fib_rsi",
            version="v2.0.0",
            config={"rsi_period": 20},
            status=VersionStatus.ACTIVE,
        )


@pytest.mark.asyncio
async def test_get_active_version(db_session):
    """Test retrieving active version for a strategy."""
    registry = VersionRegistry(db_session)

    # Register active version
    await registry.register_version(
        strategy_name="ppo_gold",
        version="v1.5.0",
        config={"threshold": 0.5},
        status=VersionStatus.ACTIVE,
    )

    # Get active version
    active = await registry.get_active_version("ppo_gold")

    assert active is not None
    assert active.version == "v1.5.0"
    assert active.status == VersionStatus.ACTIVE


@pytest.mark.asyncio
async def test_get_active_version_none(db_session):
    """Test that get_active_version returns None if no active version."""
    registry = VersionRegistry(db_session)

    # Register shadow version only
    await registry.register_version(
        strategy_name="fib_rsi",
        version="v2.0.0",
        config={"rsi_period": 14},
        status=VersionStatus.SHADOW,
    )

    # Get active version (should be None)
    active = await registry.get_active_version("fib_rsi")
    assert active is None


@pytest.mark.asyncio
async def test_get_shadow_versions(db_session):
    """Test retrieving all shadow versions for a strategy."""
    registry = VersionRegistry(db_session)

    # Register multiple shadow versions
    await registry.register_version(
        strategy_name="fib_rsi",
        version="v2.0.0",
        config={"rsi_period": 14},
        status=VersionStatus.SHADOW,
    )
    await registry.register_version(
        strategy_name="fib_rsi",
        version="v2.1.0",
        config={"rsi_period": 20},
        status=VersionStatus.SHADOW,
    )

    # Get shadow versions
    shadows = await registry.get_shadow_versions("fib_rsi")

    assert len(shadows) == 2
    versions = [s.version for s in shadows]
    assert "v2.0.0" in versions
    assert "v2.1.0" in versions


@pytest.mark.asyncio
async def test_activate_version(db_session):
    """Test promoting a shadow version to active."""
    registry = VersionRegistry(db_session)

    # Register v1.0.0 as active
    v1 = await registry.register_version(
        strategy_name="fib_rsi",
        version="v1.0.0",
        config={"rsi_period": 14},
        status=VersionStatus.ACTIVE,
    )

    # Register v2.0.0 as shadow
    await registry.register_version(
        strategy_name="fib_rsi",
        version="v2.0.0",
        config={"rsi_period": 20},
        status=VersionStatus.SHADOW,
    )

    # Activate v2.0.0 (should retire v1.0.0)
    activated = await registry.activate_version("fib_rsi", "v2.0.0")

    assert activated.version == "v2.0.0"
    assert activated.status == VersionStatus.ACTIVE
    assert activated.activated_at is not None

    # Verify v1.0.0 was retired
    await db_session.refresh(v1)
    assert v1.status == VersionStatus.RETIRED
    assert v1.retired_at is not None


@pytest.mark.asyncio
async def test_activate_version_not_found(db_session):
    """Test that activating non-existent version fails."""
    registry = VersionRegistry(db_session)

    with pytest.raises(ValueError, match="not found"):
        await registry.activate_version("fib_rsi", "v99.0.0")


@pytest.mark.asyncio
async def test_activate_canary(db_session):
    """Test starting canary rollout at 5%."""
    registry = VersionRegistry(db_session)

    # Register shadow version
    await registry.register_version(
        strategy_name="ppo_gold",
        version="v1.5.0",
        config={"threshold": 0.5},
        status=VersionStatus.SHADOW,
    )

    # Start canary at 5%
    version, canary = await registry.activate_canary(
        strategy_name="ppo_gold",
        version="v1.5.0",
        rollout_percent=5.0,
    )

    assert version.status == VersionStatus.CANARY
    assert canary.strategy_name == "ppo_gold"
    assert canary.version == "v1.5.0"
    assert canary.rollout_percent == 5.0


@pytest.mark.asyncio
async def test_update_canary_percent(db_session):
    """Test updating canary rollout percentage."""
    registry = VersionRegistry(db_session)

    # Start canary at 5%
    await registry.register_version(
        strategy_name="fib_rsi",
        version="v2.0.0",
        config={"rsi_period": 14},
        status=VersionStatus.SHADOW,
    )
    await registry.activate_canary("fib_rsi", "v2.0.0", 5.0)

    # Increase to 10%
    canary = await registry.update_canary_percent("fib_rsi", 10.0)

    assert canary.rollout_percent == 10.0


@pytest.mark.asyncio
async def test_update_canary_percent_invalid(db_session):
    """Test that invalid canary percentage is rejected."""
    registry = VersionRegistry(db_session)

    await registry.register_version(
        strategy_name="fib_rsi",
        version="v2.0.0",
        config={"rsi_period": 14},
    )
    await registry.activate_canary("fib_rsi", "v2.0.0", 5.0)

    # Try invalid percentages
    with pytest.raises(ValueError, match="0.0-100.0"):
        await registry.update_canary_percent("fib_rsi", -5.0)

    with pytest.raises(ValueError, match="0.0-100.0"):
        await registry.update_canary_percent("fib_rsi", 150.0)


@pytest.mark.asyncio
async def test_retire_version(db_session):
    """Test retiring a shadow version."""
    registry = VersionRegistry(db_session)

    # Register shadow version
    await registry.register_version(
        strategy_name="ppo_gold",
        version="v1.0.0",
        config={"threshold": 0.5},
        status=VersionStatus.SHADOW,
    )

    # Retire version
    retired = await registry.retire_version("ppo_gold", "v1.0.0")

    assert retired.status == VersionStatus.RETIRED
    assert retired.retired_at is not None


@pytest.mark.asyncio
async def test_retire_active_version_rejected(db_session):
    """Test that retiring active version is rejected."""
    registry = VersionRegistry(db_session)

    # Register active version
    await registry.register_version(
        strategy_name="fib_rsi",
        version="v1.0.0",
        config={"rsi_period": 14},
        status=VersionStatus.ACTIVE,
    )

    # Try to retire active version (should fail)
    with pytest.raises(ValueError, match="Cannot retire active"):
        await registry.retire_version("fib_rsi", "v1.0.0")


@pytest.mark.asyncio
async def test_route_user_to_version_active_only(db_session):
    """Test routing user to active version when no canary."""
    registry = VersionRegistry(db_session)

    # Register active version
    await registry.register_version(
        strategy_name="fib_rsi",
        version="v1.0.0",
        config={"rsi_period": 14},
        status=VersionStatus.ACTIVE,
    )

    # Route user (no canary → should get active)
    version = await registry.route_user_to_version(
        user_id="user_123",
        strategy_name="fib_rsi",
    )

    assert version.version == "v1.0.0"
    assert version.status == VersionStatus.ACTIVE


@pytest.mark.asyncio
async def test_route_user_to_version_canary_10_percent(db_session):
    """Test canary routing at 10% (deterministic hash-based assignment)."""
    registry = VersionRegistry(db_session)

    # Register active version
    await registry.register_version(
        strategy_name="ppo_gold",
        version="v1.0.0",
        config={"threshold": 0.5},
        status=VersionStatus.ACTIVE,
    )

    # Register canary version
    await registry.register_version(
        strategy_name="ppo_gold",
        version="v1.5.0",
        config={"threshold": 0.6},
        status=VersionStatus.SHADOW,
    )
    await registry.activate_canary("ppo_gold", "v1.5.0", 10.0)

    # Test 100 users, expect ~10% in canary
    canary_count = 0
    for i in range(100):
        user_id = f"user_{i:03d}"
        version = await registry.route_user_to_version(
            user_id=user_id,
            strategy_name="ppo_gold",
        )

        if version.version == "v1.5.0":
            canary_count += 1

            # Verify deterministic: same user always gets same version
            version2 = await registry.route_user_to_version(
                user_id=user_id,
                strategy_name="ppo_gold",
            )
            assert version2.version == "v1.5.0", "Routing must be deterministic"

    # Allow some variance (target 10%, accept 5-15%)
    assert 5 <= canary_count <= 15, f"Expected ~10 users in canary, got {canary_count}"


@pytest.mark.asyncio
async def test_route_user_deterministic(db_session):
    """Test that user routing is deterministic (same user → same version)."""
    registry = VersionRegistry(db_session)

    # Setup active + canary
    await registry.register_version(
        strategy_name="fib_rsi",
        version="v1.0.0",
        config={"rsi_period": 14},
        status=VersionStatus.ACTIVE,
    )
    await registry.register_version(
        strategy_name="fib_rsi",
        version="v2.0.0",
        config={"rsi_period": 20},
        status=VersionStatus.SHADOW,
    )
    await registry.activate_canary("fib_rsi", "v2.0.0", 50.0)

    # Route user 10 times
    user_id = "user_test_123"
    versions_seen = set()
    for _ in range(10):
        version = await registry.route_user_to_version(
            user_id=user_id,
            strategy_name="fib_rsi",
        )
        versions_seen.add(version.version)

    # User should always get same version (deterministic)
    assert len(versions_seen) == 1, "Routing must be deterministic"


@pytest.mark.asyncio
async def test_list_all_versions(db_session):
    """Test listing all versions for a strategy."""
    registry = VersionRegistry(db_session)

    # Register multiple versions
    await registry.register_version(
        strategy_name="fib_rsi",
        version="v1.0.0",
        config={"rsi_period": 14},
        status=VersionStatus.ACTIVE,
    )
    await registry.register_version(
        strategy_name="fib_rsi",
        version="v2.0.0",
        config={"rsi_period": 20},
        status=VersionStatus.SHADOW,
    )

    # List versions
    versions = await registry.list_all_versions("fib_rsi")

    assert len(versions) == 2
    version_strings = [v.version for v in versions]
    assert "v1.0.0" in version_strings
    assert "v2.0.0" in version_strings


@pytest.mark.asyncio
async def test_canary_user_hash_distribution(db_session):
    """Test that canary hash distribution is uniform."""
    registry = VersionRegistry(db_session)

    # Setup canary at 50%
    await registry.register_version(
        strategy_name="test_strategy",
        version="v1.0.0",
        config={},
        status=VersionStatus.ACTIVE,
    )
    await registry.register_version(
        strategy_name="test_strategy",
        version="v2.0.0",
        config={},
        status=VersionStatus.SHADOW,
    )
    await registry.activate_canary("test_strategy", "v2.0.0", 50.0)

    # Test 1000 users
    canary_count = 0
    for i in range(1000):
        user_id = f"user_{i:04d}"
        version = await registry.route_user_to_version(
            user_id=user_id,
            strategy_name="test_strategy",
        )
        if version.version == "v2.0.0":
            canary_count += 1

    # Expect ~500 users in canary (50%), allow 45-55% variance
    assert (
        450 <= canary_count <= 550
    ), f"Expected ~500 users in canary, got {canary_count}"


@pytest.mark.asyncio
async def test_multiple_shadows_allowed(db_session):
    """Test that multiple shadow versions are allowed per strategy."""
    registry = VersionRegistry(db_session)

    # Register 3 shadow versions (parallel A/B/C testing)
    await registry.register_version(
        strategy_name="fib_rsi",
        version="v2.0.0",
        config={"rsi_period": 14},
        status=VersionStatus.SHADOW,
    )
    await registry.register_version(
        strategy_name="fib_rsi",
        version="v2.1.0",
        config={"rsi_period": 20},
        status=VersionStatus.SHADOW,
    )
    await registry.register_version(
        strategy_name="fib_rsi",
        version="v3.0.0",
        config={"rsi_period": 10},
        status=VersionStatus.SHADOW,
    )

    shadows = await registry.get_shadow_versions("fib_rsi")
    assert len(shadows) == 3
