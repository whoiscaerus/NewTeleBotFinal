# PR-104 — Hidden SL/TP with Server-Side Auto-Close (Anti-Reselling Protection)

**Goal**
Prevent signal reselling by hiding stop-loss and take-profit levels from clients while maintaining full trade management control. Server monitors all client positions and automatically closes trades when owner's internal SL/TP levels are hit.

**Business Context**
- Trading bot generates signals with entry, SL, and TP
- Clients must NEVER see SL/TP levels (prevents them reselling your signals)
- Clients only see: Entry price + Direction (buy/sell)
- Server automatically closes client trades when YOUR hidden SL/TP is hit
- This is non-negotiable for business model protection

**Depends on**: PR-024a (EA Poll), PR-023 (Position Monitoring), PR-015 (Order Construction)

---

## Scope

### 1. Signal Schema Enhancement
- Add `owner_only` JSONB field to Signal model for sensitive params
- Store SL/TP in `owner_only` field (encrypted at rest)
- `payload` field remains for client-visible metadata only

### 2. EA Poll Response Redaction
- Modify PR-024a poll endpoint to NEVER return SL/TP to client EAs
- Return only: `entry_price`, `direction`, `instrument`, `volume`, `ttl_minutes`
- Mark these as "partial execution params" (no exit levels)

### 3. Server-Side Position Monitor Service
- Background daemon that polls ALL active client positions every 5-10 seconds
- Compares current market price vs. owner's hidden SL/TP for each position
- Issues close commands when levels breached
- Handles partial closes, slippage, retries

### 4. Remote Position Close API
- New endpoint: `POST /api/v1/admin/positions/{position_id}/close`
- Server-to-MT5 close execution (via EA ack system or direct MT5 API)
- Audit trail of all server-initiated closes

### 5. Position Tracking Table
- Links: Signal → Approval → Execution → OpenPosition
- Stores: entry price, entry time, volume, owner's hidden SL/TP
- Updated on EA ack (status: open/closed/failed)

---

## Deliverables

```
backend/app/signals/
  models.py               # Add owner_only JSONB field (encrypted)
  schemas.py              # SignalOut never includes owner_only
  encryption.py           # Fernet encryption for owner_only field

backend/app/ea/
  routes.py               # MODIFY: poll returns REDACTED params (no SL/TP)
  schemas.py              # ExecutionParamsOut (redacted version): entry_price, direction ONLY

backend/app/trading/positions/
  models.py               # OpenPosition(id, execution_id, signal_id, user_id, instrument, side,
                          #             entry_price, volume, owner_sl, owner_tp, status, opened_at, closed_at)
  monitor.py              # PositionMonitor: check_all_positions(), should_close_position()
  close.py                # close_position_remotely(position_id, reason) -> CloseResult
  routes.py               # POST /admin/positions/{id}/close (owner only)

backend/app/trading/monitoring/
  sl_tp_guard.py          # check_sl_tp_breach(position, current_price) -> BreachType | None
  close_executor.py       # execute_close_via_ea(device_id, position) OR execute_close_via_mt5_direct(account)

backend/schedulers/
  position_monitor.py     # runs every 5-10 seconds, checks all open positions

backend/alembic/versions/
  0007_open_positions.py  # OpenPosition table with owner_sl/owner_tp
  0008_signal_owner_only.py # Add owner_only JSONB to signals table
```

---

## Database Schema

### Signal Model Enhancement
```python
class Signal(Base):
    __tablename__ = "signals"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    instrument = Column(String(20), nullable=False)
    side = Column(Integer, nullable=False)  # 0=buy, 1=sell
    price = Column(Float, nullable=False)   # Entry price (visible to clients)
    status = Column(Integer, nullable=False, default=0)
    payload = Column(JSON, nullable=True)   # Client-visible metadata

    # NEW: Owner-only sensitive data (encrypted at rest)
    owner_only = Column(JSON, nullable=True)  # {"sl": 1950.0, "tp": 2000.0, "reason": "fib618"}

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
```

