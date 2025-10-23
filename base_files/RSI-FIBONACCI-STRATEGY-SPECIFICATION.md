# RSI-Fibonacci Trading Strategy Specification

**Your Exact Strategy from DemoNoStochRSI.py**

## Strategy Overview

The RSI-Fibonacci strategy is a **SaaS signal generation service** where:
1. Your bot detects RSI-Fibonacci setups on GOLD (H1)
2. Signals are sent to clients via webhook
3. Clients approve trades (legally compliant)
4. Your bot auto-closes client trades when it closes yours
5. **Strategy details remain hidden from clients** (they only see trade signal: entry, no SL/TP)

---

## Exact Algorithm (From DemoNoStochRSI.py)

### 1. Setup Detection

#### Long Setup (Buy Signal)
```
1. RSI crosses BELOW 40 (trigger: rsi[i-1] >= 40 AND rsi[i] < 40)
   - Record: rsi_low_start_time, rsi_low_value, price_low
   
2. Wait for RSI to cross ABOVE 70 within 100 hours
   - Record: rsi_high_end_time, rsi_high_value, price_high
   
3. Setup Age: Must be < 1440 hours (60 days) from detection
   - If older, SKIP setup
   
4. Time Window: RSI >= 70 must occur within 100 hours of RSI < 40
   - If not, SKIP setup
   
5. Calculate Fibonacci Levels:
   - Range = price_high - price_low
   - Entry = price_high - (range * 0.74)
   - Stop Loss = price_low - (range * 0.27)
   - Take Profit = entry + (risk * rr_ratio)
   - where rr_ratio = 3.25, risk = entry - stop_loss
```

#### Short Setup (Sell Signal)
```
1. RSI crosses ABOVE 70 (trigger: rsi[i-1] <= 70 AND rsi[i] > 70)
   - Record: rsi_high_start_time, rsi_high_value, price_high
   
2. Wait for RSI to cross BELOW 40 within 100 hours
   - Record: rsi_low_end_time, rsi_low_value, price_low
   
3. Setup Age: Must be < 1440 hours (60 days) from detection
   - If older, SKIP setup
   
4. Time Window: RSI <= 40 must occur within 100 hours of RSI > 70
   - If not, SKIP setup
   
5. Calculate Fibonacci Levels:
   - Range = price_high - price_low
   - Entry = price_low + (range * 0.74)
   - Stop Loss = price_high + (range * 0.27)
   - Take Profit = entry - (risk * rr_ratio)
   - where rr_ratio = 3.25, risk = stop_loss - entry
```

---

### 2. Position Sizing (YOUR Formula)

```python
def calculate_position_size(entry_price, stop_loss, account_balance, risk_percent=0.02):
    """
    Calculate volume based on:
    - Account balance
    - Risk per trade (2% by default)
    - Entry price
    - Stop loss
    - Symbol: GOLD tick value, point size
    """
    risk_amount = account_balance * risk_percent  # $ amount to risk
    pip_distance = abs(entry_price - stop_loss) / point  # in pips
    lot_size = (risk_amount / (pip_distance * tick_value)) / 100  # convert to volume
    
    # Apply volume constraints
    lot_size = max(volume_min, min(lot_size, volume_max))
    lot_size = round(lot_size / volume_step) * volume_step
    
    return lot_size
```

**Key Values for GOLD:**
- `risk_per_trade`: 0.02 (2% of account)
- `rr_ratio`: 3.25
- `min_stop_distance_points`: 5
- `pip_value`: 10

---

### 3. Order Management

#### Pending Order Placement
```
1. Place LIMIT order at Fibonacci entry
2. Order expires after 100 hours
3. If order fills → track as "executed"
4. If order expires → cancel it
5. Store setup metadata: point1_price, point2_price, RSI values
```

#### Trade Closing
```
1. Monitor filled positions
2. When TP or SL hit → trade closes
3. Record: exit_price, profit, pips, exit_reason
4. For SaaS clients: auto-close their mirrored positions at same levels
```

---

## PR Architecture Alignment

### PR-7: RSI-Fibonacci Signal Generation
**Purpose**: Detect setups and generate signals

```
Input: Live OHLC bars from MT5
Process:
  1. Calculate RSI(14) on close prices
  2. Detect RSI crosses (70/40 thresholds)
  3. Wait for completion of setup (100-hour window)
  4. Calculate Fibonacci levels
  5. Validate setup age (< 1440 hours)
Output: 
  - Signal event: {signal_id, setup_id, direction, entry, timestamp}
  - Webhook to clients: {signal_id, direction, volume_for_1M_account, ticker}
  - Hidden: SL/TP (calculated server-side)
DB:
  - signals table: signal_id, direction, entry_price, created_at, setup_id
  - setups table: setup_id, point1_price, point2_price, rsi_high, rsi_low, etc.
  - Hidden from API response: stop_loss, take_profit (internal only)
```

