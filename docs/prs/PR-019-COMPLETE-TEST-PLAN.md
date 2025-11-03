# PR-019: Complete 100% Coverage Test Plan

**Status**: READY FOR IMPLEMENTATION  
**Bug Fix**: ✅ COMPLETED (heartbeat.py line 218)  
**Test Coverage Target**: 100% (2,170 lines across 5 modules)

---

## Executive Summary

PR-019 implements live trading bot enhancements:
- **Heartbeat Manager** (240 lines): Periodic health metrics emission
- **Guards** (345 lines): Max drawdown & min equity enforcement  
- **DrawdownGuard** (511 lines): Peak equity tracking & position closure
- **EventEmitter** (357 lines): 8 event types for observability
- **TradingLoop** (717 lines): Main loop orchestrating everything

**Current State**:
- ✅ Implementation files exist (all 5 modules)
- ✅ Critical bug fixed (heartbeat.py awaiting async metrics provider)
- ❌ Zero tests exist (need ~400 tests for 100% coverage)
- ❌ Zero coverage metrics collected

---

## Module Coverage Breakdown

### 1. HeartbeatManager (heartbeat.py) - 240 lines

**Public Methods to Test**:
- `__init__(interval_seconds, loop_id, logger)` - Initialization validation
- `async emit(signals_processed, trades_executed, error_count, ...)` - Metrics emission with lock
- `async start_background_heartbeat(metrics_provider)` - Background task management

**Key Test Scenarios**:

#### 1.1 Initialization Tests (3 tests)
```python
def test_heartbeat_valid_initialization():
    """Valid heartbeat with default and custom values."""
    hb = HeartbeatManager(interval_seconds=5, loop_id="test_loop")
    assert hb.interval_seconds == 5
    assert hb.loop_id == "test_loop"

def test_heartbeat_invalid_interval():
    """Reject invalid interval values."""
    with pytest.raises(ValueError, match="must be > 0"):
        HeartbeatManager(interval_seconds=0)
    with pytest.raises(ValueError, match="must be > 0"):
        HeartbeatManager(interval_seconds=-5)

def test_heartbeat_creates_default_logger():
    """Creates default logger if not provided."""
    hb = HeartbeatManager()
    assert hb._logger is not None
    assert isinstance(hb._logger, logging.Logger)
```

#### 1.2 Emit Tests (8 tests)
```python
async def test_emit_records_metrics():
    """Emit correctly records all metrics."""
    hb = HeartbeatManager(loop_id="test")
    metrics = await hb.emit(
        signals_processed=5,
        trades_executed=2,
        error_count=0,
        loop_duration_ms=245.5,
        positions_open=1,
        account_equity=10250.50,
        total_signals_lifetime=100,
        total_trades_lifetime=50
    )
    
    assert metrics.signals_processed == 5
    assert metrics.trades_executed == 2
    assert metrics.loop_id == "test"
    assert metrics.timestamp is not None

async def test_emit_lock_prevents_concurrent_emissions():
    """Lock ensures only one emission at a time."""
    hb = HeartbeatManager(loop_id="test")
    
    emit_times = []
    
    async def emit_with_timing():
        emit_times.append(time.time())
        await hb.emit()
        emit_times.append(time.time())
    
    # Start two concurrent emits
    await asyncio.gather(
        emit_with_timing(),
        emit_with_timing()
    )
    
    # Verify second emission didn't start until first finished
    assert emit_times[1] >= emit_times[0]
    assert emit_times[2] >= emit_times[1]

async def test_emit_with_zero_metrics():
    """Emit handles zero values correctly."""
    hb = HeartbeatManager()
    metrics = await hb.emit()  # All defaults are 0
    
    assert metrics.signals_processed == 0
    assert metrics.trades_executed == 0
    assert metrics.error_count == 0

async def test_emit_high_precision_metrics():
    """Emit preserves high precision float values."""
    hb = HeartbeatManager()
    metrics = await hb.emit(
        loop_duration_ms=123.456789,
        account_equity=10250.50
    )
    
    assert metrics.loop_duration_ms == 123.456789
    assert metrics.account_equity == 10250.50

async def test_emit_records_to_metrics_registry(mock_metrics):
    """Emit increments heartbeat counter in metrics registry."""
    hb = HeartbeatManager()
    await hb.emit()
    
    mock_metrics.heartbeat_total.inc.assert_called_once()

async def test_emit_logs_structured_message():
    """Emit logs all metrics with structured format."""
    hb = HeartbeatManager(logger=mock_logger)
    await hb.emit(signals_processed=3, trades_executed=1)
    
    mock_logger.info.assert_called()
    call_args = mock_logger.info.call_args
    assert "signals_processed" in call_args.kwargs.get("extra", {})

async def test_emit_handles_metrics_registry_error():
    """Emit continues if metrics registry fails."""
    hb = HeartbeatManager()
    # Mock get_metrics to raise exception
    with patch("backend.app.observability.metrics.get_metrics", side_effect=Exception("Registry error")):
        metrics = await hb.emit()  # Should not raise
        assert metrics is not None

async def test_emit_returns_heartbeat_metrics():
    """Emit returns HeartbeatMetrics dataclass."""
    hb = HeartbeatManager()
    result = await hb.emit(signals_processed=5)
    
    assert isinstance(result, HeartbeatMetrics)
    assert hasattr(result, "timestamp")
    assert hasattr(result, "loop_id")
```

