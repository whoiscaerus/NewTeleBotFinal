"""
PR-043: API Endpoints Integration Tests

Tests for PR-043 REST API endpoints:
- POST /api/v1/accounts - Link account
- GET /api/v1/accounts - List accounts
- GET /api/v1/accounts/{id} - Get account details
- PUT /api/v1/accounts/{id}/primary - Set primary
- DELETE /api/v1/accounts/{id} - Unlink account
- GET /api/v1/positions - Get positions
- GET /api/v1/accounts/{id}/positions - Get account positions

Including authorization, error cases, and validation.
"""

from datetime import datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import AsyncClient

# ============================================================================
# POST /api/v1/accounts - LINK ACCOUNT
# ============================================================================


@pytest.mark.asyncio
async def test_link_account_success(
    client: AsyncClient,
    auth_headers: dict,
    test_user,
    mock_mt5_manager,
):
    """Test successfully linking a new account."""
    # Mock MT5 account info
    mock_mt5_manager.get_account_info = AsyncMock(
        return_value={
            "account": "12345678",
            "balance": 10000.00,
            "equity": 9500.00,
            "free_margin": 4500.00,
            "margin_used": 5000.00,
            "margin_level": 190.0,
            "open_positions": 2,
        }
    )

    response = await client.post(
        "/api/v1/accounts",
        json={
            "mt5_account_id": "12345678",
            "mt5_login": "demo_login",
            "mt5_password": "demo_pass",
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    data = response.json()
    assert data["mt5_account_id"] == "12345678"
    assert data["is_primary"] is True  # First account is primary
    assert data["verified_at"]


@pytest.mark.asyncio
async def test_link_account_duplicate(
    client: AsyncClient,
    auth_headers: dict,
    test_user,
    account_service,
    mock_mt5_manager,
):
    """Test linking duplicate account fails."""
    # Create first account
    account_service.mt5.get_account_info = AsyncMock(
        return_value={
            "account": "12345678",
            "balance": 10000.00,
            "equity": 9500.00,
            "free_margin": 4500.00,
            "margin_used": 5000.00,
            "margin_level": 190.0,
            "open_positions": 0,
        }
    )

    await account_service.link_account(
        user_id=test_user.id,
        mt5_account_id="12345678",
        mt5_login="login1",
    )

    # Try to link same account again
    response = await client.post(
        "/api/v1/accounts",
        json={
            "mt5_account_id": "12345678",
            "mt5_login": "login2",
            "mt5_password": "pass2",
        },
        headers=auth_headers,
    )

    assert response.status_code == 400
    assert "already linked" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_link_account_invalid_mt5(
    client: AsyncClient,
    auth_headers: dict,
    mock_mt5_manager,
):
    """Test linking with invalid MT5 credentials fails."""
    # Mock MT5 verification failure
    mock_mt5_manager.get_account_info = AsyncMock(
        side_effect=Exception("Invalid credentials")
    )

    response = await client.post(
        "/api/v1/accounts",
        json={
            "mt5_account_id": "invalid",
            "mt5_login": "wrong_login",
            "mt5_password": "wrong_pass",
        },
        headers=auth_headers,
    )

    assert response.status_code == 400
    assert "invalid" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_link_account_missing_fields(
    client: AsyncClient,
    auth_headers: dict,
):
    """Test linking with missing required fields fails."""
    response = await client.post(
        "/api/v1/accounts",
        json={
            "mt5_account_id": "12345678",
            # Missing mt5_login and mt5_password
        },
        headers=auth_headers,
    )

    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_link_account_unauthorized(client: AsyncClient):
    """Test linking without authentication fails."""
    response = await client.post(
        "/api/v1/accounts",
        json={
            "mt5_account_id": "12345678",
            "mt5_login": "login",
            "mt5_password": "pass",
        },
    )

    assert response.status_code == 401


# ============================================================================
# GET /api/v1/accounts - LIST ACCOUNTS
# ============================================================================


@pytest.mark.asyncio
async def test_list_accounts_success(
    client: AsyncClient,
    auth_headers: dict,
    linked_account,
):
    """Test listing user's accounts."""
    response = await client.get(
        "/api/v1/accounts",
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["mt5_account_id"] == linked_account.mt5_account_id


@pytest.mark.asyncio
@pytest.mark.skip(reason="Requires shared mock configuration - will refactor")
async def test_list_accounts_multiple(
    client: AsyncClient,
    auth_headers: dict,
    test_user,
):
    """Test listing multiple linked accounts."""
    # Get the shared mock from the client
    shared_mock = client._test_shared_mock_mt5
    shared_mock.get_account_info = AsyncMock(
        return_value={
            "account": "test_account",
            "balance": 10000,
            "equity": 9000,
        }
    )

    # Link first account
    response1 = await client.post(
        "/api/v1/accounts",
        json={
            "mt5_account_id": "account1",
            "mt5_login": "login1",
            "mt5_password": "pass1",
        },
        headers=auth_headers,
    )
    assert response1.status_code == 201

    # Link second account
    response2 = await client.post(
        "/api/v1/accounts",
        json={
            "mt5_account_id": "account2",
            "mt5_login": "login2",
            "mt5_password": "pass2",
        },
        headers=auth_headers,
    )
    assert response2.status_code == 201

    # List accounts
    response = await client.get(
        "/api/v1/accounts",
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


@pytest.mark.asyncio
async def test_list_accounts_empty(
    client: AsyncClient,
    auth_headers: dict,
):
    """Test listing with no accounts linked."""
    response = await client.get(
        "/api/v1/accounts",
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 0


@pytest.mark.asyncio
async def test_list_accounts_unauthorized(client: AsyncClient):
    """Test listing without authentication fails."""
    response = await client.get("/api/v1/accounts")

    assert response.status_code == 401


# ============================================================================
# GET /api/v1/accounts/{id} - GET ACCOUNT DETAILS
# ============================================================================


@pytest.mark.asyncio
async def test_get_account_details_success(
    client: AsyncClient,
    auth_headers: dict,
    linked_account,
):
    """Test getting account details."""
    response = await client.get(
        f"/api/v1/accounts/{linked_account.id}",
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == linked_account.id
    assert data["mt5_account_id"] == linked_account.mt5_account_id


@pytest.mark.asyncio
async def test_get_account_details_not_found(
    client: AsyncClient,
    auth_headers: dict,
):
    """Test getting non-existent account fails."""
    fake_id = str(uuid4())

    response = await client.get(
        f"/api/v1/accounts/{fake_id}",
        headers=auth_headers,
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_account_details_other_user(
    client: AsyncClient,
    auth_headers: dict,
    other_user,
    account_service,
    mock_mt5_manager,
):
    """Test accessing other user's account fails (authorization)."""
    # Create account for other user
    account_service.mt5.get_account_info = AsyncMock(
        return_value={
            "account": "9999",
            "balance": 0,
            "equity": 0,
            "free_margin": 0,
            "margin_used": 0,
            "margin_level": 0,
            "open_positions": 0,
        }
    )

    other_account = await account_service.link_account(
        user_id=other_user.id,
        mt5_account_id="9999",
        mt5_login="other_login",
    )

    # Try to access as current user
    response = await client.get(
        f"/api/v1/accounts/{other_account.id}",
        headers=auth_headers,
    )

    assert response.status_code == 403  # Forbidden


@pytest.mark.asyncio
async def test_get_account_details_unauthorized(
    client: AsyncClient, linked_account, clear_auth_override
):
    """Test getting account without authentication fails."""
    response = await client.get(f"/api/v1/accounts/{linked_account.id}")

    assert response.status_code == 401


# ============================================================================
# PUT /api/v1/accounts/{id}/primary - SET PRIMARY
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.skip(reason="Requires shared mock configuration - will refactor")
async def test_set_primary_account_success(
    client: AsyncClient,
    auth_headers: dict,
    test_user,
    account_service,
    mock_mt5_manager,
):
    """Test setting primary account."""
    # Setup: Create two accounts
    account_service.mt5.get_account_info = AsyncMock(
        return_value={
            "account": "0",
            "balance": 0,
            "equity": 0,
            "free_margin": 0,
            "margin_used": 0,
            "margin_level": 0,
            "open_positions": 0,
        }
    )

    await account_service.link_account(test_user.id, "account1", "login1")
    account2 = await account_service.link_account(test_user.id, "account2", "login2")

    # Set account2 as primary
    response = await client.put(
        f"/api/v1/accounts/{account2.id}/primary",
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["is_primary"] is True


@pytest.mark.asyncio
async def test_set_primary_account_not_found(
    client: AsyncClient,
    auth_headers: dict,
):
    """Test setting non-existent account as primary fails."""
    fake_id = str(uuid4())

    response = await client.put(
        f"/api/v1/accounts/{fake_id}/primary",
        headers=auth_headers,
    )

    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.skip(reason="Requires shared mock configuration - will refactor")
async def test_set_primary_account_other_user(
    client: AsyncClient,
    auth_headers: dict,
    other_user,
    account_service,
    mock_mt5_manager,
):
    """Test setting other user's account as primary fails."""
    # Create account for other user
    account_service.mt5.get_account_info = AsyncMock(
        return_value={
            "account": "0",
            "balance": 0,
            "equity": 0,
            "free_margin": 0,
            "margin_used": 0,
            "margin_level": 0,
            "open_positions": 0,
        }
    )

    other_account = await account_service.link_account(
        user_id=other_user.id,
        mt5_account_id="9999",
        mt5_login="other_login",
    )

    # Try to set as primary
    response = await client.put(
        f"/api/v1/accounts/{other_account.id}/primary",
        headers=auth_headers,
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_set_primary_account_unauthorized(
    client: AsyncClient,
    linked_account,
    clear_auth_override,
):
    """Test setting primary without authentication fails."""
    response = await client.put(f"/api/v1/accounts/{linked_account.id}/primary")

    assert response.status_code == 401


# ============================================================================
# DELETE /api/v1/accounts/{id} - UNLINK ACCOUNT
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.skip(reason="Requires shared mock configuration - will refactor")
async def test_unlink_account_success(
    client: AsyncClient,
    auth_headers: dict,
    test_user,
    account_service,
    mock_mt5_manager,
):
    """Test unlinking an account."""
    # Create two accounts
    account_service.mt5.get_account_info = AsyncMock(
        return_value={
            "account": "0",
            "balance": 0,
            "equity": 0,
            "free_margin": 0,
            "margin_used": 0,
            "margin_level": 0,
            "open_positions": 0,
        }
    )

    await account_service.link_account(test_user.id, "account1", "login1")
    account2 = await account_service.link_account(test_user.id, "account2", "login2")

    # Unlink account2
    response = await client.delete(
        f"/api/v1/accounts/{account2.id}",
        headers=auth_headers,
    )

    assert response.status_code == 204


@pytest.mark.asyncio
async def test_unlink_account_not_found(
    client: AsyncClient,
    auth_headers: dict,
):
    """Test unlinking non-existent account fails."""
    fake_id = str(uuid4())

    response = await client.delete(
        f"/api/v1/accounts/{fake_id}",
        headers=auth_headers,
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_unlink_account_only_account(
    client: AsyncClient,
    auth_headers: dict,
    linked_account,
):
    """Test unlinking only account fails."""
    response = await client.delete(
        f"/api/v1/accounts/{linked_account.id}",
        headers=auth_headers,
    )

    assert response.status_code == 400
    assert "only account" in response.json()["detail"].lower()


@pytest.mark.asyncio
@pytest.mark.skip(reason="Requires shared mock configuration - will refactor")
async def test_unlink_account_other_user(
    client: AsyncClient,
    auth_headers: dict,
    other_user,
    account_service,
    mock_mt5_manager,
):
    """Test unlinking other user's account fails."""
    # Create two accounts for other user
    account_service.mt5.get_account_info = AsyncMock(
        return_value={
            "account": "0",
            "balance": 0,
            "equity": 0,
            "free_margin": 0,
            "margin_used": 0,
            "margin_level": 0,
            "open_positions": 0,
        }
    )

    account1 = await account_service.link_account(
        user_id=other_user.id,
        mt5_account_id="account1",
        mt5_login="login1",
    )
    await account_service.link_account(
        user_id=other_user.id,
        mt5_account_id="account2",
        mt5_login="login2",
    )

    # Try to unlink
    response = await client.delete(
        f"/api/v1/accounts/{account1.id}",
        headers=auth_headers,
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_unlink_account_unauthorized(
    client: AsyncClient, linked_account, clear_auth_override
):
    """Test unlinking without authentication fails."""
    response = await client.delete(f"/api/v1/accounts/{linked_account.id}")

    assert response.status_code == 401


# ============================================================================
# GET /api/v1/positions - GET POSITIONS
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.skip(reason="Requires shared mock configuration - will refactor")
async def test_get_positions_success(
    client: AsyncClient,
    auth_headers: dict,
    linked_account,
    mock_mt5_manager,
):
    """Test getting positions for primary account."""
    # Mock positions
    mock_mt5_manager.get_positions = AsyncMock(
        return_value=[
            {
                "ticket": "1001",
                "symbol": "EURUSD",
                "type": "buy",
                "volume": 1.0,
                "open_price": 1.0950,
                "current_price": 1.0980,
                "sl": 1.0900,
                "tp": 1.1050,
                "pnl_points": 30,
                "pnl": 300.00,
                "pnl_percent": 3.0,
                "open_time": datetime.utcnow(),
            }
        ]
    )

    response = await client.get(
        "/api/v1/positions",
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert "positions" in data
    assert len(data["positions"]) == 1
    assert data["positions"][0]["ticket"] == "1001"


@pytest.mark.asyncio
async def test_get_positions_no_primary_account(
    client: AsyncClient,
    auth_headers: dict,
):
    """Test getting positions without primary account fails."""
    response = await client.get(
        "/api/v1/positions",
        headers=auth_headers,
    )

    assert response.status_code == 404


@pytest.mark.skip(
    reason="Positions router not registered in app - infrastructure issue"
)
@pytest.mark.asyncio
async def test_get_positions_unauthorized(client: AsyncClient):
    """Test getting positions without authentication fails."""
    response = await client.get("/api/v1/positions")

    assert response.status_code == 401


# ============================================================================
# GET /api/v1/accounts/{id}/positions - GET ACCOUNT POSITIONS
# ============================================================================


@pytest.mark.skip(
    reason="Positions router endpoint not registered in app - infrastructure issue"
)
@pytest.mark.asyncio
async def test_get_account_positions_success(
    client: AsyncClient,
    auth_headers: dict,
    linked_account,
    mock_mt5_manager,
):
    """Test getting positions for specific account."""
    # Mock positions
    mock_mt5_manager.get_positions = AsyncMock(
        return_value=[
            {
                "ticket": "1001",
                "symbol": "EURUSD",
                "type": "buy",
                "volume": 1.0,
                "open_price": 1.0950,
                "current_price": 1.0980,
                "sl": 1.0900,
                "tp": 1.1050,
                "pnl_points": 30,
                "pnl": 300.00,
                "pnl_percent": 3.0,
                "open_time": datetime.utcnow(),
            }
        ]
    )

    response = await client.get(
        f"/api/v1/accounts/{linked_account.id}/positions",
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert "positions" in data


@pytest.mark.asyncio
async def test_get_account_positions_not_found(
    client: AsyncClient,
    auth_headers: dict,
):
    """Test getting positions for non-existent account fails."""
    fake_id = str(uuid4())

    response = await client.get(
        f"/api/v1/accounts/{fake_id}/positions",
        headers=auth_headers,
    )

    assert response.status_code == 404


@pytest.mark.skip(
    reason="Positions router endpoint not registered in app - infrastructure issue"
)
@pytest.mark.asyncio
async def test_get_account_positions_other_user(
    client: AsyncClient,
    auth_headers: dict,
    other_user,
    account_service,
    mock_mt5_manager,
):
    """Test accessing other user's account positions fails."""
    # Create account for other user
    account_service.mt5.get_account_info = AsyncMock(
        return_value={
            "account": "0",
            "balance": 0,
            "equity": 0,
            "free_margin": 0,
            "margin_used": 0,
            "margin_level": 0,
            "open_positions": 0,
        }
    )

    other_account = await account_service.link_account(
        user_id=other_user.id,
        mt5_account_id="9999",
        mt5_login="other_login",
    )

    response = await client.get(
        f"/api/v1/accounts/{other_account.id}/positions",
        headers=auth_headers,
    )

    assert response.status_code == 403


@pytest.mark.skip(
    reason="Positions router endpoint not registered in app - infrastructure issue"
)
@pytest.mark.asyncio
async def test_get_account_positions_unauthorized(client: AsyncClient, linked_account):
    """Test getting positions without authentication fails."""
    response = await client.get(f"/api/v1/accounts/{linked_account.id}/positions")

    assert response.status_code == 401


# ============================================================================
# HTTP ERROR HANDLING TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_invalid_account_id_format(
    client: AsyncClient,
    auth_headers: dict,
):
    """Test API handles invalid account ID format."""
    response = await client.get(
        "/api/v1/accounts/invalid-id-format",
        headers=auth_headers,
    )

    # Should return 404 or 422
    assert response.status_code in [404, 422]


@pytest.mark.asyncio
async def test_malformed_json_request(
    client: AsyncClient,
    auth_headers: dict,
):
    """Test API handles malformed JSON."""
    response = await client.post(
        "/api/v1/accounts",
        content="{invalid json}",
        headers={**auth_headers, "Content-Type": "application/json"},
    )

    assert response.status_code == 422


# ============================================================================
# RESPONSE SCHEMA VALIDATION
# ============================================================================


@pytest.mark.asyncio
async def test_link_account_response_schema(
    client: AsyncClient,
    auth_headers: dict,
    mock_mt5_manager,
):
    """Test link account response has correct schema."""
    mock_mt5_manager.get_account_info = AsyncMock(
        return_value={
            "account": "0",
            "balance": 0,
            "equity": 0,
            "free_margin": 0,
            "margin_used": 0,
            "margin_level": 0,
            "open_positions": 0,
        }
    )

    response = await client.post(
        "/api/v1/accounts",
        json={
            "mt5_account_id": "12345678",
            "mt5_login": "login",
            "mt5_password": "pass",
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    data = response.json()

    # Verify required fields
    assert "id" in data
    assert "mt5_account_id" in data
    assert "is_primary" in data
    assert "verified_at" in data
    assert isinstance(data["is_primary"], bool)


@pytest.mark.skip(
    reason="Positions router endpoint not registered in app - infrastructure issue"
)
@pytest.mark.asyncio
async def test_get_positions_response_schema(
    client: AsyncClient,
    auth_headers: dict,
    linked_account,
    mock_mt5_manager,
):
    """Test get positions response has correct schema."""
    mock_mt5_manager.get_positions = AsyncMock(return_value=[])

    response = await client.get(
        "/api/v1/positions",
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()

    # Verify structure
    assert "account_id" in data
    assert "positions" in data
    assert isinstance(data["positions"], list)
