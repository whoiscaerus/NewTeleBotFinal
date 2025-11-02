# PR-048: Auto-Trace to Third-Party Trackers - Implementation Plan

**PR ID**: 048
**Phase**: Trust & Transparency
**Domain**: Post-Close Trade Publishing
**Status**: � READY FOR IMPLEMENTATION
**Estimated Hours**: 12-17 hours
**Complexity**: Medium-High
**Start Date**: November 1, 2025

---

## 📋 Overview

PR-048 implements per-client risk profile management with exposure tracking and limit enforcement. The system prevents over-leverage by validating trades against configurable risk limits before approval.

### Key Capabilities
- **Per-client risk profiles**: Customizable drawdown, daily loss, position size, and correlation limits
- **Real-time exposure calculation**: Aggregates open positions by instrument and direction
- **Pre-approval risk validation**: Blocks signals that violate risk limits
- **Historical tracking**: Snapshots for analytics and drawdown calculation
- **Global circuit breakers**: Platform-wide exposure caps

### Business Value
- Reduces platform risk and volatility
- Prevents margin calls and account wipeouts
- Enables tiered risk products (conservative/aggressive)
- Builds compliance foundation for regulations

---

## 🗂️ File Structure

### New Files Created
```
/backend/app/risk/
├── __init__.py                    # Module exports
├── models.py                      # SQLAlchemy ORM models (280 lines)
├── service.py                     # Risk business logic (600 lines)
└── routes.py                      # FastAPI endpoints (350 lines)

/backend/app/tasks/
└── risk_tasks.py                 # Celery periodic tasks (200 lines)

/backend/tests/
└── test_pr_048_risk_controls.py  # Comprehensive tests (700+ lines)

/backend/alembic/versions/
└── 048_add_risk_tables.py         # Database migration (150 lines)

/docs/prs/
├── PR-048-IMPLEMENTATION-PLAN.md        # This file
├── PR-048-ACCEPTANCE-CRITERIA.md        # Test case mapping
├── PR-048-IMPLEMENTATION-COMPLETE.md    # Final verification
└── PR-048-BUSINESS-IMPACT.md            # Strategic value
```

### Modified Files
```
/backend/app/main.py                    # Register risk router
/backend/app/approvals/routes.py        # Add risk check before approval
/backend/app/approvals/service.py       # Update exposure after approval
```

---

## 🗄️ Database Schema

### RiskProfile Table
Per-client configuration for risk limits.

```sql
CREATE TABLE risk_profiles (
    id UUID PRIMARY KEY,
    client_id UUID UNIQUE NOT NULL,
    max_drawdown_percent DECIMAL(5,2) DEFAULT 20.00,
    max_daily_loss DECIMAL(12,2),
    max_position_size DECIMAL(5,2) DEFAULT 1.0,
    max_open_positions INTEGER DEFAULT 5,
    max_correlation_exposure DECIMAL(3,2) DEFAULT 0.70,
    risk_per_trade_percent DECIMAL(4,2) DEFAULT 2.00,
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX ix_risk_profiles_client_id ON risk_profiles(client_id);
```

**Fields Explanation**:
- `max_drawdown_percent`: Peak-to-trough loss threshold (1-100%)
- `max_daily_loss`: Daily loss cap (e.g., $5000/day)
- `max_position_size`: Single trade limit (0.01-100 lots)
- `max_open_positions`: Concurrent trades limit
- `max_correlation_exposure`: Related instruments exposure (0-1)
- `risk_per_trade_percent`: Kelly-like sizing percentage (0.1-10%)

### ExposureSnapshot Table
Historical exposure tracking for analytics.

```sql
CREATE TABLE exposure_snapshots (
    id UUID PRIMARY KEY,
    client_id UUID NOT NULL,
    timestamp TIMESTAMP DEFAULT NOW(),
    total_exposure DECIMAL(12,2),
    exposure_by_instrument JSONB,
    exposure_by_direction JSONB,
    open_positions_count INTEGER,
    current_drawdown_percent DECIMAL(5,2),
    daily_pnl DECIMAL(12,2)
);

CREATE INDEX ix_exposure_snapshots_client_time
    ON exposure_snapshots(client_id, timestamp);
```

**Fields Explanation**:
- `exposure_by_instrument`: JSON dict like `{"EURUSD": 5000.00, "GOLD": 10000.50}`
- `exposure_by_direction`: JSON like `{"buy": 12000.00, "sell": 3000.50}`
- Used for position aggregation and correlation analysis

---

## 🔧 Service Layer Functions

### 1. `get_or_create_risk_profile(client_id, db) → RiskProfile`

**Purpose**: Fetch existing profile or create with defaults.

