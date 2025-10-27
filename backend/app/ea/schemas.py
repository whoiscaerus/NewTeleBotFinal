"""
Pydantic schemas for EA poll/ack endpoints (PR-024a).

Schemas for:
- PollResponse: List of approved signals ready for execution
- AckRequest: Device acknowledgment of execution attempt
- AckResponse: Confirmation of execution recorded
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, validator


class ExecutionParamsOut(BaseModel):
    """Execution parameters from signal (PR-015)."""

    entry_price: float = Field(..., gt=0, lt=1_000_000)
    stop_loss: float = Field(..., gt=0, lt=1_000_000)
    take_profit: float = Field(..., gt=0, lt=1_000_000)
    volume: float = Field(..., gt=0, le=1000)
    ttl_minutes: int = Field(..., ge=1, le=10080)  # 1 min to 7 days

    class Config:
        json_schema_extra = {
            "example": {
                "entry_price": 1950.50,
                "stop_loss": 1940.00,
                "take_profit": 1965.00,
                "volume": 0.5,
                "ttl_minutes": 240,
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
                    "stop_loss": 1940.00,
                    "take_profit": 1965.00,
                    "volume": 0.5,
                    "ttl_minutes": 240,
                },
                "approved_at": "2025-10-26T10:30:45Z",
                "created_at": "2025-10-26T10:30:00Z",
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
                            "stop_loss": 1940.00,
                            "take_profit": 1965.00,
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


class AckRequest(BaseModel):
    """Device acknowledgment of execution attempt."""

    approval_id: UUID = Field(..., description="Approval ID from poll")
    status: str = Field(
        ..., pattern="^(placed|failed)$", description="Execution outcome"
    )
    broker_ticket: Optional[str] = Field(
        default=None, max_length=128, description="Broker order ticket if placed"
    )
    error: Optional[str] = Field(
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
    broker_ticket: Optional[str]
    error: Optional[str]
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
