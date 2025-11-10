"""Quota management models.

Defines quota limits per subscription tier and tracks usage counters.
Quotas protect system resources by limiting per-feature usage (signals/day, alerts, exports).
"""

from datetime import datetime
from enum import Enum

from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint

from backend.app.core.db import Base


class QuotaType(str, Enum):
    """Quota type enumeration."""

    SIGNALS_PER_DAY = "signals_per_day"
    ALERTS_PER_DAY = "alerts_per_day"
    EXPORTS_PER_MONTH = "exports_per_month"
    API_CALLS_PER_MINUTE = "api_calls_per_minute"
    BACKTESTS_PER_DAY = "backtests_per_day"
    STRATEGIES_MAX = "strategies_max"


class QuotaPeriod(str, Enum):
    """Quota reset period."""

    MINUTE = "minute"
    HOUR = "hour"
    DAY = "day"
    MONTH = "month"
    NONE = "none"  # No reset (lifetime limit)


class QuotaDefinition(Base):
    """Quota definition by subscription tier.

    Defines quota limits for each feature per subscription plan.
    Example: Free tier = 10 signals/day, Premium = 100 signals/day.
    """

    __tablename__ = "quota_definitions"

    id = Column(String(36), primary_key=True)
    tier = Column(String(20), nullable=False)  # free, premium, pro
    quota_type = Column(String(50), nullable=False)  # signals_per_day, etc.
    limit = Column(Integer, nullable=False)  # Maximum allowed
    period = Column(String(20), nullable=False)  # day, month, none
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        UniqueConstraint("tier", "quota_type", name="uq_quota_definition_tier_type"),
    )

    def __repr__(self) -> str:
        """String representation."""
        return f"<QuotaDefinition {self.tier}:{self.quota_type} limit={self.limit}/{self.period}>"


class QuotaUsage(Base):
    """Quota usage tracking per user.

    Tracks current usage against quota limits.
    Usage counters are periodically reset based on quota period.
    Redis is primary storage (fast), this is backup/audit trail.
    """

    __tablename__ = "quota_usage"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), nullable=False, index=True)
    quota_type = Column(String(50), nullable=False, index=True)
    count = Column(Integer, nullable=False, default=0)  # Current usage
    period_start = Column(DateTime, nullable=False)  # When this period started
    period_end = Column(DateTime, nullable=False)  # When this period ends
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id", "quota_type", "period_start", name="uq_quota_usage_user_type"
        ),
    )

    def __repr__(self) -> str:
        """String representation."""
        return f"<QuotaUsage user={self.user_id} {self.quota_type} count={self.count}>"
