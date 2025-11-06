"""
Basic tests for UserPreferences model - PR-059

Simplified test suite to verify core functionality.
"""

from datetime import time

import pytest

from backend.app.prefs.models import UserPreferences


class TestUserPreferencesBasic:
    """Basic test suite for UserPreferences model."""

    @pytest.mark.asyncio
    async def test_create_preferences_with_defaults(self, db_session, test_user):
        """Test creating preferences with default values."""
        prefs = UserPreferences(user_id=test_user.id)
        db_session.add(prefs)
        await db_session.commit()
        await db_session.refresh(prefs)

        # Verify defaults
        assert prefs.id is not None
        assert prefs.user_id == test_user.id
        assert "gold" in prefs.instruments_enabled
        assert "price" in prefs.alert_types_enabled
        assert prefs.notify_via_telegram is True
        assert prefs.notify_via_email is True
        assert prefs.notify_via_push is False
        assert prefs.quiet_hours_enabled is False
        assert prefs.timezone == "UTC"
        assert prefs.digest_frequency == "immediate"
        assert prefs.notify_entry_failure is True
        assert prefs.notify_exit_failure is True
        assert prefs.max_alerts_per_hour == 10

    @pytest.mark.asyncio
    async def test_create_preferences_with_custom_values(self, db_session, test_user):
        """Test creating preferences with custom values."""
        prefs = UserPreferences(
            user_id=test_user.id,
            instruments_enabled=["gold", "sp500"],
            alert_types_enabled=["price"],
            notify_via_telegram=True,
            notify_via_email=False,
            notify_via_push=True,
            quiet_hours_enabled=True,
            quiet_hours_start=time(22, 0),
            quiet_hours_end=time(8, 0),
            timezone="Europe/London",
            digest_frequency="hourly",
            max_alerts_per_hour=20,
        )
        db_session.add(prefs)
        await db_session.commit()
        await db_session.refresh(prefs)

        # Verify custom values
        assert set(prefs.instruments_enabled) == {"gold", "sp500"}
        assert prefs.alert_types_enabled == ["price"]
        assert prefs.notify_via_push is True
        assert prefs.quiet_hours_enabled is True
        assert prefs.quiet_hours_start == time(22, 0)
        assert prefs.timezone == "Europe/London"
        assert prefs.digest_frequency == "hourly"
        assert prefs.max_alerts_per_hour == 20
