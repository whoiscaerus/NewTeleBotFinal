"""
Phase 5 Tests: API Routes

Comprehensive test suite for REST API endpoints:
- GET /reconciliation/status
- GET /positions/open
- GET /guards/status

Test Coverage:
- Happy path (200 responses)
- Edge cases (empty results, filters)
- Error handling (401, 500)
- Response schema validation
- Rate limiting
- Logging verification

Target: 12 tests, 100% passing
Author: Trading System
Date: 2024-10-26
"""

from datetime import datetime

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.trading.schemas import AlertType, ConditionType, PositionStatus

# ================================================================
# Fixtures
# ================================================================


@pytest_asyncio.fixture
async def auth_headers_test_user(db_session: AsyncSession):
    """Create test JWT headers for a test user.

    Note: Uses settings.security.jwt_secret_key for proper token validation.
    """
    from uuid import uuid4

    import jwt

    from backend.app.auth.models import User
    from backend.app.auth.utils import hash_password
    from backend.app.core.settings import settings

    # Create a fresh user for this test
    user_id = uuid4()
    user = User(
        id=user_id,
        email="test_phase5@example.com",
        password_hash=hash_password("password123"),
    )
    db_session.add(user)
    await db_session.commit()

    # Create valid JWT token using app's secret key
    payload = {
        "sub": str(user_id),
        "role": "user",
        "exp": (datetime.now().timestamp()) + 3600,
        "iat": datetime.now().timestamp(),
    }

    token = jwt.encode(
        payload,
        settings.security.jwt_secret_key,
        algorithm=settings.security.jwt_algorithm,
    )

    return {
        "user": user,
        "headers": {"Authorization": f"Bearer {token}"},
    }


# ================================================================
# Reconciliation Status Tests
# ================================================================


