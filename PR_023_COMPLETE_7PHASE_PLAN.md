# PR-023 COMPLETE IMPLEMENTATION PLAN
## Account Reconciliation & Trade Monitoring (7 Phases)

**Status**: Phases 1-2 Complete ✅ | Phase 3 Ready to Start 🚀

---

## PHASE OVERVIEW

| Phase | Module | Status | Time | Tests | Output |
|-------|--------|--------|------|-------|--------|
| 1 | Models & Database | ✅ Complete | 30m | N/A | 3 models, 1 migration |
| 2 | MT5 Sync Service | ✅ Complete | 2h | 22 ✅ | Sync + Scheduler |
| 3 | Drawdown/Market Guards | 🚀 Ready | 2-3h | ~15 | Guard services |
| 4 | Auto-Close Service | ⏳ Queued | 2-3h | ~10 | Close logic |
| 5 | API Routes | ⏳ Queued | 1-2h | ~8 | 3 endpoints |
| 6 | Test Suite | ⏳ Queued | 2-3h | ~30 | Consolidation |
| 7 | Documentation | ⏳ Queued | 1-2h | N/A | 4 docs |
| **TOTAL** | | **67%** | **10-14h** | **~85** | **Complete system** |

---

## ✅ PHASE 1: MODELS & DATABASE (COMPLETE)

### Deliverables Created
```
backend/app/trading/reconciliation/models.py (185 lines)
  ✅ ReconciliationLog model (23 columns, 4 indexes)
  ✅ PositionSnapshot model (11 columns, 2 indexes)
  ✅ DrawdownAlert model (11 columns, 2 indexes)

backend/alembic/versions/0004_reconciliation.py (160 lines)
  ✅ Migration with full upgrade/downgrade
  ✅ 14 strategic indexes
  ✅ Foreign key constraints
```

### Database Tables Created
1. **reconciliation_logs**: Tracks MT5 position sync events & divergences
2. **position_snapshots**: Account equity & position summary snapshots
3. **drawdown_alerts**: Equity guard trigger records

### Key Design Decisions
- Immutable log entries (append-only)
- Timestamps in UTC
- Foreign keys to users, signals, approvals
- Indexes for fast queries (user_id + created_at, symbol, event_type, status)

---

## ✅ PHASE 2: MT5 SYNC SERVICE (COMPLETE)

### Deliverables Created
```
backend/app/trading/reconciliation/mt5_sync.py (654 lines)
  ✅ MT5Position class - Position snapshot
  ✅ MT5AccountSnapshot class - Account state
  ✅ MT5SyncService class - Synchronization engine

backend/app/trading/reconciliation/scheduler.py (218 lines)
  ✅ ReconciliationScheduler - Periodic orchestrator
  ✅ Background job management

backend/tests/test_pr_023_phase2_mt5_sync.py (524 lines)
  ✅ 22 comprehensive tests (100% passing)
```

### Core Features
- **Position Fetching**: Connect to MT5, retrieve equity & positions
- **Position Matching**: Match MT5 positions to bot trades (5% tolerance)
- **Divergence Detection**: Identify slippage, partial fills, gaps
- **Event Recording**: Log all reconciliation events to database
- **Scheduler**: Runs every 10 seconds, 5 concurrent users
- **Error Handling**: Complete error isolation & recovery

### Test Results
```
22/22 tests PASSING (100%)
- MT5Position: 3 tests
- MT5AccountSnapshot: 3 tests
- MT5SyncService: 10 tests
- ReconciliationScheduler: 3 tests
- Integration: 3 tests
Duration: 0.24 seconds
```

---

## 🚀 PHASE 3: DRAWDOWN/MARKET GUARDS (READY TO START)

### Objectives
1. Monitor account equity in real-time
2. Trigger automatic position closure on extreme conditions
3. Alert user before liquidation
4. Market safety checks (gaps, liquidity)

### Deliverables to Create

#### 3a. DrawdownGuard Service
```
File: backend/app/trading/monitoring/drawdown_guard.py

Class: DrawdownGuard
  Method: check_drawdown(account_snapshot, peak_equity) -> (should_close, drawdown_pct)
    - Calculate: current_equity / peak_equity
    - If drawdown > threshold (20%): trigger liquidation
    - Log warning 10 seconds before close
    - Record to DrawdownAlert table

  Method: get_peak_equity(user_id) -> float
    - Query max peak_equity from position_snapshots
    - Update in database if new peak

  Method: alert_user_before_close(user_id, drawdown_pct, positions_count)
    - Send Telegram alert: "Drawdown detected: {drawdown_pct}%"
    - Show positions to be closed
    - Countdown: "Liquidating in 10 seconds..."
```

