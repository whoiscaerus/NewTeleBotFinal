# PR-017 Quick Reference Guide

**Folder**: `backend/app/trading/outbound/`
**Files**: 6 production + 2 test
**Status**: ✅ Complete, 42/42 tests passing

---

## Usage: Sending Signals

### Basic Usage (With Context Manager)

```python
from backend.app.trading.outbound import HmacClient, OutboundConfig
import logging

# Configure
config = OutboundConfig.from_env()
logger = logging.getLogger(__name__)

# Use with context manager
async with HmacClient(config, logger) as client:
    response = await client.post_signal(
        signal=signal_candidate,  # From PR-014
        idempotency_key="sig-20251025-001"
    )
    print(f"Signal {response.signal_id} status: {response.status}")
```

### Manual Session Management

```python
client = HmacClient(config, logger)

try:
    await client._ensure_session()
    response = await client.post_signal(signal_candidate)
    print(response)
finally:
    await client.close()
```

---

## Configuration

### Environment Variables

```bash
# Required
HMAC_PRODUCER_SECRET=your-secret-key-min-16-bytes-long
PRODUCER_ID=platform-producer

# Optional (with defaults)
HMAC_PRODUCER_ENABLED=true                        # Enable/disable delivery
OUTBOUND_SERVER_URL=https://api.external.com     # Server endpoint
OUTBOUND_TIMEOUT_SECONDS=30                      # HTTP timeout
OUTBOUND_MAX_BODY_SIZE=65536                     # Max request size
```

### Configuration Object

```python
from backend.app.trading.outbound import OutboundConfig

# From environment variables
config = OutboundConfig.from_env()

# Manual creation
config = OutboundConfig(
    producer_id="my-producer",
    producer_secret="min-16-byte-secret-key-here",  # ≥16 bytes
    server_base_url="https://api.example.com",
    enabled=True,
    timeout_seconds=30,      # 5-300s range
    max_body_size=65536      # 1KB-10MB range
)

# Validation happens automatically on creation
# Invalid configs raise ValueError
```

---

## API Reference

### HmacClient Class

```python
class HmacClient:
    def __init__(
        self,
        config: OutboundConfig,
        logger: logging.Logger
    ) -> None:
        """Initialize HMAC client with config and logger."""

    async def post_signal(
        self,
        signal: SignalCandidate,
        idempotency_key: str | None = None,
        timeout: float | None = None
    ) -> SignalIngestResponse:
        """
        Post signal to server.

        Args:
            signal: Trading signal from PR-014
            idempotency_key: Optional UUID for retry safety
            timeout: Optional HTTP timeout override

        Returns:
            SignalIngestResponse with server response

        Raises:
            OutboundClientError: HTTP/network errors
            ValueError: Signal validation failed
        """

    async def close(self) -> None:
        """Close HTTP session and cleanup resources."""

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit (cleanup)."""
```

### HMAC Functions

```python
from backend.app.trading.outbound import build_signature, verify_signature

# Generate HMAC signature
signature = build_signature(
    secret="your-secret-key",
    body=json.dumps(signal_data),
    timestamp="2025-10-25T14:30:45Z",
    producer_id="producer-id"
)
# Returns: base64-encoded HMAC-SHA256

# Verify HMAC signature (timing-safe)
is_valid = verify_signature(
    secret="your-secret-key",
    body=json.dumps(signal_data),
    timestamp="2025-10-25T14:30:45Z",
    producer_id="producer-id",
    provided_signature=signature  # from HTTP header
)
# Returns: True if valid, False if invalid or tampered
```

---

## Response Format

### SignalIngestResponse

```python
class SignalIngestResponse(BaseModel):
    signal_id: str              # Server-assigned signal ID
    status: str                 # "received", "pending_approval", "rejected"
    server_timestamp: str       # RFC3339 timestamp from server
    message: str | None         # Optional status message
    errors: list[str] | None    # Optional error list
```

### Example Response (HTTP 201)

```json
{
    "signal_id": "sig-abc-123",
    "status": "received",
    "server_timestamp": "2025-10-25T14:30:46.123456Z",
    "message": "Signal queued for approval",
    "errors": null
}
```

---

## Error Handling

### Exception Hierarchy

