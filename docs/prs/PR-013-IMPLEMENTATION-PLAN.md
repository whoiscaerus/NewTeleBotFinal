# PR-013: Data Pull Pipelines - IMPLEMENTATION PLAN

**Status**: Ready for Implementation
**Date**: 2025-10-24
**Dependencies**: PR-011 ✅, PR-012 ✅
**Estimated Duration**: 2-3 hours
**Complexity**: High (data processing, rate limiting, error recovery)

---

## 🎯 Objective

Implement MT5 data ingestion pipelines that continuously pull OHLCV (Open, High, Low, Close, Volume) candle data from MetaTrader5, with automatic rate limiting, error recovery, and integration with market hours gating.

---

## 📋 Acceptance Criteria

1. **Data Ingestion**
   - [ ] Pull OHLCV candles from MT5 for trading symbols
   - [ ] Support multiple timeframes (1m, 5m, 15m, 1h, 4h, 1d)
   - [ ] Automatic candle alignment to timeframe boundaries
   - [ ] Backfill historical data (last 100 candles)

2. **Rate Limiting**
   - [ ] Respect MT5 API rate limits (1000 calls/minute typical)
   - [ ] Exponential backoff on failures
   - [ ] Queue management for pending requests
   - [ ] Statistics on API usage

3. **Market Hours Gating**
   - [ ] Only pull data during market hours
   - [ ] Skip data pull for closed markets
   - [ ] Resume pull when market reopens
   - [ ] Handle market transitions smoothly

4. **Error Recovery**
   - [ ] Handle connection timeouts
   - [ ] Retry transient failures (network, temporary errors)
   - [ ] Skip permanent failures (symbol not found, permission denied)
   - [ ] Log all failures with context

5. **Data Quality**
   - [ ] Validate candle data (OHLC relationships)
   - [ ] Detect and skip incomplete candles
   - [ ] Handle gaps in data (market holidays)
   - [ ] Store with UTC timestamps

6. **Performance**
   - [ ] Async/await for non-blocking I/O
   - [ ] Process multiple symbols concurrently
   - [ ] Cache recent candles (avoid duplicate pulls)
   - [ ] Memory-efficient storage

---

## 🏗️ Architecture

### Module Structure
```
backend/app/trading/data/
├── __init__.py                  # Public API exports
├── pipeline.py                  # Main data pipeline orchestrator
├── puller.py                    # MT5 data pulling logic
├── aggregator.py                # Candle aggregation & alignment
├── rate_limiter.py              # API rate limiting
├── cache.py                     # In-memory caching
└── validator.py                 # Data validation

backend/tests/
└── test_data_pipeline.py        # Comprehensive test suite (40+ tests)
```

### Data Flow
```
MT5 API
   ↓
[Puller] ← Rate Limiting
   ↓
[Aggregator] ← Align candles to boundaries
   ↓
[Validator] ← Check OHLC relationships
   ↓
[Cache] ← Store recent candles
   ↓
Application Logic (Signals, Strategy)
```

### Integration Points
```
From PR-011 (MT5 Session Manager):
  ├─ MT5SessionManager.ensure_connected()
  ├─ CircuitBreaker.call()
  └─ MT5HealthStatus

From PR-012 (Market Hours):
  ├─ MarketCalendar.is_market_open()
  ├─ MarketCalendar.get_next_open()
  └─ to_market_tz() / to_utc()
```

---

## 📊 Data Models

### Candle (OHLCV)
```python
@dataclass
class Candle:
    """Single candlestick (OHLCV)."""
    symbol: str              # Trading symbol (e.g., "GOLD")
    timestamp: datetime      # UTC datetime of candle open
    timeframe: str          # "1m", "5m", "15m", "1h", "4h", "1d"
    open_price: float       # Opening price
    high_price: float       # Highest price
    low_price: float        # Lowest price
    close_price: float      # Closing price
    volume: float           # Trading volume
```

### PipelineStatus
```python
@dataclass
class PipelineStatus:
    """Data pipeline status."""
    symbol: str
    last_candle_time: datetime
    candle_count: int           # Total candles cached
    error_count: int            # Failed pulls (current session)
    last_error: Optional[str]   # Last error message
    api_calls_today: int        # API calls made today
    is_active: bool             # Currently pulling data?
```

---

## 🔧 Implementation Details

