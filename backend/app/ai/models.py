"""
AI Models - Database models for chat sessions and messages.
"""

from datetime import datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from backend.app.core.db import Base


class ChatMessageRole(str, Enum):
    """Chat message sender role."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ChatSession(Base):
    """Chat session for a user."""

    __tablename__ = "ai_chat_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(255), nullable=False, default="Support Chat")
    escalated = Column(Boolean, nullable=False, default=False)
    escalated_to_human_at = Column(DateTime, nullable=True)
    escalation_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    closed_at = Column(DateTime, nullable=True)

    # Relationships
    messages = relationship(
        "ChatMessage", back_populates="session", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_ai_chat_sessions_user_created", "user_id", "created_at"),
    )

    def __repr__(self):
        return (
            f"<ChatSession {self.id}: user={self.user_id}, escalated={self.escalated}>"
        )


class ChatMessage(Base):
    """Individual message in a chat session."""

    __tablename__ = "ai_chat_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ai_chat_sessions.id"),
        nullable=False,
        index=True,
    )
    role: ChatMessageRole | None = Column(  # type: ignore[assignment]
        String(50), nullable=False
    )
    content = Column(Text, nullable=False)
    citations = Column(
        JSON, nullable=False, default=list
    )  # List of {article_id, title, url}
    blocked_by_policy = Column(
        String(255), nullable=True
    )  # If null, message was allowed
    confidence_score = Column(Float, nullable=True)  # 0-1, None if not applicable
    extra_data = Column(
        JSON, nullable=False, default=dict
    )  # Any extra data (avoid 'metadata' which is reserved)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    session = relationship("ChatSession", back_populates="messages")

    __table_args__ = (
        Index("ix_ai_chat_messages_session_created", "session_id", "created_at"),
    )

    def __repr__(self):
        return (
            f"<ChatMessage {self.id}: role={self.role}, "
            f"blocked={self.blocked_by_policy is not None}>"
        )


class KBEmbedding(Base):
    """Embeddings for KB articles (RAG index)."""

    __tablename__ = "ai_kb_embeddings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    article_id = Column(
        UUID(as_uuid=True),
        ForeignKey("kb_articles.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    embedding = Column(
        JSON, nullable=False
    )  # Vector as JSON array (for now; would use pgvector in prod)
    embedding_model = Column(
        String(100), nullable=False, default="openai-text-embedding-3-small"
    )
    indexed_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (Index("ix_ai_kb_embeddings_indexed", "indexed_at"),)

    def __repr__(self):
        return f"<KBEmbedding article={self.article_id}, model={self.embedding_model}>"


class FeatureFlag(Base):
    """Feature flags for owner-controlled toggles (PR-091)."""

    __tablename__ = "feature_flags"

    name = Column(String(100), primary_key=True)
    enabled = Column(Boolean, nullable=False, default=False)
    owner_only = Column(Boolean, nullable=False, default=True)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    updated_by = Column(String(36), nullable=True)  # User ID who toggled
    description = Column(Text, nullable=True)

    __table_args__ = (Index("ix_feature_flags_enabled", "enabled"),)

    def __repr__(self):
        return f"<FeatureFlag {self.name}: enabled={self.enabled}, owner_only={self.owner_only}>"
