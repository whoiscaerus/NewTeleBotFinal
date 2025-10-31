# PR-104 Quick Reference: Hidden SL/TP Architecture

## Problem Statement
**Your trading bot generates signals with entry, SL, and TP.**
**If clients see SL/TP, they can resell your signals.**
**Solution: Hide SL/TP from clients, let server auto-close trades when YOUR levels are hit.**

---

## Architecture in 3 Steps

### 1. Signal Creation (Owner Only)
```python
# Strategy generates signal with FULL data
signal = Signal(
    instrument="XAUUSD",
    side=0,  # buy
    price=2650.50,  # Entry (VISIBLE to clients)
    payload={"rsi": 35},  # VISIBLE metadata
    owner_only={  # HIDDEN from clients (encrypted)
        "sl": 2645.00,   # Stop loss
        "tp": 2670.00    # Take profit
    }
)
```

### 2. Client EA Poll (REDACTED Response)
```python
# Client EA: GET /api/v1/client/poll
# Server returns (NO SL/TP!):
{
    "approvals": [{
        "execution_params": {
            "entry_price": 2650.50,    # ✅ Visible
            "direction": "buy",         # ✅ Visible
            "volume": 0.1,              # ✅ Visible
            # ❌ NO stop_loss field
            # ❌ NO take_profit field
        }
    }]
}
```

### 3. Server Position Monitor (Auto-Close)
```python
# Background service runs every 10 seconds
async def monitor_all_positions():
    for position in open_positions:
        current_price = get_current_price(position.instrument)

        # Check against HIDDEN SL/TP (from owner_only)
        if current_price <= position.owner_sl:  # BUY: SL hit
            close_position_remotely(position.id, reason="sl_hit")

        if current_price >= position.owner_tp:  # BUY: TP hit
            close_position_remotely(position.id, reason="tp_hit")
```

---

## What Client Sees vs. What Owner Controls

| Data Point | Client Sees | Owner Controls | Stored In |
|------------|-------------|----------------|-----------|
| Entry Price | ✅ YES | ✅ YES | `Signal.price` |
| Direction | ✅ YES | ✅ YES | `Signal.side` |
| Volume | ✅ YES | ✅ YES | `payload.volume` |
| Stop Loss | ❌ NO | ✅ YES | `Signal.owner_only.sl` (encrypted) |
| Take Profit | ❌ NO | ✅ YES | `Signal.owner_only.tp` (encrypted) |
| Strategy | ❌ NO | ✅ YES | `Signal.owner_only.strategy` |

---

## Critical Security Rules

### ✅ ALWAYS
1. Store SL/TP in `Signal.owner_only` (encrypted)
2. Redact SL/TP from ALL client-facing APIs
3. Monitor positions server-side (not client-side)
4. Issue close commands from server when levels hit
5. Audit log all server-initiated closes

### ❌ NEVER
1. Include SL/TP in `ExecutionParamsOut` schema
2. Send `owner_only` field to client EAs
3. Allow clients to set their own SL/TP
4. Trust client to close positions at your levels
5. Expose strategy reasoning in client-visible fields

---

## Database Schema

### Signal Model (Modified)
```sql
CREATE TABLE signals (
    id VARCHAR(36) PRIMARY KEY,
    instrument VARCHAR(20) NOT NULL,
    side INTEGER NOT NULL,  -- 0=buy, 1=sell
    price FLOAT NOT NULL,   -- Entry (VISIBLE)
    payload JSONB,          -- Client-visible metadata
    owner_only JSONB,       -- Owner-only (ENCRYPTED): {sl, tp, strategy}
    status INTEGER,
    created_at TIMESTAMP
);
```

