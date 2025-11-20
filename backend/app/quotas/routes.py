"""Quota management routes.

Provides API endpoints for viewing quota usage and limits.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.models import User
from backend.app.core.db import get_db
from backend.app.quotas.service import QuotaExceededException, QuotaService
from backend.app.subscriptions.models import SubscriptionTier

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/quotas", tags=["quotas"])


class QuotaStatusResponse(BaseModel):
    """Quota status response model."""

    quota_type: str = Field(..., description="Type of quota (e.g., signals_per_day)")
    current: int = Field(..., description="Current usage count")
    limit: int = Field(..., description="Maximum allowed")
    remaining: int = Field(..., description="Remaining quota")
    reset_at: str = Field(..., description="ISO timestamp when quota resets")


class AllQuotasResponse(BaseModel):
    """Response for all quotas."""

    user_id: str
    tier: str
    quotas: dict[str, dict[str, Any]]


# Stub dependency for getting current user
# TODO: Replace with actual auth dependency from PR-001/PR-002
async def get_current_user() -> User:
    """Get current authenticated user (stub)."""
    # For now, return a stub user
    # In production, this would validate JWT token and load user from DB
    user = User(
        id="test-user-123",
        email="test@example.com",
        password_hash="$2b$12$...",
        role="user",
    )
    return user


# Stub dependency for getting user's subscription tier
async def get_user_tier(user: User = Depends(get_current_user)) -> str:
    """Get user's subscription tier (stub)."""
    # For now, return free tier
    # In production, this would query user's subscription from DB
    return str(SubscriptionTier.FREE.value)


@router.get("/me", response_model=AllQuotasResponse)
async def get_my_quotas(
    user: User = Depends(get_current_user),
    tier: str = Depends(get_user_tier),
    db: AsyncSession = Depends(get_db),
) -> AllQuotasResponse:
    """Get all quota statuses for current user.

    Returns usage, limits, and reset times for all quota types.

    Example response:
    ```json
    {
      "user_id": "user-123",
      "tier": "free",
      "quotas": {
        "signals_per_day": {
          "current": 5,
          "limit": 10,
          "remaining": 5,
          "reset_at": "2025-11-10T00:00:00Z"
        },
        "alerts_per_day": {
          "current": 2,
          "limit": 5,
          "remaining": 3,
          "reset_at": "2025-11-10T00:00:00Z"
        }
      }
    }
    ```
    """
    try:
        service = QuotaService(db)
        quotas = await service.get_all_quotas(user.id, tier)

        # Convert datetime to ISO string
        for _quota_type, status in quotas.items():
            if "reset_at" in status and status["reset_at"]:
                status["reset_at"] = status["reset_at"].isoformat()

        return AllQuotasResponse(
            user_id=user.id,
            tier=tier,
            quotas=quotas,
        )
    except Exception as e:
        logger.error(f"Error fetching quotas for user {user.id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch quota information")


@router.get("/{quota_type}", response_model=QuotaStatusResponse)
async def get_quota_status(
    quota_type: str,
    user: User = Depends(get_current_user),
    tier: str = Depends(get_user_tier),
    db: AsyncSession = Depends(get_db),
) -> QuotaStatusResponse:
    """Get status for a specific quota type.

    Args:
        quota_type: Type of quota (signals_per_day, alerts_per_day, etc.)

    Returns:
        Current usage, limit, remaining, and reset time.

    Example:
    ```
    GET /api/v1/quotas/signals_per_day
    ```

    Response:
    ```json
    {
      "quota_type": "signals_per_day",
      "current": 5,
      "limit": 10,
      "remaining": 5,
      "reset_at": "2025-11-10T00:00:00Z"
    }
    ```
    """
    try:
        service = QuotaService(db)
        status = await service.get_quota_status(user.id, tier, quota_type)

        # Convert datetime to ISO string
        reset_at_str = (
            status["reset_at"].isoformat() if status.get("reset_at") else None
        )

        return QuotaStatusResponse(
            quota_type=quota_type,
            current=status["current"],
            limit=status["limit"],
            remaining=status["remaining"],
            reset_at=reset_at_str,
        )
    except Exception as e:
        logger.error(
            f"Error fetching quota {quota_type} for user {user.id}: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch quota status for {quota_type}"
        )


# Helper function for use in other routes
async def check_quota(
    user_id: str,
    tier: str,
    quota_type: str,
    db: AsyncSession,
    amount: int = 1,
) -> None:
    """Check and consume quota.

    Raises HTTPException with 429 status if quota exceeded.

    Args:
        user_id: User ID
        tier: Subscription tier
        quota_type: Type of quota
        db: Database session
        amount: Amount to consume (default 1)

    Raises:
        HTTPException: 429 if quota exceeded, includes reset_at time
    """
    service = QuotaService(db)

    try:
        await service.check_and_consume(user_id, tier, quota_type, amount)
    except QuotaExceededException as e:
        # Return 429 with problem+json format
        raise HTTPException(
            status_code=429,
            detail={
                "type": "https://api.example.com/errors/quota-exceeded",
                "title": "Quota Exceeded",
                "status": 429,
                "detail": f"Quota limit reached for {e.quota_type}: {e.current}/{e.limit}",
                "quota_type": e.quota_type,
                "current": e.current,
                "limit": e.limit,
                "reset_at": e.reset_at.isoformat(),
            },
        )