### OpenPosition Model (NEW)
```python
class OpenPosition(Base):
    __tablename__ = "open_positions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    execution_id = Column(String(36), ForeignKey("executions.id"), nullable=False)
    signal_id = Column(String(36), ForeignKey("signals.id"), nullable=False)
    approval_id = Column(String(36), ForeignKey("approvals.id"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    device_id = Column(String(36), ForeignKey("devices.id"), nullable=False)

    # Trade Details
    instrument = Column(String(20), nullable=False)
    side = Column(Integer, nullable=False)  # 0=buy, 1=sell
    entry_price = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)
    broker_ticket = Column(String(128), nullable=True)  # MT5 ticket number

    # Owner's Hidden Levels (NEVER exposed to client)
    owner_sl = Column(Float, nullable=True)    # Stop loss (hidden)
    owner_tp = Column(Float, nullable=True)    # Take profit (hidden)

    # Status Tracking
    status = Column(Integer, nullable=False, default=0)  # 0=open, 1=closed_sl, 2=closed_tp, 3=closed_manual, 4=closed_error
    opened_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)
    close_price = Column(Float, nullable=True)
    close_reason = Column(String(255), nullable=True)  # "sl_hit", "tp_hit", "manual_close", "drawdown_guard"

    # Relationships
    signal = relationship("Signal", back_populates="open_positions")
    execution = relationship("Execution", back_populates="position")
    user = relationship("User", back_populates="open_positions")
    device = relationship("Device", back_populates="open_positions")

    # Indexes
    __table_args__ = (
        Index("ix_open_positions_status", "status"),
        Index("ix_open_positions_user_status", "user_id", "status"),
        Index("ix_open_positions_signal", "signal_id"),
    )
```

---

## Logic Flow

### 1. Signal Creation (PR-021 Modified)
```python
# Strategy generates signal with FULL params
signal_data = {
    "instrument": "XAUUSD",
    "side": 0,  # buy
    "price": 2650.50,  # Entry (VISIBLE to clients)
    "payload": {"rsi": 35, "confidence": 0.85},  # VISIBLE metadata
    "owner_only": {  # HIDDEN from clients (encrypted)
        "sl": 2645.00,   # Stop loss
        "tp": 2670.00,   # Take profit
        "rr_ratio": 4.0,
        "strategy": "fib_rsi_618"
    }
}

# Create signal (owner_only encrypted before storage)
signal = create_signal(signal_data)
```

### 2. EA Poll (PR-024a Modified - REDACTED)
```python
# Client EA polls for approved signals
# Server returns REDACTED execution params (NO SL/TP!)

@router.get("/api/v1/client/poll")
async def poll(device: Device = Depends(device_auth)):
    approvals = get_approved_signals(device.client_id)

    response = []
    for approval in approvals:
        signal = approval.signal

        # CRITICAL: Return ONLY visible params
        exec_params = ExecutionParamsOut(
            entry_price=signal.price,        # ✅ VISIBLE
            direction="buy" if signal.side == 0 else "sell",  # ✅ VISIBLE
            instrument=signal.instrument,    # ✅ VISIBLE
            volume=0.1,                      # ✅ VISIBLE
            ttl_minutes=240,                 # ✅ VISIBLE
            # ❌ NO stop_loss field!
            # ❌ NO take_profit field!
        )

        response.append(ApprovedSignalOut(
            approval_id=approval.id,
            signal_id=signal.id,
            execution_params=exec_params,
            reason=None  # Don't expose strategy reasoning
        ))

    return PollResponse(approvals=response)
```

### 3. Position Opened (EA Ack)
```python
# Client EA executes trade and acknowledges
# POST /api/v1/client/ack
{
    "approval_id": "uuid-123",
    "status": "placed",
    "broker_ticket": "MT5-987654",
    "entry_price": 2650.50,
    "volume": 0.1
}

# Server creates OpenPosition with HIDDEN owner SL/TP
async def handle_ack(ack: AckRequest):
    execution = create_execution(ack)

    # Fetch signal to get owner's hidden SL/TP
    signal = get_signal(execution.approval.signal_id)
    owner_data = decrypt_owner_only(signal.owner_only)

    # Create OpenPosition with hidden levels
    position = OpenPosition(
        execution_id=execution.id,
        signal_id=signal.id,
        approval_id=execution.approval_id,
        user_id=execution.approval.user_id,
        device_id=execution.device_id,
        instrument=signal.instrument,
        side=signal.side,
        entry_price=ack.entry_price,
        volume=ack.volume,
        broker_ticket=ack.broker_ticket,
        owner_sl=owner_data["sl"],      # HIDDEN: 2645.00
        owner_tp=owner_data["tp"],      # HIDDEN: 2670.00
        status=0,  # open
        opened_at=datetime.utcnow()
    )
    db.add(position)
    db.commit()
```

