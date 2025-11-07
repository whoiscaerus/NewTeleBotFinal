"""
Comprehensive tests for User Preferences Service Layer - PR-059

Tests CRUD operations, quiet hours logic, timezone validation, and all business logic.

Coverage Target: 100% of service.py
"""

from datetime import datetime, time

import pytest
import pytz
from sqlalchemy import select

from backend.app.prefs.models import UserPreferences
from backend.app.prefs.service import (
    get_enabled_channels,
    get_user_preferences,
    is_quiet_hours_active,
    should_send_notification,
    update_user_preferences,
)


class TestGetUserPreferences:
    """Test get_user_preferences() function."""

    @pytest.mark.asyncio
    async def test_get_existing_preferences(self, db_session, test_user):
        """Test retrieving existing user preferences."""
        # Create preferences
        prefs = UserPreferences(
            user_id=test_user.id,
            instruments_enabled=["gold", "sp500"],
            notify_via_telegram=True,
        )
        db_session.add(prefs)
        await db_session.commit()

        # Retrieve
        retrieved = await get_user_preferences(db_session, test_user.id)

        assert retrieved.id == prefs.id
        assert retrieved.user_id == test_user.id
        assert set(retrieved.instruments_enabled) == {"gold", "sp500"}

    @pytest.mark.asyncio
    async def test_get_creates_defaults_if_not_exist(self, db_session, test_user):
        """
        Test that get_user_preferences() creates defaults if preferences don't exist.

        Business Logic:
        - If preferences missing, create with safe defaults
        - Default instruments: all enabled
        - Default alert types: all enabled
        - Default channels: telegram + email ON
        - Default execution failure alerts: ON (safety-first)
        """
        # Verify no preferences exist
        result = await db_session.execute(
            select(UserPreferences).where(UserPreferences.user_id == test_user.id)
        )
        existing = result.scalar_one_or_none()
        assert existing is None

        # Get preferences (should create)
        prefs = await get_user_preferences(db_session, test_user.id)

        # Verify created with defaults
        assert prefs.id is not None
        assert prefs.user_id == test_user.id
        assert set(prefs.instruments_enabled) == {
            "gold",
            "sp500",
            "crypto",
            "forex",
            "indices",
        }
        assert set(prefs.alert_types_enabled) == {
            "price",
            "drawdown",
            "copy_risk",
            "execution_failure",
        }
        assert prefs.notify_via_telegram is True
        assert prefs.notify_via_email is True
        assert prefs.notify_via_push is False
        assert prefs.notify_entry_failure is True  # Safety-first
        assert prefs.notify_exit_failure is True  # Safety-first
        assert prefs.quiet_hours_enabled is False
        assert prefs.digest_frequency == "immediate"
        assert prefs.timezone == "UTC"
        assert prefs.max_alerts_per_hour == 10

        # Verify saved to database
        result = await db_session.execute(
            select(UserPreferences).where(UserPreferences.user_id == test_user.id)
        )
        db_prefs = result.scalar_one_or_none()
        assert db_prefs is not None
        assert db_prefs.id == prefs.id


class TestUpdateUserPreferences:
    """Test update_user_preferences() function."""

    @pytest.mark.asyncio
    async def test_update_single_field(self, db_session, test_user):
        """Test updating a single preference field."""
        # Create preferences
        prefs = await get_user_preferences(db_session, test_user.id)
        original_timezone = prefs.timezone

        # Update one field
        updated = await update_user_preferences(
            db_session, test_user.id, {"timezone": "Europe/London"}
        )

        assert updated.timezone == "Europe/London"
        assert updated.timezone != original_timezone
        # Other fields unchanged
        assert updated.notify_via_telegram is True

    @pytest.mark.asyncio
    async def test_update_multiple_fields(self, db_session, test_user):
        """Test updating multiple preference fields at once."""
        # Create preferences
        await get_user_preferences(db_session, test_user.id)

        # Update multiple fields
        update_data = {
            "instruments_enabled": ["gold", "sp500"],
            "alert_types_enabled": ["price", "execution_failure"],
            "notify_via_email": False,
            "quiet_hours_enabled": True,
            "quiet_hours_start": time(22, 0),
            "quiet_hours_end": time(8, 0),
            "timezone": "America/New_York",
            "digest_frequency": "hourly",
        }
        updated = await update_user_preferences(db_session, test_user.id, update_data)

        assert set(updated.instruments_enabled) == {"gold", "sp500"}
        assert set(updated.alert_types_enabled) == {"price", "execution_failure"}
        assert updated.notify_via_email is False
        assert updated.quiet_hours_enabled is True
        assert updated.quiet_hours_start == time(22, 0)
        assert updated.quiet_hours_end == time(8, 0)
        assert updated.timezone == "America/New_York"
        assert updated.digest_frequency == "hourly"

    @pytest.mark.asyncio
    async def test_update_execution_failure_alerts(self, db_session, test_user):
        """Test updating execution failure alert preferences (PR-104 integration)."""
        # Create preferences with defaults
        await get_user_preferences(db_session, test_user.id)

        # Disable exit failure alerts (user wants entry alerts only)
        updated = await update_user_preferences(
            db_session,
            test_user.id,
            {"notify_entry_failure": True, "notify_exit_failure": False},
        )

        assert updated.notify_entry_failure is True
        assert updated.notify_exit_failure is False

    @pytest.mark.asyncio
    async def test_update_creates_if_not_exist(self, db_session, test_user):
        """Test that update creates preferences if they don't exist."""
        # Verify no preferences
        result = await db_session.execute(
            select(UserPreferences).where(UserPreferences.user_id == test_user.id)
        )
        existing = result.scalar_one_or_none()
        assert existing is None

        # Update (should create first)
        updated = await update_user_preferences(
            db_session, test_user.id, {"timezone": "Europe/London"}
        )

        assert updated is not None
        assert updated.timezone == "Europe/London"

    @pytest.mark.asyncio
    async def test_update_updates_timestamp(self, db_session, test_user):
        """Test that update_user_preferences() updates the updated_at timestamp."""
        # Create preferences
        prefs = await get_user_preferences(db_session, test_user.id)
        original_updated_at = prefs.updated_at

        # Update
        updated = await update_user_preferences(
            db_session, test_user.id, {"notify_via_push": True}
        )

        # Verify timestamp changed
        assert updated.updated_at > original_updated_at

    @pytest.mark.asyncio
    async def test_update_ignores_invalid_fields(self, db_session, test_user):
        """Test that update ignores fields not in model."""
        # Create preferences
        await get_user_preferences(db_session, test_user.id)

        # Update with invalid field (should be ignored)
        updated = await update_user_preferences(
            db_session,
            test_user.id,
            {"invalid_field": "value", "timezone": "Europe/London"},
        )

        assert updated.timezone == "Europe/London"
        assert not hasattr(updated, "invalid_field")


