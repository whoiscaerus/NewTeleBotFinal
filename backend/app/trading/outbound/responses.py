"""Response models for signal ingest endpoint."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class SignalIngestResponse(BaseModel):
    """Server response to signal ingest request.

    Returned by the server's `/api/v1/signals/ingest` endpoint after receiving
    a signed signal.

    Attributes:
        signal_id: Server-assigned UUID for this signal
        status: Processing status ("received", "pending_approval", "rejected")
        server_timestamp: Server timestamp when signal was ingested
        message: Optional human-readable message from server
        errors: List of validation errors (if status="rejected")

    Example:
        >>> response = SignalIngestResponse(
        ...     signal_id="sig-abc123",
        ...     status="pending_approval",
        ...     server_timestamp=datetime.utcnow(),
        ...     message="Signal received and queued for approval"
        ... )
        >>> response.status
        'pending_approval'
    """

    signal_id: str = Field(..., description="Server-assigned signal UUID")
    status: str = Field(
        ...,
        description="Status: received, pending_approval, rejected",
        pattern="^(received|pending_approval|rejected)$",
    )
    server_timestamp: datetime = Field(
        ..., description="Server timestamp when signal was ingested"
    )
    message: Optional[str] = Field(
        None, description="Optional server message (e.g., error description)"
    )
    errors: Optional[list[str]] = Field(
        None, description="List of validation errors if rejected"
    )

    class Config:
        """Pydantic configuration."""

        json_schema_extra = {
            "example": {
                "signal_id": "sig-abc123-def456",
                "status": "pending_approval",
                "server_timestamp": "2025-10-25T14:30:45.123456Z",
                "message": "Signal received and queued for user approval",
                "errors": None,
            }
        }

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"SignalIngestResponse(signal_id={self.signal_id!r}, "
            f"status={self.status!r}, "
            f"timestamp={self.server_timestamp})"
        )
