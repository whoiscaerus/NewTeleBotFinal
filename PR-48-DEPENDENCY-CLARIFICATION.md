# PR-48 Dependency Analysis & Implementation Path

**Date**: November 1, 2025
**Analysis**: PR-46 vs PR-48 Dependency Clarification

---

## Executive Summary

**FINDING**: PR-48 (Risk Controls) does **NOT** require PR-46 (Strategy Registry) to be implemented first.

**Recommendation**: Proceed with immediate full PR-48 implementation.

---

## Dependency Analysis

### What PR-48 Actually Needs

PR-48 specification says it depends on:
- PR-4 (Approvals) ✅
- PR-5 (Clients) ✅
- **PR-46 (Strategies)** ❓
- PR-25 (Circuit Breakers) ⚠️

### What PR-46 Provides

PR-46 (Strategy Registry & Versioning) provides:
- Strategy model with version control
- Strategy lineage tracking
- Code signing and validation
- Release tagging (alpha/beta/stable)
- Signal ↔ Strategy version linking

**Purpose**: Track which version of a strategy created each signal for governance/audit.

### What PR-48 Actually Uses

Examining PR-48's specification, it needs:
1. ✅ Signals (exist: `backend/app/signals/models.py`)
2. ✅ Approvals (exist: `backend/app/approvals/models.py`)
3. ✅ Trades (exist: `backend/app/trading/store/models.py`)
4. ✅ Clients (exist: `backend/app/clients/`)
5. ✅ User accounts with balance (exist: `backend/app/accounts/`)
6. ❌ Strategy version references (would need PR-46)

### Critical Finding

**PR-48's purpose: Risk management via position sizing, exposure limits, and drawdown controls**

PR-48 doesn't actually need to know *which strategy* created a signal. It only needs to:
- Check client's current exposure (open positions)
- Calculate if new signal would violate risk limits
- Track exposure and drawdown for each client
- Enforce position sizing based on account balance

**The Signal model doesn't require a strategy_version_id**. Signals can be evaluated for risk independently of which strategy created them.

---

## Existing Infrastructure Available for PR-48

### 1. Trade Model ✅
**Location**: `backend/app/trading/store/models.py`

```python
class Trade(Base):
    __tablename__ = "trades"

    # Can extract:
    user_id: str              # ✅ Client ID
    symbol: str               # ✅ Instrument
    volume: Decimal           # ✅ Position size in lots
    trade_type: str           # ✅ BUY/SELL for direction
    entry_price: Decimal      # ✅ Entry level
    status: str               # ✅ OPEN/CLOSED (to filter open positions)
    entry_time: datetime      # ✅ When opened
    profit: Decimal           # ✅ Current P&L
```

**Use for PR-48**: Query open trades to calculate:
- Total exposure (sum of volumes)
- Exposure by instrument
- Exposure by direction (long/short)
- Current P&L for drawdown calculation

### 2. Signal Model ✅
**Location**: `backend/app/signals/models.py`

```python
class Signal(Base):
    __tablename__ = "signals"

    id: str                   # ✅ Signal ID
    user_id: str              # ✅ Client ID
    instrument: str           # ✅ Trading pair
    side: int                 # ✅ 0=buy, 1=sell
    price: float              # ✅ Entry level
```

**Use for PR-48**: Validate new signal before approval:
- Check if client can take this position
- Calculate safe position size
- Verify doesn't violate exposure caps

### 3. Approval Model ✅
**Location**: `backend/app/approvals/models.py`

```python
class Approval(Base):
    __tablename__ = "approvals"

    signal_id: str            # ✅ Which signal
    user_id: str              # ✅ Client ID
    decision: int             # ✅ 1=approved, 0=rejected
    created_at: datetime      # ✅ When decided
```

**Use for PR-48**: Track approval decisions and execution for exposure updates.

### 4. Account/Client Models ✅
**Location**: `backend/app/accounts/` and `backend/app/clients/`

**Available**: User account balance, subscription tier, client metadata.

**Use for PR-48**: Get account balance for:
- Position sizing calculations
- Drawdown % calculations
- Account equity tracking

### 5. Existing Guards ✅
**Location**: `backend/app/trading/runtime/guards.py`

```python
class Guards:
    max_drawdown_percent: float = 20.0

    async def check(self, state: TradeState) -> GuardCheckResult:
        if state.current_drawdown >= self.max_drawdown_percent:
            return GuardCheckResult(allowed=False)
```

**Use for PR-48**: Can leverage existing drawdown checking logic, but need to:
- Extend to store per-client profiles
- Add exposure snapshots
- Add position sizing algorithm
- Integrate with signal/approval flows

---

## Conclusion: PR-46 Not Blocking

**Why PR-48 doesn't need PR-46**:

1. **Signals are independent**: Risk checks can be applied to ANY signal, regardless of strategy
2. **No strategy versioning needed**: Risk management is about position exposure, not strategy governance
3. **Trade data exists**: We can calculate exposure from existing Trade model
4. **Account data exists**: We can get balance from existing Account model
5. **Approvals exist**: We can query execution history from existing Approval model

**What PR-48 would add if PR-46 existed**:
- Optional: Link exposures to strategy version for analytics ("Which strategy uses the most leverage?")
- Optional: Risk profiles per strategy ("Fib-RSI only 1 lot, Channel allows 2 lots")

But these are enhancements, not requirements.

---

## Implementation Path

### Option A: Implement PR-48 Independently ✅ RECOMMENDED

**Feasibility**: 100%

**Implementation**:
1. Create RiskProfile model (per-client settings, strategy-agnostic)
2. Create ExposureSnapshot model (current position tracking)
3. Implement risk service functions using existing Trade/Approval models
4. Add risk checks to signal creation
5. Add exposure updates to approval execution
6. Create full test suite
7. All dependencies available NOW

**Timeline**: 8-12 hours

**Blocker**: None

### Option B: Wait for PR-46 First

**Blocker**: PR-46 not yet implemented

**Additional features if combined**:
- Track which strategy version is using the most leverage
- Per-strategy risk profiles
- Risk analytics by strategy

**Timeline**: Unknown (PR-46 needs to be done first)

---

## Recommendation

### ✅ PROCEED WITH OPTION A: IMMEDIATE PR-48 IMPLEMENTATION

**Rationale**:
1. All hard dependencies already satisfied (Trade, Approval, Signal, Account models)
2. PR-46 is not blocking - can implement later if needed
3. Risk management is too critical to delay
4. Implementation fully independent
5. PR-48 can be extended later to support PR-46 data if desired

**Action**: Implement PR-48 immediately with all 15 deliverables, 90%+ test coverage, and full documentation.

---

## Implementation Verification

Can PR-48 implementation proceed without PR-46?

✅ **YES - All Required Data Exists**:

| Data Needed | Location | Status |
|-------------|----------|--------|
| Client ID | Approval.user_id | ✅ EXISTS |
| Open positions | Trade table (status=OPEN) | ✅ EXISTS |
| Position sizes | Trade.volume | ✅ EXISTS |
| Entry prices | Trade.entry_price | ✅ EXISTS |
| Instruments | Trade.symbol | ✅ EXISTS |
| Direction (buy/sell) | Trade.direction, Trade.trade_type | ✅ EXISTS |
| Account balance | Account table | ✅ EXISTS |
| P&L history | Trade.profit | ✅ EXISTS |
| Entry times | Trade.entry_time | ✅ EXISTS |
| Strategy info | Signal.payload (optional) | ✅ EXISTS |

**Conclusion**: Zero blocking issues. Ready to implement.

---

## PR-48 Implementation Checklist

Ready to proceed with:

- [ ] Backend risk module (models, service, routes)
- [ ] Database migration
- [ ] Signal integration (risk check before approval)
- [ ] Approval integration (exposure update after execution)
- [ ] Celery background tasks
- [ ] REST API endpoints (4 total)
- [ ] Comprehensive test suite (90%+ coverage)
- [ ] 4 documentation files
- [ ] Verification script

**Total Deliverables**: 15 files
**Estimated Time**: 8-12 hours
**Status**: Ready to start immediately

---

**Decision**: Proceed with full PR-48 implementation without waiting for PR-46.
