"""Device registry schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class DeviceRegister(BaseModel):
    """Device registration request."""

    device_name: str = Field(
        ..., min_length=1, max_length=100, description="Device name"
    )


class DeviceOut(BaseModel):
    """Device information."""

    id: str
    client_id: str
    device_name: str
    hmac_key_hash: str
    last_poll: datetime | None
    last_ack: datetime | None
    is_active: bool
    created_at: datetime

    class Config:
        """Pydantic config."""

        from_attributes = True


class DevicePollRequest(BaseModel):
    """Device polling request (with HMAC signature)."""

    device_id: str = Field(..., description="Device ID")
    timestamp: int = Field(..., description="Unix timestamp")
    signature: str = Field(..., description="HMAC-SHA256 signature")


class SignalForDevice(BaseModel):
    """Signal to send to device."""

    signal_id: str
    instrument: str
    side: str  # buy/sell
    price: float
    payload: dict | None = None