class TestIsQuietHoursActive:
    """Test is_quiet_hours_active() function."""

    @pytest.mark.asyncio
    async def test_quiet_hours_disabled(self, db_session, test_user):
        """Test that quiet hours returns False when disabled."""
        prefs = UserPreferences(
            user_id=test_user.id,
            quiet_hours_enabled=False,
            quiet_hours_start=time(22, 0),
            quiet_hours_end=time(8, 0),
        )
        db_session.add(prefs)
        await db_session.commit()

        assert is_quiet_hours_active(prefs, datetime(2025, 11, 6, 23, 30)) is False

    @pytest.mark.asyncio
    async def test_quiet_hours_no_times_set(self, db_session, test_user):
        """Test that quiet hours returns False when times not set."""
        prefs = UserPreferences(
            user_id=test_user.id,
            quiet_hours_enabled=True,
            quiet_hours_start=None,
            quiet_hours_end=None,
        )
        db_session.add(prefs)
        await db_session.commit()

        assert is_quiet_hours_active(prefs, datetime(2025, 11, 6, 23, 30)) is False

    @pytest.mark.asyncio
    async def test_quiet_hours_overnight_within_hours(self, db_session, test_user):
        """
        Test overnight quiet hours (22:00-08:00) during quiet period.

        Check time: 23:30 (should be within quiet hours)
        """
        prefs = UserPreferences(
            user_id=test_user.id,
            quiet_hours_enabled=True,
            quiet_hours_start=time(22, 0),
            quiet_hours_end=time(8, 0),
            timezone="UTC",
        )
        db_session.add(prefs)
        await db_session.commit()

        # 23:30 UTC (within 22:00-08:00)
        check_time = pytz.UTC.localize(datetime(2025, 11, 6, 23, 30))
        assert is_quiet_hours_active(prefs, check_time) is True

    @pytest.mark.asyncio
    async def test_quiet_hours_overnight_before_start(self, db_session, test_user):
        """
        Test overnight quiet hours before start time.

        Check time: 21:00 (before 22:00 start, should be outside quiet hours)
        """
        prefs = UserPreferences(
            user_id=test_user.id,
            quiet_hours_enabled=True,
            quiet_hours_start=time(22, 0),
            quiet_hours_end=time(8, 0),
            timezone="UTC",
        )
        db_session.add(prefs)
        await db_session.commit()

        # 21:00 UTC (before 22:00)
        check_time = pytz.UTC.localize(datetime(2025, 11, 6, 21, 0))
        assert is_quiet_hours_active(prefs, check_time) is False

    @pytest.mark.asyncio
    async def test_quiet_hours_overnight_after_end(self, db_session, test_user):
        """
        Test overnight quiet hours after end time.

        Check time: 09:00 (after 08:00 end, should be outside quiet hours)
        """
        prefs = UserPreferences(
            user_id=test_user.id,
            quiet_hours_enabled=True,
            quiet_hours_start=time(22, 0),
            quiet_hours_end=time(8, 0),
            timezone="UTC",
        )
        db_session.add(prefs)
        await db_session.commit()

        # 09:00 UTC (after 08:00)
        check_time = pytz.UTC.localize(datetime(2025, 11, 6, 9, 0))
        assert is_quiet_hours_active(prefs, check_time) is False

    @pytest.mark.asyncio
    async def test_quiet_hours_overnight_early_morning(self, db_session, test_user):
        """
        Test overnight quiet hours in early morning.

        Check time: 03:00 (within 22:00-08:00, should be quiet)
        """
        prefs = UserPreferences(
            user_id=test_user.id,
            quiet_hours_enabled=True,
            quiet_hours_start=time(22, 0),
            quiet_hours_end=time(8, 0),
            timezone="UTC",
        )
        db_session.add(prefs)
        await db_session.commit()

        # 03:00 UTC (within 22:00-08:00)
        check_time = pytz.UTC.localize(datetime(2025, 11, 6, 3, 0))
        assert is_quiet_hours_active(prefs, check_time) is True

    @pytest.mark.asyncio
    async def test_quiet_hours_same_day_within_hours(self, db_session, test_user):
        """
        Test same-day quiet hours (12:00-14:00) during quiet period.

        Check time: 13:00 (should be within quiet hours)
        """
        prefs = UserPreferences(
            user_id=test_user.id,
            quiet_hours_enabled=True,
            quiet_hours_start=time(12, 0),
            quiet_hours_end=time(14, 0),
            timezone="UTC",
        )
        db_session.add(prefs)
        await db_session.commit()

        # 13:00 UTC (within 12:00-14:00)
        check_time = pytz.UTC.localize(datetime(2025, 11, 6, 13, 0))
        assert is_quiet_hours_active(prefs, check_time) is True

    @pytest.mark.asyncio
    async def test_quiet_hours_same_day_outside_hours(self, db_session, test_user):
        """
        Test same-day quiet hours outside quiet period.

        Check time: 15:00 (after 14:00 end, should be outside quiet hours)
        """
        prefs = UserPreferences(
            user_id=test_user.id,
            quiet_hours_enabled=True,
            quiet_hours_start=time(12, 0),
            quiet_hours_end=time(14, 0),
            timezone="UTC",
        )
        db_session.add(prefs)
        await db_session.commit()

        # 15:00 UTC (after 14:00)
        check_time = pytz.UTC.localize(datetime(2025, 11, 6, 15, 0))
        assert is_quiet_hours_active(prefs, check_time) is False

    @pytest.mark.asyncio
    async def test_quiet_hours_timezone_conversion(self, db_session, test_user):
        """
        Test quiet hours with timezone conversion.

        User timezone: Europe/London (UTC+0 in Nov, UTC+1 in summer)
        Quiet hours: 22:00-08:00 London time
        Check time: 23:00 UTC (should be 23:00 GMT, within quiet hours)
        """
        prefs = UserPreferences(
            user_id=test_user.id,
            quiet_hours_enabled=True,
            quiet_hours_start=time(22, 0),
            quiet_hours_end=time(8, 0),
            timezone="Europe/London",
        )
        db_session.add(prefs)
        await db_session.commit()

        # 23:00 UTC (same as 23:00 GMT in November)
        check_time = pytz.UTC.localize(datetime(2025, 11, 6, 23, 0))
        assert is_quiet_hours_active(prefs, check_time) is True

    @pytest.mark.asyncio
    async def test_quiet_hours_invalid_timezone_fallback_to_utc(
        self, db_session, test_user
    ):
        """
        Test that invalid timezone falls back to UTC.

        Business Logic: If timezone invalid, use UTC to prevent crashes.
        """
        prefs = UserPreferences(
            user_id=test_user.id,
            quiet_hours_enabled=True,
            quiet_hours_start=time(22, 0),
            quiet_hours_end=time(8, 0),
            timezone="Invalid/Timezone",
        )
        db_session.add(prefs)
        await db_session.commit()

        # Should fallback to UTC and still work
        check_time = pytz.UTC.localize(datetime(2025, 11, 6, 23, 0))
        result = is_quiet_hours_active(prefs, check_time)
        assert result is True  # 23:00 is within 22:00-08:00 UTC

    @pytest.mark.asyncio
    async def test_quiet_hours_defaults_to_now(self, db_session, test_user):
        """Test that is_quiet_hours_active() defaults to current time if check_time not provided."""
        prefs = UserPreferences(
            user_id=test_user.id,
            quiet_hours_enabled=True,
            quiet_hours_start=time(0, 0),  # Midnight
            quiet_hours_end=time(23, 59),  # All day quiet
            timezone="UTC",
        )
        db_session.add(prefs)
        await db_session.commit()

        # Call without check_time (should use now)
        result = is_quiet_hours_active(prefs, None)
        # Should be True since quiet hours cover all day
        assert result is True

    @pytest.mark.asyncio
    async def test_quiet_hours_boundary_exact_start_time(self, db_session, test_user):
        """Test quiet hours at exact start boundary (edge case)."""
        prefs = UserPreferences(
            user_id=test_user.id,
            quiet_hours_enabled=True,
            quiet_hours_start=time(22, 0),
            quiet_hours_end=time(8, 0),
            timezone="UTC",
        )
        db_session.add(prefs)
        await db_session.commit()

        # Exactly 22:00 (should be within quiet hours)
        check_time = pytz.UTC.localize(datetime(2025, 11, 6, 22, 0))
        assert is_quiet_hours_active(prefs, check_time) is True

    @pytest.mark.asyncio
    async def test_quiet_hours_boundary_exact_end_time(self, db_session, test_user):
        """Test quiet hours at exact end boundary (edge case)."""
        prefs = UserPreferences(
            user_id=test_user.id,
            quiet_hours_enabled=True,
            quiet_hours_start=time(22, 0),
            quiet_hours_end=time(8, 0),
            timezone="UTC",
        )
        db_session.add(prefs)
        await db_session.commit()

        # Exactly 08:00 (should be within quiet hours, <= comparison)
        check_time = pytz.UTC.localize(datetime(2025, 11, 6, 8, 0))
        assert is_quiet_hours_active(prefs, check_time) is True


