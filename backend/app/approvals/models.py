"""Approval domain models."""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Index, SmallInteger, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.app.core.db import Base


class Approval(Base):
    """Approval of a trading signal.

    Represents a user's approval/rejection decision for a signal.
    Each signal can only be approved/rejected once per user (enforced by unique index).

    Attributes:
        id: Unique approval identifier (UUID)
        signal_id: Reference to signals.id (FK)
        user_id: User who made the decision
        device_id: Device used (optional, for future tracking)
        decision: 0=approved, 1=rejected
        consent_version: Version of consent text user accepted
        ip: IP address of requester
        ua: User agent string
        created_at: Timestamp of approval (UTC)
    """

    __tablename__ = "approvals"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    signal_id = Column(String(36), ForeignKey("signals.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), nullable=False)
    device_id = Column(String(36), nullable=True)
    decision = Column(SmallInteger, nullable=False)
    consent_version = Column(Text, nullable=False)
    ip = Column(String(45), nullable=True)
    ua = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    signal = relationship("Signal", back_populates="approvals")

    __table_args__ = (
        # Prevent duplicate approvals (same user can only approve each signal once)
        Index("ix_approvals_signal_user", "signal_id", "user_id", unique=True),
        # Query approvals by user and time
        Index("ix_approvals_user_created", "user_id", "created_at"),
    )

    def __repr__(self) -> str:
        """Return string representation."""
        decision_str = "approved" if self.decision == 0 else "rejected"
        return f"<Approval {self.id}: signal {self.signal_id} {decision_str}>"
