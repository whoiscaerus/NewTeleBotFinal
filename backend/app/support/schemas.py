"""Pydantic schemas for support tickets."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, validator


class TicketCreateIn(BaseModel):
    """Request to create a new support ticket."""

    subject: str = Field(
        ..., min_length=3, max_length=200, description="Brief ticket summary"
    )
    body: str = Field(..., min_length=10, description="Detailed issue description")
    severity: str = Field(default="medium", pattern="^(low|medium|high|urgent)$")
    channel: str = Field(default="web", pattern="^(ai_chat|web|telegram|email|api)$")
    context: dict[str, Any] | None = Field(
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

    status: str | None = Field(
        None, pattern="^(open|in_progress|waiting_on_customer|resolved|closed)$"
    )
    assigned_to: str | None = Field(
        None, min_length=36, max_length=36, description="User ID to assign"
    )
    resolution_note: str | None = Field(
        None, description="Resolution summary (visible to user)"
    )
    internal_notes: str | None = Field(
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
    context: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None = None
    closed_at: datetime | None = None
    assigned_to: str | None = None
    resolution_note: str | None = None
    internal_notes: str | None = None

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
