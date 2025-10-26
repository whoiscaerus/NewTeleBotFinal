"""Stripe event models for tracking and idempotent processing."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Column, DateTime, Index, Integer, String, Text

from backend.app.core.db import Base


class StripeEvent(Base):
    """Track Stripe webhook events for idempotent processing.

    Prevents duplicate processing if webhooks are retried by Stripe.
    """

    __tablename__ = "stripe_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    event_id = Column(
        String(255), unique=True, nullable=False, index=True
    )  # Stripe event ID
    event_type = Column(
        String(100), nullable=False
    )  # charge.succeeded, charge.failed, etc
    payment_method = Column(String(50), nullable=False)  # 'stripe'
    customer_id = Column(String(255))  # Stripe customer ID
    amount_cents = Column(Integer)  # Amount in cents (nullable for refunds)
    currency = Column(String(3), nullable=False, default="USD")
    status = Column(
        Integer, nullable=False, default=0
    )  # 0=pending, 1=processed, 2=failed
    idempotency_key = Column(String(255), index=True)  # For idempotent retries
    processed_at = Column(DateTime)  # When successfully processed
    error_message = Column(Text)  # If status=failed, reason
    webhook_timestamp = Column(
        DateTime, default=datetime.utcnow
    )  # From Stripe event timestamp
    received_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Indexes for query optimization
    __table_args__ = (
        Index("ix_event_id", "event_id"),
        Index("ix_idempotency_key", "idempotency_key"),
        Index("ix_status_created", "status", "created_at"),
    )

    @property
    def is_processed(self) -> bool:
        """Check if event was successfully processed."""
        return bool(self.status == 1)

    @property
    def is_failed(self) -> bool:
        """Check if event processing failed."""
        return bool(self.status == 2)

    def __repr__(self) -> str:
        return f"<StripeEvent {self.id}: {self.event_type} {self.status}>"
