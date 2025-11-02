"""
PR-056: Revenue Models

Defines database models for revenue tracking and cohort analysis:
- RevenueSnapshot: Daily snapshot of MRR, ARR, churn
- SubscriptionCohort: Monthly cohort of subscribers
- CohortMetrics: Retention and ARPU metrics per cohort
"""

from datetime import datetime

from sqlalchemy import JSON, Column, Date, DateTime, Float, Index, Integer, String

from backend.app.core.db import Base


class RevenueSnapshot(Base):
    """Daily revenue snapshot for business metrics.

    Stores aggregated revenue data at daily level for MRR/ARR trend analysis.
    Recalculated daily via scheduled task.
    """

    __tablename__ = "revenue_snapshots"

    id = Column(
        String(36), primary_key=True, default=lambda: str(__import__("uuid").uuid4())
    )
    snapshot_date = Column(Date, nullable=False, index=True, unique=True)

    # MRR/ARR calculations
    mrr_gbp = Column(Float, nullable=False, default=0.0)  # Monthly recurring revenue
    arr_gbp = Column(Float, nullable=False, default=0.0)  # Annual recurring revenue

    # Active subscriptions
    active_subscribers = Column(Integer, nullable=False, default=0)
    annual_plan_subscribers = Column(Integer, nullable=False, default=0)
    monthly_plan_subscribers = Column(Integer, nullable=False, default=0)

    # Churn metrics
    churned_this_month = Column(Integer, nullable=False, default=0)
    churn_rate_percent = Column(Float, nullable=False, default=0.0)

    # ARPU
    arpu_gbp = Column(Float, nullable=False, default=0.0)  # Average revenue per user

    # Cohort data (JSON)
    cohorts_by_month = Column(
        JSON, nullable=True
    )  # {YYYY-MM: {retained: N, arpu: X, ...}}

    # Metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (Index("ix_revenue_snapshots_date", "snapshot_date"),)

    def __repr__(self):
        return f"<RevenueSnapshot {self.snapshot_date}: MRR £{self.mrr_gbp:.2f}, ARR £{self.arr_gbp:.2f}>"


class SubscriptionCohort(Base):
    """Monthly cohort of new subscribers.

    Used for tracking retention and ARPU trends over time.
    Each row represents all users who subscribed in a given month.
    """

    __tablename__ = "subscription_cohorts"

    id = Column(
        String(36), primary_key=True, default=lambda: str(__import__("uuid").uuid4())
    )
    cohort_month = Column(
        String(7), nullable=False, index=True, unique=True
    )  # YYYY-MM format

    # Initial cohort size
    initial_subscribers = Column(Integer, nullable=False, default=0)

    # Monthly retention tracking
    retention_data = Column(
        JSON, nullable=False, default=dict
    )  # {0: N, 1: N, 2: N, ...}

    # Metrics
    month_0_revenue_gbp = Column(
        Float, nullable=False, default=0.0
    )  # Revenue in month 0
    total_revenue_gbp = Column(Float, nullable=False, default=0.0)  # All time revenue
    average_lifetime_value_gbp = Column(
        Float, nullable=False, default=0.0
    )  # Average LTV

    # Churn tracking
    churn_rate_by_month = Column(
        JSON, nullable=False, default=dict
    )  # {0: %, 1: %, ...}

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (Index("ix_cohorts_month", "cohort_month"),)

    def __repr__(self):
        return f"<SubscriptionCohort {self.cohort_month}: {self.initial_subscribers} users>"
