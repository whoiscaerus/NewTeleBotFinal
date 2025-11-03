import os
from unittest.mock import patch

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TestSettings(BaseSettings):
    enabled: bool = Field(default=True, alias="ENABLED")
    model_config = SettingsConfigDict(case_sensitive=False)


# Test string "false"
with patch.dict(os.environ, {"ENABLED": "false"}, clear=False):
    t = TestSettings()
    print(f"String 'false': enabled={t.enabled} (type={type(t.enabled).__name__})")

# Test string "0"
with patch.dict(os.environ, {"ENABLED": "0"}, clear=False):
    t = TestSettings()
    print(f"String '0': enabled={t.enabled} (type={type(t.enabled).__name__})")

# Test string "true"
with patch.dict(os.environ, {"ENABLED": "true"}, clear=False):
    t = TestSettings()
    print(f"String 'true': enabled={t.enabled} (type={type(t.enabled).__name__})")

# Test string "1"
with patch.dict(os.environ, {"ENABLED": "1"}, clear=False):
    t = TestSettings()
    print(f"String '1': enabled={t.enabled} (type={type(t.enabled).__name__})")

# Test string "" (empty)
with patch.dict(os.environ, {"ENABLED": ""}, clear=False):
    t = TestSettings()
    print(f"String '': enabled={t.enabled} (type={type(t.enabled).__name__})")
