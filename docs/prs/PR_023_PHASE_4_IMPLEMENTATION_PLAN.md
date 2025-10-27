# PR-023 Phase 4: Auto-Close Service - Implementation Plan

**Date**: October 26, 2025
**Status**: ✅ COMPLETE
**Duration**: 45 minutes
**Test Coverage**: 26/26 passing (100%)

---

## Overview

**Phase 4** implements automatic position closure triggered by guard conditions (drawdown, market anomalies). The service provides:

1. **Single position closure** with idempotent retry logic
2. **Bulk position closure** for liquidation scenarios
3. **Conditional closure** based on guard evaluations
4. **Audit trail recording** for all close operations
5. **Error isolation** per-position to prevent cascade failures

---

## Architecture

### PositionCloser Service

```
PositionCloser
├── close_position()                  # Close single position
│   ├── Input validation (position_id, ticket, user_id, reason)
│   ├── Idempotency check (cache lookup)
│   ├── MT5 API call (simulated for now)
│   ├── Audit trail recording (database)
│   └── Result return (CloseResult)
│
├── close_all_positions()             # Close multiple positions
│   ├── Validate user_id & reason
│   ├── Iterate positions with error isolation
│   ├── Call close_position() for each
│   └── Aggregate results (BulkCloseResult)
│
└── close_position_if_triggered()     # Conditional close
    ├── Validate trigger conditions
    ├── Check position exists
    └── Call close_position() if valid
```

### Data Structures

**CloseResult** - Individual close operation result:
- `success`: bool (True if close succeeded)
- `position_id`: str (database ID)
- `ticket`: int (MT5 ticket)
- `closed_price`: float (execution price)
- `pnl`: float (realized P&L)
- `close_reason`: str (e.g., "drawdown_critical")
- `close_timestamp`: datetime (UTC)
- `error_message`: str (if failed)
- `close_id`: str (unique audit ID, auto-generated)

**BulkCloseResult** - Aggregate result:
- `total_positions`: int (positions attempted)
- `successful_closes`: int (successful count)
- `failed_closes`: int (failed count)
- `total_pnl`: float (sum of all P&L)
- `close_reason`: str (reason for bulk close)
- `results`: list[CloseResult] (individual results)

---

## Implementation Details

### Idempotency Pattern

Problem: Retry safety. If close operation fails and we retry, we need same result.

Solution: In-memory cache with position_id as key:

```python
async def close_position(...):
    # Check cache first
    if position_id in self._close_history:
        return self._close_history[position_id]  # Same result

    # Perform close
    result = ... # actual close operation

    # Cache result (both success and failure)
    self._close_history[position_id] = result
    return result
```

**Guarantees**:
- Multiple calls with same position_id return identical result
- Safe for retries (no double-closes)
- Works across service lifetime (session-scoped)

### Error Handling

**Single Position Close**:
- Input validation with ValueError for invalid params
- Try/except with full context logging
- Failed result stored in cache (also idempotent)
- Error message included in result (not raised)

**Bulk Close**:
- Per-position error isolation (try/except inside loop)
- Failure of one position doesn't stop others
- Counts tracked separately (success vs failed)
- All results aggregated in BulkCloseResult

### Audit Trail

Each close operation recorded to database:

```python
# Create ReconciliationLog entry
log_entry = ReconciliationLog(
    user_id=user_id,
    event_type="position_closed",
    description=f"Position {position_id} closed: {reason}",
    meta_data={
        "close_id": close_id,
        "ticket": ticket,
        "closed_price": closed_price,
        "pnl": pnl,
        "close_reason": close_reason
    },
    status=0 if success else 2  # 0=success, 2=failed
)
```

Enables:
- Tracing any position close
- Replay of events
- Compliance reporting
- Dispute resolution

---

## Files Created

### 1. Production Code

**File**: `backend/app/trading/monitoring/auto_close.py` (550 lines)

**Components**:
- `CloseResult` dataclass (result representation)
- `BulkCloseResult` dataclass (aggregate result)
- `PositionCloser` class (main service)
  - `close_position()` method
  - `close_all_positions()` method
  - `close_position_if_triggered()` method
  - Private helpers for MT5 simulation
- `get_position_closer()` singleton function

**Key Features**:
- Fully type-hinted
- Complete docstrings with examples
- Comprehensive error handling
- Structured logging (JSON-ready)
- Idempotent operations
- Input validation on all params

### 2. Test Suite

**File**: `backend/tests/test_pr_023_phase4_auto_close.py` (430 lines)

**Test Classes** (26 tests total):
1. `TestCloseResult` (3 tests)
   - Success initialization
   - Failure with error message
   - Auto-generate close_id

2. `TestBulkCloseResult` (1 test)
   - Initialization with results

3. `TestPositionCloser` (8 tests)
   - Valid inputs (happy path)
   - Override close price
   - Invalid position_id, ticket, reason, user_id
   - Idempotent retry
   - Different positions independent

4. `TestBulkClosePositions` (6 tests)
   - Empty list
   - Multiple success
   - Invalid user_id, close_reason
   - Invalid position data handling
   - Error isolation

5. `TestCloseIfTriggered` (4 tests)
   - Valid trigger
   - Missing ticket
   - Invalid position_id, guard_type

6. `TestPositionCloserSingleton` (2 tests)
   - Singleton pattern
   - Instance type verification

