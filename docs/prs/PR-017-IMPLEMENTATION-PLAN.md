# PR-017 Implementation Plan

**Signal Serialization + HMAC Signing for Server Ingest**

**Date Created**: October 25, 2025
**Status**: Phase 1 - Planning Complete ✅
**Target Completion**: October 25, 2025 (6 hours)

---

## 🎯 Executive Summary

PR-017 implements the **outbound signal delivery layer** for the trading platform. This PR creates a secure, HMAC-signed client that posts trading signals to the server's ingestion API with cryptographic authentication, reliable retry logic, and comprehensive telemetry.

**Key Objectives**:
1. ✅ Build HMAC signing mechanism for signal authentication
2. ✅ Implement POST client with canonical request serialization
3. ✅ Comprehensive testing of signature generation and validation
4. ✅ Telemetry integration (metrics, duration tracking)
5. ✅ Security validation (signature verification, timestamp checks)

**Business Value**:
- 🔐 Secure signal delivery (HMAC-SHA256 cryptographic signing)
- 📊 Reliable delivery tracking (telemetry + monitoring)
- 🏗️ Foundation for PR-018 (retries/backoff) and PR-019 (production trading)
- 💰 Enables premium tier differentiation (signal delivery SLAs)

---

## 📋 Project Context

### Technology Stack
- **Language**: Python 3.11.9
- **HTTP Client**: httpx (async-native, connection pooling)
- **Cryptography**: hashlib (SHA256), base64
- **Type Hints**: 100% (all functions typed)
- **Testing**: pytest 8.4.2 + pytest-asyncio
- **Code Quality**: Black (88-char lines), ruff linter, mypy type checking

### Architectural Fit
**Signal Flow**:
```
MT5 Bot (local)
    ↓ (SignalCandidate)
Strategy Engine (PR-014)
    ↓ (generates signal)
Signal Store (PR-016)
    ↓ (persists)
Outbound Client (PR-017) ← YOU ARE HERE
    ↓ (HMAC-signed POST)
Server Ingestion API (PR-021)
    ↓ (validates signature)
Server Signal Store
    ↓
User Approvals (web UI)
```

**Dependencies**:
- ✅ PR-014 (SignalCandidate model) - Used for serialization
- ✅ PR-016 (Trade Store) - Optional: call to get recent trades for context
- ➡️ PR-017 output feeds into PR-018 (retry logic) and PR-021 (server ingest)

**Integration Points**:
1. **Upstream**: Consumes `SignalCandidate` from PR-014
2. **Downstream**: Output feeds to retry wrapper (PR-018)
3. **Server**: Posts to `/api/v1/signals/ingest` endpoint (PR-021)
4. **Monitoring**: Emits metrics (signals_posted_total, duration_seconds)

---

## 📂 File Structure & Deliverables

### Files to Create

#### 1. `backend/app/trading/outbound/__init__.py` (15 lines)
**Purpose**: Module initialization and exports

**Exports**:
- `HmacClient` - Main HMAC signing client
- `build_signature` - Standalone function for signature generation
- `OutboundConfig` - Configuration dataclass

**Design Pattern**: Standard module init with minimal imports (lazy-load heavy dependencies)

---

#### 2. `backend/app/trading/outbound/config.py` (45 lines)
**Purpose**: Configuration management for outbound client

**Dataclass**:
```python
@dataclass
class OutboundConfig:
    producer_id: str              # Unique producer identifier (e.g., "mt5-gold-trader")
    producer_secret: str          # HMAC secret key (from environment)
    server_base_url: str          # Target server URL (e.g., "https://api.example.com")
    enabled: bool = True          # Feature flag
    timeout_seconds: float = 30.0 # HTTP timeout
    max_body_size: int = 65536    # Max signal body size (64 KB)

    @classmethod
    def from_env(cls) -> "OutboundConfig":
        """Load configuration from environment variables."""
```

**Environment Variables**:
- `HMAC_PRODUCER_ENABLED=true|false` (default: true)
- `HMAC_PRODUCER_SECRET=<secret-key>` (required if enabled)
- `PRODUCER_ID=mt5-gold-trader` (default from hostname)
- `OUTBOUND_SERVER_URL=https://api.example.com` (required)
- `OUTBOUND_TIMEOUT_SECONDS=30` (default: 30)

**Validation**:
- Raises `ValueError` if required vars missing
- Raises `ValueError` if secret too short (<16 bytes)
- Raises `ValueError` if timeout < 5 seconds

---

#### 3. `backend/app/trading/outbound/hmac.py` (120 lines)
**Purpose**: HMAC-SHA256 signature generation and verification

**Core Functions**:

##### `build_signature(secret: bytes, body: bytes, timestamp: str, producer_id: str) -> str`
**Algorithm**:
```
Canonical Request Format:
  METHOD:POST
  ENDPOINT:/api/v1/signals/ingest
  TIMESTAMP:<RFC3339 ISO format>
  PRODUCER_ID:<producer_id>
  BODY_SHA256:<base64(sha256(body))>

Signature = base64(HMAC-SHA256(secret, canonical_request))
```

**Parameters**:
- `secret`: HMAC secret key (bytes)
- `body`: Request body (bytes)
- `timestamp`: RFC3339 formatted timestamp (e.g., "2025-10-25T14:30:45.123456Z")
- `producer_id`: Producer identifier

**Returns**: Base64-encoded HMAC-SHA256 signature

**Example**:
```python
signature = build_signature(
    secret=b"my-secret-key",
    body=b'{"instrument":"GOLD","side":"buy"}',
    timestamp="2025-10-25T14:30:45.123456Z",
    producer_id="mt5-trader-1"
)
# Returns: "aBcDeFgHiJkLmNoPqRsTuVwXyZ1234567890=="
```

**Error Handling**:
- Raises `ValueError` if timestamp not RFC3339 format
- Raises `ValueError` if body empty
- Raises `ValueError` if secret empty

---

##### `verify_signature(secret: bytes, body: bytes, timestamp: str, producer_id: str, provided_signature: str) -> bool`
**Purpose**: Verify a signature (for testing + future server-side use)

**Algorithm**: Regenerate signature and compare with timing-safe comparison

**Returns**: True if signature matches, False otherwise

**Implementation Detail**: Use `hmac.compare_digest()` to prevent timing attacks

---

#### 4. `backend/app/trading/outbound/client.py` (250 lines)
**Purpose**: HTTP client for posting HMAC-signed signals to server

**Main Class**: `HmacClient`

```python
class HmacClient:
    """Async HTTP client for posting HMAC-signed signals."""

    def __init__(self, config: OutboundConfig, logger: Logger):
        """Initialize client with configuration."""
        self.config = config
        self.logger = logger
        self._session: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        """Context manager entry."""

    async def __aexit__(self, *args):
        """Context manager exit (close HTTP session)."""

    async def post_signal(
        self,
        signal: SignalCandidate,
        idempotency_key: Optional[str] = None,
        timeout: Optional[float] = None
    ) -> SignalIngestResponse:
        """
        Post a signal to the server with HMAC authentication.

        Args:
            signal: SignalCandidate object to send
            idempotency_key: UUID for idempotent retries
            timeout: Request timeout (overrides config)

        Returns:
            SignalIngestResponse with server's response

        Raises:
            OutboundClientError: On validation/network failure
            TimeoutError: On request timeout
        """
```

**Workflow**:
1. Validate signal (size, fields)
2. Serialize to JSON (canonical order)
3. Generate timestamp (RFC3339)
4. Calculate HMAC signature
5. Build HTTP headers
6. POST to server
7. Parse response
8. Emit telemetry
9. Log result

**HTTP Headers**:
```
POST /api/v1/signals/ingest HTTP/1.1
Host: api.example.com
Content-Type: application/json
X-Producer-Id: mt5-trader-1
X-Timestamp: 2025-10-25T14:30:45.123456Z
X-Signature: <base64-HMAC-SHA256>
X-Idempotency-Key: <uuid-for-retries>
User-Agent: TeleBot/1.0 (MT5 Signal Client)
```

