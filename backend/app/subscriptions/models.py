"""Subscription models."""

from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import Column, DateTime, Numeric, String
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class SubscriptionTier(str, Enum):
    """Subscription tier levels."""

    FREE = "free"
    PREMIUM = "premium"
    PRO = "pro"


class Subscription(Base):
    """Subscription model."""

    __tablename__ = "subscriptions"

    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False)
    tier = Column(String, default="free")
    status = Column(String, default="active")
    stripe_subscription_id = Column(String)
    amount = Column(Numeric(10, 2), default=Decimal("0.00"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
