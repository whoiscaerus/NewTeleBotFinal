# FlaskAPI → FastAPI Gateway Migration

## Overview

This document maps legacy Flask routes to new FastAPI endpoints for PR-083: FlaskAPI Decommission.

**Why Migrate?**
- **Performance**: FastAPI async/await vs Flask synchronous blocking
- **Type Safety**: Pydantic validation, automatic OpenAPI docs
- **Maintainability**: Modern async stack, better error handling
- **Scalability**: Non-blocking I/O handles more concurrent requests

**Migration Strategy**:
1. Create FastAPI equivalents with identical business logic
2. Deploy compatibility shims with 301 redirects (feature-flagged)
3. Monitor `legacy_calls_total` metric to track old route usage
4. Gradual deprecation: 301 redirects → 410 Gone → remove Flask code

---

## Route Mapping

### REST Endpoints

| Legacy Flask Route | New FastAPI Route | Method | Auth | Status |
|--------------------|-------------------|--------|------|--------|
| `/` | `/dashboard` | GET | Query param `?user=` | 301 Moved |
| `/images/<filename>` | `/api/v1/charts/<filename>` | GET | X-User-ID header | 301 Moved |
| `/api/price` | `/api/v1/market/price` | GET | X-User-ID header | 301 Moved |
| `/api/trades` | `/api/v1/trading/trades` | GET | X-User-ID header | 301 Moved |
| `/api/images` | `/api/v1/charts` | GET | X-User-ID header | 301 Moved |
| `/api/positions` | `/api/v1/trading/positions` | GET | X-User-ID header | 301 Moved |
| `/api/metrics` | `/api/v1/analytics/performance` | GET | X-User-ID header | 301 Moved |
| `/api/indicators` | `/api/v1/market/indicators` | GET | X-User-ID header | 301 Moved |
| `/api/historical` | `/api/v1/market/historical` | GET | X-User-ID header | 301 Moved |

### Real-Time Communication

| Legacy SocketIO | New WebSocket | Event Type | Auth |
|-----------------|---------------|------------|------|
| `connect` | `/ws/market?user_id=<id>` | Connection | Query param `?user_id=` |
| `disconnect` | WebSocket close | Disconnection | N/A |
| `price_update` | `{"type": "price", ...}` | Server → Client | Validated on connect |
| `position_update` | `{"type": "position", ...}` | Server → Client | Validated on connect |

---

## Business Logic Preservation

### 1. Price Data (`/api/price`)
**Legacy Logic**:
```python
tick = mt5.symbol_info_tick(SYMBOL)
return {
    "symbol": SYMBOL,
    "bid": float(tick.bid),
    "ask": float(tick.ask),
    "time": datetime.now().isoformat()
}
```

**FastAPI Equivalent**:
- Use async MT5 wrapper (non-blocking)
- Same response format
- Pydantic model validation

### 2. Trades (`/api/trades`)
**Legacy Logic**:
```python
# Optional date filtering: ?since=YYYY-MM-DD&to=YYYY-MM-DD
query = "SELECT * FROM trades WHERE symbol = ?"
if since: query += " AND close_time >= ?"
if to: query += " AND close_time <= ?"
```

**FastAPI Equivalent**:
- Same SQL query with SQLAlchemy
- Query params: `since: datetime | None`, `to: datetime | None`
- Return same JSON structure

### 3. Positions (`/api/positions`)
**Legacy Logic**:
```python
positions = mt5.positions_get(symbol=SYMBOL)
for pos in positions:
    entry_price = pos.price_open
    current_price = tick.bid if buy else tick.ask
    pl_pips = (current_price - entry_price) * 10 if buy else (entry_price - current_price) * 10
    pl = pl_pips * volume * pip_value * EXCHANGE_RATE
    pos_dict['pl'] = float(pl)
```

**FastAPI Equivalent**:
- Same P&L calculation formula
- Async MT5 calls
- Real-time price fetching

### 4. Metrics (`/api/metrics`)
**Legacy Logic**:
```python
# Equity tracking
equity_series = [...]  # From trades table

# Drawdown calculation
running_max = equity_series.cummax()
drawdown = (equity_series - running_max) / running_max
avg_drawdown = drawdown.mean()
max_drawdown = drawdown.min()

# Sharpe ratio
returns = equity_series.pct_change()
sharpe = (returns.mean() / returns.std()) * sqrt(252)

# Win rate
win_rate = len([t for t in trades if t.profit > 0]) / len(trades)

# Pips per trade
pips_per_trade = sum(trade.profit_pips) / len(trades)
```

**FastAPI Equivalent**:
- Same pandas calculations
- Same formulas (drawdown, Sharpe, win rate)
- Async database queries