### OpenPosition Model (NEW)
```sql
CREATE TABLE open_positions (
    id VARCHAR(36) PRIMARY KEY,
    signal_id VARCHAR(36) REFERENCES signals(id),
    user_id VARCHAR(36) REFERENCES users(id),
    device_id VARCHAR(36) REFERENCES devices(id),

    instrument VARCHAR(20) NOT NULL,
    side INTEGER NOT NULL,
    entry_price FLOAT NOT NULL,
    volume FLOAT NOT NULL,

    owner_sl FLOAT,         -- HIDDEN stop loss
    owner_tp FLOAT,         -- HIDDEN take profit

    status INTEGER,         -- 0=open, 1=closed_sl, 2=closed_tp
    opened_at TIMESTAMP,
    closed_at TIMESTAMP,
    close_reason VARCHAR(255)
);
```

---

## API Endpoints

### Client EA Endpoints (REDACTED)
```bash
# Poll for approved signals (NO SL/TP in response)
GET /api/v1/client/poll
Headers:
  X-Device-Id: <device_uuid>
  X-Nonce: <random>
  X-Timestamp: <rfc3339>
  X-Signature: <hmac>

Response:
{
  "approvals": [{
    "execution_params": {
      "entry_price": 2650.50,
      "direction": "buy",
      "volume": 0.1,
      "ttl_minutes": 240
      # NO stop_loss
      # NO take_profit
    }
  }]
}
```

```bash
# Acknowledge trade execution
POST /api/v1/client/ack
{
  "approval_id": "uuid",
  "status": "placed",
  "broker_ticket": "MT5-123456",
  "entry_price": 2650.50,
  "volume": 0.1
}
```

```bash
# Poll for close commands (NEW)
GET /api/v1/client/close-commands
Response:
{
  "commands": [{
    "position_id": "uuid",
    "broker_ticket": "MT5-123456",
    "reason": "sl_hit"
  }]
}
```

### Owner/Admin Endpoints (FULL DATA)
```bash
# View position with hidden SL/TP
GET /admin/positions/{position_id}
Response:
{
  "id": "uuid",
  "instrument": "XAUUSD",
  "entry_price": 2650.50,
  "owner_sl": 2645.00,     # Only owner sees this
  "owner_tp": 2670.00,     # Only owner sees this
  "status": "open"
}
```

```bash
# Manually close position
POST /admin/positions/{position_id}/close
{
  "reason": "manual_override"
}
```

---

## Position Monitor Logic

### Breach Detection (BUY Trade)
```python
def check_sl_tp_breach(position: OpenPosition, current_price: float):
    """
    BUY trade:
    - SL below entry (loss protection)
    - TP above entry (profit target)
    """
    if position.side == 0:  # BUY
        # Stop loss breach: price drops below SL
        if position.owner_sl and current_price <= position.owner_sl:
            return BreachType(type="sl", level=position.owner_sl)

        # Take profit breach: price rises above TP
        if position.owner_tp and current_price >= position.owner_tp:
            return BreachType(type="tp", level=position.owner_tp)

    return None  # No breach
```

### Breach Detection (SELL Trade)
```python
def check_sl_tp_breach(position: OpenPosition, current_price: float):
    """
    SELL trade:
    - SL above entry (loss protection)
    - TP below entry (profit target)
    """
    if position.side == 1:  # SELL
        # Stop loss breach: price rises above SL
        if position.owner_sl and current_price >= position.owner_sl:
            return BreachType(type="sl", level=position.owner_sl)

        # Take profit breach: price drops below TP
        if position.owner_tp and current_price <= position.owner_tp:
            return BreachType(type="tp", level=position.owner_tp)

    return None  # No breach
```

---

## Testing Scenarios

### Scenario 1: BUY Trade, SL Hit
```
Signal: BUY XAUUSD @ 2650.50
Owner SL: 2645.00 (hidden)
Owner TP: 2670.00 (hidden)

1. Client EA polls → gets entry_price=2650.50 (NO SL/TP)
2. Client EA executes BUY @ 2650.50
3. Position opened with owner_sl=2645.00 (server-side only)
4. Price drops to 2644.50
5. Position monitor detects: 2644.50 <= 2645.00 → SL breach
6. Server issues close command
7. Position closed @ 2644.50 (loss: -6 pips)
8. Client notified: "Position closed at stop loss"
```

