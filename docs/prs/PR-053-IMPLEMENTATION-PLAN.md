# PR-053: Performance Metrics Engine - Implementation Plan

## Overview

PR-053 implements a comprehensive performance metrics calculation engine for the analytics module. This PR introduces five professional-grade KPIs used to evaluate trading strategy performance:

1. **Sharpe Ratio** - Risk-adjusted return metric (excess return / volatility)
2. **Sortino Ratio** - Downside risk-adjusted metric (penalizes only negative returns)
3. **Calmar Ratio** - Return per unit of drawdown (annual return / max drawdown)
4. **Profit Factor** - Gross wins vs gross losses ratio
5. **Recovery Factor** - Total return divided by maximum drawdown

These metrics are essential for traders to understand strategy quality, risk management, and return efficiency.

---

## Dependencies

**MUST BE COMPLETED FIRST**:
- ✅ PR-051: Analytics warehouse ETL (EquityCurve and TradesFact models)
- ✅ PR-052: Equity & Drawdown Engine (max drawdown calculations)

---

## Architecture

### Module Structure

```
backend/app/analytics/
├── metrics.py                 # Core metrics calculations
├── routes.py                  # FastAPI endpoints
├── models.py                  # SQLAlchemy models (EquityCurve, TradesFact)
└── __init__.py
```

### Key Classes

**PerformanceMetrics Service**:
- Initializes with AsyncSession and optional custom risk-free rate
- All calculations use Python `Decimal` for precision
- Returns values rounded to 4 decimal places for Sharpe/Sortino, 2 for Profit/Recovery Factors

### API Endpoints

```
GET /api/v1/analytics/metrics
    Query Parameters:
        - window: int (30, 90, 365 days) - default: 90
    Response: MetricsResponse with all 5 metrics + supplementary data
    
GET /api/v1/analytics/metrics/all-windows
    Response: Dict[int, Dict[str, Decimal]] - metrics for all standard windows
```

---

## Implementation Details

### 1. Sharpe Ratio
**Formula**: (mean_return - risk_free_rate) / std_dev

- **Input**: Daily returns list (as Decimal)
- **Configuration**: Risk-free rate = 2% annual (adjusts to daily: 2% / 252)
- **Edge Cases**:
  - Empty list → returns 0
  - Single value → returns 0 (insufficient data)
  - Zero volatility → returns 0 (division by zero protection)
  - All positive returns → valid positive Sharpe

**Testing**:
- Happy path with mixed returns ✓
- Zero returns edge case ✓
- Negative returns handling ✓
- High volatility scenario ✓
- Constant returns (zero std dev) ✓

### 2. Sortino Ratio
**Formula**: (mean_return - risk_free_rate) / downside_std_dev

- **Input**: Daily returns list (as Decimal)
- **Special Handling**: Only negative returns contribute to downside volatility
- **Edge Cases**:
  - Empty list → returns 0
  - All positive returns → returns 999 (perfect, no downside)
  - Zero downside variance → returns 0

**Testing**:
- Happy path with mixed returns ✓
- All positive returns (perfect case) ✓
- Zero downside volatility ✓
- Downside variance calculation ✓

### 3. Calmar Ratio
**Formula**: (annual_return) / max_drawdown

- **Input**: total_return (%), max_drawdown (%), days_in_period
- **Annualization**: Scales return as `return * 365 / days`
- **Edge Cases**:
  - Zero drawdown → returns 0 (no risk measurement)
  - Negative drawdown → returns 0
  - One-year window → no annualization adjustment

**Testing**:
- One-year window (365 days) ✓
- Short window (30 days) with annualization ✓
- Zero drawdown case ✓

### 4. Profit Factor
**Formula**: sum(winning_pnls) / abs(sum(losing_pnls))

- **Input**: List of (pnl, is_winning) tuples
- **Range**: >1 = profitable, <1 = losing, infinity edge cases handled
- **Edge Cases**:
  - Empty trades → returns 0
  - Only losses → returns 0
  - Zero losses (break-even) → returns 999

**Testing**:
- Standard calculation with wins/losses ✓
- No losses case (returns 999) ✓
- Only losses case (returns 0) ✓
- Rounding to 2 decimals ✓