**Defaults**:
- Max drawdown: 20%
- Max position: 1.0 lot
- Max open positions: 5
- Risk per trade: 2%

**Usage**:
```python
profile = await RiskService.get_or_create_risk_profile("client-123", db)
```

### 2. `calculate_current_exposure(client_id, db) → ExposureSnapshot`

**Purpose**: Aggregate current exposure from open trades.

**Process**:
1. Query all OPEN trades for client
2. Sum by instrument and direction
3. Calculate total value (volume * entry_price)
4. Create database snapshot

**Returns**: ExposureSnapshot with breakdown

### 3. `check_risk_limits(client_id, signal, db) → dict`

**Purpose**: Validate signal against all risk limits.

**Checks**:
1. Max open positions
2. Max position size
3. Max daily loss
4. Max drawdown
5. Correlation exposure
6. Platform limits

**Returns**:
```python
{
    "passes": True/False,
    "violations": [
        {
            "check": "max_open_positions",
            "limit": 5,
            "current": 5,
            "message": "Already at max 5 open positions"
        }
    ],
    "exposure": ExposureSnapshot,
    "profile": RiskProfile
}
```

### 4. `calculate_position_size(client_id, signal, db) → Decimal`

**Purpose**: Safe position sizing using Kelly-like criterion.

**Formula**:
```
position_size = (account_equity * risk_percent) / stop_distance
```

**Constraints**:
- Respects max position size limit
- Respects platform max (100 lots)
- Minimum: 0.01 lots

### 5. `calculate_current_drawdown(client_id, db) → Decimal`

**Purpose**: Peak-to-trough drawdown percentage.

**Formula**:
```
drawdown = (peak_equity - current_equity) / peak_equity * 100
```

**Calculation**:
- Reconstructs equity curve from closed trades
- Tracks historical high water mark
- Returns current peak-to-trough decline

### 6. `check_global_limits(instrument, lot_size, db) → dict`

**Purpose**: Validate against platform-wide exposure caps.

**Limits**:
- Total platform exposure: $500k
- Max daily platform loss: $50k
- Max concurrent positions: 50
- Instrument concentration: 5x platform max

---

## 🔌 API Endpoints

### GET /api/v1/risk/profile
Get client's risk profile.

**Response** (200):
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "client_id": "client-123",
  "max_drawdown_percent": "20.00",
  "max_daily_loss": null,
  "max_position_size": "1.0",
  "max_open_positions": 5,
  "max_correlation_exposure": "0.70",
  "risk_per_trade_percent": "2.00",
  "updated_at": "2025-01-15T10:30:00Z"
}
```

### PATCH /api/v1/risk/profile
Update risk limits.

**Request**:
```json
{
  "max_drawdown_percent": "25.00",
  "max_position_size": "2.0"
}
```

**Response** (200): Updated profile

### GET /api/v1/risk/exposure
Get current exposure.

**Response** (200):
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440001",
  "client_id": "client-123",
  "timestamp": "2025-01-15T10:30:00Z",
  "total_exposure": "15000.50",
  "exposure_by_instrument": {
    "EURUSD": "5000.00",
    "GOLD": "10000.50"
  },
  "exposure_by_direction": {
    "buy": "12000.00",
    "sell": "3000.50"
  },
  "open_positions_count": 3,
  "current_drawdown_percent": "5.25",
  "daily_pnl": "500.00"
}
```

### GET /api/v1/admin/risk/global-exposure
Platform-wide exposure (admin only).

**Response** (200):
```json
{
  "total_platform_exposure": "450000.00",
  "total_open_positions": 42,
  "max_exposure_limit": "500.00",
  "max_positions_limit": 50,
  "exposure_utilization_percent": "90.00",
  "positions_utilization_percent": "84.00"
}
```

---

## 🔄 Integration Points

### Approval Flow (Before Approval)
**File**: `/backend/app/approvals/routes.py`

**Process**:
1. User approves signal
2. **NEW**: Call `check_risk_limits(user_id, signal, db)`
3. If violations exist: Return 403 with violation details
4. If passes: Continue with approval

**Code**:
```python
risk_check = await RiskService.check_risk_limits(user_id, signal, db)
if not risk_check["passes"]:
    raise HTTPException(status_code=403, detail={
        "message": "Signal violates risk limits",
        "violations": risk_check["violations"]
    })
```

### Exposure Tracking (After Approval)
**File**: `/backend/app/approvals/service.py`

**Process**:
1. Signal approved and status updated
2. **NEW**: Call `calculate_current_exposure(user_id, db)`
3. Stores snapshot for historical analysis

**Code**:
```python
if decision == "approved":
    await RiskService.calculate_current_exposure(user_id, db)
```