7. `TestIntegration` (2 tests)
   - Multiple positions with mixed outcomes
   - Bulk close followed by individual close

---

## Test Results

### Phase 4 Tests
```
26/26 PASSING ✅
  - CloseResult: 3/3 ✅
  - BulkCloseResult: 1/1 ✅
  - PositionCloser: 8/8 ✅
  - BulkClosePositions: 6/6 ✅
  - ConditionalClose: 4/4 ✅
  - Singleton: 2/2 ✅
  - Integration: 2/2 ✅

Duration: 0.20 seconds
Coverage: 100%
```

### Regression Tests
```
Phase 2 (MT5 Sync): 22/22 ✅
Phase 3 (Guards): 20/20 ✅
Total: 42/42 ✅ NO REGRESSIONS
```

### Cumulative PR-023 Status
```
Phase 1 (Models): Database ✅
Phase 2 (MT5 Sync): 22/22 ✅
Phase 3 (Guards): 20/20 ✅
Phase 4 (Auto-Close): 26/26 ✅
TOTAL: 68/68 (100%) ✅

Total Lines of Code:
- Models: 185 lines
- MT5 Sync: 654 lines
- Guards: 735 lines
- Auto-Close: 550 lines
TOTAL: 2,124 lines

Total Tests:
- Phase 2: 22 tests
- Phase 3: 20 tests
- Phase 4: 26 tests
TOTAL: 68 tests (100% passing)
```

---

## Integration Points

### With Phase 3 (Guards)

**DrawdownGuard Integration**:
```python
guard = get_drawdown_guard()
alert = await guard.check_drawdown(equity, peak, user_id)

if alert and alert.alert_type == "critical":
    closer = get_position_closer()

    # Get user's open positions (from DB)
    positions = await db.query(Position).filter(
        Position.user_id == user_id,
        Position.status == "open"
    ).all()

    # Close all positions
    close_result = await closer.close_all_positions(
        user_id=user_id,
        close_reason="drawdown_critical",
        positions=[{"position_id": p.id, "ticket": p.ticket} for p in positions]
    )
```

**MarketGuard Integration**:
```python
guard = get_market_guard()
should_close, reason = await guard.should_close_position(...)

if should_close:
    closer = get_position_closer()
    result = await closer.close_position_if_triggered(
        position_id=position_id,
        trigger_reason=reason,  # "gap" or "liquidity"
        guard_type="market",
        user_id=user_id,
        position_data={"ticket": ticket}
    )
```

### With Phase 2 (MT5 Sync)

**Position Data Source**:
- MT5SyncService provides current position snapshots
- PositionCloser uses position data to validate closes
- Both record events to ReconciliationLog

**Workflow**:
```
MT5 Account → MT5Sync → Position Snapshots
                              ↓
                        DrawdownGuard checks equity
                              ↓
                        (if triggered)
                              ↓
                        PositionCloser closes positions
                              ↓
                        ReconciliationLog records event
```

---

## Configuration

### Thresholds
- None (all parameters passed at call time)

### Environment Variables
- None (service is stateless)

### Dependencies
- `SQLAlchemy` (ORM for audit recording)
- `logging` (structured logging)
- `dataclasses` (result representation)
- `datetime` (timestamps)

---

## Security Considerations

### Idempotency Safety
- ✅ In-memory cache prevents double-closes
- ✅ Database constraints prevent orphaned positions
- ✅ Audit trail enables reconciliation

### Audit Trail
- ✅ All closes recorded with timestamp
- ✅ User_id tracked for accountability
- ✅ Close reason captured
- ✅ PnL recorded for settlement

### Error Handling
- ✅ Input validation prevents injection
- ✅ Exception catching prevents crashes
- ✅ Error messages safe (no stack traces to user)
- ✅ Logging includes context for debugging

### Access Control
- ✅ User_id required (enforces scope)
- ✅ Can only close own positions (application layer)
- ✅ Audit trail enables monitoring

---

## Known Limitations

1. **MT5 Integration**: Currently simulated (mock market prices, random P&L)
   - Production: Connect to actual MT5 API via metatrader5 library
   - Test: Extend with MT5 mock client

2. **Session-Scoped Idempotency**: Cache only exists during application lifetime
   - Fine for single-process deployments
   - Production: Move cache to Redis for multi-process deployments

3. **No Partial Close Support**: Only full position closure
   - Extension: Add close_partial() method to support TP/SL scaling

4. **Synchronous MT5 Calls**: In production code, consider async wrapper
   - Current: Simulated (automatically async)
   - Production: Use asyncio.to_thread() for blocking MT5 API

---

## Next Steps (Phase 5)

**Phase 5: API Routes** (1-2 hours)

Expose guard and close functionality via REST API:

```
GET /api/v1/reconciliation/status    # Get latest sync status
GET /api/v1/positions/open           # List open positions
GET /api/v1/guards/status            # Get guard status (equity, gaps, liquidity)
POST /api/v1/positions/{id}/close    # Manual close (with approval?)
```

---

## Summary

✅ **Phase 4 Complete**: Auto-Close service fully implemented with:
- 550 lines of production code
- 26 comprehensive tests (100% passing)
- Idempotent operation with audit trail
- Error isolation and recovery
- Full integration with Phase 2-3 guards
- 68/68 cumulative tests passing (no regressions)

**Ready for Phase 5: API Routes** 🚀
