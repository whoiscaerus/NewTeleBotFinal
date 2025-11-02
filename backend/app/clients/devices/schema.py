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


class DeviceCreateResponse(DeviceOut):
    """Response from device creation - includes secrets (shown once).

    PR-042: Includes both HMAC secret and encryption key material.
    Both are shown ONCE ONLY at registration time.
    """

    secret: str | None = None  # HMAC secret
    encryption_key: str | None = (
        None  # Base64-encoded AES-256 key for signal decryption
    )


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
