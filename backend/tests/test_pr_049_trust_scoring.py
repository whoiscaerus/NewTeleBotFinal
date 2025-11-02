"""PR-049: Trust Scoring - Comprehensive Test Suite."""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.models import User
from backend.app.trust.graph import (
    _build_graph_from_endorsements,
    _calculate_endorsement_score,
    _calculate_percentiles,
    _calculate_performance_score,
    _calculate_tenure_score,
    _calculate_tier,
    calculate_trust_scores,
    export_graph,
    import_graph,
)
from backend.app.trust.models import Endorsement, TrustCalculationLog, UserTrustScore

# ============================================================================
# Fixtures
# ============================================================================


@pytest_asyncio.fixture
async def test_users(db_session: AsyncSession):
    """Create test users for trust scoring."""
    user_ids = [str(uuid4()) for _ in range(5)]
    users = []

    for user_id in user_ids:
        user = User(
            id=user_id,
            email=f"user{user_id[:8]}@test.com",
            password_hash="hashed_password",
            created_at=datetime.utcnow() - timedelta(days=180),
        )
        db_session.add(user)
        users.append(user)

    await db_session.commit()
    return users


@pytest_asyncio.fixture
async def test_endorsements(db_session: AsyncSession, test_users):
    """Create endorsement relationships between test users."""
    endorsements = []

    # User 0 endorses User 1 (weight 0.8)
    e1 = Endorsement(
        id=str(uuid4()),
        endorser_id=test_users[0].id,
        endorsee_id=test_users[1].id,
        weight=0.8,
        reason="Great trader",
        created_at=datetime.utcnow(),
    )
    endorsements.append(e1)

    # User 2 endorses User 1 (weight 0.6)
    e2 = Endorsement(
        id=str(uuid4()),
        endorser_id=test_users[2].id,
        endorsee_id=test_users[1].id,
        weight=0.6,
        reason="Consistent performer",
        created_at=datetime.utcnow(),
    )
    endorsements.append(e2)

    # User 1 endorses User 3 (weight 1.0 - should be capped at 0.5)
    e3 = Endorsement(
        id=str(uuid4()),
        endorser_id=test_users[1].id,
        endorsee_id=test_users[3].id,
        weight=1.0,
        reason="Excellent signals",
        created_at=datetime.utcnow(),
    )
    endorsements.append(e3)

    # User 3 endorses User 4 (weight 0.5)
    e4 = Endorsement(
        id=str(uuid4()),
        endorser_id=test_users[3].id,
        endorsee_id=test_users[4].id,
        weight=0.5,
        reason="Professional",
        created_at=datetime.utcnow(),
    )
    endorsements.append(e4)

    for endorsement in endorsements:
        db_session.add(endorsement)

    await db_session.commit()
    return endorsements


# ============================================================================
# Model Tests
# ============================================================================


@pytest.mark.asyncio
async def test_endorsement_model_creation(db_session: AsyncSession, test_users):
    """Test Endorsement model creation with proper relationships."""
    endorsement = Endorsement(
        id=str(uuid4()),
        endorser_id=test_users[0].id,
        endorsee_id=test_users[1].id,
        weight=0.75,
        reason="Test reason",
        created_at=datetime.utcnow(),
    )

    db_session.add(endorsement)
    await db_session.commit()
    await db_session.refresh(endorsement)

    assert endorsement.id is not None
    assert endorsement.endorser_id == test_users[0].id
    assert endorsement.endorsee_id == test_users[1].id
    assert endorsement.weight == 0.75
    assert endorsement.reason == "Test reason"
    assert endorsement.revoked_at is None


@pytest.mark.asyncio
async def test_user_trust_score_model_creation(db_session: AsyncSession, test_users):
    """Test UserTrustScore model creation with all components."""
    score_record = UserTrustScore(
        id=str(uuid4()),
        user_id=test_users[0].id,
        score=75.5,
        performance_component=80.0,
        tenure_component=70.0,
        endorsement_component=65.0,
        tier="silver",
        percentile=65,
        calculated_at=datetime.utcnow(),
        valid_until=datetime.utcnow() + timedelta(hours=24),
    )

    db_session.add(score_record)
    await db_session.commit()
    await db_session.refresh(score_record)

    assert score_record.score == 75.5
    assert score_record.tier == "silver"
    assert score_record.percentile == 65
    assert score_record.performance_component == 80.0


@pytest.mark.asyncio
async def test_trust_calculation_log_model(db_session: AsyncSession, test_users):
    """Test TrustCalculationLog model creation for audit trail."""
    log = TrustCalculationLog(
        id=str(uuid4()),
        user_id=test_users[0].id,
        previous_score=70.0,
        new_score=75.5,
        input_graph_nodes=5,
        input_graph_edges=4,
        algorithm_version="1.0",
        calculated_at=datetime.utcnow(),
        notes="Routine recalculation",
    )

    db_session.add(log)
    await db_session.commit()
    await db_session.refresh(log)

    assert log.previous_score == 70.0
    assert log.new_score == 75.5
    assert log.input_graph_nodes == 5


