"""Billing models for subscriptions and payments.

Tracks user subscription status, plan details, and payment history.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.db import Base


class Plan(Base):
    """Billing plan definition."""

    __tablename__ = "plans"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    price_gbp: Mapped[float] = mapped_column(Float, nullable=False)
    billing_period: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # "monthly" or "annual"
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    def __repr__(self):
        return f"<Plan {self.name}: £{self.price_gbp} {self.billing_period}>"


class SubscriptionStatus(str, Enum):
    """Subscription status states."""

    ACTIVE = "active"
    CANCELED = "canceled"
    PAST_DUE = "past_due"


class Subscription(Base):
    """User subscription record."""

    __tablename__ = "subscriptions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    plan_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    price_gbp: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=SubscriptionStatus.ACTIVE.value
    )
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __repr__(self):
        return f"<Subscription {self.user_id}: £{self.price_gbp} - {self.status}>"
