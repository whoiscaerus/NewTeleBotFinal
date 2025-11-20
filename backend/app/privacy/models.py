"""Privacy request models for GDPR-style compliance."""

from datetime import datetime
from enum import Enum

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import relationship

from backend.app.core.db import Base


class RequestType(str, Enum):
    """Privacy request types."""

    EXPORT = "export"
    DELETE = "delete"


class RequestStatus(str, Enum):
    """Privacy request status."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ON_HOLD = "on_hold"


class PrivacyRequest(Base):
    """
    Privacy request model for data export and deletion.

    Supports GDPR-style data subject access requests (DSAR) including:
    - Data export (JSON/CSV bundle)
    - Data deletion with cooling-off period
    - Admin hold override for active disputes

    Attributes:
        id: Unique request identifier
        user_id: User making the request
        request_type: export or delete
        status: Current request status
        created_at: When request was submitted
        processed_at: When request was completed
        scheduled_deletion_at: When deletion will execute (delete requests only)
        request_metadata: Additional request context (reason, admin notes, etc.)
        export_url: S3/storage URL for export bundle (export requests only)
        export_expires_at: When export bundle expires
        hold_reason: Reason for admin hold (if on_hold status)
        hold_by: Admin user who placed hold
    """

    __tablename__ = "privacy_requests"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    request_type = Column(String(20), nullable=False)  # export, delete
    status = Column(
        String(20), nullable=False, default="pending", index=True
    )  # pending, processing, completed, failed, cancelled, on_hold

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)
    scheduled_deletion_at = Column(
        DateTime, nullable=True
    )  # For delete requests: when deletion will execute

    request_metadata = Column(
        JSON, nullable=False, default=dict
    )  # reason, admin notes, etc.

    # Export-specific fields
    export_url = Column(String(500), nullable=True)  # S3/storage URL
    export_expires_at = Column(DateTime, nullable=True)

    # Hold-specific fields (for active disputes/chargebacks)
    hold_reason = Column(String(500), nullable=True)
    hold_by = Column(String(36), nullable=True)  # Admin user ID
    hold_at = Column(DateTime, nullable=True)

    # Relationships
    user = relationship("User", back_populates="privacy_requests")

    # Indexes
    __table_args__ = (
        Index("ix_privacy_requests_user_type", "user_id", "request_type"),
        Index("ix_privacy_requests_status_created", "status", "created_at"),
        Index("ix_privacy_requests_scheduled_deletion", "scheduled_deletion_at"),
    )

    def __repr__(self):
        return f"<PrivacyRequest {self.id}: {self.request_type} for user {self.user_id}, status={self.status}>"

    @property
    def is_deletable(self) -> bool:
        """Check if request can be deleted (cooling-off period passed)."""
        if self.request_type != RequestType.DELETE:
            return False
        if self.status != RequestStatus.PENDING:
            return False
        if not self.scheduled_deletion_at:
            return False
        return bool(datetime.utcnow() >= self.scheduled_deletion_at)

    @property
    def cooling_off_hours_remaining(self) -> int | None:
        """Calculate remaining cooling-off hours for delete requests."""
        if self.request_type != RequestType.DELETE or not self.scheduled_deletion_at:
            return None
        remaining = self.scheduled_deletion_at - datetime.utcnow()
        if remaining.total_seconds() <= 0:
            return 0
        return int(remaining.total_seconds() / 3600)

    @property
    def export_url_valid(self) -> bool:
        """Check if export URL is still valid."""
        if not self.export_url or not self.export_expires_at:
            return False
        return bool(datetime.utcnow() < self.export_expires_at)

    def place_hold(self, reason: str, admin_user_id: str) -> None:
        """
        Place admin hold on request (prevents deletion).

        Args:
            reason: Reason for hold (e.g., "Active chargeback dispute")
            admin_user_id: ID of admin placing hold
        """
        self.status = RequestStatus.ON_HOLD  # type: ignore[assignment]
        self.hold_reason = reason  # type: ignore[assignment]
        self.hold_by = admin_user_id  # type: ignore[assignment]
        self.hold_at = datetime.utcnow()  # type: ignore[assignment]

    def release_hold(self) -> None:
        """Release admin hold and return to pending status."""
        if self.status == RequestStatus.ON_HOLD:
            self.status = RequestStatus.PENDING  # type: ignore[assignment]
            # Keep hold metadata for audit trail but don't clear it
