# PR-047 Implementation Plan: Public Performance Page

## Overview

PR-047 creates a public, SEO-friendly performance page that showcases trading performance with strong disclaimers and delayed data. The page displays live stats (delayed post-trade), equity curves, win rates, and risk-reward metrics without exposing sensitive information.

**Key Principle**: Delayed aggregated data only. No PII leak. Strong disclaimers.

## Scope

- Public Next.js route `/performance`
- Server endpoints to serve redacted, post-close metrics
- Strong disclaimers + "no forward guidance" copy
- Data rules: Only closed trades, T+X min delay (configurable)
- Security: Public endpoints return aggregates only; no PII

## Files to Create

### Backend
```
backend/app/public/performance_routes.py     # 350+ lines
backend/app/public/__init__.py               # Empty module marker
backend/tests/test_pr_047_public_performance.py  # 400+ lines, 90%+ coverage
```

### Frontend
```
frontend/web/app/performance/page.tsx        # Main page (250+ lines)
frontend/web/components/PerformanceHero.tsx  # Hero section (200+ lines)
frontend/web/components/EquityChartPublic.tsx # Chart component (300+ lines)
frontend/web/components/StatsTiles.tsx       # Stats display (200+ lines)
```

## Dependencies

- ✅ PR-051 (Analytics Warehouse) - provides analytics models
- ✅ PR-052 (Equity Engine) - provides equity calculations
- ✅ PR-053 (Performance Metrics) - provides KPI calculations
- ✅ PR-004 (User Management) - user authentication model
- ✅ PR-007 (Trading Domain) - Trade model with close logic

## API Endpoints

### 1. GET /api/v1/public/performance/summary
**Purpose**: Return aggregated performance metrics with T+X delay validation

**Query Parameters**:
- `delay_minutes` (int, optional, default=1440=24h): Minimum delay before publishing data
- `from_date` (date, optional): Start date for calculations
- `to_date` (date, optional): End date for calculations

**Response** (200 OK):
```json
{
  "total_trades": 143,
  "win_rate": 0.6573,
  "profit_factor": 2.15,
  "return_percent": 47.3,
  "sharpe_ratio": 1.82,
  "sortino_ratio": 2.34,
  "calmar_ratio": 1.25,
  "avg_rr": 1.8,
  "max_drawdown_percent": -12.5,
  "data_as_of": "2025-10-30T10:00:00Z",
  "delay_applied_minutes": 1440,
  "disclaimer": "Past performance is not indicative of future results..."
}
```

**Validation**:
- ❌ Returns error if delay < 1 minute (safety check)
- ✅ Only includes closed trades where `closed_at < now() - delay_minutes`
- ✅ Returns empty metrics (zeros) if no closed trades available

### 2. GET /api/v1/public/performance/equity
**Purpose**: Return equity curve data points for charting

**Query Parameters**:
- `delay_minutes` (int, optional, default=1440): Minimum delay
- `from_date` (date, optional): Start date
- `to_date` (date, optional): End date
- `granularity` (str, optional, default="daily"): "daily", "weekly", "monthly"

**Response** (200 OK):
```json
{
  "points": [
    {
      "date": "2025-10-01T00:00:00Z",
      "equity": 10000.00,
      "returns_percent": 0.0
    },
    {
      "date": "2025-10-02T00:00:00Z",
      "equity": 10234.50,
      "returns_percent": 2.34
    },
    ...
  ],
  "final_equity": 14730.00,
  "delay_applied_minutes": 1440,
  "data_as_of": "2025-10-30T10:00:00Z"
}
```

**Validation**:
- ✅ Equity points sorted by date (ascending)
- ✅ All trades included are closed
- ✅ Returns empty array if no closed trades within delay window

## Business Logic

### Delay Mechanism
```python
# Pseudo-code
safe_cutoff = now() - timedelta(minutes=delay_minutes)
closed_trades = Trade.filter(
    closed_at < safe_cutoff,
    status="closed"
)
```

