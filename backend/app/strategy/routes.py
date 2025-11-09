"""API routes for strategy versioning and canary rollout management.

Owner-only endpoints for:
- Managing strategy versions (register, activate, retire)
- Configuring canary rollouts (% of users)
- Viewing shadow decision logs
- Comparing shadow vs active performance

All endpoints require OWNER or ADMIN role.

Example:
    >>> # Start canary rollout at 5%
    >>> curl -X PATCH http://localhost:8000/api/v1/strategy/rollout \\
    ...      -H "Authorization: Bearer <owner_token>" \\
    ...      -d '{"strategy_name": "fib_rsi", "version": "v2.0.0", "rollout_percent": 5.0}'
    >>>
    >>> # Increase canary to 10%
    >>> curl -X PATCH http://localhost:8000/api/v1/strategy/rollout \\
    ...      -H "Authorization: Bearer <owner_token>" \\
    ...      -d '{"strategy_name": "fib_rsi", "version": "v2.0.0", "rollout_percent": 10.0}'
    >>>
    >>> # Promote to active (100% rollout)
    >>> curl -X POST http://localhost:8000/api/v1/strategy/versions/{version_id}/activate \\
    ...      -H "Authorization: Bearer <owner_token>"
"""

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, validator
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.models import User, UserRole
from backend.app.core.db import get_db
from backend.app.strategy.models import VersionStatus
from backend.app.strategy.shadow import ShadowExecutor
from backend.app.strategy.versioning import VersionRegistry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/strategy", tags=["strategy-versioning"])


# ========== Request/Response Models ==========


class RolloutRequest(BaseModel):
    """Request to configure canary rollout percentage."""

    strategy_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Strategy name (fib_rsi, ppo_gold)",
    )
    version: str = Field(
        ..., min_length=1, max_length=50, description="Version string (v1.0.0, v2.0.0)"
    )
    rollout_percent: float = Field(
        ..., ge=0.0, le=100.0, description="Rollout percentage (0.0 to 100.0)"
    )

    @validator("rollout_percent")
    def validate_percent(cls, v):
        """Validate rollout percentage is valid."""
        if not 0.0 <= v <= 100.0:
            raise ValueError("rollout_percent must be between 0.0 and 100.0")
        return v


class VersionRegisterRequest(BaseModel):
    """Request to register a new strategy version."""

    strategy_name: str = Field(..., min_length=1, max_length=100)
    version: str = Field(..., min_length=1, max_length=50)
    config: dict[str, Any] = Field(
        ..., description="Strategy configuration (params, thresholds, etc.)"
    )
    status: str = Field(default="shadow", description="Initial status (shadow, active)")

    @validator("status")
    def validate_status(cls, v):
        """Validate status is valid VersionStatus value."""
        valid_statuses = [s.value for s in VersionStatus]
        if v not in valid_statuses:
            raise ValueError(f"status must be one of: {', '.join(valid_statuses)}")
        return v


class VersionResponse(BaseModel):
    """Response for strategy version."""

    id: str
    strategy_name: str
    version: str
    status: str
    config: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    activated_at: datetime | None
    retired_at: datetime | None

    class Config:
        from_attributes = True


class CanaryResponse(BaseModel):
    """Response for canary configuration."""

    id: str
    strategy_name: str
    version: str
    rollout_percent: float
    created_at: datetime
    updated_at: datetime
    started_at: datetime

    class Config:
        from_attributes = True


class ShadowComparisonRequest(BaseModel):
    """Request to compare shadow vs active decisions."""

    shadow_version: str = Field(..., min_length=1, max_length=50)
    strategy_name: str = Field(..., min_length=1, max_length=100)
    symbol: str = Field(..., min_length=1, max_length=20)
    days: int = Field(
        default=7, ge=1, le=90, description="Number of days to compare (1-90)"
    )


# ========== Dependencies ==========


async def get_current_user() -> User:
    """Dependency to get current authenticated user.

    In production, this would decode JWT token and fetch user.
    For now, returns mock owner user.

    TODO: Replace with actual JWT auth dependency
    """
    # Mock owner user for testing
    mock_user = User(
        id="owner_123",
        email="owner@example.com",
        password_hash="hashed",
        role=UserRole.OWNER,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    return mock_user


def require_owner_or_admin(current_user: User = Depends(get_current_user)) -> User:
    """Dependency to require OWNER or ADMIN role.

    Args:
        current_user: Authenticated user from JWT

    Returns:
        User: User with OWNER or ADMIN role

    Raises:
        HTTPException: 403 if user is not OWNER or ADMIN

    Example:
        >>> @router.post("/admin-only")
        >>> async def admin_endpoint(user: User = Depends(require_owner_or_admin)):
        ...     # Only OWNER or ADMIN can access
        ...     pass
    """
    if current_user.role not in (UserRole.OWNER, UserRole.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only OWNER or ADMIN can manage strategy versions",
        )
    return current_user


# ========== Endpoints ==========


@router.post(
    "/versions", response_model=VersionResponse, status_code=status.HTTP_201_CREATED
)
async def register_version(
    request: VersionRegisterRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_owner_or_admin),
):
    """Register a new strategy version.

    Creates new version in SHADOW status by default.
    Use activate or canary endpoints to promote.

    Args:
        request: Version registration request
        db: Database session
        current_user: Authenticated OWNER/ADMIN user

    Returns:
        VersionResponse: Created version

    Raises:
        400: If version already exists
        403: If user is not OWNER/ADMIN
        422: If request validation fails

    Example:
        >>> # Register v2.0.0 in shadow mode
        >>> POST /api/v1/strategy/versions
        >>> {
        ...     "strategy_name": "fib_rsi",
        ...     "version": "v2.0.0",
        ...     "config": {
        ...         "rsi_period": 14,
        ...         "rsi_overbought": 70,
        ...         "rsi_oversold": 30
        ...     },
        ...     "status": "shadow"
        ... }
    """
    try:
        registry = VersionRegistry(db)
        version = await registry.register_version(
            strategy_name=request.strategy_name,
            version=request.version,
            config=request.config,
            status=VersionStatus(request.status),
        )

        logger.info(
            f"Version registered via API: {request.strategy_name} {request.version}",
            extra={
                "strategy_name": request.strategy_name,
                "version": request.version,
                "user_id": current_user.id,
                "version_id": version.id,
            },
        )

        return VersionResponse(
            id=version.id,
            strategy_name=version.strategy_name,
            version=version.version,
            status=version.status.value,
            config=version.config,
            created_at=version.created_at,
            updated_at=version.updated_at,
            activated_at=version.activated_at,
            retired_at=version.retired_at,
        )

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/versions", response_model=list[VersionResponse])
async def list_versions(
    strategy_name: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_owner_or_admin),
):
    """List all strategy versions.

    Args:
        strategy_name: Optional filter by strategy
        db: Database session
        current_user: Authenticated OWNER/ADMIN user

    Returns:
        list[VersionResponse]: All matching versions

    Example:
        >>> # List all fib_rsi versions
        >>> GET /api/v1/strategy/versions?strategy_name=fib_rsi
    """
    registry = VersionRegistry(db)
    versions = await registry.list_all_versions(strategy_name=strategy_name)

    return [
        VersionResponse(
            id=v.id,
            strategy_name=v.strategy_name,
            version=v.version,
            status=v.status.value,
            config=v.config,
            created_at=v.created_at,
            updated_at=v.updated_at,
            activated_at=v.activated_at,
            retired_at=v.retired_at,
        )
        for v in versions
    ]


