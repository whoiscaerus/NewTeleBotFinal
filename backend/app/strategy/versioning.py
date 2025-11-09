"""Strategy versioning system for version management and routing.

Provides:
- Version registration and lifecycle management (active → shadow → canary → retired)
- User routing to correct version (based on canary % or active version)
- Version comparison for A/B testing analytics
- Atomic version transitions (ensure only one active version per strategy)

Example usage:
    >>> from backend.app.strategy.versioning import VersionRegistry
    >>> from backend.app.core.db import get_async_session
    >>>
    >>> async with get_async_session() as session:
    ...     registry = VersionRegistry(session)
    ...
    ...     # Register new shadow version
    ...     version = await registry.register_version(
    ...         strategy_name="fib_rsi",
    ...         version="v2.0.0",
    ...         config={"rsi_period": 14, "fib_lookback": 55}
    ...     )
    ...
    ...     # After validation, promote to canary
    ...     await registry.activate_canary(
    ...         strategy_name="fib_rsi",
    ...         version="v2.0.0",
    ...         rollout_percent=5.0
    ...     )
    ...
    ...     # Route user to correct version
    ...     user_version = await registry.route_user_to_version(
    ...         user_id="user_123",
    ...         strategy_name="fib_rsi"
    ...     )
    ...     print(f"User gets version: {user_version.version}")
"""

import hashlib
import logging
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.strategy.models import CanaryConfig, StrategyVersion, VersionStatus

logger = logging.getLogger(__name__)


