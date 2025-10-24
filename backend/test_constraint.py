#!/usr/bin/env python3
"""Test Pydantic ge constraint."""

from typing import ClassVar

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TestSettings(BaseSettings):
    """Test settings."""

    value: int = Field(default=24, ge=1)

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )


print("Test 1: valid value=10")
try:
    s = TestSettings(value=10)
    print(f"  OK: value={s.value}")
except Exception as e:
    print(f"  Error: {e}")

print("\nTest 2: invalid value=0 (should fail, ge=1)")
try:
    s = TestSettings(value=0)
    print(f"  ERROR: Should have failed but got value={s.value}")
except Exception as e:
    print(f"  OK: Got error: {e}")

print("\nTest 3: negative value=-1 (should fail, ge=1)")
try:
    s = TestSettings(value=-1)
    print(f"  ERROR: Should have failed but got value={s.value}")
except Exception as e:
    print(f"  OK: Got error: {e}")