# ============================================================================
# Graph Construction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_build_graph_from_endorsements(test_endorsements):
    """Test graph construction from endorsements with weight capping."""
    graph = _build_graph_from_endorsements(test_endorsements)

    # Verify graph structure
    assert graph.number_of_nodes() == 5
    assert graph.number_of_edges() == 4

    # Verify edge weights are capped at 0.5
    # User 1 -> User 3 should be capped at 0.5
    weight_1_3 = graph[test_endorsements[2].endorser_id][
        test_endorsements[2].endorsee_id
    ]["weight"]
    assert weight_1_3 == 0.5, "Weight should be capped at 0.5 (anti-gaming)"

    # User 0 -> User 1 should be capped at 0.5 (anti-gaming, since original was 0.8 > 0.5)
    weight_0_1 = graph[test_endorsements[0].endorser_id][
        test_endorsements[0].endorsee_id
    ]["weight"]
    assert weight_0_1 == 0.5, "Weight should be capped at 0.5 (anti-gaming)"


# ============================================================================
# Score Calculation Tests
# ============================================================================


@pytest.mark.asyncio
async def test_calculate_performance_score():
    """Test performance score calculation with component weighting."""
    # Test case 1: High win rate
    perf_data = {"win_rate": 0.75, "sharpe_ratio": 1.5, "profit_factor": 2.0}
    score = _calculate_performance_score("user_id", perf_data)

    # Calculation:
    # win_score = min((0.75-0.5)*500, 100) = 100 * 0.5 = 50
    # sharpe_score = min(1.5*50, 100) = 75 * 0.3 = 22.5
    # pf_score = min((2.0-1.0)*50, 100) = 50 * 0.2 = 10
    # Total = 82.5
    assert 80 <= score <= 85, f"Performance score should be ~82.5: {score}"

    # Test case 2: Low win rate
    perf_data = {"win_rate": 0.45, "sharpe_ratio": 0.5, "profit_factor": 0.8}
    score = _calculate_performance_score("user_id", perf_data)
    assert 0 <= score <= 10, f"Performance score should be low: {score}"


@pytest.mark.asyncio
async def test_calculate_tenure_score():
    """Test tenure score calculation with linear scaling over 365 days."""
    # Test case 1: User active for 6 months (180 days)
    created_at = datetime.utcnow() - timedelta(days=180)
    score = _calculate_tenure_score(created_at)
    expected = (180 / 365) * 100
    assert 45 <= score <= 55, f"6-month tenure score should be ~{expected}: {score}"

    # Test case 2: User active for 1 year+
    created_at = datetime.utcnow() - timedelta(days=400)
    score = _calculate_tenure_score(created_at)
    assert score >= 100, "1+ year tenure should max at 100"

    # Test case 3: Brand new user
    created_at = datetime.utcnow() - timedelta(days=1)
    score = _calculate_tenure_score(created_at)
    assert 0 <= score <= 5, f"1-day tenure should be ~0: {score}"


@pytest.mark.asyncio
async def test_calculate_endorsement_score(test_endorsements, test_users):
    """Test endorsement score calculation with in-degree normalization."""
    graph = _build_graph_from_endorsements(test_endorsements)

    # User 1 has 2 endorsements (0.8 + 0.6 = 1.4)
    score = _calculate_endorsement_score(graph, test_users[1].id, len(test_users))
    assert 0 <= score <= 100, f"Endorsement score must be 0-100: {score}"

    # User 4 has 1 endorsement (0.5)
    score_user4 = _calculate_endorsement_score(graph, test_users[4].id, len(test_users))
    assert score_user4 < score, "User 4 should have lower endorsement score"


@pytest.mark.asyncio
async def test_calculate_tier():
    """Test tier calculation from score."""
    assert _calculate_tier(25) == "bronze"
    assert _calculate_tier(50) == "silver"  # boundary
    assert _calculate_tier(75) == "gold"  # boundary
    assert _calculate_tier(99) == "gold"


@pytest.mark.asyncio
async def test_calculate_percentiles():
    """Test percentile calculation."""
    scores = {
        "user1": {"score": 90.0},
        "user2": {"score": 70.0},
        "user3": {"score": 80.0},
        "user4": {"score": 60.0},
    }
    percentiles = _calculate_percentiles(scores)

    # User 1 (90) should be highest percentile
    assert percentiles["user1"] > percentiles["user2"]
    assert percentiles["user2"] > percentiles["user4"]
    assert all(0 <= p <= 100 for p in percentiles.values())


