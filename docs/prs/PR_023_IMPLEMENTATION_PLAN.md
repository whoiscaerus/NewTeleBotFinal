# PR-023 Account Reconciliation - Implementation Plan

## 🎯 Objective
Real-time account reconciliation: sync client positions from MT5, verify trades match bot predictions, and auto-close positions when necessary (profit targets, risk limits, market conditions).

## 📋 Dependencies Status
- ✅ PR-016 (Trade Store) - Available
- ✅ PR-021 (Signals API) - COMPLETE
- ✅ PR-022 (Approvals API) - COMPLETE
- ✅ PR-011 (MT5 Session Manager) - Available

## 🏗️ Architecture Overview

### Core Components

1. **ReconciliationLog Model** - Track position sync events
2. **MT5 Sync Service** - Connect to MT5, fetch positions, compare vs DB
3. **Drawdown Guard** - Monitor equity, auto-close on drawdown threshold
4. **Market Guard** - Monitor price gaps and liquidity conditions
5. **Auto-Close Service** - Execute position closes with audit trail
6. **Reconciliation Routes** - API endpoints for status & monitoring

### Data Flow

```
MT5 Terminal
    ↓
sync_positions(user_id)
    ↓
Compare: MT5 positions vs DB trades
    ↓
ReconciliationLog → record divergences
    ↓
Drawdown Guard + Market Guard checks
    ↓
Should close? → auto_close_position()
    ↓
Audit Log + Telegram Alert
    ↓
Update position status in DB
```

## 📁 Files to Create

### 1. Models & Database
```
backend/app/trading/reconciliation/
├── models.py              # ReconciliationLog, PositionDivergence
└── __init__.py
```

**ReconciliationLog Schema**:
```python
ReconciliationLog(
    id: UUID (pk),
    user_id: UUID (fk → users),
    signal_id: UUID (fk → signals, nullable),
    approval_id: UUID (fk → approvals, nullable),
    mt5_position_id: int,
    entry_price: float,
    current_price: float,
    volume: float,
    direction: str ('buy'|'sell'),
    matched: bool,
    divergence_reason: str (nullable),
    slippage_pips: float (nullable),
    created_at: datetime
)
```

### 2. Services
```
backend/app/trading/reconciliation/
├── mt5_sync.py            # sync_positions(user_id) → List[Position]
├── auto_close.py          # should_close_position(position) → reason?
├── drawdown_guard.py      # check_max_drawdown(account) → bool
├── market_guard.py        # check_market_conditions(symbol) → bool
└── service.py             # Main orchestration service
```

### 3. Routes & API
```
backend/app/trading/reconciliation/
└── routes.py
```

**Endpoints**:
- `GET /api/v1/reconciliation/status` - Current account status
- `GET /api/v1/reconciliation/positions` - Live positions (with MT5 sync)
- `GET /api/v1/reconciliation/logs/{user_id}` - Historical reconciliation logs
- `POST /api/v1/reconciliation/sync` - Manually trigger sync (admin)

### 4. Migration
```
backend/alembic/versions/0004_reconciliation.py
```

### 5. Tests
```
backend/tests/
├── test_pr_023_reconciliation.py
├── test_pr_023_drawdown_guard.py
└── test_pr_023_market_guard.py
```

## 🔧 Configuration (Environment Variables)

```bash
# Drawdown & Risk Guards
MAX_DRAWDOWN_PERCENT=20
MIN_EQUITY_GBP=100
PRICE_GAP_ALERT_PERCENT=5
LIQUIDITY_CHECK_ENABLED=true

# Sync Frequency
RECONCILIATION_SYNC_INTERVAL=10  # seconds
DRAWDOWN_CHECK_INTERVAL=30       # seconds
MARKET_CHECK_INTERVAL=60         # seconds

# Thresholds
MIN_POSITION_SIZE_LOTS=0.01
MAX_SLIPPAGE_PIPS=5
LIQUIDITY_SPREAD_THRESHOLD_PIPS=2.5
```

## 🔐 Security Considerations

1. **Drawdown Guard is Non-Negotiable**
   - Can't be bypassed or delayed by user
   - Prevents catastrophic losses
   - Warning sent 10 seconds before auto-close

2. **Only Auto-System Can Liquidate**
   - User cannot manually prevent auto-close
   - All closes logged to Audit Log with reason + timestamp
   - Telegram alert sent immediately

3. **Rate Limiting**
   - Prevent sync spam (1 sync per 10 seconds max)
   - Prevent close spam (1 close per symbol per 30 seconds)

4. **Permission Checks**
   - Only account owner can view their reconciliation
   - Only admin can manually trigger sync

## 📊 Telemetry Metrics