class VersionRegistry:
    """Manages strategy version registration, lifecycle, and user routing.

    Enforces business rules:
    - Only ONE active version per strategy at any time
    - Only ONE canary rollout per strategy at any time
    - Multiple shadow versions allowed (for parallel A/B testing)
    - Retired versions are immutable (historical record)

    Attributes:
        session: SQLAlchemy async session for database operations
    """

    def __init__(self, session: AsyncSession):
        """Initialize version registry with database session.

        Args:
            session: SQLAlchemy async session
        """
        self.session = session

    async def register_version(
        self,
        strategy_name: str,
        version: str,
        config: dict[str, Any],
        status: VersionStatus = VersionStatus.SHADOW,
    ) -> StrategyVersion:
        """Register a new strategy version.

        Creates a new version record in SHADOW status by default.
        Use activate_version() or activate_canary() to promote.

        Args:
            strategy_name: Strategy name (fib_rsi, ppo_gold)
            version: Version string (v1.0.0, v2.0.0, vNext)
            config: Strategy-specific configuration (RSI params, fib levels, etc.)
            status: Initial status (default: SHADOW)

        Returns:
            StrategyVersion: Created version record

        Raises:
            ValueError: If version already exists for this strategy
            ValueError: If trying to create ACTIVE version when one already exists

        Example:
            >>> registry = VersionRegistry(session)
            >>> version = await registry.register_version(
            ...     strategy_name="ppo_gold",
            ...     version="v1.5.0",
            ...     config={
            ...         "fast_period": 12,
            ...         "slow_period": 26,
            ...         "signal_period": 9,
            ...         "threshold": 0.5
            ...     }
            ... )
            >>> assert version.status == VersionStatus.SHADOW
        """
        # Check if version already exists
        existing = await self.session.execute(
            select(StrategyVersion).where(
                and_(
                    StrategyVersion.strategy_name == strategy_name,
                    StrategyVersion.version == version,
                )
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError(
                f"Version {version} already exists for strategy {strategy_name}"
            )

        # If registering as ACTIVE, ensure no other active version exists
        if status == VersionStatus.ACTIVE:
            active_version = await self.get_active_version(strategy_name)
            if active_version:
                raise ValueError(
                    f"Cannot register new ACTIVE version: {active_version.version} is already active for {strategy_name}"
                )

        # Create new version
        new_version = StrategyVersion(
            id=str(uuid4()),
            strategy_name=strategy_name,
            version=version,
            status=status,
            config=config,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            activated_at=datetime.utcnow() if status == VersionStatus.ACTIVE else None,
        )

        self.session.add(new_version)
        await self.session.commit()
        await self.session.refresh(new_version)

        logger.info(
            f"Registered version {version} for {strategy_name}",
            extra={
                "strategy_name": strategy_name,
                "version": version,
                "status": status.value,
                "version_id": new_version.id,
            },
        )

        return new_version

    async def get_active_version(self, strategy_name: str) -> StrategyVersion | None:
        """Get currently active version for a strategy.

        Args:
            strategy_name: Strategy name (fib_rsi, ppo_gold)

        Returns:
            StrategyVersion: Active version, or None if no active version

        Example:
            >>> active = await registry.get_active_version("fib_rsi")
            >>> if active:
            ...     print(f"Active version: {active.version}")
            ... else:
            ...     print("No active version")
        """
        result = await self.session.execute(
            select(StrategyVersion).where(
                and_(
                    StrategyVersion.strategy_name == strategy_name,
                    StrategyVersion.status == VersionStatus.ACTIVE,
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_shadow_versions(self, strategy_name: str) -> list[StrategyVersion]:
        """Get all shadow versions for a strategy.

        Args:
            strategy_name: Strategy name (fib_rsi, ppo_gold)

        Returns:
            list[StrategyVersion]: Shadow versions (may be empty)

        Example:
            >>> shadows = await registry.get_shadow_versions("ppo_gold")
            >>> for shadow in shadows:
            ...     print(f"Shadow version: {shadow.version}")
        """
        result = await self.session.execute(
            select(StrategyVersion)
            .where(
                and_(
                    StrategyVersion.strategy_name == strategy_name,
                    StrategyVersion.status == VersionStatus.SHADOW,
                )
            )
            .order_by(StrategyVersion.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_canary_config(self, strategy_name: str) -> CanaryConfig | None:
        """Get active canary configuration for a strategy.

        Args:
            strategy_name: Strategy name (fib_rsi, ppo_gold)

        Returns:
            CanaryConfig: Canary config, or None if no active canary

        Example:
            >>> canary = await registry.get_canary_config("fib_rsi")
            >>> if canary:
            ...     print(f"Canary rollout: {canary.rollout_percent:.1f}%")
        """
        result = await self.session.execute(
            select(CanaryConfig).where(CanaryConfig.strategy_name == strategy_name)
        )
        return result.scalar_one_or_none()

    async def activate_version(
        self, strategy_name: str, version: str
    ) -> StrategyVersion:
        """Promote a version to ACTIVE status.

        Atomically:
        1. Deactivate current active version (move to RETIRED)
        2. Activate specified version

        Args:
            strategy_name: Strategy name
            version: Version to activate

        Returns:
            StrategyVersion: Newly activated version

        Raises:
            ValueError: If version not found
            ValueError: If version already active

        Example:
            >>> # Promote v2.0.0 to active (retires v1.0.0)
            >>> active = await registry.activate_version("fib_rsi", "v2.0.0")
            >>> assert active.status == VersionStatus.ACTIVE
            >>> assert active.activated_at is not None
        """
        # Get version to activate
        result = await self.session.execute(
            select(StrategyVersion).where(
                and_(
                    StrategyVersion.strategy_name == strategy_name,
                    StrategyVersion.version == version,
                )
            )
        )
        new_active = result.scalar_one_or_none()
        if not new_active:
            raise ValueError(
                f"Version {version} not found for strategy {strategy_name}"
            )

        if new_active.status == VersionStatus.ACTIVE:
            raise ValueError(f"Version {version} is already active")

        # Deactivate current active version
        current_active = await self.get_active_version(strategy_name)
        if current_active:
            current_active.status = VersionStatus.RETIRED
            current_active.retired_at = datetime.utcnow()
            current_active.updated_at = datetime.utcnow()

            logger.info(
                f"Retired version {current_active.version} for {strategy_name}",
                extra={
                    "strategy_name": strategy_name,
                    "version": current_active.version,
                    "version_id": current_active.id,
                },
            )

        # Activate new version
        new_active.status = VersionStatus.ACTIVE
        new_active.activated_at = datetime.utcnow()
        new_active.updated_at = datetime.utcnow()

        await self.session.commit()
        await self.session.refresh(new_active)

        logger.info(
            f"Activated version {version} for {strategy_name}",
            extra={
                "strategy_name": strategy_name,
                "version": version,
                "version_id": new_active.id,
            },
        )

        return new_active

    async def activate_canary(
        self, strategy_name: str, version: str, rollout_percent: float
    ) -> tuple[StrategyVersion, CanaryConfig]:
        """Start canary rollout for a version.

        Creates/updates canary configuration and marks version as CANARY status.

        Args:
            strategy_name: Strategy name
            version: Version to canary
            rollout_percent: Percentage of users (0.0 to 100.0)

        Returns:
            tuple[StrategyVersion, CanaryConfig]: Version and canary config

        Raises:
            ValueError: If version not found
            ValueError: If rollout_percent out of range

        Example:
            >>> # Start canary at 5%
            >>> version, canary = await registry.activate_canary(
            ...     "ppo_gold", "v1.5.0", 5.0
            ... )
            >>> assert version.status == VersionStatus.CANARY
            >>> assert canary.rollout_percent == 5.0
        """
        if not 0.0 <= rollout_percent <= 100.0:
            raise ValueError(
                f"rollout_percent must be 0.0-100.0, got {rollout_percent}"
            )

        # Get version to canary
        result = await self.session.execute(
            select(StrategyVersion).where(
                and_(
                    StrategyVersion.strategy_name == strategy_name,
                    StrategyVersion.version == version,
                )
            )
        )
        canary_version = result.scalar_one_or_none()
        if not canary_version:
            raise ValueError(
                f"Version {version} not found for strategy {strategy_name}"
            )

        # Update version status
        canary_version.status = VersionStatus.CANARY
        canary_version.updated_at = datetime.utcnow()

        # Create or update canary config
        existing_canary = await self.get_canary_config(strategy_name)
        if existing_canary:
            existing_canary.version = version
            existing_canary.rollout_percent = rollout_percent
            existing_canary.updated_at = datetime.utcnow()
            canary_config = existing_canary
        else:
            canary_config = CanaryConfig(
                id=str(uuid4()),
                strategy_name=strategy_name,
                version=version,
                rollout_percent=rollout_percent,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                started_at=datetime.utcnow(),
            )
            self.session.add(canary_config)

        await self.session.commit()
        await self.session.refresh(canary_version)
        await self.session.refresh(canary_config)

        logger.info(
            f"Started canary for {strategy_name} {version} at {rollout_percent:.1f}%",
            extra={
                "strategy_name": strategy_name,
                "version": version,
                "rollout_percent": rollout_percent,
                "version_id": canary_version.id,
            },
        )

        return canary_version, canary_config

    async def update_canary_percent(
        self, strategy_name: str, rollout_percent: float
    ) -> CanaryConfig:
        """Update canary rollout percentage.

        Args:
            strategy_name: Strategy name
            rollout_percent: New percentage (0.0 to 100.0)

        Returns:
            CanaryConfig: Updated canary config

        Raises:
            ValueError: If no active canary
            ValueError: If rollout_percent out of range

        Example:
            >>> # Increase canary from 5% to 10%
            >>> canary = await registry.update_canary_percent("fib_rsi", 10.0)
            >>> assert canary.rollout_percent == 10.0
        """
        if not 0.0 <= rollout_percent <= 100.0:
            raise ValueError(
                f"rollout_percent must be 0.0-100.0, got {rollout_percent}"
            )

        canary = await self.get_canary_config(strategy_name)
        if not canary:
            raise ValueError(f"No active canary for strategy {strategy_name}")

        canary.rollout_percent = rollout_percent
        canary.updated_at = datetime.utcnow()

        await self.session.commit()
        await self.session.refresh(canary)

        logger.info(
            f"Updated canary rollout for {strategy_name} to {rollout_percent:.1f}%",
            extra={
                "strategy_name": strategy_name,
                "rollout_percent": rollout_percent,
                "canary_id": canary.id,
            },
        )

        return canary

    async def retire_version(self, strategy_name: str, version: str) -> StrategyVersion:
        """Retire a version (mark as no longer in use).

        Args:
            strategy_name: Strategy name
            version: Version to retire

        Returns:
            StrategyVersion: Retired version

        Raises:
            ValueError: If version not found
            ValueError: If trying to retire active version (use activate_version instead)

        Example:
            >>> retired = await registry.retire_version("ppo_gold", "v1.0.0")
            >>> assert retired.status == VersionStatus.RETIRED
        """
        result = await self.session.execute(
            select(StrategyVersion).where(
                and_(
                    StrategyVersion.strategy_name == strategy_name,
                    StrategyVersion.version == version,
                )
            )
        )
        ver = result.scalar_one_or_none()
        if not ver:
            raise ValueError(
                f"Version {version} not found for strategy {strategy_name}"
            )

        if ver.status == VersionStatus.ACTIVE:
            raise ValueError(
                f"Cannot retire active version {version}. Activate another version first."
            )

        ver.status = VersionStatus.RETIRED
        ver.retired_at = datetime.utcnow()
        ver.updated_at = datetime.utcnow()

        await self.session.commit()
        await self.session.refresh(ver)

        logger.info(
            f"Retired version {version} for {strategy_name}",
            extra={
                "strategy_name": strategy_name,
                "version": version,
                "version_id": ver.id,
            },
        )

        return ver

    async def route_user_to_version(
        self, user_id: str, strategy_name: str
    ) -> StrategyVersion:
        """Route user to appropriate version based on canary rollout.

        Routing logic:
        1. Check if active canary exists
        2. If yes: hash user_id and check if user in canary %
        3. If user in canary: return canary version
        4. Else: return active version

        User assignment is deterministic (same user always gets same version)
        to ensure consistent experience during rollout.

        Args:
            user_id: User ID (UUID string)
            strategy_name: Strategy name

        Returns:
            StrategyVersion: Version to use for this user

        Raises:
            ValueError: If no active version exists

        Example:
            >>> # User routing with 10% canary
            >>> version = await registry.route_user_to_version(
            ...     user_id="user_123",
            ...     strategy_name="fib_rsi"
            ... )
            >>> print(f"User gets version: {version.version}")
        """
        # Check for active canary
        canary = await self.get_canary_config(strategy_name)
        if canary and canary.rollout_percent > 0:
            # Deterministic hash-based assignment
            user_hash = int(hashlib.sha256(user_id.encode()).hexdigest(), 16) % 100
            if user_hash < canary.rollout_percent:
                # User is in canary group
                result = await self.session.execute(
                    select(StrategyVersion).where(
                        and_(
                            StrategyVersion.strategy_name == strategy_name,
                            StrategyVersion.version == canary.version,
                        )
                    )
                )
                canary_version = result.scalar_one_or_none()
                if canary_version:
                    logger.debug(
                        f"Routed user {user_id} to canary version {canary.version}",
                        extra={
                            "user_id": user_id,
                            "strategy_name": strategy_name,
                            "version": canary.version,
                            "user_hash": user_hash,
                            "rollout_percent": canary.rollout_percent,
                        },
                    )
                    return canary_version

        # No canary or user not in canary group → use active version
        active = await self.get_active_version(strategy_name)
        if not active:
            raise ValueError(f"No active version for strategy {strategy_name}")

        logger.debug(
            f"Routed user {user_id} to active version {active.version}",
            extra={
                "user_id": user_id,
                "strategy_name": strategy_name,
                "version": active.version,
            },
        )

        return active

    async def list_all_versions(
        self, strategy_name: str | None = None
    ) -> list[StrategyVersion]:
        """List all versions, optionally filtered by strategy.

        Args:
            strategy_name: Optional strategy filter

        Returns:
            list[StrategyVersion]: All matching versions

        Example:
            >>> # List all fib_rsi versions
            >>> versions = await registry.list_all_versions("fib_rsi")
            >>> for v in versions:
            ...     print(f"{v.version}: {v.status.value}")
        """
        query = select(StrategyVersion)
        if strategy_name:
            query = query.where(StrategyVersion.strategy_name == strategy_name)
        query = query.order_by(
            StrategyVersion.strategy_name, StrategyVersion.created_at.desc()
        )

        result = await self.session.execute(query)
        return list(result.scalars().all())