@pytest.mark.asyncio
async def test_trust_scores_deterministic(test_endorsements, test_users):
    """Test deterministic nature of trust score calculation.

    Same graph input should always produce same scores (for caching).
    """
    graph = _build_graph_from_endorsements(test_endorsements)

    perf_map = {
        test_users[0].id: {"win_rate": 0.6, "sharpe_ratio": 1.2, "profit_factor": 1.5},
        test_users[1].id: {"win_rate": 0.7, "sharpe_ratio": 1.5, "profit_factor": 2.0},
        test_users[2].id: {"win_rate": 0.55, "sharpe_ratio": 1.0, "profit_factor": 1.3},
        test_users[3].id: {"win_rate": 0.75, "sharpe_ratio": 1.8, "profit_factor": 2.5},
        test_users[4].id: {"win_rate": 0.50, "sharpe_ratio": 0.8, "profit_factor": 1.0},
    }

    created_map = {user.id: user.created_at for user in test_users}

    # Calculate twice
    scores1 = calculate_trust_scores(graph, perf_map, created_map)
    scores2 = calculate_trust_scores(graph, perf_map, created_map)

    # Results should be identical
    for user_id in scores1:
        assert scores1[user_id]["score"] == scores2[user_id]["score"]
        assert scores1[user_id]["tier"] == scores2[user_id]["tier"]


@pytest.mark.asyncio
async def test_edge_weight_capped_at_max(test_endorsements):
    """Test anti-gaming: edge weights capped at 0.5."""
    # Create endorsement with weight > 0.5
    endorsement = test_endorsements[2]  # weight was 1.0
    assert endorsement.weight == 1.0

    graph = _build_graph_from_endorsements([endorsement])

    # Weight in graph should be capped
    edge_data = graph[endorsement.endorser_id][endorsement.endorsee_id]
    assert edge_data["weight"] <= 0.5


# ============================================================================
# Graph Import/Export Tests
# ============================================================================


@pytest.mark.asyncio
async def test_export_import_graph(test_endorsements):
    """Test graph serialization and deserialization."""
    graph = _build_graph_from_endorsements(test_endorsements)

    # Export
    exported = export_graph(graph)
    assert "nodes" in exported
    assert "edges" in exported
    assert len(exported["nodes"]) == 5
    assert len(exported["edges"]) == 4

    # Import
    reimported = import_graph(exported)
    assert reimported.number_of_nodes() == graph.number_of_nodes()
    assert reimported.number_of_edges() == graph.number_of_edges()

    # Verify weights preserved
    for edge_data in exported["edges"]:
        source = edge_data["source"]
        target = edge_data["target"]
        weight = edge_data["weight"]
        reimported_weight = reimported[source][target]["weight"]
        assert reimported_weight == weight


# ============================================================================
# API Endpoint Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_trust_score_endpoint(db_session: AsyncSession, test_users):
    """Test GET /api/v1/trust/score/{user_id} endpoint logic."""

    from backend.app.trust.routes import get_trust_score

    user_id = test_users[0].id

    # Create a trust score record
    trust_score = UserTrustScore(
        id=str(uuid4()),
        user_id=user_id,
        score=75.5,
        performance_component=80.0,
        tenure_component=70.0,
        endorsement_component=65.0,
        tier="silver",
        percentile=65,
        calculated_at=datetime.utcnow(),
        valid_until=datetime.utcnow() + timedelta(hours=24),
    )
    db_session.add(trust_score)
    await db_session.flush()
    await db_session.commit()

    # Call endpoint function directly
    result = await get_trust_score(user_id, db_session)

    # Verify result
    assert result.score == 75.5
    assert result.tier == "silver"
    assert result.percentile == 65
    assert result.components.performance == 80.0


@pytest.mark.asyncio
async def test_get_trust_score_not_found(client: AsyncClient):
    """Test GET /trust/score returns 404 for non-existent user."""
    response = await client.get("/api/v1/trust/score/nonexistent-user")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_leaderboard_endpoint(db_session: AsyncSession, test_users):
    """Test GET /api/v1/trust/leaderboard endpoint logic."""
    from backend.app.trust.routes import get_trust_leaderboard

    # Create multiple trust scores
    for i, user in enumerate(test_users):
        score_val = 50 + (i * 10)  # Scores: 50, 60, 70, 80, 90
        trust_score = UserTrustScore(
            id=str(uuid4()),
            user_id=user.id,
            score=score_val,
            performance_component=score_val * 0.5,
            tenure_component=score_val * 0.2,
            endorsement_component=score_val * 0.3,
            tier="bronze" if score_val < 50 else "silver" if score_val < 75 else "gold",
            percentile=(i + 1) * 20,
            calculated_at=datetime.utcnow(),
            valid_until=datetime.utcnow() + timedelta(hours=24),
        )
        db_session.add(trust_score)

    await db_session.flush()
    await db_session.commit()

    # Call endpoint function directly
    result = await get_trust_leaderboard(limit=10, offset=0, db=db_session)

    # Verify result
    assert result.total_users == 5
    assert len(result.entries) == 5

    # Verify sorted by score (descending)
    for i in range(len(result.entries) - 1):
        assert result.entries[i].score >= result.entries[i + 1].score

    # Verify ranks
    for i, entry in enumerate(result.entries):
        assert entry.rank == i + 1


