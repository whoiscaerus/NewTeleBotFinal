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
    approval_token: str | None = None
    expires_at: datetime | None = None

    class Config:
        """Pydantic config."""

        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


class PendingApprovalOut(BaseModel):
    """Pending approval for mini app console.

    Contains signal details needed for approval decision.
    Does NOT include SL/TP (stored in owner_only, never exposed).
    """

    signal_id: str
    instrument: str
    side: str  # "buy" or "sell"
    lot_size: float
    created_at: datetime
    approval_token: str = Field(..., description="Short-lived JWT token (5 min expiry)")
    expires_at: datetime = Field(..., description="Token expiry timestamp")

    class Config:
        """Pydantic config."""

        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }
