"""
Journey Builder Models

Defines journey workflows, steps, triggers, and user progress tracking.
"""

from datetime import datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from backend.app.core.db import Base


class TriggerType(str, Enum):
    """Types of triggers that can start or advance a journey."""

    SIGNUP = "signup"
    FIRST_APPROVAL = "first_approval"
    PAYMENT_SUCCESS = "payment_success"
    PAYMENT_FAIL = "payment_fail"
    CHURN_RISK = "churn_risk"
    IDLE_USER = "idle_user"
    UPGRADE = "upgrade"
    DOWNGRADE = "downgrade"
    DEVICE_ADDED = "device_added"
    SUBSCRIPTION_EXPIRING = "subscription_expiring"


class ActionType(str, Enum):
    """Types of actions a journey step can perform."""

    SEND_EMAIL = "send_email"
    SEND_TELEGRAM = "send_telegram"
    SEND_PUSH = "send_push"
    APPLY_TAG = "apply_tag"
    REMOVE_TAG = "remove_tag"
    SCHEDULE_NEXT = "schedule_next"
    GRANT_REWARD = "grant_reward"
    TRIGGER_WEBHOOK = "trigger_webhook"


class Journey(Base):
    """
    Journey workflow definition.

    A journey is a series of steps triggered by user actions or time-based rules.
    """

    __tablename__ = "journeys"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name = Column(String(100), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    trigger_type = Column(String(50), nullable=False, index=True)
    trigger_config = Column(
        JSON, nullable=False, default=dict
    )  # Additional trigger parameters
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    priority = Column(Integer, nullable=False, default=0)  # Higher priority runs first
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    steps = relationship(
        "JourneyStep",
        back_populates="journey",
        cascade="all, delete-orphan",
        order_by="JourneyStep.order",
    )
    user_journeys = relationship(
        "UserJourney", back_populates="journey", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_journeys_active_trigger", "is_active", "trigger_type"),
        Index("ix_journeys_priority", "priority"),
    )

    def __repr__(self):
        return f"<Journey {self.name}: {self.trigger_type}>"


class JourneyStep(Base):
    """
    Individual step in a journey.

    Steps are executed in order, each performing one or more actions.
    """

    __tablename__ = "journey_steps"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    journey_id = Column(
        String(36),
        ForeignKey("journeys.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(100), nullable=False)
    order = Column(Integer, nullable=False)  # Execution order within journey
    action_type = Column(String(50), nullable=False)
    action_config = Column(
        JSON, nullable=False, default=dict
    )  # Action-specific parameters
    delay_minutes = Column(Integer, nullable=False, default=0)  # Delay before executing
    condition = Column(JSON, nullable=True)  # Optional conditional logic
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    journey = relationship("Journey", back_populates="steps")
    executions = relationship(
        "StepExecution", back_populates="step", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_journey_steps_journey_order", "journey_id", "order"),)

    def __repr__(self):
        return f"<JourneyStep {self.name} ({self.action_type}) order={self.order}>"


class UserJourney(Base):
    """
    Tracks a user's progress through a journey.

    One record per user per journey.
    """

    __tablename__ = "user_journeys"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    journey_id = Column(
        String(36),
        ForeignKey("journeys.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status = Column(
        String(20), nullable=False, default="active"
    )  # active, completed, failed, paused
    current_step_id = Column(
        String(36), ForeignKey("journey_steps.id", ondelete="SET NULL"), nullable=True
    )
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    completed_at = Column(DateTime, nullable=True)
    failed_at = Column(DateTime, nullable=True)
    failure_reason = Column(Text, nullable=True)
    journey_metadata = Column(
        "metadata", JSON, nullable=False, default=dict
    )  # Journey-specific context
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    journey = relationship("Journey", back_populates="user_journeys")
    executions = relationship(
        "StepExecution", back_populates="user_journey", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_user_journeys_user_journey", "user_id", "journey_id", unique=True),
        Index("ix_user_journeys_status_started", "status", "started_at"),
    )

    def __repr__(self):
        return f"<UserJourney user={self.user_id} journey={self.journey_id} status={self.status}>"


class StepExecution(Base):
    """
    Log of step execution attempts.

    Tracks when steps fire, their results, and any errors.
    """

    __tablename__ = "step_executions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_journey_id = Column(
        String(36),
        ForeignKey("user_journeys.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_id = Column(
        String(36),
        ForeignKey("journey_steps.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status = Column(
        String(20), nullable=False, default="pending"
    )  # pending, success, failed, skipped
    executed_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    completed_at = Column(DateTime, nullable=True)
    result = Column(JSON, nullable=True)  # Action-specific result data
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    user_journey = relationship("UserJourney", back_populates="executions")
    step = relationship("JourneyStep", back_populates="executions")

    __table_args__ = (
        Index("ix_step_executions_status_executed", "status", "executed_at"),
        Index("ix_step_executions_user_journey_step", "user_journey_id", "step_id"),
    )

    def __repr__(self):
        return f"<StepExecution step={self.step_id} status={self.status}>"
