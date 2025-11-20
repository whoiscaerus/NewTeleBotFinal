"""Public trust index API routes - PR-050."""

from fastapi import APIRouter, Depends, HTTPException, Query
from prometheus_client import Counter
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.db import get_db
from backend.app.core.logging import get_logger
from backend.app.public.trust_index import (
    PublicTrustIndexRecord,
    PublicTrustIndexSchema,
    calculate_trust_index,
)

logger = get_logger(__name__)

# Prometheus telemetry
trust_index_calculated_total = Counter(
    "trust_index_calculated_total",
    "Total trust indexes calculated",
    labelnames=["trust_band"],
)

trust_index_accessed_total = Counter(
    "trust_index_accessed_total", "Trust index access requests"
)

router = APIRouter(prefix="/api/v1", tags=["public"])


@router.get(
    "/public/trust-index/{user_id}",
    response_model=PublicTrustIndexSchema,
    status_code=200,
    summary="Get public trust index",
    description="Get verified trader metrics for public display (no sensitive data)",
)
async def get_public_trust_index(
    user_id: str,
    db: AsyncSession = Depends(get_db),
) -> PublicTrustIndexSchema:
    """
    Get public trust index for a user.

    Returns verified trader metrics including:
    - Accuracy metric (win rate)
    - Average risk/reward ratio
    - Percentage of verified trades
    - Trust band (unverified/verified/expert/elite)

    This endpoint is public and contains only aggregated metrics,
    no sensitive user information.

    Args:
        user_id: User identifier
        db: Database session

    Returns:
        PublicTrustIndexSchema with metrics and trust band

    Raises:
        404: User not found
        500: Calculation error

    Example:
        >>> response = await client.get("/api/v1/public/trust-index/user123")
        >>> response.json()
        {
            "user_id": "user123",
            "accuracy_metric": 0.65,
            "average_rr": 1.8,
            "verified_trades_pct": 65,
            "trust_band": "expert",
            "calculated_at": "2025-11-01T12:00:00",
            "valid_until": "2025-11-02T12:00:00"
        }
    """
    try:
        trust_index_accessed_total.inc()

        # Calculate or fetch trust index
        index = await calculate_trust_index(user_id, db)

        if not index:
            logger.warning(f"Trust index not found for user {user_id}")
            raise HTTPException(status_code=404, detail="User not found")

        # Increment telemetry counter
        trust_index_calculated_total.labels(trust_band=index.trust_band).inc()

        logger.info(
            f"Trust index accessed for user {user_id}",
            extra={
                "user_id": user_id,
                "trust_band": index.trust_band,
                "accuracy": index.accuracy_metric,
            },
        )

        return index

    except HTTPException:
        raise
    except ValueError as e:
        if "not found" in str(e).lower():
            logger.warning(f"User not found: {user_id}")
            raise HTTPException(status_code=404, detail="User not found")
        logger.error(f"Validation error for user {user_id}: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting trust index for {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get(
    "/public/trust-index",
    response_model=dict,
    status_code=200,
    summary="Get public trust index stats",
    description="Get aggregate statistics on public trust indexes",
)
async def get_trust_index_stats(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(10, ge=1, le=100),
) -> dict:
    """
    Get aggregate statistics and top users by trust index.

    Returns:
    - Total indexes calculated
    - Distribution by trust band
    - Top users by accuracy metric
    - Top users by R/R ratio

    Args:
        db: Database session
        limit: Number of top users to return (1-100, default 10)

    Returns:
        Dictionary with aggregate stats and top users

    Example:
        >>> response = await client.get("/api/v1/public/trust-index?limit=10")
        >>> response.json()
        {
            "total_indexes": 5432,
            "distribution": {
                "unverified": 1200,
                "verified": 2000,
                "expert": 1500,
                "elite": 732
            },
            "top_by_accuracy": [...],
            "top_by_rr": [...]
        }
    """
    try:
        from sqlalchemy import desc, func, select

        # Get total count
        stmt = select(func.count(PublicTrustIndexRecord.id))
        result = await db.execute(stmt)
        total = result.scalar() or 0

        # Get distribution by band
        stmt = select(
            PublicTrustIndexRecord.trust_band, func.count(PublicTrustIndexRecord.id)
        ).group_by(PublicTrustIndexRecord.trust_band)
        result = await db.execute(stmt)
        distribution = dict(result.all())

        # Get top by accuracy
        stmt = (
            select(PublicTrustIndexRecord)
            .order_by(desc(PublicTrustIndexRecord.accuracy_metric))
            .limit(limit)
        )
        result = await db.execute(stmt)
        top_accuracy: list[PublicTrustIndexRecord] = list(result.scalars().all())

        # Get top by R/R
        stmt = (
            select(PublicTrustIndexRecord)
            .order_by(desc(PublicTrustIndexRecord.average_rr))
            .limit(limit)
        )
        result = await db.execute(stmt)
        top_rr: list[PublicTrustIndexRecord] = list(result.scalars().all())

        logger.info(
            "Trust index stats accessed",
            extra={
                "total_indexes": total,
                "distribution": distribution,
            },
        )

        return {
            "total_indexes": total,
            "distribution": distribution,
            "top_by_accuracy": [
                {
                    "user_id": r.user_id,
                    "accuracy_metric": r.accuracy_metric,
                    "trust_band": r.trust_band,
                }
                for r in top_accuracy
            ],
            "top_by_rr": [
                {
                    "user_id": r.user_id,
                    "average_rr": r.average_rr,
                    "trust_band": r.trust_band,
                }
                for r in top_rr
            ],
        }

    except Exception as e:
        logger.error(f"Error getting trust index stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
