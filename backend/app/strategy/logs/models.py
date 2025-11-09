"""Decision log models for strategy audit trails.

Records every trade decision with:
- Input features (JSONB for flexible schema)
- Strategy rationale and thresholds
- Decision outcome (entered, skipped, rejected)
- Full context for replay and analytics
"""

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import Column, DateTime
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import Index, String, Text

from backend.app.core.db import Base, JSONBType


class DecisionOutcome(str, enum.Enum):
    """Possible outcomes of a trading decision."""

    ENTERED = "entered"  # Trade was executed
    SKIPPED = "skipped"  # Conditions not met, no trade
    REJECTED = "rejected"  # Failed validation or risk checks
    PENDING = "pending"  # Awaiting approval or additional data
    ERROR = "error"  # Technical error prevented decision


class DecisionLog(Base):
    """Records every trading decision for audit and analytics.

    Stores complete decision context including:
    - All input features used (price, indicators, sentiment, etc.)
    - Strategy parameters and thresholds at decision time
    - Rationale for the decision (why entered/skipped)
    - Outcome and any error messages
    - Timestamp for temporal analysis

    JSONB features field supports:
    - Flexible schema (strategy-specific features)
    - Efficient queries on nested data
    - Large payloads (full market context)

    Example features payload:
        {
            "price": {"open": 1950.50, "high": 1952.00, "low": 1949.00, "close": 1951.25},
            "indicators": {
                "rsi_14": 65.3,
                "macd": {"value": 0.52, "signal": 0.48, "histogram": 0.04},
                "fibonacci": {"level_382": 1948.00, "level_618": 1954.00}
            },
            "thresholds": {
                "rsi_overbought": 70,
                "rsi_oversold": 30,
                "risk_percent": 2.0
            },
            "sentiment": {"score": 0.65, "source": "news_api"},
            "position": {"size": 1.5, "risk_reward": 2.0}
        }
    """

    __tablename__ = "decision_logs"

    id = Column(String(36), primary_key=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    strategy = Column(String(100), nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)

    # Full decision context (flexible JSONB)
    features = Column(JSONBType, nullable=False)

    # Decision result
    outcome: DecisionOutcome = Column(  # type: ignore[assignment]
        SQLEnum(DecisionOutcome, name="decision_outcome_enum"),
        nullable=False,
        index=True,
    )

    # Human-readable rationale
    note = Column(Text, nullable=True)

    # Composite indexes for common queries
    __table_args__ = (
        Index("ix_decision_logs_strategy_timestamp", "strategy", "timestamp"),
        Index("ix_decision_logs_symbol_timestamp", "symbol", "timestamp"),
        Index("ix_decision_logs_outcome_timestamp", "outcome", "timestamp"),
        Index(
            "ix_decision_logs_strategy_symbol_timestamp",
            "strategy",
            "symbol",
            "timestamp",
        ),
    )

    def __repr__(self) -> str:
        """String representation of decision log."""
        return (
            f"<DecisionLog(id={self.id}, strategy={self.strategy}, "
            f"symbol={self.symbol}, outcome={self.outcome.value}, "
            f"timestamp={self.timestamp})>"
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization.

        Returns:
            Dictionary with all fields including features JSONB
        """
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "strategy": self.strategy,
            "symbol": self.symbol,
            "features": self.features,
            "outcome": self.outcome.value if self.outcome else None,
            "note": self.note,
        }

    @classmethod
    def sanitize_features(cls, features: dict[str, Any]) -> dict[str, Any]:
        """Remove PII from features before storage.

        Redacts:
        - User IDs (except anonymized hashes)
        - Email addresses
        - Phone numbers
        - API keys/tokens
        - Account numbers

        Args:
            features: Raw features dictionary

        Returns:
            Sanitized features dictionary
        """
        sanitized = features.copy()

        # List of keys to redact
        pii_keys = {
            "user_id",
            "email",
            "phone",
            "phone_number",
            "api_key",
            "api_token",
            "access_token",
            "account_number",
            "account_id",
        }

        def _redact_recursive(obj: Any) -> Any:
            """Recursively redact PII from nested structures."""
            if isinstance(obj, dict):
                return {
                    k: "[REDACTED]" if k.lower() in pii_keys else _redact_recursive(v)
                    for k, v in obj.items()
                }
            elif isinstance(obj, list):
                return [_redact_recursive(item) for item in obj]
            else:
                return obj

        result: dict[str, Any] = _redact_recursive(sanitized)
        return result
