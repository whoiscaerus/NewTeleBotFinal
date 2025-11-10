"""
Upsell API routes.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.jwt import get_current_user
from backend.app.auth.models import User
from backend.app.core.db import get_db
from backend.app.upsell.engine import UpsellEngine
from backend.app.upsell.models import (
    Experiment,
    ExperimentStatus,
    Exposure,
    Recommendation,
    Variant,
)
from backend.app.upsell.schema import (
    ConversionEvent,
    ExperimentCreate,
    ExperimentOut,
    ExposureCreate,
    ExposureOut,
    RecommendationOut,
    VariantCreate,
    VariantOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/upsell", tags=["upsell"])


@router.get("/recs", response_model=list[RecommendationOut])
async def get_recommendations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get personalized upgrade recommendations for current user.

    Returns:
        List of recommendations sorted by score (highest first)

    Example:
        >>> GET /api/v1/upsell/recs
        >>> [{"id": "...", "recommendation_type": "plan_upgrade", "score": 0.85, ...}]
    """
    logger.info(f"Fetching recommendations for user {current_user.id}")

    # Initialize engine
    engine = UpsellEngine(db, score_threshold=0.6, lookback_days=30)

    # Score user
    recommendations = await engine.score_user(current_user.id)

    # Persist recommendations
    for rec in recommendations:
        db.add(rec)

    await db.commit()

    # Refresh to get IDs
    for rec in recommendations:
        await db.refresh(rec)

    logger.info(
        f"Generated {len(recommendations)} recommendations for user {current_user.id}"
    )

    return recommendations