---

## ⏰ Periodic Tasks (Celery)

### calculate_exposure_snapshots_task
**Schedule**: Every 1 hour
**Purpose**: Record exposure snapshot for each active client
**Actions**: Calls `calculate_current_exposure()` for all clients

### check_drawdown_breakers_task
**Schedule**: Every 15 minutes
**Purpose**: Check for drawdown limit violations
**Actions**:
- Logs WARNING if at 80% of limit
- Logs CRITICAL if exceeded limit
- Could trigger alerts/auto-closure

### cleanup_old_exposure_snapshots_task
**Schedule**: Weekly
**Purpose**: Delete snapshots older than 90 days
**Retention**: 90 days of exposure history

---

## 🧪 Test Coverage (35+ Tests)

### Categories
1. **Risk Profile Tests** (4): CRUD, defaults, uniqueness
2. **Exposure Calculation** (5): Empty, single/multiple trades, closed trades
3. **Risk Limit Validation** (8): Each limit type + combinations
4. **Position Sizing** (4): Min/max, Kelly, custom risk
5. **Drawdown Calculation** (3): No trades, profitable, loss trades
6. **Global Limits** (3): Exposure, positions, concentration
7. **API Endpoints** (6): CRUD, validation, auth
8. **Error Handling** (5+): Large positions, edge cases, concurrency

**Coverage Target**: 90%+

---

## 📊 Acceptance Criteria Checklist

- [ ] RiskProfile model created with 7 configurable limits
- [ ] ExposureSnapshot model created with JSONB breakdowns
- [ ] Alembic migration creates both tables with indexes
- [ ] get_or_create_risk_profile() creates defaults correctly
- [ ] calculate_current_exposure() aggregates trades correctly
- [ ] check_risk_limits() validates all 6 limit types
- [ ] calculate_position_size() respects all constraints
- [ ] calculate_current_drawdown() calculates correctly
- [ ] check_global_limits() detects platform violations
- [ ] GET /api/v1/risk/profile returns profile
- [ ] PATCH /api/v1/risk/profile updates limits
- [ ] GET /api/v1/risk/exposure returns current snapshot
- [ ] GET /api/v1/admin/risk/global-exposure requires admin
- [ ] Risk check integrated into approval flow
- [ ] Exposure updated after approval execution
- [ ] Celery tasks execute on schedule
- [ ] 35+ tests passing with 90%+ coverage
- [ ] All 4 documentation files complete

---

## 🚀 Implementation Phases

### Phase 1: Database Schema ✅ COMPLETE
- [x] Create RiskProfile model
- [x] Create ExposureSnapshot model
- [x] Create Alembic migration

### Phase 2: Service Layer ✅ COMPLETE
- [x] Implement 6 core service functions
- [x] Add error handling and logging
- [x] Implement helper methods (correlation, daily PnL)

### Phase 3: API Routes ✅ COMPLETE
- [x] Create 4 REST endpoints
- [x] Add request/response validation
- [x] Register router in main.py

### Phase 4: Integration ✅ COMPLETE
- [x] Risk check in approval flow
- [x] Exposure update after approval

### Phase 5: Testing & Tasks ✅ COMPLETE
- [x] 35+ comprehensive tests
- [x] Celery periodic tasks
- [x] Error handling tests

### Phase 6: Documentation 🔄 IN PROGRESS
- [ ] IMPLEMENTATION-PLAN (this file)
- [ ] ACCEPTANCE-CRITERIA
- [ ] IMPLEMENTATION-COMPLETE
- [ ] BUSINESS-IMPACT

### Phase 7: Verification
- [ ] Run all tests locally
- [ ] Check coverage (90%+)
- [ ] Verify CI/CD pipeline
- [ ] Create verification script

---

## 🔗 Dependencies

### Hard Dependencies (Blocking)
- ✅ Trade model (backend/app/trading/store/models.py)
- ✅ Approval model (backend/app/approvals/models.py)
- ✅ Signal model (backend/app/signals/models.py)
- ✅ Account model (backend/app/accounts/service.py)

### Soft Dependencies (Nice-to-have)
- PR-46 (Strategy Registry) - NOT NEEDED for core functionality

---

## 📝 Notes

- All limits have sensible defaults to prevent excessive leverage
- Global limits serve as platform-wide circuit breakers
- Exposure snapshots enable historical analysis and regulatory reporting
- Risk checks happen BEFORE approval to prevent risky trades
- Drawdown calculation is approximate (based on closed trades)
- Correlation exposure uses instrument groupings (majors, commodities, etc.)

---

**Last Updated**: Jan 15, 2025
**Author**: AI Assistant
**Status**: Implementation Plan Complete
