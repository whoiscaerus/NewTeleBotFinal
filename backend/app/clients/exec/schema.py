"""Execution store schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class ExecutionAckRequest(BaseModel):
    """Device ACKs signal received."""

    signal_id: str = Field(..., description="Signal ID")
    device_id: str = Field(..., description="Device ID")


class ExecutionFillRequest(BaseModel):
    """Device reports trade fill."""

    signal_id: str = Field(..., description="Signal ID")
    device_id: str = Field(..., description="Device ID")
    trade_id: str = Field(..., description="Trade ID")
    fill_price: float = Field(..., gt=0, description="Fill price")
    fill_size: float = Field(..., gt=0, description="Fill size")


class ExecutionErrorRequest(BaseModel):
    """Device reports execution error."""

    signal_id: str = Field(..., description="Signal ID")
    device_id: str = Field(..., description="Device ID")
    status_code: int | None = Field(None, description="Status code")
    error_message: str = Field(..., max_length=500, description="Error message")


class ExecutionRecordOut(BaseModel):
    """Execution record response."""

    id: str
    device_id: str
    signal_id: str
    trade_id: str | None
    execution_type: int
    status_code: int | None
    error_message: str | None
    fill_price: float | None
    fill_size: float | None
    created_at: datetime

    class Config:
        """Pydantic config."""

        from_attributes = True
