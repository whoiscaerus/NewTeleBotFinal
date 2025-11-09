"""Attribution API routes for explainability.

Provides endpoints for:
- Computing feature attribution for individual decisions
- Aggregate feature importance over time periods

Integrates with:
- backend/app/explain/attribution.py: Attribution computation
- backend/app/strategy/logs: Decision logs
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.db import get_db
from backend.app.explain.attribution import (
    compute_attribution,
    compute_feature_importance,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/explain", tags=["explain"])


class AttributionResponse(BaseModel):
    """Attribution result response."""

    decision_id: str
    strategy: str
    symbol: str
    prediction: float
    baseline: float
    prediction_delta: float
    contributions: dict[str, float]
    tolerance: float
    is_valid: bool


class FeatureImportanceResponse(BaseModel):
    """Feature importance response."""

    strategy: str
    lookback_days: int
    importance: dict[str, float]


@router.get("/attribution", response_model=AttributionResponse)
async def get_attribution(
    decision_id: str = Query(..., description="Decision UUID"),
    strategy: str = Query(..., description="Strategy name"),
    tolerance: float = Query(0.01, description="Contribution sum tolerance"),
    session: AsyncSession = Depends(get_db),
) -> AttributionResponse:
    """Compute feature attribution for a decision.

    Returns SHAP-like contributions showing how much each feature
    influenced the prediction.

    Args:
        decision_id: Decision UUID
        strategy: Strategy name (fib_rsi, ppo_gold)
        tolerance: Maximum allowed error in contribution sum
        session: Database session

    Returns:
        AttributionResponse with per-feature contributions

    Raises:
        HTTPException: 404 if decision not found, 422 if strategy unsupported

    Example:
        GET /api/v1/explain/attribution?decision_id=abc-123&strategy=fib_rsi
    """
    from backend.app.observability.metrics import metrics_collector

    try:
        result = await compute_attribution(
            decision_id=decision_id,
            strategy=strategy,
            session=session,
            tolerance=tolerance,
        )

        # Increment telemetry
        metrics_collector.explain_requests_total.inc()

        logger.info(
            f"Attribution computed for decision {decision_id}: "
            f"valid={result.is_valid}, delta={result.prediction_delta:.4f}"
        )

        return AttributionResponse(
            decision_id=result.decision_id,
            strategy=result.strategy,
            symbol=result.symbol,
            prediction=result.prediction,
            baseline=result.baseline,
            prediction_delta=result.prediction_delta,
            contributions=result.contributions,
            tolerance=result.tolerance,
            is_valid=result.is_valid,
        )

    except ValueError as e:
        logger.warning(f"Attribution failed for {decision_id}: {e}")
        raise HTTPException(
            status_code=404 if "not found" in str(e) else 422, detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error computing attribution: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/feature-importance", response_model=FeatureImportanceResponse)
async def get_feature_importance(
    strategy: str = Query(..., description="Strategy name"),
    lookback_days: int = Query(30, ge=1, le=365, description="Days to analyze"),
    session: AsyncSession = Depends(get_db),
) -> FeatureImportanceResponse:
    """Compute aggregate feature importance over time.

    Averages attribution values across recent decisions to understand
    which features are most influential overall.

    Args:
        strategy: Strategy name (fib_rsi, ppo_gold)
        lookback_days: Number of days to analyze (1-365)
        session: Database session

    Returns:
        FeatureImportanceResponse with normalized importance values

    Example:
        GET /api/v1/explain/feature-importance?strategy=fib_rsi&lookback_days=30
    """
    from backend.app.observability.metrics import metrics_collector

    try:
        importance = await compute_feature_importance(
            strategy=strategy,
            session=session,
            lookback_days=lookback_days,
        )

        # Increment telemetry
        metrics_collector.explain_requests_total.inc()

        logger.info(
            f"Feature importance computed for {strategy} "
            f"(lookback={lookback_days}d): {importance}"
        )

        return FeatureImportanceResponse(
            strategy=strategy,
            lookback_days=lookback_days,
            importance=importance,
        )

    except Exception as e:
        logger.error(
            f"Unexpected error computing feature importance: {e}", exc_info=True
        )
        raise HTTPException(status_code=500, detail="Internal server error")