**Error Handling**:
- Network error (ConnectionError): Log + raise OutboundClientError
- HTTP 4xx/5xx: Parse error response, log details, raise OutboundClientError
- Timeout: Raise TimeoutError (for PR-018 retry logic)
- Invalid response: Log + raise OutboundClientError

**Telemetry Emission**:
```python
self.metrics.counter(
    "signals_posted_total",
    labels={"result": "success", "http_code": 201}
)
self.metrics.histogram(
    "signals_posted_duration_seconds",
    value=elapsed_seconds
)
```

**Request Body Serialization** (canonical JSON order):
```python
body = {
    "instrument": signal.instrument,
    "side": signal.side,  # "buy" or "sell"
    "entry_price": float(signal.entry_price),
    "take_profit": float(signal.take_profit) if signal.take_profit else None,
    "stop_loss": float(signal.stop_loss) if signal.stop_loss else None,
    "risk_percent": signal.risk_percent,
    "comment": signal.comment,
    "strategy_name": signal.strategy_name,
    "timestamp": signal.timestamp.isoformat(),
}
```

---

#### 5. `backend/app/trading/outbound/responses.py` (60 lines)
**Purpose**: Response models for signal ingest

**Pydantic Models**:

##### `SignalIngestResponse`
```python
class SignalIngestResponse(BaseModel):
    """Server response to signal ingest."""

    signal_id: str                          # Server-assigned signal ID
    status: str                             # "received", "pending_approval", "rejected"
    server_timestamp: datetime              # Server timestamp for audit
    message: Optional[str] = None           # Optional server message
    errors: Optional[list[str]] = None      # Validation errors (if rejected)

    class Config:
        use_enum_values = True
```

##### `OutboundClientError`
```python
class OutboundClientError(Exception):
    """Base exception for outbound client failures."""

    def __init__(self, message: str, http_code: Optional[int] = None, details: Optional[dict] = None):
        self.message = message
        self.http_code = http_code
        self.details = details or {}
```

---

#### 6. `backend/tests/test_outbound_hmac.py` (300 lines)
**Purpose**: Unit tests for HMAC signature generation

**Test Cases** (13 tests):

##### Test Group 1: Signature Generation (5 tests)
1. `test_build_signature_happy_path` - Correct signature generation
2. `test_build_signature_deterministic` - Same inputs → same signature
3. `test_build_signature_sensitive_to_body` - Different body → different signature
4. `test_build_signature_sensitive_to_timestamp` - Different timestamp → different signature
5. `test_build_signature_sensitive_to_producer_id` - Different producer_id → different signature

##### Test Group 2: Signature Verification (4 tests)
6. `test_verify_signature_valid` - Valid signature passes
7. `test_verify_signature_invalid_signature` - Bad signature fails
8. `test_verify_signature_invalid_timestamp_format` - Malformed timestamp rejected
9. `test_verify_signature_timing_safe_comparison` - Uses timing-safe comparison

##### Test Group 3: Error Handling (4 tests)
10. `test_build_signature_empty_secret_raises` - Empty secret → ValueError
11. `test_build_signature_empty_body_raises` - Empty body → ValueError
12. `test_build_signature_invalid_timestamp_format_raises` - Bad timestamp → ValueError
13. `test_build_signature_large_body_handled` - Large payload supported

---

#### 7. `backend/tests/test_outbound_client.py` (400 lines)
**Purpose**: Integration tests for HmacClient

**Test Cases** (18 tests):

##### Test Group 1: Client Initialization (3 tests)
1. `test_hmac_client_init_from_config` - Client initializes with config
2. `test_hmac_client_from_env_loads_config` - Loads from environment
3. `test_hmac_client_init_missing_secret_raises` - Missing secret → ValueError

