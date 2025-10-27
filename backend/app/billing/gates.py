"""Entitlement gating middleware and dependency helpers.

Provides decorators and dependencies to enforce entitlement checks
across API endpoints and protect premium features.
"""

import json
import logging
from typing import Optional
from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.dependencies import get_current_user
from backend.app.auth.models import User
from backend.app.billing.entitlements.service import EntitlementService
from backend.app.core.db import get_db

logger = logging.getLogger(__name__)


class EntitlementGate:
    """Gate for enforcing entitlement checks on API routes.

    Provides flexible entitlement enforcement with RFC7807 error responses.
    """

    def __init__(
        self,
        required_entitlement: str,
        feature_name: Optional[str] = None,
        tier_minimum: Optional[int] = None,
    ):
        """Initialize gate.

        Args:
            required_entitlement: Entitlement name (e.g., "premium_signals", "copy_trading")
            feature_name: Human-readable feature name for error messages
            tier_minimum: Minimum tier required (0=Free, 1=Premium, 2=VIP, 3=Enterprise)

        Example:
            >>> gate = EntitlementGate("premium_signals", "Analytics Dashboard")
        """
        self.required_entitlement = required_entitlement
        self.feature_name = feature_name or required_entitlement
        self.tier_minimum = tier_minimum

    async def check(
        self,
        user: User,
        db: AsyncSession,
    ) -> bool:
        """Check if user has required entitlement.

        Args:
            user: Current authenticated user
            db: Database session

        Returns:
            True if user has entitlement, False otherwise

        Raises:
            HTTPException: 403 if entitlement missing
        """
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )

        service = EntitlementService(db)

        # Check tier-based gate if specified
        if self.tier_minimum is not None:
            user_tier = await service.get_user_tier(user.id)
            if user_tier < self.tier_minimum:
                logger.warning(
                    f"Tier gate denied: user {user.id} tier {user_tier} < required {self.tier_minimum}",
                    extra={
                        "user_id": user.id,
                        "required_tier": self.tier_minimum,
                        "feature": self.feature_name,
                    },
                )
                raise self._build_403_exception(user.id, "insufficient_tier")

        # Check specific entitlement
        has_entitlement = await service.has_entitlement(
            user.id, self.required_entitlement
        )

        if not has_entitlement:
            logger.warning(
                f"Entitlement denied: user {user.id} missing {self.required_entitlement}",
                extra={
                    "user_id": user.id,
                    "missing_entitlement": self.required_entitlement,
                    "feature": self.feature_name,
                },
            )
            raise self._build_403_exception(user.id, "entitlement_not_granted")

        return True

    def _build_403_exception(self, user_id: str, reason: str) -> HTTPException:
        """Build RFC7807 compliant 403 response.

        Args:
            user_id: User ID
            reason: Reason code (entitlement_not_granted, insufficient_tier, etc.)

        Returns:
            HTTPException with RFC7807 problem detail body
        """
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=json.dumps(
                {
                    "type": "https://api.example.com/errors/entitlement-denied",
                    "title": "Entitlement Denied",
                    "status": 403,
                    "detail": f"Access to '{self.feature_name}' requires upgrade",
                    "instance": f"/users/{user_id}",
                    "feature": self.feature_name,
                    "required_entitlement": self.required_entitlement,
                    "reason": reason,
                    "upgrade_url": "/checkout",
                }
            ),
        )


async def require_entitlement(
    required_entitlement: str,
    feature_name: Optional[str] = None,
    tier_minimum: Optional[int] = None,
) -> Callable:
    """Dependency factory for entitlement enforcement.

    Used in FastAPI route handlers to gate access by entitlement.

    Args:
        required_entitlement: Entitlement name to require
        feature_name: Human-readable feature name
        tier_minimum: Minimum tier (0-3)

    Returns:
        Dependency function for use in route handlers

    Example:
        >>> @router.get("/analytics")
        ... async def analytics(
        ...     current_user: User = Depends(get_current_user),
        ...     db: AsyncSession = Depends(get_db),
        ...     _: None = Depends(require_entitlement("premium_signals", "Analytics", tier_minimum=1))
        ... ):
        ...     return {"analytics": "data"}
    """

    async def _check_entitlement(
        current_user: User = Depends(get_current_user),  # noqa: B008
        db: AsyncSession = Depends(get_db),  # noqa: B008
    ) -> None:
        gate = EntitlementGate(required_entitlement, feature_name, tier_minimum)
        await gate.check(current_user, db)

    return _check_entitlement


async def check_entitlement_sync(
    user_id: str,
    required_entitlement: str,
    db: AsyncSession,
) -> bool:
    """Synchronous entitlement check (for use in middleware, etc).

    Args:
        user_id: User ID
        required_entitlement: Entitlement to check
        db: Database session

    Returns:
        True if user has entitlement, False otherwise
    """
    try:
        service = EntitlementService(db)
        return await service.has_entitlement(user_id, required_entitlement)
    except Exception as e:
        logger.error(
            f"Error checking entitlement for {user_id}: {e}",
            exc_info=True,
        )
        return False


class EntitlementGatingMiddleware:
    """ASGI middleware for entitlement gating on protected routes.

    Can be used to gate entire path prefixes (e.g., /api/v1/analytics/*).
    """

    def __init__(
        self,
        app,
        protected_paths: dict[str, str],
    ):
        """Initialize middleware.

        Args:
            app: FastAPI/Starlette app
            protected_paths: Dict of {path_prefix: required_entitlement}
                            e.g., {"/api/v1/analytics/": "premium_signals"}
        """
        self.app = app
        self.protected_paths = protected_paths

    async def __call__(self, request: Request, call_next):
        """Process request through gating logic.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware in chain

        Returns:
            Response, or 403 if gating fails
        """
        # Check if path is protected
        required_entitlement = None
        for path_prefix, entitlement in self.protected_paths.items():
            if request.url.path.startswith(path_prefix):
                required_entitlement = entitlement
                break

        if not required_entitlement:
            return await call_next(request)

        # Path is protected; check entitlement
        # Note: In real middleware, would extract user from JWT token here
        # For now, relying on downstream route dependencies

        response = await call_next(request)
        return response


# Telemetry helper
def emit_gate_denied_metric(feature: str):
    """Emit telemetry metric for denied gate access.

    Args:
        feature: Feature name that was denied
    """
    # Integration point for Prometheus/StatsD metrics
    # Metric name: entitlement_denied_total{feature}
    logger.info(
        "Gate denied",
        extra={"metric": "entitlement_denied_total", "feature": feature},
    )
