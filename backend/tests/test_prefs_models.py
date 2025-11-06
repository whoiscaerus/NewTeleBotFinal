"""
Comprehensive tests for UserPreferences model - PR-059

Tests model creation, defaults, relationships, and data integrity.

Coverage Target: 100% of models.py
"""

import pytest
from datetime import time
from sqlalchemy.exc import IntegrityError

from backend.app.prefs.models import UserPreferences


class TestUserPreferencesModel:
    """Test suite for UserPreferences model."""

    @pytest.mark.asyncio
    async def test_create_preferences_with_defaults(self, db_session, test_user):
        """
        Test creating preferences with default values.

        Business Logic:
        - Default instruments: all enabled (gold, sp500, crypto, forex, indices)
        - Default alert types: all enabled (price, drawdown, copy_risk, execution_failure)
        - Default channels: telegram=true, email=true, push=false
        - Default execution failure alerts: ON (safety-first)
        - Default quiet hours: disabled
        - Default digest: immediate
        - Default timezone: UTC
        """
        prefs = UserPreferences(user_id=test_user.id)
        db_session.add(prefs)
        await await db_session db_session.commit()
        await await db_session db_session.refresh(prefs)

        # Verify defaults
        assert prefs.id is not None
        assert prefs.user_id == test_user.id
        assert set(prefs.instruments_enabled) == {"gold", "sp500", "crypto", "forex", "indices"}
        assert set(prefs.alert_types_enabled) == {"price", "drawdown", "copy_risk", "execution_failure"}
        assert prefs.notify_via_telegram is True
        assert prefs.notify_via_email is True
        assert prefs.notify_via_push is False
        assert prefs.quiet_hours_enabled is False
        assert prefs.quiet_hours_start is None
        assert prefs.quiet_hours_end is None
        assert prefs.timezone == "UTC"
        assert prefs.digest_frequency == "immediate"
        assert prefs.notify_entry_failure is True  # Safety-first default
        assert prefs.notify_exit_failure is True  # Safety-first default
        assert prefs.max_alerts_per_hour == 10
        assert prefs.created_at is not None
        assert prefs.updated_at is not None

    @pytest.mark.asyncio

    async def test_create_preferences_with_custom_values(self, db_session, test_user):
        """
        Test creating preferences with custom values.

        Validates that all fields can be set to non-default values.
        """
        prefs = UserPreferences(
            user_id=test_user.id,
            instruments_enabled=["gold", "sp500"],
            alert_types_enabled=["price", "execution_failure"],
            notify_via_telegram=True,
            notify_via_email=False,
            notify_via_push=True,
            quiet_hours_enabled=True,
            quiet_hours_start=time(22, 0),
            quiet_hours_end=time(8, 0),
            timezone="Europe/London",
            digest_frequency="hourly",
            notify_entry_failure=True,
            notify_exit_failure=False,
            max_alerts_per_hour=20,
        )
        db_session.add(prefs)
        await db_session db_session.commit()
        await db_session db_session.refresh(prefs)

        # Verify custom values
        assert set(prefs.instruments_enabled) == {"gold", "sp500"}
        assert set(prefs.alert_types_enabled) == {"price", "execution_failure"}
        assert prefs.notify_via_telegram is True
        assert prefs.notify_via_email is False
        assert prefs.notify_via_push is True
        assert prefs.quiet_hours_enabled is True
        assert prefs.quiet_hours_start == time(22, 0)
        assert prefs.quiet_hours_end == time(8, 0)
        assert prefs.timezone == "Europe/London"
        assert prefs.digest_frequency == "hourly"
        assert prefs.notify_entry_failure is True
        assert prefs.notify_exit_failure is False
        assert prefs.max_alerts_per_hour == 20

    @pytest.mark.asyncio

    async def test_user_preferences_unique_constraint(self, db_session, test_user):
        """
        Test unique constraint on user_id.

        Business Rule: Each user can have only ONE preferences row.
        """
        # Create first preferences
        prefs1 = UserPreferences(user_id=test_user.id)
        db_session.add(prefs1)
        await db_session db_session.commit()

        # Attempt to create duplicate
        prefs2 = UserPreferences(user_id=test_user.id)
        db_session.add(prefs2)

        with pytest.raises(IntegrityError):
            await db_session db_session.commit()
        await db_session db_session.rollback()

    @pytest.mark.asyncio

    async def test_user_preferences_cascade_delete(self, db_session, test_user):
        """
        Test cascade delete when user is deleted.

        Business Rule: When user deleted, their preferences are deleted automatically.
        """
        # Create preferences
        prefs = UserPreferences(user_id=test_user.id)
        db_session.add(prefs)
        await db_session db_session.commit()

        prefs_id = prefs.id

        # Delete user
        db_session.delete(test_user)
        await db_session db_session.commit()

        # Verify preferences deleted
        deleted_prefs = db_session.query(UserPreferences).filter(UserPreferences.id == prefs_id).first()
        assert deleted_prefs is None

    @pytest.mark.asyncio

    async def test_preferences_repr(self, db_session, test_user):
        """Test __repr__ method."""
        prefs = UserPreferences(
            user_id=test_user.id,
            instruments_enabled=["gold", "sp500", "crypto"],
            notify_via_telegram=True,
            notify_via_email=False,
            notify_via_push=False,
            quiet_hours_enabled=True,
        )
        db_session.add(prefs)
        await db_session db_session.commit()

        repr_str = repr(prefs)
        assert "UserPreferences" in repr_str
        assert f"user_id={test_user.id}" in repr_str
        assert "instruments=3" in repr_str
        assert "telegram=True" in repr_str
        assert "email=False" in repr_str
        assert "push=False" in repr_str
        assert "quiet_hours=True" in repr_str

    @pytest.mark.asyncio

    async def test_preferences_to_dict(self, db_session, test_user):
        """
        Test to_dict() method for API serialization.

        Validates that all fields are included in dictionary output.
        """
        prefs = UserPreferences(
            user_id=test_user.id,
            instruments_enabled=["gold", "sp500"],
            alert_types_enabled=["price", "execution_failure"],
            notify_via_telegram=True,
            notify_via_email=False,
            notify_via_push=True,
            quiet_hours_enabled=True,
            quiet_hours_start=time(22, 0),
            quiet_hours_end=time(8, 0),
            timezone="Europe/London",
            digest_frequency="hourly",
            notify_entry_failure=True,
            notify_exit_failure=False,
            max_alerts_per_hour=15,
        )
        db_session.add(prefs)
        await db_session db_session.commit()
        await db_session db_session.refresh(prefs)

        prefs_dict = prefs.to_dict()

        # Verify all fields present
        assert prefs_dict["id"] == prefs.id
        assert prefs_dict["user_id"] == test_user.id
        assert prefs_dict["instruments_enabled"] == ["gold", "sp500"]
        assert prefs_dict["alert_types_enabled"] == ["price", "execution_failure"]
        assert prefs_dict["notify_via_telegram"] is True
        assert prefs_dict["notify_via_email"] is False
        assert prefs_dict["notify_via_push"] is True
        assert prefs_dict["quiet_hours_enabled"] is True
        assert prefs_dict["quiet_hours_start"] == "22:00:00"
        assert prefs_dict["quiet_hours_end"] == "08:00:00"
        assert prefs_dict["timezone"] == "Europe/London"
        assert prefs_dict["digest_frequency"] == "hourly"
        assert prefs_dict["notify_entry_failure"] is True
        assert prefs_dict["notify_exit_failure"] is False
        assert prefs_dict["max_alerts_per_hour"] == 15
        assert "created_at" in prefs_dict
        assert "updated_at" in prefs_dict

    @pytest.mark.asyncio

    async def test_preferences_empty_arrays(self, db_session, test_user):
        """
        Test preferences with empty instrument/alert arrays.

        Business Rule: User can disable all instruments/alerts (opt-out).
        """
        prefs = UserPreferences(
            user_id=test_user.id,
            instruments_enabled=[],
            alert_types_enabled=[],
        )
        db_session.add(prefs)
        await db_session db_session.commit()
        await db_session db_session.refresh(prefs)

        assert prefs.instruments_enabled == []
        assert prefs.alert_types_enabled == []

    @pytest.mark.asyncio

    async def test_preferences_quiet_hours_overnight(self, db_session, test_user):
        """
        Test quiet hours spanning midnight (overnight).

        Example: 22:00 to 08:00 (10pm to 8am)
        """
        prefs = UserPreferences(
            user_id=test_user.id,
            quiet_hours_enabled=True,
            quiet_hours_start=time(22, 0),
            quiet_hours_end=time(8, 0),
        )
        db_session.add(prefs)
        await db_session db_session.commit()
        await db_session db_session.refresh(prefs)

        assert prefs.quiet_hours_start == time(22, 0)
        assert prefs.quiet_hours_end == time(8, 0)
        # Logic validation in service tests

    @pytest.mark.asyncio

    async def test_preferences_quiet_hours_same_day(self, db_session, test_user):
        """
        Test quiet hours within same day.

        Example: 12:00 to 14:00 (lunch break)
        """
        prefs = UserPreferences(
            user_id=test_user.id,
            quiet_hours_enabled=True,
            quiet_hours_start=time(12, 0),
            quiet_hours_end=time(14, 0),
        )
        db_session.add(prefs)
        await db_session db_session.commit()
        await db_session db_session.refresh(prefs)

        assert prefs.quiet_hours_start == time(12, 0)
        assert prefs.quiet_hours_end == time(14, 0)

    @pytest.mark.asyncio

    async def test_preferences_update_timestamp(self, db_session, test_user):
        """
        Test that updated_at timestamp changes on update.

        Business Rule: updated_at reflects last modification time.
        """
        prefs = UserPreferences(user_id=test_user.id)
        db_session.add(prefs)
        await db_session db_session.commit()
        await db_session db_session.refresh(prefs)

        original_updated_at = prefs.updated_at

        # Update preferences
        prefs.notify_via_push = True
        await db_session db_session.commit()
        await db_session db_session.refresh(prefs)

        # Verify timestamp changed
        assert prefs.updated_at > original_updated_at

    @pytest.mark.asyncio

    async def test_preferences_all_channels_disabled_allowed(self, db_session, test_user):
        """
        Test that all notification channels can be disabled.

        Note: API validation will prevent this, but model allows it.
        This tests model flexibility vs API business rules.
        """
        prefs = UserPreferences(
            user_id=test_user.id,
            notify_via_telegram=False,
            notify_via_email=False,
            notify_via_push=False,
        )
        db_session.add(prefs)
        await db_session db_session.commit()
        await db_session db_session.refresh(prefs)

        assert prefs.notify_via_telegram is False
        assert prefs.notify_via_email is False
        assert prefs.notify_via_push is False

    @pytest.mark.asyncio

    async def test_preferences_execution_failure_alerts_independent(self, db_session, test_user):
        """
        Test that entry/exit failure alerts are independent.

        Business Rule: User can enable/disable entry and exit failures separately.
        """
        prefs = UserPreferences(
            user_id=test_user.id,
            notify_entry_failure=True,
            notify_exit_failure=False,
        )
        db_session.add(prefs)
        await db_session db_session.commit()
        await db_session db_session.refresh(prefs)

        assert prefs.notify_entry_failure is True
        assert prefs.notify_exit_failure is False

    @pytest.mark.asyncio

    async def test_preferences_max_alerts_boundary_values(self, db_session, test_user):
        """
        Test max_alerts_per_hour boundary values.

        Valid range: 1-100 (validated in schema, but model allows any integer).
        """
        # Minimum valid value
        prefs1 = UserPreferences(user_id=test_user.id, max_alerts_per_hour=1)
        db_session.add(prefs1)
        await db_session db_session.commit()
        assert prefs1.max_alerts_per_hour == 1

        # Maximum valid value (in separate session due to unique constraint)
        db_session.delete(prefs1)
        await db_session db_session.commit()

        prefs2 = UserPreferences(user_id=test_user.id, max_alerts_per_hour=100)
        db_session.add(prefs2)
        await db_session db_session.commit()
        assert prefs2.max_alerts_per_hour == 100

    @pytest.mark.asyncio

    async def test_preferences_relationship_to_user(self, db_session, test_user):
        """
        Test relationship between UserPreferences and User.

        Validates bidirectional relationship.
        """
        prefs = UserPreferences(user_id=test_user.id)
        db_session.add(prefs)
        await db_session db_session.commit()
        await db_session db_session.refresh(prefs)
        await db_session db_session.refresh(test_user)

        # Access user from preferences
        assert prefs.user == test_user

        # Access preferences from user
        assert test_user.preferences == prefs

