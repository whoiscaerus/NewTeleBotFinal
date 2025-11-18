# 🧪 Test Failure Report
**Generated**: 2025-11-17T21:11:02.651405
**GitHub Actions Run**: Unknown

## 📊 Summary
- **Total Tests**: 3136
- ✅ **Passed**: 2079
- ❌ **Failed**: 70
- ⏭️ **Skipped**: 58
- 💥 **Errors**: 929
- **Pass Rate**: 66.3%

## 🚨 Failures by Module

| Module | Count | Tests |
|--------|-------|-------|
| `tests/integration/test_position_monitor.py` | 6 | test_buy_position_sl_breach, test_buy_position_tp_breach, test_sell_position_sl_breach, ... +3 more |
| `tests/test_data_pipeline.py` | 17 | test_symbol_price_creation, test_symbol_price_get_mid_price, test_symbol_price_get_spread, ... +14 more |
| `tests/test_decision_logs.py` | 1 | test_repr |
| `tests/test_poll_v2.py` | 7 | test_record_poll_no_approvals, test_record_poll_with_approvals, test_record_multiple_polls, ... +4 more |
| `tests/test_pr_005_ratelimit.py` | 11 | test_tokens_consumed_on_request, test_rate_limit_enforced_when_tokens_exhausted, test_different_users_have_separate_buckets, ... +8 more |
| `tests/test_pr_016_trade_store.py` | 21 | test_trade_creation_valid, test_trade_buy_price_relationships, test_trade_sell_creation, ... +18 more |
| `tests/test_pr_017_018_integration.py` | 7 | test_retry_decorator_retries_on_transient_failure, test_retry_stops_on_success_without_extra_retries, test_retry_on_timeout_error, ... +4 more |

## 📋 Detailed Failures

### tests/integration/test_position_monitor.py

#### 1. test_buy_position_sl_breach

**Test Path**: `tests/integration/test_position_monitor.py::test_buy_position_sl_breach`

**Error**:
```
backend/tests/integration/test_position_monitor.py:26: in test_buy_position_sl_breach
    position = OpenPosition(
<string>:4: in __init__
    ???
        kwargs     = {'approval_id': '92d0c90b-7ad8-4ca6-9284-6876211174ad',
 'device_id': '2691f9d5-3820-4ec0-9af9-6d8e83b6358c',
 'entry_price': 2655.0,
 'execution_id': '80e27e57-733a-44d9-853b-a2d8dda1615a',
 'id': '5b352dd0-dbcb-4fef-9f42-e0f4ca8e0d70',
 'instrument': 'XAUUSD',
 'owner_sl': 2645.0,
 'owner_tp': 2670.0,
 'side': 0,
 'signal_id': '
... (truncated)
```

#### 2. test_buy_position_tp_breach

**Test Path**: `tests/integration/test_position_monitor.py::test_buy_position_tp_breach`

**Error**:
```
backend/tests/integration/test_position_monitor.py:61: in test_buy_position_tp_breach
    position = OpenPosition(
<string>:4: in __init__
    ???
        kwargs     = {'approval_id': '81ed8a10-e611-4a2d-bc54-d3b0e388ad2d',
 'device_id': '07b046f8-1ca1-40c3-ab58-6a3a0709496b',
 'entry_price': 2655.0,
 'execution_id': 'b5b710c1-436c-4188-a047-c9e8038d41bf',
 'id': '0531e649-10d9-4b38-a86f-f90e562bccea',
 'instrument': 'XAUUSD',
 'owner_sl': 2645.0,
 'owner_tp': 2670.0,
 'side': 0,
 'signal_id': '
... (truncated)
```

#### 3. test_sell_position_sl_breach

**Test Path**: `tests/integration/test_position_monitor.py::test_sell_position_sl_breach`

**Error**:
```
backend/tests/integration/test_position_monitor.py:96: in test_sell_position_sl_breach
    position = OpenPosition(
<string>:4: in __init__
    ???
        kwargs     = {'approval_id': '262a7668-1790-491a-ada6-bfd5f6d7aac1',
 'device_id': 'bebaa0aa-a523-4a16-aeab-0dde6c27d0b0',
 'entry_price': 1.085,
 'execution_id': 'b9fe8dba-5e1f-4e80-81a8-9c0b532692a4',
 'id': '964a3b10-44ab-47fb-8d4d-2ecff95d4600',
 'instrument': 'EURUSD',
 'owner_sl': 1.087,
 'owner_tp': 1.082,
 'side': 1,
 'signal_id': '65
... (truncated)
```

#### 4. test_sell_position_tp_breach

**Test Path**: `tests/integration/test_position_monitor.py::test_sell_position_tp_breach`

**Error**:
```
backend/tests/integration/test_position_monitor.py:131: in test_sell_position_tp_breach
    position = OpenPosition(
<string>:4: in __init__
    ???
        kwargs     = {'approval_id': 'e9f6419a-a30c-4cba-bf91-d7dfc97e9c82',
 'device_id': '2a1e8d3a-e011-4161-8ead-d9387778b165',
 'entry_price': 1.085,
 'execution_id': '316ec4da-38e1-4e48-ab5d-24750575b011',
 'id': '6f0e3fc0-4f18-4286-b81a-8de52289d421',
 'instrument': 'EURUSD',
 'owner_sl': 1.087,
 'owner_tp': 1.082,
 'side': 1,
 'signal_id': '6
... (truncated)
```

#### 5. test_position_with_no_owner_levels

**Test Path**: `tests/integration/test_position_monitor.py::test_position_with_no_owner_levels`

**Error**:
```
backend/tests/integration/test_position_monitor.py:167: in test_position_with_no_owner_levels
    position = OpenPosition(
<string>:4: in __init__
    ???
        kwargs     = {'approval_id': 'bb6737ef-bb07-43f6-92ee-0055292dff12',
 'device_id': '11f77895-b08e-4232-ab3d-aae9a8fe94eb',
 'entry_price': 2655.0,
 'execution_id': '007d9ebf-2228-45af-8b29-2a91ef98f537',
 'id': 'd98d7487-ccd0-491c-9994-9dec20e68cf4',
 'instrument': 'XAUUSD',
 'owner_sl': None,
 'owner_tp': None,
 'side': 0,
 'signal_id
... (truncated)
```

#### 6. test_position_with_only_sl_set

**Test Path**: `tests/integration/test_position_monitor.py::test_position_with_only_sl_set`

**Error**:
```
backend/tests/integration/test_position_monitor.py:197: in test_position_with_only_sl_set
    position = OpenPosition(
<string>:4: in __init__
    ???
        kwargs     = {'approval_id': '6f733eaa-de8a-4ee5-9e8b-7dd690cffcb8',
 'device_id': 'c7d4227d-2fb9-4319-ac48-003383bae8cc',
 'entry_price': 2655.0,
 'execution_id': '47de0faa-9fe9-438b-92ef-5367c6cf6c53',
 'id': '2612e812-3d70-43c4-ab47-d674a8d1962e',
 'instrument': 'XAUUSD',
 'owner_sl': 2645.0,
 'owner_tp': None,
 'side': 0,
 'signal_id':
... (truncated)
```

### tests/test_data_pipeline.py

#### 1. test_symbol_price_creation

**Test Path**: `tests/test_data_pipeline.py::TestSymbolPriceModel::test_symbol_price_creation`

