# ⚠️ CRITICAL: PR-014 STRATEGY MISMATCH IDENTIFIED

**Status**: PR-014 REQUIRES COMPLETE REWRITE
**Severity**: CRITICAL - Strategy logic does not match DemoNoStochRSI
**Date**: 2024
**Action Required**: User confirmation to proceed with rewrite

---

## PROBLEM STATEMENT

PR-014 (Fib-RSI Strategy) was built with **INCORRECT signal detection logic** compared to the actual trading strategy in `DemoNoStochRSI.py`.

**Current PR-014**: ❌ WRONG
- Only checks instantaneous RSI values
- No RSI crossing/pattern detection
- No wait-for-completion logic

**Actual DemoNoStochRSI**: ✅ CORRECT
- Tracks RSI crossing events across time
- Waits for complete RSI patterns
- Uses 100-hour window to confirm patterns

---

## DEMONOSTOCHRSI STRATEGY LOGIC (ACTUAL)

### SHORT Setup Pattern (Lines 557-693)
```
1. RSI crosses ABOVE 70 (overbought condition starts)
   └─ window['RSI'].iloc[i-1] <= 70 AND window['RSI'].iloc[i] > 70

2. Track highest price while RSI > 70
   └─ price_high = find highest price in period where RSI > 70

3. WAIT for RSI to fall to <= 40 (within 100-hour window)
   └─ Look forward from overbought, find when RSI <= 40
   └─ CRITICAL: Can take MANY hours to complete pattern

4. Track lowest price when RSI <= 40
   └─ price_low = find lowest price when RSI <= 40

5. Calculate Fibonacci levels
   └─ fib_range = price_high - price_low
   └─ entry = price_low + fib_range * 0.74
   └─ stop_loss = price_high + fib_range * 0.27

6. Place SHORT (sell limit) order at entry price
   └─ Wait for execution at entry level
   └─ Stop loss above high
   └─ Take profit calculated with R:R ratio
```

### LONG Setup Pattern (Lines 702-836)
```
1. RSI crosses BELOW 40 (oversold condition starts)
   └─ window['RSI'].iloc[i-1] >= 40 AND window['RSI'].iloc[i] < 40

2. Track lowest price while RSI < 40
   └─ price_low = find lowest price in period where RSI < 40

3. WAIT for RSI to rise to >= 70 (within 100-hour window)
   └─ Look forward from oversold, find when RSI >= 70
   └─ CRITICAL: Can take MANY hours to complete pattern

4. Track highest price when RSI >= 70
   └─ price_high = find highest price when RSI >= 70

5. Calculate Fibonacci levels
   └─ fib_range = price_high - price_low
   └─ entry = price_high - fib_range * 0.74
   └─ stop_loss = price_low - fib_range * 0.27

6. Place LONG (buy limit) order at entry price
   └─ Wait for execution at entry level
   └─ Stop loss below low
   └─ Take profit calculated with R:R ratio
```

---

## PR-014 CURRENT LOGIC (INCORRECT)

### What PR-014 Does Now
```python
# engine.py _detect_buy_signal() - WRONG APPROACH
if indicators["rsi"] < 30:  # ← Only checks CURRENT bar RSI
    if indicators["roc"] > 0:  # ← Only checks CURRENT bar ROC
        # Calculate entry/SL/TP immediately
        return signal
```

### What's Missing
1. ❌ NO tracking of RSI crosses (RSI threshold boundary events)
2. ❌ NO wait-for-pattern logic (doesn't wait for RSI to complete journey)
3. ❌ NO state machine (SHORT: 70→40, LONG: 40→70)
4. ❌ NO 100-hour window validation
5. ❌ NO tracking of price extremes during RSI period
6. ❌ NO distinction between "RSI > 70 now" vs "RSI just crossed 70"

---

## KEY DIFFERENCES BREAKDOWN

| Aspect | DemoNoStochRSI | PR-014 | Status |
|--------|----------------|--------|--------|
| Signal Detection | RSI CROSSES thresholds | RSI VALUE at current bar | ❌ WRONG |
| Time Window | 100 hours max | Instant | ❌ WRONG |
| Pattern Completion | Waits for pattern end | Fires immediately | ❌ WRONG |
| Price Tracking | Finds extremes during RSI period | Uses current price | ❌ WRONG |
| State Machine | 4 states (RSI 70→40 or 40→70) | Single check per bar | ❌ WRONG |
| Entry Signal | "RSI DONE crossing" | "RSI crosses" | ❌ WRONG |
| Multiple Setups | Can have overlapping patterns | Single signal per bar | ❌ WRONG |

---

## REQUIRED REWRITE

PR-014 needs complete rewrite of signal detection to implement:

1. **RSI Crossing State Machine**
   - SHORT State: Track when RSI > 70 → waiting for RSI <= 40
   - LONG State: Track when RSI < 40 → waiting for RSI >= 70
   - Idle State: No pattern in progress

2. **100-Hour Window Validation**
   - For SHORT: Look forward up to 100 hours for RSI <= 40
   - For LONG: Look forward up to 100 hours for RSI >= 70
   - Fail validation if window exceeded

3. **Price Extremes Tracking**
   - SHORT: Find price_high during "RSI > 70" period, price_low during "RSI <= 40" period
   - LONG: Find price_low during "RSI < 40" period, price_high during "RSI >= 70" period

4. **Setup Deduplication**
   - DemoNoStochRSI prevents multiple setups of same type
   - Latest setup time: only execute if newer than active setup

5. **Exact Fibonacci Calculation**
   - SHORT: entry = price_low + (price_high - price_low) × 0.74
   - SHORT: stop_loss = price_high + (price_high - price_low) × 0.27
   - LONG: entry = price_high - (price_high - price_low) × 0.74
   - LONG: stop_loss = price_low - (price_high - price_low) × 0.27

---

## IMPACT ASSESSMENT

### Current State
- 66 tests passing ✅
- 80% coverage ✅
- **BUT**: Tests the WRONG strategy ❌

### Required Changes
- **New files**: 3-4 new modules (state machine, pattern detector, etc.)
- **Modified files**: engine.py, schema.py, indicators.py
- **New tests**: 40+ new test cases
- **Estimated effort**: 6-8 hours
- **Result**: Correct strategy matching DemoNoStochRSI exactly

---

## NEXT STEPS

**USER DECISION REQUIRED**:

Option A: **APPROVE REWRITE** ✅
- Rewrite PR-014 to match DemoNoStochRSI exactly
- Implement state machine for RSI crossing patterns
- Add comprehensive tests (60+ tests)
- Result: Correct trading strategy

Option B: **INVESTIGATE FURTHER** ⏸️
- Review DemoNoStochRSI strategy more carefully
- Confirm this is the desired strategy
- Check if there are later PRs that implement different strategy

**Recommendation**: **APPROVE REWRITE** - DemoNoStochRSI is clearly the production strategy and must be implemented exactly.

---

## DEMONOSTOCHRSI REFERENCE CODE

**File**: `c:\Users\FCumm\NewTeleBotFinal\base_files\DemoNoStochRSI.py`
**Function**: `detect_setups()` (Lines 520-836)
**Key Variables**:
- `rsi_window_hours = 100` (completion window)
- Short: RSI > 70 → waits for RSI <= 40
- Long: RSI < 40 → waits for RSI >= 70
- Fibonacci: 0.74 entry, 0.27 stop loss

---

## IMMEDIATE ACTION

Await user decision: Type one of:
- `"continue with rewrite"` → Start PR-014 rewrite
- `"verify strategy first"` → Review more carefully
- `"confirm DemoNoStochRSI is correct"` → Confirm before rewrite
