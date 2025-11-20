"""Subscription models."""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import uuid4

from sqlalchemy import Column, DateTime, Numeric, String

from backend.app.core.db import Base


class SubscriptionTier(str, Enum):
    """Subscription tier levels."""

    FREE = "free"
    PREMIUM = "premium"
    PRO = "pro"


class Subscription(Base):
    """Subscription model."""

    __tablename__ = "subscriptions"
    __table_args__ = {"extend_existing": True}

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String, nullable=False)
    tier = Column(String, default="free")
    status = Column(String, default="active")
    stripe_subscription_id = Column(String)
    amount = Column(Numeric(10, 2), default=Decimal("0.00"))
    plan_id = Column(String, nullable=True)
    price_gbp = Column(Numeric(10, 2), default=Decimal("0.00"))
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
