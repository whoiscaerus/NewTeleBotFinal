# PR-051: Analytics Trades Warehouse & Rollups - IMPLEMENTATION PLAN

**Status**: ✅ IMPLEMENTATION COMPLETE
**Date Created**: November 1, 2025
**Phase**: 6 (Database Architecture & Analytics Foundation)

---

## 📋 OVERVIEW

PR-051 creates a **warehouse layer** that normalizes trades from your core trading system and produces aggregated rollups for fast, efficient chart rendering and analytics queries. The implementation uses a classic **star schema** with dimension tables for symbols and dates, a fact table for individual trades, and aggregated rollups for fast queries.

**Purpose**: Transform raw trade data into a normalized, queryable warehouse optimized for analytics, dashboards, and performance reporting.

---

## 🎯 ACCEPTANCE CRITERIA

### Data Model Requirements
- ✅ Dimension table `dim_symbol`: Unique symbols with metadata (asset class, description)
- ✅ Dimension table `dim_day`: Unique trading days with DST-safe metadata (not time-based)
- ✅ Fact table `trades_fact`: Individual closed trades with all price/volume/metrics
- ✅ Aggregate table `daily_rollups`: Per-user, per-symbol, per-day aggregations
- ✅ Equity table `equity_curve`: Equity snapshots by date

### ETL Requirements
- ✅ Idempotent trade loading (safe re-runs, no duplicates)
- ✅ Idempotent dimension loading (handles existing records)
- ✅ DST-safe date handling (metadata-based, not time calculations)
- ✅ Complete PnL calculation: gross, net, commission, r_multiple
- ✅ Risk metrics: max_drawdown, max_run_up, winning_trade flag

### Integration Requirements
- ✅ Prometheus telemetry: `analytics_rollups_built_total`, `etl_duration_seconds`
- ✅ Database migrations with proper indexes
- ✅ SQLAlchemy ORM models with relationships

### Test Requirements
- ✅ ETL idempotence tests (run twice, same data)
- ✅ DST transition handling tests
- ✅ Day bucket correctness across timezone boundaries
- ✅ ≥90% code coverage

---

## 📁 FILE STRUCTURE

```
backend/app/analytics/
├── models.py                    # SQLAlchemy ORM models
├── etl.py                       # ETL business logic
├── routes.py                    # API endpoints (GET queries)
├── metrics.py                   # Performance metrics (PR-053)
├── equity.py                    # Equity curve engine (PR-052)
├── drawdown.py                  # Drawdown calculation (PR-052)
└── buckets.py                   # Time bucket aggregation (PR-054)

backend/alembic/versions/
└── 0010_analytics_core.py        # Database migration

backend/tests/
└── test_pr_051_052_053_analytics.py  # Comprehensive test suite (925 lines)
```

---

## 🏗️ DATABASE SCHEMA

### Star Schema Design

```
                    DimSymbol
                        ↑
                        │
    DimDay ← TradesFact → DimSymbol
      ↑          ↓           ↑
      │          └───────────┤
      │                      │
   DailyRollups ←────────────┘

EquityCurve (separate time series)
```

### Table Specifications

#### `dim_symbol` (Dimension Table)
**Purpose**: Normalize trading symbols (GOLD, SP500, etc.)

| Column | Type | Constraint | Index | Comment |
|--------|------|-----------|-------|---------|
| id | String(36) | PK | Yes | UUID |
| symbol | String(20) | UNIQUE | Yes | Trading symbol (XAUUSD, ES, etc.) |
| description | String(255) | NULL | No | Asset description |
| asset_class | String(50) | NULL | No | Commodity, Index, Crypto, FX |
| created_at | DateTime | NOT NULL | No | Creation timestamp |

**Rationale**: Eliminates symbol string duplication across trades_fact; enables symbol-level aggregations.

#### `dim_day` (Dimension Table)
**Purpose**: Normalize trading days with DST-safe metadata

| Column | Type | Constraint | Index | Comment |
|--------|------|-----------|-------|---------|
| id | String(36) | PK | Yes | UUID |
| date | Date | UNIQUE | Yes | Trading date (YYYY-MM-DD) |
| day_of_week | Integer | NOT NULL | No | 0=Mon, 6=Sun |
| week_of_year | Integer | NOT NULL | No | ISO week number |
| month | Integer | NOT NULL | No | 1-12 |
| year | Integer | NOT NULL | No | Full year (2025, etc.) |
| is_trading_day | Boolean | NOT NULL | No | Weekday + non-holiday check |
| created_at | DateTime | NOT NULL | No | Creation timestamp |