class TestShouldSendNotification:
    """Test should_send_notification() function."""

    @pytest.mark.asyncio
    async def test_send_notification_all_conditions_met(self, db_session, test_user):
        """Test notification sent when all conditions met."""
        prefs = UserPreferences(
            user_id=test_user.id,
            instruments_enabled=["gold", "sp500"],
            alert_types_enabled=["price", "execution_failure"],
            quiet_hours_enabled=False,
        )
        db_session.add(prefs)
        await db_session.commit()

        # All conditions met
        result = should_send_notification(prefs, "price", "gold")
        assert result is True

    @pytest.mark.asyncio
    async def test_send_notification_alert_type_disabled(self, db_session, test_user):
        """Test notification blocked when alert type not enabled."""
        prefs = UserPreferences(
            user_id=test_user.id,
            instruments_enabled=["gold", "sp500"],
            alert_types_enabled=["price"],  # execution_failure not enabled
            quiet_hours_enabled=False,
        )
        db_session.add(prefs)
        await db_session.commit()

        # Alert type not enabled
        result = should_send_notification(prefs, "execution_failure", "gold")
        assert result is False

    @pytest.mark.asyncio
    async def test_send_notification_instrument_disabled(self, db_session, test_user):
        """Test notification blocked when instrument not enabled."""
        prefs = UserPreferences(
            user_id=test_user.id,
            instruments_enabled=["gold", "sp500"],  # crypto not enabled
            alert_types_enabled=["price", "execution_failure"],
            quiet_hours_enabled=False,
        )
        db_session.add(prefs)
        await db_session.commit()

        # Instrument not enabled
        result = should_send_notification(prefs, "price", "crypto")
        assert result is False

    @pytest.mark.asyncio
    async def test_send_notification_blocked_by_quiet_hours(
        self, db_session, test_user
    ):
        """Test notification blocked when within quiet hours."""
        prefs = UserPreferences(
            user_id=test_user.id,
            instruments_enabled=["gold", "sp500"],
            alert_types_enabled=["price", "execution_failure"],
            quiet_hours_enabled=True,
            quiet_hours_start=time(22, 0),
            quiet_hours_end=time(8, 0),
            timezone="UTC",
        )
        db_session.add(prefs)
        await db_session.commit()

        # During quiet hours (23:30)
        check_time = pytz.UTC.localize(datetime(2025, 11, 6, 23, 30))
        result = should_send_notification(prefs, "price", "gold", check_time)
        assert result is False

    @pytest.mark.asyncio
    async def test_send_notification_outside_quiet_hours(self, db_session, test_user):
        """Test notification sent when outside quiet hours."""
        prefs = UserPreferences(
            user_id=test_user.id,
            instruments_enabled=["gold", "sp500"],
            alert_types_enabled=["price", "execution_failure"],
            quiet_hours_enabled=True,
            quiet_hours_start=time(22, 0),
            quiet_hours_end=time(8, 0),
            timezone="UTC",
        )
        db_session.add(prefs)
        await db_session.commit()

        # Outside quiet hours (15:00)
        check_time = pytz.UTC.localize(datetime(2025, 11, 6, 15, 0))
        result = should_send_notification(prefs, "price", "gold", check_time)
        assert result is True

    @pytest.mark.asyncio
    async def test_send_notification_empty_instruments_list(
        self, db_session, test_user
    ):
        """Test notification blocked when instruments_enabled is empty."""
        prefs = UserPreferences(
            user_id=test_user.id,
            instruments_enabled=[],  # Empty list
            alert_types_enabled=["price"],
            quiet_hours_enabled=False,
        )
        db_session.add(prefs)
        await db_session.commit()

        result = should_send_notification(prefs, "price", "gold")
        assert result is False

    @pytest.mark.asyncio
    async def test_send_notification_empty_alert_types_list(
        self, db_session, test_user
    ):
        """Test notification blocked when alert_types_enabled is empty."""
        prefs = UserPreferences(
            user_id=test_user.id,
            instruments_enabled=["gold"],
            alert_types_enabled=[],  # Empty list
            quiet_hours_enabled=False,
        )
        db_session.add(prefs)
        await db_session.commit()

        result = should_send_notification(prefs, "price", "gold")
        assert result is False


