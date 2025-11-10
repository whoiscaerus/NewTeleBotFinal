"""
PR-098: CRM Models

Defines playbook executions, triggers, and user CRM state tracking.
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Index, Integer, String, Text

from backend.app.core.db import Base


class CRMPlaybookExecution(Base):
    """Tracks execution of CRM playbooks for users.

    A playbook is a predefined sequence of actions triggered by lifecycle events.

    Example:
        - Payment failed → 3-step rescue sequence:
          1. Immediate email with payment update link
          2. 24h later: Telegram DM with discount code
          3. 48h later: Owner personal outreach DM

    Business Logic:
        - One active execution per user per playbook type
        - status=active: In progress, steps remaining
        - status=completed: All steps executed successfully
        - status=abandoned: User took action (e.g., payment recovered)
        - status=failed: Technical failure (e.g., send error after retries)
    """

    __tablename__ = "crm_playbook_executions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )  # Who this playbook is for
    playbook_name = Column(
        String(100), nullable=False, index=True
    )  # e.g., "payment_failed_rescue"
    trigger_event = Column(String(100), nullable=False)  # e.g., "payment_failed"
    context = Column(JSON, nullable=False)  # Event data (amount, subscription_id, etc.)

    # Execution state
    status = Column(
        String(50), nullable=False, default="active", index=True
    )  # active, completed, abandoned, failed
    current_step = Column(Integer, nullable=False, default=0)  # 0-indexed step number
    total_steps = Column(Integer, nullable=False)  # How many steps in playbook
    next_action_at = Column(
        DateTime, nullable=True, index=True
    )  # When next step should run

    # Outcomes
    converted_at = Column(
        DateTime, nullable=True
    )  # If user took desired action (e.g., updated payment)
    conversion_value = Column(Integer, nullable=True)  # E.g., £20 if plan renewed

    # Metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    completed_at = Column(DateTime, nullable=True)

    # Indexes for common queries
    __table_args__ = (
        Index("ix_crm_executions_user_status", "user_id", "status"),
        Index("ix_crm_executions_next_action", "next_action_at"),
        Index("ix_crm_executions_playbook", "playbook_name", "status"),
    )

    def __repr__(self):
        return f"<CRMPlaybookExecution {self.id}: {self.playbook_name} for {self.user_id} @ step {self.current_step}/{self.total_steps}>"


class CRMStepExecution(Base):
    """Tracks individual step executions within a playbook.

    Each playbook consists of multiple steps (e.g., email, wait 24h, DM, wait 48h, call).
    This model logs each step's outcome for analytics and debugging.
    """

    __tablename__ = "crm_step_executions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    execution_id = Column(
        String(36),
        ForeignKey("crm_playbook_executions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_number = Column(Integer, nullable=False)  # 0-indexed
    step_type = Column(
        String(50), nullable=False
    )  # "send_message", "discount_code", "owner_dm", "wait"

    # Step config (from playbook definition)
    config = Column(
        JSON, nullable=False
    )  # {"channel": "telegram", "template": "rescue_step2", ...}

    # Execution result
    status = Column(
        String(50), nullable=False, default="pending"
    )  # pending, skipped, completed, failed
    executed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)  # If failed, why

    # Message delivery tracking (if step_type=send_message)
    message_id = Column(String(36), nullable=True)  # Links to messaging bus message
    delivered_at = Column(DateTime, nullable=True)
    opened_at = Column(DateTime, nullable=True)  # If email/push and tracking enabled
    clicked_at = Column(DateTime, nullable=True)  # If CTA link clicked

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_crm_steps_execution", "execution_id", "step_number"),
        Index("ix_crm_steps_status", "status", "executed_at"),
    )

    def __repr__(self):
        return f"<CRMStepExecution {self.id}: step {self.step_number} ({self.step_type}) - {self.status}>"


class CRMDiscountCode(Base):
    """Tracks one-time discount codes issued by CRM playbooks.

    Business Logic:
        - One code per user per playbook execution
        - expires_at: Code valid for limited time (e.g., 7 days)
        - used_at: When user redeemed code
        - percent_off: Discount % (e.g., 20 = 20% off)
    """

    __tablename__ = "crm_discount_codes"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    code = Column(
        String(50), nullable=False, unique=True, index=True
    )  # e.g., "RESCUE20-ABC123"
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    execution_id = Column(
        String(36),
        ForeignKey("crm_playbook_executions.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Discount details
    percent_off = Column(Integer, nullable=False)  # 0-100
    max_uses = Column(Integer, nullable=False, default=1)
    used_count = Column(Integer, nullable=False, default=0)

    # Validity
    expires_at = Column(DateTime, nullable=False, index=True)
    used_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_crm_codes_user", "user_id", "expires_at"),
        Index("ix_crm_codes_validity", "expires_at", "used_count"),
    )

    def __repr__(self):
        return f"<CRMDiscountCode {self.code}: {self.percent_off}% off, expires {self.expires_at}>"
