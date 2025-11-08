"""Support ticket models for human escalation system."""

from datetime import datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import relationship

from backend.app.core.db import Base


class TicketSeverity(str, Enum):
    """Ticket severity levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class TicketStatus(str, Enum):
    """Ticket status states."""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    WAITING = "waiting_on_customer"
    RESOLVED = "resolved"
    CLOSED = "closed"


class TicketChannel(str, Enum):
    """Channel where ticket originated."""

    AI_CHAT = "ai_chat"
    WEB = "web"
    TELEGRAM = "telegram"
    EMAIL = "email"
    API = "api"


class Ticket(Base):
    """Support ticket for human escalation.

    Represents a support ticket created when AI cannot solve a user's issue,
    or when a user explicitly requests human support. Tickets can be triaged,
    assigned, and resolved by support staff.

    Attributes:
        id: Unique ticket identifier (UUID)
        user_id: User who created the ticket (foreign key to users.id)
        subject: Brief ticket summary (max 200 chars)
        body: Detailed description of the issue
        severity: Urgency level (low, medium, high, urgent)
        status: Current ticket state (open, in_progress, waiting, resolved, closed)
        channel: Origin channel (ai_chat, web, telegram, email, api)
        context: JSON metadata (session_id, previous_messages, etc.)
        created_at: Ticket creation timestamp
        updated_at: Last modification timestamp
        resolved_at: When ticket was marked resolved
        closed_at: When ticket was closed
        assigned_to: Admin/owner user_id assigned to handle ticket
        resolution_note: Final resolution summary (visible to user)
        internal_notes: Internal staff notes (not visible to user)
    """

    __tablename__ = "tickets"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    subject = Column(String(200), nullable=False)
    body = Column(Text, nullable=False)
    severity = Column(String(20), nullable=False, default="medium", index=True)
    status = Column(String(30), nullable=False, default="open", index=True)
    channel = Column(String(20), nullable=False, default="web")
    context = Column(JSON, nullable=True)  # {session_id, escalation_reason, metadata}

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    resolved_at = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)

    assigned_to = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    resolution_note = Column(Text, nullable=True)
    internal_notes = Column(Text, nullable=True)

    # Relationships
    user = relationship("User", foreign_keys=[user_id], backref="tickets")
    assignee = relationship("User", foreign_keys=[assigned_to])

    # Indexes for common queries
    __table_args__ = (
        Index("ix_tickets_status_severity", "status", "severity"),
        Index("ix_tickets_user_status", "user_id", "status"),
        Index("ix_tickets_assignee_status", "assigned_to", "status"),
        Index("ix_tickets_created_status", "created_at", "status"),
    )

    def __repr__(self):
        return f"<Ticket {self.id}: {self.subject[:30]}... [{self.status}]>"
