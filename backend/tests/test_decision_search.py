"""Tests for decision search API (PR-080).

Validates:
- Decision search with all filter combinations
- Pagination (page, page_size, total_pages)
- Result ordering (most recent first)
- Empty results handling
- Individual decision retrieval
- Composite filters (multiple criteria)

Uses REAL database and REAL business logic (NO MOCKS).
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient

from backend.app.strategy.logs.models import DecisionLog, DecisionOutcome


@pytest.mark.asyncio
async def test_search_decisions_no_filters(client: AsyncClient, db_session):
    """Test search returns all decisions when no filters applied."""
    # Create 5 decisions
    base_time = datetime.now(UTC)
    for i in range(5):
        decision = DecisionLog(
            id=str(uuid4()),
            timestamp=base_time - timedelta(minutes=i),
            strategy="fib_rsi",
            symbol="GOLD",
            outcome=DecisionOutcome.ENTERED,
            features={"rsi_14": 65.0 + i},
        )
        db_session.add(decision)

    await db_session.commit()

    # Search without filters
    response = await client.get("/api/v1/decisions/search")

    assert response.status_code == 200
    data = response.json()

    assert data["total"] == 5
    assert len(data["results"]) == 5
    assert data["page"] == 1
    assert data["total_pages"] == 1

    # Verify ordering (most recent first)
    timestamps = [r["timestamp"] for r in data["results"]]
    assert timestamps == sorted(
        timestamps, reverse=True
    ), "Results should be ordered by timestamp DESC"


@pytest.mark.asyncio
async def test_search_decisions_filter_by_strategy(client: AsyncClient, db_session):
    """Test filtering by strategy name."""
    # Create decisions with different strategies
    base_time = datetime.now(UTC)

    for strategy in ["fib_rsi", "ppo_gold", "fib_rsi"]:
        decision = DecisionLog(
            id=str(uuid4()),
            timestamp=base_time,
            strategy=strategy,
            symbol="GOLD",
            outcome=DecisionOutcome.ENTERED,
            features={},
        )
        db_session.add(decision)

    await db_session.commit()

    # Filter for fib_rsi only
    response = await client.get("/api/v1/decisions/search?strategy=fib_rsi")

    assert response.status_code == 200
    data = response.json()

    assert data["total"] == 2  # Only 2 fib_rsi decisions
    assert all(r["strategy"] == "fib_rsi" for r in data["results"])


@pytest.mark.asyncio
async def test_search_decisions_filter_by_symbol(client: AsyncClient, db_session):
    """Test filtering by trading symbol."""
    # Create decisions with different symbols
    base_time = datetime.now(UTC)

    for symbol in ["GOLD", "SILVER", "GOLD"]:
        decision = DecisionLog(
            id=str(uuid4()),
            timestamp=base_time,
            strategy="fib_rsi",
            symbol=symbol,
            outcome=DecisionOutcome.ENTERED,
            features={},
        )
        db_session.add(decision)

    await db_session.commit()

    # Filter for GOLD only
    response = await client.get("/api/v1/decisions/search?symbol=GOLD")

    assert response.status_code == 200
    data = response.json()

    assert data["total"] == 2  # Only 2 GOLD decisions
    assert all(r["symbol"] == "GOLD" for r in data["results"])


@pytest.mark.asyncio
async def test_search_decisions_filter_by_outcome(client: AsyncClient, db_session):
    """Test filtering by decision outcome."""
    # Create decisions with different outcomes
    base_time = datetime.now(UTC)

    for outcome in [
        DecisionOutcome.ENTERED,
        DecisionOutcome.SKIPPED,
        DecisionOutcome.ENTERED,
    ]:
        decision = DecisionLog(
            id=str(uuid4()),
            timestamp=base_time,
            strategy="fib_rsi",
            symbol="GOLD",
            outcome=outcome,
            features={},
        )
        db_session.add(decision)

    await db_session.commit()

    # Filter for ENTERED only
    response = await client.get("/api/v1/decisions/search?outcome=entered")

    assert response.status_code == 200
    data = response.json()

    assert data["total"] == 2  # Only 2 ENTERED decisions
    assert all(r["outcome"] == "entered" for r in data["results"])


@pytest.mark.asyncio
async def test_search_decisions_filter_by_date_range(client: AsyncClient, db_session):
    """Test filtering by start_date and end_date."""
    base_time = datetime.now(UTC)

    # Create decisions over 10 days
    for i in range(10):
        decision = DecisionLog(
            id=str(uuid4()),
            timestamp=base_time - timedelta(days=i),
            strategy="fib_rsi",
            symbol="GOLD",
            outcome=DecisionOutcome.ENTERED,
            features={},
        )
        db_session.add(decision)

    await db_session.commit()

    # Filter for last 5 days
    start_date = (base_time - timedelta(days=5)).isoformat()
    end_date = base_time.isoformat()

    response = await client.get(
        "/api/v1/decisions/search",
        params={"start_date": start_date, "end_date": end_date},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["total"] == 6  # Days 0-5 inclusive
    # Verify all timestamps in range
    for result in data["results"]:
        ts = datetime.fromisoformat(result["timestamp"].replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)

        start_ts = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
        if start_ts.tzinfo is None:
            start_ts = start_ts.replace(tzinfo=UTC)

        end_ts = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
        if end_ts.tzinfo is None:
            end_ts = end_ts.replace(tzinfo=UTC)

        assert ts >= start_ts
        assert ts <= end_ts


@pytest.mark.asyncio
async def test_search_decisions_composite_filters(client: AsyncClient, db_session):
    """Test multiple filters combined."""
    base_time = datetime.now(UTC)

    # Create diverse decisions
    decisions_data = [
        ("fib_rsi", "GOLD", DecisionOutcome.ENTERED),
        ("fib_rsi", "GOLD", DecisionOutcome.SKIPPED),
        ("fib_rsi", "SILVER", DecisionOutcome.ENTERED),
        ("ppo_gold", "GOLD", DecisionOutcome.ENTERED),
    ]

    for strategy, symbol, outcome in decisions_data:
        decision = DecisionLog(
            id=str(uuid4()),
            timestamp=base_time,
            strategy=strategy,
            symbol=symbol,
            outcome=outcome,
            features={},
        )
        db_session.add(decision)

    await db_session.commit()

    # Filter: fib_rsi + GOLD + ENTERED
    response = await client.get(
        "/api/v1/decisions/search?strategy=fib_rsi&symbol=GOLD&outcome=entered"
    )

    assert response.status_code == 200
    data = response.json()

    assert data["total"] == 1  # Only 1 matching decision
    result = data["results"][0]
    assert result["strategy"] == "fib_rsi"
    assert result["symbol"] == "GOLD"
    assert result["outcome"] == "entered"


@pytest.mark.asyncio
async def test_search_decisions_pagination(client: AsyncClient, db_session):
    """Test pagination (page, page_size, total_pages)."""
    # Create 25 decisions
    base_time = datetime.now(UTC)
    for i in range(25):
        decision = DecisionLog(
            id=str(uuid4()),
            timestamp=base_time - timedelta(minutes=i),
            strategy="fib_rsi",
            symbol="GOLD",
            outcome=DecisionOutcome.ENTERED,
            features={},
        )
        db_session.add(decision)

    await db_session.commit()

    # Page 1, 10 results per page
    response = await client.get("/api/v1/decisions/search?page=1&page_size=10")
    assert response.status_code == 200
    data = response.json()

    assert data["total"] == 25
    assert data["page"] == 1
    assert data["page_size"] == 10
    assert data["total_pages"] == 3  # Ceiling(25/10) = 3
    assert len(data["results"]) == 10  # First page has 10 results

    # Page 2
    response = await client.get("/api/v1/decisions/search?page=2&page_size=10")
    data = response.json()
    assert data["page"] == 2
    assert len(data["results"]) == 10

    # Page 3 (partial)
    response = await client.get("/api/v1/decisions/search?page=3&page_size=10")
    data = response.json()
    assert data["page"] == 3
    assert len(data["results"]) == 5  # Remaining 5 results


@pytest.mark.asyncio
async def test_search_decisions_empty_results(client: AsyncClient, db_session):
    """Test search with no matching results."""
    response = await client.get("/api/v1/decisions/search?strategy=nonexistent")

    assert response.status_code == 200
    data = response.json()

    assert data["total"] == 0
    assert len(data["results"]) == 0
    assert data["total_pages"] == 0


@pytest.mark.asyncio
async def test_search_decisions_result_ordering(client: AsyncClient, db_session):
    """Test results are ordered by timestamp DESC (most recent first)."""
    base_time = datetime.now(UTC)

    # Create decisions with explicit timestamps
    decision_ids = []
    for i in range(5):
        decision_id = str(uuid4())
        decision_ids.append(decision_id)
        decision = DecisionLog(
            id=decision_id,
            timestamp=base_time - timedelta(hours=i),  # i hours ago
            strategy="fib_rsi",
            symbol="GOLD",
            outcome=DecisionOutcome.ENTERED,
            features={},
        )
        db_session.add(decision)

    await db_session.commit()

    # Search
    response = await client.get("/api/v1/decisions/search")
    data = response.json()

    # Verify ordering: most recent first (i=0 should be first)
    result_ids = [r["id"] for r in data["results"]]
    assert result_ids[0] == decision_ids[0], "Most recent decision should be first"
    assert result_ids[-1] == decision_ids[-1], "Oldest decision should be last"


@pytest.mark.asyncio
async def test_search_decisions_page_size_limits(client: AsyncClient, db_session):
    """Test page_size validation (1-500)."""
    # Create 10 decisions
    for _ in range(10):
        decision = DecisionLog(
            id=str(uuid4()),
            timestamp=datetime.now(UTC),
            strategy="fib_rsi",
            symbol="GOLD",
            outcome=DecisionOutcome.ENTERED,
            features={},
        )
        db_session.add(decision)

    await db_session.commit()

    # Valid page_size
    response = await client.get("/api/v1/decisions/search?page_size=5")
    assert response.status_code == 200
    data = response.json()
    assert data["page_size"] == 5

    # Invalid page_size (>500) should be rejected by Pydantic validation
    response = await client.get("/api/v1/decisions/search?page_size=1000")
    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_get_decision_by_id_success(client: AsyncClient, db_session):
    """Test retrieving a single decision by ID."""
    decision_id = str(uuid4())
    decision = DecisionLog(
        id=decision_id,
        timestamp=datetime.now(UTC),
        strategy="fib_rsi",
        symbol="GOLD",
        outcome=DecisionOutcome.ENTERED,
        features={"rsi_14": 65.0, "macd": {"histogram": 0.05}},
        note="Strong buy signal",
    )
    db_session.add(decision)
    await db_session.commit()

    # Get by ID
    response = await client.get(f"/api/v1/decisions/{decision_id}")

    assert response.status_code == 200
    data = response.json()

    assert data["id"] == decision_id
    assert data["strategy"] == "fib_rsi"
    assert data["symbol"] == "GOLD"
    assert data["outcome"] == "entered"
    assert data["features"]["rsi_14"] == 65.0
    assert data["note"] == "Strong buy signal"


@pytest.mark.asyncio
async def test_get_decision_by_id_not_found(client: AsyncClient, db_session):
    """Test retrieving non-existent decision returns 404."""
    response = await client.get("/api/v1/decisions/nonexistent-id")

    assert response.status_code == 404
    data = response.json()
    assert "not found" in data["detail"].lower()


@pytest.mark.asyncio
async def test_search_decisions_response_schema(client: AsyncClient, db_session):
    """Test search response matches expected schema."""
    # Create 1 decision
    decision_id = str(uuid4())
    decision = DecisionLog(
        id=decision_id,
        timestamp=datetime.now(UTC),
        strategy="fib_rsi",
        symbol="GOLD",
        outcome=DecisionOutcome.ENTERED,
        features={"rsi_14": 65.0},
        note="Test decision",
    )
    db_session.add(decision)
    await db_session.commit()

    response = await client.get("/api/v1/decisions/search")
    assert response.status_code == 200
    data = response.json()

    # Validate top-level schema
    assert "total" in data
    assert "page" in data
    assert "page_size" in data
    assert "total_pages" in data
    assert "results" in data

    # Validate result item schema
    result = data["results"][0]
    assert "id" in result
    assert "timestamp" in result
    assert "strategy" in result
    assert "symbol" in result
    assert "outcome" in result
    assert "features" in result
    assert "note" in result

    assert result["id"] == decision_id
    assert result["features"] == {"rsi_14": 65.0}
    assert result["note"] == "Test decision"


@pytest.mark.asyncio
async def test_search_decisions_increments_telemetry(
    client: AsyncClient, db_session, monkeypatch
):
    """Test search increments decision_search_total metric."""
    from backend.app.observability.metrics import metrics

    # Track metric calls
    inc_called = []

    def mock_inc():
        inc_called.append(True)

    monkeypatch.setattr(metrics.decision_search_total, "inc", mock_inc)

    # Perform search
    response = await client.get("/api/v1/decisions/search")
    assert response.status_code == 200

    # Verify metric incremented
    assert len(inc_called) == 1, "decision_search_total should be incremented once"
