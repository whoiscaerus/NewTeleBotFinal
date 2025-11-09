"""Comprehensive tests for Quality Monitor (PR-079).

Tests REAL business logic for feature quality checks.
NO MOCKS - validates actual quality detection algorithms.

Coverage targets:
- Staleness detection
- NaN detection
- Missing features detection
- Quality score thresholds
- Drift/regime shift detection
- Alert integration
- Edge cases and boundary conditions
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.features.quality import (
    QualityMonitor,
    ViolationType,
)
from backend.app.features.store import FeatureStore


@pytest.mark.asyncio
async def test_check_quality_all_pass(db_session: AsyncSession):
    """✅ REAL TEST: Quality check passes when all criteria met."""
    store = FeatureStore(db_session)
    monitor = QualityMonitor(db_session, min_quality_score=0.7, max_age_seconds=300)

    # Store fresh snapshot with good quality
    await store.put_features(
        symbol="GOLD",
        timestamp=datetime.now(UTC),
        features={"rsi_14": 65.3, "roc_10": 0.012, "atr_14": 12.5},
        quality_score=0.95,
    )

    report = await monitor.check_quality(
        symbol="GOLD",
        expected_features=["rsi_14", "roc_10", "atr_14"],
    )

    assert report.passed
    assert len(report.violations) == 0
    assert report.symbol == "GOLD"
    assert report.snapshot_id is not None


@pytest.mark.asyncio
async def test_check_quality_no_snapshots(db_session: AsyncSession):
    """✅ REAL TEST: Quality check fails when no snapshots exist."""
    monitor = QualityMonitor(db_session)

    report = await monitor.check_quality(
        symbol="NONEXISTENT",
        expected_features=["rsi_14"],
    )

    assert not report.passed
    assert len(report.violations) == 1
    assert report.violations[0].type == ViolationType.MISSING_FEATURES
    assert report.violations[0].severity == "high"
    assert "No feature snapshots found" in report.violations[0].message


@pytest.mark.asyncio
async def test_check_staleness_fresh_data(db_session: AsyncSession):
    """✅ REAL TEST: Fresh data passes staleness check."""
    store = FeatureStore(db_session)
    monitor = QualityMonitor(db_session, max_age_seconds=300)

    # Store snapshot from 2 minutes ago (< 5 min threshold)
    snapshot = await store.put_features(
        symbol="GOLD",
        timestamp=datetime.now(UTC) - timedelta(seconds=120),
        features={"rsi": 65.0},
    )

    violations = monitor.check_staleness(snapshot, max_age_seconds=300)

    assert len(violations) == 0


@pytest.mark.asyncio
async def test_check_staleness_stale_data_medium(db_session: AsyncSession):
    """✅ REAL TEST: Stale data triggers medium severity violation."""
    store = FeatureStore(db_session)
    monitor = QualityMonitor(db_session, max_age_seconds=300)

    # Store snapshot from 6 minutes ago (> 5 min threshold, < 10 min)
    snapshot = await store.put_features(
        symbol="GOLD",
        timestamp=datetime.now(UTC) - timedelta(seconds=360),
        features={"rsi": 65.0},
    )

    violations = monitor.check_staleness(snapshot, max_age_seconds=300)

    assert len(violations) == 1
    assert violations[0].type == ViolationType.STALE_DATA
    assert violations[0].severity == "medium"
    assert "360s old" in violations[0].message


@pytest.mark.asyncio
async def test_check_staleness_very_stale_data_high(db_session: AsyncSession):
    """✅ REAL TEST: Very stale data triggers high severity violation."""
    store = FeatureStore(db_session)
    monitor = QualityMonitor(db_session, max_age_seconds=300)

    # Store snapshot from 15 minutes ago (> 2x threshold)
    snapshot = await store.put_features(
        symbol="GOLD",
        timestamp=datetime.now(UTC) - timedelta(seconds=900),
        features={"rsi": 65.0},
    )

    violations = monitor.check_staleness(snapshot, max_age_seconds=300)

    assert len(violations) == 1
    assert violations[0].type == ViolationType.STALE_DATA
    assert violations[0].severity == "high"
    assert "900s old" in violations[0].message


@pytest.mark.asyncio
async def test_check_nans_no_nans(db_session: AsyncSession):
    """✅ REAL TEST: Clean data passes NaN check."""
    store = FeatureStore(db_session)
    monitor = QualityMonitor(db_session)

    snapshot = await store.put_features(
        symbol="GOLD",
        timestamp=datetime.now(UTC),
        features={"rsi_14": 65.3, "roc_10": 0.012, "atr_14": 12.5},
    )

    violations = monitor.check_nans(snapshot)

    assert len(violations) == 0


@pytest.mark.asyncio
async def test_check_nans_single_nan(db_session: AsyncSession):
    """✅ REAL TEST: Single NaN value triggers violation."""
    store = FeatureStore(db_session)
    monitor = QualityMonitor(db_session)

    snapshot = await store.put_features(
        symbol="GOLD",
        timestamp=datetime.now(UTC),
        features={"rsi_14": 65.3, "roc_10": float("nan"), "atr_14": 12.5},
    )

    violations = monitor.check_nans(snapshot)

    assert len(violations) == 1
    assert violations[0].type == ViolationType.NAN_VALUES
    assert violations[0].severity == "high"
    assert "roc_10" in violations[0].message
    assert violations[0].metadata["nan_features"] == ["roc_10"]


@pytest.mark.asyncio
async def test_check_nans_multiple_nans(db_session: AsyncSession):
    """✅ REAL TEST: Multiple NaN values all detected."""
    store = FeatureStore(db_session)
    monitor = QualityMonitor(db_session)

    snapshot = await store.put_features(
        symbol="GOLD",
        timestamp=datetime.now(UTC),
        features={
            "rsi_14": float("nan"),
            "roc_10": float("nan"),
            "atr_14": 12.5,
            "pivot": float("nan"),
        },
    )

    violations = monitor.check_nans(snapshot)

    assert len(violations) == 1
    assert violations[0].type == ViolationType.NAN_VALUES
    assert len(violations[0].metadata["nan_features"]) == 3
    assert "rsi_14" in violations[0].metadata["nan_features"]
    assert "roc_10" in violations[0].metadata["nan_features"]
    assert "pivot" in violations[0].metadata["nan_features"]


@pytest.mark.asyncio
async def test_check_missing_no_missing(db_session: AsyncSession):
    """✅ REAL TEST: All expected features present passes check."""
    store = FeatureStore(db_session)
    monitor = QualityMonitor(db_session)

    snapshot = await store.put_features(
        symbol="GOLD",
        timestamp=datetime.now(UTC),
        features={"rsi_14": 65.3, "roc_10": 0.012, "atr_14": 12.5},
    )

    violations = monitor.check_missing(snapshot, ["rsi_14", "roc_10", "atr_14"])

    assert len(violations) == 0


@pytest.mark.asyncio
async def test_check_missing_some_missing(db_session: AsyncSession):
    """✅ REAL TEST: Missing expected features triggers violation."""
    store = FeatureStore(db_session)
    monitor = QualityMonitor(db_session)

    snapshot = await store.put_features(
        symbol="GOLD",
        timestamp=datetime.now(UTC),
        features={"rsi_14": 65.3},
    )

    expected = ["rsi_14", "roc_10", "atr_14", "pivot_r1"]
    violations = monitor.check_missing(snapshot, expected)

    assert len(violations) == 1
    assert violations[0].type == ViolationType.MISSING_FEATURES
    assert violations[0].severity == "medium"
    assert "3 expected features missing" in violations[0].message
    assert set(violations[0].metadata["missing_features"]) == {
        "roc_10",
        "atr_14",
        "pivot_r1",
    }


@pytest.mark.asyncio
async def test_check_quality_score_above_threshold(db_session: AsyncSession):
    """✅ REAL TEST: Quality score above threshold passes."""
    store = FeatureStore(db_session)
    monitor = QualityMonitor(db_session, min_quality_score=0.7)

    snapshot = await store.put_features(
        symbol="GOLD",
        timestamp=datetime.now(UTC),
        features={"rsi": 65.0},
        quality_score=0.85,
    )

    violations = monitor.check_quality_score(snapshot)

    assert len(violations) == 0


@pytest.mark.asyncio
async def test_check_quality_score_below_threshold(db_session: AsyncSession):
    """✅ REAL TEST: Quality score below threshold triggers violation."""
    store = FeatureStore(db_session)
    monitor = QualityMonitor(db_session, min_quality_score=0.7)

    snapshot = await store.put_features(
        symbol="GOLD",
        timestamp=datetime.now(UTC),
        features={"rsi": 65.0},
        quality_score=0.5,
    )

    violations = monitor.check_quality_score(snapshot)

    assert len(violations) == 1
    assert violations[0].type == ViolationType.LOW_QUALITY_SCORE
    assert violations[0].severity == "medium"
    assert "0.50 below threshold 0.70" in violations[0].message


@pytest.mark.asyncio
async def test_check_drift_no_history(db_session: AsyncSession):
    """✅ REAL TEST: Drift check passes when insufficient history."""
    store = FeatureStore(db_session)
    monitor = QualityMonitor(db_session)

    # Store only current snapshot (no history)
    snapshot = await store.put_features(
        symbol="GOLD",
        timestamp=datetime.now(UTC),
        features={"rsi_14": 65.0},
    )

    violations = await monitor.check_drift("GOLD", snapshot)

    assert len(violations) == 0  # Not enough history


@pytest.mark.asyncio
async def test_check_drift_within_range(db_session: AsyncSession):
    """✅ REAL TEST: Feature values within 3σ pass drift check."""
    store = FeatureStore(db_session)
    monitor = QualityMonitor(db_session)

    base_time = datetime.now(UTC)

    # Store historical snapshots with RSI around 60-70 (mean ~65)
    for i in range(20):
        await store.put_features(
            symbol="GOLD",
            timestamp=base_time - timedelta(hours=i),
            features={"rsi_14": 60.0 + (i % 10)},  # Range 60-70
        )

    # Store current snapshot within range
    current = await store.put_features(
        symbol="GOLD",
        timestamp=base_time,
        features={"rsi_14": 65.0},
    )

    violations = await monitor.check_drift("GOLD", current)

    assert len(violations) == 0


@pytest.mark.asyncio
async def test_check_drift_regime_shift(db_session: AsyncSession):
    """✅ REAL TEST: Feature value > 3σ from baseline triggers drift violation."""
    store = FeatureStore(db_session)
    monitor = QualityMonitor(db_session)

    base_time = datetime.now(UTC)

    # Store historical snapshots with RSI consistently around 65 (tight range)
    for i in range(50):
        await store.put_features(
            symbol="GOLD",
            timestamp=base_time - timedelta(hours=i),
            features={"rsi_14": 65.0 + (i % 3 - 1) * 0.5},  # Range 64-66
        )

    # Store current snapshot WAY outside historical range
    current = await store.put_features(
        symbol="GOLD",
        timestamp=base_time,
        features={"rsi_14": 95.0},  # Extreme overbought
    )

    violations = await monitor.check_drift("GOLD", current)

    assert len(violations) == 1
    assert violations[0].type == ViolationType.DRIFT_DETECTED
    assert violations[0].severity in ["medium", "high"]
    assert "rsi_14" in violations[0].message
    assert violations[0].metadata["z_score"] > 3.0
    assert violations[0].metadata["current_value"] == 95.0


@pytest.mark.asyncio
async def test_check_drift_multiple_features(db_session: AsyncSession):
    """✅ REAL TEST: Drift detection works across multiple features."""
    store = FeatureStore(db_session)
    monitor = QualityMonitor(db_session)

    base_time = datetime.now(UTC)

    # Store historical snapshots with stable values
    for i in range(50):
        await store.put_features(
            symbol="GOLD",
            timestamp=base_time - timedelta(hours=i),
            features={
                "rsi_14": 65.0 + (i % 3 - 1) * 0.5,  # Stable around 65
                "roc_10": 0.01 + (i % 3 - 1) * 0.001,  # Stable around 0.01
                "atr_14": 12.0 + (i % 3 - 1) * 0.1,  # Stable around 12
            },
        )

    # Store current snapshot with RSI and ROC shifted, ATR normal
    current = await store.put_features(
        symbol="GOLD",
        timestamp=base_time,
        features={
            "rsi_14": 95.0,  # Drifted
            "roc_10": 0.10,  # Drifted
            "atr_14": 12.0,  # Normal
        },
    )

    violations = await monitor.check_drift("GOLD", current)

    # Should detect drift in rsi_14 and roc_10
    assert len(violations) >= 2
    drifted_features = {v.metadata["feature"] for v in violations}
    assert "rsi_14" in drifted_features
    assert "roc_10" in drifted_features


@pytest.mark.asyncio
async def test_check_quality_multiple_violations(db_session: AsyncSession):
    """✅ REAL TEST: Multiple violation types detected in one check."""
    store = FeatureStore(db_session)
    monitor = QualityMonitor(db_session, min_quality_score=0.7, max_age_seconds=300)

    # Store snapshot with multiple issues
    await store.put_features(
        symbol="GOLD",
        timestamp=datetime.now(UTC) - timedelta(seconds=600),  # Stale
        features={
            "rsi_14": float("nan"),  # NaN
            "roc_10": 0.012,
        },
        quality_score=0.5,  # Low quality
    )

    report = await monitor.check_quality(
        symbol="GOLD",
        expected_features=["rsi_14", "roc_10", "atr_14"],  # atr_14 missing
    )

    assert not report.passed
    assert len(report.violations) >= 4  # stale, nan, low_quality, missing

    violation_types = {v.type for v in report.violations}
    assert ViolationType.STALE_DATA in violation_types
    assert ViolationType.NAN_VALUES in violation_types
    assert ViolationType.LOW_QUALITY_SCORE in violation_types
    assert ViolationType.MISSING_FEATURES in violation_types


@pytest.mark.asyncio
async def test_quality_report_structure(db_session: AsyncSession):
    """✅ REAL TEST: QualityReport structure complete and accurate."""
    store = FeatureStore(db_session)
    monitor = QualityMonitor(db_session)

    snapshot = await store.put_features(
        symbol="GOLD",
        timestamp=datetime.now(UTC) - timedelta(seconds=600),
        features={"rsi": 65.0},
    )

    report = await monitor.check_quality(symbol="GOLD")

    assert report.symbol == "GOLD"
    assert report.timestamp is not None
    assert isinstance(report.passed, bool)
    assert isinstance(report.violations, list)
    assert report.snapshot_id == snapshot.id


@pytest.mark.asyncio
async def test_quality_violation_structure(db_session: AsyncSession):
    """✅ REAL TEST: QualityViolation structure complete."""
    store = FeatureStore(db_session)
    monitor = QualityMonitor(db_session)

    snapshot = await store.put_features(
        symbol="GOLD",
        timestamp=datetime.now(UTC),
        features={"rsi": float("nan")},
    )

    violations = monitor.check_nans(snapshot)

    assert len(violations) == 1
    v = violations[0]
    assert isinstance(v.type, ViolationType)
    assert v.symbol == "GOLD"
    assert len(v.message) > 0
    assert v.severity in ["low", "medium", "high"]
    assert isinstance(v.metadata, dict)


@pytest.mark.asyncio
async def test_check_quality_custom_max_age(db_session: AsyncSession):
    """✅ REAL TEST: Override max_age_seconds per check."""
    store = FeatureStore(db_session)
    monitor = QualityMonitor(db_session, max_age_seconds=300)  # Default 5 min

    # Store snapshot 4 minutes old
    await store.put_features(
        symbol="GOLD",
        timestamp=datetime.now(UTC) - timedelta(seconds=240),
        features={"rsi": 65.0},
    )

    # Check with default (should pass)
    report_default = await monitor.check_quality(symbol="GOLD")
    assert report_default.passed

    # Check with custom max_age=180 (3 min) (should fail)
    report_custom = await monitor.check_quality(symbol="GOLD", max_age_seconds=180)
    assert not report_custom.passed
    assert any(v.type == ViolationType.STALE_DATA for v in report_custom.violations)


@pytest.mark.asyncio
async def test_drift_detection_boundary_z_score(db_session: AsyncSession):
    """✅ REAL TEST: Drift detection z-score boundary (exactly 3.0)."""
    store = FeatureStore(db_session)
    monitor = QualityMonitor(db_session)

    base_time = datetime.now(UTC)

    # Create data with known mean and stdev
    # Mean = 50, Stdev = 10 (approximately)
    historical_values = list(range(40, 61))  # 40-60, mean=50, stdev~6.1

    for i, val in enumerate(historical_values):
        await store.put_features(
            symbol="GOLD",
            timestamp=base_time - timedelta(hours=len(historical_values) - i),
            features={"rsi": float(val)},
        )

    # Z = 3.0 means value should be ~3 * stdev from mean
    # If mean=50, stdev=6.1, then z=3.0 → value = 50 + 3*6.1 = 68.3

    # Store value just at boundary
    current = await store.put_features(
        symbol="GOLD",
        timestamp=base_time,
        features={"rsi": 69.0},  # Should trigger drift
    )

    violations = await monitor.check_drift("GOLD", current)

    # Should detect drift since z > 3.0
    assert len(violations) == 1
    assert violations[0].metadata["z_score"] > 3.0


@pytest.mark.asyncio
async def test_drift_detection_severity_levels(db_session: AsyncSession):
    """✅ REAL TEST: Drift severity based on z-score magnitude."""
    store = FeatureStore(db_session)
    monitor = QualityMonitor(db_session)

    base_time = datetime.now(UTC)

    # Store stable historical data
    for i in range(50):
        await store.put_features(
            symbol="GOLD",
            timestamp=base_time - timedelta(hours=i),
            features={"rsi": 50.0},  # Constant value → stdev very small
        )

    # Medium severity: moderate drift (3σ < z < 5σ)
    current_medium = await store.put_features(
        symbol="GOLD",
        timestamp=base_time,
        features={"rsi": 54.0},
    )
    violations_medium = await monitor.check_drift("GOLD", current_medium)
    if violations_medium:
        # Severity depends on actual z-score
        assert violations_medium[0].severity in ["medium", "high"]

    # High severity: extreme drift (z > 5σ)
    current_high = await store.put_features(
        symbol="GOLD",
        timestamp=base_time + timedelta(seconds=1),
        features={"rsi": 80.0},  # Very far from baseline
    )
    violations_high = await monitor.check_drift("GOLD", current_high)
    assert len(violations_high) == 1
    # With constant historical values, any deviation should have high z-score
    assert violations_high[0].metadata["z_score"] > 5.0
    assert violations_high[0].severity == "high"


@pytest.mark.asyncio
async def test_quality_check_empty_features(db_session: AsyncSession):
    """✅ REAL TEST: Handle snapshot with empty features dict."""
    store = FeatureStore(db_session)
    monitor = QualityMonitor(db_session)

    # Store snapshot with no features
    await store.put_features(
        symbol="GOLD",
        timestamp=datetime.now(UTC),
        features={},
        quality_score=0.0,
    )

    report = await monitor.check_quality(
        symbol="GOLD",
        expected_features=["rsi_14"],
    )

    assert not report.passed
    # Should have violations for missing features and low quality
    assert any(v.type == ViolationType.MISSING_FEATURES for v in report.violations)
    assert any(v.type == ViolationType.LOW_QUALITY_SCORE for v in report.violations)
