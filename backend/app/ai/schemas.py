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


# PR-091: AI Analyst / Market Outlook Schemas


class VolatilityZone(BaseModel):
    """Volatility zone classification."""

    level: str  # "low", "medium", "high"
    threshold: float  # Volatility percentage threshold
    description: str  # Human-readable description


class CorrelationPair(BaseModel):
    """Correlation between two instruments."""

    instrument_a: str  # e.g., "GOLD"
    instrument_b: str  # e.g., "USD/JPY"
    coefficient: float  # -1 to 1


class OutlookReport(BaseModel):
    """Daily AI-written market outlook report (PR-091)."""

    narrative: str = Field(..., min_length=200, max_length=5000)
    volatility_zones: list[VolatilityZone] = Field(default_factory=list)
    correlations: list[CorrelationPair] = Field(default_factory=list)
    data_citations: dict[str, str | float] = Field(
        default_factory=dict
    )  # {"sharpe_ratio": 1.25, "max_drawdown": "-15.3%", ...}
    generated_at: datetime
    instruments_covered: list[str] = Field(default_factory=list)  # ["GOLD", ...]

    class Config:
        from_attributes = True


class FeatureFlagOut(BaseModel):
    """Feature flag status (PR-091)."""

    name: str
    enabled: bool
    owner_only: bool
    updated_at: datetime
    updated_by: str | None = None
    description: str | None = None

    class Config:
        from_attributes = True


class FeatureFlagUpdateIn(BaseModel):
    """Feature flag update request (PR-091)."""

    enabled: bool
    owner_only: bool = Field(default=True)
