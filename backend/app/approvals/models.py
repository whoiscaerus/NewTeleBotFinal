"""Approvals database models."""

from datetime import datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.db import Base


class ApprovalDecision(Enum):
    """User's decision on signal."""

    APPROVED = 1
    REJECTED = 0


class Approval(Base):
    """User approval record for signals.

    Represents the workflow: signal created → user reviews → approval/rejection.

    Fields:
        id: Unique approval ID
        signal_id: Associated signal (foreign key)
        user_id: User making decision
        decision: Approved (1) or rejected (0)
        consent_version: Version of consent text user agreed to
        reason: Optional reason for rejection
        created_at: Decision timestamp
    """

    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    signal_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("signals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
    )
    decision: Mapped[int] = mapped_column(
        nullable=False,
        doc="1=approved, 0=rejected",
    )
    consent_version: Mapped[int] = mapped_column(
        nullable=False,
        default=1,
        doc="Consent text version user agreed to",
    )
    reason: Mapped[str] = mapped_column(
        String(500),
        nullable=True,
        doc="Rejection reason",
    )
    ip: Mapped[str] = mapped_column(
        String(45),
        nullable=True,
        doc="Client IP address (IPv4 or IPv6)",
    )
    ua: Mapped[str] = mapped_column(
        String(500),
        nullable=True,
        doc="User-Agent header",
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=datetime.utcnow,
    )

    __table_args__ = (
        Index("ix_approval_user_created", "user_id", "created_at"),
        Index("ix_approval_signal_user", "signal_id", "user_id"),
    )

    def is_approved(self) -> bool:
        """Check if signal was approved."""
        return self.decision == ApprovalDecision.APPROVED.value
