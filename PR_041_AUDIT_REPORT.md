# PR-041 AUDIT REPORT: MT5 EA SDK & Reference EA

**Audit Date**: October 27, 2025
**Status**: ⚠️ **INCOMPLETE - 65% Done**
**Blocking Issues**: 3 Critical
**Coverage**: ~35% of requirements met

---

## EXECUTIVE SUMMARY

PR-041 is **partially implemented** with SDK files created and backend routes working, but **3 critical issues block production readiness**:

1. ❌ **MISSING TELEMETRY METRICS** - No `ea_requests_total` or `ea_errors_total` counters
2. ❌ **INCOMPLETE HMAC IMPLEMENTATION** - MQL5 uses simplified hash, not real HMAC-SHA256
3. ❌ **MISSING COMPREHENSIVE TESTS** - No boundary case tests (stale timestamp, nonce reuse, replay)

**Verdict**: **NOT PRODUCTION READY** - Requires full implementation of telemetry + security tests

---

## DETAILED FINDINGS

### ✅ WHAT'S IMPLEMENTED (65%)

#### 1. MQL5 SDK Files Created
- ✅ `/ea-sdk/include/caerus_auth.mqh` - Auth structure (114 lines)
- ✅ `/ea-sdk/include/caerus_http.mqh` - HTTP client (150 lines)
- ✅ `/ea-sdk/include/caerus_models.mqh` - Data models (167 lines)
- ✅ `/ea-sdk/examples/ReferenceEA.mq5` - Reference EA (301 lines)
- ✅ `/ea-sdk/README.md` - Installation + usage guide (378 lines)

#### 2. Backend API Routes
- ✅ `GET /api/v1/client/poll` - Returns approved signals
- ✅ `POST /api/v1/client/ack` - Acknowledges execution
- ✅ Device authentication (X-Device-Id, X-Nonce, X-Timestamp, X-Signature headers)

#### 3. Backend Models
- ✅ `Device` model (PR-023a) - Device registration
- ✅ `Execution` model (PR-025) - Execution tracking
- ✅ Full RBAC + audit logging

#### 4. Some Tests
- ✅ Tests for poll/ack endpoints in `test_pr_024a_025_ea.py`
- ✅ Device authentication header validation

---

### ❌ CRITICAL ISSUES (3 BLOCKING)

#### Issue #1: MISSING TELEMETRY METRICS ❌ CRITICAL
**Location**: `backend/app/observability/metrics.py`
**Problem**: PR spec requires 2 metrics:
- `ea_requests_total{endpoint}` - Total API requests from EAs
- `ea_errors_total` - Total EA request errors

**Current State**:
- `metrics.py` has 170+ lines but **ZERO EA metrics defined**
- Only has billing, auth, signal, audit metrics
- **No recording methods** for EA telemetry

**Impact**:
- Cannot monitor EA health
- Cannot detect failures in production
- No observability into poll/ack volumes

**Fix Required**: Add 2 Counter metrics + 2 recording methods

---

#### Issue #2: INCOMPLETE HMAC IMPLEMENTATION ❌ CRITICAL
**Location**: `/ea-sdk/include/caerus_auth.mqh` (lines 68-89)

**Problem**: HMAC-SHA256 is FAKED:
```mqh
// WRONG: This is not real HMAC-SHA256!
string signature = "";
for(int i = 0; i < StringLen(message); i++)
{
    signature += StringFormat("%02x", message[i] * 31 % 256);
}
return signature;
```

**Issues**:
1. Simple modulo math, not cryptographic HMAC-SHA256
2. Comment admits: "This would require external DLL for production"
3. Signature is **NOT replay-resistant** (no nonce mixing)
4. Cannot be validated by backend (different algorithm!)

**Impact**:
- Signatures can be forged by attackers
- Authentication is NOT secure
- Won't pass security review
- **SECURITY BREACH**: Backend expects HMAC-SHA256, receives fake hash

**Fix Required**: Implement real HMAC-SHA256 or call MQL5 OpenSSL DLL

---

#### Issue #3: MISSING COMPREHENSIVE TESTS ❌ CRITICAL
**Missing Test Scenarios** (from PR spec):
- ❌ Stale timestamp rejected (>5 min old)
- ❌ Future timestamp rejected (>5 min in future)
- ❌ Nonce reuse rejected (Redis SETNX)
- ❌ Signature mismatch rejected
- ❌ Replayed webhook rejected
- ❌ Invalid nonce format rejected
- ❌ Boundary cases (empty body, malformed JSON)

**Current Test Coverage** (file: `test_pr_024a_025_ea.py`):
- ✅ Poll with valid HMAC (basic)
- ✅ Missing headers → 401
- ✅ Invalid signature → 401
- ✅ Ack placed (basic)
- ✅ Ack failed
- ✅ Poll returns only approved

