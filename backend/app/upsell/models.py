"""
Upsell database models.

Models for recommendations, A/B experiments, variants, and exposure tracking.
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from backend.app.core.db import Base


class RecommendationType(str, Enum):
    """Type of upsell recommendation."""

    PLAN_UPGRADE = "plan_upgrade"
    COPY_TRADING = "copy_trading"
    ANALYTICS_PRO = "analytics_pro"
    DEVICE_SLOTS = "device_slots"
    TIER_UPGRADE = "tier_upgrade"


class ExperimentStatus(str, Enum):
    """Status of A/B experiment."""

    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class Recommendation(Base):
    """
    Upsell recommendation generated for a user.

    Tracks personalized upgrade suggestions based on usage, performance, and behavior.
    """

    __tablename__ = "recommendations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    recommendation_type = Column(String(50), nullable=False)  # RecommendationType
    score = Column(Float, nullable=False)  # 0.0-1.0 confidence score
    variant_id = Column(
        String(36), ForeignKey("variants.id", ondelete="SET NULL"), nullable=True
    )

    # Scoring inputs (JSON-serialized behavioral signals)
    usage_score = Column(Float, nullable=False, default=0.0)  # approvals, alerts
    performance_score = Column(Float, nullable=False, default=0.0)  # PnL stability
    intent_score = Column(Float, nullable=False, default=0.0)  # billing page visits
    cohort_score = Column(Float, nullable=False, default=0.0)  # cohort analysis

    # Recommendation details
    headline = Column(String(200), nullable=False)
    copy = Column(Text, nullable=False)
    discount_percent = Column(Integer, nullable=True)  # 0-100 or null
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # State
    shown = Column(Boolean, nullable=False, default=False)
    clicked = Column(Boolean, nullable=False, default=False)
    converted = Column(Boolean, nullable=False, default=False)

    # Timestamps
    created_at = Column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    shown_at = Column(DateTime(timezone=True), nullable=True)
    clicked_at = Column(DateTime(timezone=True), nullable=True)
    converted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", back_populates="recommendations")
    variant = relationship("Variant", back_populates="recommendations")

    __table_args__ = (
        Index("ix_recommendations_user_type", "user_id", "recommendation_type"),
        Index("ix_recommendations_score", "score"),
        Index("ix_recommendations_created", "created_at"),
        CheckConstraint(
            "score >= 0.0 AND score <= 1.0", name="ck_recommendation_score_range"
        ),
        CheckConstraint(
            "discount_percent IS NULL OR (discount_percent >= 0 AND discount_percent <= 100)",
            name="ck_recommendation_discount_range",
        ),
    )

    def __repr__(self):
        return f"<Recommendation {self.id}: {self.recommendation_type} for {self.user_id} (score={self.score:.2f})>"


class Experiment(Base):
    """
    A/B test experiment for upsell messaging.

    Defines experiment parameters and tracks overall performance.
    """

    __tablename__ = "experiments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name = Column(String(200), nullable=False, unique=True)
    description = Column(Text, nullable=True)

    # Experiment config
    recommendation_type = Column(String(50), nullable=False)  # which upsell type
    traffic_split_percent = Column(
        Integer, nullable=False, default=50
    )  # % for variant vs control
    min_sample_size = Column(Integer, nullable=False, default=100)

    # Status
    status = Column(String(20), nullable=False, default=ExperimentStatus.DRAFT.value)

    # Guardrails
    min_ctr = Column(Float, nullable=True)  # auto-fail if below
    max_duration_days = Column(Integer, nullable=True)

    # Results
    control_exposures = Column(Integer, nullable=False, default=0)
    control_conversions = Column(Integer, nullable=False, default=0)
    variant_exposures = Column(Integer, nullable=False, default=0)
    variant_conversions = Column(Integer, nullable=False, default=0)

    # Timestamps
    created_at = Column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    started_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    variants = relationship(
        "Variant", back_populates="experiment", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_experiments_status", "status"),
        Index("ix_experiments_type", "recommendation_type"),
        CheckConstraint(
            "traffic_split_percent >= 0 AND traffic_split_percent <= 100",
            name="ck_experiment_split_range",
        ),
    )

    def __repr__(self):
        return f"<Experiment {self.name}: {self.status}>"

    @property
    def control_ctr(self) -> float:
        """Calculate control CTR."""
        if self.control_exposures == 0:
            return 0.0
        return self.control_conversions / self.control_exposures

    @property
    def variant_ctr(self) -> float:
        """Calculate variant CTR."""
        if self.variant_exposures == 0:
            return 0.0
        return self.variant_conversions / self.variant_exposures

    @property
    def uplift(self) -> Optional[float]:
        """Calculate uplift (variant vs control)."""
        if self.control_ctr == 0:
            return None
        return (self.variant_ctr - self.control_ctr) / self.control_ctr


class Variant(Base):
    """
    A/B test variant with specific messaging.

    Defines copy, headline, discount, and other variant-specific parameters.
    """

    __tablename__ = "variants"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    experiment_id = Column(
        String(36), ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False
    )
    name = Column(String(200), nullable=False)  # "control", "variant_a", "variant_b"

    # Variant copy
    headline = Column(String(200), nullable=False)
    copy = Column(Text, nullable=False)
    cta_text = Column(String(100), nullable=False, default="Upgrade Now")

    # Pricing variant
    discount_percent = Column(Integer, nullable=True)  # 0-100 or null

    # Metadata
    is_control = Column(Boolean, nullable=False, default=False)

    # Timestamps
    created_at = Column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    # Relationships
    experiment = relationship("Experiment", back_populates="variants")
    recommendations = relationship("Recommendation", back_populates="variant")
    exposures = relationship(
        "Exposure", back_populates="variant", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_variants_experiment", "experiment_id"),
        Index("ix_variants_control", "is_control"),
        CheckConstraint(
            "discount_percent IS NULL OR (discount_percent >= 0 AND discount_percent <= 100)",
            name="ck_variant_discount_range",
        ),
    )

    def __repr__(self):
        return f"<Variant {self.name} for experiment {self.experiment_id}>"


class Exposure(Base):
    """
    Records when a user is exposed to a variant.

    Ensures exposure is logged exactly once per user per experiment.
    """

    __tablename__ = "exposures"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    experiment_id = Column(
        String(36), ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False
    )
    variant_id = Column(
        String(36), ForeignKey("variants.id", ondelete="CASCADE"), nullable=False
    )
    recommendation_id = Column(
        String(36), ForeignKey("recommendations.id", ondelete="SET NULL"), nullable=True
    )

    # Conversion tracking
    converted = Column(Boolean, nullable=False, default=False)
    converted_at = Column(DateTime(timezone=True), nullable=True)

    # Metadata
    channel = Column(String(50), nullable=True)  # "telegram", "miniapp", "web", "email"

    # Timestamps
    created_at = Column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    # Relationships
    user = relationship("User", back_populates="exposures")
    variant = relationship("Variant", back_populates="exposures")

    __table_args__ = (
        Index("ix_exposures_user_experiment", "user_id", "experiment_id", unique=True),
        Index("ix_exposures_variant", "variant_id"),
        Index("ix_exposures_converted", "converted"),
        Index("ix_exposures_created", "created_at"),
    )

    def __repr__(self):
        return f"<Exposure {self.id}: user={self.user_id}, experiment={self.experiment_id}>"
