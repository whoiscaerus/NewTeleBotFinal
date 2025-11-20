"""
PR-065: Smart Alert Rules - REST API Routes

API endpoints for creating, managing, and controlling smart alert rules.
"""

import logging
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.alerts.rules import (
    SmartRuleCreate,
    SmartRuleOut,
    SmartRuleService,
    SmartRuleUpdate,
)
from backend.app.auth.dependencies import get_current_user
from backend.app.auth.models import User
from backend.app.core.db import get_db
from backend.app.core.errors import ValidationError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/alerts/rules", tags=["smart-alerts"])

# Prometheus metrics
try:
    from prometheus_client import Counter

    alerts_rule_created_total = Counter(
        "alerts_rule_created_total",
        "Total smart alert rules created",
        ["type"],
    )
    alerts_muted_total = Counter(
        "alerts_muted_total",
        "Total smart alert rules muted",
        ["action"],  # mute/unmute
    )
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    logger.warning("Prometheus client not available - metrics disabled")


@router.post("", status_code=status.HTTP_201_CREATED, response_model=SmartRuleOut)
async def create_smart_rule(
    request: SmartRuleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SmartRuleOut:
    """
    Create a new smart alert rule.

    Supports advanced conditions:
    - cross_above/cross_below: Detects price crossing a level
    - percent_change: Triggers on % change over window
    - rsi_threshold: Triggers on RSI indicator threshold
    - daily_high_touch/daily_low_touch: Triggers on daily extremes

    Args:
        request: Smart rule creation request
        db: Async database session
        current_user: Authenticated user

    Returns:
        SmartRuleOut: Created rule details

    Raises:
        HTTPException: 400 if validation fails, 401 if unauthorized

    Example:
        >>> rule = await create_smart_rule(
        ...     SmartRuleCreate(
        ...         symbol="GOLD",
        ...         rule_type=RuleType.PERCENT_CHANGE,
        ...         threshold_value=2.0,
        ...         window_minutes=60,
        ...         cooldown_minutes=120,
        ...         channels=[NotificationChannel.TELEGRAM, NotificationChannel.EMAIL]
        ...     ),
        ...     db=db_session,
        ...     current_user=user
        ... )
        >>> assert rule.rule_id is not None
    """
    service = SmartRuleService()

    try:
        logger.info(
            f"Creating smart rule for user {current_user.id}",
            extra={
                "user_id": current_user.id,
                "symbol": request.symbol,
                "rule_type": request.rule_type.value,
                "threshold": request.threshold_value,
            },
        )

        result = await service.create_rule(
            db=db,
            user_id=current_user.id,
            symbol=request.symbol,
            rule_type=request.rule_type,
            threshold_value=request.threshold_value,
            window_minutes=request.window_minutes,
            rsi_period=request.rsi_period,
            cooldown_minutes=request.cooldown_minutes,
            channels=request.channels,
        )

        # Increment Prometheus metric
        if PROMETHEUS_AVAILABLE:
            alerts_rule_created_total.labels(type=request.rule_type.value).inc()

        return SmartRuleOut(
            rule_id=result["rule_id"],
            symbol=result["symbol"],
            rule_type=result["rule_type"],
            threshold_value=result["threshold_value"],
            window_minutes=result.get("window_minutes"),
            rsi_period=result.get("rsi_period"),
            cooldown_minutes=result["cooldown_minutes"],
            is_muted=result["is_muted"],
            channels=result["channels"],
            is_active=result["is_active"],
            last_triggered_at=None,
            created_at=result["created_at"],
        )

    except ValidationError as e:
        logger.warning(f"Validation error creating smart rule: {e}")
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        logger.error(f"Unexpected error creating smart rule: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.patch("/{rule_id}", response_model=dict[str, Any])
async def update_smart_rule(
    rule_id: str,
    request: SmartRuleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Update an existing smart alert rule.

    Allows updating threshold, cooldown, mute status, and channels.

    Args:
        rule_id: Rule ID to update
        request: Update request
        db: Async database session
        current_user: Authenticated user

    Returns:
        dict: Updated rule details

    Raises:
        HTTPException: 404 if rule not found, 400 if validation fails
    """
    service = SmartRuleService()

    try:
        logger.info(
            f"Updating smart rule {rule_id}",
            extra={"rule_id": rule_id, "user_id": current_user.id},
        )

        result = await service.update_rule(
            db=db, rule_id=rule_id, user_id=current_user.id, updates=request
        )

        return cast(dict[str, Any], result)

    except ValidationError as e:
        if "not found" in str(e):
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        logger.error(f"Unexpected error updating smart rule: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.post("/{rule_id}/mute", response_model=dict[str, Any])
async def mute_smart_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Mute a smart alert rule (stop notifications).

    Rule continues to evaluate but does not send notifications.

    Args:
        rule_id: Rule ID to mute
        db: Async database session
        current_user: Authenticated user

    Returns:
        dict: Updated rule status

    Raises:
        HTTPException: 404 if rule not found
    """
    service = SmartRuleService()

    try:
        logger.info(
            f"Muting smart rule {rule_id}",
            extra={"rule_id": rule_id, "user_id": current_user.id},
        )

        result = await service.mute_rule(
            db=db, rule_id=rule_id, user_id=current_user.id
        )

        # Increment Prometheus metric
        if PROMETHEUS_AVAILABLE:
            alerts_muted_total.labels(action="mute").inc()

        return cast(dict[str, Any], result)

    except ValidationError as e:
        if "not found" in str(e):
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        logger.error(f"Unexpected error muting smart rule: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.post("/{rule_id}/unmute", response_model=dict[str, Any])
async def unmute_smart_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Unmute a smart alert rule (resume notifications).

    Args:
        rule_id: Rule ID to unmute
        db: Async database session
        current_user: Authenticated user

    Returns:
        dict: Updated rule status

    Raises:
        HTTPException: 404 if rule not found
    """
    service = SmartRuleService()

    try:
        logger.info(
            f"Unmuting smart rule {rule_id}",
            extra={"rule_id": rule_id, "user_id": current_user.id},
        )

        result = await service.unmute_rule(
            db=db, rule_id=rule_id, user_id=current_user.id
        )

        # Increment Prometheus metric
        if PROMETHEUS_AVAILABLE:
            alerts_muted_total.labels(action="unmute").inc()

        return cast(dict[str, Any], result)

    except ValidationError as e:
        if "not found" in str(e):
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        logger.error(f"Unexpected error unmuting smart rule: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )
