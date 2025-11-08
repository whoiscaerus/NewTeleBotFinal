"""Pydantic schemas for support tickets."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, validator


class TicketCreateIn(BaseModel):
    """Request to create a new support ticket."""

    subject: str = Field(
        ..., min_length=3, max_length=200, description="Brief ticket summary"
    )
    body: str = Field(..., min_length=10, description="Detailed issue description")
    severity: str = Field(default="medium", pattern="^(low|medium|high|urgent)$")
    channel: str = Field(default="web", pattern="^(ai_chat|web|telegram|email|api)$")
    context: Optional[dict[str, Any]] = Field(
        default=None, description="Additional metadata"
    )

    @validator("subject")
    def subject_must_not_be_empty(cls, v):
        """Validate subject is not just whitespace."""
        if not v.strip():
            raise ValueError("Subject cannot be empty")
        return v.strip()

    @validator("body")
    def body_must_not_be_empty(cls, v):
        """Validate body is not just whitespace."""
        if not v.strip():
            raise ValueError("Body cannot be empty")
        return v.strip()


class TicketUpdateIn(BaseModel):
    """Request to update an existing ticket."""

    status: Optional[str] = Field(
        None, pattern="^(open|in_progress|waiting_on_customer|resolved|closed)$"
    )
    assigned_to: Optional[str] = Field(
        None, min_length=36, max_length=36, description="User ID to assign"
    )
    resolution_note: Optional[str] = Field(
        None, description="Resolution summary (visible to user)"
    )
    internal_notes: Optional[str] = Field(
        None, description="Internal staff notes (not visible to user)"
    )


class TicketCloseIn(BaseModel):
    """Request to close a ticket."""

    resolution_note: str = Field(
        ..., min_length=10, description="Required resolution summary"
    )

    @validator("resolution_note")
    def resolution_note_must_not_be_empty(cls, v):
        """Validate resolution note is not just whitespace."""
        if not v.strip():
            raise ValueError("Resolution note cannot be empty")
        return v.strip()


class TicketOut(BaseModel):
    """Ticket response schema."""

    id: str
    user_id: str
    subject: str
    body: str
    severity: str
    status: str
    channel: str
    context: Optional[dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime
    resolved_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    assigned_to: Optional[str] = None
    resolution_note: Optional[str] = None
    internal_notes: Optional[str] = None

    class Config:
        orm_mode = True
        json_encoders = {datetime: lambda v: v.isoformat()}


class TicketListOut(BaseModel):
    """Paginated ticket list response."""

    tickets: list[TicketOut]
    total: int
    skip: int
    limit: int

    class Config:
        orm_mode = True
