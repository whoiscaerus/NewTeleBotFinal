import os
from unittest.mock import patch

from backend.app.core.settings import RedisSettings

# Test what's happening with Redis enabled="false"
print(f"Current REDIS_ENABLED in env: {os.environ.get('REDIS_ENABLED')}")

with patch.dict(os.environ, {"REDIS_ENABLED": "false"}, clear=False):
    print(f"Inside patch - REDIS_ENABLED: {os.environ.get('REDIS_ENABLED')}")
    settings = RedisSettings()
    print(f"settings.enabled = {settings.enabled} (expected False)")
    print(f"type = {type(settings.enabled)}")
