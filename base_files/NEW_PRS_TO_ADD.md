# 🆕 NEW PRS TO ADD TO MASTER SPECIFICATION

**Date**: October 21, 2025  
**Status**: Ready to integrate into New_Master_Prs.md  
**Total New PRs**: 6  
**Updated Total**: 230 PRs (was 224)

---

## OVERVIEW

Based on legacy bot analysis, we need to add **6 new PRs** to capture features not covered in the current 224-PR specification. These PRs will preserve all functionality from your working trading bot.

---

## PR-22a: CONTENT DISTRIBUTION SYSTEM

**Priority**: 🔴 CRITICAL  
**Depends on**: PR-11 (Telegram Bot Core)  
**Phase**: 2 (Telegram Bot)  
**Estimated Time**: 3 days  

### Purpose
Multi-channel message routing system that forwards admin messages to 7 subscriber-specific Telegram groups based on keywords and subscription tiers.

### Features from Legacy Bot (ContentDistribution.py)
- ✅ **7 Telegram Groups**:
  - Gold Group (chat_id: -4608351708)
  - SP500 Group (chat_id: -4662755518)
  - Crypto Group (chat_id: -4740971535)
  - Gold+Crypto Group (chat_id: -4767465199)
  - SP500+Crypto Group (chat_id: -4654433080)
  - Gold+SP500 Group (chat_id: -4786454930)
  - All-In-One Group (chat_id: -4779379128)
- ✅ **Keyword Detection**: gold, sp500, crypto (case-insensitive)
- ✅ **Admin Confirmation**: Reply to admin after successful distribution
- ✅ **Error Handling**: Logging, retry logic
- ✅ **Rich Media Support**: Text, photos, videos, documents

### Technical Specification

#### Files to Create
```
backend/app/telegram/content_distribution.py
backend/app/telegram/channel_router.py
backend/app/models/distribution_log.py
backend/tests/test_content_distribution.py
```

#### Database Schema
```sql
CREATE TABLE distribution_logs (
    id SERIAL PRIMARY KEY,
    admin_user_id BIGINT NOT NULL,
    message_text TEXT NOT NULL,
    keywords VARCHAR[] NOT NULL,
    channels_sent VARCHAR[] NOT NULL,
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    status VARCHAR(20) NOT NULL, -- 'success', 'partial', 'failed'
    error_message TEXT,
    INDEX idx_admin_user (admin_user_id),
    INDEX idx_timestamp (timestamp)
);
```

#### Core Logic
```python
# backend/app/telegram/content_distribution.py

CHANNEL_IDS = {
    "gold": -4608351708,
    "sp500": -4662755518,
    "crypto": -4740971535,
    "gold_crypto": -4767465199,
    "sp500_crypto": -4654433080,
    "gold_sp500": -4786454930,
    "gold_sp500_crypto": -4779379128,
}

KEYWORDS = ["gold", "sp500", "crypto"]

async def distribute_message(message: Message, admin_id: int):
    """Route message to relevant channels based on keywords."""
    text = message.text.lower()
    channels_to_send = []
    
    # Detect keywords
    if "gold" in text:
        channels_to_send.append("gold")
    if "sp500" in text:
        channels_to_send.append("sp500")
    if "crypto" in text:
        channels_to_send.append("crypto")
    
    # Send to each channel
    sent_to = []
    errors = []
    
    for channel in channels_to_send:
        try:
            chat_id = CHANNEL_IDS[channel]
            await bot.send_message(chat_id=chat_id, text=message.text)
            sent_to.append(channel)
            logger.info(f"Message sent to {channel} ({chat_id})")
        except Exception as e:
            errors.append(f"{channel}: {str(e)}")
            logger.error(f"Failed to send to {channel}: {e}")
    
    # Log to database
    await log_distribution(admin_id, message.text, channels_to_send, sent_to, errors)
    
    # Confirm to admin
    if sent_to:
        confirmation = f"✅ Message sent to: {', '.join(sent_to)}"
    else:
        confirmation = "❌ No matching channels found. Use keywords: gold, sp500, crypto"
    
    await message.reply_text(confirmation)
```

### Acceptance Criteria
- [ ] Admin can send message with "gold" → forwards to Gold group
- [ ] Admin can send message with "crypto" → forwards to Crypto group
- [ ] Admin can send message with "gold crypto" → forwards to both groups
- [ ] System logs all distributions to database
- [ ] Admin receives confirmation after each send
- [ ] Errors are logged and reported
- [ ] Rich media (photos, videos) forwards correctly

---

## PR-24a: MARKETING AUTOMATION SYSTEM

**Priority**: 🟡 HIGH  
**Depends on**: PR-22a (Content Distribution)  
**Phase**: 2 (Telegram Bot)  
**Estimated Time**: 4 days  

### Purpose
Automated marketing message scheduler that posts educational guides and promotional content to subscriber groups every 4 hours.

### Features from Legacy Bot (MarketingBot.py, GuideBot.py)
- ✅ **Scheduled Posting**: Every 4 hours (14,400 seconds)
- ✅ **Educational Guides**: 6 guides hosted on Telegraph
  - UK Forex Guide
  - US Forex Guide
  - EU Forex Guide
  - Binance Crypto Guide
  - Kraken Crypto Guide
  - Coinbase Crypto Guide
- ✅ **Click Tracking**: SQLite database logs users who click buttons
- ✅ **Inline Keyboards**: Buttons with Telegraph URLs
- ✅ **Multi-Channel**: Posts to all 7 subscriber groups

### Technical Specification

#### Files to Create
```
backend/app/marketing/scheduler.py
backend/app/marketing/guide_manager.py
backend/app/models/guide_clicks.py
backend/app/marketing/templates.py
backend/tests/test_marketing_automation.py
```