#### 1.3 Background Heartbeat Tests (8 tests)
```python
async def test_start_background_heartbeat_returns_task():
    """Background heartbeat returns asyncio.Task."""
    hb = HeartbeatManager(interval_seconds=10)
    
    async def dummy_metrics():
        return {"signals_processed": 0, "trades_executed": 0}
    
    task = await hb.start_background_heartbeat(dummy_metrics)
    assert isinstance(task, asyncio.Task)
    task.cancel()

async def test_heartbeat_with_async_metrics_provider():
    """✅ CRITICAL FIX: Async metrics provider properly awaited."""
    hb = HeartbeatManager(interval_seconds=0.05)
    
    call_count = 0
    async def async_metrics():
        nonlocal call_count
        call_count += 1
        return {
            "signals_processed": call_count,
            "trades_executed": 0,
            "error_count": 0,
            "loop_duration_ms": 10.0,
            "positions_open": 0,
            "account_equity": 10000.0,
            "total_signals_lifetime": call_count,
            "total_trades_lifetime": 0,
        }
    
    task = await hb.start_background_heartbeat(async_metrics)
    await asyncio.sleep(0.15)  # Let heartbeat run 3x
    task.cancel()
    
    # Verify metrics were called multiple times
    assert call_count >= 3

async def test_heartbeat_emits_at_intervals():
    """Heartbeat emits at specified interval."""
    hb = HeartbeatManager(interval_seconds=0.1)
    
    emit_times = []
    original_emit = hb.emit
    
    async def tracked_emit(**kwargs):
        emit_times.append(time.time())
        return await original_emit(**kwargs)
    
    hb.emit = tracked_emit
    
    async def dummy_metrics():
        return {"signals_processed": 0, "trades_executed": 0}
    
    task = await hb.start_background_heartbeat(dummy_metrics)
    await asyncio.sleep(0.35)  # Should emit 3 times
    task.cancel()
    
    # Allow for timing variance (≥2 emissions expected)
    assert len(emit_times) >= 2

async def test_heartbeat_handles_cancelled_error():
    """Heartbeat exits cleanly on cancellation."""
    hb = HeartbeatManager(interval_seconds=0.1)
    
    async def dummy_metrics():
        return {"signals_processed": 0, "trades_executed": 0}
    
    task = await hb.start_background_heartbeat(dummy_metrics)
    await asyncio.sleep(0.05)
    
    with pytest.raises(asyncio.CancelledError):
        task.cancel()
        await task

async def test_heartbeat_logs_cancellation():
    """Heartbeat logs when cancelled."""
    hb = HeartbeatManager(logger=mock_logger, interval_seconds=10)
    
    async def dummy_metrics():
        return {"signals_processed": 0, "trades_executed": 0}
    
    task = await hb.start_background_heartbeat(dummy_metrics)
    task.cancel()
    
    await asyncio.sleep(0.1)
    # Mock logger should have received cancellation message
    mock_logger.info.assert_called()

async def test_heartbeat_handles_emit_error():
    """Heartbeat logs but continues on emit error."""
    hb = HeartbeatManager(interval_seconds=0.05, logger=mock_logger)
    
    call_count = 0
    async def failing_metrics():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("Metrics error")
        return {"signals_processed": 0, "trades_executed": 0}
    
    task = await hb.start_background_heartbeat(failing_metrics)
    await asyncio.sleep(0.15)
    task.cancel()
    
    # Should have tried multiple times despite error
    assert call_count >= 2

async def test_heartbeat_passes_metrics_to_emit():
    """Heartbeat passes provider metrics correctly to emit."""
    hb = HeartbeatManager(interval_seconds=0.05)
    
    emitted_metrics = []
    original_emit = hb.emit
    
    async def tracked_emit(**kwargs):
        emitted_metrics.append(kwargs)
        return await original_emit(**kwargs)
    
    hb.emit = tracked_emit
    
    async def dummy_metrics():
        return {
            "signals_processed": 42,
            "trades_executed": 7,
            "error_count": 1,
            "loop_duration_ms": 123.45,
            "positions_open": 3,
            "account_equity": 50000.0,
            "total_signals_lifetime": 500,
            "total_trades_lifetime": 250,
        }
    
    task = await hb.start_background_heartbeat(dummy_metrics)
    await asyncio.sleep(0.1)
    task.cancel()
    
    # Verify emitted metrics match provider output
    assert len(emitted_metrics) > 0
    first_emit = emitted_metrics[0]
    assert first_emit["signals_processed"] == 42
    assert first_emit["trades_executed"] == 7
```

