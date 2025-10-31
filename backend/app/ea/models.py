"""
Execution model for storing device execution results (PR-024a, PR-025).

This models stores outcomes from device acknowledgments:
- When an EA executes a signal, it acks with placed/failed status
- Stores broker ticket number and any error messages
- Links execution back to approval and device for audit trail
"""

import enum
from datetime import datetime
from uuid import uuid4

from sqlalchemy import Column, DateTime
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import relationship

from backend.app.core.db import Base


class ExecutionStatus(str, enum.Enum):
    """Execution status enumeration."""

    PLACED = "placed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class Execution(Base):
    """
    Device execution outcome.

    Records when a device acknowledges execution of an approved signal:
    - device_id: which device executed
    - approval_id: which signal was executed
    - status: placed, failed, cancelled, unknown
    - broker_ticket: order ticket from broker (if placed)
    - error: error message if failed
    """

    __tablename__ = "executions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    approval_id = Column(
        String(36), ForeignKey("approvals.id"), nullable=False, index=True
    )
    device_id = Column(String(36), ForeignKey("devices.id"), nullable=False, index=True)
    status = Column(
        SQLEnum(ExecutionStatus),
        nullable=False,
        default=ExecutionStatus.UNKNOWN,
        index=True,
    )
    broker_ticket = Column(
        String(128), nullable=True, index=True
    )  # Broker order ID if placed
    error = Column(Text, nullable=True)  # Error message if failed
    created_at = Column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, index=True
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # Relationships
    approval = relationship("Approval", back_populates="executions")
    device = relationship("Device", back_populates="executions")

    __table_args__ = (
        Index("ix_executions_approval_device", "approval_id", "device_id"),
        Index("ix_executions_status_created", "status", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Execution {self.id}: approval={self.approval_id}, device={self.device_id}, status={self.status}>"