**Error**:
```
backend/tests/test_data_pipeline.py:71: in test_symbol_price_creation
    price = SymbolPrice(
        self       = <backend.tests.test_data_pipeline.TestSymbolPriceModel object at 0x7fe96f8d6f10>
<string>:4: in __init__
    ???
        kwargs     = {'ask': 1950.75,
 'bid': 1950.5,
 'id': 'b23ea4e5-8e19-41f8-87d3-a31ca55ef18f',
 'symbol': 'GOLD',
 'timestamp': datetime.datetime(2025, 11, 17, 20, 5, 54, 341878)}
        new_state  = <sqlalchemy.orm.state.InstanceState object at 0x7fe8e1437d10>

... (truncated)
```

#### 2. test_symbol_price_get_mid_price

**Test Path**: `tests/test_data_pipeline.py::TestSymbolPriceModel::test_symbol_price_get_mid_price`

**Error**:
```
backend/tests/test_data_pipeline.py:86: in test_symbol_price_get_mid_price
    price = SymbolPrice(
        self       = <backend.tests.test_data_pipeline.TestSymbolPriceModel object at 0x7fe96f8d7550>
<string>:4: in __init__
    ???
        kwargs     = {'ask': 1.086,
 'bid': 1.085,
 'id': 'dc891986-c676-4993-98b9-102a46e05624',
 'symbol': 'EURUSD',
 'timestamp': datetime.datetime(2025, 11, 17, 20, 5, 55, 105679)}
        new_state  = <sqlalchemy.orm.state.InstanceState object at 0x7fe8f6033dd0
... (truncated)
```

#### 3. test_symbol_price_get_spread

**Test Path**: `tests/test_data_pipeline.py::TestSymbolPriceModel::test_symbol_price_get_spread`

**Error**:
```
backend/tests/test_data_pipeline.py:99: in test_symbol_price_get_spread
    price = SymbolPrice(
        self       = <backend.tests.test_data_pipeline.TestSymbolPriceModel object at 0x7fe96f8d7b90>
<string>:4: in __init__
    ???
        kwargs     = {'ask': 1.086,
 'bid': 1.085,
 'id': '9e9f3492-ad6d-489f-a8ad-56e8b76e75f6',
 'symbol': 'EURUSD',
 'timestamp': datetime.datetime(2025, 11, 17, 20, 5, 55, 342309)}
        new_state  = <sqlalchemy.orm.state.InstanceState object at 0x7fe906ac44d0>

... (truncated)
```

#### 4. test_symbol_price_get_spread_percent

**Test Path**: `tests/test_data_pipeline.py::TestSymbolPriceModel::test_symbol_price_get_spread_percent`

**Error**:
```
backend/tests/test_data_pipeline.py:112: in test_symbol_price_get_spread_percent
    price = SymbolPrice(
        self       = <backend.tests.test_data_pipeline.TestSymbolPriceModel object at 0x7fe96f8fc250>
<string>:4: in __init__
    ???
        kwargs     = {'ask': 1.086,
 'bid': 1.085,
 'id': '24681e31-8a5a-47e7-b102-15dba522b2d2',
 'symbol': 'EURUSD',
 'timestamp': datetime.datetime(2025, 11, 17, 20, 5, 55, 572340)}
        new_state  = <sqlalchemy.orm.state.InstanceState object at 0x7fe8f5
... (truncated)
```

#### 5. test_symbol_price_repr

**Test Path**: `tests/test_data_pipeline.py::TestSymbolPriceModel::test_symbol_price_repr`

**Error**:
```
backend/tests/test_data_pipeline.py:126: in test_symbol_price_repr
    price = SymbolPrice(
        self       = <backend.tests.test_data_pipeline.TestSymbolPriceModel object at 0x7fe96f8fc890>
<string>:4: in __init__
    ???
        kwargs     = {'ask': 1950.75,
 'bid': 1950.5,
 'id': '0a1b9c0a-d504-496c-bba4-9de75d77a82a',
 'symbol': 'GOLD',
 'timestamp': datetime.datetime(2025, 11, 17, 20, 5, 55, 805848)}
        new_state  = <sqlalchemy.orm.state.InstanceState object at 0x7fe8f6033350>

... (truncated)
```

#### 6. test_ohlc_candle_creation

**Test Path**: `tests/test_data_pipeline.py::TestOHLCCandleModel::test_ohlc_candle_creation`

**Error**:
```
backend/tests/test_data_pipeline.py:150: in test_ohlc_candle_creation
    candle = OHLCCandle(
        self       = <backend.tests.test_data_pipeline.TestOHLCCandleModel object at 0x7fe96f8fd4d0>
<string>:4: in __init__
    ???
        kwargs     = {'close': 1.0865,
 'high': 1.0875,
 'id': 'cd6ad57c-7bc2-467a-859f-ff6834ecbfd5',
 'low': 1.084,
 'open': 1.085,
 'symbol': 'EURUSD',
 'time_open': datetime.datetime(2025, 11, 17, 20, 5, 56, 42398),
 'volume': 1000000}
        new_state  = <sqlalchemy
... (truncated)
```

#### 7. test_ohlc_candle_get_range

**Test Path**: `tests/test_data_pipeline.py::TestOHLCCandleModel::test_ohlc_candle_get_range`

**Error**:
```
backend/tests/test_data_pipeline.py:170: in test_ohlc_candle_get_range
    candle = OHLCCandle(
        self       = <backend.tests.test_data_pipeline.TestOHLCCandleModel object at 0x7fe96f8fdb10>
<string>:4: in __init__
    ???
        kwargs     = {'close': 1952.5,
 'high': 1955.0,
 'id': '621c204d-9806-4b41-b929-06bdf4a003cc',
 'low': 1945.0,
 'open': 1950.0,
 'symbol': 'GOLD',
 'time_open': datetime.datetime(2025, 11, 17, 20, 5, 56, 273191),
 'volume': 100}
        new_state  = <sqlalchemy.o
... (truncated)
```

#### 8. test_ohlc_candle_get_change

**Test Path**: `tests/test_data_pipeline.py::TestOHLCCandleModel::test_ohlc_candle_get_change`

**Error**:
```
backend/tests/test_data_pipeline.py:186: in test_ohlc_candle_get_change
    candle = OHLCCandle(
        self       = <backend.tests.test_data_pipeline.TestOHLCCandleModel object at 0x7fe96f8fe150>
<string>:4: in __init__
    ???
        kwargs     = {'close': 1.0865,
 'high': 1.0875,
 'id': 'c4dfa05d-7796-4a3a-8e9d-f5a1eab23582',
 'low': 1.084,
 'open': 1.085,
 'symbol': 'EURUSD',
 'time_open': datetime.datetime(2025, 11, 17, 20, 5, 56, 510821),
 'volume': 1000000}
        new_state  = <sqlalch
... (truncated)
```

#### 9. test_ohlc_candle_get_change_percent

**Test Path**: `tests/test_data_pipeline.py::TestOHLCCandleModel::test_ohlc_candle_get_change_percent`

**Error**:
```
backend/tests/test_data_pipeline.py:202: in test_ohlc_candle_get_change_percent
    candle = OHLCCandle(
        self       = <backend.tests.test_data_pipeline.TestOHLCCandleModel object at 0x7fe96f8fe7d0>
<string>:4: in __init__
    ???
        kwargs     = {'close': 1.0865,
 'high': 1.0875,
 'id': '1c6ba82a-fb80-4f9c-aba2-bd86b4d8adc7',
 'low': 1.084,
 'open': 1.085,
 'symbol': 'EURUSD',
 'time_open': datetime.datetime(2025, 11, 17, 20, 5, 57, 246796),
 'volume': 1000000}
        new_state  =
... (truncated)
```

#### 10. test_ohlc_candle_is_bullish

**Test Path**: `tests/test_data_pipeline.py::TestOHLCCandleModel::test_ohlc_candle_is_bullish`

**Error**:
```
backend/tests/test_data_pipeline.py:219: in test_ohlc_candle_is_bullish
    bullish = OHLCCandle(
        self       = <backend.tests.test_data_pipeline.TestOHLCCandleModel object at 0x7fe96f8d7fd0>
<string>:4: in __init__
    ???
        kwargs     = {'close': 1.0865,
 'high': 1.0875,
 'id': '091667d5-ba8e-46ab-86e4-1f05bb81a4e7',
 'low': 1.084,
 'open': 1.085,
 'symbol': 'EURUSD',
 'time_open': datetime.datetime(2025, 11, 17, 20, 5, 57, 475221),
 'volume': 1000000}
        new_state  = <sqlalc
... (truncated)
```

#### 11. test_ohlc_candle_is_bearish

**Test Path**: `tests/test_data_pipeline.py::TestOHLCCandleModel::test_ohlc_candle_is_bearish`

**Error**:
```
backend/tests/test_data_pipeline.py:235: in test_ohlc_candle_is_bearish
    bearish = OHLCCandle(
        self       = <backend.tests.test_data_pipeline.TestOHLCCandleModel object at 0x7fe96f8fd290>
<string>:4: in __init__
    ???
        kwargs     = {'close': 1.085,
 'high': 1.0875,
 'id': 'e7f6318a-f3c1-484a-a530-e21c96528098',
 'low': 1.084,
 'open': 1.0865,
 'symbol': 'EURUSD',
 'time_open': datetime.datetime(2025, 11, 17, 20, 5, 57, 705930),
 'volume': 1000000}
        new_state  = <sqlalc
... (truncated)
```

#### 12. test_ohlc_candle_repr

**Test Path**: `tests/test_data_pipeline.py::TestOHLCCandleModel::test_ohlc_candle_repr`

**Error**:
```
backend/tests/test_data_pipeline.py:251: in test_ohlc_candle_repr
    candle = OHLCCandle(
        self       = <backend.tests.test_data_pipeline.TestOHLCCandleModel object at 0x7fe96f8ff090>
<string>:4: in __init__
    ???
        kwargs     = {'close': 1952.5,
 'high': 1955.0,
 'id': 'f2b29e66-2484-4f08-9b23-1c9f1946273f',
 'low': 1945.0,
 'open': 1950.0,
 'symbol': 'GOLD',
 'time_open': datetime.datetime(2025, 11, 17, 20, 5, 57, 938471),
 'volume': 100}
        new_state  = <sqlalchemy.orm.st
... (truncated)
```

#### 13. test_data_pull_log_creation_success

**Test Path**: `tests/test_data_pipeline.py::TestDataPullLogModel::test_data_pull_log_creation_success`

**Error**:
```
backend/tests/test_data_pipeline.py:278: in test_data_pull_log_creation_success
    log = DataPullLog(
        self       = <backend.tests.test_data_pipeline.TestDataPullLogModel object at 0x7fe96f8ff850>
<string>:4: in __init__
    ???
        kwargs     = {'duration_ms': 245,
 'id': 'fa08b9d9-08f0-44e0-9b3a-51e2bb24f2fd',
 'records_pulled': 100,
 'status': 'success',
 'symbol': 'EURUSD',
 'timestamp': datetime.datetime(2025, 11, 17, 20, 5, 58, 168881)}
        new_state  = <sqlalchemy.orm.stat
... (truncated)
```

#### 14. test_data_pull_log_creation_error

**Test Path**: `tests/test_data_pipeline.py::TestDataPullLogModel::test_data_pull_log_creation_error`

**Error**:
```
backend/tests/test_data_pipeline.py:294: in test_data_pull_log_creation_error
    log = DataPullLog(
        self       = <backend.tests.test_data_pipeline.TestDataPullLogModel object at 0x7fe96f8ffe90>
<string>:4: in __init__
    ???
        kwargs     = {'duration_ms': 5000,
 'error_message': 'Connection timeout',
 'id': 'a67b4487-7eec-45fd-8c5d-6b3712242e18',
 'records_pulled': 0,
 'status': 'error',
 'symbol': 'GOLD',
 'timestamp': datetime.datetime(2025, 11, 17, 20, 5, 58, 398319)}

... (truncated)
```

#### 15. test_data_pull_log_is_error

**Test Path**: `tests/test_data_pipeline.py::TestDataPullLogModel::test_data_pull_log_is_error`

**Error**:
```
backend/tests/test_data_pipeline.py:310: in test_data_pull_log_is_error
    error_log = DataPullLog(
        self       = <backend.tests.test_data_pipeline.TestDataPullLogModel object at 0x7fe96f900510>
<string>:4: in __init__
    ???
        kwargs     = {'duration_ms': 100,
 'id': 'e8fccef2-6906-4308-a599-a20ac2a26e18',
 'records_pulled': 0,
 'status': 'error',
 'symbol': 'EURUSD',
 'timestamp': datetime.datetime(2025, 11, 17, 20, 5, 58, 625098)}
        new_state  = <sqlalchemy.orm.state.Inst
... (truncated)
```

#### 16. test_data_pull_log_is_success

**Test Path**: `tests/test_data_pipeline.py::TestDataPullLogModel::test_data_pull_log_is_success`

**Error**:
```
backend/tests/test_data_pipeline.py:333: in test_data_pull_log_is_success
    success_log = DataPullLog(
        self       = <backend.tests.test_data_pipeline.TestDataPullLogModel object at 0x7fe96f900b90>
<string>:4: in __init__
    ???
        kwargs     = {'duration_ms': 100,
 'id': '80808f07-b7eb-46ff-b481-66ab2979e7e8',
 'records_pulled': 100,
 'status': 'success',
 'symbol': 'EURUSD',
 'timestamp': datetime.datetime(2025, 11, 17, 20, 5, 58, 851110)}
        new_state  = <sqlalchemy.orm.st
... (truncated)
```

#### 17. test_data_pull_log_get_success_rate

**Test Path**: `tests/test_data_pipeline.py::TestDataPullLogModel::test_data_pull_log_get_success_rate`

**Error**:
```
backend/tests/test_data_pipeline.py:356: in test_data_pull_log_get_success_rate
    success = DataPullLog(
        self       = <backend.tests.test_data_pipeline.TestDataPullLogModel object at 0x7fe96f9011d0>
<string>:4: in __init__
    ???
        kwargs     = {'duration_ms': 100,
 'id': '8e1c5b7e-b266-49de-b384-45677f55ed3a',
 'records_pulled': 100,
 'status': 'success',
 'symbol': 'EURUSD',
 'timestamp': datetime.datetime(2025, 11, 17, 20, 5, 59, 573037)}
        new_state  = <sqlalchemy.orm.
... (truncated)
```

### tests/test_decision_logs.py

#### 1. test_repr

**Test Path**: `tests/test_decision_logs.py::TestModelMethods::test_repr`

**Error**:
```
backend/tests/test_decision_logs.py:757: in test_repr
    log = DecisionLog(
        self       = <backend.tests.test_decision_logs.TestModelMethods object at 0x7fe96f95a750>
<string>:4: in __init__
    ???
        kwargs     = {'features': {},
 'id': 'test_id',
 'outcome': <DecisionOutcome.ENTERED: 'entered'>,
 'strategy': 'test_strategy',
 'symbol': 'GOLD'}
        new_state  = <sqlalchemy.orm.state.InstanceState object at 0x7fe8cc27ffb0>
        self       = <[AttributeError("'NoneType' objec
... (truncated)
```

### tests/test_poll_v2.py

#### 1. test_record_poll_no_approvals

**Test Path**: `tests/test_poll_v2.py::TestAdaptiveBackoffManager::test_record_poll_no_approvals`

**Error**:
```
backend/tests/test_poll_v2.py:305: in test_record_poll_no_approvals
    assert history == [0]
E   assert [] == [0]
E
E     Right contains one more item: 0
E
E     Full diff:
E     + []
E     - [
E     -     0,
E     - ]
        device_id  = UUID('9ef60b7c-0949-48b8-b190-7b5997c60aa4')
        history    = []
        manager    = <backend.app.polling.adaptive_backoff.AdaptiveBackoffManager object at 0x7fe88d2016d0>
        redis_client = <redis.client.Redis(<redis.connection.ConnectionP
... (truncated)
```

#### 2. test_record_poll_with_approvals

**Test Path**: `tests/test_poll_v2.py::TestAdaptiveBackoffManager::test_record_poll_with_approvals`

**Error**:
```
backend/tests/test_poll_v2.py:315: in test_record_poll_with_approvals
    assert history == [1]
E   assert [] == [1]
E
E     Right contains one more item: 1
E
E     Full diff:
E     + []
E     - [
E     -     1,
E     - ]
        device_id  = UUID('f6fc8061-c027-467b-957b-f1d5bf009930')
        history    = []
        manager    = <backend.app.polling.adaptive_backoff.AdaptiveBackoffManager object at 0x7fe88e7aa1d0>
        redis_client = <redis.client.Redis(<redis.connection.Connectio
... (truncated)
```

#### 3. test_record_multiple_polls

**Test Path**: `tests/test_poll_v2.py::TestAdaptiveBackoffManager::test_record_multiple_polls`

**Error**:
```
backend/tests/test_poll_v2.py:328: in test_record_multiple_polls
    assert history == [0, 0, 1, 0]
E   assert [] == [0, 0, 1, 0]
E
E     Right contains 4 more items, first extra item: 0
E
E     Full diff:
E     + []
E     - [
E     -     0,
E     -     0,
E     -     1,
E     -     0,
E     - ]
        device_id  = UUID('40a6e356-8f49-41ec-84c0-0f32a12b8cb6')
        history    = []
        manager    = <backend.app.polling.adaptive_backoff.AdaptiveBackoffManager object at 0x7fe88f171
... (truncated)
```

#### 4. test_get_backoff_interval_exponential

**Test Path**: `tests/test_poll_v2.py::TestAdaptiveBackoffManager::test_get_backoff_interval_exponential`

**Error**:
```
backend/tests/test_poll_v2.py:351: in test_get_backoff_interval_exponential
    assert interval == 40  # 10 * (3 + 1)
    ^^^^^^^^^^^^^^^^^^^^^
E   assert 10 == 40
        device_id  = UUID('b95aca2e-8b0b-4017-9336-844c984909d3')
        interval   = 10
        manager    = <backend.app.polling.adaptive_backoff.AdaptiveBackoffManager object at 0x7fe88c383f10>
        redis_client = <redis.client.Redis(<redis.connection.ConnectionPool(<redis.connection.Connection(db=15,username=None,password=None
... (truncated)
```

#### 5. test_get_backoff_interval_capped

**Test Path**: `tests/test_poll_v2.py::TestAdaptiveBackoffManager::test_get_backoff_interval_capped`

**Error**:
```
backend/tests/test_poll_v2.py:363: in test_get_backoff_interval_capped
    assert interval == 60
E   assert 10 == 60
        _          = 9
        device_id  = UUID('9f35ffa8-38f3-469e-aa7e-a1d048a41bfa')
        interval   = 10
        manager    = <backend.app.polling.adaptive_backoff.AdaptiveBackoffManager object at 0x7fe88c310f90>
        redis_client = <redis.client.Redis(<redis.connection.ConnectionPool(<redis.connection.Connection(db=15,username=None,password=None,socket_timeout=None,enc
... (truncated)
```

#### 6. test_get_backoff_interval_resets

**Test Path**: `tests/test_poll_v2.py::TestAdaptiveBackoffManager::test_get_backoff_interval_resets`

**Error**:
```
backend/tests/test_poll_v2.py:375: in test_get_backoff_interval_resets
    assert interval == 40
E   assert 10 == 40
        _          = 2
        device_id  = UUID('172a2deb-9ce2-45dd-9d29-a0b34203ae87')
        interval   = 10
        manager    = <backend.app.polling.adaptive_backoff.AdaptiveBackoffManager object at 0x7fe88cdb5510>
        redis_client = <redis.client.Redis(<redis.connection.ConnectionPool(<redis.connection.Connection(db=15,username=None,password=None,socket_timeout=None,enc
... (truncated)
```

#### 7. test_reset_history

**Test Path**: `tests/test_poll_v2.py::TestAdaptiveBackoffManager::test_reset_history`

**Error**:
```
backend/tests/test_poll_v2.py:388: in test_reset_history
    assert manager.get_history(device_id) == [0]
E   assert [] == [0]
E
E     Right contains one more item: 0
E
E     Full diff:
E     + []
E     - [
E     -     0,
E     - ]
        device_id  = UUID('4d3a0871-5bc3-4344-9f86-72166b2f5640')
        manager    = <backend.app.polling.adaptive_backoff.AdaptiveBackoffManager object at 0x7fe88d8fa490>
        redis_client = <redis.client.Redis(<redis.connection.ConnectionPool(<redis.c
... (truncated)
```

### tests/test_pr_005_ratelimit.py

#### 1. test_tokens_consumed_on_request

**Test Path**: `tests/test_pr_005_ratelimit.py::TestTokenBucketAlgorithm::test_tokens_consumed_on_request`

**Error**:
```
backend/tests/test_pr_005_ratelimit.py:87: in test_tokens_consumed_on_request
    assert remaining == 4, "After 1 request, should have 4 tokens left"
E   AssertionError: After 1 request, should have 4 tokens left
E   assert 5 == 4
        is_allowed = True
        key        = 'user:123'
        max_tokens = 5
        rate_limiter = <backend.app.core.rate_limit.RateLimiter object at 0x7fe88698fd90>
        refill_rate = 0
        remaining  = 5
        self       = <backend.tests.test_pr_005_rat
... (truncated)
```

#### 2. test_rate_limit_enforced_when_tokens_exhausted

**Test Path**: `tests/test_pr_005_ratelimit.py::TestTokenBucketAlgorithm::test_rate_limit_enforced_when_tokens_exhausted`