### 4. Position Monitor (Background Service)
```python
# Runs every 5-10 seconds
async def monitor_all_positions():
    """Check all open positions against hidden SL/TP levels."""

    open_positions = db.query(OpenPosition).filter(
        OpenPosition.status == 0  # open
    ).all()

    for position in open_positions:
        # Fetch current market price
        current_price = get_current_price(position.instrument)

        # Check if owner's hidden SL/TP is breached
        breach = check_sl_tp_breach(position, current_price)

        if breach:
            logger.info(f"Position {position.id} breached {breach.type} at {current_price}")

            # Close position remotely
            result = await close_position_remotely(
                position_id=position.id,
                reason=f"{breach.type}_hit",
                close_price=current_price
            )

            if result.success:
                # Update position status
                position.status = 1 if breach.type == "sl" else 2
                position.closed_at = datetime.utcnow()
                position.close_price = current_price
                position.close_reason = f"{breach.type}_hit"
                db.commit()

                # Notify user (Telegram)
                send_close_notification(
                    user_id=position.user_id,
                    instrument=position.instrument,
                    reason=breach.type,
                    pnl=calculate_pnl(position, current_price)
                )
            else:
                logger.error(f"Failed to close position {position.id}: {result.error}")
                # Retry logic...
```

### 5. SL/TP Breach Detection
```python
def check_sl_tp_breach(position: OpenPosition, current_price: float) -> BreachType | None:
    """
    Check if current price has breached owner's hidden SL or TP.

    BUY trade: SL below entry, TP above entry
    SELL trade: SL above entry, TP below entry
    """

    if position.side == 0:  # BUY
        if position.owner_sl and current_price <= position.owner_sl:
            return BreachType(type="sl", level=position.owner_sl)
        if position.owner_tp and current_price >= position.owner_tp:
            return BreachType(type="tp", level=position.owner_tp)

    else:  # SELL
        if position.owner_sl and current_price >= position.owner_sl:
            return BreachType(type="sl", level=position.owner_sl)
        if position.owner_tp and current_price <= position.owner_tp:
            return BreachType(type="tp", level=position.owner_tp)

    return None
```

### 6. Remote Position Close
```python
async def close_position_remotely(position_id: str, reason: str, close_price: float) -> CloseResult:
    """
    Close a client's position remotely when owner's SL/TP is hit.

    Two methods:
    1. Send close command via EA (if EA supports it)
    2. Direct MT5 API call (if server has MT5 access)
    """

    position = db.query(OpenPosition).get(position_id)

    # Method 1: Via EA (preferred - client's MT5 terminal)
    if position.device:
        close_command = CloseCommand(
            position_id=position.id,
            broker_ticket=position.broker_ticket,
            reason=reason
        )

        # Store command in pending_closes table
        # EA will poll for close commands separately
        result = await send_close_command_to_ea(position.device_id, close_command)

        if result.success:
            return CloseResult(success=True, method="ea")

    # Method 2: Direct MT5 API (fallback - if server has MT5 credentials)
    if has_mt5_access(position.user_id):
        result = await close_via_mt5_direct(
            account=position.user.mt5_account,
            ticket=position.broker_ticket,
            volume=position.volume
        )

        if result.success:
            return CloseResult(success=True, method="mt5_direct")

    return CloseResult(success=False, error="No close method available")
```

---

## Security

### 1. Owner-Only Field Encryption
- `owner_only` JSONB field encrypted at rest using Fernet (symmetric encryption)
- Encryption key stored in secrets manager (PR-007)
- Decryption only occurs server-side, never sent to clients

### 2. API Redaction
- EA poll endpoint NEVER includes `owner_only` fields in response
- Schema validation prevents accidental exposure
- Admin endpoints require owner role (RBAC from PR-004)

### 3. Position Close Authorization
- Only server (owner role) can issue remote closes
- Client EAs cannot close positions themselves (must wait for server command or manual close)
- Audit log (PR-008) records all server-initiated closes

### 4. Rate Limiting
- Position monitor throttled to prevent MT5 API abuse
- Close commands queued and rate-limited per device
- Failed closes trigger owner alert (PR-018)

---

## Env Variables

```bash
# Position Monitoring
POSITION_MONITOR_ENABLED=true
POSITION_MONITOR_INTERVAL_SECONDS=10
POSITION_MONITOR_MAX_CONCURRENT=50

# Close Execution
CLOSE_VIA_EA_ENABLED=true          # Prefer EA-based closes
CLOSE_VIA_MT5_DIRECT_ENABLED=false  # Fallback to direct MT5 API

# Owner-Only Encryption
OWNER_ONLY_ENCRYPTION_KEY=base64-encoded-key  # From secrets manager

# Breach Detection
BREACH_PRICE_TOLERANCE_PIPS=2      # Allow 2 pips slippage before close
BREACH_RECHECK_DELAY_SECONDS=5     # Recheck price before closing (avoid false triggers)

# Alerts
CLOSE_NOTIFICATION_TELEGRAM=true
CLOSE_NOTIFICATION_EMAIL=false
```

