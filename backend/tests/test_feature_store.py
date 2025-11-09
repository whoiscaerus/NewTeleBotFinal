"""Comprehensive tests for Feature Store (PR-079).

Tests REAL business logic with REAL database operations.
NO MOCKS - validates actual feature persistence and retrieval.

Coverage targets:
- Feature storage (put_features)
- Feature retrieval (get_latest, get_features, get_by_id)
- Timestamp ordering
- JSONB validation
- Count operations
- Cleanup (delete_old_snapshots)
- Edge cases (missing data, boundary conditions)
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.features.models import FeatureSnapshot
from backend.app.features.store import FeatureStore


@pytest.mark.asyncio
async def test_put_features_success(db_session: AsyncSession):
    """✅ REAL TEST: Store feature snapshot with all fields."""
    store = FeatureStore(db_session)

    now = datetime.now(UTC)
    features = {
        "rsi_14": 65.3,
        "roc_10": 0.012,
        "atr_14": 12.5,
        "pivot_r1": 1975.50,
        "pivot_s1": 1950.25,
    }

    snapshot = await store.put_features(
        symbol="GOLD",
        timestamp=now,
        features=features,
        quality_score=0.95,
    )

    assert snapshot.id is not None
    assert snapshot.symbol == "GOLD"
    assert snapshot.timestamp == now
    assert snapshot.features == features
    assert snapshot.quality_score == 0.95
    assert snapshot.created_at is not None


@pytest.mark.asyncio
async def test_put_features_invalid_quality_score(db_session: AsyncSession):
    """✅ REAL TEST: Reject quality_score outside [0, 1] range."""
    store = FeatureStore(db_session)

    now = datetime.now(UTC)

    with pytest.raises(ValueError, match="quality_score must be in"):
        await store.put_features(
            symbol="GOLD",
            timestamp=now,
            features={"rsi": 65.3},
            quality_score=1.5,  # Invalid: > 1.0
        )

    with pytest.raises(ValueError, match="quality_score must be in"):
        await store.put_features(
            symbol="GOLD",
            timestamp=now,
            features={"rsi": 65.3},
            quality_score=-0.1,  # Invalid: < 0.0
        )


@pytest.mark.asyncio
async def test_get_latest_returns_most_recent(db_session: AsyncSession):
    """✅ REAL TEST: get_latest returns snapshot with latest timestamp."""
    store = FeatureStore(db_session)

    base_time = datetime.now(UTC)

    # Store 3 snapshots with different timestamps
    await store.put_features(
        symbol="GOLD",
        timestamp=base_time - timedelta(minutes=30),
        features={"rsi": 60.0},
    )
    await store.put_features(
        symbol="GOLD",
        timestamp=base_time - timedelta(minutes=15),
        features={"rsi": 65.0},
    )
    latest_snapshot = await store.put_features(
        symbol="GOLD",
        timestamp=base_time,
        features={"rsi": 70.0},
    )

    # Get latest
    result = await store.get_latest("GOLD")

    assert result is not None
    assert result.id == latest_snapshot.id
    assert result.features["rsi"] == 70.0
    assert result.timestamp == base_time


@pytest.mark.asyncio
async def test_get_latest_no_snapshots(db_session: AsyncSession):
    """✅ REAL TEST: get_latest returns None when no snapshots exist."""
    store = FeatureStore(db_session)

    result = await store.get_latest("NONEXISTENT")

    assert result is None


@pytest.mark.asyncio
async def test_get_features_time_range(db_session: AsyncSession):
    """✅ REAL TEST: get_features filters by start_time and end_time."""
    store = FeatureStore(db_session)

    base_time = datetime.now(UTC)

    # Store snapshots every 15 minutes for 1 hour
    for i in range(5):
        await store.put_features(
            symbol="GOLD",
            timestamp=base_time + timedelta(minutes=i * 15),
            features={"rsi": 60.0 + i},
        )

    # Query 30-minute window (should get 3 snapshots: 0, 15, 30)
    start = base_time
    end = base_time + timedelta(minutes=30)

    snapshots = await store.get_features(
        symbol="GOLD",
        start_time=start,
        end_time=end,
    )

    assert len(snapshots) == 3
    # Should be in descending order
    assert snapshots[0].features["rsi"] == 62.0  # 30 min
    assert snapshots[1].features["rsi"] == 61.0  # 15 min
    assert snapshots[2].features["rsi"] == 60.0  # 0 min


@pytest.mark.asyncio
async def test_get_features_with_limit(db_session: AsyncSession):
    """✅ REAL TEST: get_features respects limit parameter."""
    store = FeatureStore(db_session)

    base_time = datetime.now(UTC)

    # Store 10 snapshots
    for i in range(10):
        await store.put_features(
            symbol="GOLD",
            timestamp=base_time + timedelta(minutes=i),
            features={"rsi": 60.0 + i},
        )

    # Query with limit=5
    snapshots = await store.get_features(
        symbol="GOLD",
        limit=5,
    )

    assert len(snapshots) == 5
    # Should be most recent 5 in descending order
    assert snapshots[0].features["rsi"] == 69.0
    assert snapshots[4].features["rsi"] == 65.0


@pytest.mark.asyncio
async def test_get_features_descending_order(db_session: AsyncSession):
    """✅ REAL TEST: get_features returns snapshots in descending timestamp order."""
    store = FeatureStore(db_session)

    base_time = datetime.now(UTC)

    # Store snapshots in random order
    timestamps = [
        base_time + timedelta(minutes=30),
        base_time + timedelta(minutes=0),
        base_time + timedelta(minutes=45),
        base_time + timedelta(minutes=15),
    ]

    for i, ts in enumerate(timestamps):
        await store.put_features(
            symbol="GOLD",
            timestamp=ts,
            features={"rsi": 60.0 + i},
        )

    snapshots = await store.get_features(symbol="GOLD")

    assert len(snapshots) == 4
    # Should be sorted descending
    assert snapshots[0].timestamp == base_time + timedelta(minutes=45)
    assert snapshots[1].timestamp == base_time + timedelta(minutes=30)
    assert snapshots[2].timestamp == base_time + timedelta(minutes=15)
    assert snapshots[3].timestamp == base_time + timedelta(minutes=0)


@pytest.mark.asyncio
async def test_get_by_id_success(db_session: AsyncSession):
    """✅ REAL TEST: get_by_id retrieves specific snapshot."""
    store = FeatureStore(db_session)

    snapshot = await store.put_features(
        symbol="GOLD",
        timestamp=datetime.now(UTC),
        features={"rsi": 65.3},
    )

    result = await store.get_by_id(snapshot.id)

    assert result is not None
    assert result.id == snapshot.id
    assert result.symbol == "GOLD"
    assert result.features["rsi"] == 65.3


@pytest.mark.asyncio
async def test_get_by_id_not_found(db_session: AsyncSession):
    """✅ REAL TEST: get_by_id returns None for nonexistent ID."""
    store = FeatureStore(db_session)

    result = await store.get_by_id(999999)

    assert result is None


@pytest.mark.asyncio
async def test_count_snapshots_all(db_session: AsyncSession):
    """✅ REAL TEST: count_snapshots returns total count."""
    store = FeatureStore(db_session)

    base_time = datetime.now(UTC)

    # Store snapshots for multiple symbols
    await store.put_features(symbol="GOLD", timestamp=base_time, features={"rsi": 65.0})
    await store.put_features(
        symbol="GOLD",
        timestamp=base_time + timedelta(minutes=15),
        features={"rsi": 66.0},
    )
    await store.put_features(
        symbol="SILVER", timestamp=base_time, features={"rsi": 55.0}
    )

    count = await store.count_snapshots()

    assert count == 3


@pytest.mark.asyncio
async def test_count_snapshots_by_symbol(db_session: AsyncSession):
    """✅ REAL TEST: count_snapshots filters by symbol."""
    store = FeatureStore(db_session)

    base_time = datetime.now(UTC)

    # Store snapshots for multiple symbols
    await store.put_features(symbol="GOLD", timestamp=base_time, features={"rsi": 65.0})
    await store.put_features(
        symbol="GOLD",
        timestamp=base_time + timedelta(minutes=15),
        features={"rsi": 66.0},
    )
    await store.put_features(
        symbol="SILVER", timestamp=base_time, features={"rsi": 55.0}
    )

    count_gold = await store.count_snapshots(symbol="GOLD")
    count_silver = await store.count_snapshots(symbol="SILVER")

    assert count_gold == 2
    assert count_silver == 1


@pytest.mark.asyncio
async def test_count_snapshots_time_range(db_session: AsyncSession):
    """✅ REAL TEST: count_snapshots filters by time range."""
    store = FeatureStore(db_session)

    base_time = datetime.now(UTC)

    # Store snapshots spanning 1 hour
    for i in range(5):
        await store.put_features(
            symbol="GOLD",
            timestamp=base_time + timedelta(minutes=i * 15),
            features={"rsi": 60.0 + i},
        )

    # Count 30-minute window
    count = await store.count_snapshots(
        symbol="GOLD",
        start_time=base_time,
        end_time=base_time + timedelta(minutes=30),
    )

    assert count == 3  # 0, 15, 30 minutes


@pytest.mark.asyncio
async def test_delete_old_snapshots_success(db_session: AsyncSession):
    """✅ REAL TEST: delete_old_snapshots removes old data."""
    store = FeatureStore(db_session)

    base_time = datetime.now(UTC)

    # Store snapshots: 2 old, 1 recent
    await store.put_features(
        symbol="GOLD",
        timestamp=base_time - timedelta(days=10),
        features={"rsi": 60.0},
    )
    await store.put_features(
        symbol="GOLD",
        timestamp=base_time - timedelta(minutes=10),
        features={"rsi": 65.0},
    )
    await store.put_features(
        symbol="GOLD", timestamp=base_time, features={"rsi": 70.0}
    )

    # Delete snapshots older than 7 days
    deleted_count = await store.delete_old_snapshots(
        symbol="GOLD",
        older_than=base_time - timedelta(days=7),
    )

    assert deleted_count == 1  # Only the 10-day-old one

    # Verify remaining snapshots
    remaining = await store.get_features(symbol="GOLD")
    assert len(remaining) == 2


@pytest.mark.asyncio
async def test_delete_old_snapshots_no_matches(db_session: AsyncSession):
    """✅ REAL TEST: delete_old_snapshots returns 0 when no old data."""
    store = FeatureStore(db_session)

    base_time = datetime.now(UTC)

    # Store recent snapshot
    await store.put_features(symbol="GOLD", timestamp=base_time, features={"rsi": 70.0})

    # Try to delete snapshots older than 7 days (none exist)
    deleted_count = await store.delete_old_snapshots(
        symbol="GOLD",
        older_than=base_time - timedelta(days=7),
    )

    assert deleted_count == 0


@pytest.mark.asyncio
async def test_feature_snapshot_model_get_feature(db_session: AsyncSession):
    """✅ REAL TEST: FeatureSnapshot.get_feature() returns value or default."""
    snapshot = FeatureSnapshot(
        symbol="GOLD",
        timestamp=datetime.now(UTC),
        features={"rsi_14": 65.3, "roc_10": 0.012},
        quality_score=1.0,
    )

    assert snapshot.get_feature("rsi_14") == 65.3
    assert snapshot.get_feature("missing") is None
    assert snapshot.get_feature("missing", 0.0) == 0.0


@pytest.mark.asyncio
async def test_feature_snapshot_model_has_nan(db_session: AsyncSession):
    """✅ REAL TEST: FeatureSnapshot.has_nan() detects NaN values."""
    snapshot_clean = FeatureSnapshot(
        symbol="GOLD",
        timestamp=datetime.now(UTC),
        features={"rsi_14": 65.3, "roc_10": 0.012},
        quality_score=1.0,
    )

    snapshot_with_nan = FeatureSnapshot(
        symbol="GOLD",
        timestamp=datetime.now(UTC),
        features={"rsi_14": 65.3, "roc_10": float("nan")},
        quality_score=0.5,
    )

    assert not snapshot_clean.has_nan()
    assert snapshot_with_nan.has_nan()


@pytest.mark.asyncio
async def test_feature_snapshot_model_count_missing(db_session: AsyncSession):
    """✅ REAL TEST: FeatureSnapshot.count_missing() counts missing features."""
    snapshot = FeatureSnapshot(
        symbol="GOLD",
        timestamp=datetime.now(UTC),
        features={"rsi_14": 65.3},
        quality_score=1.0,
    )

    expected = ["rsi_14", "roc_10", "atr_14", "pivot_r1"]
    missing_count = snapshot.count_missing(expected)

    assert missing_count == 3  # roc_10, atr_14, pivot_r1 missing


@pytest.mark.asyncio
async def test_feature_snapshot_model_to_dict(db_session: AsyncSession):
    """✅ REAL TEST: FeatureSnapshot.to_dict() serializes correctly."""
    now = datetime.now(UTC)
    snapshot = FeatureSnapshot(
        id=1,
        symbol="GOLD",
        timestamp=now,
        features={"rsi_14": 65.3},
        quality_score=0.95,
        created_at=now,
    )

    data = snapshot.to_dict()

    assert data["id"] == 1
    assert data["symbol"] == "GOLD"
    assert data["timestamp"] == now.isoformat()
    assert data["features"] == {"rsi_14": 65.3}
    assert data["quality_score"] == 0.95
    assert data["created_at"] == now.isoformat()


@pytest.mark.asyncio
async def test_jsonb_complex_features(db_session: AsyncSession):
    """✅ REAL TEST: JSONB supports nested and complex feature structures."""
    store = FeatureStore(db_session)

    complex_features = {
        "rsi_14": 65.3,
        "roc_10": 0.012,
        "pivot_levels": {
            "r3": 2000.00,
            "r2": 1990.00,
            "r1": 1980.00,
            "pivot": 1970.00,
            "s1": 1960.00,
            "s2": 1950.00,
            "s3": 1940.00,
        },
        "fibonacci": [1950.25, 1960.50, 1970.75, 1980.00],
        "indicators": ["overbought", "bullish_cross"],
    }

    snapshot = await store.put_features(
        symbol="GOLD",
        timestamp=datetime.now(UTC),
        features=complex_features,
    )

    # Retrieve and verify
    retrieved = await store.get_by_id(snapshot.id)

    assert retrieved.features["rsi_14"] == 65.3
    assert retrieved.features["pivot_levels"]["r1"] == 1980.00
    assert retrieved.features["fibonacci"][0] == 1950.25
    assert "overbought" in retrieved.features["indicators"]


@pytest.mark.asyncio
async def test_multiple_symbols_isolation(db_session: AsyncSession):
    """✅ REAL TEST: Snapshots for different symbols are isolated."""
    store = FeatureStore(db_session)

    base_time = datetime.now(UTC)

    # Store snapshots for multiple symbols
    await store.put_features(symbol="GOLD", timestamp=base_time, features={"rsi": 65.0})
    await store.put_features(
        symbol="SILVER", timestamp=base_time, features={"rsi": 55.0}
    )
    await store.put_features(
        symbol="XAUUSD", timestamp=base_time, features={"rsi": 70.0}
    )

    # Query each symbol
    gold_latest = await store.get_latest("GOLD")
    silver_latest = await store.get_latest("SILVER")
    xauusd_latest = await store.get_latest("XAUUSD")

    assert gold_latest.features["rsi"] == 65.0
    assert silver_latest.features["rsi"] == 55.0
    assert xauusd_latest.features["rsi"] == 70.0