@router.post("/versions/{version_id}/activate", response_model=VersionResponse)
async def activate_version(
    version_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_owner_or_admin),
):
    """Promote version to ACTIVE status (100% rollout).

    Atomically deactivates current active version and activates specified version.

    Args:
        version_id: Version ID to activate
        db: Database session
        current_user: Authenticated OWNER/ADMIN user

    Returns:
        VersionResponse: Activated version

    Raises:
        400: If version already active or not found
        403: If user is not OWNER/ADMIN

    Example:
        >>> # Promote v2.0.0 to active (retires v1.0.0)
        >>> POST /api/v1/strategy/versions/{version_id}/activate
    """
    try:
        registry = VersionRegistry(db)

        # Get version to activate
        versions = await registry.list_all_versions()
        target_version = next((v for v in versions if v.id == version_id), None)
        if not target_version:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Version {version_id} not found",
            )

        # Activate version
        activated = await registry.activate_version(
            strategy_name=target_version.strategy_name, version=target_version.version
        )

        logger.info(
            f"Version activated via API: {activated.strategy_name} {activated.version}",
            extra={
                "strategy_name": activated.strategy_name,
                "version": activated.version,
                "user_id": current_user.id,
                "version_id": activated.id,
            },
        )

        return VersionResponse(
            id=activated.id,
            strategy_name=activated.strategy_name,
            version=activated.version,
            status=activated.status.value,
            config=activated.config,
            created_at=activated.created_at,
            updated_at=activated.updated_at,
            activated_at=activated.activated_at,
            retired_at=activated.retired_at,
        )

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.patch("/rollout", response_model=CanaryResponse)
async def configure_canary_rollout(
    request: RolloutRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_owner_or_admin),
):
    """Configure canary rollout percentage.

    Creates or updates canary configuration for gradual rollout.

    Args:
        request: Rollout configuration request
        db: Database session
        current_user: Authenticated OWNER/ADMIN user

    Returns:
        CanaryResponse: Canary configuration

    Raises:
        400: If version not found or invalid percentage
        403: If user is not OWNER/ADMIN

    Example:
        >>> # Start canary at 5%
        >>> PATCH /api/v1/strategy/rollout
        >>> {
        ...     "strategy_name": "fib_rsi",
        ...     "version": "v2.0.0",
        ...     "rollout_percent": 5.0
        ... }
        >>>
        >>> # Increase to 10%
        >>> PATCH /api/v1/strategy/rollout
        >>> {
        ...     "strategy_name": "fib_rsi",
        ...     "version": "v2.0.0",
        ...     "rollout_percent": 10.0
        ... }
    """
    try:
        registry = VersionRegistry(db)

        # Check if canary already exists
        existing_canary = await registry.get_canary_config(request.strategy_name)

        if existing_canary and existing_canary.version == request.version:
            # Update existing canary
            canary = await registry.update_canary_percent(
                strategy_name=request.strategy_name,
                rollout_percent=request.rollout_percent,
            )
        else:
            # Create new canary
            version, canary = await registry.activate_canary(
                strategy_name=request.strategy_name,
                version=request.version,
                rollout_percent=request.rollout_percent,
            )

        logger.info(
            f"Canary rollout configured via API: {request.strategy_name} {request.version} @ {request.rollout_percent:.1f}%",
            extra={
                "strategy_name": request.strategy_name,
                "version": request.version,
                "rollout_percent": request.rollout_percent,
                "user_id": current_user.id,
                "canary_id": canary.id,
            },
        )

        return CanaryResponse(
            id=canary.id,
            strategy_name=canary.strategy_name,
            version=canary.version,
            rollout_percent=canary.rollout_percent,
            created_at=canary.created_at,
            updated_at=canary.updated_at,
            started_at=canary.started_at,
        )

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/shadow-comparison", response_model=dict[str, Any])
async def compare_shadow_vs_active(
    request: ShadowComparisonRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_owner_or_admin),
):
    """Compare shadow version decisions vs active version outcomes.

    Analyzes decision patterns over time window to validate shadow version.

    Args:
        request: Comparison request
        db: Database session
        current_user: Authenticated OWNER/ADMIN user

    Returns:
        dict: Comparison metrics (signal counts, divergence rate, etc.)

    Example:
        >>> # Compare v2.0.0 (shadow) vs v1.0.0 (active) for GOLD over 7 days
        >>> POST /api/v1/strategy/shadow-comparison
        >>> {
        ...     "shadow_version": "v2.0.0",
        ...     "strategy_name": "fib_rsi",
        ...     "symbol": "GOLD",
        ...     "days": 7
        ... }
        >>>
        >>> Response:
        >>> {
        ...     "shadow_signal_count": 15,
        ...     "active_signal_count": 12,
        ...     "divergence_rate": 20.0,
        ...     ...
        ... }
    """
    executor = ShadowExecutor(db)

    comparison = await executor.compare_shadow_vs_active(
        shadow_version=request.shadow_version,
        strategy_name=request.strategy_name,
        symbol=request.symbol,
        days=request.days,
    )

    logger.info(
        f"Shadow comparison requested via API: {request.strategy_name} {request.symbol}",
        extra={
            "shadow_version": request.shadow_version,
            "strategy_name": request.strategy_name,
            "symbol": request.symbol,
            "days": request.days,
            "user_id": current_user.id,
            "shadow_signals": comparison["shadow_signal_count"],
            "active_signals": comparison["active_signal_count"],
        },
    )

    return comparison


@router.get("/canary", response_model=CanaryResponse | None)
async def get_canary_config(
    strategy_name: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_owner_or_admin),
):
    """Get active canary configuration for a strategy.

    Args:
        strategy_name: Strategy name (fib_rsi, ppo_gold)
        db: Database session
        current_user: Authenticated OWNER/ADMIN user

    Returns:
        CanaryResponse | None: Canary config, or None if no active canary

    Example:
        >>> GET /api/v1/strategy/canary?strategy_name=fib_rsi
    """
    registry = VersionRegistry(db)
    canary = await registry.get_canary_config(strategy_name)

    if not canary:
        return None

    return CanaryResponse(
        id=canary.id,
        strategy_name=canary.strategy_name,
        version=canary.version,
        rollout_percent=canary.rollout_percent,
        created_at=canary.created_at,
        updated_at=canary.updated_at,
        started_at=canary.started_at,
    )
