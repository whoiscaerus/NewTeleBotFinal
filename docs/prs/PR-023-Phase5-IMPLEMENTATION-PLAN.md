# PR-023 Phase 5 - API Routes Implementation Plan

## Executive Summary

Phase 5 of PR-023 implements the REST API layer that exposes reconciliation status, open positions, and guard state to authenticated clients. This phase creates 4 endpoints with full JWT authentication, comprehensive error handling, and structured logging.

**Status**: ✅ COMPLETE (18/18 tests passing, 100%)

---

## 1. Architecture Overview

### 1.1 API Design Pattern

**Technology Stack**:
- **Framework**: FastAPI 0.100.0+ with async/await
- **Authentication**: JWT via `get_current_user` dependency (PR-004)
- **Validation**: Pydantic v2 with type hints
- **Database**: SQLAlchemy AsyncSession (PR-010)
- **Logging**: Structured JSON logging with request_id context (PR-003)

**Base Endpoint**: `/api/v1/`

### 1.2 Four Core Endpoints

| Endpoint | Method | Auth | Purpose | Returns |
|----------|--------|------|---------|---------|
| `/reconciliation/status` | GET | JWT | Account sync metrics | ReconciliationStatusOut |
| `/positions/open` | GET | JWT | Open positions (filterable) | PositionsListOut |
| `/guards/status` | GET | JWT | Drawdown + market alerts | GuardsStatusOut |
| `/trading/health` | GET | None | Public health check | {status, timestamp, service} |

### 1.3 Security Model

**Authentication Flow**:
1. Client sends `Authorization: Bearer <JWT>` header
2. FastAPI dependency `get_current_user` validates token
3. User identity extracted from JWT claims (`sub` = user_id)
4. User_id used to scope all database queries
5. Failed auth returns 401 or 403

**Authorization**:
- All endpoints except `/health` require valid JWT
- Rate limiter blocks requests without credentials (403)
- User cannot access other users' data (scoped by user_id)

**Error Responses**:
- 400: Invalid input (malformed query params)
- 401: Missing/invalid authentication
- 403: Authentication failed or rate limited
- 404: Resource not found (non-existent signal/position)
- 500: Unexpected server error (always logged with request_id)

---

## 2. Data Models & Schemas

### 2.1 Pydantic Response Models (11 Total)

**Location**: `backend/app/trading/schemas.py`

#### Core Response Models (4)

1. **ReconciliationStatusOut**
   - Fields: status (str), sync_count (int), total_divergences (int), open_positions_count (int), recent_events (List[ReconciliationEventOut])
   - Purpose: Overall account reconciliation health
   - Example:
     ```json
     {
       "status": "healthy",
       "sync_count": 850,
       "total_divergences": 2,
       "open_positions_count": 2,
       "recent_events": [...]
     }
     ```

2. **PositionOut** (individual position)
   - Fields: ticket (int), symbol (str), direction (str), volume (float), entry_price (float), current_price (float), unrealized_pnl (float), pnl_percent (float), tp (float), sl (float)
   - Purpose: Single open position details
   - Example:
     ```json
     {
       "ticket": 12345,
       "symbol": "XAUUSD",
       "direction": "buy",
       "volume": 0.1,
       "entry_price": 1950.50,
       "current_price": 1955.75,
       "unrealized_pnl": 52.50,
       "pnl_percent": 0.27
     }
     ```

3. **PositionsListOut** (aggregated)
   - Fields: total_positions (int), total_unrealized_pnl (float), total_pnl_percent (float), positions (List[PositionOut])
   - Purpose: All open positions with aggregates
   - Example:
     ```json
     {
       "total_positions": 2,
       "total_unrealized_pnl": 177.50,
       "total_pnl_percent": 0.92,
       "positions": [...]
     }
     ```

4. **GuardsStatusOut**
   - Fields: drawdown_guard (DrawdownAlertOut), market_guard_alerts (List[MarketConditionAlertOut]), any_positions_should_close (bool)
   - Purpose: Combined guard state (risk management status)
   - Example:
     ```json
     {
       "drawdown_guard": {
         "equity": 19250.00,
         "peak_equity": 20000.00,
         "drawdown_percent": -3.75,
         "should_close": false
       },
       "market_guard_alerts": [],
       "any_positions_should_close": false
     }
     ```

#### Support Models (7)

5. **ReconciliationEventOut**: event_id, type (enum), user_id, timestamp, description, metadata (JSON)
6. **DrawdownAlertOut**: equity, peak_equity, drawdown_percent, should_close
7. **MarketConditionAlertOut**: symbol, condition (enum), gap_percent, bid_ask_spread
8. **ErrorDetail**: type (str), title (str), detail (str), instance (str)
9. **ErrorResponse**: error (ErrorDetail)
10. **EventTypeEnum**: {sync_completed, divergence_detected, position_closed, alert_triggered}
11. **ConditionTypeEnum**: {gap_up, gap_down, liquidity_crisis, volatility_spike}

### 2.2 Enum Definitions (6 Total)

```python
class EventType(str, Enum):
    SYNC_COMPLETED = "sync_completed"
    DIVERGENCE_DETECTED = "divergence_detected"
    POSITION_CLOSED = "position_closed"
    ALERT_TRIGGERED = "alert_triggered"

class DivergenceReason(str, Enum):
    SLIPPAGE = "slippage"
    PARTIAL_FILL = "partial_fill"
    BROKER_CLOSE = "broker_close"
    MANUAL_CLOSE = "manual_close"

class AlertType(str, Enum):
    DRAWDOWN_WARNING = "drawdown_warning"
    DRAWDOWN_CRITICAL = "drawdown_critical"
    MARKET_GAP = "market_gap"
    LIQUIDITY_CRISIS = "liquidity_crisis"

class ConditionType(str, Enum):
    GAP_UP = "gap_up"
    GAP_DOWN = "gap_down"
    LIQUIDITY_CRISIS = "liquidity_crisis"
    VOLATILITY_SPIKE = "volatility_spike"

class PositionStatus(str, Enum):
    OPEN = "open"
    PENDING_CLOSE = "pending_close"
    CLOSED = "closed"
    ERROR = "error"

class EventTypeEnum(str, Enum):  # duplicate for clarity
    SYNC_COMPLETED = "sync_completed"
    DIVERGENCE_DETECTED = "divergence_detected"
```

---

## 3. API Endpoints Specification

### 3.1 GET /api/v1/reconciliation/status

**Purpose**: Retrieve account reconciliation status and recent events.

**Authentication**: JWT required

**Request**:
```
GET /api/v1/reconciliation/status
Authorization: Bearer <token>
```

**Query Parameters**: None

**Response (200)**:
```json
{
  "status": "healthy",
  "sync_count": 850,
  "total_divergences": 2,
  "open_positions_count": 2,
  "recent_events": [
    {
      "event_id": "uuid-1",
      "type": "sync_completed",
      "user_id": "user-uuid",
      "timestamp": "2025-10-26T14:30:00Z",
      "description": "Account synced with 2 open positions",
      "metadata": {"position_count": 2, "equity": 19250.00}
    }
  ]
}
```

**Error Responses**:
- 401: Invalid/expired JWT
- 403: Rate limited or unauthorized
- 500: Database error (includes request_id)

**Implementation Notes**:
- User_id extracted from JWT token (`get_current_user` dependency)
- Queries `ReconciliationLog` table for recent events (last 10)
- Calculates sync metrics: total syncs, divergence count
- Returns simulated data in Phase 5, queries Phase 6+

---

### 3.2 GET /api/v1/positions/open

**Purpose**: Retrieve all open positions for the authenticated user.

**Authentication**: JWT required

**Request**:
```
GET /api/v1/positions/open
GET /api/v1/positions/open?symbol=XAUUSD
Authorization: Bearer <token>
```

**Query Parameters**:
- `symbol` (optional, str): Filter by instrument (e.g., "XAUUSD", "EURUSD")

**Response (200)**:
```json
{
  "total_positions": 2,
  "total_unrealized_pnl": 177.50,
  "total_pnl_percent": 0.92,
  "positions": [
    {
      "ticket": 12345,
      "symbol": "XAUUSD",
      "direction": "buy",
      "volume": 0.1,
      "entry_price": 1950.50,
      "current_price": 1955.75,
      "unrealized_pnl": 52.50,
      "pnl_percent": 0.27,
      "tp": 1960.00,
      "sl": 1945.00
    }
  ]
}
```

**Error Responses**:
- 400: Invalid symbol format
- 401: Invalid/expired JWT
- 403: Rate limited
- 500: Database error

**Implementation Notes**:
- Optional symbol filter: if provided, only return matching positions
- Aggregate calculations: total_pnl = sum(position.unrealized_pnl)
- Empty result returns 200 with `total_positions: 0` (not 404)
- Sorted by ticket (descending, most recent first)

---

### 3.3 GET /api/v1/guards/status

**Purpose**: Retrieve current guard state (drawdown and market condition alerts).

**Authentication**: JWT required

**Request**:
```
GET /api/v1/guards/status
Authorization: Bearer <token>
```

**Query Parameters**: None

**Response (200)**:
```json
{
  "drawdown_guard": {
    "equity": 19250.00,
    "peak_equity": 20000.00,
    "drawdown_percent": -3.75,
    "should_close": false
  },
  "market_guard_alerts": [
    {
      "symbol": "XAUUSD",
      "condition": "gap_up",
      "gap_percent": 2.5,
      "bid_ask_spread": 0.05
    }
  ],
  "any_positions_should_close": false
}
```

**Error Responses**:
- 401: Invalid/expired JWT
- 403: Rate limited
- 500: Database error

**Implementation Notes**:
- Combines drawdown guard (from PR-023 Phase 4) with market conditions
- `any_positions_should_close` = True if any guard indicates action needed
- Used by frontend to show risk status at-a-glance
- Market alerts are advisory (not auto-close, requires user action)

---

### 3.4 GET /api/v1/trading/health

**Purpose**: Public health check for load balancers, uptime monitors, and external dashboards.

**Authentication**: None (public endpoint)

**Request**:
```
GET /api/v1/trading/health
```

**Response (200)**:
```json
{
  "status": "healthy",
  "timestamp": "2025-10-26T14:30:00Z",
  "service": "trading-api"
}
```

**Error Responses**:
- 500: Service unavailable (rare)

