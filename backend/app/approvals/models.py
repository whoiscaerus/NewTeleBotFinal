"""Approvals database models."""

from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.db import Base

if TYPE_CHECKING:
    from backend.app.ea.models import Execution


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
        client_id: Client ID (for fast filtering by device polling)
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
    client_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        index=True,
        doc="Client ID (denormalized for fast device polling queries). TODO: Determine source and make NOT NULL.",
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
    )
    decision: Mapped[int | None] = mapped_column(
        nullable=True,
        doc="1=approved, 0=rejected, NULL=pending",
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
    approval_token: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        doc="Short-lived JWT token for approval action (mini app)",
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        doc="Token expiry timestamp",
    )

    # Relationships
    executions: Mapped[list["Execution"]] = relationship(
        "Execution",
        back_populates="approval",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("signal_id", "user_id", name="uq_approval_signal_user"),
        Index("ix_approval_client_created", "client_id", "created_at"),
        Index("ix_approval_client_decision", "client_id", "decision"),
        Index("ix_approval_user_created", "user_id", "created_at"),
        Index("ix_approval_signal_user", "signal_id", "user_id"),
    )

    def is_approved(self) -> bool:
        """Check if signal was approved."""
        return self.decision == ApprovalDecision.APPROVED.value

    def is_token_valid(self) -> bool:
        """Check if approval token is still valid.

        Returns:
            bool: True if token exists and hasn't expired
        """
        if not self.expires_at:
            return False
        return datetime.now(UTC) < self.expires_at