### Scenario 2: BUY Trade, TP Hit
```
Signal: BUY XAUUSD @ 2650.50
Owner SL: 2645.00 (hidden)
Owner TP: 2670.00 (hidden)

1. Client EA polls → gets entry_price=2650.50 (NO SL/TP)
2. Client EA executes BUY @ 2650.50
3. Position opened with owner_tp=2670.00 (server-side only)
4. Price rises to 2670.50
5. Position monitor detects: 2670.50 >= 2670.00 → TP breach
6. Server issues close command
7. Position closed @ 2670.50 (profit: +20 pips)
8. Client notified: "Position closed at profit target"
```

### Scenario 3: Client Cannot Resell Signal
```
Bad Actor Client:
1. Receives signal via EA poll
2. Gets ONLY: entry_price=2650.50, direction=buy
3. Attempts to resell: "BUY XAUUSD @ 2650.50"
4. PROBLEM: No SL/TP included → worthless signal
5. Buyers cannot manage risk → signal has no value
6. ✅ Anti-reselling protection WORKS
```

---

## Configuration

### Environment Variables
```bash
# Position Monitoring
POSITION_MONITOR_ENABLED=true
POSITION_MONITOR_INTERVAL_SECONDS=10
BREACH_PRICE_TOLERANCE_PIPS=2

# Encryption
OWNER_ONLY_ENCRYPTION_KEY=<base64-fernet-key>

# Close Execution
CLOSE_VIA_EA_ENABLED=true
CLOSE_VIA_MT5_DIRECT_ENABLED=false

# Alerts
CLOSE_NOTIFICATION_TELEGRAM=true
```

---

## Rollout Plan

### Phase 1: Dry-Run (3-5 days)
- Position monitor logs breaches but doesn't close
- Verify breach detection accuracy
- No impact on live trades

### Phase 2: Canary (1 week)
- Enable auto-close for 1-2 test accounts
- Monitor close success rate
- Confirm no false positives

### Phase 3: Gradual (1-2 weeks)
- 10% of users → 50% → 100%
- Monitor close latency and success rate
- Continuous performance monitoring

---

## Success Metrics

### Anti-Reselling Protection
- ✅ 100% of EA poll responses have NO SL/TP fields
- ✅ 0 instances of owner_only data in client logs
- ✅ Client EAs cannot extract SL/TP from any API

### Position Management
- ✅ >95% close success rate (SL/TP breaches executed)
- ✅ <5 second breach detection latency
- ✅ <10 second close execution time

### Performance
- ✅ Position monitor handles 1000+ positions in <10 seconds
- ✅ No database bottlenecks or timeouts
- ✅ Price feed cache hit rate >90%

---

## Troubleshooting

### Issue: Client complains they don't see SL/TP
**Resolution**: This is by design. Explain:
> "Our system manages exits automatically. You'll be notified when your position is closed at optimal levels. This protects our proprietary strategy while ensuring your trades are managed professionally."

### Issue: Position not closing at exact SL level
**Check**:
1. Breach tolerance setting (default 2 pips)
2. Price feed latency (should be <5 seconds)
3. Close command queue backlog
4. MT5 API rate limits

### Issue: False positive (position closed too early)
**Check**:
1. Price feed accuracy (compare vs. broker price)
2. Breach recheck delay (default 5 seconds)
3. Slippage during close execution
4. Review position monitor logs for breach detection

---

## Key Takeaways

1. **Clients never see SL/TP** → Cannot resell your signals
2. **Server monitors all positions** → Automatic exit management
3. **Owner maintains control** → Your levels, your strategy
4. **Encrypted storage** → SL/TP protected at rest and in transit
5. **Audit trail** → Every close logged with reason

**Bottom Line**: Your intellectual property is protected. Clients get execution without seeing your exit strategy.
