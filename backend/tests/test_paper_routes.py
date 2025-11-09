"""
Tests for Paper Trading API Routes

Validates enable/disable toggle, isolation from live, order placement, and statement retrieval.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_enable_paper_trading(client: AsyncClient, test_user, db_session):
    """Test enabling paper trading creates account."""
    response = await client.post(
        "/api/v1/paper/enable", json={"initial_balance": 5000.00}
    )

    assert response.status_code == 201
    data = response.json()
    assert data["balance"] == 5000.00
    assert data["equity"] == 5000.00
    assert data["enabled"] is True
    assert data["user_id"] == test_user.id


@pytest.mark.asyncio
async def test_enable_paper_trading_already_enabled(
    client: AsyncClient, test_user, db_session
):
    """Test enabling paper trading when already enabled returns 400."""
    # Enable first time
    await client.post("/api/v1/paper/enable", json={"initial_balance": 10000.00})

    # Enable again
    response = await client.post(
        "/api/v1/paper/enable", json={"initial_balance": 5000.00}
    )

    assert response.status_code == 400
    assert "already enabled" in response.json()["detail"]


@pytest.mark.asyncio
async def test_enable_paper_trading_default_balance(
    client: AsyncClient, test_user, db_session
):
    """Test enabling paper trading with default balance."""
    response = await client.post("/api/v1/paper/enable", json={})

    assert response.status_code == 201
    data = response.json()
    assert data["balance"] == 10000.00  # Default


@pytest.mark.asyncio
async def test_disable_paper_trading(client: AsyncClient, test_user, db_session):
    """Test disabling paper trading preserves account."""
    # Enable first
    await client.post("/api/v1/paper/enable", json={"initial_balance": 10000.00})

    # Disable
    response = await client.post("/api/v1/paper/disable")

    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is False
    assert data["balance"] == 10000.00  # Preserved


@pytest.mark.asyncio
async def test_disable_paper_trading_not_found(
    client: AsyncClient, test_user, db_session
):
    """Test disabling paper trading when not enabled returns 404."""
    response = await client.post("/api/v1/paper/disable")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_get_paper_account(client: AsyncClient, test_user, db_session):
    """Test getting paper account details."""
    # Enable first
    await client.post("/api/v1/paper/enable", json={"initial_balance": 7500.00})

    # Get account
    response = await client.get("/api/v1/paper/account")

    assert response.status_code == 200
    data = response.json()
    assert data["balance"] == 7500.00
    assert data["equity"] == 7500.00
    assert data["enabled"] is True


@pytest.mark.asyncio
async def test_get_paper_account_not_found(client: AsyncClient, test_user, db_session):
    """Test getting paper account when not enabled returns 404."""
    response = await client.get("/api/v1/paper/account")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_place_paper_order(client: AsyncClient, test_user, db_session):
    """Test placing paper order."""
    # Enable paper trading
    await client.post("/api/v1/paper/enable", json={"initial_balance": 10000.00})

    # Place order
    response = await client.post(
        "/api/v1/paper/order",
        json={
            "symbol": "GOLD",
            "side": "buy",
            "volume": 1.0,
            "bid": 1950.00,
            "ask": 1950.50,
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["symbol"] == "GOLD"
    assert data["side"] == "buy"
    assert data["volume"] == 1.0
    assert data["entry_price"] == 1950.27  # Mid + slippage (2 pips)
    assert data["slippage"] == 0.02


@pytest.mark.asyncio
async def test_place_paper_order_insufficient_balance(
    client: AsyncClient, test_user, db_session
):
    """Test placing paper order with insufficient balance returns 400."""
    # Enable with low balance
    await client.post("/api/v1/paper/enable", json={"initial_balance": 100.00})

    # Place large order
    response = await client.post(
        "/api/v1/paper/order",
        json={
            "symbol": "GOLD",
            "side": "buy",
            "volume": 10.0,  # Requires ~19500
            "bid": 1950.00,
            "ask": 1950.50,
        },
    )

    assert response.status_code == 400
    assert "Insufficient balance" in response.json()["detail"]


@pytest.mark.asyncio
async def test_place_paper_order_disabled(client: AsyncClient, test_user, db_session):
    """Test placing paper order when disabled returns 403."""
    # Enable then disable
    await client.post("/api/v1/paper/enable", json={"initial_balance": 10000.00})
    await client.post("/api/v1/paper/disable")

    # Place order
    response = await client.post(
        "/api/v1/paper/order",
        json={
            "symbol": "GOLD",
            "side": "buy",
            "volume": 1.0,
            "bid": 1950.00,
            "ask": 1950.50,
        },
    )

    assert response.status_code == 403
    assert "disabled" in response.json()["detail"]


@pytest.mark.asyncio
async def test_get_paper_positions(client: AsyncClient, test_user, db_session):
    """Test getting open paper positions."""
    # Enable and place order
    await client.post("/api/v1/paper/enable", json={"initial_balance": 10000.00})
    await client.post(
        "/api/v1/paper/order",
        json={
            "symbol": "GOLD",
            "side": "buy",
            "volume": 1.0,
            "bid": 1950.00,
            "ask": 1950.50,
        },
    )

    # Get positions
    response = await client.get("/api/v1/paper/positions")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["symbol"] == "GOLD"
    assert data[0]["side"] == "buy"
    assert data[0]["volume"] == 1.0
    assert data[0]["unrealized_pnl"] == 0.0


@pytest.mark.asyncio
async def test_get_paper_positions_empty(client: AsyncClient, test_user, db_session):
    """Test getting positions when none exist returns empty list."""
    # Enable without placing orders
    await client.post("/api/v1/paper/enable", json={"initial_balance": 10000.00})

    response = await client.get("/api/v1/paper/positions")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_get_paper_positions_no_account(
    client: AsyncClient, test_user, db_session
):
    """Test getting positions without account returns empty list."""
    response = await client.get("/api/v1/paper/positions")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_get_paper_trades(client: AsyncClient, test_user, db_session):
    """Test getting paper trade history."""
    # Enable and place orders
    await client.post("/api/v1/paper/enable", json={"initial_balance": 10000.00})
    await client.post(
        "/api/v1/paper/order",
        json={
            "symbol": "GOLD",
            "side": "buy",
            "volume": 1.0,
            "bid": 1950.00,
            "ask": 1950.50,
        },
    )
    await client.post(
        "/api/v1/paper/order",
        json={
            "symbol": "SILVER",
            "side": "sell",
            "volume": 2.0,
            "bid": 25.00,
            "ask": 25.10,
        },
    )

    # Get trades
    response = await client.get("/api/v1/paper/trades")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    # Most recent first (SILVER)
    assert data[0]["symbol"] == "SILVER"
    assert data[1]["symbol"] == "GOLD"


@pytest.mark.asyncio
async def test_get_paper_trades_empty(client: AsyncClient, test_user, db_session):
    """Test getting trades when none exist returns empty list."""
    await client.post("/api/v1/paper/enable", json={"initial_balance": 10000.00})

    response = await client.get("/api/v1/paper/trades")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_paper_trading_isolation(client: AsyncClient, test_user, db_session):
    """Test paper trading is isolated from live trading."""
    # Enable paper trading
    await client.post("/api/v1/paper/enable", json={"initial_balance": 10000.00})

    # Place paper order
    await client.post(
        "/api/v1/paper/order",
        json={
            "symbol": "GOLD",
            "side": "buy",
            "volume": 1.0,
            "bid": 1950.00,
            "ask": 1950.50,
        },
    )

    # Get paper account
    response = await client.get("/api/v1/paper/account")
    paper_data = response.json()

    # Verify paper balance reduced
    assert paper_data["balance"] < 10000.00

    # Note: Live trading would be separate API endpoints (not implemented yet)
    # This test verifies paper trading maintains separate state


@pytest.mark.asyncio
async def test_re_enable_paper_trading_resets_balance(
    client: AsyncClient, test_user, db_session
):
    """Test re-enabling paper trading after disabling resets balance."""
    # Enable with 5000
    await client.post("/api/v1/paper/enable", json={"initial_balance": 5000.00})

    # Disable
    await client.post("/api/v1/paper/disable")

    # Re-enable with 7500
    response = await client.post(
        "/api/v1/paper/enable", json={"initial_balance": 7500.00}
    )

    assert response.status_code == 201
    data = response.json()
    assert data["balance"] == 7500.00  # Reset to new amount


@pytest.mark.asyncio
async def test_paper_order_validation(client: AsyncClient, test_user, db_session):
    """Test paper order input validation."""
    await client.post("/api/v1/paper/enable", json={"initial_balance": 10000.00})

    # Invalid symbol (too short)
    response = await client.post(
        "/api/v1/paper/order",
        json={
            "symbol": "G",
            "side": "buy",
            "volume": 1.0,
            "bid": 1950.00,
            "ask": 1950.50,
        },
    )
    assert response.status_code == 422

    # Invalid volume (negative)
    response = await client.post(
        "/api/v1/paper/order",
        json={
            "symbol": "GOLD",
            "side": "buy",
            "volume": -1.0,
            "bid": 1950.00,
            "ask": 1950.50,
        },
    )
    assert response.status_code == 422

    # Invalid volume (too large)
    response = await client.post(
        "/api/v1/paper/order",
        json={
            "symbol": "GOLD",
            "side": "buy",
            "volume": 999.0,
            "bid": 1950.00,
            "ask": 1950.50,
        },
    )
    assert response.status_code == 422

    # Invalid price (zero)
    response = await client.post(
        "/api/v1/paper/order",
        json={
            "symbol": "GOLD",
            "side": "buy",
            "volume": 1.0,
            "bid": 0.00,
            "ask": 1950.50,
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_paper_trading_telemetry(
    client: AsyncClient, test_user, db_session, monkeypatch
):
    """Test paper trading increments telemetry metrics."""
    from backend.app.observability.metrics import metrics

    # Track metric calls
    fills_calls = []
    pnl_calls = []

    def mock_fills_inc(symbol, side):
        fills_calls.append((symbol, side))

    def mock_pnl_set(value):
        pnl_calls.append(value)

    # Monkeypatch metrics
    monkeypatch.setattr(
        metrics.paper_fills_total,
        "labels",
        lambda symbol, side: type(
            "MockCounter", (), {"inc": lambda: mock_fills_inc(symbol, side)}
        )(),
    )
    monkeypatch.setattr(metrics.paper_pnl_total, "set", mock_pnl_set)

    # Enable and place order
    await client.post("/api/v1/paper/enable", json={"initial_balance": 10000.00})
    await client.post(
        "/api/v1/paper/order",
        json={
            "symbol": "GOLD",
            "side": "buy",
            "volume": 1.0,
            "bid": 1950.00,
            "ask": 1950.50,
        },
    )

    # Verify metrics incremented
    assert len(fills_calls) == 1
    assert fills_calls[0] == ("GOLD", "buy")