---

## Telemetry

```python
# Counters
position_monitor_checks_total{status}      # open positions checked
position_breaches_total{type}              # sl, tp breaches detected
position_closes_total{method,result}       # ea, mt5_direct, success/fail
position_close_retries_total{reason}       # retry counts

# Gauges
open_positions_gauge{instrument}           # current open positions count
pending_closes_gauge                       # closes waiting for execution

# Histograms
position_monitor_duration_seconds          # monitor loop duration
position_close_duration_seconds{method}    # time to close position
breach_to_close_latency_seconds            # breach detection → close completion
```

---

## Tests

### Unit Tests
```python
def test_signal_owner_only_encrypted():
    """Owner-only field is encrypted before storage."""
    signal = create_signal(owner_only={"sl": 100, "tp": 200})
    assert signal.owner_only != {"sl": 100, "tp": 200}  # Encrypted
    decrypted = decrypt_owner_only(signal.owner_only)
    assert decrypted == {"sl": 100, "tp": 200}

def test_ea_poll_redacts_sl_tp():
    """EA poll response never includes SL/TP."""
    response = poll_endpoint(device)
    for approval in response.approvals:
        assert "stop_loss" not in approval.execution_params
        assert "take_profit" not in approval.execution_params
        assert approval.execution_params.entry_price is not None  # Only entry

def test_breach_detection_buy_sl():
    """Buy position SL breach detected correctly."""
    position = OpenPosition(side=0, entry_price=100, owner_sl=95, owner_tp=110)
    breach = check_sl_tp_breach(position, current_price=94)
    assert breach.type == "sl"

def test_breach_detection_sell_tp():
    """Sell position TP breach detected correctly."""
    position = OpenPosition(side=1, entry_price=100, owner_sl=105, owner_tp=90)
    breach = check_sl_tp_breach(position, current_price=89)
    assert breach.type == "tp"

def test_position_monitor_closes_on_breach():
    """Position monitor closes position when SL hit."""
    position = create_open_position(owner_sl=100)
    mock_price_feed(95)  # Below SL

    await monitor_all_positions()

    position = db.query(OpenPosition).get(position.id)
    assert position.status == 1  # closed_sl
    assert position.close_reason == "sl_hit"

def test_close_via_ea_queues_command():
    """Close command queued for EA to pick up."""
    result = await close_position_remotely(position.id, "sl_hit", 95.0)

    assert result.success
    assert result.method == "ea"

    # EA polls for close commands
    commands = get_pending_close_commands(device.id)
    assert len(commands) == 1
    assert commands[0].position_id == position.id
```

### Integration Tests
```python
async def test_end_to_end_sl_close():
    """Full flow: signal → approval → execution → position opened → SL hit → closed."""

    # 1. Create signal with hidden SL/TP
    signal = create_signal(
        instrument="GOLD",
        side=0,  # buy
        price=2650.0,
        owner_only={"sl": 2645.0, "tp": 2670.0}
    )

    # 2. User approves
    approval = create_approval(signal.id, user.id)

    # 3. EA polls (gets REDACTED params)
    response = await client.get("/api/v1/client/poll", headers=device_headers)
    assert response.status_code == 200
    exec_params = response.json()["approvals"][0]["execution_params"]
    assert "stop_loss" not in exec_params  # REDACTED
    assert exec_params["entry_price"] == 2650.0

    # 4. EA executes and acks
    ack_response = await client.post("/api/v1/client/ack", json={
        "approval_id": approval.id,
        "status": "placed",
        "broker_ticket": "MT5-123",
        "entry_price": 2650.0,
        "volume": 0.1
    }, headers=device_headers)
    assert ack_response.status_code == 200

    # 5. Position opened (with hidden SL)
    position = db.query(OpenPosition).filter_by(approval_id=approval.id).first()
    assert position.owner_sl == 2645.0  # Hidden
    assert position.status == 0  # open

    # 6. Market price drops to SL
    mock_price_feed("GOLD", 2644.5)  # Below SL

    # 7. Position monitor detects breach
    await monitor_all_positions()

    # 8. Position closed
    db.refresh(position)
    assert position.status == 1  # closed_sl
    assert position.close_reason == "sl_hit"
    assert position.closed_at is not None

    # 9. User notified
    notifications = get_telegram_messages(user.telegram_id)
    assert any("stop loss hit" in msg.lower() for msg in notifications)
```