##### Test Group 2: Signal Posting - Happy Path (4 tests)
4. `test_post_signal_success_201` - POST → 201 response
5. `test_post_signal_sets_headers_correctly` - Headers include X-Producer-Id, X-Timestamp, X-Signature
6. `test_post_signal_serializes_json_canonical_order` - JSON keys in alphabetical order
7. `test_post_signal_returns_server_response` - Parses SignalIngestResponse correctly

##### Test Group 3: Signal Validation (3 tests)
8. `test_post_signal_rejects_empty_instrument` - Empty instrument → OutboundClientError
9. `test_post_signal_rejects_body_too_large` - Body > max_body_size → OutboundClientError
10. `test_post_signal_rejects_invalid_side` - Invalid side → OutboundClientError

##### Test Group 4: Error Handling (5 tests)
11. `test_post_signal_handles_network_error` - ConnectionError → OutboundClientError
12. `test_post_signal_handles_timeout` - Request timeout → TimeoutError
13. `test_post_signal_handles_http_400` - Server 400 → OutboundClientError with details
14. `test_post_signal_handles_http_500` - Server 500 → OutboundClientError
15. `test_post_signal_handles_invalid_response_json` - Malformed JSON → OutboundClientError

##### Test Group 5: Telemetry (3 tests)
16. `test_post_signal_emits_success_metric` - Success → signals_posted_total{result=success}
17. `test_post_signal_emits_duration_histogram` - Emits signals_posted_duration_seconds
18. `test_post_signal_emits_failure_metric` - Failure → signals_posted_total{result=failure}

**Mock Strategy**:
- Use `pytest-httpx` to mock HTTP responses
- Mock metrics client to verify telemetry
- Use `freezegun` to control timestamps in tests

---

#### 8. `backend/app/trading/outbound/exceptions.py` (25 lines)
**Purpose**: Exception hierarchy for outbound module

**Exceptions**:
```python
class OutboundError(Exception):
    """Base exception for outbound module."""
    pass

class OutboundClientError(OutboundError):
    """Signal posting failed."""
    pass

class OutboundSignatureError(OutboundError):
    """HMAC signature generation/verification failed."""
    pass
```

---

## 🗄️ Database Impact

**None** - PR-017 is purely a client-side outbound module. No database schema changes.

---

## 🔐 Security Checklist

### HMAC Signing
- ✅ SHA256 (cryptographically strong)
- ✅ Base64 encoding (safe for transmission)
- ✅ Timing-safe comparison (prevents timing attacks on signature verification)
- ✅ Secret from environment (never hardcoded)

### Input Validation
- ✅ Timestamp RFC3339 format validation
- ✅ Body size limits (max 64 KB)
- ✅ Signal field validation (instrument, side)
- ✅ No sensitive data in logs (secrets redacted)

### Network Security
- ✅ HTTPS only (enforced by server_base_url format)
- ✅ Connection timeout (prevents hanging)
- ✅ User-Agent header (identifies client)
- ✅ Idempotency key support (prevents duplicate processing)

### Error Handling
- ✅ No stack traces to user (logged, generic response)
- ✅ No secret material in exceptions
- ✅ Detailed logging for debugging (with context)

---

## 📊 Telemetry & Monitoring

### Metrics

#### Counter: `signals_posted_total`
```
Labels:
  - result: "success" | "failure" | "timeout" | "validation_error"
  - http_code: 201 | 400 | 401 | 500 | etc.
  - producer_id: <producer_id>

Example:
  signals_posted_total{result="success", http_code=201} = 1
  signals_posted_total{result="failure", http_code=500} = 2
```

#### Histogram: `signals_posted_duration_seconds`
```
Labels:
  - result: "success" | "failure"
  - producer_id: <producer_id>

Buckets: [0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0]

Example:
  signals_posted_duration_seconds_bucket{result="success", le="0.5"} = 45
  signals_posted_duration_seconds_sum{result="success"} = 12.5
```

### Logging

