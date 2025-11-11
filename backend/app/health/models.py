"""
Health Monitoring Models - PR-100

Database models for autonomous health monitoring system.
"""

import enum
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from backend.app.core.db import Base


class IncidentStatus(str, enum.Enum):
    """Incident lifecycle states."""

    OPEN = "open"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
    CLOSED = "closed"


class IncidentSeverity(str, enum.Enum):
    """Incident severity levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SyntheticStatus(str, enum.Enum):
    """Synthetic check result states."""

    PASS = "pass"
    FAIL = "fail"
    TIMEOUT = "timeout"
    ERROR = "error"


class RemediationStatus(str, enum.Enum):
    """Remediation action states."""

    PENDING = "pending"
    EXECUTING = "executing"
    SUCCESS = "success"
    FAILED = "failed"


class Incident(Base):
    """
    Incident tracking for system health issues.

    Represents a detected problem requiring investigation/remediation.
    State machine: open → investigating → resolved → closed
    """

    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(
        String(50), nullable=False, index=True
    )  # websocket_down, mt5_unreachable, etc.
    severity = Column(
        Enum(IncidentSeverity), nullable=False, default=IncidentSeverity.MEDIUM
    )
    status = Column(
        Enum(IncidentStatus), nullable=False, default=IncidentStatus.OPEN, index=True
    )
    opened_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    owner_notified = Column(Integer, nullable=False, default=0)  # 0=no, 1=yes

    # Relationships
    synthetic_checks = relationship("SyntheticCheck", back_populates="incident")
    remediation_actions = relationship("RemediationAction", back_populates="incident")

    # Indexes for common queries
    __table_args__ = (
        Index("ix_incidents_status_severity", "status", "severity"),
        Index("ix_incidents_opened_at", "opened_at"),
    )

    def __repr__(self):
        return f"<Incident {self.id}: {self.type} [{self.status}]>"

    def can_transition_to(self, new_status: IncidentStatus) -> bool:
        """
        Validate state machine transitions.

        Valid transitions:
        - open → investigating
        - investigating → resolved
        - resolved → closed
        - any → open (reopen)
        """
        if new_status == IncidentStatus.OPEN:
            return True  # Allow reopening from any state

        valid_transitions = {
            IncidentStatus.OPEN: [IncidentStatus.INVESTIGATING],
            IncidentStatus.INVESTIGATING: [IncidentStatus.RESOLVED],
            IncidentStatus.RESOLVED: [IncidentStatus.CLOSED],
            IncidentStatus.CLOSED: [],  # Terminal state (except reopen)
        }

        return new_status in valid_transitions.get(self.status, [])


class SyntheticCheck(Base):
    """
    Results from synthetic monitoring probes.

    Records outcomes of automated health checks against system endpoints.
    """

    __tablename__ = "synthetic_checks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    probe_name = Column(
        String(50), nullable=False, index=True
    )  # websocket_ping, mt5_poll, etc.
    status = Column(Enum(SyntheticStatus), nullable=False, index=True)
    latency_ms = Column(Float, nullable=True)  # Response time in milliseconds
    checked_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    error_message = Column(Text, nullable=True)
    incident_id = Column(Integer, ForeignKey("incidents.id"), nullable=True)

    # Relationships
    incident = relationship("Incident", back_populates="synthetic_checks")

    # Indexes for common queries
    __table_args__ = (
        Index("ix_synthetic_checks_probe_status", "probe_name", "status"),
        Index("ix_synthetic_checks_checked_at", "checked_at"),
    )

    def __repr__(self):
        return f"<SyntheticCheck {self.probe_name}: {self.status} @ {self.checked_at}>"


class RemediationAction(Base):
    """
    Automated remediation actions taken to resolve incidents.

    Records self-healing operations executed by the system.
    """

    __tablename__ = "remediation_actions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    incident_id = Column(Integer, ForeignKey("incidents.id"), nullable=False)
    action_type = Column(
        String(50), nullable=False, index=True
    )  # restart_service, rotate_token, etc.
    status = Column(
        Enum(RemediationStatus), nullable=False, default=RemediationStatus.PENDING
    )
    executed_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    result = Column(Text, nullable=True)  # JSON result of the action
    error_message = Column(Text, nullable=True)

    # Relationships
    incident = relationship("Incident", back_populates="remediation_actions")

    # Indexes
    __table_args__ = (
        Index("ix_remediation_actions_incident_id", "incident_id"),
        Index("ix_remediation_actions_action_type", "action_type"),
    )

    def __repr__(self):
        return f"<RemediationAction {self.action_type}: {self.status}>"
