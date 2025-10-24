#!/usr/bin/env python3
"""Test SecuritySettings validation."""

from typing import ClassVar

from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class TestSecuritySettings(BaseSettings):
    """Test security settings."""

    jwt_expiration_hours: int = Field(default=24, ge=1)

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )


# Test
print("Testing jwt_expiration_hours=0...")
try:
    s = TestSecuritySettings(jwt_expiration_hours=0)
    print(
        f"FAILED: Should have raised ValidationError, got jwt_expiration_hours={s.jwt_expiration_hours}"
    )
except ValidationError as e:
    print(f"SUCCESS: Raised ValidationError as expected: {e.errors()[0]['msg']}")