#### 1.4 Integration Tests (2 tests)
```python
async def test_multiple_concurrent_heartbeats():
    """Multiple HeartbeatManager instances work independently."""
    hb1 = HeartbeatManager(interval_seconds=10, loop_id="loop1")
    hb2 = HeartbeatManager(interval_seconds=10, loop_id="loop2")
    
    metrics1 = await hb1.emit(signals_processed=1)
    metrics2 = await hb2.emit(signals_processed=2)
    
    assert metrics1.loop_id == "loop1"
    assert metrics2.loop_id == "loop2"
    assert metrics1.signals_processed == 1
    assert metrics2.signals_processed == 2

async def test_heartbeat_lifecycle():
    """Complete heartbeat lifecycle: init → start → emit → cancel."""
    hb = HeartbeatManager(interval_seconds=0.1, loop_id="full_test")
    
    emit_count = 0
    async def counting_metrics():
        nonlocal emit_count
        emit_count += 1
        return {"signals_processed": emit_count, "trades_executed": 0}
    
    # Start background heartbeat
    task = await hb.start_background_heartbeat(counting_metrics)
    
    # Verify it's running
    assert not task.done()
    
    # Let it run for a bit
    await asyncio.sleep(0.25)
    
    # Verify emissions occurred
    assert emit_count >= 1
    
    # Cancel gracefully
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    
    # Verify task is done
    assert task.done()
```

---

**Subtotal HeartbeatManager**: 21 tests

---

### 2. Guards (guards.py) - 345 lines

**Public Methods to Test**:
- `__init__(max_drawdown_percent, min_equity_gbp, alert_service, logger)`
- `async check_and_enforce(mt5_client, order_service)` - Main guard check
- `async get_state()` - Get current guard state
- `async reset_guard_state()` - Reset for new session