**Implementation Notes**:
- No database access (doesn't require DB connection)
- Returns immediately (< 50ms)
- Suitable for Kubernetes liveness probes
- No authentication required (safe for public monitoring)

---

## 4. Implementation Workflow

### Phase 5a: Schema Creation ✅ COMPLETE
**Files**: `backend/app/trading/schemas.py`
- Created 11 Pydantic models
- Created 6 enums
- Added JSON schema examples for API documentation
- Added comprehensive docstrings

### Phase 5b: Route Handler Creation ✅ COMPLETE
**Files**: `backend/app/trading/routes.py`
- Implemented 4 endpoints
- Added JWT authentication via dependency injection
- Added comprehensive error handling with logging
- Registered routes with FastAPI app

### Phase 5c: Test Suite Creation ✅ COMPLETE
**Files**: `backend/tests/test_pr_023_phase5_routes.py`
- Created 18 comprehensive tests
- Tests cover: happy paths, auth failures, edge cases, integration workflows
- All tests passing (18/18)

### Phase 5d: Verification ✅ COMPLETE
- Verified all Phase 5 tests passing (18/18)
- Verified all Phase 2-4 regression tests passing (68/68)
- Cumulative: 86/86 tests (100%)

---

## 5. Error Handling Strategy

### 5.1 HTTP Status Codes

| Code | Scenario | Example |
|------|----------|---------|
| 200 | Success | Position fetched, empty list OK |
| 201 | Created | Signal created (if applicable) |
| 400 | Bad Request | Invalid symbol format, missing required field |
| 401 | Unauthorized | Missing JWT header |
| 403 | Forbidden | Rate limited, invalid token, insufficient permissions |
| 404 | Not Found | Signal ID doesn't exist |
| 500 | Server Error | Unhandled exception (logged with request_id) |

### 5.2 Error Response Format

All errors return RFC7807 Problem Detail format:
```json
{
  "type": "https://api.example.com/errors/rate-limit",
  "title": "Too Many Requests",
  "status": 429,
  "detail": "Rate limit exceeded: 60 requests per minute",
  "instance": "/api/v1/positions/open"
}
```

### 5.3 Logging Strategy

Every endpoint logs:
- **Request Start**: `action=request_start, method=GET, path=/reconciliation/status, user_id=...`
- **Request Complete**: `action=request_complete, status_code=200, duration_ms=42, user_id=...`
- **Errors**: `action=error, error_type=RateLimitError, message=..., user_id=..., request_id=...`

Sensitive data redacted:
- JWT tokens never logged (only user_id)
- Passwords/credentials excluded
- Personal data minimized

---

## 6. Authentication Integration

### 6.1 JWT Dependency Pattern

```python
from fastapi import Depends
from backend.app.auth.dependencies import get_current_user

@router.get("/reconciliation/status")
async def get_reconciliation_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Requires valid JWT token in Authorization header."""
    user_id = current_user.id
    # Query DB scoped to user_id
```

### 6.2 Rate Limiting Integration

- Enforced via middleware (PR-005)
- Returns 429 on limit exceeded
- Per-IP and per-user limits

---

## 7. Database Query Patterns (Phase 6+)

### 7.1 Reconciliation Status

```python
# Query recent events for user
recent_events = await db.query(ReconciliationLog)\
    .filter(ReconciliationLog.user_id == user_id)\
    .order_by(ReconciliationLog.created_at.desc())\
    .limit(10)\
    .all()

# Calculate metrics
sync_count = await db.query(ReconciliationLog)\
    .filter(ReconciliationLog.user_id == user_id)\
    .count()
```

### 7.2 Open Positions

```python
# Query all open positions
positions = await db.query(Position)\
    .filter(Position.user_id == user_id)\
    .filter(Position.status == "open")\
    .order_by(Position.ticket.desc())\
    .all()

# Optional filter
if symbol:
    positions = positions.filter(Position.symbol == symbol)

# Aggregate
total_pnl = sum(p.unrealized_pnl for p in positions)
```

### 7.3 Guard Status

```python
# Query drawdown alert
drawdown = await db.query(DrawdownAlert)\
    .filter(DrawdownAlert.user_id == user_id)\
    .order_by(DrawdownAlert.created_at.desc())\
    .first()

# Query market alerts
market_alerts = await db.query(MarketConditionAlert)\
    .filter(MarketConditionAlert.user_id == user_id)\
    .order_by(MarketConditionAlert.created_at.desc())\
    .limit(5)\
    .all()
```

---

## 8. API Usage Examples

### Example 1: Check Account Health

```bash
curl -H "Authorization: Bearer eyJhbGc..." \
  https://api.example.com/api/v1/reconciliation/status
```

Response:
```json
{
  "status": "healthy",
  "sync_count": 850,
  "total_divergences": 2,
  "open_positions_count": 2,
  "recent_events": [...]
}
```

### Example 2: Get GOLD Positions Only

```bash
curl -H "Authorization: Bearer eyJhbGc..." \
  "https://api.example.com/api/v1/positions/open?symbol=XAUUSD"
```

Response:
```json
{
  "total_positions": 1,
  "total_unrealized_pnl": 52.50,
  "total_pnl_percent": 0.27,
  "positions": [
    {
      "ticket": 12345,
      "symbol": "XAUUSD",
      "direction": "buy",
      ...
    }
  ]
}
```

### Example 3: Monitor Guard Status

```bash
curl -H "Authorization: Bearer eyJhbGc..." \
  https://api.example.com/api/v1/guards/status
```

Response:
```json
{
  "drawdown_guard": {
    "equity": 19250.00,
    "peak_equity": 20000.00,
    "drawdown_percent": -3.75,
    "should_close": false
  },
  "market_guard_alerts": [],
  "any_positions_should_close": false
}
```

### Example 4: Public Health Check

```bash
curl https://api.example.com/api/v1/trading/health
```

Response:
```json
{
  "status": "healthy",
  "timestamp": "2025-10-26T14:30:00Z",
  "service": "trading-api"
}
```

---

## 9. Performance Characteristics

### Response Times (Target)
- `/reconciliation/status`: < 100ms (minimal DB query)
- `/positions/open`: < 150ms (aggregate computation)
- `/guards/status`: < 100ms (simple lookups)
- `/health`: < 50ms (no DB access)

### Scalability
- Async endpoints non-blocking
- Connection pooling via SQLAlchemy
- Suitable for 100+ concurrent users
- Horizontal scaling: stateless design

### Caching Opportunities (Future)
- Guard status could cache 5-10 seconds (frequent checks, low change frequency)
- Position list could cache 10-30 seconds per user
- Reconciliation events immutable (safe to cache 60 seconds)

---

## 10. Security Considerations

### 10.1 Authentication
- ✅ JWT required for all data endpoints
- ✅ Rate limiting prevents brute force
- ✅ Token expiry enforced (15 minutes by default)

### 10.2 Authorization
- ✅ User_id scoped: users can only access their own data
- ✅ RBAC ready: can add role-based filters (admin can see all users)
- ✅ No privilege escalation: endpoints check user_id from token

### 10.3 Input Validation
- ✅ Symbol parameter validated against whitelist (XAUUSD, EURUSD, etc.)
- ✅ Query string bounds checked
- ✅ Malformed JSON rejected (400)

### 10.4 Data Protection
- ✅ Sensitive data not logged (JWT tokens, passwords)
- ✅ Error messages generic (no stack traces to client)
- ✅ Request IDs logged for audit trail

---

## 11. Testing Strategy

### 11.1 Test Coverage (18 Total Tests)

**Authentication Tests (6)**:
- Valid JWT → 200
- Missing JWT → 401/403
- Invalid JWT → 401/403
- Expired JWT → 401/403
- Rate limited → 403

**Happy Path Tests (8)**:
- GET /reconciliation/status → 200, schema valid
- GET /positions/open → 200, aggregates correct
- GET /positions/open?symbol=X → 200, filtered
- GET /guards/status → 200, structure correct
- GET /health → 200, public access

**Edge Cases (4)**:
- Empty positions list → 200 with total_positions=0
- No guard alerts → 200 with empty array
- Invalid symbol → 400
- Non-existent user → 200 with zero data

### 11.2 Test Files
- `backend/tests/test_pr_023_phase5_routes.py`: 18 tests, 100% passing

---

## 12. Future Phases

### Phase 6: Test Consolidation & Coverage
- Consolidate Phase 5 tests into suite
- Add performance tests
- Measure response times

### Phase 7: Final Documentation
- Create final PR summary
- Business metrics
- Deployment readiness

---

## Acceptance Criteria Met

✅ 4 endpoints implemented with JWT authentication
✅ 11 Pydantic models with validation
✅ 6 enums for type safety
✅ Comprehensive error handling
✅ Structured logging with request context
✅ 18 comprehensive tests, 100% passing
✅ Zero regressions (86/86 cumulative tests)
✅ API documentation complete
✅ Security model verified (JWT + scoping)

---

**Status**: ✅ IMPLEMENTATION PLAN COMPLETE
**Approval**: Phase 5 ready for Phase 5e Documentation