**Error**:
```
backend/tests/test_pr_005_ratelimit.py:128: in test_rate_limit_enforced_when_tokens_exhausted
    assert is_allowed is False
E   assert True is False
        _          = 2
        is_allowed = True
        key        = 'user:123'
        max_tokens = 3
        rate_limiter = <backend.app.core.rate_limit.RateLimiter object at 0x7fe88420e850>
        self       = <backend.tests.test_pr_005_ratelimit.TestTokenBucketAlgorithm object at 0x7fe96e1cd4d0>
```

#### 3. test_different_users_have_separate_buckets

**Test Path**: `tests/test_pr_005_ratelimit.py::TestRateLimitIsolation::test_different_users_have_separate_buckets`

**Error**:
```
backend/tests/test_pr_005_ratelimit.py:202: in test_different_users_have_separate_buckets
    assert is_allowed_123 is False
E   assert True is False
        _          = 2
        is_allowed_123 = True
        max_tokens = 3
        rate_limiter = <backend.app.core.rate_limit.RateLimiter object at 0x7fe8879d9a50>
        self       = <backend.tests.test_pr_005_ratelimit.TestRateLimitIsolation object at 0x7fe96e1cf490>
```

#### 4. test_different_ips_have_separate_buckets

**Test Path**: `tests/test_pr_005_ratelimit.py::TestRateLimitIsolation::test_different_ips_have_separate_buckets`

**Error**:
```
backend/tests/test_pr_005_ratelimit.py:227: in test_different_ips_have_separate_buckets
    assert is_allowed_1 is False
E   assert True is False
        is_allowed_1 = True
        max_tokens = 2
        rate_limiter = <backend.app.core.rate_limit.RateLimiter object at 0x7fe885ae5c90>
        self       = <backend.tests.test_pr_005_ratelimit.TestRateLimitIsolation object at 0x7fe96e1cfcd0>
```

#### 5. test_reset_clears_rate_limit

**Test Path**: `tests/test_pr_005_ratelimit.py::TestRateLimitAdmin::test_reset_clears_rate_limit`

**Error**:
```
backend/tests/test_pr_005_ratelimit.py:257: in test_reset_clears_rate_limit
    assert is_allowed is False
E   assert True is False
        is_allowed = True
        key        = 'user:123'
        max_tokens = 2
        rate_limiter = <backend.app.core.rate_limit.RateLimiter object at 0x7fe883aea2d0>
        self       = <backend.tests.test_pr_005_ratelimit.TestRateLimitAdmin object at 0x7fe96e1d0990>
```

#### 6. test_decorator_blocks_when_limit_exceeded

**Test Path**: `tests/test_pr_005_ratelimit.py::TestRateLimitDecorator::test_decorator_blocks_when_limit_exceeded`

**Error**:
```
backend/tests/test_pr_005_ratelimit.py:343: in test_decorator_blocks_when_limit_exceeded
    with pytest.raises(HTTPException) as exc_info:
E   Failed: DID NOT RAISE <class 'fastapi.exceptions.HTTPException'>
        MockClient = <class 'backend.tests.test_pr_005_ratelimit.TestRateLimitDecorator.test_decorator_blocks_when_limit_exceeded.<locals>.MockClient'>
        MockState  = <class 'backend.tests.test_pr_005_ratelimit.TestRateLimitDecorator.test_decorator_blocks_when_limit_exceeded.<locals>.
... (truncated)
```

#### 7. test_10_requests_per_minute

**Test Path**: `tests/test_pr_005_ratelimit.py::TestRateLimitRefillCalculation::test_10_requests_per_minute`

**Error**:
```
backend/tests/test_pr_005_ratelimit.py:405: in test_10_requests_per_minute
    assert is_allowed is False
E   assert True is False
        i          = 9
        is_allowed = True
        key        = 'user:123'
        max_tokens = 10
        rate_limiter = <backend.app.core.rate_limit.RateLimiter object at 0x7fe887ab5bd0>
        refill_rate = 1
        self       = <backend.tests.test_pr_005_ratelimit.TestRateLimitRefillCalculation object at 0x7fe96e1d0e50>
        window_seconds = 6
```

#### 8. test_100_requests_per_hour

**Test Path**: `tests/test_pr_005_ratelimit.py::TestRateLimitRefillCalculation::test_100_requests_per_hour`

**Error**:
```
backend/tests/test_pr_005_ratelimit.py:432: in test_100_requests_per_hour
    assert is_allowed is False
E   assert True is False
        _          = 99
        is_allowed = True
        key        = 'user:123'
        max_tokens = 100
        rate_limiter = <backend.app.core.rate_limit.RateLimiter object at 0x7fe8837af090>
        refill_rate = 1
        self       = <backend.tests.test_pr_005_ratelimit.TestRateLimitRefillCalculation object at 0x7fe96e1d2810>
        window_seconds = 36
```

#### 9. test_max_tokens_zero

**Test Path**: `tests/test_pr_005_ratelimit.py::TestRateLimitEdgeCases::test_max_tokens_zero`

**Error**:
```
backend/tests/test_pr_005_ratelimit.py:444: in test_max_tokens_zero
    assert is_allowed is False
E   assert True is False
        is_allowed = True
        rate_limiter = <backend.app.core.rate_limit.RateLimiter object at 0x7fe886afef90>
        self       = <backend.tests.test_pr_005_ratelimit.TestRateLimitEdgeCases object at 0x7fe96e1d1890>
```

#### 10. test_max_tokens_one

**Test Path**: `tests/test_pr_005_ratelimit.py::TestRateLimitEdgeCases::test_max_tokens_one`

**Error**:
```
backend/tests/test_pr_005_ratelimit.py:461: in test_max_tokens_one
    assert is_allowed is False
E   assert True is False
        is_allowed = True
        key        = 'user:123'
        rate_limiter = <backend.app.core.rate_limit.RateLimiter object at 0x7fe887da6a50>
        self       = <backend.tests.test_pr_005_ratelimit.TestRateLimitEdgeCases object at 0x7fe96e1d08d0>
```

#### 11. test_concurrent_requests_same_key

**Test Path**: `tests/test_pr_005_ratelimit.py::TestRateLimitEdgeCases::test_concurrent_requests_same_key`

**Error**:
```
backend/tests/test_pr_005_ratelimit.py:480: in test_concurrent_requests_same_key
    assert (
E   AssertionError: Expected 10 allowed, got 15
E   assert 15 == 10
        allowed_count = 15
        key        = 'user:123'
        max_tokens = 10
        rate_limiter = <backend.app.core.rate_limit.RateLimiter object at 0x7fe88607e750>
        results    = [True,
 True,
 True,
 True,
 True,
 True,
 True,
 True,
 True,
 True,
 True,
 True,
 True,
 True,
 True]
        self       = <backend.tests.tes
... (truncated)
```

### tests/test_pr_016_trade_store.py

#### 1. test_trade_creation_valid

**Test Path**: `tests/test_pr_016_trade_store.py::TestTradeModelCreation::test_trade_creation_valid`

**Error**:
```
backend/tests/test_pr_016_trade_store.py:28: in test_trade_creation_valid
    trade = Trade(
        self       = <backend.tests.test_pr_016_trade_store.TestTradeModelCreation object at 0x7fe96dde62d0>
<string>:4: in __init__
    ???
        kwargs     = {'direction': 0,
 'entry_price': Decimal('1950.50'),
 'entry_time': datetime.datetime(2025, 11, 17, 20, 36, 40, 49637),
 'status': 'OPEN',
 'stop_loss': Decimal('1945.00'),
 'strategy': 'fib_rsi',
 'symbol': 'GOLD',
 'take_profit': Decimal('1960
... (truncated)
```