**INFO Level** (normal operations):
```json
{
  "timestamp": "2025-10-25T14:30:45.123456Z",
  "level": "INFO",
  "message": "Signal posted successfully",
  "producer_id": "mt5-trader-1",
  "signal_id": "sig_abc123",
  "server_signal_id": "srv_xyz789",
  "duration_ms": 234,
  "http_code": 201
}
```

**WARN Level** (recoverable issues):
```json
{
  "timestamp": "2025-10-25T14:30:45.123456Z",
  "level": "WARN",
  "message": "Signal post failed, retry recommended",
  "producer_id": "mt5-trader-1",
  "signal_id": "sig_abc123",
  "http_code": 500,
  "error": "Internal server error"
}
```

**ERROR Level** (permanent failures):
```json
{
  "timestamp": "2025-10-25T14:30:45.123456Z",
  "level": "ERROR",
  "message": "Signal validation failed",
  "producer_id": "mt5-trader-1",
  "signal_id": "sig_abc123",
  "error": "instrument must be non-empty",
  "error_type": "OutboundClientError"
}
```

---

## ✅ Acceptance Criteria

**Criterion 1: HMAC Signature Generation**
- ✅ `build_signature()` generates SHA256 HMAC
- ✅ Signature is base64-encoded
- ✅ Same inputs always produce same signature
- ✅ Different body/timestamp/producer_id → different signature
- **Test**: `test_build_signature_deterministic`

**Criterion 2: HTTP Headers**
- ✅ `X-Producer-Id` header set correctly
- ✅ `X-Timestamp` in RFC3339 format
- ✅ `X-Signature` contains base64 HMAC
- ✅ `X-Idempotency-Key` (UUID) included for retries
- **Test**: `test_post_signal_sets_headers_correctly`

**Criterion 3: Signal Serialization**
- ✅ JSON request body matches canonical format
- ✅ All signal fields present (instrument, side, price, TP, SL, etc.)
- ✅ Numeric fields properly formatted (float, not string)
- ✅ Timestamps in ISO format
- **Test**: `test_post_signal_serializes_json_canonical_order`

**Criterion 4: HTTP POST to Server**
- ✅ Client POSTs to configured server URL
- ✅ Endpoint is `/api/v1/signals/ingest`
- ✅ Content-Type is `application/json`
- ✅ Request timeout enforced
- **Test**: `test_post_signal_success_201`

**Criterion 5: Server Response Handling**
- ✅ 201 → Parse and return SignalIngestResponse
- ✅ 4xx → Log error details, raise OutboundClientError
- ✅ 5xx → Log error, raise OutboundClientError (retry candidate)
- ✅ Timeout → Raise TimeoutError (for PR-018 retry logic)
- **Tests**: `test_post_signal_handles_*` (5 tests)

**Criterion 6: Input Validation**
- ✅ Empty instrument rejected
- ✅ Invalid side (not "buy"/"sell") rejected
- ✅ Body size exceeds max → rejected
- ✅ Errors include clear error messages
- **Tests**: `test_post_signal_rejects_*` (3 tests)

**Criterion 7: Telemetry**
- ✅ `signals_posted_total` counter emitted (success/failure)
- ✅ `signals_posted_duration_seconds` histogram emitted
- ✅ Labels include producer_id, http_code, result
- ✅ Logging structured (JSON format)
- **Tests**: `test_post_signal_emits_*` (3 tests)

**Criterion 8: Error Messages**
- ✅ Clear error messages for validation failures
- ✅ HTTP error details logged (not exposed to caller)
- ✅ No secrets in logs or exceptions
- ✅ Request/response (non-sensitive parts) logged for debugging
- **Tests**: Various error handling tests

**Criterion 9: Configuration Management**
- ✅ Config loads from environment variables
- ✅ Missing required vars → ValueError with clear message
- ✅ Secret validation (minimum length check)
- ✅ Defaults for optional vars
- **Test**: `test_hmac_client_from_env_loads_config`

