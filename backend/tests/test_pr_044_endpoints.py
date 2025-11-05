"""
PR-044: Price Alerts & Notifications - HTTP Endpoint Integration Tests

Tests for PR-044 REST API endpoints:
- POST /api/v1/alerts - Create alert
- GET /api/v1/alerts - List alerts
- GET /api/v1/alerts/{id} - Get alert
- PUT /api/v1/alerts/{id} - Update alert
- DELETE /api/v1/alerts/{id} - Delete alert
- GET /api/v1/alerts/active - List active alerts

Including authorization, validation, error cases, and edge cases.
"""

import pytest
from httpx import AsyncClient

# ============================================================================
# POST /api/v1/alerts - CREATE ALERT
# ============================================================================


@pytest.mark.asyncio
async def test_create_alert_endpoint_valid(client: AsyncClient, auth_headers: dict):
    """Test creating alert via HTTP endpoint."""
    response = await client.post(
        "/api/v1/alerts",
        json={
            "symbol": "GOLD",
            "operator": "above",
            "price_level": 2000.0,
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    data = response.json()
    assert data["alert_id"] is not None
    assert data["symbol"] == "GOLD"
    assert data["operator"] == "above"
    assert data["price_level"] == 2000.0
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_create_alert_endpoint_below_operator(
    client: AsyncClient, auth_headers: dict
):
    """Test creating alert with 'below' operator."""
    response = await client.post(
        "/api/v1/alerts",
        json={
            "symbol": "EURUSD",
            "operator": "below",
            "price_level": 1.1000,
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    data = response.json()
    assert data["operator"] == "below"


@pytest.mark.asyncio
async def test_create_alert_endpoint_invalid_symbol(
    client: AsyncClient, auth_headers: dict
):
    """Test creating alert with invalid symbol returns 422."""
    response = await client.post(
        "/api/v1/alerts",
        json={
            "symbol": "INVALID",
            "operator": "above",
            "price_level": 2000.0,
        },
        headers=auth_headers,
    )

    assert response.status_code == 422
    detail = response.json()["detail"].lower()
    assert "symbol" in detail or "not supported" in detail or "validation" in detail


@pytest.mark.asyncio
async def test_create_alert_endpoint_invalid_operator(
    client: AsyncClient, auth_headers: dict
):
    """Test creating alert with invalid operator returns 400."""
    response = await client.post(
        "/api/v1/alerts",
        json={
            "symbol": "GOLD",
            "operator": "invalid",
            "price_level": 2000.0,
        },
        headers=auth_headers,
    )

    assert response.status_code == 400 or response.status_code == 422


@pytest.mark.asyncio
async def test_create_alert_endpoint_zero_price(
    client: AsyncClient, auth_headers: dict
):
    """Test creating alert with zero price returns 400."""
    response = await client.post(
        "/api/v1/alerts",
        json={
            "symbol": "GOLD",
            "operator": "above",
            "price_level": 0.0,
        },
        headers=auth_headers,
    )

    assert response.status_code == 400 or response.status_code == 422


@pytest.mark.asyncio
async def test_create_alert_endpoint_negative_price(
    client: AsyncClient, auth_headers: dict
):
    """Test creating alert with negative price returns 400."""
    response = await client.post(
        "/api/v1/alerts",
        json={
            "symbol": "GOLD",
            "operator": "above",
            "price_level": -100.0,
        },
        headers=auth_headers,
    )

    assert response.status_code == 400 or response.status_code == 422


@pytest.mark.asyncio
async def test_create_alert_endpoint_excessive_price(
    client: AsyncClient, auth_headers: dict
):
    """Test creating alert with price above max returns 400."""
    response = await client.post(
        "/api/v1/alerts",
        json={
            "symbol": "GOLD",
            "operator": "above",
            "price_level": 10_000_000.0,
        },
        headers=auth_headers,
    )

    assert response.status_code == 400 or response.status_code == 422


@pytest.mark.asyncio
async def test_create_alert_endpoint_duplicate(client: AsyncClient, auth_headers: dict):
    """Test creating duplicate alert returns 400."""
    # Create first alert
    response1 = await client.post(
        "/api/v1/alerts",
        json={
            "symbol": "GOLD",
            "operator": "above",
            "price_level": 2000.0,
        },
        headers=auth_headers,
    )
    assert response1.status_code == 201

    # Try to create same alert again
    response2 = await client.post(
        "/api/v1/alerts",
        json={
            "symbol": "GOLD",
            "operator": "above",
            "price_level": 2000.0,
        },
        headers=auth_headers,
    )
    assert response2.status_code == 400


@pytest.mark.asyncio
async def test_create_alert_endpoint_unauthorized(client: AsyncClient):
    """Test creating alert without authentication returns 401."""
    response = await client.post(
        "/api/v1/alerts",
        json={
            "symbol": "GOLD",
            "operator": "above",
            "price_level": 2000.0,
        },
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_alert_endpoint_missing_fields(
    client: AsyncClient, auth_headers: dict
):
    """Test creating alert without required fields."""
    response = await client.post(
        "/api/v1/alerts",
        json={
            "symbol": "GOLD",
            # Missing operator and price_level
        },
        headers=auth_headers,
    )

    assert response.status_code == 422


# ============================================================================
# GET /api/v1/alerts - LIST ALERTS
# ============================================================================


@pytest.mark.asyncio
async def test_list_alerts_endpoint_empty(client: AsyncClient, auth_headers: dict):
    """Test listing alerts when user has none."""
    response = await client.get("/api/v1/alerts", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 0


@pytest.mark.asyncio
async def test_list_alerts_endpoint_single(client: AsyncClient, auth_headers: dict):
    """Test listing alerts when user has one."""
    # Create alert
    create_response = await client.post(
        "/api/v1/alerts",
        json={
            "symbol": "GOLD",
            "operator": "above",
            "price_level": 2000.0,
        },
        headers=auth_headers,
    )
    assert create_response.status_code == 201

    # List alerts
    response = await client.get("/api/v1/alerts", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["symbol"] == "GOLD"


@pytest.mark.asyncio
async def test_list_alerts_endpoint_multiple(client: AsyncClient, auth_headers: dict):
    """Test listing multiple alerts."""
    # Create multiple alerts
    for i in range(3):
        response = await client.post(
            "/api/v1/alerts",
            json={
                "symbol": "GOLD",
                "operator": "above" if i % 2 == 0 else "below",
                "price_level": 2000.0 + i * 100,
            },
            headers=auth_headers,
        )
        assert response.status_code == 201

    # List alerts
    response = await client.get("/api/v1/alerts", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3


@pytest.mark.asyncio
async def test_list_alerts_endpoint_unauthorized(client: AsyncClient):
    """Test listing alerts without authentication returns 401."""
    response = await client.get("/api/v1/alerts")

    assert response.status_code == 401


# ============================================================================
# GET /api/v1/alerts/{id} - GET ALERT
# ============================================================================


@pytest.mark.asyncio
async def test_get_alert_endpoint_valid(client: AsyncClient, auth_headers: dict):
    """Test getting a single alert."""
    # Create alert
    create_response = await client.post(
        "/api/v1/alerts",
        json={
            "symbol": "GOLD",
            "operator": "above",
            "price_level": 2000.0,
        },
        headers=auth_headers,
    )
    alert_id = create_response.json()["alert_id"]

    # Get alert
    response = await client.get(f"/api/v1/alerts/{alert_id}", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["alert_id"] == alert_id
    assert data["symbol"] == "GOLD"


@pytest.mark.asyncio
async def test_get_alert_endpoint_not_found(client: AsyncClient, auth_headers: dict):
    """Test getting non-existent alert returns 404."""
    response = await client.get("/api/v1/alerts/non-existent-id", headers=auth_headers)

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_alert_endpoint_unauthorized(client: AsyncClient):
    """Test getting alert without authentication returns 401."""
    response = await client.get("/api/v1/alerts/some-id")

    assert response.status_code == 401


# ============================================================================
# PUT /api/v1/alerts/{id} - UPDATE ALERT
# ============================================================================


@pytest.mark.asyncio
async def test_update_alert_endpoint_toggle_active(
    client: AsyncClient, auth_headers: dict
):
    """Test updating alert to deactivate."""
    # Create alert
    create_response = await client.post(
        "/api/v1/alerts",
        json={
            "symbol": "GOLD",
            "operator": "above",
            "price_level": 2000.0,
        },
        headers=auth_headers,
    )
    alert_id = create_response.json()["alert_id"]

    # Update alert to inactive
    response = await client.put(
        f"/api/v1/alerts/{alert_id}",
        json={"is_active": False},
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["is_active"] is False


@pytest.mark.asyncio
async def test_update_alert_endpoint_change_price(
    client: AsyncClient, auth_headers: dict
):
    """Test updating alert price level."""
    # Create alert
    create_response = await client.post(
        "/api/v1/alerts",
        json={
            "symbol": "GOLD",
            "operator": "above",
            "price_level": 2000.0,
        },
        headers=auth_headers,
    )
    alert_id = create_response.json()["alert_id"]

    # Update price
    response = await client.put(
        f"/api/v1/alerts/{alert_id}",
        json={"price_level": 2050.0},
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["price_level"] == 2050.0


@pytest.mark.asyncio
async def test_update_alert_endpoint_not_found(client: AsyncClient, auth_headers: dict):
    """Test updating non-existent alert returns 404."""
    response = await client.put(
        "/api/v1/alerts/non-existent-id",
        json={"is_active": False},
        headers=auth_headers,
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_alert_endpoint_unauthorized(client: AsyncClient):
    """Test updating alert without authentication returns 401."""
    response = await client.put(
        "/api/v1/alerts/some-id",
        json={"is_active": False},
    )

    assert response.status_code == 401


# ============================================================================
# DELETE /api/v1/alerts/{id} - DELETE ALERT
# ============================================================================


@pytest.mark.asyncio
async def test_delete_alert_endpoint_valid(client: AsyncClient, auth_headers: dict):
    """Test deleting an alert."""
    # Create alert
    create_response = await client.post(
        "/api/v1/alerts",
        json={
            "symbol": "GOLD",
            "operator": "above",
            "price_level": 2000.0,
        },
        headers=auth_headers,
    )
    alert_id = create_response.json()["alert_id"]

    # Delete alert
    response = await client.delete(f"/api/v1/alerts/{alert_id}", headers=auth_headers)

    assert response.status_code == 204

    # Verify deleted
    get_response = await client.get(f"/api/v1/alerts/{alert_id}", headers=auth_headers)
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_delete_alert_endpoint_not_found(client: AsyncClient, auth_headers: dict):
    """Test deleting non-existent alert returns 404."""
    response = await client.delete(
        "/api/v1/alerts/non-existent-id", headers=auth_headers
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_alert_endpoint_unauthorized(client: AsyncClient):
    """Test deleting alert without authentication returns 401."""
    response = await client.delete("/api/v1/alerts/some-id")

    assert response.status_code == 401


# ============================================================================
# GET /api/v1/alerts/active - LIST ACTIVE ALERTS
# ============================================================================


@pytest.mark.asyncio
async def test_list_active_alerts_endpoint_mixed(
    client: AsyncClient, auth_headers: dict
):
    """Test listing only active alerts."""
    # Create 2 alerts
    create1 = await client.post(
        "/api/v1/alerts",
        json={
            "symbol": "GOLD",
            "operator": "above",
            "price_level": 2000.0,
        },
        headers=auth_headers,
    )
    alert_id_1 = create1.json()["alert_id"]

    create2 = await client.post(
        "/api/v1/alerts",
        json={
            "symbol": "EURUSD",
            "operator": "below",
            "price_level": 1.1000,
        },
        headers=auth_headers,
    )
    alert_id_2 = create2.json()["alert_id"]

    # Deactivate one alert
    await client.put(
        f"/api/v1/alerts/{alert_id_1}",
        json={"is_active": False},
        headers=auth_headers,
    )

    # List active alerts
    response = await client.get("/api/v1/alerts/active", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["alert_id"] == alert_id_2
    assert data[0]["is_active"] is True


@pytest.mark.asyncio
async def test_list_active_alerts_endpoint_empty(
    client: AsyncClient, auth_headers: dict
):
    """Test listing active alerts when all are inactive."""
    # Create alert
    create = await client.post(
        "/api/v1/alerts",
        json={
            "symbol": "GOLD",
            "operator": "above",
            "price_level": 2000.0,
        },
        headers=auth_headers,
    )
    alert_id = create.json()["alert_id"]

    # Deactivate
    await client.put(
        f"/api/v1/alerts/{alert_id}",
        json={"is_active": False},
        headers=auth_headers,
    )

    # List active
    response = await client.get("/api/v1/alerts/active", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 0


@pytest.mark.asyncio
async def test_list_active_alerts_endpoint_unauthorized(client: AsyncClient):
    """Test listing active alerts without authentication returns 401."""
    response = await client.get("/api/v1/alerts/active")

    assert response.status_code == 401


# ============================================================================
# MULTI-USER ISOLATION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_alert_isolation_different_users(
    client: AsyncClient, auth_headers: dict, auth_headers_user2: dict
):
    """Test that users can't see each other's alerts."""
    # User 1 creates alert
    response1 = await client.post(
        "/api/v1/alerts",
        json={
            "symbol": "GOLD",
            "operator": "above",
            "price_level": 2000.0,
        },
        headers=auth_headers,
    )
    assert response1.status_code == 201

    # User 2 lists alerts
    response2 = await client.get("/api/v1/alerts", headers=auth_headers_user2)
    assert response2.status_code == 200
    data = response2.json()
    assert len(data) == 0  # User 2 shouldn't see User 1's alerts


@pytest.mark.asyncio
async def test_alert_delete_isolation_different_users(
    client: AsyncClient, auth_headers: dict, auth_headers_user2: dict
):
    """Test that user can't delete another user's alert."""
    # User 1 creates alert
    response1 = await client.post(
        "/api/v1/alerts",
        json={
            "symbol": "GOLD",
            "operator": "above",
            "price_level": 2000.0,
        },
        headers=auth_headers,
    )
    alert_id = response1.json()["alert_id"]

    # User 2 tries to delete User 1's alert
    response2 = await client.delete(
        f"/api/v1/alerts/{alert_id}", headers=auth_headers_user2
    )
    assert response2.status_code == 404


# ============================================================================
# VALIDATION & EDGE CASE TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_alert_all_symbols_valid(client: AsyncClient, auth_headers: dict):
    """Test that all valid symbols can be used."""
    from backend.app.alerts.service import VALID_SYMBOLS

    for symbol in list(VALID_SYMBOLS)[:5]:  # Test first 5
        response = await client.post(
            "/api/v1/alerts",
            json={
                "symbol": symbol,
                "operator": "above",
                "price_level": 1000.0,
            },
            headers=auth_headers,
        )
        assert response.status_code == 201


@pytest.mark.asyncio
async def test_alert_boundary_price_low(client: AsyncClient, auth_headers: dict):
    """Test creating alert at low price boundary."""
    response = await client.post(
        "/api/v1/alerts",
        json={
            "symbol": "GOLD",
            "operator": "above",
            "price_level": 0.01,
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    assert response.json()["price_level"] == 0.01


@pytest.mark.asyncio
async def test_alert_boundary_price_high(client: AsyncClient, auth_headers: dict):
    """Test creating alert at high price boundary."""
    response = await client.post(
        "/api/v1/alerts",
        json={
            "symbol": "GOLD",
            "operator": "above",
            "price_level": 999999.99,
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    assert response.json()["price_level"] == 999999.99


@pytest.mark.asyncio
async def test_alert_malformed_json(client: AsyncClient, auth_headers: dict):
    """Test creating alert with malformed JSON."""
    response = await client.post(
        "/api/v1/alerts",
        content="not json",
        headers=auth_headers,
    )

    assert response.status_code in [400, 422]


@pytest.mark.asyncio
async def test_alert_response_schema(client: AsyncClient, auth_headers: dict):
    """Test that alert response includes all required fields."""
    response = await client.post(
        "/api/v1/alerts",
        json={
            "symbol": "GOLD",
            "operator": "above",
            "price_level": 2000.0,
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    data = response.json()

    # Verify all required fields present
    assert "alert_id" in data
    assert "symbol" in data
    assert "operator" in data
    assert "price_level" in data
    assert "is_active" in data
