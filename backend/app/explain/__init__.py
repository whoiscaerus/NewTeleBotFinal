"""Model explainability module.

Provides feature attribution and SHAP-like analysis for strategy decisions.
Helps understand "why" a decision was made by computing per-feature contributions.

Key capabilities:
- Feature importance/SHAP-like computation
- Per-decision attribution analysis
- Support for multiple strategy types
- Contribution validation (sum to prediction delta)

Example:
    >>> from backend.app.explain import compute_attribution
    >>> result = await compute_attribution(
    ...     decision_id="abc-123",
    ...     strategy="fib_rsi"
    ... )
    >>> print(result.contributions)  # {"rsi_14": 0.35, "fib_level": 0.15, ...}
    >>> print(result.prediction_delta)  # 0.50 (sum of contributions)
"""

from backend.app.explain.attribution import (
    AttributionResult,
    compute_attribution,
    compute_feature_importance,
)

__all__ = [
    "AttributionResult",
    "compute_attribution",
    "compute_feature_importance",
]