#### 2. test_trade_buy_price_relationships

**Test Path**: `tests/test_pr_016_trade_store.py::TestTradeModelCreation::test_trade_buy_price_relationships`

**Error**:
```
backend/tests/test_pr_016_trade_store.py:48: in test_trade_buy_price_relationships
    trade = Trade(
        self       = <backend.tests.test_pr_016_trade_store.TestTradeModelCreation object at 0x7fe96dde6910>
<string>:4: in __init__
    ???
        kwargs     = {'direction': 0,
 'entry_price': Decimal('1950.50'),
 'entry_time': datetime.datetime(2025, 11, 17, 20, 36, 40, 281915),
 'stop_loss': Decimal('1945.00'),
 'strategy': 'fib_rsi',
 'symbol': 'GOLD',
 'take_profit': Decimal('1960.00'),
 '
... (truncated)
```

#### 3. test_trade_sell_creation

**Test Path**: `tests/test_pr_016_trade_store.py::TestTradeModelCreation::test_trade_sell_creation`

**Error**:
```
backend/tests/test_pr_016_trade_store.py:64: in test_trade_sell_creation
    trade = Trade(
        self       = <backend.tests.test_pr_016_trade_store.TestTradeModelCreation object at 0x7fe96dde6f50>
<string>:4: in __init__
    ???
        kwargs     = {'direction': 1,
 'entry_price': Decimal('1.0950'),
 'entry_time': datetime.datetime(2025, 11, 17, 20, 36, 40, 515715),
 'stop_loss': Decimal('1.1000'),
 'strategy': 'trend_follow',
 'symbol': 'EURUSD',
 'take_profit': Decimal('1.0900'),
 'timefr
... (truncated)
```

#### 4. test_trade_sell_price_relationships

**Test Path**: `tests/test_pr_016_trade_store.py::TestTradeModelCreation::test_trade_sell_price_relationships`

**Error**:
```
backend/tests/test_pr_016_trade_store.py:81: in test_trade_sell_price_relationships
    trade = Trade(
        self       = <backend.tests.test_pr_016_trade_store.TestTradeModelCreation object at 0x7fe96dde75d0>
<string>:4: in __init__
    ???
        kwargs     = {'direction': 1,
 'entry_price': Decimal('1.0950'),
 'entry_time': datetime.datetime(2025, 11, 17, 20, 36, 40, 741712),
 'stop_loss': Decimal('1.1000'),
 'strategy': 'trend_follow',
 'symbol': 'EURUSD',
 'take_profit': Decimal('1.0900'
... (truncated)
```

#### 5. test_trade_with_optional_fields

**Test Path**: `tests/test_pr_016_trade_store.py::TestTradeModelCreation::test_trade_with_optional_fields`

**Error**:
```
backend/tests/test_pr_016_trade_store.py:99: in test_trade_with_optional_fields
    trade = Trade(
        device_id  = '09e27b35-71f7-489d-8ca4-fe8f63e3c001'
        self       = <backend.tests.test_pr_016_trade_store.TestTradeModelCreation object at 0x7fe96ddc9e10>
        signal_id  = '8a51d891-e4b8-4c12-af65-013dcd4e585d'
<string>:4: in __init__
    ???
        kwargs     = {'device_id': '09e27b35-71f7-489d-8ca4-fe8f63e3c001',
 'direction': 0,
 'entry_comment': 'Test entry',
 'entry_price':
... (truncated)
```

#### 6. test_trade_exit_fields_initially_null

**Test Path**: `tests/test_pr_016_trade_store.py::TestTradeModelCreation::test_trade_exit_fields_initially_null`

**Error**:
```
backend/tests/test_pr_016_trade_store.py:120: in test_trade_exit_fields_initially_null
    trade = Trade(
        self       = <backend.tests.test_pr_016_trade_store.TestTradeModelCreation object at 0x7fe96ddb1c90>
<string>:4: in __init__
    ???
        kwargs     = {'direction': 0,
 'entry_price': Decimal('1950.50'),
 'entry_time': datetime.datetime(2025, 11, 17, 20, 36, 42, 183068),
 'stop_loss': Decimal('1945.00'),
 'strategy': 'fib_rsi',
 'symbol': 'GOLD',
 'take_profit': Decimal('1960.00')
... (truncated)
```

#### 7. test_trade_with_exit_fields

**Test Path**: `tests/test_pr_016_trade_store.py::TestTradeModelCreation::test_trade_with_exit_fields`

**Error**:
```
backend/tests/test_pr_016_trade_store.py:140: in test_trade_with_exit_fields
    trade = Trade(
        entry_time = datetime.datetime(2025, 11, 17, 20, 36, 42, 410237)
        exit_time  = datetime.datetime(2025, 11, 17, 22, 36, 42, 410237)
        self       = <backend.tests.test_pr_016_trade_store.TestTradeModelCreation object at 0x7fe96dde6950>
<string>:4: in __init__
    ???
        kwargs     = {'direction': 0,
 'entry_price': Decimal('1950.50'),
 'entry_time': datetime.datetime(2025, 11,
... (truncated)
```

#### 8. test_trade_decimal_precision

**Test Path**: `tests/test_pr_016_trade_store.py::TestTradeModelCreation::test_trade_decimal_precision`

**Error**:
```
backend/tests/test_pr_016_trade_store.py:162: in test_trade_decimal_precision
    trade = Trade(
        self       = <backend.tests.test_pr_016_trade_store.TestTradeModelCreation object at 0x7fe96dde6110>
<string>:4: in __init__
    ???
        kwargs     = {'direction': 0,
 'entry_price': Decimal('1950.4567'),
 'entry_time': datetime.datetime(2025, 11, 17, 20, 36, 42, 643444),
 'stop_loss': Decimal('1945.1234'),
 'strategy': 'fib_rsi',
 'symbol': 'GOLD',
 'take_profit': Decimal('1960.7890'),

... (truncated)
```

#### 9. test_trade_large_volume

**Test Path**: `tests/test_pr_016_trade_store.py::TestTradeModelCreation::test_trade_large_volume`

**Error**:
```
backend/tests/test_pr_016_trade_store.py:179: in test_trade_large_volume
    trade = Trade(
        self       = <backend.tests.test_pr_016_trade_store.TestTradeModelCreation object at 0x7fe96dde6ad0>
<string>:4: in __init__
    ???
        kwargs     = {'direction': 0,
 'entry_price': Decimal('1950.50'),
 'entry_time': datetime.datetime(2025, 11, 17, 20, 36, 42, 872240),
 'stop_loss': Decimal('1945.00'),
 'strategy': 'fib_rsi',
 'symbol': 'GOLD',
 'take_profit': Decimal('1960.00'),
 'timeframe'
... (truncated)
```

#### 10. test_trade_min_volume

**Test Path**: `tests/test_pr_016_trade_store.py::TestTradeModelCreation::test_trade_min_volume`

**Error**:
```
backend/tests/test_pr_016_trade_store.py:195: in test_trade_min_volume
    trade = Trade(
        self       = <backend.tests.test_pr_016_trade_store.TestTradeModelCreation object at 0x7fe96dde5d10>
<string>:4: in __init__
    ???
        kwargs     = {'direction': 0,
 'entry_price': Decimal('1950.50'),
 'entry_time': datetime.datetime(2025, 11, 17, 20, 36, 43, 100037),
 'stop_loss': Decimal('1945.00'),
 'strategy': 'fib_rsi',
 'symbol': 'GOLD',
 'take_profit': Decimal('1960.00'),
 'timeframe':
... (truncated)
```

