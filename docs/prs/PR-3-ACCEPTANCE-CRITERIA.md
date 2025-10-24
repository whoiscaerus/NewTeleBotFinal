# PR-3: Signals Domain v1 - Acceptance Criteria

**Status:** 🔄 IN PROGRESS  
**Target Coverage:** ≥90% backend, ≥70% frontend  
**Test Cases:** 42 required  

---

## ✅ Acceptance Criteria Matrix

Each criterion is verified by specific test case(s). All must pass before merge.

---

## 🎯 HAPPY PATH ACCEPTANCE CRITERIA

### AC-1: Valid Signal Ingestion
**Criterion:** System accepts valid signal and returns 201 Created

**Test Cases:**
```
test_create_signal_valid_minimal              [REQUIRED]
test_create_signal_valid_with_payload         [REQUIRED]
test_signal_persisted_in_database             [REQUIRED]
```

**Expected Behavior:**
- Input: SignalCreate with instrument="XAUUSD", side=0, time=now, payload={optional}
- Response: 201 Created with SignalOut (id, status=0, created_at)
- Database: Signal row exists with exact values
- No errors or warnings in logs

**Verification:**
```python
✓ response.status_code == 201
✓ response.json()["id"] is not None
✓ response.json()["status"] == 0
✓ db.query(Signal).filter_by(id=response.json()["id"]).first() is not None
```

---

### AC-2: Response Format Compliance
**Criterion:** SignalOut response matches exact schema

**Test Cases:**
```
test_response_format_complete
test_response_has_all_required_fields
```

**Expected Fields:**
- `id`: string (UUID)
- `status`: integer (0)
- `created_at`: ISO8601 datetime
- No extra fields (strict)

**Verification:**
```python
✓ response.json() has exactly 3 keys
✓ isinstance(response.json()["id"], str)
✓ isinstance(response.json()["created_at"], str)
```

---

## 🚫 INPUT VALIDATION ACCEPTANCE CRITERIA

### AC-3: Instrument Validation
**Criterion:** Invalid instrument codes rejected with 422

**Test Cases:**
```
test_invalid_instrument_uppercase_only
test_invalid_instrument_numbers_and_underscores
test_invalid_instrument_too_short
test_invalid_instrument_too_long
test_invalid_instrument_special_chars
test_valid_instrument_min_length
test_valid_instrument_max_length
```

**Valid Pattern:** `^[A-Z0-9._-]{2,20}$`

**Test Matrix:**
| Instrument | Valid | Reason |
|------------|-------|--------|
| A | ❌ | Too short (1 char) |
| XY | ✅ | Min length (2 chars) |
| XAUUSD | ✅ | Standard format |
| EURUSD_M15 | ✅ | Underscore allowed |
| GOLD.SPOT | ✅ | Dot allowed |
| BTC-USD | ✅ | Dash allowed |
| XY**** | ❌ | Special char * not allowed |
| xauusd | ❌ | Lowercase not allowed |
| XAUUSDEXTRALONG2X | ❌ | Too long (21 chars) |
| EUR USD | ❌ | Space not allowed |

**Verification:**
```python
✓ response.status_code == 422
✓ "instrument" in response.json()["detail"][0]["loc"]
✓ "string_pattern" in response.json()["detail"][0]["type"]
```

---

### AC-4: Side (Buy/Sell) Validation
**Criterion:** Only side 0 (buy) or 1 (sell) accepted

**Test Cases:**
```
test_side_zero_valid
test_side_one_valid
test_side_negative_invalid
test_side_two_invalid
test_side_string_invalid
test_side_null_invalid
```

**Verification:**
```python
✓ side=0 → 201 Created
✓ side=1 → 201 Created
✓ side=-1 → 422 Unprocessable Entity
✓ side=2 → 422 Unprocessable Entity
✓ side="buy" → 422 Unprocessable Entity
✓ side=null → 422 Unprocessable Entity
```

---

### AC-5: Timestamp Format Validation
**Criterion:** Time must be ISO8601 datetime, not past or future

**Test Cases:**
```
test_time_iso8601_valid
test_time_past_valid
test_time_future_valid
test_time_malformed_invalid
test_time_unix_epoch_invalid
test_time_missing_tz_invalid
```

**Valid Formats:**
- ✅ `2024-01-15T10:30:45Z`
- ✅ `2024-01-15T10:30:45+00:00`
- ✅ `2024-01-15T10:30:45.123456Z`

**Invalid Formats:**
- ❌ `01-15-2024 10:30:45` (wrong order)
- ❌ `2024-01-15 10:30:45` (missing timezone)
- ❌ `1705317045` (Unix epoch)
- ❌ `2024/01/15` (date only)

**Verification:**
```python
✓ response.status_code == 422 for malformed
✓ Error message mentions "datetime"
```

---

### AC-6: Payload Validation (Structure)
**Criterion:** Payload must be valid JSON object (dict) if provided

**Test Cases:**
```
test_payload_valid_empty_dict
test_payload_valid_nested_dict
test_payload_invalid_array
test_payload_invalid_string
test_payload_invalid_number
test_payload_null
```

**Verification:**
```python
✓ payload={} → 201 Created
✓ payload={"rsi": 75, "bb": {"upper": 100}} → 201 Created
✓ payload=[] → 422 Unprocessable Entity
✓ payload="string" → 422 Unprocessable Entity
✓ payload=123 → 422 Unprocessable Entity
✓ payload=null → 201 Created (optional field)
```

---

## 📏 PAYLOAD SIZE ACCEPTANCE CRITERIA

### AC-7: Payload Size Limits
**Criterion:** Payload capped at 32KB, larger requests rejected with 413

**Test Cases:**
```
test_payload_1kb_valid
test_payload_16kb_valid
test_payload_32kb_valid
test_payload_32kb_1byte_invalid
test_payload_64kb_invalid
```

**Size Matrix:**
| Size | Status | Code |
|------|--------|------|
| 1KB | ✅ Accepted | 201 |
| 16KB | ✅ Accepted | 201 |
| 32KB | ✅ Accepted | 201 |
| 32KB + 1 byte | ❌ Rejected | 413 |
| 64KB | ❌ Rejected | 413 |

**Verification:**
```python
✓ 32KB payload → 201 Created
✓ 32KB+1 payload → 413 Payload Too Large
✓ Response includes Content-Length header
```

---

## 🔐 HMAC AUTHENTICATION ACCEPTANCE CRITERIA

### AC-8: HMAC Disabled (Default)
**Criterion:** When HMAC_PRODUCER_ENABLED=false, signature validation skipped

**Test Cases:**
```
test_hmac_disabled_no_headers_allowed
test_hmac_disabled_with_headers_ignored
test_hmac_disabled_missing_producer_id_allowed
test_hmac_disabled_missing_signature_allowed
test_hmac_disabled_missing_timestamp_allowed
```

**Environment:** `HMAC_PRODUCER_ENABLED=false`

**Behavior:**
- Requests with NO HMAC headers → 201 Created ✅
- Requests WITH HMAC headers → 201 Created ✅ (headers ignored)
- All fields optional when disabled

**Verification:**
```python
# No headers
response = client.post("/api/v1/signals", json=signal_data)
assert response.status_code == 201

# With headers but disabled
response = client.post(
    "/api/v1/signals",
    json=signal_data,
    headers={"X-Producer-Id": "test"}
)
assert response.status_code == 201
```

---

### AC-9: HMAC Enabled (Production)
**Criterion:** When HMAC_PRODUCER_ENABLED=true, all HMAC fields required

**Test Cases:**
```
test_hmac_enabled_missing_producer_id
test_hmac_enabled_missing_signature
test_hmac_enabled_missing_timestamp
test_hmac_enabled_empty_producer_id
```

**Environment:** `HMAC_PRODUCER_ENABLED=true`, `HMAC_PRODUCER_SECRET=test-secret`