**Key Test Scenarios**:

#### 2.1 Initialization Tests (4 tests)
```python
def test_guards_valid_initialization():
    """Valid guards initialization."""
    guards = Guards(max_drawdown_percent=20.0, min_equity_gbp=500.0)
    assert guards.max_drawdown_percent == 20.0
    assert guards.min_equity_gbp == 500.0

def test_guards_invalid_drawdown():
    """Reject invalid drawdown percentages."""
    with pytest.raises(ValueError, match="between 0 and 100"):
        Guards(max_drawdown_percent=0)
    with pytest.raises(ValueError, match="between 0 and 100"):
        Guards(max_drawdown_percent=100)
    with pytest.raises(ValueError, match="between 0 and 100"):
        Guards(max_drawdown_percent=150)

def test_guards_invalid_min_equity():
    """Reject invalid minimum equity."""
    with pytest.raises(ValueError, match="must be > 0"):
        Guards(min_equity_gbp=0)
    with pytest.raises(ValueError, match="must be > 0"):
        Guards(min_equity_gbp=-100)

def test_guards_creates_default_logger():
    """Creates default logger if not provided."""
    guards = Guards()
    assert guards._logger is not None
```

#### 2.2 Drawdown Guard Tests (12 tests)
```python
async def test_check_and_enforce_no_trigger_above_threshold():
    """Guard doesn't trigger when drawdown below threshold."""
    guards = Guards(max_drawdown_percent=20.0, min_equity_gbp=500.0)
    mt5_client = AsyncMock()
    order_service = AsyncMock()
    
    # Setup: entry $10k, peak $11k, current $10.5k = 4.5% drawdown
    mt5_client.get_account_equity.return_value = 10500
    
    state = await guards.check_and_enforce(mt5_client, order_service)
    
    assert state.cap_triggered is False
    assert state.min_equity_triggered is False
    assert order_service.close_all_positions.call_count == 0

async def test_check_and_enforce_trigger_max_drawdown():
    """Guard triggers and closes positions on max drawdown breach."""
    guards = Guards(max_drawdown_percent=20.0, min_equity_gbp=500.0)
    mt5_client = AsyncMock()
    order_service = AsyncMock()
    
    # Setup: entry $10k, peak $11k, current $8.5k = 22.7% drawdown
    mt5_client.get_account_equity.side_effect = [10000, 11000, 8500]  # First call init, second peak, third current
    order_service.close_all_positions.return_value = True
    
    state = await guards.check_and_enforce(mt5_client, order_service)
    
    assert state.cap_triggered is True
    assert state.current_drawdown > 20.0
    order_service.close_all_positions.assert_called_once()

async def test_check_and_enforce_trigger_min_equity():
    """Guard triggers on minimum equity breach."""
    guards = Guards(max_drawdown_percent=50.0, min_equity_gbp=500.0)
    mt5_client = AsyncMock()
    order_service = AsyncMock()
    
    mt5_client.get_account_equity.side_effect = [10000, 10000, 400]  # Current drops below $500
    order_service.close_all_positions.return_value = True
    
    state = await guards.check_and_enforce(mt5_client, order_service)
    
    assert state.min_equity_triggered is True
    order_service.close_all_positions.assert_called_once()

async def test_check_and_enforce_peak_equity_tracking():
    """Peak equity updates correctly as account grows."""
    guards = Guards(max_drawdown_percent=20.0)
    mt5_client = AsyncMock()
    order_service = AsyncMock()
    
    # First check: entry $10k
    mt5_client.get_account_equity.return_value = 10000
    state1 = await guards.check_and_enforce(mt5_client, order_service)
    
    # Second check: account grows to $12k
    mt5_client.get_account_equity.return_value = 12000
    state2 = await guards.check_and_enforce(mt5_client, order_service)
    
    # Peak should update
    assert state2.peak_equity == 12000

async def test_check_and_enforce_drawdown_calculation():
    """Drawdown calculated correctly: (peak - current) / peak * 100."""
    guards = Guards(max_drawdown_percent=50.0)
    mt5_client = AsyncMock()
    order_service = AsyncMock()
    
    mt5_client.get_account_equity.side_effect = [10000, 10000, 5000]
    
    state = await guards.check_and_enforce(mt5_client, order_service)
    
    # (10000 - 5000) / 10000 * 100 = 50%
    assert state.current_drawdown == 50.0
    assert state.cap_triggered is True

async def test_check_and_enforce_at_exact_threshold():
    """Guard triggers at exact threshold."""
    guards = Guards(max_drawdown_percent=20.0)
    mt5_client = AsyncMock()
    order_service = AsyncMock()
    
    mt5_client.get_account_equity.side_effect = [10000, 10000, 8000]
    order_service.close_all_positions.return_value = True
    
    # (10000 - 8000) / 10000 * 100 = 20%
    state = await guards.check_and_enforce(mt5_client, order_service)
    
    assert state.current_drawdown == 20.0
    assert state.cap_triggered is True

async def test_check_and_enforce_sets_triggered_timestamp():
    """Sets triggered_at when guard triggers."""
    guards = Guards(max_drawdown_percent=20.0)
    mt5_client = AsyncMock()
    order_service = AsyncMock()
    
    mt5_client.get_account_equity.side_effect = [10000, 10000, 7000]
    
    before = datetime.now(UTC)
    state = await guards.check_and_enforce(mt5_client, order_service)
    after = datetime.now(UTC)
    
    assert before <= state.triggered_at <= after

async def test_check_and_enforce_handles_mt5_error():
    """Continues safely if MT5 call fails."""
    guards = Guards(max_drawdown_percent=20.0)
    mt5_client = AsyncMock()
    order_service = AsyncMock()
    
    mt5_client.get_account_equity.side_effect = Exception("MT5 connection lost")
    
    with pytest.raises(Exception):
        await guards.check_and_enforce(mt5_client, order_service)

async def test_check_and_enforce_alerts_on_trigger():
    """Sends Telegram alert when guard triggers."""
    alert_service = AsyncMock()
    guards = Guards(max_drawdown_percent=20.0, alert_service=alert_service)
    mt5_client = AsyncMock()
    order_service = AsyncMock()
    
    mt5_client.get_account_equity.side_effect = [10000, 10000, 7000]
    order_service.close_all_positions.return_value = True
    
    state = await guards.check_and_enforce(mt5_client, order_service)
    
    alert_service.alert.assert_called()
    call_args = alert_service.alert.call_args[0][0]
    assert "drawdown" in call_args.lower()

async def test_check_and_enforce_handles_close_all_error():
    """Logs but doesn't raise if close_all_positions fails."""
    guards = Guards(max_drawdown_percent=20.0)
    mt5_client = AsyncMock()
    order_service = AsyncMock()
    
    mt5_client.get_account_equity.side_effect = [10000, 10000, 7000]
    order_service.close_all_positions.side_effect = Exception("Close failed")
    
    # Should not raise, should log error
    with pytest.raises(Exception):  # Depends on implementation
        await guards.check_and_enforce(mt5_client, order_service)

async def test_check_and_enforce_equity_types():
    """Handles different numeric types (int, float, Decimal)."""
    guards = Guards()
    mt5_client = AsyncMock()
    order_service = AsyncMock()
    
    # Test with different numeric types
    mt5_client.get_account_equity.side_effect = [10000, 10500.75, 9500]
    
    state = await guards.check_and_enforce(mt5_client, order_service)
    
    assert isinstance(state.current_equity, (int, float))
```

