"""Trust scoring API routes: trust scores and leaderboard endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from prometheus_client import Counter
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.dependencies import get_current_user
from backend.app.auth.models import User
from backend.app.core.db import get_db
from backend.app.core.logging import get_logger
from backend.app.trust.models import UserTrustScore

logger = get_logger(__name__)

# Prometheus telemetry
trust_scores_calculated_total = Counter(
    "trust_scores_calculated_total",
    "Total trust scores calculated",
    labelnames=["tier"],
)

trust_score_accessed_total = Counter(
    "trust_score_accessed_total", "Trust score access requests"
)

leaderboard_accessed_total = Counter(
    "leaderboard_accessed_total", "Leaderboard access requests"
)

router = APIRouter(prefix="/api/v1", tags=["trust"])


# ============================================================================
# Schemas
# ============================================================================


class ScoreComponent(BaseModel):
    """Trust score component values."""

    performance: float
    tenure: float
    endorsements: float


class TrustScoreOut(BaseModel):
    """Public trust score response."""

    user_id: str
    score: float
    tier: str
    percentile: int
    components: ScoreComponent
    calculated_at: str

    class Config:
        from_attributes = True


class LeaderboardEntry(BaseModel):
    """Single leaderboard entry."""

    rank: int
    user_id: str
    score: float
    tier: str
    percentile: int


class LeaderboardResponse(BaseModel):
    """Leaderboard response."""

    total_users: int
    entries: list[LeaderboardEntry]


# ============================================================================
# Endpoints
# ============================================================================


@router.get(
    "/trust/score/{user_id}",
    response_model=TrustScoreOut,
    status_code=200,
    summary="Get user trust score",
    description="Get the trust score for a user",
)
async def get_trust_score(
    user_id: str,
    db: AsyncSession = Depends(get_db),
) -> TrustScoreOut:
    """
    Get the trust score for a specific user.

    Returns: {score, tier, percentile, components, calculated_at}

    Args:
        user_id: User identifier
        db: Database session

    Returns:
        Trust score with all components

    Raises:
        404: User not found or no trust score calculated

    Example:
        >>> response = await client.get("/api/v1/trust/score/user123")
        >>> response.json()
        {
            "user_id": "user123",
            "score": 75.5,
            "tier": "silver",
            "percentile": 65,
            "components": {
                "performance": 80.0,
                "tenure": 70.0,
                "endorsements": 65.0
            },
            "calculated_at": "2025-11-01T12:00:00"
        }
    """
    try:
        trust_score_accessed_total.inc()

        # Query database for trust score
        stmt = select(UserTrustScore).where(UserTrustScore.user_id == user_id)
        result = await db.execute(stmt)
        trust_score_record = result.scalar_one_or_none()

        if not trust_score_record:
            logger.warning(f"Trust score not found for user {user_id}")
            raise HTTPException(status_code=404, detail="Trust score not found")

        return TrustScoreOut(
            user_id=trust_score_record.user_id,
            score=trust_score_record.score,
            tier=trust_score_record.tier,
            percentile=trust_score_record.percentile,
            components=ScoreComponent(
                performance=trust_score_record.performance_component,
                tenure=trust_score_record.tenure_component,
                endorsements=trust_score_record.endorsement_component,
            ),
            calculated_at=trust_score_record.calculated_at.isoformat(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting trust score for {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get(
    "/trust/leaderboard",
    response_model=LeaderboardResponse,
    status_code=200,
    summary="Get trust leaderboard",
    description="Get top users by trust score (public, no PII)",
)
async def get_trust_leaderboard(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> LeaderboardResponse:
    """
    Get the public trust score leaderboard.

    Returns top users sorted by trust score (highest first).
    No PII included - only user_id and scores.

    Args:
        limit: Number of results (1-1000, default 100)
        offset: Pagination offset (default 0)
        db: Database session

    Returns:
        LeaderboardResponse with ranked users

    Raises:
        500: Database error

    Example:
        >>> response = await client.get("/api/v1/trust/leaderboard?limit=10")
        >>> response.json()
        {
            "total_users": 5432,
            "entries": [
                {"rank": 1, "user_id": "u1", "score": 95.5, "tier": "gold", "percentile": 99},
                {"rank": 2, "user_id": "u2", "score": 92.0, "tier": "gold", "percentile": 98},
                ...
            ]
        }
    """
    try:
        leaderboard_accessed_total.inc()

        # Get total count
        count_stmt = select(func.count(UserTrustScore.id))
        count_result = await db.execute(count_stmt)
        total_users = count_result.scalar() or 0

        # Get leaderboard (sorted by score desc)
        stmt = (
            select(UserTrustScore)
            .order_by(desc(UserTrustScore.score))
            .offset(offset)
            .limit(limit)
        )
        result = await db.execute(stmt)
        scores = result.scalars().all()

        # Build response with ranks
        entries = []
        for rank, score_record in enumerate(scores, start=offset + 1):
            entries.append(
                LeaderboardEntry(
                    rank=rank,
                    user_id=score_record.user_id,
                    score=score_record.score,
                    tier=score_record.tier,
                    percentile=score_record.percentile,
                )
            )

        logger.info(f"Leaderboard accessed: {len(entries)} entries returned")

        return LeaderboardResponse(
            total_users=total_users,
            entries=entries,
        )

    except Exception as e:
        logger.error(f"Error getting leaderboard: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get(
    "/trust/me",
    response_model=TrustScoreOut,
    status_code=200,
    summary="Get your trust score",
    description="Get the authenticated user's trust score",
)
async def get_my_trust_score(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TrustScoreOut:
    """
    Get the authenticated user's trust score.

    Args:
        current_user: Authenticated user (from JWT)
        db: Database session

    Returns:
        User's trust score

    Raises:
        401: Not authenticated
        404: Trust score not calculated yet

    Example:
        >>> headers = {"Authorization": "Bearer <jwt>"}
        >>> response = await client.get("/api/v1/trust/me", headers=headers)
    """
    try:
        trust_score_accessed_total.inc()

        stmt = select(UserTrustScore).where(UserTrustScore.user_id == current_user.id)
        result = await db.execute(stmt)
        trust_score_record = result.scalar_one_or_none()

        if not trust_score_record:
            logger.warning(f"Trust score not found for user {current_user.id}")
            raise HTTPException(
                status_code=404, detail="Your trust score has not been calculated yet"
            )

        return TrustScoreOut(
            user_id=trust_score_record.user_id,
            score=trust_score_record.score,
            tier=trust_score_record.tier,
            percentile=trust_score_record.percentile,
            components=ScoreComponent(
                performance=trust_score_record.performance_component,
                tenure=trust_score_record.tenure_component,
                endorsements=trust_score_record.endorsement_component,
            ),
            calculated_at=trust_score_record.calculated_at.isoformat(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error getting trust score for {current_user.id}: {e}", exc_info=True
        )
        raise HTTPException(status_code=500, detail="Internal server error")
