"""Feature Store and Quality Monitoring.

This module provides:
- Feature persistence (RSI, ROC, ATR, pivots, etc.)
- Quality checks (staleness, NaNs, regime shifts)
- Alert generation for quality violations

PR-079 deliverables.
"""

from backend.app.features.models import FeatureSnapshot
from backend.app.features.quality import QualityMonitor, QualityReport, QualityViolation
from backend.app.features.store import FeatureStore

__all__ = [
    "FeatureSnapshot",
    "FeatureStore",
    "QualityMonitor",
    "QualityReport",
    "QualityViolation",
]
