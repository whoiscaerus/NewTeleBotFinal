"""Feature quality monitoring.

Checks for:
- Missing features
- NaN values
- Stale data
- Drift/regime shifts

Examples:
    Run quality checks:
        monitor = QualityMonitor(session)
        report = await monitor.check_quality(
            symbol="GOLD",
            expected_features=["rsi_14", "roc_10", "atr_14"],
            max_age_seconds=300
        )

        if not report.passed:
            for violation in report.violations:
                await send_feature_quality_alert(violation)
"""

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.features.store import FeatureStore

logger = logging.getLogger(__name__)


class ViolationType(str, Enum):
    """Quality violation types."""

    MISSING_FEATURES = "missing_features"
    NAN_VALUES = "nan_values"
    STALE_DATA = "stale_data"
    DRIFT_DETECTED = "drift_detected"
    LOW_QUALITY_SCORE = "low_quality_score"


@dataclass
class QualityViolation:
    """A quality check violation.

    Attributes:
        type: Violation type
        symbol: Trading instrument
        message: Human-readable description
        severity: low/medium/high
        metadata: Additional context
    """

    type: ViolationType
    symbol: str
    message: str
    severity: str = "medium"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        return f"<QualityViolation {self.type.value} [{self.severity}]: {self.message}>"


@dataclass
class QualityReport:
    """Quality check report.

    Attributes:
        symbol: Trading instrument
        timestamp: When check was performed
        passed: True if all checks passed
        violations: List of violations found
        snapshot_id: ID of checked snapshot (optional)
    """

    symbol: str
    timestamp: datetime
    passed: bool
    violations: List[QualityViolation] = field(default_factory=list)
    snapshot_id: Optional[int] = None

    def __repr__(self) -> str:
        status = (
            "PASSED" if self.passed else f"FAILED ({len(self.violations)} violations)"
        )
        return f"<QualityReport {self.symbol} @ {self.timestamp}: {status}>"