**Required Headers:**
- `X-Producer-Id`: Non-empty string
- `X-Timestamp`: ISO8601 datetime (recent)
- `X-Signature`: Base64-encoded HMAC-SHA256

**Verification:**
```python
✓ No X-Producer-Id → 401 Unauthorized
✓ No X-Signature → 401 Unauthorized
✓ No X-Timestamp → 401 Unauthorized
✓ Empty X-Producer-Id="" → 400 Bad Request
```

---

### AC-10: HMAC Signature Validation
**Criterion:** Signature must be valid HMAC-SHA256 of (body + timestamp + producer_id)

**Test Cases:**
```
test_hmac_valid_signature
test_hmac_invalid_signature
test_hmac_wrong_producer_id
test_hmac_tampered_body
test_hmac_modified_timestamp
```

**Signature Format:**
```
secret = "test-secret"
canonical = f"{body}{timestamp}{producer_id}"
signature = base64.b64encode(hmac.new(
    secret.encode(),
    canonical.encode(),
    hashlib.sha256
).digest())
```

**Verification:**
```python
# Valid signature
response = client.post(
    "/api/v1/signals",
    json=signal_data,
    headers={
        "X-Producer-Id": "producer-1",
        "X-Timestamp": "2024-01-15T10:30:45Z",
        "X-Signature": "VALID_BASE64_HMAC"
    }
)
assert response.status_code == 201

# Invalid signature
response = client.post(
    "/api/v1/signals",
    json=signal_data,
    headers={
        "X-Producer-Id": "producer-1",
        "X-Timestamp": "2024-01-15T10:30:45Z",
        "X-Signature": "INVALID_BASE64_HMAC"
    }
)
assert response.status_code == 401
```

---

### AC-11: HMAC Clock Skew Tolerance
**Criterion:** Timestamp must be within 5 minutes (±300 seconds)

**Test Cases:**
```
test_hmac_clock_skew_current_time
test_hmac_clock_skew_1_minute_old
test_hmac_clock_skew_4_minutes_59_seconds_old
test_hmac_clock_skew_exactly_5_minutes_old
test_hmac_clock_skew_5_minutes_1_second_old
test_hmac_clock_skew_10_minutes_old
test_hmac_clock_skew_future_time_allowed
```

**Clock Window:**
```
±5 minutes (300 seconds)
current_time - 300s ≤ request_timestamp ≤ current_time + 300s
```

**Verification:**
```python
# Valid (0s skew)
ts = datetime.utcnow()
response = client.post(..., headers={..., "X-Timestamp": ts.isoformat() + "Z"})
assert response.status_code == 201

# Valid (299s old)
ts = datetime.utcnow() - timedelta(seconds=299)
response = client.post(..., headers={..., "X-Timestamp": ts.isoformat() + "Z"})
assert response.status_code == 201

# Valid (300s old - edge case)
ts = datetime.utcnow() - timedelta(seconds=300)
response = client.post(..., headers={..., "X-Timestamp": ts.isoformat() + "Z"})
assert response.status_code == 201

# Invalid (301s old)
ts = datetime.utcnow() - timedelta(seconds=301)
response = client.post(..., headers={..., "X-Timestamp": ts.isoformat() + "Z"})
assert response.status_code == 401

# Invalid (future beyond 5 min)
ts = datetime.utcnow() + timedelta(seconds=301)
response = client.post(..., headers={..., "X-Timestamp": ts.isoformat() + "Z"})
assert response.status_code == 401
```

---

### AC-12: HMAC Signature Encoding
**Criterion:** Signature must be valid base64

**Test Cases:**
```
test_hmac_signature_valid_base64
test_hmac_signature_invalid_base64
test_hmac_signature_non_ascii
```

**Verification:**
```python
# Valid base64
response = client.post(..., headers={..., "X-Signature": "dGVzdA=="})
# May be 401 (invalid HMAC) but not 400 (format error)

# Invalid base64
response = client.post(..., headers={..., "X-Signature": "!!!invalid!!!"})
assert response.status_code == 400  # Bad format
```

