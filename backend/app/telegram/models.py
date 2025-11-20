"""Telegram webhook models for event tracking and command registry."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from backend.app.core.db import Base


class TelegramWebhook(Base):
    """Telegram webhook event log.

    Tracks all incoming Telegram webhook events for audit and debugging.
    Uses message_id as unique key for idempotency.
    """

    __tablename__ = "telegram_webhooks"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), nullable=True)
    message_id = Column(Integer, nullable=False)
    chat_id = Column(Integer, nullable=False)
    command = Column(String(32), nullable=True)
    text = Column(Text, nullable=True)
    status = Column(
        Integer, nullable=False, default=0
    )  # 0=new, 1=processing, 2=success, 3=error
    error_message = Column(String(255), nullable=True)
    handler_response_time_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_webhooks_user_created", "user_id", "created_at"),
        Index("ix_webhooks_message_id", "message_id", unique=True),
        Index("ix_webhooks_command", "command"),
    )

    def __repr__(self) -> str:
        return f"<TelegramWebhook {self.id}: {self.command} from {self.user_id}>"


class TelegramCommand(Base):
    """Telegram command registry and metadata.

    Stores available commands, categories, and permissions.
    """

    __tablename__ = "telegram_commands"

    id = Column(String(36), primary_key=True)
    command = Column(String(32), nullable=False, unique=True)
    category = Column(
        String(32), nullable=False
    )  # 'billing', 'signals', 'help', 'affiliate'
    description = Column(String(255), nullable=True)
    requires_auth = Column(Integer, nullable=False, default=1)
    requires_premium = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_commands_command", "command"),
        Index("ix_commands_category", "category"),
    )

    def __repr__(self) -> str:
        return f"<TelegramCommand /{self.command}: {self.description}>"


class TelegramUser(Base):
    """Telegram user account and permissions.

    Stores Telegram user profiles with role-based access control.
    Role levels: 0=PUBLIC, 1=SUBSCRIBER, 2=ADMIN, 3=OWNER
    """

    __tablename__ = "telegram_users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    telegram_id = Column(String(36), unique=True, nullable=True)
    telegram_username = Column(String(32), nullable=True)
    telegram_first_name = Column(String(64), nullable=True)
    telegram_last_name = Column(String(64), nullable=True)
    role = Column(
        Integer, nullable=False, default=0
    )  # 0=PUBLIC, 1=SUBSCRIBER, 2=ADMIN, 3=OWNER
    is_active = Column(Boolean, nullable=False, default=True)
    preferences = Column(Text, nullable=True)  # JSON-encoded user preferences
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    guide_collections = relationship(
        "TelegramUserGuideCollection",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<TelegramUser {self.id}: @{self.telegram_username} (role={self.role})>"


class TelegramGuide(Base):
    """Educational guide content for delivery via Telegram.

    Stores tutorial/guide content with metadata for discovery and tracking.
    """

    __tablename__ = "telegram_guides"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    content_url = Column(String(512), nullable=False)  # Telegraph/external link
    category = Column(
        String(32), nullable=False
    )  # 'trading', 'technical', 'risk', 'psychology', 'automation', 'platform'
    tags = Column(Text, nullable=True)  # comma-separated tags
    difficulty_level = Column(
        Integer, nullable=False, default=0
    )  # 0=beginner, 1=intermediate, 2=advanced
    views_count = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    collections = relationship(
        "TelegramUserGuideCollection",
        back_populates="guide",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_guides_title", "title"),
        Index("ix_guides_category", "category"),
        Index("ix_guides_difficulty", "difficulty_level"),
        Index("ix_guides_created", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<TelegramGuide {self.id}: {self.title} ({self.category})>"


class TelegramBroadcast(Base):
    """Marketing broadcast messages for scheduled distribution.

    Stores campaign messages with scheduling and delivery tracking.
    """

    __tablename__ = "telegram_broadcasts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    title = Column(String(255), nullable=False)
    message_text = Column(Text, nullable=False)
    message_type = Column(
        String(32), nullable=False, default="text"
    )  # 'text', 'photo', 'video'
    target_audience = Column(
        String(32), nullable=False, default="all"
    )  # 'all', 'subscriber', 'admin'
    status = Column(
        Integer, nullable=False, default=0
    )  # 0=draft, 1=scheduled, 2=sent, 3=failed
    scheduled_at = Column(DateTime, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    recipients_count = Column(Integer, nullable=False, default=0)
    failed_count = Column(Integer, nullable=False, default=0)
    created_by_id = Column(String(36), nullable=True)  # Admin who created it
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        Index("ix_broadcasts_status", "status"),
        Index("ix_broadcasts_scheduled", "scheduled_at"),
        Index("ix_broadcasts_created", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<TelegramBroadcast {self.id}: {self.title} (status={self.status})>"


class TelegramUserGuideCollection(Base):
    """User's saved/bookmarked guides.

    Tracks which guides users have saved for later reference.
    """

    __tablename__ = "telegram_user_guide_collections"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(36), ForeignKey("telegram_users.id"), nullable=False)
    guide_id = Column(String(36), ForeignKey("telegram_guides.id"), nullable=False)
    is_read = Column(Boolean, nullable=False, default=False)
    times_viewed = Column(Integer, nullable=False, default=0)
    last_viewed_at = Column(DateTime, nullable=True)
    saved_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    user = relationship(
        "TelegramUser", back_populates="guide_collections", lazy="selectin"
    )
    guide = relationship("TelegramGuide", back_populates="collections", lazy="selectin")

    __table_args__ = (
        Index("ix_collection_user", "user_id"),
        Index("ix_collection_guide", "guide_id"),
        Index("ix_collection_user_guide", "user_id", "guide_id", unique=True),
        Index("ix_collection_saved", "saved_at"),
    )

    def __repr__(self) -> str:
        return f"<TelegramUserGuideCollection {self.id}: user={self.user_id} guide={self.guide_id}>"


class DistributionAuditLog(Base):
    """Audit log for content distributions (PR-030).

    Tracks all content distributions to Telegram groups, including:
    - Keywords used
    - Groups targeted
    - Success/failure counts
    - Detailed results per keyword and group
    """

    __tablename__ = "distribution_audit_log"

    id = Column(String(36), primary_key=True)
    keywords = Column(
        JSON, nullable=False, comment="List of keywords used for distribution"
    )
    matched_groups = Column(
        JSON, nullable=False, comment="Mapping of keywords to group IDs"
    )
    messages_sent = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Count of successfully sent messages",
    )
    messages_failed = Column(
        Integer, nullable=False, default=0, comment="Count of failed sends"
    )
    results = Column(JSON, nullable=False, comment="Detailed results per keyword")
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        comment="Timestamp of distribution",
    )

    __table_args__ = (
        Index("ix_distribution_audit_log_created_at", "created_at"),
        Index("ix_distribution_audit_log_keywords", "keywords"),
    )

    def __repr__(self) -> str:
        return f"<DistributionAuditLog {self.id}: {self.messages_sent} sent, {self.messages_failed} failed>"


class GuideScheduleLog(Base):
    """Audit log for scheduled guide posts (PR-031).

    Tracks all scheduled guide postings to Telegram groups, including:
    - Which guide was posted
    - How many groups successfully received it
    - How many posts failed
    - Timestamps and error information
    """

    __tablename__ = "guide_schedule_log"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    guide_id = Column(
        String(36),
        nullable=False,
        comment="ID of the guide that was posted",
    )
    posted_to = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of groups successfully posted to",
    )
    failed = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of groups where post failed",
    )
    posted_to_chats = Column(
        JSON,
        nullable=True,
        comment="List of chat IDs that successfully received the guide",
    )
    failed_chats = Column(
        JSON,
        nullable=True,
        comment="List of chat IDs where post failed",
    )
    error_details = Column(
        JSON,
        nullable=True,
        comment="Error messages and details for failed posts",
    )
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        comment="Timestamp of scheduled posting",
    )

    __table_args__ = (
        Index("ix_guide_schedule_log_created_at", "created_at"),
        Index("ix_guide_schedule_log_guide_id", "guide_id"),
    )

    def __repr__(self) -> str:
        return f"<GuideScheduleLog {self.id}: guide={self.guide_id} posted={self.posted_to} failed={self.failed}>"