### 5. Indicators (`/api/indicators`)
**Legacy Logic**:
```python
# RSI calculation
rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M15, 0, 100)
df = pd.DataFrame(rates)
delta = df['close'].diff()
gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
rs = gain / loss
rsi = 100 - (100 / (1 + rs))

# Moving Average
ma = df['close'].rolling(window=20).mean()
```

**FastAPI Equivalent**:
- Same RSI formula (14-period)
- Same MA formula (20-period)
- Async MT5 data fetching

### 6. Historical Data (`/api/historical`)
**Legacy Logic**:
```python
# Query params: timeframe=15m, period=1y
timeframe_map = {
    '15m': mt5.TIMEFRAME_M15,
    '30m': mt5.TIMEFRAME_M30,
    '1h': mt5.TIMEFRAME_H1,
    '4h': mt5.TIMEFRAME_H4,
    '1d': mt5.TIMEFRAME_D1,
    '1w': mt5.TIMEFRAME_W1
}
rates = mt5.copy_rates_range(SYMBOL, mt5_timeframe, start_date, end_date)
data = [
    {
        "timestamp": int(row['time'] * 1000),
        "open": float(row['open']),
        "high": float(row['high']),
        "low": float(row['low']),
        "close": float(row['close'])
    }
    for _, row in df.iterrows()
]
```

**FastAPI Equivalent**:
- Same timeframe mapping
- Same period calculation (10y, 1y)
- Same OHLC response format

---

## Authentication Mechanism

**Legacy (Flask)**:
```python
class AuthResource(Resource):
    def check_auth(self):
        return request.headers.get('X-User-ID') == TELEGRAM_USER_ID
```

**New (FastAPI)**:
```python
async def verify_user_id(x_user_id: str = Header(...)):
    if x_user_id != settings.telegram_user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return x_user_id
```

**WebSocket Auth**:
- Legacy: Query param `?user_id=` checked on `connect` event
- New: Same query param, validated on WebSocket connection

---

## Real-Time Updates (SocketIO → WebSocket)

### Legacy Price Update Task
```python
def price_update_task():
    while True:
        tick = mt5.symbol_info_tick(SYMBOL)
        socketio.emit('price_update', {
            "symbol": SYMBOL,
            "bid": float(tick.bid),
            "ask": float(tick.ask),
            "time": datetime.now().isoformat()
        })
        time.sleep(1)
```

### FastAPI WebSocket Replacement
```python
@router.websocket("/ws/market")
async def market_websocket(
    websocket: WebSocket,
    user_id: str = Query(...)
):
    # Auth check
    if user_id != settings.telegram_user_id:
        await websocket.close(code=4401)
        return

    await websocket.accept()

    try:
        while True:
            tick = await mt5_async.symbol_info_tick(SYMBOL)
            await websocket.send_json({
                "type": "price",
                "symbol": SYMBOL,
                "bid": float(tick.bid),
                "ask": float(tick.ask),
                "time": datetime.now().isoformat()
            })
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {user_id}")
```

### Legacy Position Update Task
```python
# Track closed positions
previous_positions = {pos.ticket for pos in positions}
current_positions = {pos.ticket for pos in mt5.positions_get()}

# Emit close events
for ticket in previous_positions - current_positions:
    socketio.emit('position_update', {"ticket": ticket, "action": "close"})

# Emit open/update events
for pos in positions:
    action = "open" if pos.ticket not in previous_positions else "update"
    socketio.emit('position_update', {
        "ticket": pos.ticket,
        "entry_price": float(pos.price_open),
        "volume": float(pos.volume),
        "pl": float(pl),  # Same P&L formula
        "type": pos.type,
        "action": action
    })
```

### FastAPI WebSocket Replacement
```python
previous_positions = set()
while True:
    positions = await mt5_async.positions_get(symbol=SYMBOL)
    current_tickets = {pos.ticket for pos in positions}

    # Close events
    for ticket in previous_positions - current_tickets:
        await websocket.send_json({
            "type": "position",
            "ticket": ticket,
            "action": "close"
        })

    # Open/update events
    for pos in positions:
        action = "open" if pos.ticket not in previous_positions else "update"
        await websocket.send_json({
            "type": "position",
            "ticket": pos.ticket,
            "entry_price": float(pos.price_open),
            "volume": float(pos.volume),
            "pl": float(pl),
            "type": pos.type,
            "action": action
        })

    previous_positions = current_tickets
    await asyncio.sleep(1)
```

---

## Compatibility Shims (Feature-Flagged)

**Environment Variable**: `FLASK_COMPATIBILITY_MODE` (default: `true`)

**Behavior**:
- `FLASK_COMPATIBILITY_MODE=true`: 301 redirects from old routes → new routes
- `FLASK_COMPATIBILITY_MODE=false`: 410 Gone for all old routes

