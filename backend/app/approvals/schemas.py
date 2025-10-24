"""Approval domain Pydantic schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class ApprovalRequest(BaseModel):
    """Request to approve or reject a signal.

    Attributes:
        signal_id: ID of signal to approve/reject
        decision: 0=approve, 1=reject
        device_id: Optional device identifier
        consent_version: Version of consent text accepted
        ip: IP address of requester
        ua: User agent string

    Example:
        >>> req = ApprovalRequest(
        ...     signal_id="sig-123",
        ...     decision=0,
        ...     consent_version="2024-01-15",
        ...     ip="192.168.1.1",
        ...     ua="Mozilla/5.0..."
        ... )
    """

    signal_id: str = Field(..., min_length=1, max_length=36)
    decision: int = Field(..., ge=0, le=1, description="0=approve, 1=reject")
    device_id: Optional[str] = Field(None, max_length=36)
    consent_version: str = Field(..., min_length=1, max_length=500)
    ip: Optional[str] = Field(None, max_length=45)
    ua: Optional[str] = Field(None, max_length=2000)

    @field_validator("signal_id")
    @classmethod
    def validate_signal_id(cls, v: str) -> str:
        """Validate signal ID format."""
        if not v.strip():
            raise ValueError("signal_id cannot be empty")
        return v.strip()

    @field_validator("consent_version")
    @classmethod
    def validate_consent_version(cls, v: str) -> str:
        """Validate consent version format."""
        if not v.strip():
            raise ValueError("consent_version cannot be empty")
        return v.strip()

    model_config = {
        "json_schema_extra": {
            "example": {
                "signal_id": "sig-abc123def456",
                "decision": 0,
                "device_id": "device-xyz",
                "consent_version": "2024-01-15",
                "ip": "192.168.1.1",
                "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            }
        }
    }


class ApprovalOut(BaseModel):
    """Approval response.

    Attributes:
        id: Approval ID
        signal_id: Signal ID
        user_id: User ID
        decision: 0=approved, 1=rejected
        created_at: Creation timestamp

    Example:
        >>> approval = ApprovalOut(
        ...     id="apr-123",
        ...     signal_id="sig-123",
        ...     user_id="user-123",
        ...     decision=0,
        ...     created_at=datetime.now()
        ... )
    """

    id: str
    signal_id: str
    user_id: str
    decision: int
    created_at: datetime

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": "apr-abc123",
                "signal_id": "sig-abc123",
                "user_id": "user-xyz",
                "decision": 0,
                "created_at": "2024-01-15T10:30:00Z",
            }
        },
    }


class ApprovalListOut(BaseModel):
    """List of approvals response.

    Attributes:
        count: Total number of approvals returned
        approvals: List of approval objects

    Example:
        >>> resp = ApprovalListOut(
        ...     count=2,
        ...     approvals=[approval1, approval2]
        ... )
    """

    count: int = Field(..., ge=0)
    approvals: list[ApprovalOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}
