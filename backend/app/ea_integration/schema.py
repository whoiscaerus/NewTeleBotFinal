"""Request/Response schemas for EA integration."""

from pydantic import BaseModel, Field


class PollRequestIn(BaseModel):
    """EA poll request schema."""

    timestamp: int = Field(..., description="Unix timestamp")
    nonce: str = Field(..., description="Request nonce for replay prevention")
    signature: str = Field(..., description="HMAC signature")


class AckRequestIn(BaseModel):
    """EA acknowledgment request schema."""

    signal_id: str = Field(..., description="Signal ID being acknowledged")
    order_id: str | None = Field(None, description="Order ID if executed")
    status: str = Field(
        ..., description="Execution status (executed, rejected, pending)"
    )
    reason: str | None = Field(None, description="Reason if rejected")