### PII Protection
- ❌ Never return user IDs, names, emails, API keys
- ❌ Never return individual trade details (entry/exit prices, symbols)
- ✅ Return only aggregated metrics (win_rate, sharpe_ratio, equity curve)
- ✅ Return equity curve dates (day-level granularity only)

### Prometheus Telemetry
```
public_performance_views_total{endpoint,delay_minutes}
public_performance_error_total{endpoint,error_type}
public_performance_trades_count{status}
```

## Frontend Components

### page.tsx (Main Page)
- SEO meta tags (title, description, og:image)
- Hero section with headline + CTA
- PerformanceHero component
- EquityChartPublic component
- StatsTiles component
- Strong disclaimers at bottom
- Mobile-responsive layout

### PerformanceHero.tsx
- Headline: "Proven Trading Excellence"
- Subheading with key metric (e.g., "143 Closed Trades, 65.7% Win Rate")
- CTA button linking to signup/demo
- Professional background gradient

### EquityChartPublic.tsx
- Recharts library for equity curve
- Interactive tooltips showing date + equity value
- No individual trade markers
- Responsive sizing
- Loading state while fetching
- Error state with message

### StatsTiles.tsx
- 6 stat tiles: Win Rate, Profit Factor, Sharpe Ratio, Sortino, Return %, Max Drawdown
- Color-coded: Green for positive, Red for negative
- Icon + value + label format
- Loading skeleton states
- Disclaimer text below stats

## Test Scenarios

### Test 1: Delay Enforcement
- **Setup**: Create 3 closed trades (now-2d, now-1d, now-1h)
- **Action**: Call `/public/performance/summary` with `delay_minutes=1440` (24h)
- **Assert**: Only 2 oldest trades included; most recent trade excluded

### Test 2: Closed Trades Only
- **Setup**: Create 2 closed trades + 1 open trade
- **Action**: Call `/public/performance/summary`
- **Assert**: Response includes only 2 closed trades

### Test 3: No PII Leak
- **Setup**: Create closed trade
- **Action**: Call `/public/performance/equity`
- **Assert**: Response contains no user_id, names, entry prices, SL/TP values

### Test 4: Empty Data Handling
- **Setup**: No closed trades in database
- **Action**: Call `/public/performance/summary`
- **Assert**: Returns 200 OK with all metrics = 0, total_trades = 0

### Test 5: Prometheus Telemetry
- **Setup**: Mock Prometheus client
- **Action**: Call endpoints 3 times
- **Assert**: `public_performance_views_total` incremented 3 times

### Test 6: Invalid Delay Parameter
- **Setup**: None
- **Action**: Call with `delay_minutes=-10`
- **Assert**: Returns 400 Bad Request with validation error

## Phase Breakdown

### Phase 1: Backend (1 hour)
- Create `/backend/app/public/` directory
- Implement performance_routes.py (2 endpoints)
- Add Prometheus telemetry
- Validate all business logic

### Phase 2: Frontend (1.5 hours)
- Create `/frontend/web/app/performance/` directory
- Create page.tsx main route
- Create 3 components (Hero, Chart, Stats)
- Integrate with backend endpoints
- Add responsive styling

### Phase 3: Tests (1 hour)
- Create test_pr_047_public_performance.py
- Write 20+ test cases
- Achieve 90%+ coverage
- Validate all acceptance criteria

### Phase 4: Documentation (0.5 hours)
- Create ACCEPTANCE-CRITERIA.md
- Create IMPLEMENTATION-COMPLETE.md
- Create BUSINESS-IMPACT.md

### Phase 5: Verification (0.5 hours)
- Run full test suite
- Verify coverage
- GitHub Actions green
- Production ready

## Success Criteria

✅ All 5 deliverables created in exact paths
✅ Both endpoints working with proper validation
✅ T+X delay correctly enforced
✅ No PII leak in responses
✅ Frontend components responsive and interactive
✅ 90%+ test coverage
✅ All tests passing locally
✅ GitHub Actions green
✅ Prometheus telemetry working
✅ All 4 documentation files complete
✅ Production-ready code quality

---

**Created**: 2025-11-01
**Status**: Planning Phase
**Estimated Duration**: 4.5 hours total