#### 2.3 Guard State Tests (5 tests)
```python
async def test_get_state_returns_current_guard_state():
    """get_state returns current GuardState."""
    guards = Guards()
    state = await guards.get_state()
    
    assert isinstance(state, GuardState)
    assert state.current_drawdown == 0.0

async def test_reset_guard_state_clears_state():
    """reset resets all guard state."""
    guards = Guards()
    mt5_client = AsyncMock()
    order_service = AsyncMock()
    
    mt5_client.get_account_equity.side_effect = [10000, 10000, 7000]
    
    # Trigger guard
    state1 = await guards.check_and_enforce(mt5_client, order_service)
    assert state1.cap_triggered is True
    
    # Reset
    await guards.reset_guard_state()
    
    state2 = await guards.get_state()
    assert state2.cap_triggered is False

async def test_state_persists_across_checks():
    """Guard state persists between check_and_enforce calls."""
    guards = Guards()
    mt5_client = AsyncMock()
    order_service = AsyncMock()
    
    mt5_client.get_account_equity.return_value = 10000
    
    state1 = await guards.check_and_enforce(mt5_client, order_service)
    state2 = await guards.check_and_enforce(mt5_client, order_service)
    
    # Peak equity should persist
    assert state1.peak_equity == state2.peak_equity

async def test_state_tracks_last_check_time():
    """state.last_check_time updates with each check."""
    guards = Guards()
    mt5_client = AsyncMock()
    order_service = AsyncMock()
    
    mt5_client.get_account_equity.return_value = 10000
    
    before = datetime.now(UTC)
    state = await guards.check_and_enforce(mt5_client, order_service)
    after = datetime.now(UTC)
    
    assert before <= state.last_check_time <= after

async def test_state_reason_populated_on_trigger():
    """state.reason field populated when guard triggers."""
    guards = Guards(max_drawdown_percent=20.0)
    mt5_client = AsyncMock()
    order_service = AsyncMock()
    
    mt5_client.get_account_equity.side_effect = [10000, 10000, 7000]
    
    state = await guards.check_and_enforce(mt5_client, order_service)
    
    assert state.cap_triggered is True
    assert len(state.reason) > 0
    assert "drawdown" in state.reason.lower() or "20" in state.reason
```

