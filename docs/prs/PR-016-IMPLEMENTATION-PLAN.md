# PR-016: Local Trade Store Migration (SQLite → Postgres) — IMPLEMENTATION PLAN

**Status**: Phase 1 - PLANNING (ACTIVE)
**Date**: October 24, 2025
**Estimated Duration**: 10-12 hours total (4 phases)
**Target Coverage**: ≥90% (20+ tests)
**Dependencies**: ✅ PR-010 (DB baseline), ✅ PR-015 (Orders)

---

## 📋 PR-016 SPECIFICATION SUMMARY

### Goal
Normalize local SQLite trade records (`trades`, `equity`, `validation_logs`) into Postgres with proper schema, migrations, and query service.

### Business Value
- ✅ Centralize trade history in production database
- ✅ Enable trade analytics (P&L, win rate, recovery time)
- ✅ Support reconciliation with MT5 (detect manual trades)
- ✅ Foundation for Phase 1B reporting APIs

### Deliverables (Create/Update)

```
backend/app/trading/store/
  __init__.py                    # Package exports
  models.py                      # Trade, Position, EquityPoint, ValidationLog (SQLAlchemy)
  service.py                     # TradeService with query/filter logic
  schemas.py                     # Pydantic models for API responses
  queries.py                     # Specialized query builders (optional)
  reconciliation.py              # Detect manual MT5 trades

backend/alembic/versions/
  XXXX_create_trading_store.py   # Migration: create all tables + indexes

backend/tests/
  test_trade_store_models.py     # Model validation, constraints
  test_trade_store_service.py    # CRUD operations, filtering
  test_trade_store_queries.py    # Complex queries (P&L, filters)
  test_trading_store_migration.py # Migration up/down testing

docs/prs/
  PR-016-IMPLEMENTATION-PLAN.md    (This file)
  PR-016-IMPLEMENTATION-COMPLETE.md (After completion)
  PR-016-ACCEPTANCE-CRITERIA.md    (Test verification)
  PR-016-BUSINESS-IMPACT.md        (Financial analysis)

scripts/verify/
  verify-pr-016.sh               # Automated verification script
```

---

## 🗄️ DATABASE SCHEMA DESIGN

### Table: `trades` (Core trading records)

```python
class Trade(Base):
    """Represents a completed trade in the system."""
    __tablename__ = "trades"

    # Primary Key & Foreign Keys
    trade_id: str                  # UUID primary key
    signal_id: str                 # Foreign key → signals table
    device_id: str | None          # Foreign key → devices table (if executed by device)

    # Trade Metadata
    symbol: str                    # "GOLD", "EURUSD", etc.
    strategy: str                  # "fib_rsi", "channel", etc.
    timeframe: str                 # "H1", "H15", "M15", etc.
    setup_id: str | None           # Original setup identifier

    # Trade Direction & Type
    trade_type: str                # "BUY" or "SELL"
    direction: int                 # 0=BUY, 1=SELL (legacy compatibility)

    # Entry Details
    entry_price: float             # Entry level (decimal 10,2)
    entry_time: datetime           # Entry timestamp (UTC)
    entry_comment: str | None      # Reason for entry

    # Exit Details
    exit_price: float | None       # Exit level (NULL if open)
    exit_time: datetime | None     # Exit timestamp (NULL if open)
    exit_reason: str | None        # "TP_HIT", "SL_HIT", "MANUAL_CLOSE", etc.

    # Risk Management
    stop_loss: float               # Stop loss level (decimal 10,2)
    take_profit: float             # Take profit level (decimal 10,2)
    volume: float                  # Position size in lots (decimal 10,2)

    # Performance Metrics
    profit: float | None           # P&L in account currency
    pips: float | None             # Profit in pips
    risk_reward_ratio: float | None # Actual R:R achieved
    percent_equity_return: float | None # % of equity risked

    # Trade State
    status: str                    # "OPEN", "CLOSED", "CANCELLED"
    duration_hours: float | None   # How long trade was open

    # Timestamps
    created_at: datetime           # When record created (UTC)
    updated_at: datetime           # When last modified (UTC)

    # Indexes for common queries
    __table_args__ = (
        Index("ix_trades_symbol_time", "symbol", "entry_time"),
        Index("ix_trades_status_created", "status", "created_at"),
        Index("ix_trades_strategy_symbol", "strategy", "symbol"),
        Index("ix_trades_signal_id", "signal_id"),
    )
```

