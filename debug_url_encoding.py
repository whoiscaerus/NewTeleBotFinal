"""Test URL encoding issue."""

from urllib.parse import quote, unquote

dt_with_tz = "2025-11-04T18:46:12.832173+00:00"
print(f"Original: {dt_with_tz}")

# URL encode
encoded = quote(dt_with_tz, safe="")
print(f"URL encoded: {encoded}")

# What if + gets decoded as space?
with_space_instead = dt_with_tz.replace("+00:00", " 00:00")
print(f"With space: {with_space_instead}")

# This is the issue!
print("\nThe '+' in '+00:00' might be interpreted as a space by URL decoding!")
print(f"The query string would be: ?since={encoded}")
print(f"Which when decoded by FastAPI becomes: ?since={unquote(encoded)}")

# Solution 1: Use Z notation instead of +00:00
dt_with_z = dt_with_tz.replace("+00:00", "Z")
print(f"\nSolution 1 - Use Z: {dt_with_z}")
encoded_z = quote(dt_with_z, safe="")
print(f"URL encoded: {encoded_z}")

# Solution 2: Use ISO format without timezone
dt_no_tz = "2025-11-04T18:46:12.832173"
print(f"\nSolution 2 - No timezone: {dt_no_tz}")
encoded_no_tz = quote(dt_no_tz, safe=":T")
print(f"URL encoded: {encoded_no_tz}")
