"""Privacy request schemas for API validation."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from backend.app.privacy.models import RequestType


class PrivacyRequestCreate(BaseModel):
    """Schema for creating a privacy request."""

    request_type: RequestType = Field(
        ..., description="Type of request: export or delete"
    )
    reason: str | None = Field(
        None, max_length=500, description="Optional reason for request"
    )

    class Config:
        use_enum_values = True


class PrivacyRequestResponse(BaseModel):
    """Schema for privacy request response."""

    id: str
    user_id: str
    request_type: str
    status: str
    created_at: datetime
    processed_at: datetime | None
    scheduled_deletion_at: datetime | None
    metadata: dict[str, Any]
    export_url: str | None
    export_expires_at: datetime | None
    hold_reason: str | None
    hold_by: str | None
    hold_at: datetime | None
    cooling_off_hours_remaining: int | None
    export_url_valid: bool

    class Config:
        orm_mode = True


class PrivacyRequestHold(BaseModel):
    """Schema for placing hold on privacy request."""

    reason: str = Field(
        ...,
        min_length=10,
        max_length=500,
        description="Reason for hold (e.g., active dispute)",
    )


class PrivacyRequestCancel(BaseModel):
    """Schema for cancelling privacy request."""

    reason: str | None = Field(
        None, max_length=500, description="Optional cancellation reason"
    )
