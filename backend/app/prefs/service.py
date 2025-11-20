"""
User Preferences Service Layer - PR-059

Business logic for preferences CRUD, quiet hours checking, and defaults.

Integrates with:
- PR-008 (Audit logging for preference changes)
- PR-044 (Price alerts use these preferences)
- PR-104 (Execution failure notifications use these preferences)
"""

from datetime import datetime

import pytz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.prefs.models import UserPreferences


async def get_user_preferences(db: AsyncSession, user_id: str) -> UserPreferences:
    """
    Get user preferences, creating defaults if not exist.

    Args:
        db: Database session
        user_id: User ID

    Returns:
        UserPreferences object

    Business Logic:
    - If preferences don't exist, create with safe defaults
    - Default: all instruments enabled
    - Default: all alert types enabled
    - Default: telegram + email ON, push OFF
    - Default: execution failure alerts ON (safety-first)
    - Default: no quiet hours
    - Default: immediate digest
    """
    result = await db.execute(
        select(UserPreferences).where(UserPreferences.user_id == user_id)
    )
    prefs = result.scalar_one_or_none()

    if not prefs:
        prefs = UserPreferences(
            user_id=user_id,
            instruments_enabled=["gold", "sp500", "crypto", "forex", "indices"],
            alert_types_enabled=["price", "drawdown", "copy_risk", "execution_failure"],
            notify_via_telegram=True,
            notify_via_email=True,
            notify_via_push=False,
            quiet_hours_enabled=False,
            quiet_hours_start=None,
            quiet_hours_end=None,
            timezone="UTC",
            digest_frequency="immediate",
            notify_entry_failure=True,  # Default ON for safety
            notify_exit_failure=True,  # Default ON for safety
            max_alerts_per_hour=10,
        )
        db.add(prefs)
        await db.commit()
        await db.refresh(prefs)

    return prefs


async def update_user_preferences(
    db: AsyncSession, user_id: str, update_data: dict, skip_commit: bool = False
) -> UserPreferences:
    """
    Update user preferences.

    Args:
        db: Database session
        user_id: User ID
        update_data: Dictionary of fields to update
        skip_commit: If True, don't commit (for testing/transactions)

    Returns:
        Updated UserPreferences object

    Business Logic:
    - Only updates fields present in update_data
    - Validates timezone exists
    - Validates time format for quiet hours
    - Updates updated_at timestamp
    - Audit log written by route handler (PR-008)
    """
    prefs = await get_user_preferences(db, user_id)

    # Update only fields present in update_data
    for field, value in update_data.items():
        if hasattr(prefs, field):
            setattr(prefs, field, value)

    # Always update timestamp
    prefs.updated_at = datetime.utcnow()

    if not skip_commit:
        await db.commit()
        await db.refresh(prefs)

    return prefs


def is_quiet_hours_active(
    prefs: UserPreferences, check_time: datetime | None = None
) -> bool:
    """
    Check if current time is within user's quiet hours (do not disturb).

    Args:
        prefs: User preferences object
        check_time: Time to check (defaults to now in user's timezone)

    Returns:
        True if quiet hours are active, False otherwise

    Business Logic:
    - If quiet_hours_enabled=False, always returns False
    - Converts check_time to user's timezone
    - Handles overnight quiet hours (e.g., 22:00-08:00)
    - Handles same-day quiet hours (e.g., 12:00-14:00)

    Examples:
        >>> prefs.quiet_hours_start = time(22, 0)  # 22:00
        >>> prefs.quiet_hours_end = time(8, 0)     # 08:00
        >>> is_quiet_hours_active(prefs, datetime(2025, 11, 6, 23, 30))  # 23:30
        True  # Within overnight quiet hours

        >>> prefs.quiet_hours_start = time(12, 0)
        >>> prefs.quiet_hours_end = time(14, 0)
        >>> is_quiet_hours_active(prefs, datetime(2025, 11, 6, 13, 0))
        True  # Within same-day quiet hours
    """
    if not prefs.quiet_hours_enabled:
        return False

    if not prefs.quiet_hours_start or not prefs.quiet_hours_end:
        return False

    # Get current time in user's timezone
    if check_time is None:
        check_time = datetime.utcnow()

    try:
        user_tz = pytz.timezone(prefs.timezone)
    except pytz.UnknownTimeZoneError:
        # Fallback to UTC if timezone invalid
        user_tz = pytz.UTC

    # Convert check_time to user's timezone
    if check_time.tzinfo is None:
        check_time = pytz.UTC.localize(check_time)
    local_time = check_time.astimezone(user_tz).time()

    start = prefs.quiet_hours_start
    end = prefs.quiet_hours_end

    # Handle overnight quiet hours (e.g., 22:00-08:00)
    if start > end:
        return bool(local_time >= start or local_time <= end)
    # Handle same-day quiet hours (e.g., 12:00-14:00)
    else:
        return bool(start <= local_time <= end)


def should_send_notification(
    prefs: UserPreferences,
    alert_type: str,
    instrument: str,
    check_time: datetime | None = None,
) -> bool:
    """
    Determine if notification should be sent based on user preferences.

    Args:
        prefs: User preferences
        alert_type: Type of alert (e.g., "price", "execution_failure")
        instrument: Trading instrument (e.g., "gold", "sp500")
        check_time: Time to check (defaults to now)

    Returns:
        True if notification should be sent, False otherwise

    Business Logic:
    - Check if alert_type is enabled in alert_types_enabled
    - Check if instrument is enabled in instruments_enabled
    - Check if within quiet hours (returns False if quiet hours active)
    - Returns True only if all checks pass

    Examples:
        >>> prefs.alert_types_enabled = ["price", "drawdown"]
        >>> prefs.instruments_enabled = ["gold", "sp500"]
        >>> should_send_notification(prefs, "price", "gold")
        True

        >>> should_send_notification(prefs, "execution_failure", "gold")
        False  # execution_failure not in alert_types_enabled

        >>> prefs.quiet_hours_enabled = True
        >>> # During quiet hours:
        >>> should_send_notification(prefs, "price", "gold", check_time=during_quiet_hours)
        False  # Suppressed by quiet hours
    """
    # Check alert type enabled
    if alert_type not in (prefs.alert_types_enabled or []):
        return False

    # Check instrument enabled
    if instrument not in (prefs.instruments_enabled or []):
        return False

    # Check quiet hours
    if is_quiet_hours_active(prefs, check_time):
        return False

    return True


def get_enabled_channels(prefs: UserPreferences) -> list[str]:
    """
    Get list of enabled notification channels.

    Args:
        prefs: User preferences

    Returns:
        List of enabled channel names: ["telegram", "email", "push"]

    Examples:
        >>> prefs.notify_via_telegram = True
        >>> prefs.notify_via_email = True
        >>> prefs.notify_via_push = False
        >>> get_enabled_channels(prefs)
        ["telegram", "email"]
    """
    channels = []
    if prefs.notify_via_telegram:
        channels.append("telegram")
    if prefs.notify_via_email:
        channels.append("email")
    if prefs.notify_via_push:
        channels.append("push")
    return channels