---

## 🗄️ DATABASE PERSISTENCE ACCEPTANCE CRITERIA

### AC-13: Signal Stored with Correct Fields
**Criterion:** Signal persists to database with all fields populated correctly

**Test Cases:**
```
test_signal_id_matches_response
test_signal_instrument_persisted
test_signal_side_persisted
test_signal_time_persisted
test_signal_payload_persisted
test_signal_status_defaults_zero
test_signal_version_defaults_one
```

**Verification:**
```python
# Create signal via API
response = client.post("/api/v1/signals", json={
    "instrument": "XAUUSD",
    "side": 0,
    "time": "2024-01-15T10:30:45Z",
    "payload": {"rsi": 75}
})

# Query database
signal_id = response.json()["id"]
signal = db.query(Signal).filter_by(id=signal_id).first()

# Verify persistence
assert signal.instrument == "XAUUSD"
assert signal.side == 0
assert signal.payload == {"rsi": 75}
assert signal.status == 0
assert signal.version == 1
assert signal.created_at == response.json()["created_at"]
```

---

### AC-14: Timestamps Auto-Managed
**Criterion:** created_at and updated_at set automatically by database

**Test Cases:**
```
test_created_at_auto_set
test_updated_at_auto_set
test_updated_at_unchanged_on_read
```

**Verification:**
```python
# Immediately after create
before = datetime.utcnow()
response = client.post("/api/v1/signals", json=signal_data)
after = datetime.utcnow()

created_at_str = response.json()["created_at"]
created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))

assert before <= created_at <= after
assert created_at.tzinfo == timezone.utc
```

---

### AC-15: JSONB Payload Storage
**Criterion:** Payload stored as JSONB in PostgreSQL with data integrity

**Test Cases:**
```
test_payload_jsonb_nested_objects
test_payload_jsonb_arrays
test_payload_jsonb_numbers
test_payload_jsonb_nulls
test_payload_jsonb_unicode
```

**Sample Payloads:**
```python
payloads = [
    {"rsi": 75, "macd": -0.5},
    {"levels": [100, 105, 110]},
    {"name": "XAUUSD", "value": 1950.50},
    {"data": None},
    {"text": "测试数据"}  # Unicode
]

for payload in payloads:
    response = client.post(..., json={..., "payload": payload})
    signal = db.query(Signal).first()
    assert signal.payload == payload
```

---

### AC-16: Concurrent Signal Creation
**Criterion:** Multiple simultaneous signals don't deadlock or corrupt data

**Test Cases:**
```
test_concurrent_10_signals_no_deadlock
test_concurrent_100_signals_all_created
test_concurrent_signals_no_duplicate_ids
```

**Verification:**
```python
import asyncio

async def create_signal_async(i):
    return client.post("/api/v1/signals", json={
        "instrument": f"TEST{i:04d}",
        "side": i % 2,
        "time": datetime.utcnow().isoformat() + "Z",
        "payload": {"index": i}
    })

# Create 100 signals concurrently
responses = asyncio.run(asyncio.gather(*[
    create_signal_async(i) for i in range(100)
]))

# Verify all successful
assert all(r.status_code == 201 for r in responses)

# Verify all in database
signals = db.query(Signal).all()
assert len(signals) == 100

# Verify no duplicates
ids = [s.id for s in signals]
assert len(set(ids)) == 100  # All unique
```

---

## 🪵 LOGGING & OBSERVABILITY ACCEPTANCE CRITERIA

### AC-17: Signal Creation Logged
**Criterion:** Successful signal creation logged with request context

**Test Cases:**
```
test_log_contains_signal_id
test_log_contains_instrument
test_log_contains_side
test_log_level_info
test_log_not_contains_full_payload
```