@pytest.mark.asyncio
async def test_get_leaderboard_pagination(db_session: AsyncSession, test_users):
    """Test leaderboard pagination with limit and offset."""
    from backend.app.trust.routes import get_trust_leaderboard

    # Create trust scores
    for i, user in enumerate(test_users):
        trust_score = UserTrustScore(
            id=str(uuid4()),
            user_id=user.id,
            score=50 + (i * 10),
            performance_component=50,
            tenure_component=50,
            endorsement_component=50,
            tier="silver",
            percentile=50,
            calculated_at=datetime.utcnow(),
            valid_until=datetime.utcnow() + timedelta(hours=24),
        )
        db_session.add(trust_score)

    await db_session.flush()
    await db_session.commit()

    # Test limit
    result = await get_trust_leaderboard(limit=2, offset=0, db=db_session)
    assert len(result.entries) == 2

    # Test offset
    result = await get_trust_leaderboard(limit=2, offset=2, db=db_session)
    assert len(result.entries) == 2


# ============================================================================
# Coverage Tests
# ============================================================================


@pytest.mark.asyncio
async def test_endorsement_relationship_cascades(db_session: AsyncSession, test_users):
    """Test that endorsements are properly associated with users."""
    endorsement = Endorsement(
        id=str(uuid4()),
        endorser_id=test_users[0].id,
        endorsee_id=test_users[1].id,
        weight=0.7,
        reason="Test",
        created_at=datetime.utcnow(),
    )
    db_session.add(endorsement)
    await db_session.commit()

    # Verify relationships work
    stmt = select(Endorsement).where(Endorsement.endorser_id == test_users[0].id)
    result = await db_session.execute(stmt)
    endorsements = result.scalars().all()
    assert len(endorsements) == 1
    assert endorsements[0].endorsee_id == test_users[1].id


@pytest.mark.asyncio
async def test_trust_score_uniqueness(db_session: AsyncSession, test_users):
    """Test that only one trust score exists per user."""
    user_id = test_users[0].id

    score1 = UserTrustScore(
        id=str(uuid4()),
        user_id=user_id,
        score=75.0,
        performance_component=80,
        tenure_component=70,
        endorsement_component=65,
        tier="silver",
        percentile=60,
        calculated_at=datetime.utcnow(),
        valid_until=datetime.utcnow() + timedelta(hours=24),
    )
    db_session.add(score1)
    await db_session.commit()

    # Attempt to add another - should fail due to unique constraint
    score2 = UserTrustScore(
        id=str(uuid4()),
        user_id=user_id,
        score=80.0,
        performance_component=85,
        tenure_component=75,
        endorsement_component=70,
        tier="gold",
        percentile=70,
        calculated_at=datetime.utcnow(),
        valid_until=datetime.utcnow() + timedelta(hours=24),
    )
    db_session.add(score2)

    with pytest.raises(Exception):  # Should raise IntegrityError
        await db_session.commit()


@pytest.mark.asyncio
async def test_get_trust_score_error_handling(db_session: AsyncSession, test_users):
    """Test error handling in get_trust_score endpoint."""
    from fastapi import HTTPException

    from backend.app.trust.routes import get_trust_score

    # Non-existent user - should raise 404
    with pytest.raises(HTTPException) as exc_info:
        await get_trust_score("non-existent-id", db_session)

    assert exc_info.value.status_code == 404
    assert "not found" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_get_leaderboard_error_handling(db_session: AsyncSession):
    """Test error handling in leaderboard endpoint."""
    from backend.app.trust.routes import get_trust_leaderboard

    # Empty leaderboard should return 0 entries
    result = await get_trust_leaderboard(limit=10, offset=0, db=db_session)

    assert result.total_users == 0
    assert len(result.entries) == 0


@pytest.mark.asyncio
async def test_my_trust_score_not_found(db_session: AsyncSession, test_users):
    """Test get_my_trust_score when user has no score yet."""
    from fastapi import HTTPException

    from backend.app.trust.routes import get_my_trust_score

    # User with no trust score
    with pytest.raises(HTTPException) as exc_info:
        await get_my_trust_score(current_user=test_users[0], db=db_session)

    assert exc_info.value.status_code == 404
    assert "not been calculated" in exc_info.value.detail