```
mt5_position_sync_total              # Counter: position sync attempts
reconciliation_divergences_total     # Counter: divergences by reason
drawdown_guard_triggers_total        # Counter: drawdown events
positions_autoclosed_total           # Counter: auto-closes by reason
reconciliation_latency_seconds       # Histogram: sync duration
mt5_positions_total                  # Gauge: current open positions
account_equity_gbp                   # Gauge: current account equity
account_drawdown_percent             # Gauge: current drawdown
```

## ✅ Implementation Checklist

### Phase 1: Database & Models (1-2 hours)
- [ ] Create ReconciliationLog model
- [ ] Create Alembic migration
- [ ] Add indexes (user_id, created_at; reason)
- [ ] Run migration locally

### Phase 2: MT5 Sync Service (2-3 hours)
- [ ] Implement mt5_sync.py with connect/fetch/compare logic
- [ ] Handle MT5 connection errors gracefully
- [ ] Record divergences to DB
- [ ] Detect slippage, partial fills, broker closes
- [ ] Add retry logic with exponential backoff

### Phase 3: Guard Services (1-2 hours)
- [ ] Implement drawdown_guard.py
- [ ] Implement market_guard.py
- [ ] Add equity peak tracking
- [ ] Test guard logic with various scenarios

### Phase 4: Auto-Close Service (1-2 hours)
- [ ] Implement position close via MT5 API
- [ ] Record close to audit log
- [ ] Notify user via Telegram
- [ ] Update trade status in DB

### Phase 5: API Routes (1 hour)
- [ ] Create routes for status/positions/logs
- [ ] Add permission checks
- [ ] Wire up metrics recording

### Phase 6: Tests (2-3 hours)
- [ ] Unit tests: sync, guards, close logic
- [ ] Integration tests: full workflow
- [ ] Edge cases: partial fills, gap closes, etc.
- [ ] Security tests: permissions, rate limits

### Phase 7: Documentation (1 hour)
- [ ] API endpoint documentation
- [ ] Guard behavior explained
- [ ] Test coverage report
- [ ] Deployment notes

## 🧪 Test Scenarios

### Sync Position Tests
1. ✅ Position exists in MT5 → logged as matched
2. ✅ Position manually closed in MT5 → detected in sync
3. ✅ Partial fill (1 order → 2 positions) → reconciliation detects + consolidates
4. ✅ Slippage on entry → recorded with pips deviation

### Drawdown Guard Tests
1. ✅ Equity drops 20% from peak → auto-close all positions
2. ✅ User receives warning 10 seconds before close
3. ✅ Close recorded to audit log with reason
4. ✅ Telegram alert sent immediately

### Market Guard Tests
1. ✅ Price gap 10% unexpectedly → market guard triggers
2. ✅ Bid-ask spread > threshold → liquidity crisis detected
3. ✅ Position marked for close
4. ✅ Admin can review flagged positions

### Edge Cases
1. ✅ Zero positions → no divergence
2. ✅ MT5 connection fails → retry with backoff, alert ops
3. ✅ Multiple positions, only some closed → partial reconciliation
4. ✅ Race condition: position closed during sync → handled gracefully

## 📈 Success Metrics

After implementation:
- [ ] 100% of open positions sync successfully every 10 seconds
- [ ] Zero divergences in normal market conditions
- [ ] Drawdown guard prevents account losses > threshold
- [ ] All closes logged and auditable
- [ ] Telegram alerts sent within 5 seconds of event
- [ ] No false positives (unnecessary closes)
- [ ] Zero sync errors in 24-hour test run

## 🚀 Deployment Readiness

### Pre-Deployment
- [ ] All tests passing locally
- [ ] Code review approved
- [ ] Load testing: sync can handle high frequency
- [ ] MT5 API reliability verified
- [ ] Telegram alerts working

### Deployment Steps
1. Merge to main branch
2. GitHub Actions CI/CD runs
3. Deploy to staging
4. Verify with test MT5 account
5. Deploy to production
6. Monitor metrics closely for 24 hours

### Rollback Plan
If critical issues:
1. Disable auto-close guard (manual intervention only)
2. Keep monitoring sync (read-only mode)
3. Investigate root cause
4. Fix and redeploy

## 📚 Reference Documentation

**Master PR Doc**: `/base_files/Final_Master_Prs.md` (PR-023 section)

**Related PRs**:
- PR-011: MT5 Session Manager
- PR-016: Trade Store
- PR-021: Signals API
- PR-022: Approvals API

---

## Next Steps

1. ✅ **Review this plan** (confirm architecture & scope)
2. 🔄 **Start Phase 1** (Models & Database)
3. 🔄 **Continue through phases** (Services → Routes → Tests)
4. ✅ **Complete & verify** (all tests passing)
5. ✅ **Deploy to production**

---

**Status**: Ready to implement
**Estimated Duration**: 10-14 hours (one dev sprint)
**Dependencies**: All met ✅
**Blockers**: None

Let's begin! 🚀