**Expected Log Format (JSON):**
```json
{
  "level": "info",
  "message": "Signal created",
  "signal_id": "550e8400-e29b-41d4-a716-446655440000",
  "instrument": "XAUUSD",
  "side": 0,
  "producer_id": "producer-1",
  "timestamp": "2024-01-15T10:30:45.123456Z"
}
```

**Security Rule:** Payload values never logged (prevent information disclosure)

**Verification:**
```python
with caplog.at_level(logging.INFO):
    response = client.post("/api/v1/signals", json=signal_data)
    assert "Signal created" in caplog.text
    assert signal_id in caplog.text
    assert "XAUUSD" in caplog.text
    assert "raw_payload_content" not in caplog.text  # Never log payload
```

---

### AC-18: Validation Errors Logged
**Criterion:** Validation failures logged with error details

**Test Cases:**
```
test_log_invalid_instrument
test_log_missing_required_field
test_log_oversized_payload
test_log_hmac_validation_failure
```

**Verification:**
```python
with caplog.at_level(logging.WARNING):
    response = client.post("/api/v1/signals", json={
        "instrument": "INVALID!!!",
        "side": 0,
        "time": "2024-01-15T10:30:45Z"
    })
    assert response.status_code == 422
    assert "invalid" in caplog.text.lower()
```

---

### AC-19: HMAC Validation Logged (Audit Trail)
**Criterion:** All HMAC validation attempts logged for security audit

**Test Cases:**
```
test_log_hmac_validation_success
test_log_hmac_validation_failure
test_log_hmac_clock_skew_failure
```

**Log Entries (Always):**
```json
{
  "event": "hmac_validation_attempted",
  "producer_id": "producer-1",
  "result": "success|failure",
  "reason": "valid_signature|invalid_signature|clock_skew|missing_header",
  "timestamp": "2024-01-15T10:30:45.123456Z"
}
```

**Verification:**
```python
# Successful
with caplog.at_level(logging.INFO):
    response = client.post(..., headers=valid_hmac_headers)
    assert "hmac_validation" in caplog.text
    assert "success" in caplog.text

# Failed
with caplog.at_level(logging.INFO):
    response = client.post(..., headers=invalid_hmac_headers)
    assert response.status_code == 401
    assert "hmac_validation" in caplog.text
    assert "failure" in caplog.text
```

---

## 🔗 INTEGRATION ACCEPTANCE CRITERIA

### AC-20: Router Mounted in Main App
**Criterion:** Signals router properly integrated into FastAPI application

**Test Cases:**
```
test_signals_route_accessible
test_signals_route_under_api_v1_prefix
test_signals_route_404_when_unmounted
```

**Verification:**
```python
# Should work
response = client.post("/api/v1/signals", json=signal_data)
assert response.status_code in [201, 400, 401, 422]

# Should fail
response = client.post("/signals", json=signal_data)
assert response.status_code == 404  # Not at root

response = client.post("/api/v0/signals", json=signal_data)
assert response.status_code == 404  # Wrong API version
```

---

### AC-21: HTTP Status Codes Correct
**Criterion:** All responses use appropriate HTTP status codes

**Test Cases:**
```
test_status_201_on_success
test_status_400_on_bad_request
test_status_401_on_unauthorized
test_status_413_on_payload_too_large
test_status_422_on_validation_error
test_status_500_on_server_error
```

**Status Code Matrix:**
| Scenario | Code | Test |
|----------|------|------|
| Valid signal | 201 | test_valid_signal |
| Malformed JSON | 400 | test_malformed_json |
| Missing HMAC header | 401 | test_missing_hmac |
| Invalid HMAC | 401 | test_invalid_hmac |
| Payload 33KB | 413 | test_oversized_payload |
| Invalid instrument | 422 | test_invalid_instrument |
| DB connection error | 500 | test_db_error |

---

### AC-22: Content-Type Validation
**Criterion:** Only application/json accepted, rejects other types

**Test Cases:**
```
test_content_type_application_json_accepted
test_content_type_text_plain_rejected
test_content_type_application_xml_rejected
test_content_type_missing
```

