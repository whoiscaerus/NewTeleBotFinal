"""
AI Schemas - Request/response models for chat endpoints.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ChatCitation(BaseModel):
    """Citation reference in a chat response."""

    article_id: UUID
    title: str
    url: str
    excerpt: str | None = None


class ChatMessageOut(BaseModel):
    """Chat message in list view."""

    id: UUID
    role: str  # "user", "assistant", "system"
    content: str
    citations: list[ChatCitation] = Field(default_factory=list)
    blocked_by_policy: str | None = None
    confidence_score: float | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class ChatSessionOut(BaseModel):
    """Chat session summary."""

    id: UUID
    title: str
    escalated: bool
    escalated_to_human_at: datetime | None = None
    escalation_reason: str | None = None
    message_count: int = 0
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None = None

    class Config:
        from_attributes = True


class ChatSessionDetailOut(ChatSessionOut):
    """Chat session with full message history."""

    messages: list[ChatMessageOut] = Field(default_factory=list)


class ChatRequestIn(BaseModel):
    """User chat message request."""

    session_id: UUID | None = None  # None for new session
    question: str = Field(..., min_length=1, max_length=2000)
    channel: str = Field(default="web", pattern="^(telegram|web)$")


class ChatResponseOut(BaseModel):
    """AI assistant response."""

    session_id: UUID
    message_id: UUID
    answer: str
    citations: list[ChatCitation] = Field(default_factory=list)
    confidence_score: float  # 0-1
    blocked_by_policy: str | None = None
    requires_escalation: bool = False
    escalation_reason: str | None = None

    class Config:
        from_attributes = True


class EscalateRequestIn(BaseModel):
    """Request to escalate to human support."""

    session_id: UUID
    reason: str = Field(..., min_length=5, max_length=500)


class IndexStatusOut(BaseModel):
    """RAG index status."""

    total_articles: int
    indexed_articles: int
    pending_articles: int
    last_indexed_at: datetime | None = None
    embedding_model: str


class GuardrailPolicyOut(BaseModel):
    """Active guardrail policy."""

    policy_name: str
    blocked: bool
    reason: str | None = None