```
Exception
  └─ OutboundError (base for all PR-017 errors)
      ├─ OutboundClientError (HTTP/network errors)
      │   └─ Includes: http_code, details dict
      └─ OutboundSignatureError (signature validation failed)
```

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `OutboundClientError` 400 | Signal validation failed | Check: instrument, side, price, confidence |
| `OutboundClientError` 401 | Authentication failed | Verify HMAC secret and producer_id |
| `OutboundClientError` 413 | Body too large | Reduce signal payload size |
| `OutboundClientError` 500 | Server error | Retry with backoff (PR-018) |
| `OutboundSignatureError` | Signature invalid | Check secret, don't modify canonical request |
| `asyncio.TimeoutError` | HTTP timeout | Increase OUTBOUND_TIMEOUT_SECONDS |

### Error Handling Example

```python
from backend.app.trading.outbound import HmacClient, OutboundClientError

async with HmacClient(config, logger) as client:
    try:
        response = await client.post_signal(signal)
        logger.info(f"Signal sent: {response.signal_id}")
    except OutboundClientError as e:
        logger.error(f"HTTP error: {e.http_code} - {e.details}")
        # Implement retry logic (will be in PR-018)
    except asyncio.TimeoutError:
        logger.error("Signal delivery timeout")
        # Retry with longer timeout or different server
```

---

## Security Details

### HMAC-SHA256 Signing

**Canonical Request Format**:
```
METHOD:POST
ENDPOINT:/api/v1/signals/ingest
TIMESTAMP:<RFC3339>
PRODUCER_ID:<id>
BODY_SHA256:<base64(sha256(body))>
```

**Example**:
```
METHOD:POST
ENDPOINT:/api/v1/signals/ingest
TIMESTAMP:2025-10-25T14:30:45.123456Z
PRODUCER_ID:my-producer
BODY_SHA256:X+dPTxGRKLGJPLrvgqaH5hB8n+h7RaFt5R5M4yJ+e2k=
```

**Signature Generation**:
```python
import hmac
import hashlib
import base64

canonical = "METHOD:POST\nENDPOINT:/api/v1/signals/ingest\n..."
signature = base64.b64encode(
    hmac.new(
        secret.encode(),
        canonical.encode(),
        hashlib.sha256
    ).digest()
).decode()
```

### HTTP Headers

**Request Headers**:
```
X-Producer-Id: my-producer
X-Timestamp: 2025-10-25T14:30:45.123456Z
X-Signature: <base64-HMAC-SHA256>
X-Idempotency-Key: <uuid-for-retries>
Content-Type: application/json
```

**Server Verification**:
```python
# Server side (pseudo-code)
computed_sig = build_signature(
    secret, body, timestamp, producer_id
)
is_valid = hmac.compare_digest(
    computed_sig.encode(),
    provided_sig.encode()
)  # Timing-safe comparison
```

---

## Testing

### Unit Tests (HMAC Module)

```bash
# Run HMAC tests
.venv/Scripts/python.exe -m pytest backend/tests/test_outbound_hmac.py -v

# Run specific test class
.venv/Scripts/python.exe -m pytest backend/tests/test_outbound_hmac.py::TestHmacSignatureGeneration -v

# With coverage
.venv/Scripts/python.exe -m pytest backend/tests/test_outbound_hmac.py --cov=backend/app/trading/outbound
```

### Integration Tests (Client Module)

```bash
# Run client tests (uses mock HTTP)
.venv/Scripts/python.exe -m pytest backend/tests/test_outbound_client.py -v

# Run all outbound tests
.venv/Scripts/python.exe -m pytest backend/tests/test_outbound*.py -v
```

### Test Fixtures

```python
@pytest.fixture
def config() -> OutboundConfig:
    """Standard test configuration."""
    return OutboundConfig(
        producer_id="test-producer",
        producer_secret="test-secret-key-min-16-bytes-long",
        server_base_url="https://api.example.com",
        enabled=True,
        timeout_seconds=30.0,
        max_body_size=65536,
    )

@pytest.fixture
def signal() -> SignalCandidate:
    """Standard test signal from PR-014."""
    return SignalCandidate(
        instrument="GOLD",
        side="buy",
        entry_price=1950.50,
        stop_loss=1945.00,
        take_profit=1960.00,
        confidence=0.85,
        reason="test_signal",
        timestamp=datetime(2025, 10, 25, 14, 30, 45, 123456),
        payload={"rsi": 35, "atr": 5.5},
    )
```

---

## Logging

### Log Output (Structured JSON)