### 5. Recovery Factor
**Formula**: total_return / max_drawdown

- **Input**: total_return (%), max_drawdown (%)
- **Output**: How many times the drawdown is recovered by return
- **Edge Cases**:
  - Zero drawdown → returns 0
  - Negative drawdown → returns 0
  - Poor recovery (return < drawdown) → decimal < 1
  - Excellent recovery (return >> drawdown) → high decimal

**Testing**:
- Zero drawdown case ✓
- Poor recovery scenario ✓
- Excellent recovery scenario ✓

---

## Data Flow

### Async Method: `get_metrics_for_window(user_id, window_days)`

1. Calculate date range: `today - window_days` to `today`
2. Fetch EquityCurve snapshots for user in date range
3. Calculate daily returns from consecutive snapshots
4. Calculate max drawdown from equity snapshots
5. Fetch TradesFact for date range to build profit factor
6. Call all 5 metric methods
7. Return dictionary with all metrics + supplementary data (total return, win rate, num trades)

### Async Method: `get_all_window_metrics(user_id)`

- Iterates over [30, 90, 365] days
- Calls `get_metrics_for_window` for each
- Handles errors gracefully (returns empty dict if insufficient data)
- Returns `Dict[int, Dict[str, Decimal]]`

---

## Configuration

**Risk-Free Rate**:
```python
DEFAULT_RISK_FREE_RATE = Decimal("0.02")  # 2% annual
RISK_FREE_DAILY = DEFAULT_RISK_FREE_RATE / Decimal(252)  # 252 trading days/year
```

**Customizable**:
```python
metrics = PerformanceMetrics(db_session, risk_free_rate=Decimal("0.03"))
```

---

## Testing Strategy

### Unit Tests (32 tests)
- Each metric calculation method tested in isolation
- Edge cases: empty data, single values, zero variance/drawdown
- Configuration testing: custom risk-free rates
- Precision testing: Decimal rounding and precision maintenance

### Integration Tests
- End-to-end workflow from trades → equity → metrics
- Database operations: EquityCurve and TradesFact queries
- Error handling: insufficient data, missing snapshots

### Edge Cases Covered
1. **Sharpe Ratio**: Empty, single, constant, negative, high-volatility returns
2. **Sortino Ratio**: Empty, single, all-positive, mixed returns
3. **Calmar Ratio**: Zero drawdown, negative drawdown, short/long windows
4. **Profit Factor**: Empty trades, only losses, break-even, exact calculation
5. **Recovery Factor**: Zero drawdown, negative drawdown, poor/excellent recovery

---

## Files Modified/Created

### New Files
- `backend/app/analytics/metrics.py` (517 lines)
  - PerformanceMetrics class with 5 metric methods
  - get_daily_returns() async helper
  - get_metrics_for_window() async method
  - get_all_window_metrics() async method
  - Module-level wrapper functions for backward compatibility

### Modified Files
- `backend/app/analytics/routes.py`
  - Added `GET /analytics/metrics` endpoint (line 233)
  - Added `GET /analytics/metrics/all-windows` endpoint (line 287)
  - Integration with PerformanceMetrics service

- `backend/tests/test_pr_051_052_053_analytics.py`
  - TestPerformanceMetrics class (6 original tests → 32 total)
  - 26 new tests covering all edge cases
  - 100% of accept criteria covered

---

## Success Criteria

✅ All 5 metrics implemented with correct formulas
✅ All 32 tests passing (100% pass rate)
✅ Coverage ≥90% for metrics.py
✅ Async database operations properly implemented
✅ Error handling for insufficient data
✅ API endpoints functional with window parameter support
✅ Configuration customizable (risk-free rate)
✅ All acceptance criteria met and documented

---

## Time Estimate

- Implementation: 1-2 hours
- Testing: 1-2 hours
- Documentation: 30 minutes
- **Total**: 2.5-4.5 hours

---

## Notes

- All metrics use `Decimal` for financial precision (not floats)
- Risk-free rate configured for 252 trading days/year (standard)
- Prometheus monitoring available if prometheus_client installed
- Window size validated (1-365 days)
- Metrics gracefully handle edge cases without exceptions
- Sortino ratio returns 999 for perfect strategies (no downside)
- Profit factor returns 999 when no losses (profitable)