---

## Verification/Rollout

### Stage 1: Testing (1-2 days)
1. Unit test all redaction logic
2. Integration test full signal → close flow
3. Verify encryption/decryption of owner_only field
4. Test breach detection with synthetic price feeds

### Stage 2: Dry-Run (3-5 days)
1. Deploy position monitor in "log-only" mode (no closes)
2. Monitor for 3-5 days with real positions
3. Verify breach detection accuracy
4. Tune thresholds (tolerance, recheck delay)

### Stage 3: Canary (1 week)
1. Enable auto-close for 1-2 test accounts only
2. Monitor close execution success rate
3. Verify no false positives (premature closes)
4. Confirm client EAs never see SL/TP

### Stage 4: Full Rollout (gradual)
1. Enable for 10% of users (owner feature flag)
2. Monitor for 48 hours
3. Increase to 50% → 100% over 1 week
4. Continuous monitoring of close latency and success rate

---

## Admin Tools

### Position Monitor Dashboard
```
GET /admin/positions/monitor/status

{
  "monitor_running": true,
  "last_check": "2025-10-30T20:00:00Z",
  "open_positions_count": 45,
  "pending_closes_count": 2,
  "avg_check_duration_ms": 850,
  "breaches_last_hour": {
    "sl": 3,
    "tp": 7
  },
  "close_success_rate_24h": 0.98
}
```

### Manual Close Override
```
POST /admin/positions/{position_id}/close

{
  "reason": "manual_override",
  "note": "Market conditions unsafe"
}
```

### Breach Detection Test
```
POST /admin/positions/{position_id}/test-breach

{
  "simulated_price": 2645.0
}

Response:
{
  "breach_detected": true,
  "breach_type": "sl",
  "would_close": true,
  "position": {...}
}
```

---

## Migration Path

### Existing Signals
```python
# Backfill script for existing signals
async def migrate_existing_signals():
    """Move SL/TP from payload to encrypted owner_only field."""

    signals = db.query(Signal).filter(Signal.owner_only == None).all()

    for signal in signals:
        payload = signal.payload or {}

        # Extract SL/TP if present
        owner_data = {}
        if "sl" in payload:
            owner_data["sl"] = payload.pop("sl")
        if "tp" in payload:
            owner_data["tp"] = payload.pop("tp")
        if "stop_loss" in payload:
            owner_data["sl"] = payload.pop("stop_loss")
        if "take_profit" in payload:
            owner_data["tp"] = payload.pop("take_profit")

        if owner_data:
            signal.owner_only = encrypt_owner_only(owner_data)
            signal.payload = payload

    db.commit()
```

---

## Documentation

### For Clients (Redacted)
> **What you see:**
> - Entry price
> - Direction (buy/sell)
> - Volume
> - Time-to-live
>
> **What happens automatically:**
> - Our system monitors your position
> - We close it at optimal exit (profit target or risk limit)
> - You receive notification when closed
> - No manual intervention needed

### For Owner (Full Context)
> **Architecture:**
> - Signals store SL/TP in encrypted `owner_only` field
> - Client EAs never receive SL/TP (redacted from API)
> - Position monitor checks all open positions every 10 seconds
> - When YOUR SL/TP is hit, server issues remote close command
> - Close executed via EA command queue or direct MT5 API
>
> **Why this works:**
> - Clients cannot resell signals (no SL/TP knowledge)
> - You maintain full control over exits
> - Automated execution ensures discipline
> - Audit trail proves all closes

---

## Notes

### Anti-Reselling Protection (Critical)
This architecture prevents clients from:
1. Seeing your SL/TP levels (redacted from all APIs)
2. Manually setting their own SL/TP (EA receives no such params)
3. Reverse-engineering your strategy (payload contains only generic metadata)
4. Reselling your signals (incomplete information = worthless)

### Trade Management Control
Server maintains full control:
1. Monitors all positions in real-time
2. Closes trades at YOUR levels (not client's choice)
3. Handles slippage, retries, errors automatically
4. Provides consistent execution across all clients

### Performance Considerations
- Position monitor scales to 1000s of open positions
- Price feed cached (updated every 1-5 seconds)
- Close commands batched and rate-limited
- Database indexes optimize position queries

### Future Enhancements
- Trailing stop logic (move SL as price moves in favor)
- Partial closes (close 50% at TP1, 50% at TP2)
- Breakeven logic (move SL to entry after X pips profit)
- Time-based closes (close after N hours if not hit SL/TP)
