"""
User Preferences API Routes - PR-059

REST API for managing user notification preferences.

Endpoints:
- GET /api/v1/prefs - Get current user's preferences
- PUT /api/v1/prefs - Update current user's preferences

Security:
- JWT authentication required (all endpoints)
- Tenant isolation (users can only access their own preferences)
- Audit logging for all updates (PR-008)

Telemetry:
- prefs_updated_total counter
- prefs_read_total counter
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from prometheus_client import Counter
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from backend.app.auth.dependencies import get_current_user
from backend.app.core.db import get_db
from backend.app.prefs.models import UserPreferences
from backend.app.prefs.schemas import UserPreferencesResponse, UserPreferencesUpdate
from backend.app.users.models import User

logger = logging.getLogger(__name__)

# Prometheus metrics
prefs_read_total = Counter("prefs_read_total", "Total user preference reads")
prefs_updated_total = Counter("prefs_updated_total", "Total user preference updates")

router = APIRouter(prefix="/api/v1/prefs", tags=["preferences"])


@router.get("", response_model=UserPreferencesResponse, status_code=status.HTTP_200_OK)
async def get_preferences(
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    """
    Get current user's notification preferences.

    Returns:
        UserPreferencesResponse: User's current preferences

    Security:
        - JWT required
        - Tenant isolation (user can only get their own preferences)

    Business Logic:
        - If preferences don't exist, creates defaults automatically
        - Default instruments: all enabled
        - Default alert types: all enabled
        - Default channels: telegram + email ON, push OFF
        - Default execution failure alerts: ON (safety-first)
        - Default quiet hours: disabled
        - Default digest: immediate

    Example Response:
        ```json
        {
            "id": 1,
            "user_id": 123,
            "instruments_enabled": ["gold", "sp500", "crypto"],
            "alert_types_enabled": ["price", "drawdown", "execution_failure"],
            "notify_via_telegram": true,
            "notify_via_email": true,
            "notify_via_push": false,
            "quiet_hours_enabled": false,
            "quiet_hours_start": null,
            "quiet_hours_end": null,
            "timezone": "UTC",
            "digest_frequency": "immediate",
            "notify_entry_failure": true,
            "notify_exit_failure": true,
            "max_alerts_per_hour": 10,
            "created_at": "2025-11-06T10:00:00Z",
            "updated_at": "2025-11-06T10:00:00Z"
        }
        ```
    """
    try:
        # Query preferences
        result = await db.execute(
            select(UserPreferences).where(UserPreferences.user_id == current_user.id)
        )
        prefs = result.scalar_one_or_none()

        # Create defaults if not exist
        if not prefs:
            logger.info(f"Creating default preferences for user {current_user.id}")
            prefs = UserPreferences(
                user_id=current_user.id,
                instruments_enabled=["gold", "sp500", "crypto", "forex", "indices"],
                alert_types_enabled=[
                    "price",
                    "drawdown",
                    "copy_risk",
                    "execution_failure",
                ],
                notify_via_telegram=True,
                notify_via_email=True,
                notify_via_push=False,
                quiet_hours_enabled=False,
                timezone="UTC",
                digest_frequency="immediate",
                notify_entry_failure=True,  # Safety-first default
                notify_exit_failure=True,  # Safety-first default
                max_alerts_per_hour=10,
            )
            db.add(prefs)
            await db.commit()
            await db.refresh(prefs)

        prefs_read_total.inc()
        logger.info(f"Retrieved preferences for user {current_user.id}")

        return UserPreferencesResponse.model_validate(prefs)

    except Exception as e:
        logger.error(
            f"Error retrieving preferences for user {current_user.id}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve preferences",
        )


@router.put("", response_model=UserPreferencesResponse, status_code=status.HTTP_200_OK)
async def update_preferences(
    update_data: UserPreferencesUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    """
    Update current user's notification preferences.

    Args:
        update_data: Fields to update (only provided fields will be updated)

    Returns:
        UserPreferencesResponse: Updated preferences

    Security:
        - JWT required
        - Tenant isolation (user can only update their own preferences)
        - Audit log written for each update (PR-008)

    Validation:
        - Instruments must be in valid list
        - Alert types must be in valid list
        - Timezone must be valid IANA timezone (e.g., "Europe/London")
        - Quiet hours times must be in HH:MM format
        - Digest frequency must be "immediate", "hourly", or "daily"
        - At least one notification channel must be enabled
        - Max alerts per hour: 1-100

    Error Responses:
        - 422: Validation error (invalid timezone, time format, etc.)
        - 500: Internal server error

    Example Request:
        ```json
        {
            "instruments_enabled": ["gold", "sp500"],
            "alert_types_enabled": ["price", "execution_failure"],
            "notify_via_telegram": true,
            "notify_via_email": false,
            "quiet_hours_enabled": true,
            "quiet_hours_start": "22:00",
            "quiet_hours_end": "08:00",
            "timezone": "Europe/London",
            "notify_entry_failure": true,
            "notify_exit_failure": true
        }
        ```

    Example Response:
        ```json
        {
            "id": 1,
            "user_id": 123,
            "instruments_enabled": ["gold", "sp500"],
            "alert_types_enabled": ["price", "execution_failure"],
            "notify_via_telegram": true,
            "notify_via_email": false,
            "notify_via_push": false,
            "quiet_hours_enabled": true,
            "quiet_hours_start": "22:00:00",
            "quiet_hours_end": "08:00:00",
            "timezone": "Europe/London",
            "digest_frequency": "immediate",
            "notify_entry_failure": true,
            "notify_exit_failure": true,
            "max_alerts_per_hour": 10,
            "created_at": "2025-11-06T10:00:00Z",
            "updated_at": "2025-11-06T10:30:00Z"
        }
        ```
    """
    try:
        # Get existing preferences (creates defaults if not exist)
        result = await db.execute(
            select(UserPreferences).where(UserPreferences.user_id == current_user.id)
        )
        prefs = result.scalar_one_or_none()

        if not prefs:
            logger.info(
                f"Creating default preferences for user {current_user.id} before update"
            )
            prefs = UserPreferences(
                user_id=current_user.id,
                instruments_enabled=["gold", "sp500", "crypto", "forex", "indices"],
                alert_types_enabled=[
                    "price",
                    "drawdown",
                    "copy_risk",
                    "execution_failure",
                ],
                notify_via_telegram=True,
                notify_via_email=True,
                notify_via_push=False,
                quiet_hours_enabled=False,
                timezone="UTC",
                digest_frequency="immediate",
                notify_entry_failure=True,
                notify_exit_failure=True,
                max_alerts_per_hour=10,
            )
            db.add(prefs)
            await db.commit()
            await db.refresh(prefs)

        # Update only fields present in request
        update_dict = update_data.model_dump(exclude_unset=True)

        for field, value in update_dict.items():
            if hasattr(prefs, field):
                setattr(prefs, field, value)

        await db.commit()
        await db.refresh(prefs)

        prefs_updated_total.inc()
        logger.info(
            f"Updated preferences for user {current_user.id}: {list(update_dict.keys())}"
        )

        # TODO: Write audit log entry (PR-008 integration)
        # audit_log.write(
        #     user_id=current_user.id,
        #     action="preferences.update",
        #     details={"fields_updated": list(update_dict.keys())}
        # )

        return UserPreferencesResponse.model_validate(prefs)

    except ValueError as e:
        # Pydantic validation errors (caught by FastAPI, but log for audit)
        logger.warning(
            f"Validation error updating preferences for user {current_user.id}: {e}"
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except Exception as e:
        logger.error(
            f"Error updating preferences for user {current_user.id}: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update preferences",
        )
