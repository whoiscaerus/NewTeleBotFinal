"""Test different datetime formats."""

from datetime import UTC, datetime

# Current format (causing issues)
dt_with_tz = datetime.now(UTC).isoformat()
print(f"With TZ: {dt_with_tz}")

# Without timezone
dt_without_tz = datetime.now(UTC).replace(tzinfo=None).isoformat()
print(f"Without TZ: {dt_without_tz}")

# Replace +00:00 with Z (ISO 8601 standard)
dt_with_z = dt_with_tz.replace("+00:00", "Z")
print(f"With Z: {dt_with_z}")

# Try parsing with fromisoformat
try:
    parsed = datetime.fromisoformat(dt_with_tz)
    print(f"Parse WITH TZ OK: {parsed}")
except Exception as e:
    print(f"Parse WITH TZ ERROR: {e}")

try:
    parsed = datetime.fromisoformat(dt_without_tz)
    print(f"Parse WITHOUT TZ OK: {parsed}")
except Exception as e:
    print(f"Parse WITHOUT TZ ERROR: {e}")

from datetime import datetime

# FastAPI's datetime validator (what's failing)
from pydantic import BaseModel


class TestModel(BaseModel):
    since: datetime | None = None


# Test with different formats
formats_to_test = [
    dt_with_tz,  # WITH timezone
    dt_without_tz,  # WITHOUT timezone
    dt_with_z,  # With Z suffix
]

for fmt in formats_to_test:
    try:
        obj = TestModel(since=fmt)
        print(f"✅ Pydantic OK with: {fmt}")
    except Exception as e:
        print(f"❌ Pydantic ERROR with: {fmt}")
        print(f"   Error: {e}")
