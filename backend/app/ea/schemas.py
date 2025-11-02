"""
Pydantic schemas for EA poll/ack endpoints (PR-024a + PR-104).

Schemas for:
- PollResponse: List of approved signals ready for execution
- AckRequest: Device acknowledgment of execution attempt
- AckResponse: Confirmation of execution recorded

SECURITY NOTE (PR-104):
ExecutionParamsOut is REDACTED - it does NOT include stop_loss or take_profit.
These levels are kept server-side only to prevent signal reselling.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, validator


class ExecutionParamsOut(BaseModel):
    """
    Execution parameters from signal (PR-015 + PR-104 REDACTED).

    CRITICAL SECURITY:
    This schema is sent to client EAs. It does NOT include stop_loss or take_profit
    to prevent clients from seeing complete trading strategy (anti-reselling protection).

    The server tracks hidden SL/TP in OpenPosition.owner_sl/owner_tp and will
    automatically close positions when those levels are hit.
    """

    entry_price: float = Field(..., gt=0, lt=1_000_000)
    volume: float = Field(..., gt=0, le=1000)
    ttl_minutes: int = Field(..., ge=1, le=10080)  # 1 min to 7 days

    class Config:
        json_schema_extra = {
            "example": {
                "entry_price": 1950.50,
                "volume": 0.5,
                "ttl_minutes": 240,
                # NOTE: stop_loss and take_profit are INTENTIONALLY ABSENT
                # They are kept server-side only (OpenPosition.owner_sl/owner_tp)
            }
        }


class ApprovedSignalOut(BaseModel):
    """Approved signal ready for polling."""

    approval_id: UUID = Field(..., description="Approval ID (used in ack)")
    instrument: str = Field(
        ..., min_length=2, max_length=20, description="Instrument symbol"
    )
    side: str = Field(..., pattern="^(buy|sell)$", description="Trade direction")
    execution_params: ExecutionParamsOut
    approved_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "approval_id": "550e8400-e29b-41d4-a716-446655440000",
                "instrument": "XAUUSD",
                "side": "buy",
                "execution_params": {
                    "entry_price": 1950.50,
                    # NO stop_loss ❌ (kept server-side)
                    # NO take_profit ❌ (kept server-side)
                    "volume": 0.5,
                    "ttl_minutes": 240,
                },
                "approved_at": "2025-10-26T10:30:45Z",
                "created_at": "2025-10-26T10:30:00Z",
            }
        }


class EncryptedSignalEnvelope(BaseModel):
    """PR-042: Encrypted signal envelope with AEAD protection.

    Signal payloads are encrypted with AES-256-GCM using per-device keys.
    Clients decrypt using caerus_crypto.mqh SDK.
    """

    approval_id: UUID = Field(..., description="Approval ID (used in ack)")
    ciphertext: str = Field(..., description="Base64-encoded AES-256-GCM ciphertext")
    nonce: str = Field(..., description="Base64-encoded 12-byte nonce")
    aad: str = Field(..., description="Authenticated Associated Data (device_id)")

    class Config:
        json_schema_extra = {
            "example": {
                "approval_id": "550e8400-e29b-41d4-a716-446655440000",
                "ciphertext": "k2hSU0FhbWJlcjMyICsgQUI4YjdjTHJmMDhpWEorUWVDMmhWVnc9PQ==",
                "nonce": "L4FqCw0xR5L8M3xJ",
                "aad": "dev_123abc",
            }
        }


class PollResponse(BaseModel):
    """Response from poll endpoint."""

    approvals: list[ApprovedSignalOut] = Field(
        default_factory=list, description="Approved signals"
    )
    count: int = Field(..., ge=0, description="Number of signals returned")
    polled_at: datetime
    next_poll_seconds: int = Field(
        default=10, description="Recommended delay before next poll"
    )

    @validator("count")
    def count_matches_approvals(cls, v, values):
        if v != len(values.get("approvals", [])):
            raise ValueError("count must match length of approvals")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "approvals": [
                    {
                        "approval_id": "550e8400-e29b-41d4-a716-446655440000",
                        "instrument": "XAUUSD",
                        "side": "buy",
                        "execution_params": {
                            "entry_price": 1950.50,
                            # NO stop_loss ❌ (hidden from client)
                            # NO take_profit ❌ (hidden from client)
                            "volume": 0.5,
                            "ttl_minutes": 240,
                        },
                        "approved_at": "2025-10-26T10:30:45Z",
                        "created_at": "2025-10-26T10:30:00Z",
                    }
                ],
                "count": 1,
                "polled_at": "2025-10-26T10:31:00Z",
                "next_poll_seconds": 10,
            }
        }


class EncryptedPollResponse(BaseModel):
    """PR-042: Poll response with encrypted signal envelopes.

    All signal payloads are wrapped in AES-256-GCM AEAD envelopes.
    Clients decrypt using device encryption key and caerus_crypto.mqh SDK.
    """

    approvals: list[EncryptedSignalEnvelope] = Field(
        default_factory=list, description="Encrypted approved signals"
    )
    count: int = Field(..., ge=0, description="Number of signals returned")
    polled_at: datetime
    next_poll_seconds: int = Field(
        default=10, description="Recommended delay before next poll"
    )

    @validator("count")
    def count_matches_approvals(cls, v, values):
        if v != len(values.get("approvals", [])):
            raise ValueError("count must match length of approvals")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "approvals": [
                    {
                        "approval_id": "550e8400-e29b-41d4-a716-446655440000",
                        "ciphertext": "k2hSU0FhbWJlcjMyICsgQUI4YjdjTHJmMDhpWEorUWVDMmhWVnc9PQ==",
                        "nonce": "L4FqCw0xR5L8M3xJ",
                        "aad": "dev_123abc",
                    }
                ],
                "count": 1,
                "polled_at": "2025-10-26T10:31:00Z",
                "next_poll_seconds": 10,
            }
        }


class AckRequest(BaseModel):
    """Device acknowledgment of execution attempt."""

    approval_id: UUID = Field(..., description="Approval ID from poll")
    status: str = Field(
        ..., pattern="^(placed|failed)$", description="Execution outcome"
    )
    broker_ticket: str | None = Field(
        default=None, max_length=128, description="Broker order ticket if placed"
    )
    error: str | None = Field(
        default=None, max_length=1024, description="Error message if failed"
    )

    @validator("error")
    def error_required_if_failed(cls, v, values):
        if values.get("status") == "failed" and not v:
            raise ValueError("error message required when status is failed")
        return v

    @validator("broker_ticket")
    def broker_ticket_required_if_placed(cls, v, values):
        if values.get("status") == "placed" and not v:
            raise ValueError("broker_ticket required when status is placed")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "approval_id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "placed",
                "broker_ticket": "123456789",
                "error": None,
            }
        }


class AckResponse(BaseModel):
    """Response from ack endpoint."""

    execution_id: UUID = Field(..., description="Created execution ID")
    approval_id: UUID = Field(..., description="Approval ID")
    status: str = Field(..., description="Execution status")
    recorded_at: datetime

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "execution_id": "660e8400-e29b-41d4-a716-446655440001",
                "approval_id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "placed",
                "recorded_at": "2025-10-26T10:31:15Z",
            }
        }


class ExecutionOut(BaseModel):
    """Full execution details (for admin query)."""

    id: UUID
    approval_id: UUID
    device_id: UUID
    status: str
    broker_ticket: str | None
    error: str | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AggregateExecutionStatus(BaseModel):
    """Aggregate execution status for an approval."""

    approval_id: UUID
    placed_count: int = Field(ge=0, description="Devices that placed")
    failed_count: int = Field(ge=0, description="Devices that failed")
    total_count: int = Field(ge=0, description="Total execution attempts")
    last_update: datetime
    executions: list[ExecutionOut] = Field(default_factory=list)

    class Config:
        json_schema_extra = {
            "example": {
                "approval_id": "550e8400-e29b-41d4-a716-446655440000",
                "placed_count": 2,
                "failed_count": 0,
                "total_count": 2,
                "last_update": "2025-10-26T10:31:15Z",
                "executions": [],
            }
        }