**Example Shim** (`compat.py`):
```python
@router.get("/api/price")
async def legacy_price_endpoint(request: Request):
    if settings.flask_compatibility_mode:
        # Increment telemetry
        metrics.legacy_calls_total.labels(route="/api/price").inc()

        # 301 redirect to new endpoint
        return RedirectResponse(
            url="/api/v1/market/price",
            status_code=301,
            headers={"X-Deprecation-Warning": "This endpoint moved to /api/v1/market/price"}
        )
    else:
        # 410 Gone (endpoint removed)
        raise HTTPException(
            status_code=410,
            detail="This endpoint has been removed. Use /api/v1/market/price"
        )
```

---

## Telemetry

**Metric**: `legacy_calls_total` (Counter)

**Purpose**: Track usage of old Flask routes to determine when it's safe to remove them

**Labels**:
- `route`: Old Flask route path (e.g., `/api/price`, `/api/trades`)

**Expected Behavior**:
- After migration: `legacy_calls_total` should be high (clients using old routes)
- After client updates: `legacy_calls_total` should trend toward zero
- When zero for 30 days: Safe to remove Flask code

**Query** (Prometheus):
```promql
# Total legacy calls per route (last 24h)
sum by (route) (increase(legacy_calls_total[24h]))

# Check if any legacy calls in last 30 days
sum(increase(legacy_calls_total[30d])) > 0
```

---

## Deprecation Timeline

### Phase 1: Deploy with Compatibility Mode ON (Week 1)
- Deploy FastAPI gateway with all new routes
- Enable `FLASK_COMPATIBILITY_MODE=true`
- 301 redirects active (old routes → new routes)
- Monitor `legacy_calls_total` to track old route usage

### Phase 2: Client Notification (Week 2-4)
- Email all API clients with deprecation notice
- Provide migration guide (this document)
- Set deprecation deadline: 90 days

### Phase 3: Gradual Flag Off (Week 5-12)
- Canary rollout: 10% → 50% → 100% with `FLASK_COMPATIBILITY_MODE=false`
- Old routes return 410 Gone instead of 301
- Monitor error rates, rollback if issues

### Phase 4: Remove Flask Code (Week 13+)
- When `legacy_calls_total == 0` for 30 days
- Remove `base_files/FlaskAPI.py`
- Remove compatibility shims from `gateway/compat.py`
- Update documentation

---

## Testing Requirements

### Unit Tests
- [ ] Each FastAPI route returns same response as Flask equivalent
- [ ] Auth validation works (X-User-ID header)
- [ ] Query params parsed correctly (dates, timeframes, periods)
- [ ] Business logic preserved (P&L, Sharpe, RSI, MA calculations)

### Integration Tests
- [ ] 301 redirects work when `FLASK_COMPATIBILITY_MODE=true`
- [ ] 410 Gone returned when `FLASK_COMPATIBILITY_MODE=false`
- [ ] `legacy_calls_total` increments on old route usage
- [ ] WebSocket connects/disconnects correctly
- [ ] WebSocket auth validation works

### End-to-End Tests
- [ ] Full user flow: connect → fetch price → fetch positions → disconnect
- [ ] Real-time updates: price changes → WebSocket event received
- [ ] Position tracking: open position → update event → close event
- [ ] Historical data: query different timeframes/periods

### Performance Tests
- [ ] FastAPI latency < Flask latency (expect 2-3x improvement)
- [ ] WebSocket handles 100+ concurrent connections
- [ ] No memory leaks in long-running WebSocket connections

---

## Rollback Procedure

If issues occur during migration:

1. **Immediate**: Set `FLASK_COMPATIBILITY_MODE=true` (re-enable redirects)
2. **Investigate**: Check logs for errors, monitor metrics
3. **Fix**: Patch FastAPI gateway if needed
4. **Redeploy**: Test in staging, then production
5. **Resume**: Continue deprecation timeline

**Criteria for Rollback**:
- Error rate > 5% on new routes
- Latency > 2x Flask baseline
- WebSocket connection failures > 10%
- Critical business logic errors (wrong P&L, incorrect Sharpe, etc.)

---

## Success Criteria

- [ ] All 9 REST endpoints migrated (identical responses)
- [ ] SocketIO replaced with FastAPI WebSocket (same events)
- [ ] Compatibility shims working (301 redirects, 410 Gone)
- [ ] Telemetry tracking legacy usage (`legacy_calls_total`)
- [ ] 100% test coverage (unit, integration, E2E)
- [ ] Performance improvement: FastAPI ≥2x faster than Flask
- [ ] Zero regressions: All existing clients work without changes
- [ ] Documentation complete: This migration doc + deprecation runbook