**Verification:**
```python
# Accepted
response = client.post(
    "/api/v1/signals",
    json=signal_data,
    headers={"Content-Type": "application/json"}
)
assert response.status_code == 201

# Rejected
response = client.post(
    "/api/v1/signals",
    data="not json",
    headers={"Content-Type": "text/plain"}
)
assert response.status_code == 415  # Unsupported Media Type
```

---

## 📊 ERROR HANDLING ACCEPTANCE CRITERIA

### AC-23: Database Connection Errors
**Criterion:** Graceful handling of database connection failures

**Test Cases:**
```
test_db_connection_error_returns_500
test_db_connection_error_logged
test_db_timeout_returns_500
```

**Verification:**
```python
# Simulate DB connection error
with monkeypatch.setattr("db.add", side_effect=DBConnectionError):
    response = client.post("/api/v1/signals", json=signal_data)
    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error"  # Generic
```

---

### AC-24: Invalid JSON Handling
**Criterion:** Malformed JSON request bodies rejected

**Test Cases:**
```
test_invalid_json_syntax
test_invalid_json_trailing_comma
test_invalid_json_single_quote
```

**Verification:**
```python
response = client.post(
    "/api/v1/signals",
    data='{"instrument": "XAUUSD",}',  # Trailing comma
    headers={"Content-Type": "application/json"}
)
assert response.status_code == 400
assert "JSON" in response.json()["detail"]
```

---

### AC-25: Unknown Fields Handling
**Criterion:** Extra fields in request ignored (forward compatibility)

**Test Cases:**
```
test_unknown_field_ignored
test_multiple_unknown_fields_ignored
```

**Pydantic Config:** `extra = "ignore"`

**Verification:**
```python
response = client.post("/api/v1/signals", json={
    "instrument": "XAUUSD",
    "side": 0,
    "time": "2024-01-15T10:30:45Z",
    "unknown_field": "ignored",
    "another_field": 123
})
assert response.status_code == 201  # Still created
```

---

## 🧩 COMPLETE COVERAGE MATRIX

**Total Test Cases: 42+**

| Category | Count | Coverage |
|----------|-------|----------|
| Happy Path | 3 | Core flow |
| Input Validation | 8 | All fields |
| Payload Size | 3 | Limits |
| HMAC Disabled | 5 | Default mode |
| HMAC Enabled | 12 | Auth flow |
| DB Persistence | 4 | Data integrity |
| Logging | 3 | Observability |
| Integration | 5 | HTTP/routing |
| Error Handling | 3 | Failure modes |
| **TOTAL** | **46** | **100%** |

---

## ✅ FINAL VERIFICATION CHECKLIST

Before declaring PR-3 complete:

```
TESTS
□ All 42 tests passing locally
□ Coverage ≥90% for backend/app/signals/
□ No skipped or todo tests
□ pytest --cov output shows details

DATABASE
□ Migration 0002_signals creates table correctly
□ alembic upgrade head succeeds
□ alembic downgrade -1 removes table (rollback works)
□ Indexes created and queryable

API
□ POST /api/v1/signals returns 201 on valid input
□ HMAC validation works when enabled
□ HMAC ignored when disabled
□ All HTTP status codes correct

SECURITY
□ No raw payloads in logs
□ Secrets not hardcoded
□ HMAC-SHA256 implemented correctly
□ 5-minute clock skew enforced

LOGGING
□ Signal creation logged
□ Validation errors logged
□ HMAC attempts logged (audit trail)
□ No sensitive data exposed

DOCUMENTATION
□ PR-3-IMPLEMENTATION-PLAN.md complete ✅
□ PR-3-ACCEPTANCE-CRITERIA.md complete ✅ (this file)
□ Code has docstrings + type hints
□ Examples in docstrings

GITHUB ACTIONS
□ All checks passing (green ✅)
□ pytest passing with ≥90% coverage
□ black formatting compliant
□ ruff linting clean
□ No merge conflicts
```

---

**Next Phase:** Begin Phase 1 - Database layer implementation