#### Database Schema
```sql
CREATE TABLE guide_clicks (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    guide_name VARCHAR(100) NOT NULL,
    clicked_at TIMESTAMP NOT NULL DEFAULT NOW(),
    channel VARCHAR(50) NOT NULL,
    INDEX idx_user_id (user_id),
    INDEX idx_guide_name (guide_name),
    INDEX idx_clicked_at (clicked_at)
);

CREATE TABLE scheduled_posts (
    id SERIAL PRIMARY KEY,
    post_type VARCHAR(50) NOT NULL, -- 'guides', 'promotion', 'update'
    content TEXT NOT NULL,
    channels VARCHAR[] NOT NULL,
    scheduled_at TIMESTAMP NOT NULL,
    posted_at TIMESTAMP,
    status VARCHAR(20) NOT NULL, -- 'pending', 'sent', 'failed'
    error_message TEXT
);
```

#### Core Logic
```python
# backend/app/marketing/scheduler.py

from apscheduler.schedulers.asyncio import AsyncIOScheduler

GUIDE_URLS = {
    "uk_forex": "https://telegra.ph/Forex-Trading-Guide-for-UK-Clients-12-23",
    "us_forex": "https://telegra.ph/Forex-Trading-Guide-for-US-Clients-12-23",
    "eu_forex": "https://telegra.ph/Forex-Trading-Guide-for-European-Clients-12-23",
    "binance": "https://telegra.ph/Binance-Guide-Buying-and-Selling-Cryptos-While-Minimizing-Fees-12-23",
    "kraken": "https://telegra.ph/Kraken-Guide-Buying-and-Selling-Cryptos-While-Minimizing-Fees-12-23",
    "coinbase": "https://telegra.ph/Coinbase-Guide-Buying-and-Selling-Cryptos-While-Minimizing-Fees-12-23",
}

MARKETING_MESSAGE = """
🌟 *Maximize Your Trading Potential!* 🌟

Follow these guides to trade Forex and Cryptocurrency signals effectively.
Minimize fees and taxes based on your location.

📚 *Forex Trading Guides:*
- UK Clients: Tax benefits with spread betting
- US Clients: Broker selection and strategies
- EU Clients: ESMA regulations and leverage

📚 *Cryptocurrency Trading Guides:*
- Binance, Kraken, Coinbase: Buy/sell crypto safely with minimal fees

📖 Click the buttons below to get started! 📖
"""

async def post_guides_to_all_channels():
    """Post educational guides to all subscriber groups."""
    keyboard = [
        [
            InlineKeyboardButton("UK Forex", url=GUIDE_URLS["uk_forex"], callback_data="guide_uk_forex"),
            InlineKeyboardButton("US Forex", url=GUIDE_URLS["us_forex"], callback_data="guide_us_forex"),
        ],
        [
            InlineKeyboardButton("EU Forex", url=GUIDE_URLS["eu_forex"], callback_data="guide_eu_forex"),
        ],
        [
            InlineKeyboardButton("Binance", url=GUIDE_URLS["binance"], callback_data="guide_binance"),
            InlineKeyboardButton("Kraken", url=GUIDE_URLS["kraken"], callback_data="guide_kraken"),
        ],
        [
            InlineKeyboardButton("Coinbase", url=GUIDE_URLS["coinbase"], callback_data="guide_coinbase"),
        ],
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    for channel_name, chat_id in CHANNEL_IDS.items():
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=MARKETING_MESSAGE,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
            logger.info(f"Guides posted to {channel_name}")
        except Exception as e:
            logger.error(f"Failed to post to {channel_name}: {e}")
    
    # Log the post
    await log_scheduled_post("guides", MARKETING_MESSAGE, list(CHANNEL_IDS.keys()))

# Schedule every 4 hours
scheduler = AsyncIOScheduler()
scheduler.add_job(post_guides_to_all_channels, 'interval', hours=4)
scheduler.start()
```

#### Click Tracking
```python
@router.callback_query(lambda c: c.data.startswith("guide_"))
async def track_guide_click(callback: CallbackQuery):
    """Track which users click on guide buttons."""
    user_id = callback.from_user.id
    guide_name = callback.data.replace("guide_", "")
    channel = callback.message.chat.title or "Unknown"
    
    # Log to database
    await log_guide_click(user_id, guide_name, channel)
    
    # No need to answer callback (link opens automatically)
```

### Acceptance Criteria
- [ ] Guides post automatically every 4 hours
- [ ] All 7 channels receive the message
- [ ] Inline keyboard buttons work correctly
- [ ] Click tracking logs user_id + guide_name
- [ ] Telegraph links open correctly
- [ ] Scheduler survives server restart
- [ ] Admin can manually trigger posting

---

## PR-26b: LIVE EXCHANGE RATE SYSTEM

**Priority**: 🔴 CRITICAL  
**Depends on**: PR-26 (Subscription Plans)  
**Phase**: 3 (Monetization)  
**Estimated Time**: 3 days  

### Purpose
Real-time exchange rate fetching for GBP/USD and 15 cryptocurrencies to calculate accurate subscription pricing.

### Features from Legacy Bot (RateFetcher.py)
- ✅ **GBP/USD Rate**: ExchangeRate-API (refreshes every 15 minutes)
- ✅ **Crypto Prices**: CoinGecko API (refreshes every 15 minutes)
- ✅ **15 Cryptocurrencies**:
  - BTC (Bitcoin)
  - ETH (Ethereum)
  - LTC (Litecoin)
  - XRP (Ripple)
  - BCH (Bitcoin Cash)
  - ETC (Ethereum Classic)
  - BNB (Binance Coin)
  - DOGE (Dogecoin)
  - DASH (Dash)
  - ZEC (Zcash)
  - ADA (Cardano)
  - DOT (Polkadot)
  - SOL (Solana)
  - XLM (Stellar)
  - TRX (Tron)
- ✅ **Pricing Calculation**: £ → $ → crypto conversion
- ✅ **Fallback**: Use last known rate if API fails
- ✅ **Threading**: Background thread updates rates

### Technical Specification

#### Files to Create
```
backend/app/payments/exchange_rates.py
backend/app/models/exchange_rate.py
backend/app/payments/crypto_pricing.py
backend/tests/test_exchange_rates.py
```

#### Database Schema
```sql
CREATE TABLE exchange_rates (
    id SERIAL PRIMARY KEY,
    currency_pair VARCHAR(10) NOT NULL, -- 'GBP_USD', 'BTC_USD', etc.
    rate DECIMAL(18, 8) NOT NULL,
    fetched_at TIMESTAMP NOT NULL DEFAULT NOW(),
    source VARCHAR(50) NOT NULL, -- 'exchangerate-api', 'coingecko'
    INDEX idx_currency_pair (currency_pair),
    INDEX idx_fetched_at (fetched_at)
);

CREATE TABLE crypto_prices (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL, -- 'BTC', 'ETH', etc.
    usd_price DECIMAL(18, 8) NOT NULL,
    fetched_at TIMESTAMP NOT NULL DEFAULT NOW(),
    INDEX idx_symbol (symbol),
    INDEX idx_fetched_at (fetched_at)
);
```

#### Core Logic
```python
# backend/app/payments/exchange_rates.py

import requests
from threading import Timer
import asyncio

EXCHANGERATE_API_TOKEN = "7b8e8db657261aff7e5946c7"
GBP_USD_URL = f"https://v6.exchangerate-api.com/v6/{EXCHANGERATE_API_TOKEN}/latest/GBP"

COINGECKO_URL = (
    "https://api.coingecko.com/api/v3/simple/price?"
    "ids=bitcoin,litecoin,ethereum,ripple,bitcoin-cash,ethereum-classic,"
    "binancecoin,dogecoin,dash,zcash,cardano,polkadot,solana,stellar,tron"
    "&vs_currencies=usd"
)

CRYPTO_MAP = {
    "bitcoin": "BTC",
    "ethereum": "ETH",
    "litecoin": "LTC",
    "ripple": "XRP",
    "bitcoin-cash": "BCH",
    "ethereum-classic": "ETC",
    "binancecoin": "BNB",
    "dogecoin": "DOGE",
    "dash": "DASH",
    "zcash": "ZEC",
    "cardano": "ADA",
    "polkadot": "DOT",
    "solana": "SOL",
    "stellar": "XLM",
    "tron": "TRX",
}

# Global cache
gbp_to_usd_rate = None
crypto_rates = {}

async def fetch_gbp_usd():
    """Fetch GBP to USD exchange rate."""
    global gbp_to_usd_rate
    try:
        response = requests.get(GBP_USD_URL, timeout=10)
        response.raise_for_status()
        data = response.json()
        gbp_to_usd_rate = data["conversion_rates"]["USD"]
        
        # Save to database
        await save_exchange_rate("GBP_USD", gbp_to_usd_rate, "exchangerate-api")
        
        logger.info(f"GBP/USD rate updated: {gbp_to_usd_rate}")
    except Exception as e:
        logger.error(f"Failed to fetch GBP/USD: {e}")
        # Use last known rate from database
        gbp_to_usd_rate = await get_last_known_rate("GBP_USD")

async def fetch_crypto_prices():
    """Fetch cryptocurrency prices in USD."""
    global crypto_rates
    try:
        response = requests.get(COINGECKO_URL, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        for coingecko_id, symbol in CRYPTO_MAP.items():
            price = data[coingecko_id]["usd"]
            crypto_rates[symbol] = price
            
            # Save to database
            await save_crypto_price(symbol, price)
        
        logger.info(f"Crypto prices updated: {len(crypto_rates)} currencies")
    except Exception as e:
        logger.error(f"Failed to fetch crypto prices: {e}")
        # Use last known rates from database
        crypto_rates = await get_last_known_crypto_prices()

async def calculate_crypto_pricing(gbp_amount: float) -> dict:
    """Convert GBP amount to crypto amounts."""
    if not gbp_to_usd_rate or not crypto_rates:
        raise ValueError("Exchange rates not available")
    
    usd_amount = gbp_amount * gbp_to_usd_rate
    
    crypto_amounts = {}
    for symbol, usd_price in crypto_rates.items():
        crypto_amount = usd_amount / usd_price
        crypto_amounts[symbol] = round(crypto_amount, 8)
    
    return {
        "gbp": gbp_amount,
        "usd": round(usd_amount, 2),
        "crypto": crypto_amounts
    }

# Background task to refresh rates every 15 minutes
async def refresh_rates_loop():
    """Background task to refresh rates."""
    while True:
        await fetch_gbp_usd()
        await fetch_crypto_prices()
        await asyncio.sleep(900)  # 15 minutes

# Start on app startup
def start_rate_fetcher():
    asyncio.create_task(refresh_rates_loop())
```

#### Usage in Subscription Flow
```python
# When user selects subscription plan
plan_price_gbp = 49  # Gold 1-month

pricing = await calculate_crypto_pricing(plan_price_gbp)

message = f"""
💳 PAYMENT DETAILS - Gold (1 Month)

Price: £{pricing['gbp']} (${pricing['usd']})

Choose your payment method:
🪙 BTC: {pricing['crypto']['BTC']}
💎 ETH: {pricing['crypto']['ETH']}
🔷 LTC: {pricing['crypto']['LTC']}
... (15 total options)

Send exact amount to the address below:
"""
```

### Acceptance Criteria
- [ ] GBP/USD rate fetches every 15 minutes
- [ ] All 15 crypto prices fetch every 15 minutes
- [ ] Rates save to database on each fetch
- [ ] Fallback to last known rate if API fails
- [ ] Pricing calculation accurate (£ → $ → crypto)
- [ ] Thread-safe (no race conditions)
- [ ] Survives server restart (uses DB cache)
- [ ] Admin can manually trigger refresh

---

## PR-32a: FLASK API DASHBOARD

**Priority**: 🟢 MEDIUM  
**Depends on**: PR-101a (Trading Strategy), PR-160a (Analytics)  
**Phase**: 6 (Analytics & Reporting)  
**Estimated Time**: 5 days  

### Purpose
Real-time monitoring dashboard with REST API and WebSocket for admins to view trading performance, positions, and analytics.

### Features from Legacy Bot (FlaskAPI.py)
- ✅ **REST Endpoints**:
  - `/api/price` - Current GOLD/SP500/crypto prices
  - `/api/trades` - Trade history with pagination
  - `/api/positions` - Active positions
  - `/api/metrics` - Performance statistics
  - `/api/indicators` - RSI, ROC, Fibonacci levels
  - `/api/historical` - OHLCV data
- ✅ **WebSocket**: Real-time price/position updates
- ✅ **Static Files**: Serve charts/images
- ✅ **Port Discovery**: Auto-find available port (5000-5010)
- ✅ **Eventlet**: Async handling for WebSocket

### Technical Specification

#### Files to Create
```
backend/app/dashboard/api.py
backend/app/dashboard/websocket.py
backend/app/dashboard/static_server.py
backend/tests/test_dashboard_api.py
frontend/dashboard/index.html
frontend/dashboard/app.js
frontend/dashboard/styles.css
```

#### REST Endpoints
```python
# backend/app/dashboard/api.py

from flask import Flask, jsonify, send_from_directory
from flask_socketio import SocketIO
from flask_restful import Api, Resource

app = Flask(__name__, static_folder='static')
api = Api(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

class PriceData(Resource):
    def get(self):
        """Get current market prices."""
        return jsonify({
            "symbol": "GOLD",
            "bid": get_current_bid(),
            "ask": get_current_ask(),
            "spread": get_spread(),
            "timestamp": datetime.now().isoformat()
        })

class Trades(Resource):
    def get(self):
        """Get trade history with pagination."""
        page = request.args.get('page', 1, type=int)
        limit = request.args.get('limit', 50, type=int)
        
        trades = get_trades_paginated(page, limit)
        
        return jsonify({
            "trades": trades,
            "page": page,
            "total": get_total_trades(),
            "pages": math.ceil(get_total_trades() / limit)
        })

class Positions(Resource):
    def get(self):
        """Get active positions."""
        positions = get_active_positions()
        
        return jsonify({
            "positions": positions,
            "total_unrealized_pl": sum(p["unrealized_pl"] for p in positions)
        })

class Metrics(Resource):
    def get(self):
        """Get performance metrics."""
        return jsonify({
            "total_trades": get_total_trades(),
            "win_rate": get_win_rate(),
            "profit_factor": get_profit_factor(),
            "sharpe_ratio": get_sharpe_ratio(),
            "max_drawdown": get_max_drawdown(),
            "total_profit": get_total_profit(),
            "equity": get_current_equity()
        })

class Indicators(Resource):
    def get(self):
        """Get current indicator values."""
        return jsonify({
            "rsi": get_current_rsi(),
            "roc_price": get_current_roc(),
            "fibonacci_levels": get_fib_levels(),
            "timestamp": datetime.now().isoformat()
        })

class HistoricalData(Resource):
    def get(self):
        """Get OHLCV historical data."""
        symbol = request.args.get('symbol', 'GOLD')
        timeframe = request.args.get('timeframe', 'H1')
        bars = request.args.get('bars', 1000, type=int)
        
        data = fetch_ohlcv(symbol, timeframe, bars)
        
        return jsonify({
            "symbol": symbol,
            "timeframe": timeframe,
            "data": data
        })

# Register endpoints
api.add_resource(PriceData, '/api/price')
api.add_resource(Trades, '/api/trades')
api.add_resource(Positions, '/api/positions')
api.add_resource(Metrics, '/api/metrics')
api.add_resource(Indicators, '/api/indicators')
api.add_resource(HistoricalData, '/api/historical')
```

#### WebSocket Real-Time Updates
```python
# backend/app/dashboard/websocket.py

@socketio.on('connect')
def handle_connect():
    logger.info(f"Client connected: {request.sid}")
    emit('connection_response', {'status': 'connected'})

@socketio.on('disconnect')
def handle_disconnect():
    logger.info(f"Client disconnected: {request.sid}")

# Background task to push updates
def price_update_task():
    while True:
        try:
            # Get current price
            price = get_current_price()
            
            # Get active positions
            positions = get_active_positions()
            
            # Emit to all connected clients
            socketio.emit('price_update', {
                'price': price,
                'timestamp': datetime.now().isoformat()
            })
            
            socketio.emit('positions_update', {
                'positions': positions
            })
            
        except Exception as e:
            logger.error(f"Price update error: {e}")
        
        time.sleep(1)  # Update every second

# Start background task
price_thread = threading.Thread(target=price_update_task, daemon=True)
price_thread.start()
```

#### Frontend Dashboard
```html
<!-- frontend/dashboard/index.html -->
<!DOCTYPE html>
<html>
<head>
    <title>Caerus Trading Dashboard</title>
    <link rel="stylesheet" href="styles.css">
    <script src="https://cdn.socket.io/4.0.0/socket.io.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body>
    <div class="dashboard">
        <h1>🏆 Caerus Trading Dashboard</h1>
        
        <div class="metrics">
            <div class="metric-card">
                <h3>Current Price</h3>
                <span id="current-price">--</span>
            </div>
            <div class="metric-card">
                <h3>Total Profit</h3>
                <span id="total-profit">--</span>
            </div>
            <div class="metric-card">
                <h3>Win Rate</h3>
                <span id="win-rate">--</span>
            </div>
            <div class="metric-card">
                <h3>Active Positions</h3>
                <span id="active-positions">--</span>
            </div>
        </div>
        
        <div class="charts">
            <canvas id="equity-chart"></canvas>
        </div>
        
        <div class="positions">
            <h2>Active Positions</h2>
            <table id="positions-table">
                <thead>
                    <tr>
                        <th>Symbol</th>
                        <th>Type</th>
                        <th>P&L</th>
                        <th>Duration</th>
                    </tr>
                </thead>
                <tbody></tbody>
            </table>
        </div>
    </div>
    
    <script src="app.js"></script>
</body>
</html>
```

```javascript
// frontend/dashboard/app.js

const socket = io('http://localhost:5000');

socket.on('connect', () => {
    console.log('Connected to dashboard');
});

socket.on('price_update', (data) => {
    document.getElementById('current-price').textContent = data.price.toFixed(2);
});

socket.on('positions_update', (data) => {
    updatePositionsTable(data.positions);
});

// Fetch metrics on load
async function loadMetrics() {
    const response = await fetch('/api/metrics');
    const metrics = await response.json();
    
    document.getElementById('total-profit').textContent = `£${metrics.total_profit}`;
    document.getElementById('win-rate').textContent = `${metrics.win_rate}%`;
    document.getElementById('active-positions').textContent = metrics.total_trades;
}

loadMetrics();
```

### Acceptance Criteria
- [ ] All 6 REST endpoints return correct data
- [ ] WebSocket connects and receives real-time updates
- [ ] Dashboard UI loads correctly
- [ ] Metrics display in real-time
- [ ] Charts render correctly
- [ ] Port auto-discovery works (5000-5010)
- [ ] Static files serve correctly
- [ ] JWT authentication protects endpoints

---

## PR-101a: RSI-FIBONACCI STRATEGY ENGINE

**Priority**: 🔴 CRITICAL  
**Depends on**: PR-102 (MT5 Integration), PR-105 (Technical Indicators)  
**Phase**: 5 (Trading Integration)  
**Estimated Time**: 7 days  

### Purpose
Core trading strategy implementation using RSI swing detection + Fibonacci retracement/extension for entry/exit levels.

### Features from Legacy Bot (DemoNoStochRSI.py)
- ✅ **Strategy Type**: Rule-based pattern recognition (NOT AI/ML)
- ✅ **RSI Window Tracking**: Find highest/lowest prices during RSI extreme periods
- ✅ **Fibonacci Levels**: 0.74 retracement, 0.27 extension
- ✅ **Position Sizing**: 2% account risk
- ✅ **Risk-Reward**: 3.25:1 minimum
- ✅ **Validation**: ±0.20 tolerance on Fibonacci levels
- ✅ **Time Constraints**: 100-hour max between crossings, 1440-hour max age
- ✅ **Order Management**: Limit orders with 100-hour expiry

### Technical Specification

#### Files to Create
```
backend/app/trading/strategy_engine.py
backend/app/trading/setup_detector.py
backend/app/trading/fibonacci_calculator.py
backend/app/trading/position_sizer.py
backend/app/models/trade_setup.py
backend/tests/test_strategy_engine.py
docs/STRATEGY_DOCUMENTATION.md
```

#### Database Schema
```sql
CREATE TABLE trade_setups (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    direction VARCHAR(10) NOT NULL, -- 'LONG', 'SHORT'
    
    -- RSI window tracking
    rsi_high_time TIMESTAMP,
    rsi_low_time TIMESTAMP,
    price_high DECIMAL(10, 2),
    price_low DECIMAL(10, 2),
    
    -- Fibonacci levels
    fib_range DECIMAL(10, 2),
    entry_price DECIMAL(10, 2),
    stop_loss DECIMAL(10, 2),
    take_profit DECIMAL(10, 2),
    
    -- Validation
    entry_fib_deviation DECIMAL(6, 4),
    sl_fib_deviation DECIMAL(6, 4),
    rr_ratio DECIMAL(6, 2),
    
    -- Timing
    setup_detected_at TIMESTAMP NOT NULL,
    setup_age_hours INT,
    rsi_crossing_duration_hours INT,
    
    -- Status
    status VARCHAR(20) NOT NULL, -- 'pending', 'placed', 'filled', 'expired', 'cancelled'
    order_id BIGINT,
    expiry_time TIMESTAMP,
    
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    INDEX idx_symbol (symbol),
    INDEX idx_status (status),
    INDEX idx_created_at (created_at)
);
```

#### Core Logic - Setup Detection
```python
# backend/app/trading/setup_detector.py

async def detect_setups(df: pd.DataFrame, symbol: str, timeframe: str) -> List[TradeSetup]:
    """Detect RSI-Fibonacci setups in price data."""
    setups = []
    
    # Need at least 200 bars for reliable indicators
    if len(df) < 200:
        return setups
    
    # Calculate indicators
    df = calculate_indicators(df)
    
    # Scan for SHORT setups
    short_setups = detect_short_setups(df, symbol, timeframe)
    setups.extend(short_setups)
    
    # Scan for LONG setups
    long_setups = detect_long_setups(df, symbol, timeframe)
    setups.extend(long_setups)
    
    return setups

def detect_short_setups(df: pd.DataFrame, symbol: str, timeframe: str) -> List[TradeSetup]:
    """Detect SHORT setups: RSI > 70 → RSI ≤ 40."""
    setups = []
    
    for i in range(len(df) - 1):
        # Step 1: RSI crosses above 70
        if df.iloc[i]['RSI'] <= 70 and df.iloc[i+1]['RSI'] > 70:
            # Step 2: Track all candles while RSI > 70
            rsi_high_window = df.iloc[i+1:][df['RSI'] > 70]
            
            if rsi_high_window.empty:
                continue
            
            # Find highest price during overbought period
            price_high = rsi_high_window['HIGH'].max()
            price_high_time = rsi_high_window['HIGH'].idxmax()
            
            # Step 3: Wait for RSI to cross below 40
            for j in range(i+1, len(df)):
                if df.iloc[j]['RSI'] <= 40:
                    # Calculate time elapsed
                    time_elapsed = (df.index[j] - df.index[i]).total_seconds() / 3600
                    
                    if time_elapsed > 100:
                        break  # Too much time elapsed
                    
                    # Step 4: Track all candles while RSI ≤ 40
                    rsi_low_window = df.iloc[j:][df['RSI'] <= 40]
                    
                    if rsi_low_window.empty:
                        continue
                    
                    # Find lowest price during oversold period
                    price_low = rsi_low_window['LOW'].min()
                    price_low_time = rsi_low_window['LOW'].idxmin()
                    
                    # Step 5: Calculate Fibonacci levels
                    fib_range = price_high - price_low
                    entry = price_low + (fib_range * 0.74)
                    stop_loss = price_high + (fib_range * 0.27)
                    take_profit = entry - (abs(entry - stop_loss) * 3.25)
                    
                    # Step 6: Validate setup
                    if validate_fib_levels(entry, stop_loss, price_high, price_low, False):
                        setup = TradeSetup(
                            symbol=symbol,
                            timeframe=timeframe,
                            direction='SHORT',
                            price_high=price_high,
                            price_low=price_low,
                            rsi_high_time=price_high_time,
                            rsi_low_time=price_low_time,
                            fib_range=fib_range,
                            entry_price=entry,
                            stop_loss=stop_loss,
                            take_profit=take_profit,
                            setup_detected_at=datetime.now(),
                            rsi_crossing_duration_hours=time_elapsed
                        )
                        setups.append(setup)
                    
                    break
    
    return setups

def detect_long_setups(df: pd.DataFrame, symbol: str, timeframe: str) -> List[TradeSetup]:
    """Detect LONG setups: RSI < 40 → RSI ≥ 70."""
    setups = []
    
    for i in range(len(df) - 1):
        # Step 1: RSI crosses below 40
        if df.iloc[i]['RSI'] >= 40 and df.iloc[i+1]['RSI'] < 40:
            # Step 2: Track all candles while RSI < 40
            rsi_low_window = df.iloc[i+1:][df['RSI'] < 40]
            
            if rsi_low_window.empty:
                continue
            
            # Find lowest price during oversold period
            price_low = rsi_low_window['LOW'].min()
            price_low_time = rsi_low_window['LOW'].idxmin()
            
            # Step 3: Wait for RSI to cross above 70
            for j in range(i+1, len(df)):
                if df.iloc[j]['RSI'] >= 70:
                    # Calculate time elapsed
                    time_elapsed = (df.index[j] - df.index[i]).total_seconds() / 3600
                    
                    if time_elapsed > 100:
                        break  # Too much time elapsed
                    
                    # Step 4: Track all candles while RSI ≥ 70
                    rsi_high_window = df.iloc[j:][df['RSI'] >= 70]
                    
                    if rsi_high_window.empty:
                        continue
                    
                    # Find highest price during overbought period
                    price_high = rsi_high_window['HIGH'].max()
                    price_high_time = rsi_high_window['HIGH'].idxmax()
                    
                    # Step 5: Calculate Fibonacci levels
                    fib_range = price_high - price_low
                    entry = price_high - (fib_range * 0.74)
                    stop_loss = price_low - (fib_range * 0.27)
                    take_profit = entry + (abs(entry - stop_loss) * 3.25)
                    
                    # Step 6: Validate setup
                    if validate_fib_levels(entry, stop_loss, price_high, price_low, True):
                        setup = TradeSetup(
                            symbol=symbol,
                            timeframe=timeframe,
                            direction='LONG',
                            price_high=price_high,
                            price_low=price_low,
                            rsi_high_time=price_high_time,
                            rsi_low_time=price_low_time,
                            fib_range=fib_range,
                            entry_price=entry,
                            stop_loss=stop_loss,
                            take_profit=take_profit,
                            setup_detected_at=datetime.now(),
                            rsi_crossing_duration_hours=time_elapsed
                        )
                        setups.append(setup)
                    
                    break
    
    return setups
```

#### Fibonacci Validation
```python
# backend/app/trading/fibonacci_calculator.py

def validate_fib_levels(
    entry: float,
    stop_loss: float,
    price_high: float,
    price_low: float,
    is_long: bool,
    tolerance: float = 0.20
) -> bool:
    """Validate Fibonacci levels are within tolerance."""
    
    # Must have positive range
    fib_range = price_high - price_low
    if fib_range <= 0:
        logger.warning("Invalid Fibonacci range (not positive)")
        return False
    
    # Calculate expected levels
    if is_long:
        expected_entry = price_high - (fib_range * 0.74)
        expected_sl = price_low - (fib_range * 0.27)
    else:
        expected_entry = price_low + (fib_range * 0.74)
        expected_sl = price_high + (fib_range * 0.27)
    
    # Check entry deviation
    entry_deviation = abs(entry - expected_entry)
    if entry_deviation > tolerance:
        logger.warning(f"Entry deviation too large: {entry_deviation}")
        return False
    
    # Check stop loss deviation
    sl_deviation = abs(stop_loss - expected_sl)
    if sl_deviation > tolerance:
        logger.warning(f"Stop loss deviation too large: {sl_deviation}")
        return False
    
    # Validate risk-reward ratio
    risk = abs(entry - stop_loss)
    if risk < 5.0:
        logger.warning(f"Risk too small: {risk} points")
        return False
    
    reward = abs(take_profit - entry)
    rr_ratio = reward / risk
    
    if rr_ratio < 3.25:
        logger.warning(f"Risk-reward ratio too low: {rr_ratio}")
        return False
    
    return True
```

#### Position Sizing
```python
# backend/app/trading/position_sizer.py

def calculate_position_size(
    account_equity: float,
    entry_price: float,
    stop_loss: float,
    risk_percent: float = 0.02
) -> float:
    """Calculate position size based on 2% risk."""
    
    # Calculate risk amount
    risk_amount = account_equity * risk_percent
    
    # Calculate stop distance in points
    stop_distance = abs(entry_price - stop_loss)
    
    # Get contract specifications (GOLD standard)
    contract_size = 100  # Standard lot
    point_value = 1.0    # $1 per point
    
    # Calculate position size
    position_size = risk_amount / (stop_distance * point_value)
    
    # Round to broker's minimum lot size (0.01)
    position_size = round(position_size, 2)
    
    # Ensure minimum position size
    if position_size < 0.01:
        position_size = 0.01
    
    logger.info(f"Position size: {position_size} lots (risk: ${risk_amount})")
    
    return position_size
```

#### Order Placement
```python
# backend/app/trading/strategy_engine.py

async def place_setup_order(setup: TradeSetup) -> bool:
    """Place limit order for detected setup."""
    
    # Calculate position size
    account_equity = await get_account_equity()
    position_size = calculate_position_size(
        account_equity,
        setup.entry_price,
        setup.stop_loss
    )
    
    # Determine order type
    order_type = mt5.ORDER_TYPE_SELL_LIMIT if setup.direction == 'SHORT' else mt5.ORDER_TYPE_BUY_LIMIT
    
    # Set expiry (100 hours from now)
    expiry = datetime.now() + timedelta(hours=100)
    
    # Place order
    order_request = {
        "action": mt5.TRADE_ACTION_PENDING,
        "symbol": setup.symbol,
        "volume": position_size,
        "type": order_type,
        "price": setup.entry_price,
        "sl": setup.stop_loss,
        "tp": setup.take_profit,
        "deviation": 10,
        "magic": 234000,
        "comment": f"RSI-Fib {setup.direction}",
        "type_time": mt5.ORDER_TIME_SPECIFIED,
        "type_filling": mt5.ORDER_FILLING_IOC,
        "expiration": int(expiry.timestamp())
    }
    
    result = mt5.order_send(order_request)
    
    if result.retcode == mt5.TRADE_RETCODE_DONE:
        logger.info(f"Order placed: {result.order}")
        
        # Update setup status
        setup.status = 'placed'
        setup.order_id = result.order
        setup.expiry_time = expiry
        await save_setup(setup)
        
        # Send Telegram notification (NO PRICES!)
        await send_telegram_notification(
            f"✅ {setup.direction} position pending on {setup.symbol}"
        )
        
        return True
    else:
        logger.error(f"Order failed: {result.retcode} - {result.comment}")
        return False
```

### Acceptance Criteria
- [ ] SHORT setups detect correctly (RSI > 70 → RSI ≤ 40)
- [ ] LONG setups detect correctly (RSI < 40 → RSI ≥ 70)
- [ ] Fibonacci levels calculate accurately (0.74/0.27)
- [ ] Validation enforces ±0.20 tolerance
- [ ] Time constraints enforced (100-hour max, 1440-hour max age)
- [ ] Position sizing uses 2% risk model
- [ ] Orders place as limit orders with 100-hour expiry
- [ ] Setups save to database with full details
- [ ] Telegram notifications sent (NO prices shown to clients)
- [ ] Risk-reward ratio ≥ 3.25:1 enforced

---

## PR-160a: ADVANCED ANALYTICS SYSTEM

**Priority**: 🟡 HIGH  
**Depends on**: PR-101a (Strategy Engine)  
**Phase**: 6 (Analytics & Reporting)  
**Estimated Time**: 6 days  

### Purpose
Comprehensive analytics and reporting system with 15+ chart types, performance metrics, and scheduled reports.

### Features from Legacy Bot (LIVEFXPROFinal5.py)
- ✅ **15+ Chart Types**:
  - Equity curve
  - Drawdown curve
  - Trade heatmap
  - Monthly returns
  - Win rate by hour/day/month
  - Profit factor by symbol
  - Risk-reward distribution
  - Holding time vs profitability
  - Feature importance (RSI, Fibonacci, ROC)
  - Future outlook projection
  - Period comparison
  - Sharpe ratio evolution
  - Max drawdown tracking
  - Consecutive wins/losses
  - Recovery factor
- ✅ **Performance Metrics**: Win rate, profit factor, Sharpe, max DD
- ✅ **Date Range Filtering**: Custom periods for all reports
- ✅ **Alerts**: Monthly profit >5%, drawdown >5%
- ✅ **Export**: CSV, PDF, JSON

### Technical Specification

#### Files to Create
```
backend/app/analytics/chart_generator.py
backend/app/analytics/metrics_calculator.py
backend/app/analytics/report_scheduler.py
backend/app/models/performance_snapshot.py
backend/tests/test_analytics.py
```

#### Database Schema
```sql
CREATE TABLE performance_snapshots (
    id SERIAL PRIMARY KEY,
    snapshot_date DATE NOT NULL,
    
    -- Equity metrics
    equity DECIMAL(12, 2) NOT NULL,
    peak_equity DECIMAL(12, 2),
    drawdown_percent DECIMAL(6, 2),
    
    -- Trade metrics
    total_trades INT,
    winning_trades INT,
    losing_trades INT,
    win_rate DECIMAL(6, 2),
    
    -- P&L metrics
    total_profit DECIMAL(12, 2),
    total_loss DECIMAL(12, 2),
    profit_factor DECIMAL(6, 2),
    average_win DECIMAL(10, 2),
    average_loss DECIMAL(10, 2),
    
    -- Risk metrics
    sharpe_ratio DECIMAL(6, 2),
    max_drawdown DECIMAL(6, 2),
    max_consecutive_wins INT,
    max_consecutive_losses INT,
    
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    INDEX idx_snapshot_date (snapshot_date)
);
```

#### Chart Generation
```python
# backend/app/analytics/chart_generator.py

import matplotlib
matplotlib.use('Agg')  # Prevent threading issues
import matplotlib.pyplot as plt
import seaborn as sns

async def generate_equity_curve(start_date: date, end_date: date) -> str:
    """Generate equity curve chart."""
    trades = await get_trades_in_range(start_date, end_date)
    
    if not trades:
        return None
    
    # Calculate cumulative equity
    equity = [10000]  # Starting equity
    dates = [start_date]
    
    for trade in trades:
        equity.append(equity[-1] + trade.profit_loss)
        dates.append(trade.closed_at)
    
    # Create plot
    plt.figure(figsize=(12, 6))
    plt.plot(dates, equity, linewidth=2, color='#2E86DE')
    plt.fill_between(dates, equity, alpha=0.3, color='#2E86DE')
    plt.title('Equity Curve', fontsize=16, fontweight='bold')
    plt.xlabel('Date')
    plt.ylabel('Equity (£)')
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    
    # Save to file
    filename = f"equity_curve_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    filepath = os.path.join(PLOT_PATH, filename)
    plt.savefig(filepath, dpi=150, bbox_inches='tight')
    plt.close()
    
    return filepath

async def generate_trade_heatmap(start_date: date, end_date: date) -> str:
    """Generate trade heatmap (hour x day of week)."""
    trades = await get_trades_in_range(start_date, end_date)
    
    if not trades:
        return None
    
    # Create matrix: 24 hours x 7 days
    heatmap_data = np.zeros((24, 7))
    
    for trade in trades:
        hour = trade.closed_at.hour
        day = trade.closed_at.weekday()
        heatmap_data[hour][day] += trade.profit_loss
    
    # Create heatmap
    plt.figure(figsize=(10, 8))
    sns.heatmap(
        heatmap_data,
        cmap='RdYlGn',
        center=0,
        xticklabels=['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
        yticklabels=range(24),
        cbar_kws={'label': 'Profit/Loss (£)'}
    )
    plt.title('Trade Profitability Heatmap', fontsize=16, fontweight='bold')
    plt.xlabel('Day of Week')
    plt.ylabel('Hour of Day')
    plt.tight_layout()
    
    # Save to file
    filename = f"heatmap_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    filepath = os.path.join(PLOT_PATH, filename)
    plt.savefig(filepath, dpi=150, bbox_inches='tight')
    plt.close()
    
    return filepath

# Similar functions for other 13+ chart types...
```