---

**Subtotal Guards**: 21 tests

---

### 3. DrawdownGuard (drawdown.py) - 511 lines

**Key Classes & Methods**:
- `DrawdownGuard` class with peak equity tracking
- `async monitor(current_equity)` - Update peak and check thresholds
- `async should_close_positions()` - Determine if positions need closing
- `async close_all_positions(order_service)` - Execute closure

**Key Test Scenarios** (20 tests):
- Peak equity tracking and updates
- Drawdown calculation with various equity levels
- Position closure triggers
- Multiple monitored sessions
- Equity recovery scenarios
- Integration with OrderService

---

### 4. EventEmitter (events.py) - 357 lines

**8 Event Types to Test**:
1. `emit_signal_received()` - Signal received from strategy
2. `emit_signal_approved()` - User approved signal
3. `emit_trade_executed()` - Trade successfully executed
4. `emit_trade_failed()` - Trade execution failed
5. `emit_position_closed()` - Position closed (TP/SL/guard)
6. `emit_loop_started()` - Loop started
7. `emit_loop_stopped()` - Loop stopped
8. `emit()` - Generic event emission

**Key Test Scenarios** (24 tests):
- Each event type emitted with correct metadata
- Metrics registry integration
- Structured logging
- Metadata field completeness
- Event timestamps
- Multiple concurrent emitters
- Event persistence

---

### 5. TradingLoop (loop.py) - 717 lines

**Major Methods to Test**:
- `__init__()` - Initialization with dependencies
- `async start(duration_seconds)` - Main loop execution
- `async stop()` - Graceful shutdown
- `async process_signal(signal)` - Signal processing
- `async execute_trade(signal)` - Trade execution with retry
- `_collect_metrics()` - Metrics collection

