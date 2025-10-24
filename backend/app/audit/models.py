"""Audit logging models and service for immutable event trails."""

from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Index, String
from sqlalchemy.dialects.postgresql import JSON

from backend.app.core.db import Base


class AuditLog(Base):
    """Immutable audit log for sensitive operations.

    All columns are set at creation; no updates allowed.
    Used for compliance, security investigation, and system monitoring.
    """

    __tablename__ = "audit_logs"

    # Primary key
    id = Column(
        String(36), primary_key=True, default=lambda: str(__import__("uuid").uuid4())
    )

    # Timing
    timestamp = Column(
        DateTime, nullable=False, default=lambda: datetime.now(UTC), index=True
    )

    # Actor (who performed the action)
    actor_id = Column(String(36), nullable=True, index=True)  # None for system actions
    actor_role = Column(String(20), nullable=False)  # OWNER, ADMIN, USER, SYSTEM

    # Action (what happened)
    action = Column(
        String(50), nullable=False, index=True
    )  # e.g., "auth.login", "user.create"
    target = Column(
        String(50), nullable=False, index=True
    )  # Resource type: "user", "signal", "payment"
    target_id = Column(String(36), nullable=True, index=True)  # Resource ID

    # Details
    meta = Column(JSON, nullable=True)  # Structured data (no PII, no secrets)

    # Network
    ip_address = Column(String(45), nullable=True)  # IPv4 or IPv6
    user_agent = Column(String(255), nullable=True)

    # Status
    status = Column(
        String(20), nullable=False, default="success"
    )  # success, failure, error

    # Indexes for common queries
    __table_args__ = (
        Index("ix_audit_actor_time", "actor_id", "timestamp"),
        Index("ix_audit_action_time", "action", "timestamp"),
        Index("ix_audit_target_time", "target", "target_id", "timestamp"),
        Index("ix_audit_status_time", "status", "timestamp"),
    )

    def __repr__(self):
        return (
            f"<AuditLog {self.id}: {self.action} on {self.target} by {self.actor_id}>"
        )


# Predefined audit actions
AUDIT_ACTIONS = {
    # Authentication
    "auth.login": "User login (success or failure)",
    "auth.logout": "User logout",
    "auth.register": "New user registration",
    "auth.password_change": "User password changed",
    "auth.mfa_enable": "Multi-factor authentication enabled",
    "auth.mfa_disable": "Multi-factor authentication disabled",
    # User management
    "user.create": "User created",
    "user.update": "User updated",
    "user.delete": "User deleted",
    "user.role_change": "User role changed",
    "user.activate": "User account activated",
    "user.deactivate": "User account deactivated",
    # Billing
    "billing.checkout": "Checkout initiated",
    "billing.payment": "Payment processed",
    "billing.refund": "Refund issued",
    "billing.subscription_change": "Subscription changed",
    "billing.webhook": "External webhook received",
    # Trading signals (domain-specific, added later)
    "signal.create": "Signal created",
    "signal.approve": "Signal approved",
    "signal.reject": "Signal rejected",
    "signal.execute": "Signal executed",
    # Admin operations
    "admin.config_change": "Configuration changed",
    "admin.api_key_create": "API key created",
    "admin.api_key_revoke": "API key revoked",
    "admin.user_ban": "User banned",
    "admin.audit_export": "Audit logs exported",
    # Device management
    "device.register": "Device registered",
    "device.revoke": "Device revoked",
    "device.trust": "Device marked as trusted",
}
