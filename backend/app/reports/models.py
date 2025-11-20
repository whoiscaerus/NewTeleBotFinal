"""
SQLAlchemy models for report storage (PR-101).

Report entity tracks generated reports with storage URLs and delivery status.
"""

import enum
from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, Column, DateTime, Enum, ForeignKey, Index, String, Text
from sqlalchemy.orm import relationship

from backend.app.core.db import Base


class ReportType(str, enum.Enum):
    """Report type: client account summary or owner business summary."""

    CLIENT = "client"
    OWNER = "owner"


class ReportPeriod(str, enum.Enum):
    """Report period: daily, weekly, or monthly."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class ReportStatus(str, enum.Enum):
    """Report generation status."""

    PENDING = "pending"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


class Report(Base):
    """
    Generated report entity (PR-101).

    Tracks AI-generated narrative reports for clients and owners.
    Stores HTML/PDF URLs, delivery status, and metadata.

    Example:
        >>> report = Report(
        ...     type=ReportType.CLIENT,
        ...     period=ReportPeriod.WEEKLY,
        ...     user_id="user_123"
        ... )
        >>> db.add(report)
        >>> await db.commit()
    """

    __tablename__ = "reports"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    type: Column[ReportType] = Column(Enum(ReportType), nullable=False, index=True)
    period: Column[ReportPeriod] = Column(Enum(ReportPeriod), nullable=False)
    status: Column[ReportStatus] = Column(
        Enum(ReportStatus), nullable=False, default=ReportStatus.PENDING, index=True
    )

    # Scoping
    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )  # NULL for owner reports

    # Time range
    period_start = Column(DateTime, nullable=False, index=True)
    period_end = Column(DateTime, nullable=False)

    # Storage
    html_url = Column(Text, nullable=True)  # S3/local signed URL
    pdf_url = Column(Text, nullable=True)  # S3/local signed URL

    # Content metadata
    summary = Column(Text, nullable=True)  # Short narrative summary
    data = Column(JSON, nullable=False, default=dict)  # Report data payload

    # Delivery tracking
    delivered_channels = Column(
        JSON, nullable=False, default=list
    )  # ["email", "telegram"]
    delivery_failed_channels = Column(JSON, nullable=False, default=list)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    generated_at = Column(DateTime, nullable=True)  # When PDF generated
    error_message = Column(Text, nullable=True)

    # Relationships
    user = relationship("User", back_populates="reports")

    # Indexes
    __table_args__ = (
        Index("ix_reports_user_created", "user_id", "created_at"),
        Index("ix_reports_type_period_created", "type", "period", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Report {self.id}: {self.type} {self.period} {self.status}>"
