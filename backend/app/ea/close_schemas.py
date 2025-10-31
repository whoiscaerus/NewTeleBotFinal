"""Pydantic schemas for Close Commands API (PR-104 Phase 5).

These schemas define the request/response formats for the close commands
endpoint that enables server-initiated position closes.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class CloseCommandOut(BaseModel):
    """Single close command for EA to execute.

    The EA receives these from polling and executes the position close.
    """

    id: str = Field(..., description="Close command UUID")
    position_id: str = Field(..., description="Position to close")
    reason: str = Field(..., description="Reason: sl_hit, tp_hit, manual")
    expected_price: float = Field(..., description="Expected close price")
    created_at: datetime = Field(..., description="Command creation time")

    class Config:
        from_attributes = True


class CloseCommandsResponse(BaseModel):
    """Response from /close-commands poll endpoint.

    Returns all pending close commands for the device.
    """

    commands: list[CloseCommandOut] = Field(
        default_factory=list,
        description="List of pending close commands",
    )
    count: int = Field(..., description="Number of commands")


class CloseAckRequest(BaseModel):
    """EA acknowledges close command execution (PR-104 Phase 5).

    After receiving a close command and attempting to execute it,
    the EA sends this acknowledgment.
    """

    command_id: str = Field(..., description="Close command UUID")
    status: str = Field(
        ...,
        pattern="^(executed|failed)$",
        description="Execution result: executed or failed",
    )
    actual_close_price: float | None = Field(
        None,
        description="Actual close price (required if status=executed)",
    )
    error_message: str | None = Field(
        None,
        max_length=500,
        description="Error details (required if status=failed)",
    )
    timestamp: datetime = Field(..., description="When close was executed")


class CloseAckResponse(BaseModel):
    """Response from /close-ack endpoint (PR-104 Phase 5).

    Confirms the close acknowledgment was recorded.
    """

    command_id: str = Field(..., description="Close command UUID")
    position_id: str = Field(..., description="Position that was closed")
    status: str = Field(..., description="Final status: executed or failed")
    recorded_at: datetime = Field(..., description="When ack was recorded")