### PR-8: Position Sizing & Risk Management
**Purpose**: Calculate position size for given account balance

```
Input: Entry price, stop loss, client account balance
Process:
  1. YOUR exact formula: risk_amount = balance * 0.02
  2. pip_distance = abs(entry - sl) / point
  3. lot_size = (risk_amount / (pip_distance * tick_value)) / 100
  4. Apply volume constraints
Output: lot_size for their account
Webhook Response to Client:
  {
    signal_id,
    direction,
    volume,  // <-- CLIENT'S VOLUME (not yours)
    you_approve?: false  // <-- Client must approve
  }
```

### PR-9: Client Portfolio Tracking
**Purpose**: Track client executions and auto-close logic

```
Input: Client approved signal, client traded
Process:
  1. Store: client_signal_execution (account_id, signal_id, volume, entry, status)
  2. Monitor: When signal closes (SL/TP hit), query all clients following signal
  3. For each client: Calculate their P&L, auto-close if needed
Output:
  - Client sees: Their positions, P&L, exit reason (TP/SL but not actual levels)
  - Client does NOT see: Your strategy logic, actual SL/TP, why signal was generated
DB:
  - client_signal_executions table
  - client_positions table
  - client_trades (closed positions with P&L)
```

---

## Key Compliance Points (Legal)

1. **Client Approval Required**: Webhook sent, client MUST click "Approve" before trade
2. **No Strategy Disclosure**: Clients get signal direction + volume only
3. **SL/TP Hidden**: Never sent to client, only used internally for auto-close
4. **P&L Tracking**: Full transparency on their executions and profits/losses
5. **Auto-Close**: Your bot closes client positions in sync with yours

---

## Configuration Parameters

```python
CONFIG = {
    'symbol': 'GOLD',
    'timeframe': 'H1',
    'rsi_window': 14,
    'rsi_threshold_high': 70,
    'rsi_threshold_low': 40,
    'fib_entry_ratio': 0.74,
    'fib_stop_ratio': 0.27,
    'rr_ratio': 3.25,
    'risk_per_trade': 0.02,  # 2% of account
    'setup_window_hours': 100,  # RSI must complete within 100 hours
    'max_setup_age_hours': 1440,  # 60 days
    'order_expiry_hours': 100,
    'min_stop_distance_points': 5,
}
```

---

## Files to Create

### PR-7: Signal Generation
- `backend/app/signals/rsi_fibonacci.py` - Strategy implementation
- `backend/app/signals/models.py` - DB models for signals/setups
- `backend/app/signals/schemas.py` - Pydantic schemas (NO SL/TP in API response)
- `backend/app/signals/routes.py` - Webhook endpoints for clients
- `backend/app/signals/service.py` - Core signal detection logic
- `backend/tests/test_rsi_fibonacci.py` - Strategy tests

### PR-8: Position Sizing
- `backend/app/positioning/calculator.py` - YOUR position sizing formula
- `backend/app/positioning/schemas.py` - Request/response models
- `backend/app/positioning/routes.py` - API endpoint
- `backend/tests/test_positioning.py` - Position sizing tests

### PR-9: Client Portfolio
- `backend/app/portfolio/client_tracker.py` - Track client executions
- `backend/app/portfolio/models.py` - Client position/trade models
- `backend/app/portfolio/routes.py` - Client dashboard APIs
- `backend/tests/test_client_portfolio.py` - Tracking tests

---

## No Longer Needed

Delete these directories/files (they're generic, not YOUR strategy):
- ~~`backend/app/signals/`~~ (replace with RSI-Fib only)
- ~~`backend/app/risk/`~~ (replace with positioning only)
- ~~`backend/app/analytics/`~~ (replace with client tracking only)
- ~~`backend/tests/test_pr7_signals.py`~~
- ~~`backend/tests/test_pr8_risk.py`~~
- ~~`backend/tests/test_pr9_analytics.py`~~

---

## Next Steps

1. ✅ Confirm this specification matches your strategy
2. Delete incorrect files from backend/
3. Implement PR-7, 8, 9 with YOUR exact logic
4. Create comprehensive tests
5. Document with PRs
6. Build frontend dashboard

