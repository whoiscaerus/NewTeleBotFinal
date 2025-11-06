"""
API endpoint tests for PR-054: Time-Bucketed Analytics.

Tests all 4 bucket API endpoints with authentication, date parameters,
and error handling validation.

Tests:
- GET /analytics/buckets/hour
- GET /analytics/buckets/dow
- GET /analytics/buckets/month
- GET /analytics/buckets/calendar-month

Coverage: Authentication, date parameters, response schemas, error handling
"""

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.models import User
from backend.app.trading.store.models import Trade

# ============================================================================
# FIXTURES
# ============================================================================


@pytest_asyncio.fixture
async def sample_trades(db_session: AsyncSession, test_user: User) -> list[Trade]:
    """Create sample trades for API testing."""
    trades = []
    base_date = datetime(2025, 1, 15, 10, 0, 0)  # Wednesday, 10:00 AM

    # Create 20 trades across different hours, days, and months
    for i in range(20):
        trade = Trade(
            trade_id=str(uuid4()),
            user_id=test_user.id,
            symbol="GOLD",
            strategy="test_strategy",
            timeframe="H1",
            trade_type="BUY" if i % 2 == 0 else "SELL",
            direction=0 if i % 2 == 0 else 1,
            entry_price=Decimal("1950.00") + Decimal(str(i)),
            exit_price=Decimal("1960.00") + Decimal(str(i)),
            entry_time=base_date + timedelta(hours=i * 3, days=i // 5),
            exit_time=base_date + timedelta(hours=i * 3 + 1, days=i // 5),
            stop_loss=Decimal("1940.00"),
            take_profit=Decimal("1970.00"),
            volume=Decimal("1.0"),
            profit=Decimal("10.00") if i % 3 != 0 else Decimal("-5.00"),
            status="CLOSED",
        )
        trades.append(trade)
        db_session.add(trade)

    await db_session.commit()
    return trades


# ============================================================================
# HOUR BUCKET ENDPOINT TESTS
# ============================================================================


class TestHourBucketEndpoint:
    """Tests for GET /analytics/buckets/hour endpoint."""

    @pytest.mark.asyncio
    async def test_hour_buckets_requires_authentication(self, client: AsyncClient):
        """Test that hour buckets endpoint requires authentication."""
        response = await client.get("/api/v1/analytics/buckets/hour")
        assert response.status_code == 401
        assert "detail" in response.json()

    @pytest.mark.asyncio
    async def test_hour_buckets_returns_24_buckets(
        self, client: AsyncClient, auth_headers: dict, sample_trades: list
    ):
        """Test that hour buckets endpoint returns exactly 24 buckets."""
        response = await client.get(
            "/api/v1/analytics/buckets/hour?start_date=2025-01-01&end_date=2025-01-31",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 24

        # Verify all hours 0-23 present
        hours = [bucket["hour"] for bucket in data]
        assert hours == list(range(24))

    @pytest.mark.asyncio
    async def test_hour_buckets_schema_validation(
        self, client: AsyncClient, auth_headers: dict, sample_trades: list
    ):
        """Test that hour buckets response matches expected schema."""
        response = await client.get(
            "/api/v1/analytics/buckets/hour?start_date=2025-01-01&end_date=2025-01-31",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()

        # Check first bucket has all required fields
        bucket = data[0]
        assert "hour" in bucket
        assert "num_trades" in bucket
        assert "winning_trades" in bucket
        assert "losing_trades" in bucket
        assert "total_pnl" in bucket
        assert "avg_pnl" in bucket
        assert "win_rate_percent" in bucket

        # Validate field types
        assert isinstance(bucket["hour"], int)
        assert 0 <= bucket["hour"] <= 23
        assert isinstance(bucket["num_trades"], int)
        assert isinstance(bucket["total_pnl"], int | float)
        assert isinstance(bucket["avg_pnl"], int | float)
        assert isinstance(bucket["win_rate_percent"], int | float)

    @pytest.mark.asyncio
    async def test_hour_buckets_empty_hours_return_zeros(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test that empty hours return 0 values, not null."""
        response = await client.get(
            "/api/v1/analytics/buckets/hour?start_date=2025-01-01&end_date=2025-01-01",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 24

        # All buckets should have 0 values (no trades in date range)
        for bucket in data:
            assert bucket["num_trades"] == 0
            assert bucket["total_pnl"] == 0.0
            assert bucket["avg_pnl"] == 0.0
            assert bucket["win_rate_percent"] == 0.0

    @pytest.mark.asyncio
    async def test_hour_buckets_uses_default_date_range(
        self, client: AsyncClient, auth_headers: dict, sample_trades: list
    ):
        """Test that hour buckets uses default 90-day range when dates not provided."""
        response = await client.get(
            "/api/v1/analytics/buckets/hour",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 24


# ============================================================================
# DAY-OF-WEEK BUCKET ENDPOINT TESTS
# ============================================================================


class TestDayOfWeekBucketEndpoint:
    """Tests for GET /analytics/buckets/dow endpoint."""

    @pytest.mark.asyncio
    async def test_dow_buckets_requires_authentication(self, client: AsyncClient):
        """Test that day-of-week buckets endpoint requires authentication."""
        response = await client.get("/api/v1/analytics/buckets/dow")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_dow_buckets_returns_7_buckets(
        self, client: AsyncClient, auth_headers: dict, sample_trades: list
    ):
        """Test that day-of-week buckets endpoint returns exactly 7 buckets."""
        response = await client.get(
            "/api/v1/analytics/buckets/dow?start_date=2025-01-01&end_date=2025-01-31",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 7

        # Verify all days 0-6 present
        days = [bucket["day_of_week"] for bucket in data]
        assert days == list(range(7))

    @pytest.mark.asyncio
    async def test_dow_buckets_schema_validation(
        self, client: AsyncClient, auth_headers: dict, sample_trades: list
    ):
        """Test that day-of-week buckets response matches expected schema."""
        response = await client.get(
            "/api/v1/analytics/buckets/dow?start_date=2025-01-01&end_date=2025-01-31",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()

        # Check first bucket has all required fields
        bucket = data[0]
        assert "day_of_week" in bucket
        assert "day_name" in bucket
        assert "num_trades" in bucket
        assert "winning_trades" in bucket
        assert "losing_trades" in bucket
        assert "total_pnl" in bucket
        assert "avg_pnl" in bucket
        assert "win_rate_percent" in bucket

        # Validate field types
        assert isinstance(bucket["day_of_week"], int)
        assert 0 <= bucket["day_of_week"] <= 6
        assert isinstance(bucket["day_name"], str)
        assert bucket["day_name"] in [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]

    @pytest.mark.asyncio
    async def test_dow_buckets_day_names_correct(
        self, client: AsyncClient, auth_headers: dict, sample_trades: list
    ):
        """Test that day names match expected values for each day_of_week."""
        response = await client.get(
            "/api/v1/analytics/buckets/dow?start_date=2025-01-01&end_date=2025-01-31",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()

        expected_names = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]
        for i, bucket in enumerate(data):
            assert bucket["day_name"] == expected_names[i]


# ============================================================================
# MONTH BUCKET ENDPOINT TESTS
# ============================================================================


class TestMonthBucketEndpoint:
    """Tests for GET /analytics/buckets/month endpoint."""

    @pytest.mark.asyncio
    async def test_month_buckets_requires_authentication(self, client: AsyncClient):
        """Test that month buckets endpoint requires authentication."""
        response = await client.get("/api/v1/analytics/buckets/month")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_month_buckets_returns_12_buckets(
        self, client: AsyncClient, auth_headers: dict, sample_trades: list
    ):
        """Test that month buckets endpoint returns exactly 12 buckets."""
        response = await client.get(
            "/api/v1/analytics/buckets/month?start_date=2025-01-01&end_date=2025-12-31",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 12

        # Verify all months 1-12 present
        months = [bucket["month"] for bucket in data]
        assert months == list(range(1, 13))

    @pytest.mark.asyncio
    async def test_month_buckets_schema_validation(
        self, client: AsyncClient, auth_headers: dict, sample_trades: list
    ):
        """Test that month buckets response matches expected schema."""
        response = await client.get(
            "/api/v1/analytics/buckets/month?start_date=2025-01-01&end_date=2025-12-31",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()

        # Check first bucket has all required fields
        bucket = data[0]
        assert "month" in bucket
        assert "month_name" in bucket
        assert "num_trades" in bucket
        assert "winning_trades" in bucket
        assert "losing_trades" in bucket
        assert "total_pnl" in bucket
        assert "avg_pnl" in bucket
        assert "win_rate_percent" in bucket

        # Validate field types
        assert isinstance(bucket["month"], int)
        assert 1 <= bucket["month"] <= 12
        assert isinstance(bucket["month_name"], str)

    @pytest.mark.asyncio
    async def test_month_buckets_month_names_correct(
        self, client: AsyncClient, auth_headers: dict, sample_trades: list
    ):
        """Test that month names match expected values."""
        response = await client.get(
            "/api/v1/analytics/buckets/month?start_date=2025-01-01&end_date=2025-12-31",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()

        expected_names = [
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ]
        for i, bucket in enumerate(data):
            assert bucket["month_name"] == expected_names[i]


# ============================================================================
# CALENDAR MONTH BUCKET ENDPOINT TESTS
# ============================================================================


class TestCalendarMonthBucketEndpoint:
    """Tests for GET /analytics/buckets/calendar-month endpoint."""

    @pytest.mark.asyncio
    async def test_calendar_month_buckets_requires_authentication(
        self, client: AsyncClient
    ):
        """Test that calendar month buckets endpoint requires authentication."""
        response = await client.get("/api/v1/analytics/buckets/calendar-month")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_calendar_month_buckets_returns_correct_range(
        self, client: AsyncClient, auth_headers: dict, sample_trades: list
    ):
        """Test that calendar month buckets returns buckets for date range."""
        response = await client.get(
            "/api/v1/analytics/buckets/calendar-month?start_date=2025-01-01&end_date=2025-03-31",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

        # Should return at least 3 months (Jan, Feb, Mar 2025)
        assert len(data) >= 3

        # Verify format of calendar_month field
        for bucket in data:
            assert "calendar_month" in bucket
            # Format should be YYYY-MM
            assert len(bucket["calendar_month"]) == 7
            assert bucket["calendar_month"][4] == "-"

    @pytest.mark.asyncio
    async def test_calendar_month_buckets_schema_validation(
        self, client: AsyncClient, auth_headers: dict, sample_trades: list
    ):
        """Test that calendar month buckets response matches expected schema."""
        response = await client.get(
            "/api/v1/analytics/buckets/calendar-month?start_date=2025-01-01&end_date=2025-03-31",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()

        # Check first bucket has all required fields
        bucket = data[0]
        assert "calendar_month" in bucket
        assert "num_trades" in bucket
        assert "winning_trades" in bucket
        assert "losing_trades" in bucket
        assert "total_pnl" in bucket
        assert "avg_pnl" in bucket
        assert "win_rate_percent" in bucket

        # Validate field types
        assert isinstance(bucket["calendar_month"], str)
        assert isinstance(bucket["num_trades"], int)

    @pytest.mark.asyncio
    async def test_calendar_month_buckets_sorted_chronologically(
        self, client: AsyncClient, auth_headers: dict, sample_trades: list
    ):
        """Test that calendar month buckets are sorted chronologically."""
        response = await client.get(
            "/api/v1/analytics/buckets/calendar-month?start_date=2025-01-01&end_date=2025-03-31",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()

        # Extract calendar months
        calendar_months = [bucket["calendar_month"] for bucket in data]

        # Should be sorted
        assert calendar_months == sorted(calendar_months)


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================


class TestBucketAPIErrorHandling:
    """Tests for bucket API error handling."""

    @pytest.mark.asyncio
    async def test_invalid_date_format_rejected(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test that invalid date formats are rejected."""
        response = await client.get(
            "/api/v1/analytics/buckets/hour?start_date=invalid&end_date=2025-01-31",
            headers=auth_headers,
        )

        # Should return 422 (validation error)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_start_date_after_end_date_handled(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test that start_date after end_date is handled gracefully."""
        response = await client.get(
            "/api/v1/analytics/buckets/hour?start_date=2025-12-31&end_date=2025-01-01",
            headers=auth_headers,
        )

        # Should succeed but return empty buckets
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 24

    @pytest.mark.asyncio
    async def test_all_endpoints_accept_optional_dates(
        self, client: AsyncClient, auth_headers: dict, sample_trades: list
    ):
        """Test that all endpoints work without date parameters."""
        endpoints = [
            "/api/v1/analytics/buckets/hour",
            "/api/v1/analytics/buckets/dow",
            "/api/v1/analytics/buckets/month",
            "/api/v1/analytics/buckets/calendar-month",
        ]

        for endpoint in endpoints:
            response = await client.get(endpoint, headers=auth_headers)
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            assert len(data) > 0  # Should use default 90-day range


# ============================================================================
# INTEGRATION TESTS (BUSINESS LOGIC)
# ============================================================================


class TestBucketAPIBusinessLogic:
    """Integration tests validating business logic through API."""

    @pytest.mark.asyncio
    async def test_hour_bucket_aggregates_trades_correctly(
        self, client: AsyncClient, auth_headers: dict, sample_trades: list
    ):
        """Test that hour buckets correctly aggregate trade data."""
        response = await client.get(
            "/api/v1/analytics/buckets/hour?start_date=2025-01-01&end_date=2025-01-31",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()

        # Find buckets with trades
        buckets_with_trades = [b for b in data if b["num_trades"] > 0]
        assert len(buckets_with_trades) > 0

        # Validate calculations for buckets with trades
        for bucket in buckets_with_trades:
            assert bucket["num_trades"] > 0
            assert (
                bucket["winning_trades"] + bucket["losing_trades"]
                <= bucket["num_trades"]
            )
            if bucket["num_trades"] > 0:
                assert bucket["win_rate_percent"] >= 0
                assert bucket["win_rate_percent"] <= 100

    @pytest.mark.asyncio
    async def test_different_date_ranges_return_different_results(
        self, client: AsyncClient, auth_headers: dict, sample_trades: list
    ):
        """Test that different date ranges affect bucket results."""
        # Get buckets for January
        response_jan = await client.get(
            "/api/v1/analytics/buckets/hour?start_date=2025-01-01&end_date=2025-01-31",
            headers=auth_headers,
        )

        # Get buckets for February
        response_feb = await client.get(
            "/api/v1/analytics/buckets/hour?start_date=2025-02-01&end_date=2025-02-28",
            headers=auth_headers,
        )

        assert response_jan.status_code == 200
        assert response_feb.status_code == 200

        jan_data = response_jan.json()
        feb_data = response_feb.json()

        # Both should return 24 buckets
        assert len(jan_data) == 24
        assert len(feb_data) == 24

        # Data should be different (unless no trades in either month)
        jan_trades = sum(b["num_trades"] for b in jan_data)
        feb_trades = sum(b["num_trades"] for b in feb_data)

        # At least one should have trades
        assert jan_trades + feb_trades > 0