**Criterion 10: Code Quality**
- ✅ 100% type hints (all functions)
- ✅ All functions have docstrings with examples
- ✅ Black formatted (88-char lines)
- ✅ All classes have __repr__ for debugging
- ✅ All public functions have error documentation
- ✅ No TODOs or placeholders
- **Validation**: `black --check backend/app/trading/outbound/`

---

## 🧪 Test Strategy

### Unit Tests (18 tests)
- HMAC generation: 5 tests
- HMAC verification: 4 tests
- Error handling: 4 tests
- Client initialization: 3 tests
- Configuration: 2 tests

### Integration Tests (18 tests)
- Client POST success: 4 tests
- Server error handling: 5 tests
- Input validation: 3 tests
- Telemetry: 3 tests
- Configuration from env: 3 tests

### Test Coverage Target
- **Minimum**: 85% (httpx mocking adds complexity)
- **Target**: 90%
- **Stretch**: 95%

### Mock Strategy
- HTTP responses: `pytest-httpx` library
- Metrics/logging: Mock logger, counter, histogram
- Timestamps: `freezegun` for RFC3339 control
- Environment vars: `monkeypatch`

---

## 📅 Implementation Timeline

### Phase 1: Planning (Now) ✅
- Extract PR-017 specification
- Design architecture
- Plan test strategy
- Estimate effort
- **Duration**: 30 minutes
- **Deliverable**: This document

### Phase 2: Implementation (1.5 hours)
**Step 1** (20 min): Create core HMAC module
- `config.py` - Configuration (45 lines)
- `hmac.py` - Signature generation (120 lines)
- `responses.py` - Response models (60 lines)
- `exceptions.py` - Exception hierarchy (25 lines)

**Step 2** (30 min): Create HTTP client
- `client.py` - Main posting client (250 lines)
- `__init__.py` - Module exports (15 lines)

**Step 3** (20 min): Documentation
- Docstrings in all files
- README.md with usage examples

### Phase 3: Testing (1.5 hours)
**Step 1** (45 min): HMAC tests
- `test_outbound_hmac.py` (13 tests, 300 lines)
- All signature generation/verification covered
- Error cases tested

**Step 2** (45 min): Client tests
- `test_outbound_client.py` (18 tests, 400 lines)
- All HTTP paths covered
- Telemetry validation
- Error scenarios

**Validation**:
- Run: `.venv/Scripts/python.exe -m pytest backend/tests/test_outbound_*.py -v`
- Coverage: `.venv/Scripts/python.exe -m pytest backend/tests/test_outbound_*.py --cov=backend/app/trading/outbound`
- Target: ≥90% coverage

### Phase 4: Verification (30 min)
- ✅ All tests passing locally
- ✅ Coverage ≥90%
- ✅ Black formatting compliant
- ✅ Type hints complete
- ✅ No TODOs or placeholders

**Commands**:
```bash
# Test execution
.venv/Scripts/python.exe -m pytest backend/tests/test_outbound_*.py -v

# Coverage check
.venv/Scripts/python.exe -m pytest backend/tests/test_outbound_*.py --cov=backend/app/trading/outbound --cov-report=html

# Format check
.venv/Scripts/python.exe -m black --check backend/app/trading/outbound/

# Type check
.venv/Scripts/python.exe -m mypy backend/app/trading/outbound/
```

### Phase 5: Documentation (45 min)
- ✅ IMPLEMENTATION-COMPLETE.md (deployment checklist)
- ✅ ACCEPTANCE-CRITERIA.md (test specification)
- ✅ BUSINESS-IMPACT.md (revenue/strategic value)
- ✅ Update CHANGELOG.md
- ✅ Create quick reference guide

**Total Effort**: ~4.5 hours

---

## 🚀 Deployment Readiness

### Environment Variables (Required)
```bash
HMAC_PRODUCER_ENABLED=true
HMAC_PRODUCER_SECRET=<base64-secret-key-min-32-chars>
PRODUCER_ID=mt5-gold-trader-prod
OUTBOUND_SERVER_URL=https://api.prod.example.com
OUTBOUND_TIMEOUT_SECONDS=30
```

