"""Approval schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class ApprovalCreate(BaseModel):
    """Create approval request."""

    signal_id: str = Field(..., description="Signal ID")
    decision: str = Field(
        ...,
        pattern="^(approved|rejected)$",
        description="Decision",
    )
    reason: str | None = Field(None, max_length=500, description="Rejection reason")
    consent_version: int = Field(default=1, description="Consent text version")


class ApprovalOut(BaseModel):
    """Approval response."""

    id: str
    signal_id: str
    user_id: str
    decision: str
    reason: str | None
    consent_version: int
    created_at: datetime

    class Config:
        """Pydantic config."""

        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }
