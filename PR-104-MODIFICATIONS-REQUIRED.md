# PR-104 Implementation: Required Modifications to Existing PRs

## Overview
PR-104 introduces **Hidden SL/TP with Server-Side Auto-Close** to prevent signal reselling. This requires modifications to several existing PRs in the master document.

---

## Critical Understanding

### Business Requirement
- **Your trading bot** generates signals with entry, SL, and TP
- **Clients must NEVER see** SL/TP levels (prevents reselling your signals)
- **Clients only see**: Entry price + Direction
- **Server automatically closes** client trades when YOUR hidden SL/TP is hit

### Why This Wasn't in Original PRs
The original PR specifications assumed clients would see full execution params (entry/SL/TP). This exposes your intellectual property and enables signal reselling. PR-104 fixes this architectural gap.

---

## Required Modifications

### 1. ⚠️ PR-021 (Signals API) - CRITICAL MODIFICATION

**File**: `base_files/Final_Master_Prs.md` lines ~900-970

**Current State**:
```
Signal model has:
- instrument, side, price (entry), status, payload (generic JSONB)
```

**Required Change**:
Add new field to Signal model:
```python
class Signal(Base):
    # ... existing fields ...
    payload = Column(JSON, nullable=True)      # Client-visible metadata

    # NEW FIELD (add to migration)
    owner_only = Column(JSON, nullable=True)   # Owner-only sensitive data (encrypted)
    # Stores: {"sl": 2645.0, "tp": 2670.0, "rr_ratio": 4.0, "strategy": "fib_rsi"}
```

**Migration Required**: `0003b_signal_owner_only.py`

**Why**: Separate client-visible data (payload) from owner-only sensitive data (SL/TP)

---

### 2. ⚠️ PR-024a (EA Poll/Ack API) - CRITICAL MODIFICATION

**File**: `base_files/Final_Master_Prs.md` lines ~1290-1360

**Current State (PROBLEM)**:
```
Logic:
* Poll: return approvals for this device's client_id, decision=approved,
  not yet acked, plus **FULL execution params (entry/SL/TP/TTL)** from PR-015.
```

**Required Change**:
```
Logic:
* Poll: return approvals for this device's client_id, decision=approved,
  not yet acked, plus **REDACTED execution params (entry/direction/TTL ONLY - NO SL/TP)**.
  SL/TP are stored in Signal.owner_only (encrypted) and NEVER sent to clients.
```

**Schema Change**:
```python
# OLD (exposes SL/TP - BAD!)
class ExecutionParamsOut(BaseModel):
    entry_price: float
    stop_loss: float      # ❌ REMOVE
    take_profit: float    # ❌ REMOVE
    volume: float
    ttl_minutes: int

# NEW (redacted - client only sees entry)
class ExecutionParamsOut(BaseModel):
    entry_price: float     # ✅ VISIBLE
    direction: str         # ✅ VISIBLE (buy/sell)
    instrument: str        # ✅ VISIBLE
    volume: float          # ✅ VISIBLE
    ttl_minutes: int       # ✅ VISIBLE
    # NO stop_loss field
    # NO take_profit field
```

**Why**: This is the core anti-reselling protection. Clients cannot see SL/TP, so they cannot resell your signals.

---

### 3. ⚠️ PR-015 (Order Construction) - MINOR MODIFICATION

**File**: `base_files/Final_Master_Prs.md` lines ~678-720

**Current State**:
```
Deliverables:
backend/app/trading/orders.py   # build_order(signal, params) -> Order(entry, sl, tp, ...)
```

**Required Change**:
Add new function variant:
```python
# Existing: build_order_full() - for internal use (owner)
def build_order_full(signal, params) -> Order:
    """Build order with FULL params including SL/TP."""
    owner_data = decrypt_owner_only(signal.owner_only)
    return Order(
        entry=signal.price,
        sl=owner_data["sl"],
        tp=owner_data["tp"],
        ...
    )

# NEW: build_order_redacted() - for client EAs
def build_order_redacted(signal, params) -> OrderRedacted:
    """Build order with REDACTED params (no SL/TP)."""
    return OrderRedacted(
        entry=signal.price,
        direction="buy" if signal.side == 0 else "sell",
        volume=params.get("volume", 0.1),
        ttl_minutes=params.get("ttl_minutes", 240),
        # No SL/TP fields
    )
```

**Why**: Need separate order construction paths for owner (full) vs. clients (redacted)

---

### 4. ✅ PR-023 (Account Reconciliation) - ENHANCEMENT

**File**: `base_files/Final_Master_Prs.md` lines ~980-1080

**Current State**:
Already has auto-close functionality for:
- Drawdown guards (20% loss)
- Market condition guards (gaps, liquidity)

**Required Addition**:
Add SL/TP breach monitoring:
```python
# Existing: auto_close.py has should_close_position()
def should_close_position(position, account) -> reason: str | None:
    # Existing checks...
    if drawdown > MAX_DRAWDOWN:
        return "drawdown_breach"
    if market_unsafe():
        return "market_condition"

    # NEW: Add SL/TP breach check
    if sl_tp_breached(position):
        return "sl_hit" or "tp_hit"
```

**Deliverables Addition**:
```
backend/app/trading/monitoring/
  sl_tp_guard.py          # NEW: check_sl_tp_breach(position, current_price)
```

**Why**: Integrate with existing position monitoring infrastructure

---

### 5. 🆕 PR-104 (New PR) - ADD TO MASTER DOCUMENT

**File**: `base_files/Final_Master_Prs.md`

**Insert After**: PR-046 (Copy-Trading Risk & Compliance Controls), before PR-047

**Location**: After line ~2200

**Content**: Full PR-104 specification (see `PR-104-HIDDEN-SL-TP-AUTO-CLOSE.md`)

**Why**: This is a NEW PR that wasn't in the original plan but is critical for business model protection

---

## Implementation Order

### Phase 1: Database & Schema (1-2 days)
1. ✅ Add `owner_only` field to Signal model (PR-021 modification)
2. ✅ Create OpenPosition model (PR-104 new table)
3. ✅ Run migrations: `0003b_signal_owner_only.py`, `0007_open_positions.py`
4. ✅ Backfill existing signals (move SL/TP from payload to owner_only)

### Phase 2: API Redaction (1 day)
1. ✅ Modify EA Poll endpoint to return REDACTED params (PR-024a modification)
2. ✅ Update ExecutionParamsOut schema (remove stop_loss, take_profit fields)
3. ✅ Add encryption/decryption helpers for owner_only field
4. ✅ Test: Verify EA poll response NEVER includes SL/TP

### Phase 3: Position Tracking (2 days)
1. ✅ Implement OpenPosition creation on EA ack
2. ✅ Store owner's hidden SL/TP in OpenPosition table
3. ✅ Link Execution → OpenPosition → Signal
4. ✅ Test: Position created with correct hidden levels

### Phase 4: Position Monitor (2-3 days)
1. ✅ Build position monitor background service
2. ✅ Implement SL/TP breach detection logic
3. ✅ Add price feed integration
4. ✅ Test: Breach detection accuracy (buy/sell scenarios)

### Phase 5: Remote Close (2-3 days)
1. ✅ Implement close_position_remotely() function
2. ✅ Add close command queue for EAs
3. ✅ Implement direct MT5 API close (fallback)
4. ✅ Test: Close execution success rate

### Phase 6: Integration & Testing (3-5 days)
1. ✅ End-to-end test: Signal → Approval → Execution → Position → Breach → Close
2. ✅ Verify client never sees SL/TP at any point
3. ✅ Test close notification delivery
4. ✅ Load test: 100+ open positions monitored correctly

### Phase 7: Rollout (1-2 weeks)
1. ✅ Dry-run mode (log only, no closes) for 3-5 days
2. ✅ Canary rollout (1-2 test accounts) for 1 week
3. ✅ Gradual rollout (10% → 50% → 100%) over 1 week
4. ✅ Monitor close success rate, false positives, latency

---

## Testing Checklist

### Unit Tests
- [ ] Signal.owner_only field encrypted/decrypted correctly
- [ ] EA poll response never includes stop_loss or take_profit fields
- [ ] Breach detection: BUY trade, SL below entry, price drops → SL breach detected
- [ ] Breach detection: SELL trade, TP below entry, price drops → TP breach detected
- [ ] Position monitor: Breach detected → close_position_remotely() called
- [ ] Close command queued for EA correctly

### Integration Tests
- [ ] Full flow: Signal creation → EA poll (redacted) → Position opened → SL hit → Position closed
- [ ] Client EA never receives SL/TP at any API endpoint
- [ ] Position status updated correctly after close
- [ ] User notified via Telegram when position closed
- [ ] Audit log records server-initiated close with reason

### Security Tests
- [ ] Attempt to access owner_only via EA poll → not present in response
- [ ] Attempt to decode owner_only → encrypted data unreadable
- [ ] Non-owner user cannot access /admin/positions/close endpoint
- [ ] Rate limiting prevents position monitor spam

### Performance Tests
- [ ] Position monitor handles 1000+ open positions in <10 seconds
- [ ] Price feed cache reduces external API calls
- [ ] Close commands batched and rate-limited correctly
- [ ] Database queries use indexes (no full table scans)

---

## Critical Success Factors

### 1. ✅ Client Redaction (Non-Negotiable)
- EA poll response MUST NOT include SL/TP
- No other endpoint can expose owner_only data to clients
- Encryption prevents database access from revealing SL/TP

### 2. ✅ Server Control (Non-Negotiable)
- Server must monitor all positions in real-time
- Server must issue close commands when levels hit
- Clients cannot override or prevent server closes

### 3. ✅ Reliable Execution (Critical)
- Close commands must execute with high success rate (>95%)
- Retries handle transient failures
- Owner alerted on persistent close failures

### 4. ✅ Performance (Important)
- Monitor loop completes in <10 seconds (1000+ positions)
- Breach detection latency <5 seconds (detection → close command)
- No database bottlenecks or API rate limit issues

---

## Documentation Updates

### Master PR Document
```markdown
# Add after PR-046, before PR-047:

# PR-104 — Hidden SL/TP with Server-Side Auto-Close (Anti-Reselling Protection)

**Goal**
Prevent signal reselling by hiding stop-loss and take-profit levels from clients
while maintaining full trade management control via server-side position monitoring
and automatic closure.

**Depends on**: PR-021 (Signals), PR-024a (EA Poll), PR-015 (Orders), PR-023 (Monitoring)

**Key Changes to Existing PRs**:
- **PR-021**: Add Signal.owner_only encrypted field for SL/TP
- **PR-024a**: Redact EA poll response (remove SL/TP from ExecutionParamsOut)
- **PR-015**: Add build_order_redacted() variant for client EAs
- **PR-023**: Enhance auto_close with SL/TP breach detection

**New Components**:
- OpenPosition table (tracks live positions with hidden owner SL/TP)
- Position monitor service (checks all positions every 10 seconds)
- Remote close API (issues close commands when SL/TP hit)
- Close command queue (EA polls for close instructions)

**Anti-Reselling Protection**:
Clients receive ONLY: Entry price, Direction, Volume, TTL
Clients NEVER see: Stop loss, Take profit, Strategy reasoning

For full specification, see: /PR-104-HIDDEN-SL-TP-AUTO-CLOSE.md
```

### Copilot Instructions
Add to `.github/copilot-instructions.md`:
```markdown
## Critical: Hidden SL/TP Architecture (PR-104)

**Anti-Reselling Protection (Non-Negotiable)**:
- Signal.owner_only field stores SL/TP (encrypted, never exposed to clients)
- EA poll endpoint returns REDACTED params (entry/direction ONLY, no SL/TP)
- Server monitors all positions and closes trades when owner's hidden SL/TP hit

**When implementing ANY signal/approval/EA code**:
- ✅ NEVER expose Signal.owner_only to client APIs
- ✅ NEVER include stop_loss or take_profit in ExecutionParamsOut schema
- ✅ ALWAYS use build_order_redacted() for client-facing code
- ✅ ALWAYS use build_order_full() for owner/admin code only

**When in doubt**: Client EAs see ONLY entry price and direction, nothing more.
```

---

## Owner Action Items

### Immediate (Before Starting Implementation)
1. [ ] Review PR-104 specification document
2. [ ] Confirm this architecture matches your business requirements
3. [ ] Approve modifications to existing PRs (021, 024a, 015, 023)
4. [ ] Decide on close method preference (EA command queue vs. direct MT5 API)

### During Implementation
1. [ ] Provide test MT5 account credentials for integration testing
2. [ ] Review EA poll response schema (confirm SL/TP redaction is correct)
3. [ ] Test with real signal to verify client never sees SL/TP
4. [ ] Monitor dry-run phase for false positives

### Before Rollout
1. [ ] Approve close notification templates (Telegram messages)
2. [ ] Set position monitor interval (recommend 10 seconds)
3. [ ] Set breach tolerance (recommend 2 pips slippage buffer)
4. [ ] Approve canary test accounts for initial rollout

---

## Summary

**What This Fixes**:
- ✅ Prevents clients from seeing your SL/TP levels (anti-reselling)
- ✅ Maintains your control over trade exits (server-side monitoring)
- ✅ Automates position management (no manual intervention needed)
- ✅ Protects your intellectual property (strategy remains secret)

**What Changes**:
- Signal model gains encrypted owner_only field
- EA poll endpoint redacts SL/TP from response
- New position monitoring service watches all open trades
- Server issues close commands when YOUR levels are hit

**What Stays the Same**:
- Signal generation logic (PR-014)
- Approval workflow (PR-022)
- EA authentication (PR-024a HMAC)
- Trade execution and ack flow

**Bottom Line**: Your trading signals remain YOUR intellectual property. Clients get execution without seeing your exit strategy.
