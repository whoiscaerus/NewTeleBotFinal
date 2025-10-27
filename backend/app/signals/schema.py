"""Pydantic schemas for signal API validation and serialization."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, validator


class SignalStatusEnum(str, Enum):
    """Signal lifecycle status."""

    NEW = "new"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class SignalCreate(BaseModel):
    """Schema for creating new signal via API.

    Validation:
    - instrument: 2-20 chars, alphanumeric + underscores
    - side: must be 'buy' or 'sell'
    - price: positive float
    - payload: JSON data from strategy (max 1KB)
    """

    instrument: str = Field(
        ...,
        min_length=2,
        max_length=20,
        pattern="^[A-Z0-9_]+$",
        description="Trading instrument (e.g., XAUUSD, EURUSD)",
    )
    side: str = Field(
        ...,
        pattern="^(buy|sell)$",
        description="Trade direction",
    )
    price: float = Field(
        ...,
        gt=0,
        lt=1_000_000,
        description="Entry price",
    )
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Strategy metadata (RSI, Fib level, etc.)",
    )
    version: str = Field(
        default="1.0",
        min_length=1,
        max_length=20,
        pattern="^[0-9.]+$",
        description="Signal schema version for deduplication",
    )

    @validator("instrument")
    def validate_instrument(cls, v: str) -> str:
        """Validate instrument is in whitelist."""
        VALID_INSTRUMENTS = {
            "XAUUSD",
            "EURUSD",
            "GBPUSD",
            "USDJPY",
            "AUDUSD",
            "NZDUSD",
            "USDCAD",
            "USDCHF",
            "EURGBP",
            "EURJPY",
            # Add more as needed
        }
        if v not in VALID_INSTRUMENTS:
            raise ValueError(f"Instrument {v} not in whitelist")
        return v

    @validator("payload")
    def validate_payload(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Validate payload size."""
        import json

        payload_size = len(json.dumps(v))
        if payload_size > 1024:  # 1KB max
            raise ValueError(f"Payload exceeds 1KB limit: {payload_size} bytes")
        return v

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "instrument": "XAUUSD",
                "side": "buy",
                "price": 1950.50,
                "payload": {
                    "rsi": 75.5,
                    "fib_level": 0.618,
                    "confidence": 0.85,
                },
            }
        }


class SignalOut(BaseModel):
    """Schema for signal responses."""

    id: str = Field(..., description="Unique signal ID")
    instrument: str
    side: int  # 0=buy, 1=sell (from database)
    price: float
    status: int  # Use int directly from database
    payload: dict[str, Any]
    version: str = Field(default="1.0", description="Signal schema version")
    external_id: str | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        """Pydantic config."""

        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }

    @property
    def side_label(self) -> str:
        """Get human-readable side label."""
        return "buy" if self.side == 0 else "sell"

    @property
    def status_label(self) -> str:
        """Get human-readable status label."""
        labels = {
            0: "new",
            1: "approved",
            2: "rejected",
            3: "executed",
            4: "closed",
            5: "cancelled",
        }
        return labels.get(self.status, "unknown")


class SignalListOut(BaseModel):
    """Schema for list of signals with pagination."""

    items: list[SignalOut]
    total: int
    page: int
    page_size: int

    @property
    def pages(self) -> int:
        """Calculate total pages."""
        return (self.total + self.page_size - 1) // self.page_size