@router.post(
    "/exposures", response_model=ExposureOut, status_code=status.HTTP_201_CREATED
)
async def record_exposure(
    exposure_data: ExposureCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Record user exposure to A/B test variant.

    Ensures exposure is logged exactly once per user per experiment.

    Args:
        exposure_data: Exposure details

    Returns:
        Exposure record

    Raises:
        HTTPException: 400 if already exposed, 404 if experiment/variant not found
    """
    logger.info(
        f"Recording exposure for user {current_user.id} to experiment {exposure_data.experiment_id}"
    )

    # Check if already exposed
    existing_query = select(Exposure).where(
        and_(
            Exposure.user_id == current_user.id,
            Exposure.experiment_id == exposure_data.experiment_id,
        )
    )
    existing_result = await db.execute(existing_query)
    existing = existing_result.scalar_one_or_none()

    if existing:
        logger.warning(
            f"User {current_user.id} already exposed to experiment {exposure_data.experiment_id}"
        )
        return existing

    # Validate experiment exists and is active
    exp_query = select(Experiment).where(Experiment.id == exposure_data.experiment_id)
    exp_result = await db.execute(exp_query)
    experiment = exp_result.scalar_one_or_none()

    if not experiment:
        raise HTTPException(status_code=404, detail="Experiment not found")

    if experiment.status != ExperimentStatus.ACTIVE.value:
        raise HTTPException(status_code=400, detail="Experiment not active")

    # Validate variant exists
    variant_query = select(Variant).where(Variant.id == exposure_data.variant_id)
    variant_result = await db.execute(variant_query)
    variant = variant_result.scalar_one_or_none()

    if not variant:
        raise HTTPException(status_code=404, detail="Variant not found")

    # Create exposure
    exposure = Exposure(
        user_id=current_user.id,
        experiment_id=exposure_data.experiment_id,
        variant_id=exposure_data.variant_id,
        recommendation_id=exposure_data.recommendation_id,
        channel=exposure_data.channel,
    )

    db.add(exposure)

    # Update experiment counters
    if variant.is_control:
        experiment.control_exposures += 1
    else:
        experiment.variant_exposures += 1

    # Mark recommendation as shown
    if exposure_data.recommendation_id:
        rec_query = select(Recommendation).where(
            Recommendation.id == exposure_data.recommendation_id
        )
        rec_result = await db.execute(rec_query)
        rec = rec_result.scalar_one_or_none()
        if rec:
            rec.shown = True
            rec.shown_at = datetime.utcnow()

    await db.commit()
    await db.refresh(exposure)

    logger.info(f"Exposure recorded: {exposure.id}")

    return exposure


@router.post("/conversions", status_code=status.HTTP_204_NO_CONTENT)
async def record_conversion(
    conversion_data: ConversionEvent,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Record conversion for an exposure.

    Triggered by successful checkout webhook.

    Args:
        conversion_data: Conversion event details

    Raises:
        HTTPException: 404 if exposure not found, 400 if already converted
    """
    logger.info(f"Recording conversion for exposure {conversion_data.exposure_id}")

    # Get exposure
    exposure_query = select(Exposure).where(
        and_(
            Exposure.id == conversion_data.exposure_id,
            Exposure.user_id == current_user.id,
        )
    )
    exposure_result = await db.execute(exposure_query)
    exposure = exposure_result.scalar_one_or_none()

    if not exposure:
        raise HTTPException(status_code=404, detail="Exposure not found")

    if exposure.converted:
        logger.warning(f"Exposure {exposure.id} already marked as converted")
        return

    # Mark as converted
    exposure.converted = True
    exposure.converted_at = datetime.utcnow()

    # Update experiment counters
    exp_query = select(Experiment).where(Experiment.id == exposure.experiment_id)
    exp_result = await db.execute(exp_query)
    experiment = exp_result.scalar_one_or_none()

    if experiment:
        variant_query = select(Variant).where(Variant.id == exposure.variant_id)
        variant_result = await db.execute(variant_query)
        variant = variant_result.scalar_one_or_none()

        if variant:
            if variant.is_control:
                experiment.control_conversions += 1
            else:
                experiment.variant_conversions += 1

    # Mark recommendation as converted
    if exposure.recommendation_id:
        rec_query = select(Recommendation).where(
            Recommendation.id == exposure.recommendation_id
        )
        rec_result = await db.execute(rec_query)
        rec = rec_result.scalar_one_or_none()
        if rec:
            rec.converted = True
            rec.converted_at = datetime.utcnow()

    await db.commit()

    logger.info(f"Conversion recorded for exposure {exposure.id}")


# Admin endpoints for managing experiments


@router.post(
    "/admin/experiments",
    response_model=ExperimentOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_experiment(
    experiment_data: ExperimentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create A/B test experiment (admin only).

    Args:
        experiment_data: Experiment configuration

    Returns:
        Created experiment
    """
    # TODO: Add admin role check
    logger.info(f"Creating experiment: {experiment_data.name}")

    experiment = Experiment(
        name=experiment_data.name,
        description=experiment_data.description,
        recommendation_type=experiment_data.recommendation_type,
        traffic_split_percent=experiment_data.traffic_split_percent,
        min_sample_size=experiment_data.min_sample_size,
        min_ctr=experiment_data.min_ctr,
        max_duration_days=experiment_data.max_duration_days,
        status=ExperimentStatus.DRAFT.value,
    )

    db.add(experiment)
    await db.commit()
    await db.refresh(experiment)

    logger.info(f"Experiment created: {experiment.id}")

    return experiment


@router.post(
    "/admin/variants", response_model=VariantOut, status_code=status.HTTP_201_CREATED
)
async def create_variant(
    variant_data: VariantCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create variant for experiment (admin only).

    Args:
        variant_data: Variant configuration

    Returns:
        Created variant
    """
    # TODO: Add admin role check
    logger.info(f"Creating variant: {variant_data.name}")

    # Validate experiment exists
    exp_query = select(Experiment).where(Experiment.id == variant_data.experiment_id)
    exp_result = await db.execute(exp_query)
    experiment = exp_result.scalar_one_or_none()

    if not experiment:
        raise HTTPException(status_code=404, detail="Experiment not found")

    variant = Variant(
        experiment_id=variant_data.experiment_id,
        name=variant_data.name,
        headline=variant_data.headline,
        copy=variant_data.copy,
        cta_text=variant_data.cta_text,
        discount_percent=variant_data.discount_percent,
        is_control=variant_data.is_control,
    )

    db.add(variant)
    await db.commit()
    await db.refresh(variant)

    logger.info(f"Variant created: {variant.id}")

    return variant


@router.get("/admin/experiments", response_model=list[ExperimentOut])
async def list_experiments(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List all experiments (admin only).

    Returns:
        List of experiments
    """
    # TODO: Add admin role check
    query = select(Experiment).order_by(Experiment.created_at.desc())
    result = await db.execute(query)
    experiments = result.scalars().all()

    return experiments


@router.patch(
    "/admin/experiments/{experiment_id}/activate", response_model=ExperimentOut
)
async def activate_experiment(
    experiment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Activate experiment (admin only).

    Args:
        experiment_id: Experiment ID

    Returns:
        Updated experiment
    """
    # TODO: Add admin role check
    query = select(Experiment).where(Experiment.id == experiment_id)
    result = await db.execute(query)
    experiment = result.scalar_one_or_none()

    if not experiment:
        raise HTTPException(status_code=404, detail="Experiment not found")

    experiment.status = ExperimentStatus.ACTIVE.value
    experiment.started_at = datetime.utcnow()

    await db.commit()
    await db.refresh(experiment)

    logger.info(f"Experiment {experiment_id} activated")

    return experiment
