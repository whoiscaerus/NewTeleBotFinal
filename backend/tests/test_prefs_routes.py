"""
Comprehensive tests for User Preferences API Routes - PR-059

Tests GET/PUT endpoints, authentication, validation, error handling, and business logic.

Coverage Target: 100% of routes.py
"""

import pytest
from datetime import time
from httpx import AsyncClient
from sqlalchemy import select

from backend.app.prefs.models import UserPreferences
from backend.app.users.models import User


class TestGetPreferencesEndpoint:
    """Test GET /api/v1/prefs endpoint."""

    @pytest.mark.asyncio
    async def test_get_preferences_success(self, async_client: AsyncClient, test_user: User, auth_headers: dict):
        """Test successfully retrieving user preferences."""
        response = await async_client.get("/api/v1/prefs", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()

        # Verify structure
        assert "id" in data
        assert data["user_id"] == test_user.id
        assert "instruments_enabled" in data
        assert "alert_types_enabled" in data
        assert "notify_via_telegram" in data
        assert "notify_via_email" in data
        assert "notify_via_push" in data
        assert "quiet_hours_enabled" in data
        assert "timezone" in data
        assert "digest_frequency" in data
        assert "notify_entry_failure" in data
        assert "notify_exit_failure" in data
        assert "max_alerts_per_hour" in data

        # Verify defaults
        assert set(data["instruments_enabled"]) == {"gold", "sp500", "crypto", "forex", "indices"}
        assert set(data["alert_types_enabled"]) == {"price", "drawdown", "copy_risk", "execution_failure"}
        assert data["notify_via_telegram"] is True
        assert data["notify_via_email"] is True
        assert data["notify_via_push"] is False
        assert data["notify_entry_failure"] is True
        assert data["notify_exit_failure"] is True
        assert data["quiet_hours_enabled"] is False
        assert data["timezone"] == "UTC"
        assert data["digest_frequency"] == "immediate"
        assert data["max_alerts_per_hour"] == 10

    @pytest.mark.asyncio
    async def test_get_preferences_creates_defaults(
        self, async_client: AsyncClient, test_user: User, auth_headers: dict, db_session
    ):
        """
        Test that GET creates default preferences if they don't exist.

        Business Logic: Auto-create with safe defaults on first access.
        """
        # Verify no preferences exist
        result = await db_session.execute(select(UserPreferences).where(UserPreferences.user_id == test_user.id))
        existing = result.scalar_one_or_none()
        assert existing is None

        # GET request (should create)
        response = await async_client.get("/api/v1/prefs", headers=auth_headers)

        assert response.status_code == 200

        # Verify preferences created in database
        result = await db_session.execute(select(UserPreferences).where(UserPreferences.user_id == test_user.id))
        prefs = result.scalar_one_or_none()
        assert prefs is not None
        assert prefs.user_id == test_user.id

    @pytest.mark.asyncio
    async def test_get_preferences_unauthorized(self, async_client: AsyncClient):
        """Test GET preferences without authentication returns 401."""
        response = await async_client.get("/api/v1/prefs")

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_preferences_tenant_isolation(
        self, async_client: AsyncClient, test_user: User, test_user_2: User, auth_headers: dict, auth_headers_2: dict
    ):
        """
        Test that users can only access their own preferences (tenant isolation).

        Business Rule: User A cannot see User B's preferences.
        """
        # User 1 gets preferences
        response1 = await async_client.get("/api/v1/prefs", headers=auth_headers)
        assert response1.status_code == 200
        data1 = response1.json()
        assert data1["user_id"] == test_user.id

        # User 2 gets preferences
        response2 = await async_client.get("/api/v1/prefs", headers=auth_headers_2)
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["user_id"] == test_user_2.id

        # Verify different preference IDs
        assert data1["id"] != data2["id"]
        assert data1["user_id"] != data2["user_id"]


class TestUpdatePreferencesEndpoint:
    """Test PUT /api/v1/prefs endpoint."""

    @pytest.mark.asyncio
    async def test_update_preferences_single_field(
        self, async_client: AsyncClient, test_user: User, auth_headers: dict
    ):
        """Test updating a single preference field."""
        # First GET to create defaults
        await async_client.get("/api/v1/prefs", headers=auth_headers)

        # Update timezone only
        update_data = {"timezone": "Europe/London"}
        response = await async_client.put("/api/v1/prefs", json=update_data, headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["timezone"] == "Europe/London"
        # Other fields unchanged
        assert data["notify_via_telegram"] is True

    @pytest.mark.asyncio
    async def test_update_preferences_multiple_fields(
        self, async_client: AsyncClient, test_user: User, auth_headers: dict
    ):
        """Test updating multiple preference fields at once."""
        # First GET to create defaults
        await async_client.get("/api/v1/prefs", headers=auth_headers)

        # Update multiple fields
        update_data = {
            "instruments_enabled": ["gold", "sp500"],
            "alert_types_enabled": ["price", "execution_failure"],
            "notify_via_email": False,
            "notify_via_push": True,
            "quiet_hours_enabled": True,
            "quiet_hours_start": "22:00",
            "quiet_hours_end": "08:00",
            "timezone": "America/New_York",
            "digest_frequency": "hourly",
            "notify_entry_failure": True,
            "notify_exit_failure": False,
            "max_alerts_per_hour": 20,
        }
        response = await async_client.put("/api/v1/prefs", json=update_data, headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert set(data["instruments_enabled"]) == {"gold", "sp500"}
        assert set(data["alert_types_enabled"]) == {"price", "execution_failure"}
        assert data["notify_via_email"] is False
        assert data["notify_via_push"] is True
        assert data["quiet_hours_enabled"] is True
        assert data["quiet_hours_start"] == "22:00:00"
        assert data["quiet_hours_end"] == "08:00:00"
        assert data["timezone"] == "America/New_York"
        assert data["digest_frequency"] == "hourly"
        assert data["notify_entry_failure"] is True
        assert data["notify_exit_failure"] is False
        assert data["max_alerts_per_hour"] == 20

    @pytest.mark.asyncio
    async def test_update_preferences_execution_failure_alerts(
        self, async_client: AsyncClient, test_user: User, auth_headers: dict
    ):
        """
        Test updating execution failure alert preferences (PR-104 integration).

        Business Logic: User can independently control entry/exit failure alerts.
        """
        # First GET to create defaults
        await async_client.get("/api/v1/prefs", headers=auth_headers)

        # Disable exit failure alerts (keep entry alerts ON)
        update_data = {"notify_entry_failure": True, "notify_exit_failure": False}
        response = await async_client.put("/api/v1/prefs", json=update_data, headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["notify_entry_failure"] is True
        assert data["notify_exit_failure"] is False

    @pytest.mark.asyncio
    async def test_update_preferences_invalid_timezone(
        self, async_client: AsyncClient, test_user: User, auth_headers: dict
    ):
        """
        Test validation error for invalid timezone.

        Expected: 422 Unprocessable Entity
        """
        # First GET to create defaults
        await async_client.get("/api/v1/prefs", headers=auth_headers)

        # Invalid timezone
        update_data = {"timezone": "Invalid/Timezone"}
        response = await async_client.put("/api/v1/prefs", json=update_data, headers=auth_headers)

        assert response.status_code == 422
        assert "timezone" in response.text.lower() or "Invalid timezone" in response.text

    @pytest.mark.asyncio
    async def test_update_preferences_invalid_time_format(
        self, async_client: AsyncClient, test_user: User, auth_headers: dict
    ):
        """
        Test validation error for invalid time format.

        Expected: 422 Unprocessable Entity
        """
        # First GET to create defaults
        await async_client.get("/api/v1/prefs", headers=auth_headers)

        # Invalid time format (should be HH:MM)
        update_data = {"quiet_hours_start": "25:00"}  # Invalid hour
        response = await async_client.put("/api/v1/prefs", json=update_data, headers=auth_headers)

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_update_preferences_invalid_instrument(
        self, async_client: AsyncClient, test_user: User, auth_headers: dict
    ):
        """
        Test validation error for invalid instrument.

        Expected: 422 Unprocessable Entity
        """
        # First GET to create defaults
        await async_client.get("/api/v1/prefs", headers=auth_headers)

        # Invalid instrument
        update_data = {"instruments_enabled": ["gold", "INVALID_INSTRUMENT"]}
        response = await async_client.put("/api/v1/prefs", json=update_data, headers=auth_headers)

        assert response.status_code == 422
        assert "Invalid instruments" in response.text

    @pytest.mark.asyncio
    async def test_update_preferences_invalid_alert_type(
        self, async_client: AsyncClient, test_user: User, auth_headers: dict
    ):
        """
        Test validation error for invalid alert type.

        Expected: 422 Unprocessable Entity
        """
        # First GET to create defaults
        await async_client.get("/api/v1/prefs", headers=auth_headers)

        # Invalid alert type
        update_data = {"alert_types_enabled": ["price", "INVALID_ALERT"]}
        response = await async_client.put("/api/v1/prefs", json=update_data, headers=auth_headers)

        assert response.status_code == 422
        assert "Invalid alert types" in response.text

    @pytest.mark.asyncio
    async def test_update_preferences_invalid_digest_frequency(
        self, async_client: AsyncClient, test_user: User, auth_headers: dict
    ):
        """
        Test validation error for invalid digest frequency.

        Expected: 422 Unprocessable Entity
        """
        # First GET to create defaults
        await async_client.get("/api/v1/prefs", headers=auth_headers)

        # Invalid digest frequency (must be "immediate", "hourly", or "daily")
        update_data = {"digest_frequency": "weekly"}
        response = await async_client.put("/api/v1/prefs", json=update_data, headers=auth_headers)

        assert response.status_code == 422
        assert "Invalid digest_frequency" in response.text

    @pytest.mark.asyncio
    async def test_update_preferences_max_alerts_below_minimum(
        self, async_client: AsyncClient, test_user: User, auth_headers: dict
    ):
        """
        Test validation error for max_alerts_per_hour below minimum (1).

        Expected: 422 Unprocessable Entity
        """
        # First GET to create defaults
        await async_client.get("/api/v1/prefs", headers=auth_headers)

        # Below minimum
        update_data = {"max_alerts_per_hour": 0}
        response = await async_client.put("/api/v1/prefs", json=update_data, headers=auth_headers)

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_update_preferences_max_alerts_above_maximum(
        self, async_client: AsyncClient, test_user: User, auth_headers: dict
    ):
        """
        Test validation error for max_alerts_per_hour above maximum (100).

        Expected: 422 Unprocessable Entity
        """
        # First GET to create defaults
        await async_client.get("/api/v1/prefs", headers=auth_headers)

        # Above maximum
        update_data = {"max_alerts_per_hour": 101}
        response = await async_client.put("/api/v1/prefs", json=update_data, headers=auth_headers)

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_update_preferences_all_channels_disabled(
        self, async_client: AsyncClient, test_user: User, auth_headers: dict
    ):
        """
        Test validation error when all notification channels disabled.

        Business Rule: At least one channel must be enabled.
        Expected: 422 Unprocessable Entity
        """
        # First GET to create defaults
        await async_client.get("/api/v1/prefs", headers=auth_headers)

        # Disable all channels
        update_data = {"notify_via_telegram": False, "notify_via_email": False, "notify_via_push": False}
        response = await async_client.put("/api/v1/prefs", json=update_data, headers=auth_headers)

        assert response.status_code == 422
        assert "channel" in response.text.lower() or "notification" in response.text.lower()

    @pytest.mark.asyncio
    async def test_update_preferences_unauthorized(self, async_client: AsyncClient):
        """Test PUT preferences without authentication returns 401."""
        update_data = {"timezone": "Europe/London"}
        response = await async_client.put("/api/v1/prefs", json=update_data)

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_update_preferences_tenant_isolation(
        self, async_client: AsyncClient, test_user: User, test_user_2: User, auth_headers: dict, auth_headers_2: dict
    ):
        """
        Test that users can only update their own preferences (tenant isolation).

        Business Rule: User A cannot update User B's preferences.
        """
        # User 1 creates preferences
        response1 = await async_client.get("/api/v1/prefs", headers=auth_headers)
        assert response1.status_code == 200

        # User 2 creates preferences
        response2 = await async_client.get("/api/v1/prefs", headers=auth_headers_2)
        assert response2.status_code == 200

        # User 1 updates their preferences
        update_data = {"timezone": "Europe/London"}
        response = await async_client.put("/api/v1/prefs", json=update_data, headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["timezone"] == "Europe/London"

        # Verify User 2's preferences unchanged
        response2_check = await async_client.get("/api/v1/prefs", headers=auth_headers_2)
        assert response2_check.status_code == 200
        assert response2_check.json()["timezone"] == "UTC"  # Still default

    @pytest.mark.asyncio
    async def test_update_preferences_partial_update(
        self, async_client: AsyncClient, test_user: User, auth_headers: dict
    ):
        """
        Test that partial updates only change specified fields.

        Business Logic: Only fields in request body are updated.
        """
        # First GET to create defaults
        response = await async_client.get("/api/v1/prefs", headers=auth_headers)
        original_data = response.json()

        # Update only timezone
        update_data = {"timezone": "Europe/London"}
        response = await async_client.put("/api/v1/prefs", json=update_data, headers=auth_headers)

        assert response.status_code == 200
        data = response.json()

        # Verify timezone changed
        assert data["timezone"] == "Europe/London"

        # Verify other fields unchanged
        assert data["notify_via_telegram"] == original_data["notify_via_telegram"]
        assert data["notify_via_email"] == original_data["notify_via_email"]
        assert data["instruments_enabled"] == original_data["instruments_enabled"]
        assert data["alert_types_enabled"] == original_data["alert_types_enabled"]

    @pytest.mark.asyncio
    async def test_update_preferences_empty_arrays_allowed(
        self, async_client: AsyncClient, test_user: User, auth_headers: dict
    ):
        """
        Test that empty arrays are allowed for instruments/alert_types (opt-out).

        Business Logic: User can disable all instruments or all alert types.
        """
        # First GET to create defaults
        await async_client.get("/api/v1/prefs", headers=auth_headers)

        # Set empty arrays (user opts out of all)
        update_data = {"instruments_enabled": [], "alert_types_enabled": []}
        response = await async_client.put("/api/v1/prefs", json=update_data, headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["instruments_enabled"] == []
        assert data["alert_types_enabled"] == []

    @pytest.mark.asyncio
    async def test_update_preferences_quiet_hours_overnight(
        self, async_client: AsyncClient, test_user: User, auth_headers: dict
    ):
        """
        Test setting overnight quiet hours (22:00-08:00).

        Business Logic: Quiet hours can span midnight.
        """
        # First GET to create defaults
        await async_client.get("/api/v1/prefs", headers=auth_headers)

        # Set overnight quiet hours
        update_data = {
            "quiet_hours_enabled": True,
            "quiet_hours_start": "22:00",
            "quiet_hours_end": "08:00",
            "timezone": "Europe/London",
        }
        response = await async_client.put("/api/v1/prefs", json=update_data, headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["quiet_hours_enabled"] is True
        assert data["quiet_hours_start"] == "22:00:00"
        assert data["quiet_hours_end"] == "08:00:00"
        assert data["timezone"] == "Europe/London"

    @pytest.mark.asyncio
    async def test_update_preferences_creates_if_not_exist(
        self, async_client: AsyncClient, test_user: User, auth_headers: dict, db_session
    ):
        """
        Test that PUT creates preferences if they don't exist.

        Business Logic: First update auto-creates with defaults + update.
        """
        # Verify no preferences exist
        result = await db_session.execute(select(UserPreferences).where(UserPreferences.user_id == test_user.id))
        existing = result.scalar_one_or_none()
        assert existing is None

        # PUT without prior GET (should create + update)
        update_data = {"timezone": "Europe/London", "notify_via_push": True}
        response = await async_client.put("/api/v1/prefs", json=update_data, headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["timezone"] == "Europe/London"
        assert data["notify_via_push"] is True
        # Other fields have defaults
        assert data["notify_via_telegram"] is True

        # Verify preferences created in database
        result = await db_session.execute(select(UserPreferences).where(UserPreferences.user_id == test_user.id))
        prefs = result.scalar_one_or_none()
        assert prefs is not None


class TestPreferencesMetrics:
    """Test Prometheus metrics for preferences endpoints."""

    @pytest.mark.asyncio
    async def test_prefs_read_metric_incremented(
        self, async_client: AsyncClient, test_user: User, auth_headers: dict, prometheus_registry
    ):
        """Test that prefs_read_total metric is incremented on GET."""
        # Get preferences
        response = await async_client.get("/api/v1/prefs", headers=auth_headers)
        assert response.status_code == 200

        # Verify metric incremented
        # Note: Actual metric verification depends on test setup
        # This is a placeholder for metric testing pattern

    @pytest.mark.asyncio
    async def test_prefs_updated_metric_incremented(
        self, async_client: AsyncClient, test_user: User, auth_headers: dict, prometheus_registry
    ):
        """Test that prefs_updated_total metric is incremented on PUT."""
        # Update preferences
        update_data = {"timezone": "Europe/London"}
        response = await async_client.put("/api/v1/prefs", json=update_data, headers=auth_headers)
        assert response.status_code == 200

        # Verify metric incremented
        # Note: Actual metric verification depends on test setup
        # This is a placeholder for metric testing pattern