**Env Vars**:
- `MAX_DRAWDOWN_PERCENT=20` (threshold for liquidation)
- `DRAWDOWN_ALERT_THRESHOLD_PERCENT=15` (warning threshold)
- `MIN_EQUITY_GBP=100` (minimum account balance)
- `PRE_LIQUIDATION_WARNING_SECONDS=10`

**Tests Needed** (8 tests):
1. `test_check_drawdown_within_threshold` - No alert
2. `test_check_drawdown_warning_threshold` - Alert triggered
3. `test_check_drawdown_critical` - Liquidation triggered
4. `test_check_drawdown_below_min_equity` - Force liquidation
5. `test_get_peak_equity_new_peak` - Update peak
6. `test_get_peak_equity_existing_peak` - Return existing
7. `test_alert_user_telegram_sent` - Message verified
8. `test_alert_user_multiple_positions` - Show all positions

#### 3b. MarketGuard Service
```
File: backend/app/trading/monitoring/market_guard.py

Class: MarketGuard
  Method: check_price_gap(symbol, last_close, current_open) -> (is_safe, gap_pct)
    - Calculate: abs(current_open - last_close) / last_close
    - If gap > threshold (5%): mark unsafe
    - Log market condition alert
    - Record to database

  Method: check_liquidity(symbol, bid, ask, position_volume) -> (is_liquid, spread_pct)
    - Calculate: (ask - bid) / bid
    - If spread too wide or position_volume > available: mark unsafe
    - Consider market conditions (news, volatility)

  Method: mark_position_for_close(position_id, reason)
    - Flag position for manual/auto close
    - Log reason (gap, liquidity crisis, margin pressure)
    - Alert user immediately

  Method: should_close_position(position_id, market_conditions) -> (should_close, reason)
    - Check all guard conditions
    - Return true if any condition triggered
    - Reason: "gap", "liquidity", "margin", etc.
```

**Env Vars**:
- `PRICE_GAP_ALERT_PERCENT=5` (gap threshold)
- `LIQUIDITY_CHECK_ENABLED=true`
- `BID_ASK_SPREAD_MAX_PERCENT=0.5` (max acceptable spread)
- `MIN_LIQUIDITY_VOLUME_LOTS=10` (minimum available volume)

**Tests Needed** (7 tests):
1. `test_check_price_gap_normal` - No gap
2. `test_check_price_gap_large_up` - Gap detected (up)
3. `test_check_price_gap_large_down` - Gap detected (down)
4. `test_check_liquidity_sufficient` - Liquid
5. `test_check_liquidity_wide_spread` - Spread too wide
6. `test_check_liquidity_insufficient_volume` - Not enough volume
7. `test_mark_position_for_close` - Position flagged

#### 3c. Integration with Phase 2
```
Modify: backend/app/trading/reconciliation/scheduler.py

After sync_positions_for_user():
  1. Check drawdown for each user
  2. Check market conditions for each position
  3. Record guard status to DrawdownAlert table
  4. Send alerts to users
  5. Mark positions for auto-close if needed
```

### Implementation Approach

**Step 1: Create Guard Services** (40 min)
- DrawdownGuard: equity monitoring & liquidation logic
- MarketGuard: price gap & liquidity checks
- Both with comprehensive error handling

**Step 2: Integrate with Scheduler** (30 min)
- Call guards after position sync
- Record guard status
- Alert users

**Step 3: Write Tests** (60 min)
- Unit tests for guard logic (15 tests)
- Integration tests with scheduler (3 tests)
- Mock MT5 data & user alerts

**Step 4: Document** (10 min)
- Update Phase 2 implementation plan
- Add guard behavior documentation

### Success Criteria for Phase 3
- ✅ All guard checks implemented
- ✅ 15+ tests passing (100%)
- ✅ Proper error handling
- ✅ User alerts working
- ✅ Database recording working
- ✅ Integrated with scheduler

---

## ⏳ PHASE 4: AUTO-CLOSE SERVICE (Planned)

### Objectives
Close positions via MT5 API with full audit trail

### Key Modules
```
backend/app/trading/monitoring/auto_close.py

Class: PositionCloser
  Method: close_position(position_ticket, close_reason, price=None)
    - Send close request to MT5 API
    - Record closed price & PnL
    - Audit trail with timestamp
    - Idempotent (safe to retry)

  Method: close_all_positions(user_id, reason)
    - Close all open positions for user
    - Bulk operation with error isolation
    - Transaction safety

  Method: close_position_if_triggered(position_id, trigger_reason)
    - Check if close should proceed
    - Send Telegram alert to user
    - Record execution
```

