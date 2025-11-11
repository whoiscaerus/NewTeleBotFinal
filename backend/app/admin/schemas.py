"""
PR-099: Admin Portal Pydantic Schemas

Request/response models for admin API endpoints.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, validator

# ===== User Management =====


class UserSearchRequest(BaseModel):
    """Request schema for searching users."""

    query: Optional[str] = Field(
        None, description="Search by email, telegram_id, or name"
    )
    tier: Optional[str] = Field(None, description="Filter by subscription tier")
    status: Optional[str] = Field(None, description="Filter by account status")
    limit: int = Field(50, ge=1, le=500)
    offset: int = Field(0, ge=0)


class UserOut(BaseModel):
    """Response schema for user details."""

    id: str
    email: Optional[str]
    telegram_id: Optional[str]
    tier: str
    status: str
    kyc_status: str
    created_at: datetime
    last_active_at: Optional[datetime]
    total_approvals: int
    total_devices: int

    class Config:
        orm_mode = True


class UserUpdateRequest(BaseModel):
    """Request schema for updating user."""

    tier: Optional[str] = Field(None, pattern="^(free|standard|premium|elite)$")
    status: Optional[str] = Field(None, pattern="^(active|suspended|banned)$")
    kyc_status: Optional[str] = Field(None, pattern="^(pending|approved|rejected)$")
    notes: Optional[str] = Field(None, max_length=1000)


# ===== Device Management =====


class DeviceSearchRequest(BaseModel):
    """Request schema for searching devices."""

    user_id: Optional[str] = None
    status: Optional[str] = Field(None, pattern="^(active|revoked|expired)$")
    limit: int = Field(50, ge=1, le=500)
    offset: int = Field(0, ge=0)


class DeviceOut(BaseModel):
    """Response schema for device details."""

    id: str
    user_id: str
    device_name: str
    status: str
    created_at: datetime
    last_poll_at: Optional[datetime]
    total_positions: int

    class Config:
        orm_mode = True


# ===== Billing & Refunds =====


class RefundRequest(BaseModel):
    """Request schema for processing refund."""

    user_id: str = Field(..., min_length=1)
    amount: float = Field(..., gt=0, description="Refund amount in GBP")
    reason: str = Field(..., min_length=10, max_length=500)
    stripe_payment_intent_id: Optional[str] = None

    @validator("amount")
    def validate_amount(cls, v):
        """Validate amount has max 2 decimal places."""
        if round(v, 2) != v:
            raise ValueError("Amount must have at most 2 decimal places")
        return v


class RefundOut(BaseModel):
    """Response schema for refund result."""

    refund_id: str
    user_id: str
    amount: float
    status: str
    stripe_refund_id: Optional[str]
    processed_at: datetime
    processed_by: str


# ===== Fraud Management =====


class FraudEventOut(BaseModel):
    """Response schema for fraud event."""

    id: str
    user_id: str
    event_type: str
    severity: str
    details: dict
    status: str
    created_at: datetime
    resolved_at: Optional[datetime]
    resolved_by: Optional[str]

    class Config:
        orm_mode = True


class FraudResolutionRequest(BaseModel):
    """Request schema for resolving fraud event."""

    event_id: str
    resolution: str = Field(
        ..., pattern="^(false_positive|confirmed_fraud|needs_review)$"
    )
    action_taken: str = Field(..., min_length=10, max_length=500)
    notes: Optional[str] = Field(None, max_length=1000)


# ===== Support Tickets =====


class TicketOut(BaseModel):
    """Response schema for support ticket."""

    id: str
    user_id: str
    subject: str
    severity: str
    status: str
    channel: str
    created_at: datetime
    assigned_to: Optional[str]
    resolved_at: Optional[datetime]

    class Config:
        orm_mode = True


class TicketUpdateRequest(BaseModel):
    """Request schema for updating ticket."""

    status: Optional[str] = Field(None, pattern="^(open|assigned|resolved|closed)$")
    assigned_to: Optional[str] = None
    response: Optional[str] = Field(None, max_length=2000)
    internal_notes: Optional[str] = Field(None, max_length=1000)


# ===== Analytics Dashboard =====


class AnalyticsDashboardOut(BaseModel):
    """Response schema for admin analytics dashboard."""

    # API Health
    api_health_status: str
    api_error_rate_percent: float
    api_avg_latency_ms: float

    # Signal Ingestion
    signals_ingested_last_hour: int
    signals_ingested_last_24h: int
    ingestion_rate_per_minute: float

    # Payment Errors
    payment_errors_last_24h: int
    failed_payment_amount_gbp: float
    retry_success_rate_percent: float

    # Copy Trading
    copy_trading_active_users: int
    copy_trading_positions_open: int
    copy_trading_pnl_today_gbp: float

    # User Stats
    total_users: int
    active_users_last_7d: int
    new_signups_last_24h: int

    # System
    db_connections_active: int
    redis_cache_hit_rate_percent: float
    celery_queue_depth: int


# ===== KB/CMS =====


class ArticleOut(BaseModel):
    """Response schema for KB article."""

    id: str
    title: str
    status: str
    locale: str
    tags: list[str]
    author_id: str
    created_at: datetime
    updated_at: datetime
    published_at: Optional[datetime]
    views: int

    class Config:
        orm_mode = True


class ArticlePublishRequest(BaseModel):
    """Request schema for publishing article."""

    article_id: str
    publish: bool = Field(..., description="True to publish, False to unpublish")