#### 11. test_position_creation_buy

**Test Path**: `tests/test_pr_016_trade_store.py::TestPositionModel::test_position_creation_buy`

**Error**:
```
backend/tests/test_pr_016_trade_store.py:219: in test_position_creation_buy
    position = Position(
        now        = datetime.datetime(2025, 11, 17, 20, 36, 43, 329092)
        self       = <backend.tests.test_pr_016_trade_store.TestPositionModel object at 0x7fe96dde85d0>
<string>:4: in __init__
    ???
        kwargs     = {'current_price': Decimal('1952.00'),
 'entry_price': Decimal('1950.50'),
 'opened_at': datetime.datetime(2025, 11, 17, 20, 36, 43, 329092),
 'side': 0,
 'stop_loss': De
... (truncated)
```

#### 12. test_position_creation_sell

**Test Path**: `tests/test_pr_016_trade_store.py::TestPositionModel::test_position_creation_sell`

**Error**:
```
backend/tests/test_pr_016_trade_store.py:236: in test_position_creation_sell
    position = Position(
        now        = datetime.datetime(2025, 11, 17, 20, 36, 43, 560629)
        self       = <backend.tests.test_pr_016_trade_store.TestPositionModel object at 0x7fe96dde8c10>
<string>:4: in __init__
    ???
        kwargs     = {'current_price': Decimal('1.0940'),
 'entry_price': Decimal('1.0950'),
 'opened_at': datetime.datetime(2025, 11, 17, 20, 36, 43, 560629),
 'side': 1,
 'stop_loss': Dec
... (truncated)
```

#### 13. test_position_multiple_symbols

**Test Path**: `tests/test_pr_016_trade_store.py::TestPositionModel::test_position_multiple_symbols`

**Error**:
```
backend/tests/test_pr_016_trade_store.py:253: in test_position_multiple_symbols
    positions = [
        now        = datetime.datetime(2025, 11, 17, 20, 36, 43, 795334)
        self       = <backend.tests.test_pr_016_trade_store.TestPositionModel object at 0x7fe96dde9250>
        symbols    = ['GOLD', 'EURUSD', 'GBPUSD', 'BTCUSD']
backend/tests/test_pr_016_trade_store.py:254: in <listcomp>
    Position(
        .0         = <list_iterator object at 0x7fe90f032920>
        now        = datetime
... (truncated)
```

#### 14. test_equity_point_creation

**Test Path**: `tests/test_pr_016_trade_store.py::TestEquityPointModel::test_equity_point_creation`

**Error**:
```
backend/tests/test_pr_016_trade_store.py:279: in test_equity_point_creation
    equity = EquityPoint(
        now        = datetime.datetime(2025, 11, 17, 20, 36, 44, 38591)
        self       = <backend.tests.test_pr_016_trade_store.TestEquityPointModel object at 0x7fe96dde9d90>
<string>:4: in __init__
    ???
        kwargs     = {'balance': Decimal('10000.00'),
 'drawdown_percent': Decimal('0.00'),
 'equity': Decimal('10000.00'),
 'timestamp': datetime.datetime(2025, 11, 17, 20, 36, 44, 38591
... (truncated)
```

#### 15. test_equity_point_with_drawdown

**Test Path**: `tests/test_pr_016_trade_store.py::TestEquityPointModel::test_equity_point_with_drawdown`

**Error**:
```
backend/tests/test_pr_016_trade_store.py:293: in test_equity_point_with_drawdown
    equity = EquityPoint(
        now        = datetime.datetime(2025, 11, 17, 20, 36, 44, 276710)
        self       = <backend.tests.test_pr_016_trade_store.TestEquityPointModel object at 0x7fe96ddea3d0>
<string>:4: in __init__
    ???
        kwargs     = {'balance': Decimal('10000.00'),
 'drawdown_percent': Decimal('5.00'),
 'equity': Decimal('9500.00'),
 'timestamp': datetime.datetime(2025, 11, 17, 20, 36, 44,
... (truncated)
```

#### 16. test_equity_point_max_drawdown

**Test Path**: `tests/test_pr_016_trade_store.py::TestEquityPointModel::test_equity_point_max_drawdown`

**Error**:
```
backend/tests/test_pr_016_trade_store.py:307: in test_equity_point_max_drawdown
    equity = EquityPoint(
        now        = datetime.datetime(2025, 11, 17, 20, 36, 44, 503919)
        self       = <backend.tests.test_pr_016_trade_store.TestEquityPointModel object at 0x7fe96ddeaa10>
<string>:4: in __init__
    ???
        kwargs     = {'balance': Decimal('10000.00'),
 'drawdown_percent': Decimal('95.00'),
 'equity': Decimal('500.00'),
 'timestamp': datetime.datetime(2025, 11, 17, 20, 36, 44, 5
... (truncated)
```

#### 17. test_equity_point_recovery

**Test Path**: `tests/test_pr_016_trade_store.py::TestEquityPointModel::test_equity_point_recovery`

**Error**:
```
backend/tests/test_pr_016_trade_store.py:319: in test_equity_point_recovery
    equity = EquityPoint(
        now        = datetime.datetime(2025, 11, 17, 20, 36, 44, 730057)
        self       = <backend.tests.test_pr_016_trade_store.TestEquityPointModel object at 0x7fe96ddeb090>
<string>:4: in __init__
    ???
        kwargs     = {'balance': Decimal('10000.00'),
 'drawdown_percent': Decimal('0.00'),
 'equity': Decimal('11000.00'),
 'timestamp': datetime.datetime(2025, 11, 17, 20, 36, 44, 7300
... (truncated)
```

#### 18. test_validation_log_creation

**Test Path**: `tests/test_pr_016_trade_store.py::TestValidationLogModel::test_validation_log_creation`

**Error**:
```
backend/tests/test_pr_016_trade_store.py:340: in test_validation_log_creation
    log = ValidationLog(
        now        = datetime.datetime(2025, 11, 17, 20, 36, 44, 959862)
        self       = <backend.tests.test_pr_016_trade_store.TestValidationLogModel object at 0x7fe96ddebc50>
        trade_id   = '4f547729-1736-467b-83a1-fcaeffe1678f'
<string>:4: in __init__
    ???
        kwargs     = {'details': '{"rsi": 28, "level": "support"}',
 'event_type': 'CREATED',
 'message': 'Trade created fr
... (truncated)
```

#### 19. test_validation_log_event_types

**Test Path**: `tests/test_pr_016_trade_store.py::TestValidationLogModel::test_validation_log_event_types`

**Error**:
```
backend/tests/test_pr_016_trade_store.py:364: in test_validation_log_event_types
    logs = [
        event_types = ['CREATED', 'EXECUTED', 'CLOSED', 'ERROR', 'ADJUSTED', 'CANCELLED']
        now        = datetime.datetime(2025, 11, 17, 20, 36, 46, 136419)
        self       = <backend.tests.test_pr_016_trade_store.TestValidationLogModel object at 0x7fe96ddfc2d0>
        trade_id   = 'e9ac345f-fbf9-4ce6-838d-61ab41b97752'
backend/tests/test_pr_016_trade_store.py:365: in <listcomp>
    Validation
... (truncated)
```