### Estimated Work: 2-3 hours
- Implementation: 1.5 hours
- Testing: 1 hour
- Integration: 0.5 hour

---

## ⏳ PHASE 5: API ROUTES (Planned)

### Endpoints to Create
```
GET /api/v1/reconciliation/{user_id}
  - Returns: Reconciliation status, last sync time, divergence count

GET /api/v1/positions
  - Returns: Live open positions, equity, drawdown %

GET /api/v1/guards
  - Returns: Guard status, last check time, alerts pending

POST /api/v1/guards/manual-close
  - Request: { position_id, reason }
  - Response: Close confirmation, PnL
```

### Estimated Work: 1-2 hours

---

## ⏳ PHASE 6: TEST SUITE (Planned)

### Consolidation & Expansion
- Combine all tests into single `test_pr_023_reconciliation.py`
- Add ~30 additional tests
- Target >90% coverage
- Performance tests for scheduler

### Estimated Work: 2-3 hours

---

## ⏳ PHASE 7: DOCUMENTATION (Planned)

### Documents to Create
1. **PR-023-IMPLEMENTATION-PLAN.md** - What was built & how
2. **PR-023-IMPLEMENTATION-COMPLETE.md** - Verification checklist
3. **PR-023-ACCEPTANCE-CRITERIA.md** - All requirements validated
4. **PR-023-BUSINESS-IMPACT.md** - Why this matters

### Estimated Work: 1-2 hours

---

## 📊 RESOURCE ALLOCATION

### Time Estimate
- **Phase 3**: 2-3 hours (next)
- **Phase 4**: 2-3 hours
- **Phase 5**: 1-2 hours
- **Phase 6**: 2-3 hours
- **Phase 7**: 1-2 hours
- **Total Remaining**: 8-13 hours

### Test Target
- Phase 3: ~15 tests
- Phase 4: ~10 tests
- Phase 5: ~8 tests
- Phase 6: ~30 tests (consolidation + new)
- **Total for PR-023**: ~85 tests

### Code Output
- Phase 3: ~400 lines
- Phase 4: ~300 lines
- Phase 5: ~200 lines
- Phase 6: ~150 lines (test expansion)
- Phase 7: ~400 lines (docs)
- **Total for PR-023**: ~1,450 lines

---

## 🔗 DEPENDENCIES

### Phase 3 Depends On
✅ Phase 1 (Models) - Complete
✅ Phase 2 (Sync Service) - Complete

### Phase 4 Depends On
✅ Phase 1 - Complete
✅ Phase 2 - Complete
⏳ Phase 3 - Guard logic

### Phase 5 Depends On
✅ All previous phases

### Phase 6 Depends On
✅ All phases (testing all)

### Phase 7 Depends On
✅ All phases (documentation)

---

## ✅ QUALITY GATES (All Phases)

For each phase to be considered "complete":
- ✅ All code files created
- ✅ All functions have docstrings & type hints
- ✅ All tests passing (≥90% for backend)
- ✅ All error scenarios handled
- ✅ No TODOs or FIXMEs
- ✅ Audit logging implemented
- ✅ Documentation complete

---

## 🎯 FINAL DELIVERABLE

When all 7 phases complete, PR-023 will deliver:

**Complete Account Reconciliation System**:
- ✅ Real-time MT5 position synchronization
- ✅ Automated drawdown protection
- ✅ Market condition monitoring
- ✅ Automatic position closure on triggers
- ✅ RESTful API for status & control
- ✅ Comprehensive test coverage (85+ tests)
- ✅ Production-grade logging & error handling
- ✅ Complete documentation

**Business Value**:
- ✅ Prevents catastrophic losses (drawdown guard)
- ✅ Ensures position accuracy (reconciliation)
- ✅ Enables automated trading (guards + close)
- ✅ Provides real-time visibility (API)
- ✅ Reduces operational risk (monitoring)

---

## 🚀 NEXT: START PHASE 3

**When Ready**:
1. Review this plan
2. Create `backend/app/trading/monitoring/drawdown_guard.py`
3. Create `backend/app/trading/monitoring/market_guard.py`
4. Write tests (15+ tests)
5. Integrate with scheduler
6. Verify all tests passing

**Estimated Duration**: 2-3 hours

---

Generated: October 26, 2024
Status: Ready for Phase 3 🚀