### 1. Rate Limiter (rate_limiter.py)
```python
class RateLimiter:
    """API rate limiting with exponential backoff."""

    def __init__(self, calls_per_minute: int = 1000,
                 backoff_base: float = 0.5, max_backoff: float = 60):
        self.calls_per_minute = calls_per_minute
        self.backoff_base = backoff_base
        self.max_backoff = max_backoff

    async def acquire(self, symbol: str) -> None:
        """Wait until we can make an API call."""
        # Check if we've exceeded rate limit
        # Return immediately if within limit
        # Sleep if approaching limit

    async def record_failure(self, symbol: str) -> float:
        """Record API failure, return backoff seconds."""
        # Exponential backoff: 0.5s, 1s, 2s, 4s, ..., 60s max
        # Reset on success

    async def record_success(self, symbol: str) -> None:
        """Record API success, reset backoff."""
```

### 2. Data Puller (puller.py)
```python
class DataPuller:
    """MT5 data pulling with error handling."""

    def __init__(self, session_manager: MT5SessionManager,
                 rate_limiter: RateLimiter):
        self.session_manager = session_manager
        self.rate_limiter = rate_limiter

    async def pull_candles(self, symbol: str, timeframe: str,
                          count: int = 100) -> List[Candle]:
        """Pull candles from MT5."""
        # Wait for rate limit
        # Ensure market open (optional for historical data)
        # Connect to MT5
        # Pull candles via MT5SessionManager
        # Convert to Candle objects
        # Record success/failure
        # Return or raise

    async def pull_latest(self, symbol: str, timeframe: str) -> Optional[Candle]:
        """Pull just the latest completed candle."""
```

### 3. Candle Aggregator (aggregator.py)
```python
class CandleAggregator:
    """Align candles to timeframe boundaries."""

    @staticmethod
    def align_timestamp(dt: datetime, timeframe: str) -> datetime:
        """Align datetime to candle boundary."""
        # 1m: round to nearest minute
        # 5m: round to 0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55
        # 1h: round to nearest hour
        # etc.

    @staticmethod
    def is_complete(candle: Candle, now: datetime) -> bool:
        """Check if candle is complete (closed)."""
        # Candle is complete if current time > candle time + timeframe
```

### 4. Data Validator (validator.py)
```python
class CandleValidator:
    """Validate OHLCV data quality."""

    @staticmethod
    def validate(candle: Candle) -> Tuple[bool, Optional[str]]:
        """Validate candle data."""
        # Check: high >= max(open, close) >= low
        # Check: low <= min(open, close)
        # Check: prices are positive
        # Check: volume >= 0
        # Return (is_valid, error_message)
```

### 5. Pipeline Orchestrator (pipeline.py)
```python
class DataPipeline:
    """Orchestrate data pulling, validation, caching."""

    def __init__(self, session_manager: MT5SessionManager,
                 market_calendar: MarketCalendar):
        self.session_manager = session_manager
        self.market_calendar = market_calendar
        self.rate_limiter = RateLimiter()
        self.puller = DataPuller(session_manager, self.rate_limiter)
        self.cache = CandleCache()
        self.status_tracker = {}

    async def start(self):
        """Start continuous data pulling."""
        # Start background tasks for each symbol
        # Main loop: pull data, validate, cache

    async def stop(self):
        """Stop data pulling."""

    async def get_candles(self, symbol: str, timeframe: str,
                         count: int = 100) -> List[Candle]:
        """Get cached candles, pull if needed."""
```

---

## 🧪 Test Strategy

### Test Categories (40+ tests)

#### 1. Data Puller Tests (10 tests)
```python
test_pull_candles_valid_symbol()
test_pull_candles_unknown_symbol()
test_pull_candles_market_closed()
test_pull_candles_connection_timeout()
test_pull_candles_retry_on_failure()
test_pull_latest_candle()
test_pull_multiple_symbols_concurrent()
test_pull_respects_rate_limit()
test_pull_with_backoff()
test_pull_invalid_timeframe()
```

#### 2. Rate Limiter Tests (8 tests)
```python
test_rate_limiter_allows_under_limit()
test_rate_limiter_blocks_over_limit()
test_rate_limiter_exponential_backoff()
test_rate_limiter_reset_on_success()
test_rate_limiter_max_backoff()
test_rate_limiter_multiple_symbols()
test_rate_limiter_daily_reset()
test_rate_limiter_statistics()
```

#### 3. Candle Aggregator Tests (6 tests)
```python
test_align_1m_candle()
test_align_5m_candle()
test_align_1h_candle()
test_candle_complete_detection()
test_candle_incomplete_detection()
test_align_across_hour_boundary()
```

#### 4. Data Validator Tests (6 tests)
```python
test_validate_valid_candle()
test_validate_high_low_violation()
test_validate_negative_volume()
test_validate_negative_price()
test_validate_ohlc_relationships()
test_validate_invalid_timestamp()
```