**Validation Rules**:
- entry_price, stop_loss, take_profit: Must be positive
- For BUY: stop_loss < entry_price < take_profit
- For SELL: take_profit < entry_price < stop_loss
- volume: Must be positive (0.01 - 100.0)
- duration_hours: Calculated as (exit_time - entry_time).total_seconds() / 3600
- profit: Calculated as (exit_price - entry_price) × volume (for BUY)
- status: Only transitions OPEN → CLOSED or CANCELLED

---

### Table: `positions` (Open positions)

```python
class Position(Base):
    """Represents a currently open position."""
    __tablename__ = "positions"

    position_id: str               # UUID primary key
    trade_id: str | None           # Foreign key → trades (initially)

    symbol: str                    # "GOLD", etc.
    side: int                      # 0=BUY, 1=SELL
    volume: float                  # Current lot size
    entry_price: float             # Entry level
    current_price: float           # Last market price

    stop_loss: float               # SL level
    take_profit: float             # TP level

    unrealized_profit: float       # Current P&L (calc: (current_price - entry) × volume)
    opened_at: datetime            # When position opened

    __table_args__ = (
        Index("ix_positions_symbol", "symbol"),
    )
```

---

### Table: `equity_points` (Daily equity tracking)

```python
class EquityPoint(Base):
    """Represents account equity at a point in time."""
    __tablename__ = "equity_points"

    equity_id: str                 # UUID primary key
    timestamp: datetime            # When measured (UTC)
    equity: float                  # Account equity in GBP
    balance: float                 # Account balance in GBP
    drawdown_percent: float        # Current drawdown %
    trades_open: int               # Count of open trades

    __table_args__ = (
        Index("ix_equity_timestamp", "timestamp"),
    )
```

---

### Table: `validation_logs` (Audit trail)

```python
class ValidationLog(Base):
    """Audit trail for trade validation and state changes."""
    __tablename__ = "validation_logs"

    log_id: str                    # UUID primary key
    trade_id: str                  # Foreign key → trades
    timestamp: datetime            # When event occurred (UTC)
    event_type: str                # "CREATED", "EXECUTED", "CLOSED", "ERROR", etc.
    message: str                   # Human-readable description
    details: dict | None           # JSON metadata (stored as JSONB)

    __table_args__ = (
        Index("ix_validation_logs_trade", "trade_id"),
        Index("ix_validation_logs_timestamp", "timestamp"),
    )
```

---

## 🔧 SERVICE LAYER DESIGN

### TradeService Class

```python
class TradeService:
    """Service for trade CRUD and querying."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # Create Operations
    async def create_trade(self, trade_data: TradeCreate) -> Trade:
        """Create a new trade record."""
        # Validate data (relationships, constraints)
        # Insert into database
        # Log validation event
        # Return created trade

    async def close_trade(self, trade_id: str, exit_price: float, exit_reason: str) -> Trade:
        """Close an open trade."""
        # Fetch trade (ensure OPEN status)
        # Calculate P&L, pips, duration
        # Update trade record
        # Create equity point
        # Log validation event
        # Return updated trade

    # Read Operations
    async def get_trade(self, trade_id: str) -> Trade:
        """Fetch single trade by ID."""

    async def list_trades(
        self,
        symbol: str | None = None,
        status: str | None = None,
        strategy: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 100,
        offset: int = 0
    ) -> list[Trade]:
        """List trades with filtering."""

    # Analytics Queries
    async def get_trade_stats(self, symbol: str | None = None) -> dict:
        """Calculate overall trade statistics."""
        # Returns: {
        #   "total_trades": 100,
        #   "win_rate": 0.65,
        #   "profit_factor": 2.3,
        #   "avg_profit": 125.50,
        #   "avg_loss": -45.25,
        #   "largest_win": 500.00,
        #   "largest_loss": -200.00,
        # }

    async def get_drawdown_peaks() -> list[dict]:
        """Get equity peaks and corresponding drawdowns."""

    async def get_position_summary() -> dict:
        """Summary of current open positions."""

    # Reconciliation
    async def find_orphaned_trades(self, mt5_positions: list[dict]) -> list[Trade]:
        """Find trades not in MT5 (manually closed or deleted)."""

    async def sync_with_mt5(self, mt5_positions: list[dict]) -> dict:
        """Reconcile MT5 positions with our trade store."""
        # Returns: {
        #   "synced": 5,
        #   "mismatches": 2,
        #   "orphaned": 0,
        #   "actions": [...]
        # }
```

