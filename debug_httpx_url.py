"""Test httpx URL handling."""

from datetime import UTC, datetime

from httpx import Client

dt_with_tz = datetime.now(UTC).isoformat()
print(f"Datetime ISO: {dt_with_tz}")

# Simulate what the test does
url = f"http://example.com/api?since={dt_with_tz}"
print(f"URL string: {url}")

# What httpx actually sends
client = Client()
request = client.build_request("GET", url)
print(f"Request URL: {request.url}")
print(f"Request query: {request.url.query}")
print(f"Request raw: {str(request.url)}")
