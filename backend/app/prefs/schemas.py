"""
Pydantic Schemas for User Preferences - PR-059

Validation, serialization, and documentation for preference API.
"""

from datetime import time
from typing import Optional

import pytz
from pydantic import BaseModel, Field, field_validator

# Valid values
VALID_INSTRUMENTS = [
    "gold",
    "sp500",
    "crypto",
    "forex",
    "indices",
    "commodities",
    "bonds",
]
VALID_ALERT_TYPES = [
    "price",
    "drawdown",
    "copy_risk",
    "execution_failure",
    "account_balance",
    "margin",
]
VALID_DIGEST_FREQUENCIES = ["immediate", "hourly", "daily"]


class UserPreferencesResponse(BaseModel):
    """
    Response schema for user preferences.

    Returned by GET /api/v1/prefs endpoint.
    """

    id: int
    user_id: int
    instruments_enabled: list[str] = Field(
        default_factory=list, description="List of instruments to monitor"
    )
    alert_types_enabled: list[str] = Field(
        default_factory=list, description="List of alert types to receive"
    )
    notify_via_telegram: bool = Field(
        default=True, description="Send notifications via Telegram"
    )
    notify_via_email: bool = Field(
        default=True, description="Send notifications via email"
    )
    notify_via_push: bool = Field(
        default=False, description="Send notifications via web push (PWA)"
    )
    quiet_hours_enabled: bool = Field(
        default=False, description="Enable do not disturb periods"
    )
    quiet_hours_start: Optional[str] = Field(
        default=None, description="Quiet hours start time (HH:MM format)"
    )
    quiet_hours_end: Optional[str] = Field(
        default=None, description="Quiet hours end time (HH:MM format)"
    )
    timezone: str = Field(
        default="UTC", description="User timezone (IANA timezone name)"
    )
    digest_frequency: str = Field(
        default="immediate", description="Notification batching frequency"
    )
    notify_entry_failure: bool = Field(
        default=True, description="Alert on EA entry execution failure (PR-104)"
    )
    notify_exit_failure: bool = Field(
        default=True, description="Alert on position exit failure at SL/TP (PR-104)"
    )
    max_alerts_per_hour: int = Field(
        default=10, ge=1, le=100, description="Max alerts per hour to prevent spam"
    )
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class UserPreferencesUpdate(BaseModel):
    """
    Update schema for user preferences.

    Used by PUT /api/v1/prefs endpoint.

    Validation Rules:
    - Instruments must be in VALID_INSTRUMENTS
    - Alert types must be in VALID_ALERT_TYPES
    - Digest frequency must be in VALID_DIGEST_FREQUENCIES
    - Timezone must be valid IANA timezone
    - Quiet hours times must be in HH:MM format
    - Max alerts per hour must be 1-100
    - At least one notification channel must be enabled
    """

    instruments_enabled: Optional[list[str]] = Field(
        default=None, description="List of instruments to monitor", min_length=0
    )
    alert_types_enabled: Optional[list[str]] = Field(
        default=None, description="List of alert types to receive", min_length=0
    )
    notify_via_telegram: Optional[bool] = Field(
        default=None, description="Send notifications via Telegram"
    )
    notify_via_email: Optional[bool] = Field(
        default=None, description="Send notifications via email"
    )
    notify_via_push: Optional[bool] = Field(
        default=None, description="Send notifications via web push (PWA)"
    )
    quiet_hours_enabled: Optional[bool] = Field(
        default=None, description="Enable do not disturb periods"
    )
    quiet_hours_start: Optional[str] = Field(
        default=None, description="Quiet hours start time (HH:MM format, local time)"
    )
    quiet_hours_end: Optional[str] = Field(
        default=None, description="Quiet hours end time (HH:MM format, local time)"
    )
    timezone: Optional[str] = Field(
        default=None, description="User timezone (IANA timezone name)"
    )
    digest_frequency: Optional[str] = Field(
        default=None, description="Notification batching frequency"
    )
    notify_entry_failure: Optional[bool] = Field(
        default=None, description="Alert on EA entry execution failure (PR-104)"
    )
    notify_exit_failure: Optional[bool] = Field(
        default=None, description="Alert on position exit failure at SL/TP (PR-104)"
    )
    max_alerts_per_hour: Optional[int] = Field(
        default=None, ge=1, le=100, description="Max alerts per hour to prevent spam"
    )

    @field_validator("instruments_enabled")
    @classmethod
    def validate_instruments(cls, v):
        """Validate instruments are in the allowed list."""
        if v is not None:
            invalid = [inst for inst in v if inst not in VALID_INSTRUMENTS]
            if invalid:
                raise ValueError(
                    f"Invalid instruments: {invalid}. Must be one of: {VALID_INSTRUMENTS}"
                )
        return v

    @field_validator("alert_types_enabled")
    @classmethod
    def validate_alert_types(cls, v):
        """Validate alert types are in the allowed list."""
        if v is not None:
            invalid = [at for at in v if at not in VALID_ALERT_TYPES]
            if invalid:
                raise ValueError(
                    f"Invalid alert types: {invalid}. Must be one of: {VALID_ALERT_TYPES}"
                )
        return v

    @field_validator("digest_frequency")
    @classmethod
    def validate_digest_frequency(cls, v):
        """Validate digest frequency is in the allowed list."""
        if v is not None and v not in VALID_DIGEST_FREQUENCIES:
            raise ValueError(
                f"Invalid digest_frequency: {v}. Must be one of: {VALID_DIGEST_FREQUENCIES}"
            )
        return v

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v):
        """Validate timezone is a valid IANA timezone."""
        if v is not None:
            try:
                pytz.timezone(v)
            except pytz.UnknownTimeZoneError:
                raise ValueError(
                    f"Invalid timezone: {v}. Must be a valid IANA timezone (e.g., 'Europe/London')"
                )
        return v

    @field_validator("quiet_hours_start", "quiet_hours_end")
    @classmethod
    def validate_time_format(cls, v):
        """Validate time is in HH:MM format."""
        if v is not None:
            try:
                time.fromisoformat(v)
            except ValueError:
                raise ValueError(
                    f"Invalid time format: {v}. Must be HH:MM format (e.g., '22:00')"
                )
        return v

    def model_post_init(self, __context):
        """
        Additional validation after all fields parsed.

        Business Rule: At least one notification channel must be enabled.
        """
        # Check if at least one channel is enabled (only if any channel field is being updated)
        channels = [
            self.notify_via_telegram,
            self.notify_via_email,
            self.notify_via_push,
        ]
        # Only validate if we're updating channels
        if any(ch is not None for ch in channels):
            # If all explicit values are False
            enabled_channels = [ch for ch in channels if ch is not None and ch is True]
            all_disabled = all(ch is False for ch in channels if ch is not None)
            if all_disabled and len([ch for ch in channels if ch is not None]) == 3:
                raise ValueError(
                    "At least one notification channel (telegram, email, or push) must be enabled"
                )