```json
{
    "timestamp": "2025-10-25 14:30:45.123",
    "level": "INFO",
    "logger": "backend.app.trading.outbound.client",
    "message": "Signal posted successfully",
    "producer_id": "my-producer",
    "signal_id": "sig-abc-123",
    "http_code": 201,
    "duration_ms": 145
}
```

### Log Levels

| Level | When | Example |
|-------|------|---------|
| `DEBUG` | Low-level operations | Signal serialization details |
| `INFO` | Normal operations | Signal posted, received response |
| `WARNING` | Recoverable issues | Slow response time, retry attempt |
| `ERROR` | Client/server errors | HTTP 400/500, timeout, validation failure |
| `CRITICAL` | System failures | Unable to create session, lost connection |

---

## Common Patterns

### Pattern 1: Post and Log Result

```python
async with HmacClient(config, logger) as client:
    signal = create_signal(...)
    response = await client.post_signal(signal)

    logger.info(
        f"Signal {response.signal_id} status: {response.status}",
        extra={
            "signal_id": response.signal_id,
            "status": response.status,
            "producer_id": config.producer_id
        }
    )
```

### Pattern 2: Conditional Delivery

```python
async with HmacClient(config, logger) as client:
    signal = create_signal(...)

    if config.enabled:
        try:
            response = await client.post_signal(signal)
        except OutboundClientError as e:
            logger.warning(f"Could not deliver externally: {e}")
            # Fall back to internal storage
    else:
        logger.info("External delivery disabled, using internal only")
```

### Pattern 3: Batch Delivery (Future - PR-018)

```python
# Will be implemented in PR-018 with retry logic
async with HmacClient(config, logger) as client:
    for signal in signals:
        try:
            response = await client.post_signal(
                signal,
                idempotency_key=signal.id,
                timeout=5.0
            )
        except OutboundClientError as e:
            logger.error(f"Delivery failed for {signal.id}: {e}")
            # Retry logic will be in PR-018
```

---

## Files Reference

| File | Purpose | Lines | Coverage |
|------|---------|-------|----------|
| `__init__.py` | Module exports | 17 | 100% |
| `exceptions.py` | Exception hierarchy | 50 | 65% |
| `config.py` | Configuration + validation | 155 | 47% |
| `hmac.py` | HMAC-SHA256 signing | 165 | 93% ✅ |
| `client.py` | Async HTTP client | 413 | 84% ✅ |
| `responses.py` | Response models | 60 | 92% ✅ |
| `test_outbound_hmac.py` | HMAC tests (22 tests) | 330 | - |
| `test_outbound_client.py` | Client tests (20 tests) | 400+ | - |

---

## Next Steps

### Immediate (PR-018)
- [ ] Add retry logic with exponential backoff
- [ ] Add Telegram alerts on failures
- [ ] Add metrics collection (success rate, latency)

### Medium-term (PR-021)
- [ ] Implement server-side signal ingest
- [ ] Validate incoming HMAC signatures
- [ ] Store signals in database

### Long-term (Phase 2)
- [ ] WebSocket real-time delivery
- [ ] Multi-producer support
- [ ] API documentation for partners

---

## Troubleshooting

**Q: "producer_secret must be at least 16 bytes"**
A: Your secret is too short. Use: `openssl rand -base64 24` to generate a 16+ byte secret.

**Q: "Unable to connect to https://api.example.com"**
A: Check OUTBOUND_SERVER_URL environment variable. Verify server is running and reachable.

**Q: "Signature does not match"**
A: Verify HMAC_PRODUCER_SECRET is correct. Ensure body/timestamp/producer_id haven't changed.

**Q: "Request timeout"**
A: Server is slow. Increase OUTBOUND_TIMEOUT_SECONDS (max: 300s). Consider adding retry logic (PR-018).

**Q: "HTTP 401 Unauthorized"**
A: Server rejected signature. Verify producer credentials and that canonical request format is correct.

---

## Support

For issues, questions, or PRs related to signal delivery:
1. Check test file examples: `backend/tests/test_outbound_client.py`
2. Review implementation: `backend/app/trading/outbound/`
3. Check logs: Look for `OutboundClientError` with http_code
4. Open GitHub issue with error details

---

**PR-017 Status**: ✅ Complete and Production-Ready
**Last Updated**: October 25, 2025
**Test Results**: 42/42 PASSING
**Coverage**: 76% (93% on critical HMAC module)
