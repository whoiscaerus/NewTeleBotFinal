"""Comprehensive tests for PR-075 Trading Control API routes.

Tests validate REAL HTTP request/response cycles:
- PATCH /trading/pause - Pauses trading with telemetry
- PATCH /trading/resume - Resumes trading on next candle
- PUT /trading/size - Updates position size override
- GET /trading/status - Returns comprehensive status

NO MOCKS - Real FastAPI client, real database, real auth.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

# ============================================================================
# Test: PATCH /trading/pause
# ============================================================================


@pytest.mark.asyncio
async def test_pause_trading_endpoint_success(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
    current_user: dict,
):
    """Test PATCH /trading/pause pauses trading successfully.

    Business Logic:
    - Returns 200 with TradingStatusOut
    - is_paused=True in response
    - Telemetry incremented
    """
    response = await client.patch(
        "/api/v1/trading/pause",
        json={"reason": "Manual pause for risk review"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()

    assert data["is_paused"] is True
    assert data["paused_by"] == "user"
    assert data["pause_reason"] == "Manual pause for risk review"
    assert "paused_at" in data
    assert "updated_at" in data


@pytest.mark.asyncio
async def test_pause_trading_endpoint_without_reason(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
    current_user: dict,
):
    """Test pause works without reason (optional field)."""
    response = await client.patch(
        "/api/v1/trading/pause",
        json={},  # No reason provided
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()

    assert data["is_paused"] is True
    assert data["pause_reason"] is None  # Optional field


@pytest.mark.asyncio
async def test_pause_trading_endpoint_fails_when_already_paused(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
    current_user: dict,
):
    """Test double pause returns 400 error.

    Business Logic:
    - First pause succeeds (200)
    - Second pause fails (400)
    - Error message clear and actionable
    """
    # First pause
    response1 = await client.patch(
        "/api/v1/trading/pause",
        json={},
        headers=auth_headers,
    )
    assert response1.status_code == 200

    # Second pause fails
    response2 = await client.patch(
        "/api/v1/trading/pause",
        json={},
        headers=auth_headers,
    )
    assert response2.status_code == 400
    assert "already paused" in response2.json()["detail"]


@pytest.mark.asyncio
async def test_pause_trading_endpoint_requires_auth(
    client: AsyncClient,
    db_session: AsyncSession,
):
    """Test pause requires authentication.

    Business Logic:
    - No auth token → 401 Unauthorized
    - Prevents anonymous pause operations
    """
    response = await client.patch(
        "/api/v1/trading/pause",
        json={},
    )

    assert response.status_code == 401


# ============================================================================
# Test: PATCH /trading/resume
# ============================================================================


@pytest.mark.asyncio
async def test_resume_trading_endpoint_success(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
    current_user: dict,
):
    """Test PATCH /trading/resume resumes trading successfully.

    Business Logic:
    - Pause first, then resume
    - Returns 200 with TradingStatusOut
    - is_paused=False in response
    - Preserves pause history for audit
    """
    # Pause first
    await client.patch(
        "/api/v1/trading/pause",
        json={},
        headers=auth_headers,
    )

    # Resume
    response = await client.patch(
        "/api/v1/trading/resume",
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()

    assert data["is_paused"] is False
    # History preserved
    assert data["paused_at"] is not None  # Still has timestamp
    assert data["paused_by"] is not None  # Still has actor


@pytest.mark.asyncio
async def test_resume_trading_endpoint_fails_when_already_running(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
    current_user: dict,
):
    """Test double resume returns 400 error.

    Business Logic:
    - Trading starts running by default
    - Resume without pause fails (400)
    - Error message clear and actionable
    """
    response = await client.patch(
        "/api/v1/trading/resume",
        headers=auth_headers,
    )

    assert response.status_code == 400
    assert "already running" in response.json()["detail"]


@pytest.mark.asyncio
async def test_resume_trading_endpoint_requires_auth(
    client: AsyncClient,
    db_session: AsyncSession,
):
    """Test resume requires authentication."""
    response = await client.patch(
        "/api/v1/trading/resume",
    )

    assert response.status_code == 401


# ============================================================================
# Test: PUT /trading/size
# ============================================================================


@pytest.mark.asyncio
async def test_update_position_size_endpoint_sets_override(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
    current_user: dict,
):
    """Test PUT /trading/size sets position size override.

    Business Logic:
    - Returns 200 with TradingStatusOut
    - position_size_override=X in response
    - Overrides default risk % calculations
    """
    response = await client.put(
        "/api/v1/trading/size",
        json={"position_size": "0.5"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()

    assert data["position_size_override"] == 0.5


@pytest.mark.asyncio
async def test_update_position_size_endpoint_clears_override_with_null(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
    current_user: dict,
):
    """Test null clears position size override.

    Business Logic:
    - position_size=null → use default risk %
    - Enables switching between manual and automatic sizing
    """
    # Set override
    await client.put(
        "/api/v1/trading/size",
        json={"position_size": "0.5"},
        headers=auth_headers,
    )

    # Clear override
    response = await client.put(
        "/api/v1/trading/size",
        json={"position_size": None},
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()

    assert data["position_size_override"] is None


@pytest.mark.asyncio
async def test_update_position_size_endpoint_validates_minimum(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
    current_user: dict,
):
    """Test size rejects < 0.01 lots.

    Business Logic:
    - Minimum 0.01 lots (broker standard)
    - Returns 400 with clear error message
    """
    response = await client.put(
        "/api/v1/trading/size",
        json={"position_size": "0.001"},  # Too small
        headers=auth_headers,
    )

    assert response.status_code == 400
    assert "0.01 lots" in response.json()["detail"]


@pytest.mark.asyncio
async def test_update_position_size_endpoint_validates_maximum(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
    current_user: dict,
):
    """Test size rejects > 100 lots.

    Business Logic:
    - Maximum 100 lots (platform limit)
    - Returns 400 with clear error message
    """
    response = await client.put(
        "/api/v1/trading/size",
        json={"position_size": "101"},  # Too large
        headers=auth_headers,
    )

    assert response.status_code == 400
    assert "100 lots" in response.json()["detail"]


@pytest.mark.asyncio
async def test_update_position_size_endpoint_accepts_valid_range(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
    current_user: dict,
):
    """Test size accepts values in valid range.

    Business Logic:
    - 0.01 to 100 lots accepted
    - Returns 200 for all valid values
    """
    valid_sizes = ["0.01", "0.5", "1.0", "10.0", "100"]

    for size in valid_sizes:
        response = await client.put(
            "/api/v1/trading/size",
            json={"position_size": size},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["position_size_override"] == float(size)


@pytest.mark.asyncio
async def test_update_position_size_endpoint_requires_auth(
    client: AsyncClient,
    db_session: AsyncSession,
):
    """Test size update requires authentication."""
    response = await client.put(
        "/api/v1/trading/size",
        json={"position_size": "0.5"},
    )

    assert response.status_code == 401


# ============================================================================
# Test: GET /trading/status
# ============================================================================


@pytest.mark.asyncio
async def test_get_trading_status_endpoint_returns_default_state(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
    current_user: dict,
):
    """Test GET /trading/status returns default running state.

    Business Logic:
    - New user starts with trading enabled
    - Returns comprehensive status
    - Creates control if doesn't exist
    """
    response = await client.get(
        "/api/v1/trading/status",
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()

    assert data["is_paused"] is False  # Default running
    assert data["paused_at"] is None
    assert data["paused_by"] is None
    assert data["pause_reason"] is None
    assert data["position_size_override"] is None
    assert data["notifications_enabled"] is True
    assert "updated_at" in data


@pytest.mark.asyncio
async def test_get_trading_status_endpoint_reflects_paused_state(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
    current_user: dict,
):
    """Test status endpoint reflects paused state after pause.

    Business Logic:
    - Pause changes state
    - Status endpoint immediately reflects change
    - Returns all pause metadata
    """
    # Pause trading
    await client.patch(
        "/api/v1/trading/pause",
        json={"reason": "Testing status"},
        headers=auth_headers,
    )

    # Get status
    response = await client.get(
        "/api/v1/trading/status",
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()

    assert data["is_paused"] is True
    assert data["paused_by"] == "user"
    assert data["pause_reason"] == "Testing status"
    assert data["paused_at"] is not None


@pytest.mark.asyncio
async def test_get_trading_status_endpoint_reflects_position_size_override(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
    current_user: dict,
):
    """Test status endpoint reflects position size override.

    Business Logic:
    - Size update changes state
    - Status endpoint immediately reflects change
    """
    # Set position size
    await client.put(
        "/api/v1/trading/size",
        json={"position_size": "0.75"},
        headers=auth_headers,
    )

    # Get status
    response = await client.get(
        "/api/v1/trading/status",
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()

    assert data["position_size_override"] == 0.75


@pytest.mark.asyncio
async def test_get_trading_status_endpoint_requires_auth(
    client: AsyncClient,
    db_session: AsyncSession,
):
    """Test status requires authentication."""
    response = await client.get(
        "/api/v1/trading/status",
    )

    assert response.status_code == 401


# ============================================================================
# Test: Integration Flows
# ============================================================================


@pytest.mark.asyncio
async def test_full_pause_resume_cycle_via_api(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
    current_user: dict,
):
    """Test complete pause/resume cycle through API.

    Business Logic:
    - Status starts running
    - Pause stops trading
    - Resume restarts trading
    - All state changes reflected in status endpoint
    """
    # Initial status (running)
    response1 = await client.get("/api/v1/trading/status", headers=auth_headers)
    assert response1.json()["is_paused"] is False

    # Pause
    response2 = await client.patch(
        "/api/v1/trading/pause",
        json={"reason": "Testing cycle"},
        headers=auth_headers,
    )
    assert response2.json()["is_paused"] is True

    # Status reflects pause
    response3 = await client.get("/api/v1/trading/status", headers=auth_headers)
    assert response3.json()["is_paused"] is True

    # Resume
    response4 = await client.patch("/api/v1/trading/resume", headers=auth_headers)
    assert response4.json()["is_paused"] is False

    # Status reflects resume
    response5 = await client.get("/api/v1/trading/status", headers=auth_headers)
    assert response5.json()["is_paused"] is False
    # History preserved
    assert response5.json()["paused_at"] is not None


@pytest.mark.asyncio
async def test_position_size_changes_via_api(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
    current_user: dict,
):
    """Test position size updates through API.

    Business Logic:
    - Set override
    - Change override
    - Clear override (use default)
    """
    # Set override
    response1 = await client.put(
        "/api/v1/trading/size",
        json={"position_size": "0.5"},
        headers=auth_headers,
    )
    assert response1.json()["position_size_override"] == 0.5

    # Change override
    response2 = await client.put(
        "/api/v1/trading/size",
        json={"position_size": "1.0"},
        headers=auth_headers,
    )
    assert response2.json()["position_size_override"] == 1.0

    # Clear override
    response3 = await client.put(
        "/api/v1/trading/size",
        json={"position_size": None},
        headers=auth_headers,
    )
    assert response3.json()["position_size_override"] is None

    # Status reflects cleared override
    response4 = await client.get("/api/v1/trading/status", headers=auth_headers)
    assert response4.json()["position_size_override"] is None


@pytest.mark.asyncio
async def test_pause_with_position_size_override(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
    current_user: dict,
):
    """Test pause and size override work independently.

    Business Logic:
    - Can pause while size override active
    - Size override persists through pause/resume
    - Independent controls don't interfere
    """
    # Set position size
    await client.put(
        "/api/v1/trading/size",
        json={"position_size": "0.5"},
        headers=auth_headers,
    )

    # Pause trading
    response = await client.patch(
        "/api/v1/trading/pause",
        json={},
        headers=auth_headers,
    )

    data = response.json()
    assert data["is_paused"] is True
    assert data["position_size_override"] == 0.5  # Still set

    # Resume trading
    response2 = await client.patch(
        "/api/v1/trading/resume",
        headers=auth_headers,
    )

    data2 = response2.json()
    assert data2["is_paused"] is False
    assert data2["position_size_override"] == 0.5  # Still set


@pytest.mark.asyncio
async def test_concurrent_users_independent_controls(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
    auth_headers_2: dict,
    current_user: dict,
    current_user_2: dict,
):
    """Test different users have independent trading controls.

    Business Logic:
    - Each user has own TradingControl record
    - User 1 pause doesn't affect User 2
    - Prevents cross-user interference
    """
    # User 1 pauses
    response1 = await client.patch(
        "/api/v1/trading/pause",
        json={},
        headers=auth_headers,
    )
    assert response1.json()["is_paused"] is True

    # User 2 status still running
    response2 = await client.get(
        "/api/v1/trading/status",
        headers=auth_headers_2,
    )
    assert response2.json()["is_paused"] is False

    # User 2 sets different position size
    response3 = await client.put(
        "/api/v1/trading/size",
        json={"position_size": "1.0"},
        headers=auth_headers_2,
    )
    assert response3.json()["position_size_override"] == 1.0

    # User 1 status unaffected
    response4 = await client.get(
        "/api/v1/trading/status",
        headers=auth_headers,
    )
    assert response4.json()["is_paused"] is True
    assert response4.json()["position_size_override"] is None