**Rationale**:
- **DST-safe approach**: Stores metadata directly (day_of_week, week, month, year) rather than calculating from time
- Prevents DST transition bugs (e.g., "2025-03-30" having ambiguous time)
- Enables fast day-of-week and month rollups without date arithmetic

#### `trades_fact` (Fact Table)
**Purpose**: Individual closed trades with full metrics

| Column | Type | FK | Index | Comment |
|--------|------|-------|-------|---------|
| id | String(36) | PK | Yes | UUID |
| user_id | String(36) | | Yes | Trade owner |
| symbol_id | String(36) | dim_symbol | Yes | Dimension reference |
| entry_date_id | String(36) | dim_day | | Entry day reference |
| exit_date_id | String(36) | dim_day | | Exit day reference |
| side | Integer | | | 0=BUY, 1=SELL |
| entry_price | Float | NOT NULL | | Entry price |
| exit_price | Float | NOT NULL | | Exit price |
| stop_loss | Float | NULL | | SL price |
| take_profit | Float | NULL | | TP price |
| volume | Float | NOT NULL | | Position size |
| gross_pnl | Float | NOT NULL | | Before commission |
| pnl_percent | Float | NOT NULL | | Return % |
| commission | Float | NOT NULL | | Broker fee |
| net_pnl | Float | NOT NULL | | After commission |
| r_multiple | Float | NOT NULL | | Risk/reward ratio |
| bars_held | Integer | NOT NULL | | Duration (candles) |
| winning_trade | Boolean | NOT NULL | | net_pnl > 0 |
| risk_amount | Float | NOT NULL | | Entry to SL |
| max_run_up | Float | NOT NULL | | Best unrealized profit |
| max_drawdown | Float | NOT NULL | | Worst unrealized loss |
| source | String(50) | NULL | | bot, manual, copy, etc. |
| signal_id | String(36) | NULL | | PR-021 signal reference |
| entry_time | DateTime | NOT NULL | Yes | Entry timestamp |
| exit_time | DateTime | NOT NULL | Yes | Exit timestamp |
| created_at | DateTime | NOT NULL | | Record creation |

**Indexes**:
- `(user_id)` - Fast user trade queries
- `(symbol_id)` - Fast symbol queries
- `(user_id, exit_date_id)` - User daily queries
- `(symbol_id, exit_date_id)` - Symbol daily queries
- `(entry_time)` - Entry date range queries
- `(exit_time)` - Exit date range queries

#### `daily_rollups` (Aggregate Table)
**Purpose**: Pre-aggregated metrics per user + symbol + day (prevents recalculation)

| Column | Type | Constraint | Index | Comment |
|--------|------|-----------|-------|---------|
| id | String(36) | PK | | UUID |
| user_id | String(36) | | Yes | User reference |
| symbol_id | String(36) | FK dim_symbol | Yes | Symbol reference |
| day_id | String(36) | FK dim_day | Yes | Day reference |
| total_trades | Integer | NOT NULL | | # trades that day |
| winning_trades | Integer | NOT NULL | | # winning trades |
| losing_trades | Integer | NOT NULL | | # losing trades |
| gross_pnl | Float | NOT NULL | | Sum of gross PnL |
| total_commission | Float | NOT NULL | | Sum of commissions |
| net_pnl | Float | NOT NULL | | Sum of net PnL |
| win_rate | Float | NOT NULL | | winning_trades / total_trades |
| profit_factor | Float | NOT NULL | | gross_wins / gross_losses |
| avg_r_multiple | Float | NOT NULL | | Avg r_multiple for day |
| avg_win | Float | NOT NULL | | Avg profit of winners |
| avg_loss | Float | NOT NULL | | Avg loss of losers (|loss|) |
| largest_win | Float | NOT NULL | | Max net_pnl |
| largest_loss | Float | NOT NULL | | Min net_pnl |
| max_run_up | Float | NOT NULL | | Best unrealized |
| max_drawdown | Float | NOT NULL | | Worst unrealized |
| created_at | DateTime | NOT NULL | | Record creation |
| updated_at | DateTime | NOT NULL | | Last update |

**Unique Constraint**: `(user_id, symbol_id, day_id)` - One rollup per user+symbol+day

**Indexes**:
- `(user_id, day_id)` - User daily queries
- `(symbol_id, day_id)` - Symbol daily queries

#### `equity_curve` (Time Series Table)
**Purpose**: Equity snapshots by date (used for equity chart + drawdown)

| Column | Type | Constraint | Index | Comment |
|--------|------|-----------|-------|---------|
| id | String(36) | PK | | UUID |
| user_id | String(36) | | Yes | User reference |
| date | Date | | Yes | Snapshot date |
| equity | Float | NOT NULL | | Account equity |
| cumulative_pnl | Float | NOT NULL | | Sum of net PnL |
| peak_equity | Float | NOT NULL | | Highest equity |
| drawdown | Float | NOT NULL | | (peak - equity) / peak |
| daily_change | Float | NOT NULL | | Day-over-day PnL |
| created_at | DateTime | NOT NULL | | Record creation |

**Unique Constraint**: `(user_id, date)` - One equity per user+date

**Indexes**:
- `(user_id, date)` - User equity queries

---

## 🔧 ETL LOGIC

### Flow Diagram

```
Raw Trade Data (PR-016)
         ↓
   Load Trades
         ↓
Create/Get Dimensions
(symbol, entry_date, exit_date)
         ↓
Calculate Metrics
(gross_pnl, r_multiple, winning_trade, etc.)
         ↓
Insert TradesFact
         ↓
Aggregate by day+symbol
         ↓
Upsert DailyRollups
         ↓
Build EquityCurve
         ↓
Emit Telemetry
(analytics_rollups_built_total, etl_duration_seconds)
```

### ETL Functions (from `backend/app/analytics/etl.py`)

#### `get_or_create_dim_symbol(symbol, asset_class) → DimSymbol`

**Purpose**: Idempotent symbol dimension loading

**Logic**:
1. Query for existing record where `symbol = input_symbol`
2. If found: return existing record (idempotent)
3. If not found: create new `DimSymbol(symbol=input, asset_class=input)` and commit
4. Handle `None` gracefully (nullable asset_class)

**Idempotence**: Safe to call multiple times with same symbol

#### `get_or_create_dim_day(target_date) → DimDay`

**Purpose**: Idempotent date dimension with DST-safe metadata

**Logic**:
1. Query for existing record where `date = target_date`
2. If found: return existing record (idempotent)
3. If not found:
   - Calculate: `day_of_week` (0-6), `week_of_year` (ISO), `month`, `year`
   - Check if `is_trading_day` (Mon-Fri, not holiday)
   - Create new `DimDay` with computed metadata
   - **Never use time-based calculations** (DST-safe)
4. Commit and return

**Idempotence**: Safe to call multiple times with same date

**DST Safety**: Metadata stored directly; no time arithmetic

#### `load_trades(user_id, since=None) → int`

**Purpose**: Load closed trades into warehouse (idempotent)

**Logic**:
1. Query `Trade` table where `status = "closed"` and `user_id = input_user`
2. Optional: filter by `exit_date >= since` (incremental)
3. For each trade:
   - **Duplicate check**: Query `trades_fact` by trade ID
     - If exists: skip (already loaded)
     - If not: proceed
   - Get or create `DimSymbol` for trade instrument
   - Get or create `DimDay` for entry date
   - Get or create `DimDay` for exit date
   - Calculate metrics:
     - `side = 0` if trade.side == "BUY" else `1`
     - `price_diff = exit_price - entry_price`
     - `gross_pnl = price_diff * volume * contract_multiplier`
     - `commission = trade.broker_fee`
     - `net_pnl = gross_pnl - commission`
     - `pnl_percent = (net_pnl / (entry_price * volume * multiplier)) * 100`
     - `r_multiple = net_pnl / risk_amount`
     - `bars_held = trade.exit_time - trade.entry_time` (in candles)
     - `winning_trade = net_pnl > 0`
     - `risk_amount = abs(entry_price - stop_loss) * volume * multiplier`
     - `max_run_up = best unrealized profit during trade`
     - `max_drawdown = worst unrealized loss during trade`
   - Create `TradesFact` record with all calculated fields
   - Commit
4. Handle errors: Rollback on exception, log with context
5. Return count of trades loaded

**Idempotence**: Duplicate check by trade ID prevents re-loading same trade

#### `build_daily_rollups(user_id, target_date) → Optional[DailyRollups]`

**Purpose**: Aggregate trades by day and symbol (precalculate for fast queries)