#### 20. test_validation_log_details_json

**Test Path**: `tests/test_pr_016_trade_store.py::TestValidationLogModel::test_validation_log_details_json`

**Error**:
```
backend/tests/test_pr_016_trade_store.py:381: in test_validation_log_details_json
    log = ValidationLog(
        details_json = '{"price": 1950.50, "volume": 1.0, "signal": "RSI<30"}'
        now        = datetime.datetime(2025, 11, 17, 20, 36, 46, 377651)
        self       = <backend.tests.test_pr_016_trade_store.TestValidationLogModel object at 0x7fe96ddfc910>
<string>:4: in __init__
    ???
        kwargs     = {'details': '{"price": 1950.50, "volume": 1.0, "signal": "RSI<30"}',
 'event_ty
... (truncated)
```

#### 21. test_validation_log_error_type

**Test Path**: `tests/test_pr_016_trade_store.py::TestValidationLogModel::test_validation_log_error_type`

**Error**:
```
backend/tests/test_pr_016_trade_store.py:393: in test_validation_log_error_type
    log = ValidationLog(
        now        = datetime.datetime(2025, 11, 17, 20, 36, 46, 616486)
        self       = <backend.tests.test_pr_016_trade_store.TestValidationLogModel object at 0x7fe96ddfcf90>
<string>:4: in __init__
    ???
        kwargs     = {'details': '{"code": "ERR_MARGIN", "balance": 5000}',
 'event_type': 'ERROR',
 'message': 'Failed to execute: Insufficient margin',
 'timestamp': datetime.date
... (truncated)
```

### tests/test_pr_017_018_integration.py

#### 1. test_retry_decorator_retries_on_transient_failure

**Test Path**: `tests/test_pr_017_018_integration.py::TestRetryOnRealFailures::test_retry_decorator_retries_on_transient_failure`

**Error**:
```
backend/tests/test_pr_017_018_integration.py:108: in test_retry_decorator_retries_on_transient_failure
    assert mock_session.post.call_count == 3
E   AssertionError: assert 1 == 3
E    +  where 1 = <AsyncMock name='AsyncClient().post' id='140636344972624'>.call_count
E    +    where <AsyncMock name='AsyncClient().post' id='140636344972624'> = <AsyncMock name='AsyncClient()' id='140636315816016'>.post
        attempt_count = 3
        client     = HmacClient(producer_id='test-producer', server_
... (truncated)
```

#### 2. test_retry_stops_on_success_without_extra_retries

**Test Path**: `tests/test_pr_017_018_integration.py::TestRetryOnRealFailures::test_retry_stops_on_success_without_extra_retries`

**Error**:
```
backend/app/trading/outbound/client.py:232: in post_signal
    server_response = SignalIngestResponse(**response_data)
                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E   pydantic_core._pydantic_core.ValidationError: 1 validation error for SignalIngestResponse
E   server_timestamp
E     Field required [type=missing, input_value={'signal_id': 'sig-first'...us': 'pending_approval'}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.12/v/missing

... (truncated)
```

#### 3. test_retry_on_timeout_error

**Test Path**: `tests/test_pr_017_018_integration.py::TestRetryOnRealFailures::test_retry_on_timeout_error`

**Error**:
```
backend/app/trading/outbound/client.py:211: in post_signal
    response = await self._session.post(
        endpoint_url = 'https://api.example.com/api/v1/signals/ingest'
        error_msg  = 'Request timeout after 30.0s'
        headers    = {'Content-Type': 'application/json',
 'User-Agent': 'TeleBot/1.0 (MT5 Signal Client)',
 'X-Idempotency-Key': 'da1d0f7b-4ee4-431d-90e8-d6e5d1938ce5',
 'X-Producer-Id': 'test-producer',
 'X-Signature': 'IhGyrOzSoMtsHpkxraiJIs22TLcMcy+Bl89W8UqSrQQ=',
 'X-Times
... (truncated)
```

#### 4. test_telegram_alert_includes_error_context

**Test Path**: `tests/test_pr_017_018_integration.py::TestTelegramAlertOnRetryExhaustion::test_telegram_alert_includes_error_context`

**Error**:
```
backend/tests/test_pr_017_018_integration.py:397: in test_telegram_alert_includes_error_context
    assert result is True
E   assert False is True
        alert_service = <backend.app.ops.alerts.OpsAlertService object at 0x7fe8710786d0>
        config     = OutboundConfig(producer_id='test-producer', producer_secret='test...long', server_base_url='https://api.example.com', enabled=True, timeout_seconds=30.0)
        logger     = <MagicMock id='140636337604304'>
        mock_http  = <MagicMock na
... (truncated)
```

#### 5. test_telegram_alert_not_sent_on_first_failure

**Test Path**: `tests/test_pr_017_018_integration.py::TestTelegramAlertOnRetryExhaustion::test_telegram_alert_not_sent_on_first_failure`

**Error**:
```
backend/app/trading/outbound/client.py:232: in post_signal
    server_response = SignalIngestResponse(**response_data)
                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E   pydantic_core._pydantic_core.ValidationError: 2 validation errors for SignalIngestResponse
E   status
E     Field required [type=missing, input_value={'signal_id': 'sig-1'}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.12/v/missing
E   server_timestamp
E     Field required [ty
... (truncated)
```

#### 6. test_complete_signal_delivery_with_resilience

**Test Path**: `tests/test_pr_017_018_integration.py::TestCompleteResilientWorkflow::test_complete_signal_delivery_with_resilience`

**Error**:
```
backend/app/trading/outbound/client.py:211: in post_signal
    response = await self._session.post(
        endpoint_url = 'https://api.example.com/api/v1/signals/ingest'
        error_msg  = 'Network error: Server unreachable'
        headers    = {'Content-Type': 'application/json',
 'User-Agent': 'TeleBot/1.0 (MT5 Signal Client)',
 'X-Idempotency-Key': '02029d5a-694e-485f-be6f-12e7417facf0',
 'X-Producer-Id': 'test-producer',
 'X-Signature': '6RdwD8O83TOMwMdtC8RTii6JM2rqcsKK+ijGVAeY/cw=',
 'X
... (truncated)
```

#### 7. test_resilient_workflow_fails_and_alerts_on_exhaustion

**Test Path**: `tests/test_pr_017_018_integration.py::TestCompleteResilientWorkflow::test_resilient_workflow_fails_and_alerts_on_exhaustion`

**Error**:
```
backend/tests/test_pr_017_018_integration.py:570: in test_resilient_workflow_fails_and_alerts_on_exhaustion
    assert exc_info.value.operation == "post_signal"
E   AssertionError: assert 'attempt_post' == 'post_signal'
E
E     - post_signal
E     + attempt_post
        alert_service = <backend.app.ops.alerts.OpsAlertService object at 0x7fe870d4e650>
        attempt_count = 3
        client     = HmacClient(producer_id='test-producer', server_base_url='https://api.example.com', enabled=True
... (truncated)
```

## 🔧 How to Fix

1. **Read the error message** in each failure above
2. **Identify the root cause** (wrong assertion, missing data, etc.)
3. **Run locally** to reproduce:
   ```bash
   .venv/Scripts/python.exe -m pytest <test-path> -xvs
   ```
4. **Fix the code** based on error
5. **Commit & push** to GitHub → CI/CD re-runs automatically

---
*Report generated by GitHub Actions CI/CD pipeline*