class TestGetEnabledChannels:
    """Test get_enabled_channels() function."""

    @pytest.mark.asyncio
    async def test_all_channels_enabled(self, db_session, test_user):
        """Test all channels enabled."""
        prefs = UserPreferences(
            user_id=test_user.id,
            notify_via_telegram=True,
            notify_via_email=True,
            notify_via_push=True,
        )
        db_session.add(prefs)
        await db_session.commit()

        channels = get_enabled_channels(prefs)
        assert set(channels) == {"telegram", "email", "push"}

    @pytest.mark.asyncio
    async def test_only_telegram_enabled(self, db_session, test_user):
        """Test only telegram enabled."""
        prefs = UserPreferences(
            user_id=test_user.id,
            notify_via_telegram=True,
            notify_via_email=False,
            notify_via_push=False,
        )
        db_session.add(prefs)
        await db_session.commit()

        channels = get_enabled_channels(prefs)
        assert channels == ["telegram"]

    @pytest.mark.asyncio
    async def test_telegram_and_email_enabled(self, db_session, test_user):
        """Test telegram and email enabled."""
        prefs = UserPreferences(
            user_id=test_user.id,
            notify_via_telegram=True,
            notify_via_email=True,
            notify_via_push=False,
        )
        db_session.add(prefs)
        await db_session.commit()

        channels = get_enabled_channels(prefs)
        assert set(channels) == {"telegram", "email"}

    @pytest.mark.asyncio
    async def test_no_channels_enabled(self, db_session, test_user):
        """Test no channels enabled (returns empty list)."""
        prefs = UserPreferences(
            user_id=test_user.id,
            notify_via_telegram=False,
            notify_via_email=False,
            notify_via_push=False,
        )
        db_session.add(prefs)
        await db_session.commit()

        channels = get_enabled_channels(prefs)
        assert channels == []

    @pytest.mark.asyncio
    async def test_only_push_enabled(self, db_session, test_user):
        """Test only web push enabled."""
        prefs = UserPreferences(
            user_id=test_user.id,
            notify_via_telegram=False,
            notify_via_email=False,
            notify_via_push=True,
        )
        db_session.add(prefs)
        await db_session.commit()

        channels = get_enabled_channels(prefs)
        assert channels == ["push"]
