"""
PR-044: Price Alerts & Notifications - API Routes

REST API endpoints for managing price alerts.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.alerts.service import (
    AlertCreate,
    AlertOut,
    AlertUpdate,
    PriceAlertService,
)
from backend.app.auth.dependencies import get_current_user
from backend.app.auth.models import User
from backend.app.core.db import get_db
from backend.app.core.errors import ValidationError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])
alert_service = PriceAlertService()


@router.post("", status_code=status.HTTP_201_CREATED, response_model=AlertOut)
async def create_alert(
    request: AlertCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AlertOut:
    """
    Create a new price alert.

    Alert triggers when market price crosses the specified level.
    Only one alert per symbol/operator/price combination allowed.

    Args:
        request: Alert creation request
        db: Async database session
        current_user: Authenticated user

    Returns:
        AlertOut: Created alert details

    Raises:
        HTTPException: 400 if validation fails, 422 if invalid symbol, 401 if unauthorized

    Example:
        >>> alert = await create_alert(
        ...     AlertCreate(symbol="GOLD", operator="above", price_level=2000.00),
        ...     db=db_session,
        ...     current_user=user
        ... )
        >>> assert alert.alert_id is not None
    """
    try:
        logger.info(
            f"Creating alert for user {current_user.id}",
            extra={
                "user_id": current_user.id,
                "symbol": request.symbol,
                "operator": request.operator,
                "price_level": request.price_level,
            },
        )

        result = await alert_service.create_alert(
            db=db,
            user_id=current_user.id,
            symbol=request.symbol,
            operator=request.operator,
            price_level=request.price_level,
        )

        return AlertOut(
            alert_id=result["alert_id"],
            symbol=result["symbol"],
            operator=result["operator"],
            price_level=result["price_level"],
            is_active=result["is_active"],
        )

    except ValidationError as e:
        logger.warning(f"Validation error creating alert: {e}")
        # Check if it's a symbol validation error (422) or other (400)
        if "not supported" in str(e):
            raise HTTPException(status_code=422, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        logger.error(f"Unexpected error creating alert: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get("", response_model=list[AlertOut])
async def list_alerts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AlertOut]:
    """
    List all alerts for the authenticated user.

    Args:
        db: Async database session
        current_user: Authenticated user

    Returns:
        List of AlertOut: User's alerts

    Example:
        >>> alerts = await list_alerts(db=db_session, current_user=user)
        >>> assert len(alerts) >= 0
    """
    try:
        logger.info(f"Listing alerts for user {current_user.id}")

        alerts = await alert_service.list_user_alerts(db=db, user_id=current_user.id)

        return [
            AlertOut(
                alert_id=alert["alert_id"],
                symbol=alert["symbol"],
                operator=alert["operator"],
                price_level=alert["price_level"],
                is_active=alert["is_active"],
                last_triggered=alert.get("last_triggered"),
                created_at=alert.get("created_at"),
            )
            for alert in alerts
        ]

    except Exception as e:
        logger.error(f"Error listing alerts: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get("/{alert_id}", response_model=AlertOut)
async def get_alert(
    alert_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AlertOut:
    """
    Get a single alert by ID.

    Args:
        alert_id: Alert identifier
        db: Async database session
        current_user: Authenticated user

    Returns:
        AlertOut: Alert details

    Raises:
        HTTPException: 404 if alert not found

    Example:
        >>> alert = await get_alert("alert-123", db=db_session, current_user=user)
        >>> assert alert.symbol == "GOLD"
    """
    try:
        logger.info(f"Getting alert {alert_id} for user {current_user.id}")

        alert = await alert_service.get_alert(
            db=db, alert_id=alert_id, user_id=current_user.id
        )

        if not alert:
            logger.warning(f"Alert not found: {alert_id}")
            raise HTTPException(status_code=404, detail="Alert not found")

        return AlertOut(
            alert_id=alert["alert_id"],
            symbol=alert["symbol"],
            operator=alert["operator"],
            price_level=alert["price_level"],
            is_active=alert["is_active"],
            last_triggered=alert.get("last_triggered"),
            created_at=alert.get("created_at"),
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Error getting alert {alert_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.put("/{alert_id}", response_model=AlertOut)
async def update_alert(
    alert_id: str,
    request: AlertUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AlertOut:
    """
    Update an alert.

    Can update operator, price_level, or is_active status.

    Args:
        alert_id: Alert identifier
        request: Update request
        db: Async database session
        current_user: Authenticated user

    Returns:
        AlertOut: Updated alert

    Raises:
        HTTPException: 404 if alert not found, 400 if validation fails

    Example:
        >>> updated = await update_alert(
        ...     "alert-123",
        ...     AlertUpdate(is_active=False),
        ...     db=db_session,
        ...     current_user=user
        ... )
        >>> assert updated.is_active == False
    """
    try:
        logger.info(f"Updating alert {alert_id} for user {current_user.id}")

        # Validate input
        if request.operator is not None:
            if request.operator not in ("above", "below"):
                raise ValidationError("Operator must be 'above' or 'below'")

        if request.price_level is not None:
            if request.price_level <= 0 or request.price_level >= 1_000_000:
                raise ValidationError("Price level must be between 0 and 1,000,000")

        # Update in database
        alert = await alert_service.update_alert(
            db=db,
            alert_id=alert_id,
            user_id=current_user.id,
            operator=request.operator,
            price_level=request.price_level,
            is_active=request.is_active,
        )

        if not alert:
            logger.warning(f"Alert not found: {alert_id}")
            raise HTTPException(status_code=404, detail="Alert not found")

        logger.info(f"Alert updated: {alert_id}")

        return AlertOut(
            alert_id=alert["alert_id"],
            symbol=alert["symbol"],
            operator=alert["operator"],
            price_level=alert["price_level"],
            is_active=alert["is_active"],
            last_triggered=alert.get("last_triggered"),
            created_at=alert.get("created_at"),
        )

    except HTTPException:
        raise

    except ValidationError as e:
        logger.warning(f"Validation error updating alert: {e}")
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        logger.error(f"Error updating alert {alert_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.delete("/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert(
    alert_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """
    Delete an alert.

    Args:
        alert_id: Alert identifier
        db: Async database session
        current_user: Authenticated user

    Raises:
        HTTPException: 404 if alert not found

    Example:
        >>> await delete_alert("alert-123", db=db_session, current_user=user)
        >>> # Alert is now deleted
    """
    try:
        logger.info(f"Deleting alert {alert_id} for user {current_user.id}")

        deleted = await alert_service.delete_alert(
            db=db, alert_id=alert_id, user_id=current_user.id
        )

        if not deleted:
            logger.warning(f"Alert not found for deletion: {alert_id}")
            raise HTTPException(status_code=404, detail="Alert not found")

        logger.info(f"Alert deleted: {alert_id}")

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Error deleting alert {alert_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get("/active", response_model=list[AlertOut])
async def list_active_alerts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AlertOut]:
    """
    List only active alerts for the user.

    Subset of list_alerts that shows only is_active=True alerts.

    Args:
        db: Async database session
        current_user: Authenticated user

    Returns:
        List of AlertOut: User's active alerts

    Example:
        >>> active = await list_active_alerts(db=db_session, current_user=user)
        >>> assert all(a.is_active for a in active)
    """
    try:
        logger.info(f"Listing active alerts for user {current_user.id}")

        all_alerts = await alert_service.list_user_alerts(
            db=db, user_id=current_user.id
        )

        active_alerts = [a for a in all_alerts if a["is_active"]]

        return [
            AlertOut(
                alert_id=alert["alert_id"],
                symbol=alert["symbol"],
                operator=alert["operator"],
                price_level=alert["price_level"],
                is_active=alert["is_active"],
                last_triggered=alert.get("last_triggered"),
                created_at=alert.get("created_at"),
            )
            for alert in active_alerts
        ]

    except Exception as e:
        logger.error(f"Error listing active alerts: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )
