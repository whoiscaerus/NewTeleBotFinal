# MT5 Trading Integration - Quick Reference Guide

## 🚀 Quick Start (5 minutes)

### Basic Usage

```python
from backend.app.trading.mt5 import MT5SessionManager

# 1. Create manager
manager = MT5SessionManager(
    login="12345678",
    password="your_password",
    server="MetaQuotes-Demo",
    terminal_path="/opt/mt5"
)

# 2. Connect
await manager.connect()

# 3. Use
account = await manager.get_account_info()
price = await manager.get_price("EURUSD")

# 4. Disconnect
await manager.disconnect()
```

---

## 📚 API Reference

### MT5SessionManager

#### Connection Methods

```python
# Connect to MT5
await manager.connect()

# Check if connected
if manager.is_connected:
    print("Connected!")

# Disconnect gracefully
await manager.disconnect()

# Force reconnect
await manager.reconnect()
```

#### Account Methods

```python
# Get account information
account_info = await manager.get_account_info()
print(account_info.balance)
print(account_info.name)
print(account_info.equity)

# Get account leverage
leverage = await manager.get_leverage()

# Get account margins
used_margin = await manager.get_margin_used()
free_margin = await manager.get_margin_free()
```

#### Price Methods

```python
# Get current price
price = await manager.get_price("EURUSD")
print(f"Bid: {price.bid}, Ask: {price.ask}")

# Get multiple prices
prices = await manager.get_prices(["EURUSD", "GBPUSD", "USDJPY"])
for symbol, price in prices.items():
    print(f"{symbol}: {price.bid}")

# Get historical prices (OHLC)
candles = await manager.get_candles("EURUSD", timeframe=15)
# Returns list of OHLC data
```

---

## 🛡️ Error Handling

### Error Types

```python
from backend.app.trading.mt5.errors import (
    MT5InitError,              # Initialization failed
    MT5AuthError,              # Authentication failed
    MT5CircuitBreakerOpen,     # Service temporarily unavailable
    MT5TimeoutError,           # Operation timed out
    MT5DataError,              # Invalid data received
    MT5ConnectionError,        # Connection lost
    MT5ValidationError,        # Input validation failed
    MT5StateError,             # Invalid operation state
)
```

### Handling Each Error Type

```python
try:
    price = await manager.get_price("EURUSD")

except MT5InitError:
    # MT5 terminal not properly initialized
    logger.error("MT5 initialization failed")
    await try_reinitialize()

except MT5AuthError:
    # Credentials invalid
    logger.error("Authentication failed - check credentials")
    alert_admin()

except MT5CircuitBreakerOpen:
    # Too many failures - service protecting itself
    logger.warning("Circuit breaker open - service unavailable")
    queue_request_for_retry()

except MT5TimeoutError:
    # Operation took too long
    logger.warning("Operation timed out")
    retry_with_longer_timeout()

except MT5ConnectionError:
    # Connection lost
    logger.error("Connection lost")
    await manager.reconnect()

except MT5DataError:
    # Invalid data received
    logger.error(f"Data error: {e}")
    investigate_data()

except MT5ValidationError:
    # Input invalid
    logger.error(f"Validation error: {e}")
    # Fix input and retry

except MT5StateError:
    # Invalid operation state
    logger.error("Invalid state")
    # Ensure proper state before retrying
```

### Pattern: Automatic Retry

```python
from backend.app.trading.mt5 import MT5SessionManager
from backend.app.trading.mt5.errors import MT5ConnectionError
import asyncio

async def get_price_with_retry(manager, symbol, max_retries=3):
    """Get price with automatic retry."""
    for attempt in range(max_retries):
        try:
            return await manager.get_price(symbol)
        except MT5ConnectionError:
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(2 ** attempt)  # Exponential backoff
```

---

## 🔍 Health Monitoring

### Check Service Health

```python
from backend.app.trading.mt5 import probe

# Get health status
status = await probe(manager)

# Check individual components
if status.connection_ok:
    print("✓ Connected to MT5")
else:
    print("✗ Not connected")

if status.auth_ok:
    print("✓ Authenticated")
else:
    print("✗ Authentication failed")

if status.data_feed_ok:
    print("✓ Data feed active")
else:
    print("✗ Data feed inactive")

# Check latency
print(f"Latency: {status.latency_ms}ms")
```

### Pattern: Periodic Health Check

```python
import asyncio
from backend.app.trading.mt5 import probe

async def monitor_health(manager, interval=30):
    """Monitor health every interval seconds."""
    while True:
        try:
            status = await probe(manager)

            if not status.connection_ok:
                logger.warning("Connection lost - attempting recovery")
                await manager.reconnect()

            if not status.data_feed_ok:
                logger.warning("Data feed stalled")

            metrics.record('mt5.latency', status.latency_ms)

        except Exception as e:
            logger.error(f"Health check failed: {e}")

        await asyncio.sleep(interval)

# Usage
asyncio.create_task(monitor_health(manager))
```

---

## 🔄 Circuit Breaker Pattern

### Understanding Circuit Breaker

The circuit breaker protects your system from cascading failures:

```
┌──────────────────────────────────────────────┐
│              Circuit Breaker States           │
├──────────────────────────────────────────────┤
│                                              │
│  CLOSED (Normal Operation)                  │
│    ↓ (too many failures)                    │
│  OPEN (Rejecting All Requests)              │
│    ↓ (after delay)                          │
│  HALF_OPEN (Testing Recovery)               │
│    ├→ CLOSED (if recovery successful)       │
│    └→ OPEN (if recovery failed)             │
│                                              │
└──────────────────────────────────────────────┘
```

### State Details

```python
# CLOSED: Normal operation
# ✓ All requests allowed
# ✓ Failures counted
# ✓ After N failures → OPEN

# OPEN: Service protecting itself
# ✗ All requests rejected immediately
# ✗ MT5CircuitBreakerOpen raised
# ✗ Wait for timeout → HALF_OPEN

# HALF_OPEN: Testing recovery
# ≈ Limited requests allowed (1 per timeout)
# ≈ If success → CLOSED
# ≈ If failure → OPEN
```

### Configuration

```python
manager = MT5SessionManager(
    login="...",
    password="...",
    max_failures=3,           # Failures before OPEN (default: 3)
    backoff_base_seconds=60,  # Initial backoff (default: 60s)
    backoff_max_seconds=600,  # Max backoff (default: 600s)
)
```

---

## 📊 Logging & Debugging

### Structured Logging

```python
# All logging is structured JSON for easy parsing
# Example log output:
# {"level": "INFO", "event": "connected", "user_id": "123", "latency_ms": 45}
# {"level": "ERROR", "event": "connection_failed", "error": "timeout"}
```

### Enable Debug Logging

```python
import logging

# Enable debug logging for MT5 module
logger = logging.getLogger("backend.app.trading.mt5")
logger.setLevel(logging.DEBUG)

# Now you'll see detailed operations
```

### What Gets Logged

```
✓ Connection opened/closed
✓ Authentication attempts
✓ Price fetches
✓ Account updates
✓ All errors with full context
✓ Circuit breaker state changes
✓ Performance metrics
```

---

## ⚡ Performance Tips

### 1. Connection Reuse
```python
# ✓ GOOD: Reuse connection
manager = MT5SessionManager(...)
await manager.connect()

price1 = await manager.get_price("EURUSD")
price2 = await manager.get_price("GBPUSD")

await manager.disconnect()

# ✗ BAD: Create new connection for each operation
for symbol in symbols:
    m = MT5SessionManager(...)
    await m.connect()
    price = await m.get_price(symbol)
    await m.disconnect()
```

### 2. Batch Operations
```python
# ✓ GOOD: Batch requests
prices = await manager.get_prices(["EURUSD", "GBPUSD", "USDJPY"])

# ✗ BAD: Individual requests
for symbol in symbols:
    price = await manager.get_price(symbol)
```