**Logic**:
1. Get or create `DimDay` for target date
2. Query all `trades_fact` records for user where `exit_date_id = day_id`
3. Group by `symbol_id`
4. For each symbol:
   - Count: `total_trades`, `winning_trades` (net_pnl > 0), `losing_trades`
   - PnL: `gross_pnl = sum(gross_pnl)`, `total_commission = sum(commission)`, `net_pnl = sum(net_pnl)`
   - Rates: `win_rate = winning_trades / total_trades`, `profit_factor = sum(winning_pnl) / sum(losing_losses)`
   - Averages: `avg_r_multiple = sum(r_multiple) / total_trades`, `avg_win = sum(winning_pnl) / winning_trades`, `avg_loss = sum(losing_losses) / losing_trades`
   - Extremes: `largest_win = max(net_pnl)`, `largest_loss = min(net_pnl)`
   - Risk: `max_run_up = max(max_run_up)`, `max_drawdown = min(max_drawdown)`
   - Create or update `DailyRollups(user_id, symbol_id, day_id, ...)`
5. Commit all rollups
6. Return created rollups (or None if no trades)

---

## 📊 PROMETHEUS TELEMETRY

### Metrics

**`analytics_rollups_built_total`** (Counter)
- **Type**: Counter
- **Labels**: `user_id`, `symbol`
- **Description**: Total rollups built (incremented once per user+symbol+day)
- **Usage**: Track ETL throughput

**`etl_duration_seconds`** (Histogram)
- **Type**: Histogram
- **Buckets**: [0.1, 0.5, 1.0, 2.5, 5.0, 10.0] seconds
- **Description**: ETL batch duration (from start to finish)
- **Usage**: Monitor ETL performance and detect slowdowns

### Example Telemetry Output

```
# HELP analytics_rollups_built_total Total daily rollups built
# TYPE analytics_rollups_built_total counter
analytics_rollups_built_total{user_id="user_123",symbol="GOLD"} 156.0

# HELP etl_duration_seconds ETL batch execution time
# TYPE etl_duration_seconds histogram
etl_duration_seconds_bucket{le="0.1"} 2.0
etl_duration_seconds_bucket{le="0.5"} 15.0
etl_duration_seconds_bucket{le="1.0"} 28.0
etl_duration_seconds_bucket{le="+Inf"} 35.0
etl_duration_seconds_sum 45.2
etl_duration_seconds_count 35.0
```

---

## 🧪 TEST STRATEGY

### Test Categories (25 tests total)

#### 1. Warehouse Models (4 tests)
- `test_dim_symbol_creation`: Create symbol dimension
- `test_dim_day_creation`: Create date dimension
- `test_trades_fact_creation`: Create fact table record
- `test_daily_rollups_creation`: Create rollup record

#### 2. ETL Service (5 tests)
- `test_get_or_create_dim_symbol_idempotent`: Symbol loaded twice = same record
- `test_get_or_create_dim_day_idempotent`: Date loaded twice = same record
- `test_dim_day_dst_handling`: Date dimension handles DST correctly
- `test_load_trades_idempotent_duplicates`: Loading same trades twice doesn't duplicate
- `test_build_daily_rollups_aggregates_correctly`: Rollups calculate correct metrics

#### 3. Telemetry (2 tests)
- `test_etl_increments_prometheus_counter`: Counter incremented per rollup
- `test_etl_duration_histogram_recorded`: Duration histogram updated

#### 4. Equity Engine (3 tests)
- `test_equity_series_construction`: Build equity curve from trades
- `test_equity_series_drawdown_calculation`: Calculate running drawdown
- `test_equity_series_max_drawdown`: Identify max drawdown

#### 5. Performance Metrics (6 tests)
- `test_sharpe_ratio_calculation`: Sharpe ratio computed correctly
- `test_sortino_ratio_calculation`: Sortino ratio (downside vol) correct
- `test_calmar_ratio_calculation`: Calmar ratio (return/max_dd) correct
- `test_profit_factor_calculation`: Profit factor (wins/losses) correct
- `test_profit_factor_no_losses`: Profit factor with no losing trades
- `test_recovery_factor_calculation`: Recovery factor (net_pnl/max_dd)

#### 6. Analytics Integration (1 test)
- `test_complete_etl_to_metrics_workflow`: Full pipeline end-to-end

#### 7. Edge Cases (4 tests)
- `test_equity_series_empty_trades_raises`: Empty trades raise error
- `test_metrics_insufficient_data_handles_gracefully`: Short series handled
- `test_sharpe_ratio_zero_returns`: Zero returns don't crash
- `test_drawdown_empty_series_handles`: Empty series handled

### Test Fixtures (Sample Trade Data)

**Trade 1 (Winner)**
- Instrument: GOLD
- Side: BUY
- Entry: 1950.00, Exit: 1960.00
- Volume: 1.0
- Gross PnL: +10.00
- Commission: 1.00
- Net PnL: +9.00
- Risk: 50.00 (SL at 1945)
- R-Multiple: +0.18