#### 5. Pipeline Integration Tests (10 tests)
```python
test_pipeline_pull_and_cache()
test_pipeline_market_hours_gating()
test_pipeline_skip_closed_markets()
test_pipeline_resume_after_market_open()
test_pipeline_error_recovery()
test_pipeline_concurrent_symbols()
test_pipeline_cache_invalidation()
test_pipeline_status_tracking()
test_pipeline_get_candles_from_cache()
test_pipeline_get_candles_pull_if_missing()
```

---

## 📝 Public API

### Main Classes
```python
# From pipeline.py
from backend.app.trading.data import DataPipeline
from backend.app.trading.data import Candle, PipelineStatus

# Usage
pipeline = DataPipeline(session_manager, market_calendar)
await pipeline.start()

# Get candles (from cache or pull)
candles = await pipeline.get_candles("GOLD", "1h", count=100)

# Get status
status = pipeline.get_status("GOLD")
print(f"Last candle: {status.last_candle_time}")
print(f"API calls today: {status.api_calls_today}")
```

### Rate Limiting
```python
rate_limiter = RateLimiter(calls_per_minute=1000)
await rate_limiter.acquire("GOLD")  # Wait if needed
# ... make API call ...
await rate_limiter.record_success("GOLD")
```

### Data Validation
```python
validator = CandleValidator()
is_valid, error = validator.validate(candle)
if not is_valid:
    log.warning(f"Invalid candle: {error}")
```

---

## 🔄 Dependencies

**PR-013 Depends On**:
- ✅ PR-011 (MT5 Session Manager) - COMPLETE
  - Uses: MT5SessionManager, CircuitBreaker, MT5HealthStatus
- ✅ PR-012 (Market Hours) - COMPLETE
  - Uses: MarketCalendar, to_market_tz, to_utc

**PR-014 Depends On**:
- ⏳ PR-013 (Data Pull Pipelines) - THIS PR
  - Will Use: DataPipeline, Candle, get_candles()

---

## ⚙️ Configuration

### Environment Variables
```bash
# Rate limiting
MT5_RATE_LIMIT_CALLS_PER_MINUTE=1000
MT5_RATE_LIMIT_MAX_BACKOFF=60

# Data retention
DATA_CACHE_MAX_CANDLES_PER_SYMBOL=1000
DATA_CACHE_RETENTION_HOURS=48

# Pull frequency
DATA_PULL_INTERVAL_SECONDS=5
DATA_PULL_BATCH_SIZE=10
```

---

## 🎯 Success Criteria

- ✅ 40+ test cases passing
- ✅ ≥90% code coverage
- ✅ 100% type hints
- ✅ 100% docstrings
- ✅ Handles all error paths
- ✅ Rate limiting functional
- ✅ Market hours integration
- ✅ Performance acceptable (<100ms per pull)
- ✅ Zero TODOs/FIXMEs
- ✅ Black formatted

---

## 📅 Timeline Estimate

**Phase 1: Data Puller** (45 minutes)
- Implement DataPuller class
- Integration with MT5SessionManager
- Error handling and retry logic
- Write 10 tests

**Phase 2: Rate Limiter** (30 minutes)
- Implement RateLimiter with exponential backoff
- Statistics tracking
- Write 8 tests

**Phase 3: Validation & Aggregation** (30 minutes)
- Implement CandleValidator
- Implement CandleAggregator
- Write 12 tests

**Phase 4: Pipeline Orchestrator** (45 minutes)
- Implement DataPipeline
- Market hours integration
- Caching logic
- Write 10 tests

**Phase 5: Testing & Refinement** (30 minutes)
- Run full test suite
- Coverage verification
- Black formatting
- Documentation

**Total**: 2.5 - 3 hours

---

## 📌 Notes

### Market Hours Integration
- Only pull candles during market hours
- Skip pull requests if market closed
- Don't pull historical data (backfill) during market hours
- Resume automatic pulls when market reopens

### Error Scenarios
1. Symbol not found → Skip (permanent)
2. Connection timeout → Retry with backoff
3. Rate limit hit → Wait and retry
4. Invalid data → Log and skip
5. Market closed → Wait for next open

### Performance Considerations
- Use asyncio for concurrent pulls
- Batch requests when possible
- Cache to avoid duplicate pulls
- Limit concurrent requests (e.g., max 10)

---

## 🔗 Related Files

**PR-011 Integration**:
- `backend/app/trading/mt5/session.py` - MT5SessionManager
- `backend/app/trading/mt5/circuit_breaker.py` - CircuitBreaker
- `backend/app/trading/mt5/errors.py` - Error types

**PR-012 Integration**:
- `backend/app/trading/time/market_calendar.py` - MarketCalendar
- `backend/app/trading/time/tz.py` - Timezone utilities

**Database** (if needed):
- Store candles in PostgreSQL
- Create candlestick table with indexes
- Query by symbol + timeframe + timestamp

---

**Ready to implement PR-013** ✅