**Missing**:
- ❌ Timestamp freshness tests
- ❌ Nonce replay detection tests
- ❌ MQL5 SDK boundary tests
- ❌ Integration tests (MQL5 ↔ Backend)
- ❌ Error recovery tests (network timeout, malformed response)

**Impact**:
- Cannot verify security requirements met
- Replay attacks not tested
- Edge cases not covered
- Nonce collision risk unknown

---

### ⚠️ SECONDARY ISSUES (3 Medium)

#### Issue #4: MQL5 HMAC Implementation Incomplete
**File**: `/ea-sdk/include/caerus_auth.mqh`

**Problems**:
1. `GetAuthHeader()` builds auth string but doesn't actually HMAC it correctly
2. Comment line 91: "Format: 'CaerusHMAC device_id:signature:nonce:timestamp'" - format correct but signature wrong
3. No validation of timestamp freshness
4. Nonce counter not seeded properly (uses `GetTickCount()` which can repeat)

**Fix Required**:
- Call real HMAC-SHA256 function (via DLL or native MQL5)
- Add timestamp validation (±300 seconds)
- Implement proper nonce generation

---

#### Issue #5: Missing XOR Obfuscation for Device Secrets
**File**: `ReferenceEA.mq5`

**Problem**: Device secret stored as plain text in EA inputs:
```mql5
input string DEVICE_SECRET = "device_secret_key_here";  // EXPOSED!
```

**PR Spec Says**: "Store secrets in EA input params with optional XOR obfuscation"

**Current State**: NO obfuscation implemented

**Risk**:
- Someone decompiling EA can read secret
- Memory dump can expose secret
- MT5 file backup contains secret in plain text

**Fix Required**:
- Add XOR cipher utility function
- Encrypt secret on input
- Decrypt at auth time

---

#### Issue #6: No JSON Parsing for Poll Response
**File**: `ReferenceEA.mq5` (line 112)

**Problem**: Poll response parsing is FAKE:
```mql5
void ParsePollResponse(string json_response)
{
    // Placeholder: In production, use JSON parser library
    // For now, set up test signals
    pending_count = 0;

    if(StringLen(json_response) > 0)
    {
        // ... creates HARDCODED test signal instead of parsing JSON ...
    }
}
```

**Issue**:
- Always returns fake signal (XAUUSD BUY)
- Never actually parses server response
- Real signals never received by EA

**Fix Required**:
- Implement JSON parser (or use library like `rapidjson`)
- Actually parse signal array from response
- Handle edge cases (empty array, malformed JSON)

---

## WHAT'S MISSING (35%)

### 🔴 CRITICAL MISSING PIECES

#### 1. Telemetry Metrics (MUST HAVE)
```python
# MISSING from metrics.py
self.ea_requests_total = Counter(
    "ea_requests_total",
    "Total EA API requests",
    ["endpoint"],  # /poll, /ack
    registry=self.registry,
)

self.ea_errors_total = Counter(
    "ea_errors_total",
    "Total EA request errors",
    ["endpoint", "error_type"],  # auth_failed, timeout, etc.
    registry=self.registry,
)

# MISSING recording methods
def record_ea_request(self, endpoint: str):
    self.ea_requests_total.labels(endpoint=endpoint).inc()

def record_ea_error(self, endpoint: str, error_type: str):
    self.ea_errors_total.labels(endpoint=endpoint, error_type=error_type).inc()
```

#### 2. Real HMAC-SHA256 Implementation (MUST HAVE)
Current fake implementation must be replaced with:
- Python backend: Already uses `hmac.sha256` ✅
- MQL5 SDK: **Needs real implementation** ❌

Options:
1. Call Windows Crypt API via DLL
2. Use MQL5's built-in hash functions if available
3. Create wrapper to Python backend for signature generation

#### 3. Comprehensive Security Tests (MUST HAVE)
```python
# MISSING test cases in test_pr_024a_025_ea.py

def test_poll_rejects_stale_timestamp():
    """Timestamp > 5 min old rejected"""
    # Create request with old timestamp
    # Assert 401 + "Timestamp too old"

def test_poll_rejects_future_timestamp():
    """Timestamp > 5 min in future rejected"""
    # Assert 401 + "Timestamp in future"

def test_poll_rejects_nonce_reuse():
    """Same nonce twice rejected"""
    # First request with nonce_123 → 200
    # Second request with nonce_123 → 401 + "Nonce replayed"

def test_poll_invalid_signature_various():
    """Various signature tampering attempts rejected"""
    # Missing character, extra character, wrong device_id, etc.
    # All should → 401

def test_mql5_signature_matches_backend():
    """MQL5-generated signature validates on backend"""
    # Generate signature in MQL5
    # POST to backend
    # Assert signature accepted
```

---

## TEST COVERAGE ASSESSMENT

**Current Test Coverage**: ~40%

### Tests That Exist ✅
- Poll with valid headers
- Missing headers rejection
- Invalid signature rejection
- Ack creates execution record
- Ack with error message
- Poll filters to approved signals only
- Device revocation works

### Tests That DON'T Exist ❌
- Timestamp freshness (stale/future)
- Nonce replay detection
- Boundary conditions (empty body, malformed JSON)
- Network timeout handling
- Signature collision scenarios
- XOR obfuscation/deobfuscation
- JSON parsing edge cases
- Integration (MQL5 ↔ Python backend)

**Required**: +15 tests to reach 90%+ coverage

---

## BUSINESS LOGIC COMPLETENESS

| Component | Status | Notes |
|-----------|--------|-------|
| Device registration | ✅ 100% | PR-023a complete |
| Poll endpoint | ⚠️ 60% | Exists but no real JSON parsing |
| Ack endpoint | ✅ 90% | Works, needs error telemetry |
| HMAC auth | ❌ 20% | Fake implementation |
| Nonce validation | ❌ 0% | Not implemented |
| Timestamp validation | ❌ 0% | Not implemented |
| Telemetry | ❌ 0% | Missing metrics |
| MQL5 SDK | ⚠️ 50% | Skeleton exists, security incomplete |
| Copy-trading mode | ⚠️ 70% | Logic present, needs integration tests |
| Approval mode | ✅ 80% | Functional |

**Overall**: **~50% business logic complete** (blocking on security + telemetry)

---

## PRODUCTION READINESS CHECKLIST

```
☐ CRITICAL ISSUES (must fix):
  ☐ Telemetry metrics defined (ea_requests_total, ea_errors_total)
  ☐ Real HMAC-SHA256 implementation (not fake hash)
  ☐ Timestamp freshness validation tests
  ☐ Nonce replay detection tests
  ☐ Signature verification tests

☐ HIGH PRIORITY (strongly recommended):
  ☐ JSON parsing in MQL5 SDK (real signal parsing)
  ☐ XOR obfuscation for device secrets
  ☐ Error recovery + retry logic tests
  ☐ Integration tests (MQL5 ↔ Backend)

☐ DOCUMENTATION:
  ☐ Security architecture document
  ☐ MQL5 setup guide
  ☐ Troubleshooting guide
  ☐ Example trading strategies

NOT READY FOR PRODUCTION until all CRITICAL items checked.
```

---

## RECOMMENDATIONS

### Immediate Actions (Before Production)

1. **Add EA Telemetry Metrics** (30 min)
   - File: `backend/app/observability/metrics.py`
   - Add 2 Counter metrics
   - Add 2 recording methods
   - Call from `/api/v1/client/poll` and `/api/v1/client/ack`

2. **Implement Real HMAC-SHA256** (60 min)
   - File: `/ea-sdk/include/caerus_auth.mqh`
   - Replace fake hash with real HMAC-SHA256
   - Option: Call MQL5 OpenSSL library

3. **Add Security Tests** (90 min)
   - File: `backend/tests/test_pr_024a_025_ea.py`
   - Add 8-10 new test cases for security boundaries
   - Verify nonce/timestamp/signature enforcement

### Secondary Actions (Week 1)

4. **Implement JSON Parsing** (45 min)
   - File: `ReferenceEA.mq5`
   - Replace fake signal with real JSON parsing
   - Handle edge cases

5. **Add XOR Obfuscation** (30 min)
   - File: `ReferenceEA.mq5` + `caerus_auth.mqh`
   - Encrypt/decrypt device secret

6. **Write Integration Tests** (120 min)
   - Create harness to run MQL5 code
   - Test full poll → execute → ack flow

---

## SUMMARY

**PR-041 Status**: ⚠️ **65% Complete - Not Production Ready**

**Blocking Issues**:
1. ❌ No telemetry metrics (ea_requests_total, ea_errors_total)
2. ❌ Fake HMAC implementation (security risk!)
3. ❌ Missing security tests (nonce/timestamp replay)

**Estimated Time to Fix**: 3-4 hours

**Next Steps**:
1. Implement telemetry metrics
2. Replace fake HMAC with real HMAC-SHA256
3. Add 8+ security test cases
4. Run full test suite to verify 90%+ coverage

**Go/No-Go Decision**: **NO-GO** for production until above fixed.

---

**Audit Completed**: October 27, 2025
**Recommendation**: Implement all 3 blocking issues in current session