### 3. Timeout Configuration
```python
# Set appropriate timeouts for your network
manager = MT5SessionManager(
    ...,
    connection_timeout=5,  # 5 seconds
    operation_timeout=10,  # 10 seconds
)
```

---

## 🔐 Security Notes

### Do's ✅
- ✅ Use environment variables for credentials
- ✅ Never log passwords
- ✅ Use HTTPS only
- ✅ Validate all inputs
- ✅ Keep credentials out of git

### Don'ts ❌
- ❌ Hardcode credentials in code
- ❌ Log sensitive data
- ❌ Expose error details to users
- ❌ Skip input validation
- ❌ Trust external data blindly

### Secure Configuration

```python
import os
from dotenv import load_dotenv

load_dotenv()

manager = MT5SessionManager(
    login=os.getenv("MT5_LOGIN"),      # From .env file
    password=os.getenv("MT5_PASSWORD"),
    server=os.getenv("MT5_SERVER"),
    terminal_path=os.getenv("MT5_PATH"),
)
```

---

## 🧪 Testing Your Code

### Unit Test Example

```python
import pytest
from unittest.mock import AsyncMock, patch
from backend.app.trading.mt5 import MT5SessionManager

@pytest.fixture
def manager():
    return MT5SessionManager(
        login="test",
        password="test",
        server="test"
    )

@pytest.mark.asyncio
async def test_get_price_success(manager):
    """Test successful price fetch."""
    with patch.object(manager, '_get_price') as mock:
        mock.return_value = MockPrice(bid=1.0500, ask=1.0502)

        price = await manager.get_price("EURUSD")

        assert price.bid == 1.0500
        assert price.ask == 1.0502

@pytest.mark.asyncio
async def test_get_price_connection_error(manager):
    """Test error handling."""
    with patch.object(manager, '_get_price') as mock:
        mock.side_effect = ConnectionError("Lost connection")

        with pytest.raises(MT5ConnectionError):
            await manager.get_price("EURUSD")
```

---

## 📞 Common Issues & Solutions

| Problem | Solution |
|---------|----------|
| `MT5InitError` | Check MT5 installation and terminal path |
| `MT5AuthError` | Verify login credentials in .env |
| `Connection timeout` | Check network connection and firewall |
| `Circuit breaker open` | Wait for automatic recovery or call reconnect() |
| `High latency` | Check network conditions and MT5 server load |
| `Memory leak` | Ensure disconnect() is called (use context manager) |

---

## 🎯 Integration Examples

### FastAPI Route
```python
from fastapi import APIRouter
from backend.app.trading.mt5 import MT5SessionManager

router = APIRouter()

@router.get("/api/v1/price/{symbol}")
async def get_price(symbol: str):
    """Get current price for symbol."""
    manager = get_mt5_manager()
    try:
        price = await manager.get_price(symbol)
        return {"bid": price.bid, "ask": price.ask}
    except MT5CircuitBreakerOpen:
        return {"error": "Service temporarily unavailable"}, 503
```

### Telegram Bot
```python
from telebot.async_telebot import AsyncTeleBot
from backend.app.trading.mt5 import MT5SessionManager

bot = AsyncTeleBot("TOKEN")
manager = MT5SessionManager(...)

@bot.message_handler(commands=['price'])
async def price_command(message):
    """Get price via Telegram."""
    try:
        await manager.connect()
        price = await manager.get_price("EURUSD")
        await bot.send_message(
            message.chat.id,
            f"EURUSD: {price.bid}/{price.ask}"
        )
    except Exception as e:
        await bot.send_message(message.chat.id, f"Error: {e}")
    finally:
        await manager.disconnect()
```

---

## 📖 Additional Resources

- **Full Documentation**: See `/docs/prs/PR-XYZ-MT5-INTEGRATION-COMPLETE.md`
- **API Reference**: See docstrings in each module
- **Test Examples**: See `/backend/tests/test_mt5_session.py`
- **Error Types**: See `/backend/app/trading/mt5/errors.py`

---

**Last Updated**: 2024
**Version**: 1.0.0
**Status**: Production Ready ✅