#### Performance Metrics
```python
# backend/app/analytics/metrics_calculator.py

async def calculate_metrics(start_date: date, end_date: date) -> dict:
    """Calculate all performance metrics."""
    trades = await get_trades_in_range(start_date, end_date)
    
    if not trades:
        return {}
    
    winning_trades = [t for t in trades if t.profit_loss > 0]
    losing_trades = [t for t in trades if t.profit_loss <= 0]
    
    total_profit = sum(t.profit_loss for t in winning_trades)
    total_loss = abs(sum(t.profit_loss for t in losing_trades))
    
    return {
        "total_trades": len(trades),
        "winning_trades": len(winning_trades),
        "losing_trades": len(losing_trades),
        "win_rate": len(winning_trades) / len(trades) * 100 if trades else 0,
        "profit_factor": total_profit / total_loss if total_loss > 0 else 0,
        "average_win": total_profit / len(winning_trades) if winning_trades else 0,
        "average_loss": total_loss / len(losing_trades) if losing_trades else 0,
        "sharpe_ratio": calculate_sharpe_ratio(trades),
        "max_drawdown": calculate_max_drawdown(trades),
        "total_profit": total_profit - total_loss,
        "expectancy": calculate_expectancy(trades)
    }
```

#### Scheduled Reports
```python
# backend/app/analytics/report_scheduler.py

from apscheduler.schedulers.asyncio import AsyncIOScheduler

async def send_daily_report():
    """Send daily performance report to all subscribers."""
    yesterday = date.today() - timedelta(days=1)
    
    # Generate charts
    equity_chart = await generate_equity_curve(yesterday - timedelta(days=30), yesterday)
    heatmap = await generate_trade_heatmap(yesterday - timedelta(days=30), yesterday)
    
    # Calculate metrics
    metrics = await calculate_metrics(yesterday - timedelta(days=30), yesterday)
    
    # Format message (NO INDIVIDUAL TRADE PRICES!)
    message = f"""
📊 DAILY PERFORMANCE REPORT - {yesterday.strftime('%B %d, %Y')}

✅ Total Profit: £{metrics['total_profit']:.2f}
📈 Win Rate: {metrics['win_rate']:.1f}%
💰 Profit Factor: {metrics['profit_factor']:.2f}
📉 Max Drawdown: {metrics['max_drawdown']:.2f}%

See attached charts for detailed analysis.
    """
    
    # Send to all subscribers
    subscribers = await get_all_subscribers()
    for user_id in subscribers:
        try:
            await bot.send_message(chat_id=user_id, text=message)
            await bot.send_photo(chat_id=user_id, photo=open(equity_chart, 'rb'))
            await bot.send_photo(chat_id=user_id, photo=open(heatmap, 'rb'))
        except Exception as e:
            logger.error(f"Failed to send report to {user_id}: {e}")

# Schedule daily at 9 AM
scheduler = AsyncIOScheduler()
scheduler.add_job(send_daily_report, 'cron', hour=9, minute=0)
scheduler.start()
```

### Acceptance Criteria
- [ ] All 15+ chart types generate correctly
- [ ] Equity curve shows cumulative returns
- [ ] Drawdown curve shows peak-to-trough
- [ ] Heatmap shows hour x day profitability
- [ ] Metrics calculate accurately
- [ ] Date range filtering works
- [ ] Daily/weekly/monthly reports send automatically
- [ ] Alerts trigger for >5% profit or >5% drawdown
- [ ] CSV/PDF export works
- [ ] Charts save to correct directory
- [ ] Matplotlib thread-safe (Agg backend)

---

## SUMMARY

### 6 New PRs Added
1. **PR-22a**: Content Distribution System (3 days) - 🔴 CRITICAL
2. **PR-24a**: Marketing Automation (4 days) - 🟡 HIGH
3. **PR-26b**: Live Exchange Rates (3 days) - 🔴 CRITICAL
4. **PR-32a**: Flask API Dashboard (5 days) - 🟢 MEDIUM
5. **PR-101a**: RSI-Fibonacci Strategy Engine (7 days) - 🔴 CRITICAL
6. **PR-160a**: Advanced Analytics System (6 days) - 🟡 HIGH

### Total Additional Time
- **28 days** (approximately 6 weeks)

### Updated Timeline
- **Original**: 224 PRs in 26 weeks
- **New**: 230 PRs in 27 weeks (added 1 week for buffer)

### Integration Plan
1. Insert PR-22a after PR-22 in New_Master_Prs.md
2. Insert PR-24a after PR-24 in New_Master_Prs.md
3. Insert PR-26b after PR-26 in New_Master_Prs.md
4. Insert PR-32a after PR-32 in New_Master_Prs.md
5. Insert PR-101a after PR-101 in New_Master_Prs.md
6. Insert PR-160a after PR-160 in New_Master_Prs.md
7. Update PROJECT_TRACKER.md (224→230)
8. Update all framework files (224→230)

---

**Ready to integrate these PRs into the master specification.**