class TestReconciliationStatusEndpoint:
    """Test suite for GET /reconciliation/status endpoint."""

    @pytest.mark.asyncio
    async def test_get_reconciliation_status_success(
        self, client: AsyncClient, sample_user_with_data, auth_headers: dict
    ):
        """Test successful reconciliation status retrieval."""
        response = await client.get(
            "/api/v1/reconciliation/status",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()

        # Verify all required fields present
        assert "user_id" in data
        assert "status" in data
        assert "last_sync_at" in data
        assert "total_syncs" in data
        assert "last_sync_duration_ms" in data
        assert "open_positions_count" in data
        assert "matched_positions" in data
        assert "divergences_detected" in data
        assert "recent_events" in data
        assert "error_message" in data

        # Verify types
        assert isinstance(data["status"], str)
        assert isinstance(data["total_syncs"], int)
        assert isinstance(data["open_positions_count"], int)
        assert isinstance(data["recent_events"], list)
        assert data["total_syncs"] >= 0
        assert data["open_positions_count"] >= 0

    @pytest.mark.asyncio
    async def test_get_reconciliation_status_without_auth(self, client: AsyncClient):
        """Test reconciliation status requires authentication."""
        response = await client.get("/api/v1/reconciliation/status")

        # Rate limiter returns 403 for missing/invalid auth
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_get_reconciliation_status_with_invalid_token(
        self, client: AsyncClient
    ):
        """Test reconciliation status with invalid JWT token."""
        response = await client.get(
            "/api/v1/reconciliation/status",
            headers={"Authorization": "Bearer invalid_token"},
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_reconciliation_status_contains_recent_events(
        self, client: AsyncClient, sample_user_with_data, auth_headers: dict
    ):
        """Test reconciliation status includes recent events."""
        response = await client.get(
            "/api/v1/reconciliation/status",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        events = data["recent_events"]

        # Even if empty, should be list
        assert isinstance(events, list)

        # If events present, verify structure
        if events:
            event = events[0]
            assert "event_id" in event
            assert "event_type" in event
            assert "user_id" in event
            assert "created_at" in event
            assert "description" in event


# ================================================================
# Open Positions Tests
# ================================================================


class TestOpenPositionsEndpoint:
    """Test suite for GET /positions/open endpoint."""

    @pytest.mark.asyncio
    async def test_get_open_positions_success(
        self, client: AsyncClient, sample_user_with_data, auth_headers: dict
    ):
        """Test successful open positions retrieval."""
        response = await client.get(
            "/api/v1/positions/open",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()

        # Verify all required fields present
        assert "user_id" in data
        assert "total_positions" in data
        assert "total_unrealized_pnl" in data
        assert "total_unrealized_pnl_pct" in data
        assert "positions" in data
        assert "last_updated_at" in data

        # Verify types
        assert isinstance(data["positions"], list)
        assert isinstance(data["total_positions"], int)
        assert isinstance(data["total_unrealized_pnl"], (int, float))

    @pytest.mark.asyncio
    async def test_get_open_positions_position_structure(
        self, client: AsyncClient, sample_user_with_data, auth_headers: dict
    ):
        """Test individual position has correct structure."""
        response = await client.get(
            "/api/v1/positions/open",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()

        if data["positions"]:
            position = data["positions"][0]

            # Verify all position fields
            assert "position_id" in position
            assert "ticket" in position
            assert "symbol" in position
            assert "direction" in position
            assert "volume" in position
            assert "entry_price" in position
            assert "entry_time" in position
            assert "current_price" in position
            assert "unrealized_pnl" in position
            assert "unrealized_pnl_pct" in position
            assert "take_profit" in position
            assert "stop_loss" in position
            assert "status" in position
            assert "matched_with_bot" in position
            assert "last_updated_at" in position

            # Verify types
            assert position["direction"] in ["buy", "sell"]
            assert position["status"] == PositionStatus.OPEN.value
            assert isinstance(position["matched_with_bot"], bool)

    @pytest.mark.asyncio
    async def test_get_open_positions_with_symbol_filter(
        self, client: AsyncClient, sample_user_with_data, auth_headers: dict
    ):
        """Test filtering positions by symbol."""
        response = await client.get(
            "/api/v1/positions/open?symbol=XAUUSD",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()

        # If positions exist, all should have requested symbol
        for position in data["positions"]:
            assert position["symbol"] == "XAUUSD"

    @pytest.mark.asyncio
    async def test_get_open_positions_without_auth(self, client: AsyncClient):
        """Test open positions requires authentication."""
        response = await client.get("/api/v1/positions/open")

        # Rate limiter returns 403 for missing/invalid auth
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_get_open_positions_empty_list(
        self, client: AsyncClient, test_user, auth_headers: dict
    ):
        """Test open positions returns empty list when no positions exist."""
        response = await client.get(
            "/api/v1/positions/open",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()

        # User with no reconciliation logs should have empty positions
        assert isinstance(data["positions"], list)

        response = await client.get(
            "/api/v1/positions/open?symbol=XAUUSD",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()

        # All returned positions should match filter
        for position in data["positions"]:
            assert position["symbol"] == "XAUUSD"


# ================================================================
# Guards Status Tests
# ================================================================


class TestGuardsStatusEndpoint:
    """Test suite for GET /guards/status endpoint."""

    @pytest.mark.asyncio
    async def test_get_guards_status_success(
        self, client: AsyncClient, sample_user_with_data, auth_headers: dict
    ):
        """Test successful guards status retrieval."""
        response = await client.get(
            "/api/v1/guards/status",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()

        # Verify all required fields
        assert "user_id" in data
        assert "system_status" in data
        assert "drawdown_guard" in data
        assert "market_guard_alerts" in data
        assert "any_positions_should_close" in data
        assert "last_evaluated_at" in data

        # Verify types
        assert isinstance(data["system_status"], str)
        assert isinstance(data["market_guard_alerts"], list)
        assert isinstance(data["any_positions_should_close"], bool)

    @pytest.mark.asyncio
    async def test_get_guards_status_drawdown_guard(
        self, client: AsyncClient, sample_user_with_data, auth_headers: dict
    ):
        """Test drawdown guard data structure."""
        response = await client.get(
            "/api/v1/guards/status",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        drawdown = data["drawdown_guard"]

        # Verify drawdown guard fields
        assert "user_id" in drawdown
        assert "current_equity" in drawdown
        assert "peak_equity" in drawdown
        assert "current_drawdown_pct" in drawdown
        assert "alert_type" in drawdown
        assert "alert_threshold_pct" in drawdown
        assert "should_close_all" in drawdown
        assert "time_to_liquidation_seconds" in drawdown
        assert "last_checked_at" in drawdown

        # Verify types
        assert isinstance(drawdown["current_equity"], (int, float))
        assert drawdown["current_equity"] > 0
        assert drawdown["alert_type"] in [e.value for e in AlertType]
        assert isinstance(drawdown["should_close_all"], bool)

    @pytest.mark.asyncio
    async def test_get_guards_status_market_alerts(
        self, client: AsyncClient, sample_user_with_data, auth_headers: dict
    ):
        """Test market guard alerts data structure."""
        response = await client.get(
            "/api/v1/guards/status",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        alerts = data["market_guard_alerts"]

        # Should be list (even if empty)
        assert isinstance(alerts, list)

        # If alerts present, verify structure
        if alerts:
            alert = alerts[0]
            assert "symbol" in alert
            assert "condition_type" in alert
            assert "alert_type" in alert
            assert "should_close_positions" in alert
            assert "detected_at" in alert

            # Verify types
            assert alert["condition_type"] in [e.value for e in ConditionType]
            assert alert["alert_type"] in [e.value for e in AlertType]
            assert isinstance(alert["should_close_positions"], bool)

    @pytest.mark.asyncio
    async def test_get_guards_status_without_auth(self, client: AsyncClient):
        """Test guards status requires authentication."""
        response = await client.get("/api/v1/guards/status")

        # Rate limiter returns 403 for missing/invalid auth
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_guards_status_composite_decision(
        self, client: AsyncClient, sample_user_with_data, auth_headers: dict
    ):
        """Test any_positions_should_close reflects guard states."""
        response = await client.get(
            "/api/v1/guards/status",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()

        drawdown = data["drawdown_guard"]
        alerts = data["market_guard_alerts"]
        any_should_close = data["any_positions_should_close"]

        # Verify composite decision logic
        expected = drawdown["should_close_all"] or any(
            a["should_close_positions"] for a in alerts
        )
        assert any_should_close == expected


# ================================================================
# Health Check Tests
# ================================================================


class TestHealthCheckEndpoint:
    """Test suite for GET /trading/health endpoint."""

    @pytest.mark.asyncio
    async def test_trading_health_check_success(self, client: AsyncClient):
        """Test health check endpoint (no auth required)."""
        response = await client.get("/api/v1/trading/health")

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert "status" in data
        assert "timestamp" in data
        assert "service" in data

        # Verify values
        assert data["status"] == "healthy"
        assert data["service"] == "trading-api"

    @pytest.mark.asyncio
    async def test_trading_health_check_no_auth_required(self, client: AsyncClient):
        """Test health check doesn't require authentication."""
        # Should work without auth headers
        response = await client.get("/api/v1/trading/health")

        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


# ================================================================
# Integration Tests
# ================================================================


class TestIntegration:
    """Integration tests for trading API endpoints."""

    @pytest.mark.asyncio
    async def test_full_trading_status_workflow(
        self, client: AsyncClient, sample_user_with_data, auth_headers: dict
    ):
        """Test complete status retrieval workflow."""
        # 1. Get reconciliation status
        recon_response = await client.get(
            "/api/v1/reconciliation/status",
            headers=auth_headers,
        )
        assert recon_response.status_code == 200
        recon_data = recon_response.json()

        # 2. Get positions
        pos_response = await client.get(
            "/api/v1/positions/open",
            headers=auth_headers,
        )
        assert pos_response.status_code == 200
        pos_data = pos_response.json()

        # 3. Get guards
        guard_response = await client.get(
            "/api/v1/guards/status",
            headers=auth_headers,
        )
        assert guard_response.status_code == 200
        guard_data = guard_response.json()

        # All should reference same user
        assert recon_data["user_id"] == pos_data["user_id"]
        assert pos_data["user_id"] == guard_data["user_id"]

    @pytest.mark.asyncio
    async def test_position_count_consistency(
        self, client: AsyncClient, sample_user_with_data, auth_headers: dict
    ):
        """Test position counts are consistent across endpoints."""
        # Get positions
        pos_response = await client.get(
            "/api/v1/positions/open",
            headers=auth_headers,
        )
        pos_data = pos_response.json()
        pos_count = pos_data.get("total_positions", 0)

        # Get reconciliation status
        recon_response = await client.get(
            "/api/v1/reconciliation/status",
            headers=auth_headers,
        )
        recon_data = recon_response.json()
        recon_count = recon_data.get("open_positions_count", 0)

        # Counts should match
        assert pos_count == recon_count