---

## 🧪 TEST STRATEGY (20+ tests)

### Test Classes & Cases

#### 1. **TestTradeModel** (8 tests)
- [ ] Create trade with valid data
- [ ] Price constraints (BUY: SL < Entry < TP)
- [ ] Price constraints (SELL: TP < Entry < SL)
- [ ] Volume validation (0.01 - 100.0)
- [ ] Duration calculation (hours)
- [ ] P&L calculation (profit = (exit - entry) × volume)
- [ ] Pips calculation
- [ ] Status transitions (OPEN → CLOSED only)

#### 2. **TestTradeService** (12 tests)
- [ ] create_trade() with valid data → returns Trade with UUID
- [ ] create_trade() validates relationships (signal_id exists)
- [ ] close_trade() updates status to CLOSED
- [ ] close_trade() calculates P&L correctly
- [ ] list_trades() with no filters
- [ ] list_trades() filters by symbol
- [ ] list_trades() filters by date range
- [ ] list_trades() pagination (limit/offset)
- [ ] get_trade_stats() calculates win rate
- [ ] get_trade_stats() calculates profit factor
- [ ] find_orphaned_trades() detects manual closes
- [ ] sync_with_mt5() reconciles positions

#### 3. **TestMigration** (3 tests)
- [ ] Migration up: tables created with correct schema
- [ ] Migration down: tables dropped cleanly
- [ ] Indexes created (5 total)

#### 4. **TestEquityTracking** (2 tests)
- [ ] create_equity_point() records balance + drawdown
- [ ] get_drawdown_peaks() returns correct valley points

---

## 🔄 ALEMBIC MIGRATION STRUCTURE

**File**: `backend/alembic/versions/XXXX_create_trading_store.py`

```python
def upgrade() -> None:
    """Create trading store tables."""
    # Create trades table
    op.create_table(
        'trades',
        sa.Column('trade_id', sa.String(36), primary_key=True),
        sa.Column('symbol', sa.String(20), nullable=False, index=True),
        # ... all other columns
    )

    # Create indexes
    op.create_index('ix_trades_symbol_time', 'trades', ['symbol', 'entry_time'])
    op.create_index('ix_trades_status_created', 'trades', ['status', 'created_at'])

    # Create positions table
    op.create_table('positions', ...)

    # Create equity_points table
    op.create_table('equity_points', ...)

    # Create validation_logs table
    op.create_table('validation_logs', ...)

def downgrade() -> None:
    """Drop trading store tables."""
    op.drop_table('validation_logs')
    op.drop_table('equity_points')
    op.drop_table('positions')
    op.drop_table('trades')
```

---

## ✅ ACCEPTANCE CRITERIA

### Criterion 1: Schema Correctness
- [ ] All 4 tables created with correct columns
- [ ] Data types: decimals for prices (10,2), strings for enums
- [ ] Foreign key constraints defined (optional cascade)
- [ ] Indexes created (5 total)
- [ ] Timestamps use UTC

### Criterion 2: CRUD Operations
- [ ] create_trade() stores record
- [ ] get_trade() retrieves by ID
- [ ] list_trades() returns paginated results
- [ ] close_trade() updates status + calculates P&L
- [ ] delete_trade() works (cascades to validation_logs)

### Criterion 3: Validation
- [ ] Invalid prices rejected (SL < Entry < TP for BUY)
- [ ] Invalid volume rejected (<0.01 or >100)
- [ ] Status transition violations caught
- [ ] Foreign key violations caught (orphan checks)

### Criterion 4: Queries
- [ ] Filter by symbol: Only GOLD returned
- [ ] Filter by status: Only CLOSED trades
- [ ] Filter by date: Only trades in range
- [ ] Pagination: offset=10, limit=5 returns correct 5 trades
- [ ] Stats: win_rate calculates correctly (wins / total)

