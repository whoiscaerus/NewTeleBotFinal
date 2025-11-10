"""Fraud detection models for anomaly tracking."""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import uuid4

from sqlalchemy import Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.db import Base


class AnomalyType(str, Enum):
    """Types of detected anomalies."""

    SLIPPAGE_EXTREME = "slippage_extreme"  # Slippage beyond z-score threshold
    LATENCY_SPIKE = "latency_spike"  # Execution delay spike
    OUT_OF_BAND_FILL = "out_of_band_fill"  # Fill price outside expected range
    VOLUME_ANOMALY = "volume_anomaly"  # Unexpected volume change
    REPEATED_FAILURE = "repeated_failure"  # Multiple failures in short time
    PRICE_MANIPULATION = "price_manipulation"  # Suspicious price patterns


class AnomalySeverity(str, Enum):
    """Severity levels for anomalies."""

    LOW = "low"  # Minor deviation, informational
    MEDIUM = "medium"  # Moderate concern, review recommended
    HIGH = "high"  # Significant issue, immediate review
    CRITICAL = "critical"  # Severe fraud indicator, urgent action


class AnomalyEvent(Base):
    """Represents a detected anomaly in trade execution.

    Tracks suspicious patterns in MT5 execution including slippage,
    latency bursts, and out-of-band fills for fraud detection.

    Attributes:
        event_id: Unique identifier (UUID)
        user_id: User associated with the trade
        trade_id: Reference to suspicious trade (nullable for batch anomalies)
        anomaly_type: Type of detected anomaly
        severity: Severity level (low, medium, high, critical)
        score: Anomaly score (0-1, higher = more suspicious)
        details: JSON details about the anomaly
        detected_at: When anomaly was detected (UTC)
        reviewed_at: When admin reviewed (nullable)
        reviewed_by: Admin user_id who reviewed (nullable)
        status: OPEN, INVESTIGATING, RESOLVED, FALSE_POSITIVE
        resolution_note: Admin's resolution notes (nullable)

    Business Rules:
        - Score range: 0.0 to 1.0
        - Severity thresholds: <0.3 LOW, 0.3-0.6 MEDIUM, 0.6-0.85 HIGH, >0.85 CRITICAL
        - Status transitions: OPEN → INVESTIGATING → RESOLVED/FALSE_POSITIVE
        - Auto-escalate CRITICAL to admin Telegram within 5 minutes
    """

    __tablename__ = "anomaly_events"

    # Primary Key
    event_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )

    # Foreign Keys
    user_id: Mapped[str] = mapped_column(
        String(36), nullable=False, index=True, doc="User whose trade triggered anomaly"
    )
    trade_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True, doc="Suspicious trade (null for batch)"
    )

    # Anomaly Details
    anomaly_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True, doc="Type of anomaly detected"
    )
    severity: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="low",
        doc="Severity: low, medium, high, critical",
    )
    score: Mapped[Decimal] = mapped_column(
        nullable=False, doc="Anomaly score 0-1 (higher = more suspicious)"
    )

    # Metadata
    details: Mapped[dict] = mapped_column(
        type_=Text,
        nullable=False,
        doc="JSON details: slippage_pips, latency_ms, expected_range, etc.",
    )

    # Detection Timestamp
    detected_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.utcnow, index=True
    )

    # Review Tracking
    reviewed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(
        String(36), nullable=True, doc="Admin user_id who reviewed"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="open",
        doc="Status: open, investigating, resolved, false_positive",
    )
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Indexes for common queries
    __table_args__ = (
        Index("ix_anomaly_events_type_detected", "anomaly_type", "detected_at"),
        Index("ix_anomaly_events_severity_status", "severity", "status"),
        Index("ix_anomaly_events_user_detected", "user_id", "detected_at"),
    )

    def __repr__(self) -> str:
        """String representation of anomaly event."""
        return (
            f"<AnomalyEvent {self.event_id}: {self.anomaly_type} "
            f"score={float(self.score):.3f} severity={self.severity}>"
        )