### Backward Compatibility
- ✅ No breaking changes to existing APIs
- ✅ Optional feature (can disable with HMAC_PRODUCER_ENABLED=false)
- ✅ No database schema changes

### Monitoring Setup
- ✅ Prometheus scrapers configured for signals_posted_total counter
- ✅ Alerts set on failure rates (>5% over 5 minutes)
- ✅ Dashboards display signals_posted_duration_seconds histogram

### Rollback Plan
- ✅ Feature flag: Set HMAC_PRODUCER_ENABLED=false to disable
- ✅ No data migration needed
- ✅ Revert code changes: `git revert <pr-017-commit>`

---

## 📚 Deliverables Summary

| File | Lines | Purpose |
|------|-------|---------|
| `config.py` | 45 | Configuration management |
| `hmac.py` | 120 | HMAC-SHA256 signature generation |
| `client.py` | 250 | Async HTTP POST client |
| `responses.py` | 60 | Response models |
| `exceptions.py` | 25 | Exception hierarchy |
| `__init__.py` | 15 | Module exports |
| `test_outbound_hmac.py` | 300 | 13 unit tests for HMAC |
| `test_outbound_client.py` | 400 | 18 integration tests for client |
| **Total Code** | **1,215** | **Production-ready code** |

---

## 🔗 Dependencies & Integration

### Upstream Dependencies
- **PR-014** (SignalCandidate): Used as input to `post_signal()`
- **PR-016** (Trade Store): Optional for trade context

### Downstream Dependents
- **PR-018** (Retries/Backoff): Wraps HmacClient with retry logic
- **PR-021** (Server Ingest): Validates signatures from PR-017

### Integration with Existing Code
- **Core Settings** (PR-002): Uses OutboundConfig pattern
- **Logging** (PR-003): Structured JSON logging
- **Metrics** (PR-009): Emits prometheus metrics

---

## ✨ Success Metrics

### Code Quality
- ✅ 100% type hints
- ✅ 100% docstrings
- ✅ ≥90% test coverage
- ✅ 0 linting errors
- ✅ Black formatted

### Functionality
- ✅ HMAC signatures cryptographically correct
- ✅ All HTTP response codes handled
- ✅ Telemetry emitted correctly
- ✅ Configuration management working
- ✅ Error messages clear and actionable

### Security
- ✅ No secrets in logs
- ✅ Timing-safe signature comparison
- ✅ Input validation on all boundaries
- ✅ HTTPS enforced

### Deployment
- ✅ All tests pass in CI/CD
- ✅ No breaking changes
- ✅ Feature flag works correctly
- ✅ Rollback procedure documented

---

## 🎯 Next Steps After PR-017

### Immediate (PR-018)
- Add retry/backoff wrapper around HmacClient
- Implement Telegram alerts on permanent failures
- Add exponential backoff with jitter

### Short-term (PR-019-020)
- Production trading loop hardening
- Charts/analytics integration
- Live bot enhancements

### Medium-term (Phase 2)
- Server-side signal ingestion (PR-021)
- User approvals workflow
- Analytics dashboard

---

## 📝 Phase 1 Completion Checklist

- [x] PR-017 specification extracted from master doc
- [x] Architecture designed (HMAC, client, config)
- [x] File structure planned (8 files, 1,215 lines)
- [x] Test strategy defined (31 tests, 700 lines)
- [x] Dependencies validated (PR-014, PR-016 ready)
- [x] Security checklist complete
- [x] Telemetry plan documented
- [x] Deployment readiness assessed
- [x] Integration points mapped
- [x] Timeline estimated (4.5 hours)
- [x] This document created

**Phase 1 Status**: ✅ **COMPLETE**

---

**Ready for Phase 2 Implementation**

Next Action: Begin Phase 2 (Implementation)
- Create backend/app/trading/outbound/config.py
- Create backend/app/trading/outbound/hmac.py
- Create backend/app/trading/outbound/client.py
- Continue with remaining files...