class QualityMonitor:
    """Feature quality monitoring service.

    Runs checks on feature snapshots and generates violation reports.
    """

    def __init__(
        self,
        session: AsyncSession,
        min_quality_score: float = 0.7,
        max_age_seconds: int = 300,
    ):
        """Initialize quality monitor.

        Args:
            session: Database session
            min_quality_score: Minimum acceptable quality score (0.0-1.0)
            max_age_seconds: Maximum age for fresh data (seconds)
        """
        self.session = session
        self.store = FeatureStore(session)
        self.min_quality_score = min_quality_score
        self.max_age_seconds = max_age_seconds

    async def check_quality(
        self,
        symbol: str,
        expected_features: Optional[List[str]] = None,
        max_age_seconds: Optional[int] = None,
    ) -> QualityReport:
        """Run all quality checks on the latest snapshot.

        Args:
            symbol: Trading instrument
            expected_features: List of expected feature names (optional)
            max_age_seconds: Override default max age (optional)

        Returns:
            QualityReport with violations

        Examples:
            >>> report = await monitor.check_quality(
            ...     symbol="GOLD",
            ...     expected_features=["rsi_14", "roc_10", "atr_14"],
            ...     max_age_seconds=300
            ... )
            >>> report.passed
            True
        """
        violations: List[QualityViolation] = []
        snapshot = await self.store.get_latest(symbol)

        if not snapshot:
            violations.append(
                QualityViolation(
                    type=ViolationType.MISSING_FEATURES,
                    symbol=symbol,
                    message=f"No feature snapshots found for {symbol}",
                    severity="high",
                    metadata={"reason": "no_snapshots"},
                )
            )
            return QualityReport(
                symbol=symbol,
                timestamp=datetime.now(),
                passed=False,
                violations=violations,
            )

        # Check staleness
        staleness_violations = self.check_staleness(
            snapshot, max_age_seconds or self.max_age_seconds
        )
        violations.extend(staleness_violations)

        # Check for NaNs
        nan_violations = self.check_nans(snapshot)
        violations.extend(nan_violations)

        # Check missing features
        if expected_features:
            missing_violations = self.check_missing(snapshot, expected_features)
            violations.extend(missing_violations)

        # Check quality score
        score_violations = self.check_quality_score(snapshot)
        violations.extend(score_violations)

        # Check drift (if historical data available)
        drift_violations = await self.check_drift(symbol, snapshot)
        violations.extend(drift_violations)

        return QualityReport(
            symbol=symbol,
            timestamp=datetime.now(),
            passed=len(violations) == 0,
            violations=violations,
            snapshot_id=snapshot.id,
        )

    def check_staleness(
        self, snapshot: Any, max_age_seconds: int
    ) -> List[QualityViolation]:
        """Check if data is stale.

        Args:
            snapshot: FeatureSnapshot to check
            max_age_seconds: Maximum acceptable age

        Returns:
            List of violations (empty if fresh)

        Examples:
            >>> violations = monitor.check_staleness(snapshot, 300)
            >>> len(violations)
            0
        """
        violations = []
        now = datetime.now()
        age_seconds = (now - snapshot.timestamp).total_seconds()

        if age_seconds > max_age_seconds:
            violations.append(
                QualityViolation(
                    type=ViolationType.STALE_DATA,
                    symbol=snapshot.symbol,
                    message=f"Data is {age_seconds:.0f}s old (max {max_age_seconds}s)",
                    severity="high" if age_seconds > max_age_seconds * 2 else "medium",
                    metadata={
                        "age_seconds": age_seconds,
                        "max_age_seconds": max_age_seconds,
                        "snapshot_timestamp": snapshot.timestamp.isoformat(),
                    },
                )
            )

        return violations

    def check_nans(self, snapshot: Any) -> List[QualityViolation]:
        """Check for NaN values in features.

        Args:
            snapshot: FeatureSnapshot to check

        Returns:
            List of violations (empty if no NaNs)

        Examples:
            >>> snapshot.features = {"rsi": 65.3, "roc": float("nan")}
            >>> violations = monitor.check_nans(snapshot)
            >>> len(violations)
            1
        """
        violations = []
        nan_features = []

        for name, value in snapshot.features.items():
            if isinstance(value, (int, float)) and math.isnan(value):
                nan_features.append(name)

        if nan_features:
            violations.append(
                QualityViolation(
                    type=ViolationType.NAN_VALUES,
                    symbol=snapshot.symbol,
                    message=f"{len(nan_features)} features contain NaN: {', '.join(nan_features)}",
                    severity="high",
                    metadata={
                        "nan_features": nan_features,
                        "snapshot_id": snapshot.id,
                    },
                )
            )

        return violations

    def check_missing(
        self, snapshot: Any, expected_features: List[str]
    ) -> List[QualityViolation]:
        """Check for missing expected features.

        Args:
            snapshot: FeatureSnapshot to check
            expected_features: List of required feature names

        Returns:
            List of violations (empty if all present)

        Examples:
            >>> snapshot.features = {"rsi_14": 65.3}
            >>> violations = monitor.check_missing(snapshot, ["rsi_14", "roc_10", "atr_14"])
            >>> len(violations)
            1
        """
        violations = []
        missing_features = [f for f in expected_features if f not in snapshot.features]

        if missing_features:
            violations.append(
                QualityViolation(
                    type=ViolationType.MISSING_FEATURES,
                    symbol=snapshot.symbol,
                    message=f"{len(missing_features)} expected features missing: {', '.join(missing_features)}",
                    severity="medium",
                    metadata={
                        "missing_features": missing_features,
                        "snapshot_id": snapshot.id,
                    },
                )
            )

        return violations

    def check_quality_score(self, snapshot: Any) -> List[QualityViolation]:
        """Check if quality score is below threshold.

        Args:
            snapshot: FeatureSnapshot to check

        Returns:
            List of violations (empty if score acceptable)

        Examples:
            >>> snapshot.quality_score = 0.5
            >>> violations = monitor.check_quality_score(snapshot)
            >>> len(violations)
            1
        """
        violations = []

        if snapshot.quality_score < self.min_quality_score:
            violations.append(
                QualityViolation(
                    type=ViolationType.LOW_QUALITY_SCORE,
                    symbol=snapshot.symbol,
                    message=f"Quality score {snapshot.quality_score:.2f} below threshold {self.min_quality_score:.2f}",
                    severity="medium",
                    metadata={
                        "quality_score": snapshot.quality_score,
                        "threshold": self.min_quality_score,
                        "snapshot_id": snapshot.id,
                    },
                )
            )

        return violations

    async def check_drift(
        self, symbol: str, current_snapshot: Any
    ) -> List[QualityViolation]:
        """Check for feature drift/regime shifts.

        Compares current features to historical mean/std to detect
        significant shifts that may indicate regime change.

        Args:
            symbol: Trading instrument
            current_snapshot: Current FeatureSnapshot

        Returns:
            List of violations (empty if no drift)

        Examples:
            >>> violations = await monitor.check_drift("GOLD", snapshot)
            >>> len(violations)
            0
        """
        violations = []

        # Get last 7 days of snapshots for baseline
        lookback = datetime.now() - timedelta(days=7)
        historical = await self.store.get_features(
            symbol=symbol,
            start_time=lookback,
            limit=1000,
        )

        if len(historical) < 10:
            # Not enough history for drift detection
            return violations

        # Calculate mean and std for each feature
        import statistics

        for feature_name, current_value in current_snapshot.features.items():
            if not isinstance(current_value, (int, float)) or math.isnan(current_value):
                continue

            # Get historical values
            historical_values = [
                s.features.get(feature_name)
                for s in historical
                if s.features.get(feature_name) is not None
                and isinstance(s.features.get(feature_name), (int, float))
                and not math.isnan(s.features.get(feature_name))
            ]

            if len(historical_values) < 10:
                continue

            try:
                mean = statistics.mean(historical_values)
                stdev = statistics.stdev(historical_values)

                # Check if current value is > 3 std deviations from mean
                if stdev > 0:
                    z_score = abs((current_value - mean) / stdev)

                    if z_score > 3.0:
                        violations.append(
                            QualityViolation(
                                type=ViolationType.DRIFT_DETECTED,
                                symbol=symbol,
                                message=f"Feature {feature_name} drifted {z_score:.2f}σ from baseline",
                                severity="medium" if z_score < 5.0 else "high",
                                metadata={
                                    "feature": feature_name,
                                    "current_value": current_value,
                                    "historical_mean": mean,
                                    "historical_stdev": stdev,
                                    "z_score": z_score,
                                    "baseline_samples": len(historical_values),
                                },
                            )
                        )

            except statistics.StatisticsError:
                # Skip if not enough variance
                continue

        return violations