### Criterion 5: Reconciliation
- [ ] find_orphaned_trades() detects manual closes
- [ ] sync_with_mt5() updates our records
- [ ] Mismatch detection (volume diff, price diff)

### Criterion 6: Migration
- [ ] Alembic upgrade: tables created
- [ ] Alembic downgrade: tables dropped
- [ ] Up+down+up: idempotent (tables clean after down)

---

## 📊 PHASE BREAKDOWN

### Phase 1: Discovery & Planning ✅ (45 min - CURRENT)
- [x] Read PR-016 spec
- [x] Understand schema requirements
- [x] Design database models
- [x] Plan test strategy
- [x] Create this implementation plan

### Phase 2: Implementation (6-8 hours)
- [ ] Create `/backend/app/trading/store/models.py` (250+ lines)
- [ ] Create `/backend/app/trading/store/service.py` (300+ lines)
- [ ] Create `/backend/app/trading/store/schemas.py` (100+ lines)
- [ ] Create Alembic migration (150+ lines)
- [ ] Create `/backend/app/trading/store/__init__.py` (30 lines)

### Phase 3: Testing (2-3 hours)
- [ ] Write 20+ tests (600+ lines)
- [ ] Achieve ≥90% coverage
- [ ] All tests passing locally

### Phase 4: Verification (1-2 hours)
- [ ] Run migration up/down
- [ ] Verify schema in psql
- [ ] Sample queries work
- [ ] Performance: list_trades() <100ms
- [ ] Create verification script

---

## 🎯 FILES TO CREATE (EXACT PATHS)

```
backend/app/trading/store/__init__.py              (30 lines)
backend/app/trading/store/models.py               (250+ lines)
backend/app/trading/store/service.py              (300+ lines)
backend/app/trading/store/schemas.py              (100+ lines)
backend/alembic/versions/XXXX_create_trading_store.py (150+ lines)
backend/tests/test_trade_store_models.py          (200+ lines)
backend/tests/test_trade_store_service.py         (300+ lines)
backend/tests/test_trade_store_migration.py       (100+ lines)
docs/prs/PR-016-IMPLEMENTATION-PLAN.md            (this file)
scripts/verify/verify-pr-016.sh                   (verification script)
```

**Total**: ~1,600+ lines of code + tests

---

## 🚀 NEXT STEPS

### Immediately (Ready to code)
1. ✅ Phase 1 complete: Specification understood
2. ⏭️ Begin Phase 2: Create models.py file
3. ⏭️ Then: Create migration file
4. ⏭️ Then: Create service.py

### Quality Checklist (Before Phase 3 Testing)
- [ ] All imports correct
- [ ] Type hints 100%
- [ ] Docstrings on all classes/methods
- [ ] No hardcoded values
- [ ] Black formatting applied

### Before Merge
- [ ] 20+ tests passing
- [ ] ≥90% coverage
- [ ] Migration up/down works
- [ ] 4 PR docs complete
- [ ] GitHub Actions green

---

## 📚 REFERENCES

**PR-016 Spec**:
- `/base_files/Final_Master_Prs.md` (line ~717)

**Related PRs** (Reference):
- PR-010: Database baseline + Alembic setup
- PR-014: SignalCandidate schema
- PR-015: OrderParams schema
- PR-023: Reconciliation (depends on PR-016)

**Database Patterns**:
- `/backend/app/core/db.py` (Base, get_db)
- `/backend/alembic/env.py` (migration config)

---

## 💡 QUICK REFERENCE: Trade State Machine

```
[NEW]
  ↓
[OPEN] ←──── create_trade()
  ├─→ [CLOSED] ←──── close_trade() with exit_price
  ├─→ [CANCELLED] ←──── manual_cancel()
  └─→ [ERROR] ←──── validation failure

Final states: CLOSED, CANCELLED, ERROR (no further transitions)
```

---

**Status**: ✅ PHASE 1 COMPLETE - Ready for Phase 2 Implementation

**Next Command**: `begin phase-2` or I'll auto-start creating models.py

**Estimated Completion**: 8-10 hours total
