#!/usr/bin/env python3
"""Test Pydantic validator on empty string."""

from typing import ClassVar

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class TestDbSettings(BaseSettings):
    """Test database settings."""

    url: str = Field(..., alias="DATABASE_URL")

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )

    @field_validator("url", mode="after")
    @classmethod
    def validate_db_url(cls, v: str) -> str:
        """Validate database URL format."""
        print(f"Validator called with v={repr(v)}, is_empty={not v}")
        if not v:
            raise ValueError("DATABASE_URL cannot be empty")
        return v


try:
    d = TestDbSettings(url="")
    print(f"FAILED: Should have raised ValueError, but got url='{d.url}'")
except ValueError as e:
    print(f"SUCCESS: Raised ValueError as expected: {e}")