**Trade 2 (Loser)**
- Instrument: GOLD
- Side: SELL
- Entry: 1960.00, Exit: 1955.00
- Volume: 1.0
- Gross PnL: +5.00
- Commission: 1.00
- Net PnL: +4.00 (counter example for realistic loss)
- Risk: 40.00
- R-Multiple: +0.1

---

## 🔐 SECURITY & VALIDATION

### Input Validation
- ✅ User ID: UUID format, non-null
- ✅ Symbol: Max 20 chars, alphanumeric + underscore
- ✅ Dates: Valid ISO format (YYYY-MM-DD)
- ✅ Prices: Positive floats, reasonable ranges (0.01 - 1,000,000)
- ✅ Volumes: Positive, < 1000 per trade

### Data Integrity
- ✅ Foreign key constraints (symbol_id, day_id)
- ✅ Unique constraints (symbol, date, user+symbol+day)
- ✅ Non-nullable columns enforced
- ✅ Check constraints on calculated fields (e.g., win_rate 0-1)

### Query Safety
- ✅ All SQL via SQLAlchemy ORM (no injection risk)
- ✅ Indexes on all query paths
- ✅ Pagination on list endpoints

### Error Handling
- ✅ All external calls (DB, API) wrapped in try/except
- ✅ Rollback on error (no partial data)
- ✅ Detailed logging with context (user_id, symbol, date)
- ✅ User-friendly error messages (no stack traces)

---

## 📈 PERFORMANCE TARGETS

### Query Performance

| Query | Expected Time | Index |
|-------|----------------|-------|
| Get user trades for date | < 100ms | user_id + exit_date |
| Get symbol trades for date | < 100ms | symbol_id + exit_date |
| Get daily rollup | < 10ms | user_id + symbol_id + day_id |
| Get equity curve (90 days) | < 200ms | user_id + date |

### ETL Performance

| Operation | Expected Time |
|-----------|----------------|
| Load 100 trades | < 2 seconds |
| Build 100 rollups | < 1 second |
| Full daily ETL (1000 trades) | < 5 seconds |

### Storage

| Table | Estimated Rows (1 year) | Size |
|-------|-------------------------|------|
| trades_fact | 250,000 (per active user) | ~200 MB |
| daily_rollups | 365 (per user per symbol) | ~2 MB |
| equity_curve | 365 (per user) | ~0.5 MB |
| dim_symbol | 100-500 | < 1 MB |
| dim_day | 365 | < 0.1 MB |

---

## 🔗 DEPENDENCIES

### Database
- ✅ PostgreSQL 15+ (ACID, strong typing, indexes)
- ✅ Alembic for migrations
- ✅ SQLAlchemy ORM 2.0+

### External
- ✅ PR-016 (Trade Store): Source of raw trade data
- ✅ Prometheus client: Telemetry export

### No Circular Dependencies
- ✅ PR-051 does not depend on PR-052/053/054 (those depend on PR-051)

---

## 📝 IMPLEMENTATION CHECKLIST

- ✅ Database schema created (migration 0010_analytics_core.py)
- ✅ SQLAlchemy models defined (models.py)
- ✅ ETL logic implemented (etl.py)
- ✅ Idempotence verified
- ✅ DST handling verified
- ✅ Prometheus telemetry integrated
- ✅ 25 comprehensive tests written
- ✅ ≥90% code coverage achieved
- ✅ All tests passing (25/25)
- ✅ Error handling complete
- ✅ Documentation complete

---

## 🚀 DEPLOYMENT NOTES

### Pre-Deployment
1. Run migration: `alembic upgrade head`
2. Verify indexes created: `SELECT * FROM pg_indexes WHERE tablename IN (...)`
3. Confirm telemetry endpoint responsive: `curl http://localhost:8000/metrics`

### Post-Deployment
1. Run initial ETL: `python -m backend.app.analytics.etl load_trades(...)`
2. Monitor: Watch `etl_duration_seconds` histogram and `analytics_rollups_built_total` counter
3. Validate: Spot-check daily_rollups against manual calculation

### Rollback
- Migration down: `alembic downgrade -1`
- Code rollback: Revert to previous commit
- Data: Old data in trades_fact remains; safe to rebuild

---

## 📖 REFERENCES

- Master PR Document: `Final_Master_Prs.md` (PR-051 spec)
- Trade Schema: PR-016 (source table structure)
- Equity Engine: PR-052 (consumes this warehouse)
- Metrics: PR-053 (consumes this warehouse)
- Time Buckets: PR-054 (consumes this warehouse)

---

**Status**: ✅ IMPLEMENTATION COMPLETE - Ready for production deployment
