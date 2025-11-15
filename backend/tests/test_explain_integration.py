"""Integration tests for explainability + decision search (PR-080).

Tests end-to-end flows:
- Create decision → compute attribution → verify contributions
- Search decisions → select decision → explain
- Feature importance across strategies
- API endpoint integration

Uses REAL database and REAL business logic (NO MOCKS).
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient

from backend.app.strategy.logs.models import DecisionLog, DecisionOutcome


@pytest.mark.asyncio
async def test_end_to_end_create_search_explain(client: AsyncClient, db_session):
    """Test complete flow: create decision → search → explain."""
    # Step 1: Create a decision with features
    decision_id = str(uuid4())
    decision = DecisionLog(
        id=decision_id,
        timestamp=datetime.now(UTC),
        strategy="fib_rsi",
        symbol="GOLD",
        outcome=DecisionOutcome.ENTERED,
        features={
            "price": {"close": 1950.00},
            "indicators": {
                "rsi_14": 25.0,  # Strong oversold
                "macd": {"histogram": 0.08},
                "fibonacci": {"level_618": 1960.00, "level_382": 1940.00},
            },
            "thresholds": {"rsi_oversold": 30, "rsi_overbought": 70},
        },
        note="Strong buy signal from RSI oversold",
    )
    db_session.add(decision)
    await db_session.commit()

    # Step 2: Search for decisions
    response = await client.get("/api/v1/decisions/search?strategy=fib_rsi&symbol=GOLD")
    assert response.status_code == 200
    search_data = response.json()

    assert search_data["total"] >= 1
    found_decision = next(d for d in search_data["results"] if d["id"] == decision_id)
    assert found_decision is not None

    # Step 3: Get attribution for found decision
    response = await client.get(
        f"/api/v1/explain/attribution?decision_id={decision_id}&strategy=fib_rsi"
    )
    assert response.status_code == 200
    attribution_data = response.json()

    # Verify attribution result
    assert attribution_data["decision_id"] == decision_id
    assert attribution_data["strategy"] == "fib_rsi"
    assert attribution_data["symbol"] == "GOLD"
    assert attribution_data["is_valid"] is True

    # Verify contributions
    contributions = attribution_data["contributions"]
    assert "rsi_14" in contributions
    assert contributions["rsi_14"] > 0, "RSI oversold should have positive contribution"

    # Verify sum
    contribution_sum = sum(contributions.values())
    delta = attribution_data["prediction_delta"]
    error = abs(contribution_sum - delta)
    assert error <= attribution_data["tolerance"]


@pytest.mark.asyncio
async def test_explain_multiple_strategies(client: AsyncClient, db_session):
    """Test attribution works for different strategy types."""
    base_time = datetime.now(UTC)

    # Create fib_rsi decision
    fib_decision_id = str(uuid4())
    fib_decision = DecisionLog(
        id=fib_decision_id,
        timestamp=base_time,
        strategy="fib_rsi",
        symbol="GOLD",
        outcome=DecisionOutcome.ENTERED,
        features={
            "indicators": {"rsi_14": 75.0},
            "thresholds": {"rsi_oversold": 30, "rsi_overbought": 70},
        },
    )

    # Create ppo_gold decision
    ppo_decision_id = str(uuid4())
    ppo_decision = DecisionLog(
        id=ppo_decision_id,
        timestamp=base_time,
        strategy="ppo_gold",
        symbol="GOLD",
        outcome=DecisionOutcome.ENTERED,
        features={
            "ppo": {
                "state": {"price_norm": 0.3, "rsi_norm": -0.2, "position_norm": 0.0},
                "action_prob": 0.82,
            },
        },
    )

    db_session.add(fib_decision)
    db_session.add(ppo_decision)
    await db_session.commit()

    # Get attribution for fib_rsi
    response = await client.get(
        f"/api/v1/explain/attribution?decision_id={fib_decision_id}&strategy=fib_rsi"
    )
    assert response.status_code == 200
    fib_data = response.json()
    assert fib_data["strategy"] == "fib_rsi"
    assert "rsi_14" in fib_data["contributions"]

    # Get attribution for ppo_gold
    response = await client.get(
        f"/api/v1/explain/attribution?decision_id={ppo_decision_id}&strategy=ppo_gold"
    )
    assert response.status_code == 200
    ppo_data = response.json()
    assert ppo_data["strategy"] == "ppo_gold"
    assert "price_normalized" in ppo_data["contributions"]


@pytest.mark.asyncio
async def test_feature_importance_across_decisions(client: AsyncClient, db_session):
    """Test feature importance aggregation over multiple decisions."""
    base_time = datetime.now(UTC)

    # Create 15 decisions with varying features
    for i in range(15):
        decision = DecisionLog(
            id=str(uuid4()),
            timestamp=base_time - timedelta(days=i),
            strategy="fib_rsi",
            symbol="GOLD",
            outcome=DecisionOutcome.ENTERED,
            features={
                "price": {"close": 1950.00 + i * 5},
                "indicators": {
                    "rsi_14": 30.0 + i * 3,
                    "macd": {"histogram": 0.01 * i},
                    "fibonacci": {"level_618": 1960.00, "level_382": 1940.00},
                },
                "thresholds": {"rsi_oversold": 30, "rsi_overbought": 70},
                "volume": {"ratio_avg": 1.0 + i * 0.05},
            },
        )
        db_session.add(decision)

    await db_session.commit()

    # Get feature importance
    response = await client.get(
        "/api/v1/explain/feature-importance?strategy=fib_rsi&lookback_days=30"
    )
    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert data["strategy"] == "fib_rsi"
    assert data["lookback_days"] == 30
    assert "importance" in data

    importance = data["importance"]
    assert len(importance) > 0, "Should have computed importance for some features"

    # Verify normalization (sum to 1.0)
    total = sum(importance.values())
    assert abs(total - 1.0) < 0.01, f"Importance should sum to 1.0, got {total}"

    # Verify common features present
    assert "rsi_14" in importance


@pytest.mark.asyncio
async def test_search_then_explain_workflow(client: AsyncClient, db_session):
    """Test typical user workflow: search → paginate → explain."""
    base_time = datetime.now(UTC)

    # Create 25 decisions
    decision_ids = []
    for i in range(25):
        decision_id = str(uuid4())
        decision_ids.append(decision_id)
        decision = DecisionLog(
            id=decision_id,
            timestamp=base_time - timedelta(hours=i),
            strategy="fib_rsi",
            symbol="GOLD",
            outcome=DecisionOutcome.ENTERED if i % 2 == 0 else DecisionOutcome.SKIPPED,
            features={
                "indicators": {"rsi_14": 30.0 + i * 2},
                "thresholds": {"rsi_oversold": 30, "rsi_overbought": 70},
            },
        )
        db_session.add(decision)

    await db_session.commit()

    # Step 1: Search page 1
    response = await client.get(
        "/api/v1/decisions/search?strategy=fib_rsi&page=1&page_size=10"
    )
    assert response.status_code == 200
    page1_data = response.json()
    assert len(page1_data["results"]) == 10

    # Step 2: Select first decision from page 1
    selected_decision = page1_data["results"][0]
    selected_id = selected_decision["id"]

    # Step 3: Explain selected decision
    response = await client.get(
        f"/api/v1/explain/attribution?decision_id={selected_id}&strategy=fib_rsi"
    )
    assert response.status_code == 200
    attribution_data = response.json()

    assert attribution_data["decision_id"] == selected_id
    assert attribution_data["is_valid"] is True

    # Step 4: Search page 2
    response = await client.get(
        "/api/v1/decisions/search?strategy=fib_rsi&page=2&page_size=10"
    )
    assert response.status_code == 200
    page2_data = response.json()
    assert len(page2_data["results"]) == 10

    # Step 5: Explain decision from page 2
    selected_id_page2 = page2_data["results"][0]["id"]
    response = await client.get(
        f"/api/v1/explain/attribution?decision_id={selected_id_page2}&strategy=fib_rsi"
    )
    assert response.status_code == 200
    attribution_data_page2 = response.json()
    assert attribution_data_page2["is_valid"] is True


@pytest.mark.asyncio
async def test_explain_telemetry_integration(
    client: AsyncClient, db_session, monkeypatch
):
    """Test explain endpoints increment telemetry correctly."""
    from backend.app.observability.metrics import metrics

    explain_calls = []
    search_calls = []

    def mock_explain_inc():
        explain_calls.append(True)

    def mock_search_inc():
        search_calls.append(True)

    monkeypatch.setattr(metrics.explain_requests_total, "inc", mock_explain_inc)
    monkeypatch.setattr(metrics.decision_search_total, "inc", mock_search_inc)

    # Create decision
    decision_id = str(uuid4())
    decision = DecisionLog(
        id=decision_id,
        timestamp=datetime.now(UTC),
        strategy="fib_rsi",
        symbol="GOLD",
        outcome=DecisionOutcome.ENTERED,
        features={
            "indicators": {"rsi_14": 65.0},
            "thresholds": {"rsi_oversold": 30, "rsi_overbought": 70},
        },
    )
    db_session.add(decision)
    await db_session.commit()

    # Call attribution endpoint
    response = await client.get(
        f"/api/v1/explain/attribution?decision_id={decision_id}&strategy=fib_rsi"
    )
    assert response.status_code == 200
    assert len(explain_calls) == 1

    # Call feature importance endpoint
    response = await client.get("/api/v1/explain/feature-importance?strategy=fib_rsi")
    assert response.status_code == 200
    assert len(explain_calls) == 2  # Both endpoints increment same metric

    # Call search endpoint
    response = await client.get("/api/v1/decisions/search")
    assert response.status_code == 200
    assert len(search_calls) == 1


@pytest.mark.asyncio
async def test_attribution_validation_tolerance(client: AsyncClient, db_session):
    """Test attribution with different tolerance values."""
    # Create decision
    decision_id = str(uuid4())
    decision = DecisionLog(
        id=decision_id,
        timestamp=datetime.now(UTC),
        strategy="fib_rsi",
        symbol="GOLD",
        outcome=DecisionOutcome.ENTERED,
        features={
            "indicators": {"rsi_14": 65.0},
            "thresholds": {"rsi_oversold": 30, "rsi_overbought": 70},
        },
    )
    db_session.add(decision)
    await db_session.commit()

    # Get attribution with stricter tolerance
    response = await client.get(
        f"/api/v1/explain/attribution?decision_id={decision_id}&strategy=fib_rsi&tolerance=0.001"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["tolerance"] == 0.001

    # Should still be valid (contributions are computed correctly)
    assert data["is_valid"] is True


@pytest.mark.asyncio
async def test_search_filter_with_explain(client: AsyncClient, db_session):
    """Test filtering decisions then explaining specific outcomes."""
    base_time = datetime.now(UTC)

    # Create mix of outcomes
    outcomes = [
        DecisionOutcome.ENTERED,
        DecisionOutcome.SKIPPED,
        DecisionOutcome.REJECTED,
    ]
    decision_ids_by_outcome = {outcome: [] for outcome in outcomes}

    for outcome in outcomes:
        for i in range(3):
            decision_id = str(uuid4())
            decision_ids_by_outcome[outcome].append(decision_id)
            decision = DecisionLog(
                id=decision_id,
                timestamp=base_time - timedelta(minutes=i),
                strategy="fib_rsi",
                symbol="GOLD",
                outcome=outcome,
                features={
                    "indicators": {"rsi_14": 30.0 + i * 10},
                    "thresholds": {"rsi_oversold": 30, "rsi_overbought": 70},
                },
            )
            db_session.add(decision)

    await db_session.commit()

    # Search for only ENTERED decisions
    response = await client.get("/api/v1/decisions/search?outcome=entered")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert all(d["outcome"] == "entered" for d in data["results"])

    # Explain first ENTERED decision
    entered_id = data["results"][0]["id"]
    response = await client.get(
        f"/api/v1/explain/attribution?decision_id={entered_id}&strategy=fib_rsi"
    )
    assert response.status_code == 200
    attribution = response.json()
    assert attribution["decision_id"] == entered_id

    # Search for REJECTED decisions
    response = await client.get("/api/v1/decisions/search?outcome=rejected")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3

    # Explain first REJECTED decision
    rejected_id = data["results"][0]["id"]
    response = await client.get(
        f"/api/v1/explain/attribution?decision_id={rejected_id}&strategy=fib_rsi"
    )
    assert response.status_code == 200
    attribution = response.json()
    assert attribution["decision_id"] == rejected_id


@pytest.mark.asyncio
async def test_explain_error_handling(client: AsyncClient, db_session):
    """Test error handling in explain endpoints."""
    # Attribution for non-existent decision
    response = await client.get(
        "/api/v1/explain/attribution?decision_id=nonexistent&strategy=fib_rsi"
    )
    assert response.status_code == 404

    # Create decision with fib_rsi strategy
    decision_id = str(uuid4())
    decision = DecisionLog(
        id=decision_id,
        timestamp=datetime.now(UTC),
        strategy="fib_rsi",
        symbol="GOLD",
        outcome=DecisionOutcome.ENTERED,
        features={"indicators": {"rsi_14": 65.0}},
    )
    db_session.add(decision)
    await db_session.commit()

    # Attribution with wrong strategy
    response = await client.get(
        f"/api/v1/explain/attribution?decision_id={decision_id}&strategy=ppo_gold"
    )
    assert response.status_code in [404, 422]  # Strategy mismatch

    # Feature importance for non-existent strategy
    response = await client.get(
        "/api/v1/explain/feature-importance?strategy=nonexistent_strategy&lookback_days=30"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["importance"] == {}  # No decisions found