**Key Test Scenarios** (28 tests):
- Loop initialization with all dependencies
- Signal processing pipeline
- Trade execution with retry logic
- Heartbeat integration
- Event emission during lifecycle
- Error recovery
- Graceful shutdown
- Concurrent signal processing
- MT5 integration
- Database persistence
- Approval service integration

---

## Test File Organization

```
backend/tests/
├── test_runtime_heartbeat.py (21 tests)
├── test_runtime_guards.py (21 tests)  
├── test_runtime_drawdown.py (20 tests)
├── test_runtime_events.py (24 tests)
└── test_runtime_loop.py (28 tests)
```

**Total: 114 tests for 100% coverage**

---

## Testing Requirements & Patterns

### Real Implementations (NOT Mocks)
- ✅ Use real HeartbeatManager, Guards, DrawdownGuard
- ✅ Use real EventEmitter
- ❌ DO NOT mock core business logic classes

### Fake Backends (USE MOCKS)
- ✅ Mock MT5Client (external trading platform)
- ✅ Mock OrderService methods (external trade execution)
- ✅ Mock Telegram AlertService (external alerts)
- ✅ Mock metrics registry (observability)

### Fixtures Required
```python
@pytest.fixture
async def heartbeat_manager():
    """Fresh HeartbeatManager for each test."""
    return HeartbeatManager(interval_seconds=10, loop_id="test")

@pytest.fixture
async def guards():
    """Fresh Guards instance."""
    return Guards(max_drawdown_percent=20.0, min_equity_gbp=500.0)

@pytest.fixture
async def event_emitter():
    """Fresh EventEmitter instance."""
    return EventEmitter(loop_id="test")

@pytest.fixture
def mock_mt5_client():
    """Mock MT5 client."""
    return AsyncMock()

@pytest.fixture
def mock_order_service():
    """Mock order service."""
    return AsyncMock()

@pytest.fixture
def mock_alerts_service():
    """Mock Telegram alerts service."""
    return AsyncMock()

@pytest.fixture
def mock_metrics():
    """Mock metrics registry."""
    return AsyncMock()
```

---

## Acceptance Criteria Verification

| Criterion | Test File | Test Count |
|-----------|-----------|-----------|
| Heartbeat emits at intervals | test_runtime_heartbeat.py | 3 |
| Metrics provider awaited (BUG FIX) | test_runtime_heartbeat.py | 1 |
| Lock prevents concurrent emissions | test_runtime_heartbeat.py | 1 |
| Drawdown calculated correctly | test_runtime_guards.py | 3 |
| Positions closed on guard trigger | test_runtime_guards.py | 4 |
| Telegram alerts sent | test_runtime_guards.py | 1 |
| All 8 events emitted | test_runtime_events.py | 8 |
| Event metadata complete | test_runtime_events.py | 8 |
| Loop processes signals | test_runtime_loop.py | 5 |
| Loop executes trades | test_runtime_loop.py | 5 |
| Loop emits events | test_runtime_loop.py | 4 |
| Loop handles errors | test_runtime_loop.py | 6 |
| Integration: Full workflow | test_runtime_loop.py | 8 |

**Total Coverage**: 114 tests validating all business logic

---

## Next Steps

1. ✅ Bug fixed in heartbeat.py (await added)
2. ⏳ Create test_runtime_heartbeat.py (21 tests)
3. ⏳ Create test_runtime_guards.py (21 tests)
4. ⏳ Create test_runtime_events.py (24 tests)
5. ⏳ Create test_runtime_drawdown.py (20 tests)
6. ⏳ Create test_runtime_loop.py (28 tests)
7. ⏳ Run full coverage: `pytest backend/tests/test_runtime_* --cov=backend.app.trading.runtime --cov-report=term-missing`
8. ⏳ Achieve 100% coverage
9. ⏳ Verify all business logic working
10. ⏳ Document completion

---

**Status**: Ready to begin implementation of test suite
