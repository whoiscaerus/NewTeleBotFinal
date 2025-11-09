"""Feature Store database models.

Stores computed features (RSI, ROC, ATR, pivots) per symbol/timestamp
with quality scores for monitoring.

Examples:
    Store features:
        snapshot = FeatureSnapshot(
            symbol="GOLD",
            timestamp=datetime.now(UTC),
            features={
                "rsi_14": 65.3,
                "roc_10": 0.012,
                "atr_14": 12.5,
                "pivot_r1": 1975.50
            },
            quality_score=0.95
        )
        session.add(snapshot)
        await session.commit()
"""

from datetime import datetime
from typing import Any, Dict

from sqlalchemy import Column, DateTime, Float, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB

from backend.app.core.db import Base


class FeatureSnapshot(Base):
    """Feature snapshot model.

    Stores computed features for a symbol at a specific timestamp.
    Features are stored as JSONB for flexibility (different strategies
    may compute different features).

    Attributes:
        id: Primary key
        symbol: Trading instrument (GOLD, XAUUSD, etc.)
        timestamp: When features were computed (UTC)
        features: JSONB dict of feature name -> value
        quality_score: Overall quality score (0.0-1.0)
        created_at: Record creation timestamp
    """

    __tablename__ = "feature_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    features = Column(JSONB, nullable=False)
    quality_score = Column(Float, nullable=False, default=1.0)
    created_at = Column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now()
    )

    # Composite indexes for common queries
    __table_args__ = (
        Index("ix_features_symbol_timestamp", "symbol", "timestamp"),
        Index("ix_features_symbol_quality", "symbol", "quality_score"),
        Index("ix_features_timestamp_desc", "timestamp", postgresql_using="btree"),
    )

    def __repr__(self) -> str:
        return f"<FeatureSnapshot {self.symbol} @ {self.timestamp}: {len(self.features)} features, quality={self.quality_score:.2f}>"

    def get_feature(self, name: str, default: Any = None) -> Any:
        """Get a specific feature value.

        Args:
            name: Feature name (e.g., "rsi_14")
            default: Default value if feature not present

        Returns:
            Feature value or default

        Examples:
            >>> snapshot.get_feature("rsi_14")
            65.3
            >>> snapshot.get_feature("missing", 0.0)
            0.0
        """
        return self.features.get(name, default)

    def has_nan(self) -> bool:
        """Check if any features contain NaN values.

        Returns:
            True if any feature is NaN

        Examples:
            >>> snapshot.features = {"rsi": 65.3, "roc": float("nan")}
            >>> snapshot.has_nan()
            True
        """
        import math

        for value in self.features.values():
            if isinstance(value, (int, float)) and math.isnan(value):
                return True
        return False

    def count_missing(self, expected_features: list[str]) -> int:
        """Count missing expected features.

        Args:
            expected_features: List of expected feature names

        Returns:
            Count of missing features

        Examples:
            >>> snapshot.features = {"rsi_14": 65.3}
            >>> snapshot.count_missing(["rsi_14", "roc_10", "atr_14"])
            2
        """
        return sum(1 for f in expected_features if f not in self.features)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Dict with snapshot data

        Examples:
            >>> snapshot.to_dict()
            {
                "id": 1,
                "symbol": "GOLD",
                "timestamp": "2025-11-09T12:00:00Z",
                "features": {"rsi_14": 65.3},
                "quality_score": 0.95,
                "created_at": "2025-11-09T12:00:00Z"
            }
        """
        return {
            "id": self.id,
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "features": self.features,
            "quality_score": self.quality_score,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
