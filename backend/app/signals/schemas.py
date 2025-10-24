"""Pydantic schemas for signals domain."""

import re
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, ConfigDict


# Constants
INSTRUMENT_PATTERN = r"^[A-Z0-9._-]{2,20}$"
MAX_PAYLOAD_BYTES = 32768


class SignalCreate(BaseModel):
    """Request model for creating a new signal.

    Validates all inputs for safety and consistency.

    Attributes:
        instrument: Trading pair code (e.g., "XAUUSD")
                   Pattern: ^[A-Z0-9._-]{2,20}$
        side: Trade direction (0=buy, 1=sell)
        time: Signal creation timestamp (ISO8601 with timezone)
        payload: Optional strategy data (max 32KB JSON)
        version: Signal format version (default 1)

    Example:
        >>> signal = SignalCreate(
        ...     instrument="XAUUSD",
        ...     side=0,
        ...     time=datetime.utcnow(),
        ...     payload={"rsi": 75}
        ... )
    """

    instrument: str = Field(
        ...,
        min_length=2,
        max_length=20,
        description="Trading instrument code (e.g., XAUUSD)",
        examples=["XAUUSD", "EURUSD", "BTC.USD"],
    )

    side: int = Field(
        ...,
        ge=0,
        le=1,
        description="Trade direction: 0=buy, 1=sell",
    )

    time: datetime = Field(
        ...,
        description="Signal creation timestamp (ISO8601 with timezone)",
    )

    payload: Optional[dict[str, Any]] = Field(
        default=None,
        description="Strategy-specific data (max 32KB)",
    )

    version: int = Field(
        default=1,
        ge=1,
        description="Signal format version",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "instrument": "XAUUSD",
                "side": 0,
                "time": "2024-01-15T10:30:45Z",
                "payload": {"rsi": 75, "macd": -0.5},
                "version": 1,
            }
        }
    )

    @field_validator("instrument")
    @classmethod
    def validate_instrument(cls, v: str) -> str:
        """Validate instrument code format.

        Args:
            v: Instrument code to validate

        Returns:
            Validated instrument code

        Raises:
            ValueError: If instrument doesn't match pattern
        """
        if not re.match(INSTRUMENT_PATTERN, v):
            raise ValueError(
                f"Instrument must match pattern {INSTRUMENT_PATTERN}. "
                f"Uppercase letters, numbers, dots, underscores, hyphens only. "
                f"Got: {v}"
            )
        return v

    @field_validator("time")
    @classmethod
    def validate_time(cls, v: datetime) -> datetime:
        """Validate timestamp is valid datetime with timezone.

        Args:
            v: Timestamp to validate

        Returns:
            Validated timestamp

        Raises:
            ValueError: If timestamp is invalid
        """
        if v.tzinfo is None:
            raise ValueError("Timestamp must include timezone information")
        return v

    @field_validator("payload")
    @classmethod
    def validate_payload(cls, v: Optional[dict]) -> Optional[dict]:
        """Validate payload size limit.

        Args:
            v: Payload dict to validate

        Returns:
            Validated payload

        Raises:
            ValueError: If payload exceeds size limit
        """
        if v is None:
            return v

        if not isinstance(v, dict):
            raise ValueError("Payload must be a JSON object (dict)")

        # Estimate size (conservative - actual may vary with encoding)
        import json
        payload_size = len(json.dumps(v).encode("utf-8"))

        if payload_size > MAX_PAYLOAD_BYTES:
            raise ValueError(
                f"Payload size {payload_size} bytes exceeds maximum "
                f"{MAX_PAYLOAD_BYTES} bytes"
            )

        return v


class SignalOut(BaseModel):
    """Response model for signal operations.

    Attributes:
        id: Unique signal identifier
        status: Current signal state (0=new, 1=queued, 2=closed)
        created_at: When signal was ingested

    Example:
        >>> signal = SignalOut(
        ...     id="550e8400-e29b-41d4-a716-446655440000",
        ...     status=0,
        ...     created_at=datetime.utcnow()
        ... )
    """

    id: str = Field(
        ...,
        description="Unique signal identifier (UUID)",
    )

    status: int = Field(
        ...,
        ge=0,
        le=2,
        description="Signal state (0=new, 1=queued, 2=closed)",
    )

    created_at: datetime = Field(
        ...,
        description="When signal was ingested",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "status": 0,
                "created_at": "2024-01-15T10:30:45.123456Z",
            }
        }
    )
