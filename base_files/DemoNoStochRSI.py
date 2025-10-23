import pandas as pd
import numpy as np
import MetaTrader5 as mt5
import sqlite3
import logging
import os
import asyncio
import requests
import telegram
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import uuid
from ta.momentum import RSIIndicator, ROCIndicator
from send_signal import send_signal


# Configuration
CONFIG = {
    'symbols': [
        {
            'name': 'GOLD',
            'fallback': 'XAUUSD',
            'log_file': 'GOLD_h1_log.txt',
            'is_forex': True,
            'timeframes': [
                {
                    'name': 'H1',
                    'mt5_timeframe': mt5.TIMEFRAME_H1,
                    'window_size': 200,
                    'main_bars': 1680,
                    'monitor_bars': 150
                }
            ]
        }
    ],
    'database': "gold_h1_trades.db",
    'risk_per_trade': 0.02,
    'rr_ratio': 3.25,
    'poll_interval': 60,
    'max_retries': 5,
    'retry_delay': 5,
    'min_stop_distance_points': 5,
    'order_expiry_hours': 100,
    'max_age_hours': 1440,
    'pip_value': 10,

    # ✅ New key: your signal forwarding API endpoint
    'signal_server_url': "http://127.0.0.1:8000/receive_signal"  # Replace with your production server URL
}


# Credentials
MT5_LOGIN = 590338389
MT5_PASSWORD = "!c7XzdfMWK"
MT5_SERVER = "FxPro-MT5 Demo"
MT5_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"
TELEGRAM_BOT_TOKEN = "8195080561:AAGX79Zt3OTt8X5AnNTovlm2mYN7F3izPLA"
TELEGRAM_USER_ID = "7336312249"

# Global variables
loggers = {}
validation_logs = []
bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
logger = None

# Setup logging
def setup_logging(symbol, log_file):
    logger = logging.getLogger(symbol)
    logger.setLevel(logging.DEBUG)
    file_handler = logging.FileHandler(log_file, mode='a')
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(console_handler)
    loggers[symbol] = logger
    return logger

# Initialize SQLite database
def init_database():
    try:
        conn = sqlite3.connect(CONFIG['database'])
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                trade_id TEXT PRIMARY KEY,
                setup_id TEXT,
                timeframe TEXT,
                trade_type TEXT,
                direction TEXT,
                entry_price REAL,
                exit_price REAL,
                take_profit REAL,
                stop_loss REAL,
                volume REAL,
                entry_time DATETIME,
                exit_time DATETIME,
                duration_hours REAL,
                profit REAL,
                pips REAL,
                risk_reward_ratio REAL,
                percent_equity_return REAL,
                exit_reason TEXT,
                status TEXT,
                symbol TEXT,
                strategy TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS equity (
                equity_id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME,
                balance REAL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS validation_logs (
                log_id TEXT PRIMARY KEY,
                trade_id TEXT,
                check_type TEXT,
                status TEXT,
                message TEXT,
                timestamp TEXT
            )
        ''')
        conn.commit()
        logger.info("Database initialized successfully")
    except sqlite3.Error as e:
        logger.error(f"Database initialization failed: {e}")
        raise
    finally:
        conn.close()

# Send Telegram message
async def send_telegram_message(bot, message, symbol):
    prefixed_message = f"[{symbol}] {message}"
    try:
        await bot.send_message(chat_id=TELEGRAM_USER_ID, text=prefixed_message)
        loggers[symbol].info(f"Telegram message sent: {prefixed_message}")
    except Exception as e:
        loggers[symbol].error(f"Failed to send Telegram message: {e}")

# Check market status
def is_market_open(symbol):
    now = datetime.now(ZoneInfo("America/New_York"))
    weekday = now.weekday()
    hour = now.hour
    if weekday == 4 and hour >= 17 or weekday == 5 or (weekday == 6 and hour < 17):
        loggers[symbol].warning("Market closed for GOLD (weekend)")
        return False
    return True

# Initialize MT5
async def init_mt5():
    global logger
    for symbol_config in CONFIG['symbols']:
        logger = setup_logging(symbol_config['name'], symbol_config['log_file'])
    
    if not mt5.initialize(path=MT5_PATH, login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
        logger.error(f"MT5 initialization failed: {mt5.last_error()}")
        await send_telegram_message(bot, f"MT5 initialization failed: {mt5.last_error()}", CONFIG['symbols'][0]['name'])
        return False
    
    terminal_info = mt5.terminal_info()
    if terminal_info and not terminal_info.trade_allowed:
        logger.warning("Algo trading disabled in MT5. Enable in Tools > Options > Expert Advisors.")
    
    for symbol_config in CONFIG['symbols']:
        symbol = symbol_config['name']
        fallback = symbol_config['fallback']
        logger = loggers[symbol]
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            logger.warning(f"Symbol {symbol} not found, trying fallback {fallback}")
            symbol_info = mt5.symbol_info(fallback)
            if symbol_info is None:
                logger.error(f"Fallback symbol {fallback} not found")
                continue
            symbol_config['name'] = fallback
        logger.info(f"Using symbol: {symbol_config['name']}")
    
    logger.info("MT5 initialized successfully")
    await send_telegram_message(bot, "Trading bot started for GOLD (H1)", CONFIG['symbols'][0]['name'])
    return True

# Fetch real-time data
def fetch_data(symbol, timeframe, num_bars, timeframe_name):
    logger = loggers[symbol]
    try:
        end_time = datetime.now(ZoneInfo("UTC"))
        logger.debug(f"Fetching {num_bars} bars for {symbol} on {timeframe_name} ending at {end_time}")
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, num_bars)
        if rates is None or len(rates) == 0:
            logger.warning(f"No data fetched for {symbol} on {timeframe_name}")
            return None
        
        df = pd.DataFrame(rates)
        df['datetime'] = pd.to_datetime(df['time'], unit='s', utc=True)
        df = df[['datetime', 'open', 'high', 'low', 'close', 'tick_volume', 'spread']]
        df.columns = ['datetime', 'OPEN', 'HIGH', 'LOW', 'CLOSE', 'TICKVOL', 'SPREAD']
        df.set_index('datetime', inplace=True)
        logger.debug(f"Fetched {len(df)} bars for {symbol} on {timeframe_name}")
        return df
    except Exception as e:
        logger.error(f"Error fetching data for {symbol} on {timeframe_name}: {e}")
        return None

# Calculate indicators
def calculate_indicators(df):
    logger = loggers[CONFIG['symbols'][0]['name']]
    if df.empty:
        logger.error("Input DataFrame is empty, cannot calculate indicators")
        return df
    
    rsi = RSIIndicator(df['CLOSE'], window=14).rsi()
    price_roc = ROCIndicator(df['CLOSE'], window=24).roc()
    rsi_roc = ROCIndicator(rsi, window=24).roc()
    
    df['RSI'] = rsi
    df['Price_ROC'] = price_roc
    df['RSI_ROC'] = rsi_roc
    
    df['RSI_ROC'] = df['RSI_ROC'].clip(-100, 100) / 100
    for lag in range(1, 4):
        df[f'RSI_ROC_lag{lag}'] = df['RSI_ROC'].shift(lag)
    
    df.dropna(inplace=True)
    
    if df['RSI'].isna().any():
        logger.warning(f"Found {df['RSI'].isna().sum()} NaN values in RSI column")
    
    window_size = CONFIG['symbols'][0]['timeframes'][0]['window_size']
    window_df = df.tail(window_size)[['OPEN', 'HIGH', 'LOW', 'CLOSE', 'RSI']].reset_index()
    csv_file = "GOLD_H1_window_data.csv"
    rsi_log_file = "GOLD_H1_rsi_log.txt"
    try:
        window_df.to_csv(csv_file, index=False)
        if not window_df['RSI'].isna().all():
            rsi_high, rsi_low = window_df['RSI'].max(), window_df['RSI'].min()
            high_rsi_row = window_df.loc[window_df['RSI'].idxmax()]
            low_rsi_row = window_df.loc[window_df['RSI'].idxmin()]
            rsi_summary = (
                f"H1 RSI Summary at {datetime.now(ZoneInfo('UTC')).isoformat()}:\n"
                f"Highest RSI: {rsi_high:.2f} at {high_rsi_row['datetime']} (Close: {high_rsi_row['CLOSE']:.5f})\n"
                f"Lowest RSI: {rsi_low:.2f} at {low_rsi_row['datetime']} (Close: {low_rsi_row['CLOSE']:.5f})\n"
            )
            logger.info(rsi_summary)
            with open(rsi_log_file, 'a') as f:
                f.write(rsi_summary + "\n")
        else:
            logger.warning("All RSI values are NaN in window, skipping RSI summary")
        logger.info(f"Updated H1 data in {csv_file}")
    except Exception as e:
        logger.error(f"Error updating {csv_file}: {e}")
    
    return df

# Validate Fibonacci levels
def validate_fib_levels(high_price, low_price, entry, stop_loss, trade_id, is_long):
    logger = loggers[CONFIG['symbols'][0]['name']]
    fib_range = high_price - low_price
    if fib_range <= 0:
        log = {
            'log_id': str(uuid.uuid4()),
            'trade_id': trade_id,
            'check_type': 'Fibonacci Range',
            'status': 'Failed',
            'message': f'Invalid Fibonacci range: {fib_range}, high_price: {high_price}, low_price: {low_price}',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        validation_logs.append(log)
        logger.debug(f"Validation failed: {log['message']}")
        return False
    expected_entry = high_price - fib_range * 0.74 if is_long else low_price + fib_range * 0.74
    expected_stop = low_price - fib_range * 0.27 if is_long else high_price + fib_range * 0.27
    checks = [
        (abs(entry - expected_entry) < 0.20, 'Entry Level', f'Entry {entry} != {expected_entry}'),
        (abs(stop_loss - expected_stop) < 0.20, 'Stop-Loss Level', f'Stop-Loss {stop_loss} != {expected_stop}')
    ]
    for valid, check, message in checks:
        if not valid:
            log = {
                'log_id': str(uuid.uuid4()),
                'trade_id': trade_id,
                'check_type': check,
                'status': 'Failed',
                'message': message,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            validation_logs.append(log)
            logger.debug(f"Validation failed: {log['message']}")
            return False
    return True

# Calculate target and risk-reward
def calculate_target_and_rr(entry, stop_loss, trade_id, is_long):
    logger = loggers[CONFIG['symbols'][0]['name']]
    risk = entry - stop_loss if is_long else stop_loss - entry
    if risk <= 0:
        log = {
            'log_id': str(uuid.uuid4()),
            'trade_id': trade_id,
            'check_type': 'Risk-Reward',
            'status': 'Failed',
            'message': f'Invalid risk {risk}',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        validation_logs.append(log)
        logger.debug(f"Risk-reward calculation failed: {log['message']}")
        return None, None
    reward = risk * CONFIG['rr_ratio']
    target = entry + reward if is_long else entry - reward
    rr_ratio = reward / risk
    rr_config = CONFIG['rr_ratio']
    if abs(rr_ratio - rr_config) > 0.1:
        log = {
            'log_id': str(uuid.uuid4()),
            'trade_id': trade_id,
            'check_type': 'Risk-Reward Ratio',
            'status': 'Warning',
            'message': f'Risk-reward ratio {rr_ratio:.2f} deviates from {rr_config}',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        validation_logs.append(log)
        logger.debug(f"Risk-reward warning: {log['message']}")
    return target, rr_ratio

# Calculate position size
def calculate_position_size(symbol, entry_price, stop_loss, risk_percent):
    logger = loggers[symbol]
    account_info = mt5.account_info()
    if not account_info:
        logger.error("Failed to get account info")
        return None
    account_balance = account_info.balance
    risk_amount = account_balance * risk_percent
    symbol_info = mt5.symbol_info(symbol)
    if not symbol_info:
        logger.error(f"Symbol {symbol} not found")
        return None
    tick_value = symbol_info.trade_tick_value
    point = symbol_info.point
    pip_distance = abs(entry_price - stop_loss) / point
    lot_size = (risk_amount / (pip_distance * tick_value)) / 100
    lot_size = round(lot_size, 2)
    volume_min = symbol_info.volume_min
    volume_max = symbol_info.volume_max
    volume_step = symbol_info.volume_step
    if volume_step > 0:
        lot_size = round(round(lot_size / volume_step) * volume_step, 8)
    lot_size = max(volume_min, min(lot_size, volume_max))
    logger.debug(f"Calculated volume: {lot_size:.2f} (min: {volume_min}, max: {volume_max}, step: {volume_step})")
    return lot_size

def send_signal_to_server(signal_data):
    try:
        response = requests.post(CONFIG['signal_server_url'], json=signal_data, timeout=10)
        if response.status_code == 200:
            loggers[CONFIG['symbols'][0]['name']].info(f"Signal sent to server: {signal_data['setup_id']}")
        else:
            loggers[CONFIG['symbols'][0]['name']].error(f"Failed to send signal: {response.status_code} - {response.text}")
    except Exception as e:
        loggers[CONFIG['symbols'][0]['name']].error(f"Exception sending signal to server: {e}")

# Execute trade
async def execute_trade(symbol, trade_type, volume, price, sl, tp, bot, timeframe_name, is_limit_order, setup_id, direction):
    logger = loggers[symbol]
    try:
        symbol_info = mt5.symbol_info(symbol)
        if not symbol_info:
            logger.error(f"Symbol {symbol} not found")
            return None
        point = symbol_info.point
        digits = symbol_info.digits
        min_stop_distance = CONFIG['min_stop_distance_points'] * point
        logger.debug(f"Using min_stop_distance: {min_stop_distance:.5f}")
        
        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            logger.error(f"Failed to get tick data for {symbol}")
            return None
        current_ask, current_bid = tick.ask, tick.bid
        
        if is_limit_order:
            if trade_type == mt5.ORDER_TYPE_BUY_LIMIT and price >= current_ask:
                price = current_ask - point * 10
                logger.warning(f"Adjusted buy limit price to {price:.5f}")
            if trade_type == mt5.ORDER_TYPE_SELL_LIMIT and price <= current_bid:
                price = current_bid + point * 10
                logger.warning(f"Adjusted sell limit price to {price:.5f}")
        else:
            price = current_ask if trade_type == mt5.ORDER_TYPE_BUY else current_bid
        
        sl = round(sl, digits)
        tp = round(tp, digits)
        price = round(price, digits)
        
        sl_distance = abs(price - sl)
        tp_distance = abs(price - tp)
        
        if sl_distance < min_stop_distance:
            original_sl = sl
            sl = price - min_stop_distance if trade_type == mt5.ORDER_TYPE_BUY_LIMIT else price + min_stop_distance
            sl = round(sl, digits)
            logger.warning(f"Adjusted SL from {original_sl:.5f} to {sl:.5f} to meet minimum stop distance {min_stop_distance:.5f}")
        
        if tp_distance < min_stop_distance:
            original_tp = tp
            tp = price + min_stop_distance if trade_type == mt5.ORDER_TYPE_BUY_LIMIT else price - min_stop_distance
            tp = round(tp, digits)
            logger.warning(f"Adjusted TP from {original_tp:.5f} to {tp:.5f} to meet minimum stop distance {min_stop_distance:.5f}")
        
        request = {
            "action": mt5.TRADE_ACTION_PENDING if is_limit_order else mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": trade_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": 20,
            "magic": 123456,
            "comment": "Live Trading Demo",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC
        }
        
        logger.debug(f"Trade request: {request}")
        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"Order failed: retcode={result.retcode}, comment={result.comment}")
            await send_telegram_message(bot, f"Order failed: {result.comment}", symbol)
            return None
        
        trade_msg = (
            f"{'Limit Order Placed' if is_limit_order else 'Trade Executed'} (H1)\n"
            f"Strategy: rsi_fibonacci\n"
            f"Symbol: {symbol}\n"
            f"Type: {'Buy' if trade_type == mt5.ORDER_TYPE_BUY_LIMIT else 'Sell'}\n"
            f"Direction: {direction}\n"
            f"Volume: {volume:.2f}\n"
            f"Price: {price:.5f}\n"
            f"Stop Loss: {sl:.5f}\n"
            f"Take Profit: {tp:.5f}\n"
            f"Order ID: {result.order}"
        )
        await send_telegram_message(bot, trade_msg, symbol)
        logger.info(f"Order processed: {trade_msg}")
        
        try:
            conn = sqlite3.connect(CONFIG['database'])
            cursor = conn.cursor()
            risk_reward = abs(tp - price) / abs(price - sl) if trade_type == mt5.ORDER_TYPE_BUY_LIMIT else abs(price - tp) / abs(sl - price)
            entry_time = datetime.now(ZoneInfo("UTC")).isoformat()
            cursor.execute('''
                INSERT INTO trades (
                    trade_id, setup_id, timeframe, trade_type, direction, entry_price, take_profit, stop_loss, volume,
                    entry_time, risk_reward_ratio, status, symbol, strategy
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                str(uuid.uuid4()), setup_id, timeframe_name, 'buy' if trade_type == mt5.ORDER_TYPE_BUY_LIMIT else 'sell',
                direction, price, tp, sl, volume, entry_time, risk_reward,
                'pending' if is_limit_order else 'executed', symbol, 'rsi_fibonacci'
            ))
            account_info = mt5.account_info()
            cursor.execute('''INSERT INTO equity (timestamp, balance) VALUES (?, ?)''', (entry_time, account_info.balance if account_info else 0.0))
            conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")
        finally:
            conn.close()
        
        return result.order
    except Exception as e:
        logger.error(f"Error executing trade: {e}")
        await send_telegram_message(bot, f"Error executing trade: {e}", symbol)
        return None

# Cancel order
async def cancel_order(symbol, order_id, bot, timeframe_name, reason="Expired"):
    logger = loggers[symbol]
    try:
        request = {
            "action": mt5.TRADE_ACTION_REMOVE,
            "order": order_id,
            "symbol": symbol
        }
        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"Failed to cancel order {order_id}: retcode={result.retcode}")
            return False
        
        msg = f"Limit Order Canceled (H1)\nSymbol: {symbol}\nOrder ID: {order_id}\nReason: {reason}"
        await send_telegram_message(bot, msg, symbol)
        logger.info(f"Order canceled: {msg}")
        
        try:
            conn = sqlite3.connect(CONFIG['database'])
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE trades SET status = 'canceled', exit_time = ?, exit_reason = ?
                WHERE order_id = ? AND status = 'pending'
            ''', (datetime.now(ZoneInfo("UTC")).isoformat(), reason, order_id))
            conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")
        finally:
            conn.close()
        return True
    except Exception as e:
        logger.error(f"Error canceling order {order_id}: {e}")
        return False

# Save validation log
def save_validation_log(log):
    logger = loggers[CONFIG['symbols'][0]['name']]
    try:
        conn = sqlite3.connect(CONFIG['database'])
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO validation_logs (log_id, trade_id, check_type, status, message, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            log['log_id'], log['trade_id'], log['check_type'], log['status'], log['message'], log['timestamp']
        ))
        conn.commit()
        logger.debug(f"Validation log saved: {log['log_id']}")
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
    finally:
        conn.close()

# Detect setups
async def detect_setups(df, window_size, timeframe_name, active_setups, symbol, active_trades, bot):
    logger = loggers[symbol]
    setups = []
    max_age = timedelta(hours=CONFIG['max_age_hours'])
    window = df.tail(window_size).copy()
    now = window.index.max()
    rsi_window_hours = 100
    latest_setup_time = None
    
    logger.debug(f"Starting setup detection for {symbol} on {timeframe_name}, window size: {len(window)}, latest time: {now}")
    
    if window.empty:
        logger.error("Window DataFrame is empty, cannot detect setups")
        return setups
    if window['RSI'].isna().all():
        logger.error("All RSI values are NaN, cannot detect setups")
        return setups
    
    logger.debug(f"RSI Statistics: count={window['RSI'].count()}, mean={window['RSI'].mean():.2f}, "
                 f"min={window['RSI'].min():.2f}, max={window['RSI'].max():.2f}")
    
    # Short setup (RSI > 70 to RSI <= 40)
    short_attempts = 0
    for i in range(1, len(window)):
        if window['RSI'].iloc[i-1] <= 70 and window['RSI'].iloc[i] > 70:
            short_attempts += 1
            rsi_high_start_time = window.index[i]
            rsi_high = window['RSI'].iloc[i]
            logger.debug(f"Short setup attempt {short_attempts}: RSI crossed above 70 at {rsi_high_start_time}, RSI={rsi_high:.2f}")
            
            rsi_high_period = window.loc[window.index[i]:][window['RSI'] > 70]
            if rsi_high_period.empty:
                logger.debug(f"Short setup {short_attempts}: No period found where RSI > 70 after {rsi_high_start_time}")
                continue
            price_high = rsi_high_period['HIGH'].max()
            price_high_time = rsi_high_period['HIGH'].idxmax()
            logger.debug(f"Short setup {short_attempts}: Highest price {price_high:.5f} at {price_high_time}")
            
            rsi_low_end_idx = None
            rsi_low_end_time = None
            for j in range(i + 1, min(i + rsi_window_hours + 1, len(window))):
                if (window.index[j] - rsi_high_start_time).total_seconds() / 3600 > rsi_window_hours:
                    break
                if window['RSI'].iloc[j] <= 40:
                    rsi_low_end_idx = j
                    rsi_low_end_time = window.index[j]
                    break
            
            if rsi_low_end_idx is None:
                log = {
                    'log_id': str(uuid.uuid4()),
                    'trade_id': str(uuid.uuid4()),
                    'check_type': 'RSI Window (Short)',
                    'status': 'Failed',
                    'message': f'No RSI <= 40 within {rsi_window_hours} hours after RSI > 70 at {rsi_high_start_time}',
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                validation_logs.append(log)
                logger.debug(f"Short setup {short_attempts}: {log['message']}")
                continue
            
            rsi_low_period = window.loc[window.index[rsi_low_end_idx]:][window['RSI'] <= 40]
            if rsi_low_period.empty:
                rsi_low_period = window.iloc[rsi_low_end_idx:rsi_low_end_idx+1]
            price_low = rsi_low_period['LOW'].min()
            if pd.isna(price_low):
                logger.debug(f"Short setup {short_attempts}: No valid low price found for RSI <= 40 period")
                continue
            price_low_time = rsi_low_period['LOW'].idxmax()
            rsi_low = window['RSI'].iloc[rsi_low_end_idx]
            logger.debug(f"Short setup {short_attempts}: Lowest price {price_low:.5f} at {price_low_time}, RSI={rsi_low:.2f}")
            
            time_diff = (price_low_time - price_high_time).total_seconds() / 3600
            age = (now - price_low_time).total_seconds() / 3600
            if time_diff > rsi_window_hours:
                log = {
                    'log_id': str(uuid.uuid4()),
                    'trade_id': str(uuid.uuid4()),
                    'check_type': 'Time Window (Short)',
                    'status': 'Failed',
                    'message': f'RSI <= 40 after {time_diff:.1f} hours (> {rsi_window_hours}) at {price_low_time}',
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                validation_logs.append(log)
                logger.debug(f"Short setup {short_attempts}: {log['message']}")
                continue
            if age > CONFIG['max_age_hours']:
                log = {
                    'log_id': str(uuid.uuid4()),
                    'trade_id': str(uuid.uuid4()),
                    'check_type': 'Setup Age (Short)',
                    'status': 'Failed',
                    'message': f'Setup age {age:.1f} hours (> {CONFIG["max_age_hours"]}) at {price_low_time}',
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                validation_logs.append(log)
                logger.debug(f"Short setup {short_attempts}: {log['message']}")
                continue
            if price_high <= price_low:
                log = {
                    'log_id': str(uuid.uuid4()),
                    'trade_id': str(uuid.uuid4()),
                    'check_type': 'Fibonacci Range (Short)',
                    'status': 'Failed',
                    'message': f'Invalid Fibonacci range: {price_high - price_low}, high_price: {price_high}, low_price: {price_low}',
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                validation_logs.append(log)
                logger.debug(f"Short setup {short_attempts}: {log['message']}")
                continue
            
            fib_range = price_high - price_low
            entry_price = price_low + fib_range * 0.74
            stop_loss = price_high + fib_range * 0.27
            trade_id = str(uuid.uuid4())
            
            logger.debug(f"Short setup {short_attempts}: Calculated entry={entry_price:.5f}, stop_loss={stop_loss:.5f}")
            
            if not validate_fib_levels(price_high, price_low, entry_price, stop_loss, trade_id, False):
                logger.debug(f"Short setup {short_attempts}: Failed Fibonacci validation")
                continue
            
            target, rr_ratio = calculate_target_and_rr(entry_price, stop_loss, trade_id, False)
            if target is None:
                logger.debug(f"Short setup {short_attempts}: Failed risk-reward calculation")
                continue
            
            setup_id = f"{symbol}_H1_short_{price_low_time.isoformat()}"
            setup = {
                'type': 'short',
                'strategy': 'rsi_fibonacci',
                'point1_idx': window.index.get_loc(rsi_high_start_time),
                'point1_datetime': rsi_high_start_time,
                'point1_price': price_high,
                'point1_rsi': rsi_high,
                'point2_idx': window.index.get_loc(rsi_low_end_time),
                'point2_datetime': price_low_time,
                'point2_price': price_low,
                'point2_rsi': rsi_low,
                'fib_data': {'entry': entry_price, 'stop_loss': stop_loss, 'target': target},
                'stop_loss': stop_loss,
                'risk_per_trade': CONFIG['risk_per_trade'],
                'setup_id': setup_id
            }
            setups.append(setup)
            log_msg = (
                f"[RSI-Fib] H1: New Short Setup\n"
                f"High RSI: Price={price_high:.5f}, RSI={rsi_high:.2f}, Time={rsi_high_start_time}\n"
                f"Low RSI: Price={price_low:.5f}, RSI={rsi_low:.2f}, Time={price_low_time}\n"
                f"Entry: {entry_price:.5f}\n"
                f"Stop Loss: {stop_loss:.5f}\n"
                f"Take Profit: {target:.5f}"
            )
            await send_telegram_message(bot, log_msg, symbol)
            logger.info(log_msg)
            latest_setup_time = price_low_time
    
    logger.debug(f"Total short setup attempts: {short_attempts}")
    
    # Long setup (RSI < 40 to RSI >= 70)
    long_attempts = 0
    for i in range(1, len(window)):
        if window['RSI'].iloc[i-1] >= 40 and window['RSI'].iloc[i] < 40:
            long_attempts += 1
            rsi_low_start_time = window.index[i]
            rsi_low = window['RSI'].iloc[i]
            logger.debug(f"Long setup attempt {long_attempts}: RSI crossed below 40 at {rsi_low_start_time}, RSI={rsi_low:.2f}")
            
            rsi_low_period = window.loc[window.index[i]:][window['RSI'] < 40]
            if rsi_low_period.empty:
                logger.debug(f"Long setup {long_attempts}: No period found where RSI < 40 after {rsi_low_start_time}")
                continue
            price_low = rsi_low_period['LOW'].min()
            if pd.isna(price_low):
                logger.debug(f"Long setup {long_attempts}: No valid low price found for RSI < 40 period")
                continue
            price_low_time = rsi_low_period['LOW'].idxmin()
            logger.debug(f"Long setup {long_attempts}: Lowest price {price_low:.5f} at {price_low_time}")
            
            rsi_high_end_idx = None
            rsi_high_end_time = None
            for j in range(i + 1, min(i + rsi_window_hours + 1, len(window))):
                if (window.index[j] - rsi_low_start_time).total_seconds() / 3600 > rsi_window_hours:
                    break
                if window['RSI'].iloc[j] >= 70:
                    rsi_high_end_idx = j
                    rsi_high_end_time = window.index[j]
                    break
            
            if rsi_high_end_idx is None:
                log = {
                    'log_id': str(uuid.uuid4()),
                    'trade_id': str(uuid.uuid4()),
                    'check_type': 'RSI Window (Long)',
                    'status': 'Failed',
                    'message': f'No RSI >= 70 within {rsi_window_hours} hours after RSI < 40 at {rsi_low_start_time}',
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                validation_logs.append(log)
                logger.debug(f"Long setup {long_attempts}: {log['message']}")
                continue
            
            rsi_high_period = window.loc[window.index[rsi_high_end_idx]:][window['RSI'] >= 70]
            if rsi_high_period.empty:
                rsi_high_period = window.iloc[rsi_high_end_idx:rsi_high_end_idx+1]
            price_high = rsi_high_period['HIGH'].max()
            if pd.isna(price_high):
                logger.debug(f"Long setup {long_attempts}: No valid high price found for RSI >= 70 period")
                continue
            price_high_time = rsi_high_period['HIGH'].idxmax()
            rsi_high = window['RSI'].iloc[rsi_high_end_idx]
            logger.debug(f"Long setup {long_attempts}: Highest price {price_high:.5f} at {price_high_time}, RSI={rsi_high:.2f}")
            
            time_diff = (price_high_time - price_low_time).total_seconds() / 3600
            age = (now - price_high_time).total_seconds() / 3600
            if time_diff > rsi_window_hours:
                log = {
                    'log_id': str(uuid.uuid4()),
                    'trade_id': str(uuid.uuid4()),
                    'check_type': 'Time Window (Long)',
                    'status': 'Failed',
                    'message': f'RSI >= 70 after {time_diff:.1f} hours (> {rsi_window_hours}) at {price_high_time}',
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                validation_logs.append(log)
                logger.debug(f"Long setup {long_attempts}: {log['message']}")
                continue
            if age > CONFIG['max_age_hours']:
                log = {
                    'log_id': str(uuid.uuid4()),
                    'trade_id': str(uuid.uuid4()),
                    'check_type': 'Setup Age (Long)',
                    'status': 'Failed',
                    'message': f'Setup age {age:.1f} hours (> {CONFIG["max_age_hours"]}) at {price_high_time}',
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                validation_logs.append(log)
                logger.debug(f"Long setup {long_attempts}: {log['message']}")
                continue
            if price_high <= price_low:
                log = {
                    'log_id': str(uuid.uuid4()),
                    'trade_id': str(uuid.uuid4()),
                    'check_type': 'Fibonacci Range (Long)',
                    'status': 'Failed',
                    'message': f'Invalid Fibonacci range: {price_high - price_low}, high_price: {price_high}, low_price: {price_low}',
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                validation_logs.append(log)
                logger.debug(f"Long setup {long_attempts}: {log['message']}")
                continue
            
            fib_range = price_high - price_low
            entry_price = price_high - fib_range * 0.74
            stop_loss = price_low - fib_range * 0.27
            trade_id = str(uuid.uuid4())
            
            logger.debug(f"Long setup {long_attempts}: Calculated entry={entry_price:.5f}, stop_loss={stop_loss:.5f}")
            
            if not validate_fib_levels(price_high, price_low, entry_price, stop_loss, trade_id, True):
                logger.debug(f"Long setup {long_attempts}: Failed Fibonacci validation")
                continue
            
            target, rr_ratio = calculate_target_and_rr(entry_price, stop_loss, trade_id, True)
            if target is None:
                logger.debug(f"Long setup {long_attempts}: Failed risk-reward calculation")
                continue
            
            # Only keep the most recent setup to avoid duplicates
            if latest_setup_time and price_high_time <= latest_setup_time:
                logger.debug(f"Long setup {long_attempts}: Skipped, older than latest setup at {latest_setup_time}")
                continue
            
            setup_id = f"{symbol}_H1_long_{price_high_time.isoformat()}"
            setup = {
                'type': 'long',
                'strategy': 'rsi_fibonacci',
                'point1_idx': window.index.get_loc(rsi_low_start_time),
                'point1_datetime': rsi_low_start_time,
                'point1_price': price_low,
                'point1_rsi': rsi_low,
                'point2_idx': window.index.get_loc(rsi_high_end_time),
                'point2_datetime': price_high_time,
                'point2_price': price_high,
                'point2_rsi': rsi_high,
                'fib_data': {'entry': entry_price, 'stop_loss': stop_loss, 'target': target},
                'stop_loss': stop_loss,
                'risk_per_trade': CONFIG['risk_per_trade'],
                'setup_id': setup_id
            }
            setups.append(setup)
            log_msg = (
                f"[RSI-Fib] H1: New Long Setup\n"
                f"Low RSI: Price={price_low:.5f}, RSI={rsi_low:.2f}, Time={rsi_low_start_time}\n"
                f"High RSI: Price={price_high:.5f}, RSI={rsi_high:.2f}, Time={price_high_time}\n"
                f"Entry: {entry_price:.5f}\n"
                f"Stop Loss: {stop_loss:.5f}\n"
                f"Take Profit: {target:.5f}"
            )
            await send_telegram_message(bot, log_msg, symbol)
            logger.info(log_msg)
            latest_setup_time = price_high_time
    
    logger.debug(f"Total long setup attempts: {long_attempts}")
    
    if not setups:
        logger.debug(f"No setups found within {CONFIG['max_age_hours']} hours")
    else:
        logger.debug(f"Found {len(setups)} setups: {len([s for s in setups if s['type'] == 'long'])} long, {len([s for s in setups if s['type'] == 'short'])} short")
    
    return setups

# Monitor trades
async def monitor_trades(df, symbol, active_trades, active_setups, bot, timeframe_name, monitor_bars):
    logger = loggers[symbol]
    logger.debug(f"Monitoring H1")
    symbol_info = mt5.symbol_info(symbol)
    if not symbol_info:
        logger.error(f"Symbol {symbol} not found")
        return

    setups = await detect_setups(df, CONFIG['symbols'][0]['timeframes'][0]['window_size'], timeframe_name, active_setups, symbol, active_trades, bot)

    for setup in setups:
        is_long = setup['type'] == 'long'
        direction = 'buy' if is_long else 'sell'
        trade_type = mt5.ORDER_TYPE_BUY_LIMIT if is_long else mt5.ORDER_TYPE_SELL_LIMIT
        point2_time = setup['point2_datetime']
        setup_id = setup['setup_id']
        active_key = f"{symbol}_H1_{setup['type']}"

        if active_key in active_setups and active_setups[active_key]['point2_datetime'] >= point2_time:
            logger.debug(f"H1: Skipping {setup['type']} setup, active setup at {active_setups[active_key]['point2_datetime']}")
            continue

        for trade_key in list(active_trades.keys()):
            if (active_trades[trade_key]['timeframe'] == timeframe_name and 
                active_trades[trade_key]['direction'] == direction and 
                active_trades[trade_key]['symbol'] == symbol):
                await cancel_order(symbol, active_trades[trade_key]['order_id'], bot, timeframe_name, reason="New Setup")
                del active_trades[trade_key]

        active_setups[active_key] = setup
        fib_data = setup['fib_data']

        volume = calculate_position_size(symbol, fib_data['entry'], fib_data['stop_loss'], CONFIG['risk_per_trade'])
        if volume is None:
            logger.debug(f"Failed to calculate position size for {setup['type']} setup {setup_id}")
            continue

        try:
            order_id = await execute_trade(
                symbol=symbol,
                trade_type=trade_type,
                volume=volume,
                price=fib_data['entry'],
                sl=fib_data['stop_loss'],
                tp=fib_data['target'],
                bot=bot,
                timeframe_name=timeframe_name,
                is_limit_order=True,
                setup_id=setup_id,
                direction=direction
            )

            if order_id:
                active_trades[setup_id] = {
                    'order_id': order_id,
                    'order_type': 'pending',
                    'entry_price': fib_data['entry'],
                    'stop_loss': fib_data['stop_loss'],
                    'take_profit': fib_data['target'],
                    'position_size': volume,
                    'type': 'buy' if is_long else 'sell',
                    'timeframe': timeframe_name,
                    'trigger_time': datetime.now(ZoneInfo("UTC")),
                    'setup_time': point2_time,
                    'point1_price': setup['point1_price'],
                    'point2_price': setup['point2_price'],
                    'setup_id': setup_id,
                    'symbol': symbol,
                    'strategy': 'rsi_fibonacci',
                    'direction': direction
                }
                logger.debug(f"Placed {setup['type']} trade, order_id={order_id}, setup_id={setup_id}")

                # === NEW: Send signal to external server ===
                try:
                    signal_data = {
                        'setup_id': setup_id,
                        'symbol': symbol,
                        'direction': direction,
                        'entry_price': fib_data['entry'],
                        'stop_loss': fib_data['stop_loss'],
                        'take_profit': fib_data['target'],
                        'volume': volume,
                        'strategy': setup['strategy'],
                        'timeframe': timeframe_name,
                        'timestamp': datetime.now(ZoneInfo("UTC")).isoformat()
                    }
                    import requests
                    signal_url = CONFIG.get("signal_server_url", "http://127.0.0.1:8000/receive_signal")
                    response = requests.post(signal_url, json=signal_data, timeout=10)
                    if response.status_code == 200:
                        logger.info(f"Signal sent to server: {setup_id}")
                    else:
                        logger.error(f"Failed to send signal to server: {response.status_code} - {response.text}")
                except Exception as ex:
                    logger.error(f"Error sending signal to server: {ex}")

        except Exception as e:
            logger.error(f"Error placing {setup['type']} order: {e}")
            await send_telegram_message(bot, f"Error placing {setup['type']} order: {e}", symbol)


# Check trade status
async def check_trade_status(active_trades, active_setups, bot, symbol):
    logger = loggers[symbol]
    retries = CONFIG['max_retries']
    retry_delay = CONFIG['retry_delay']
    
    for attempt in range(retries):
        try:
            orders = mt5.orders_get(symbol=symbol) or []
            positions = mt5.positions_get(symbol=symbol) or []
            tick = mt5.symbol_info_tick(symbol)
            
            if not tick:
                logger.warning(f"Failed to retrieve MT5 data for {symbol}, attempt {attempt + 1}/{retries}")
                if attempt < retries - 1:
                    await asyncio.sleep(retry_delay)
                    continue
                logger.error(f"Max retries reached for {symbol}")
                return
            
            current_price = tick.bid
            symbol_info = mt5.symbol_info(symbol)
            point = symbol_info.point
            current_time = datetime.now(ZoneInfo("UTC"))
            expiry_threshold = timedelta(hours=CONFIG['order_expiry_hours'])
            
            for trade_key, trade_info in list(active_trades.items()):
                if trade_info['symbol'] != symbol:
                    continue
                order_id = trade_info['order_id']
                timeframe_name = trade_info['timeframe']
                
                if trade_info['order_type'] == 'pending':
                    order_found = any(order.ticket == order_id for order in orders)
                    if not order_found:
                        for pos in positions:
                            if pos.ticket == order_id:
                                trade_info['order_type'] = 'executed'
                                trade_info['entry_time'] = current_time.isoformat()
                                trade_info['position_size'] = pos.volume
                                try:
                                    conn = sqlite3.connect(CONFIG['database'])
                                    cursor = conn.cursor()
                                    cursor.execute('''
                                        UPDATE trades SET status = 'executed', entry_time = ?, volume = ?
                                        WHERE setup_id = ? AND status = 'pending'
                                    ''', (current_time.isoformat(), pos.volume, trade_info['setup_id']))
                                    conn.commit()
                                except sqlite3.Error as e:
                                    logger.error(f"Database error: {e}")
                                finally:
                                    conn.close()
                                logger.debug(f"Order {order_id} transitioned to executed, setup_id={trade_info['setup_id']}")
                                break
                        else:
                            history = mt5.history_deals_get(position=order_id)
                            if history:
                                last_deal = history[-1]
                                exit_price = last_deal.price
                                profit = last_deal.profit
                                exit_time = datetime.fromtimestamp(last_deal.time, tz=ZoneInfo("UTC"))
                                entry_time = trade_info.get('entry_time', trade_info['trigger_time'].isoformat())
                                duration = (exit_time - datetime.fromisoformat(entry_time)).total_seconds() / 3600
                                pips = (exit_price - trade_info['entry_price']) / point * 10 if trade_info['direction'] == 'buy' else (trade_info['entry_price'] - exit_price) / point * 10
                                account_info = mt5.account_info()
                                balance = account_info.balance if account_info else 0.0
                                percent_return = (profit / balance) * 100 if balance > 0 else 0
                                exit_reason = 'take_profit' if abs(exit_price - trade_info['take_profit']) < point * 10 else 'stop_loss'
                                
                                try:
                                    conn = sqlite3.connect(CONFIG['database'])
                                    cursor = conn.cursor()
                                    cursor.execute('''
                                        UPDATE trades
                                        SET status = 'closed', exit_time = ?, exit_price = ?, exit_reason = ?, profit = ?, pips = ?, percent_equity_return = ?
                                        WHERE setup_id = ? AND status = 'pending'
                                    ''', (exit_time.isoformat(), exit_price, exit_reason, profit, pips, percent_return, trade_info['setup_id']))
                                    conn.commit()
                                except sqlite3.Error as e:
                                    logger.error(f"Database error: {e}")
                                finally:
                                    conn.close()
                                
                                msg = (
                                    f"Pending Order Closed (H1)\n"
                                    f"Symbol: {symbol}\n"
                                    f"Order ID: {order_id}\n"
                                    f"Reason: {exit_reason.title()}"
                                )
                                await send_telegram_message(bot, msg, symbol)
                                logger.debug(f"Closed pending order {order_id}, reason={exit_reason}, setup_id={trade_info['setup_id']}")
                                del active_trades[trade_key]
                                active_key = f"{symbol}_H1_{trade_info['type']}"
                                if active_key in active_setups and active_setups[active_key]['point2_datetime'] == trade_info['setup_time']:
                                    del active_setups[active_key]
                            else:
                                logger.warning(f"Order {order_id} not found, assuming closed")
                                del active_trades[trade_key]
                                active_key = f"{symbol}_H1_{trade_info['type']}"
                                if active_key in active_setups and active_setups[active_key]['point2_datetime'] == trade_info['setup_time']:
                                    del active_setups[active_key]
                    else:
                        age = current_time - trade_info['trigger_time']
                        if age > expiry_threshold:
                            if await cancel_order(symbol, order_id, bot, timeframe_name, reason="Expired"):
                                del active_trades[trade_key]
                                active_key = f"{symbol}_H1_{trade_info['type']}"
                                if active_key in active_setups and active_setups[active_key]['point2_datetime'] == trade_info['setup_time']:
                                    del active_setups[active_key]
                                logger.debug(f"Order {order_id} expired, setup_id={trade_info['setup_id']}")
                
                else:
                    position_found = any(pos.ticket == order_id for pos in positions)
                    if not position_found:
                        history = mt5.history_deals_get(position=order_id)
                        if history:
                            last_deal = history[-1]
                            exit_price = last_deal.price
                            profit = last_deal.profit
                            exit_time = datetime.fromtimestamp(last_deal.time, tz=ZoneInfo("UTC"))
                            entry_time = trade_info.get('entry_time', trade_info['trigger_time'].isoformat())
                            duration = (exit_time - datetime.fromisoformat(entry_time)).total_seconds() / 3600
                            pips = (exit_price - trade_info['entry_price']) / point * 10 if trade_info['direction'] == 'buy' else (trade_info['entry_price'] - exit_price) / point * 10
                            account_info = mt5.account_info()
                            balance = account_info.balance if account_info else 0.0
                            percent_return = (profit / balance) * 100 if balance > 0 else 0
                            exit_reason = 'take_profit' if abs(exit_price - trade_info['take_profit']) < point * 10 else 'stop_loss'
                            
                            try:
                                conn = sqlite3.connect(CONFIG['database'])
                                cursor = conn.cursor()
                                cursor.execute('''
                                    UPDATE trades
                                    SET exit_price = ?, exit_time = ?, duration_hours = ?, profit = ?, pips = ?,
                                        percent_equity_return = ?, exit_reason = ?, status = 'closed'
                                    WHERE setup_id = ? AND status = 'executed'
                                ''', (exit_price, exit_time.isoformat(), duration, profit, pips, percent_return, exit_reason, trade_info['setup_id']))
                                cursor.execute('''INSERT INTO equity (timestamp, balance) VALUES (?, ?)''', (exit_time.isoformat(), balance))
                                conn.commit()
                            except sqlite3.Error as e:
                                logger.error(f"Database error: {e}")
                            finally:
                                conn.close()
                            
                            msg = (
                                f"Trade Closed (H1)\n"
                                f"Strategy: rsi_fibonacci\n"
                                f"Symbol: {symbol}\n"
                                f"Type: {trade_info['direction'].capitalize()}\n"
                                f"Entry Price: {trade_info['entry_price']:.5f}\n"
                                f"Exit Price: {exit_price:.5f}\n"
                                f"Profit: {profit:.2f}\n"
                                f"Pips: {pips:.2f}\n"
                                f"Outcome: {exit_reason.title()}"
                            )
                            await send_telegram_message(bot, msg, symbol)
                            logger.debug(f"Closed executed trade {order_id}, reason={exit_reason}, setup_id={trade_info['setup_id']}")
                            del active_trades[trade_key]
                            active_key = f"{symbol}_H1_{trade_info['type']}"
                            if active_key in active_setups and active_setups[active_key]['point2_datetime'] == trade_info['setup_time']:
                                del active_setups[active_key]
                        else:
                            logger.warning(f"Position {order_id} not found, assuming closed")
                            del active_trades[trade_key]
                            active_key = f"{symbol}_H1_{trade_info['type']}"
                            if active_key in active_setups and active_setups[active_key]['point2_datetime'] == trade_info['setup_time']:
                                del active_setups[active_key]
            break
        except Exception as e:
            logger.error(f"Error checking trade status, attempt {attempt + 1}/{retries}: {e}")
            if attempt < retries - 1:
                await asyncio.sleep(retry_delay)
            else:
                logger.error(f"Max retries reached for {symbol}")

# Main trading loop
async def main():
    global validation_logs, bot, logger
    validation_logs = []
    bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
    
    if not await init_mt5():
        return
    
    init_database()
    
    symbol_info = CONFIG['symbols'][0]
    symbol = symbol_info['name']
    timeframe = symbol_info['timeframes'][0]
    mt5_timeframe = timeframe['mt5_timeframe']
    window_size = timeframe['window_size']
    main_bars = timeframe['main_bars']
    monitor_bars = timeframe['monitor_bars']
    timeframe_name = timeframe['name']
    
    if not mt5.symbol_select(symbol, True):
        logger.error(f"Failed to select symbol {symbol}")
        await send_telegram_message(bot, f"Failed to select symbol {symbol}", symbol)
        return
    
    active_trades = {}
    active_setups = {}
    last_processed_time = None
    
    while True:
        try:
            if not is_market_open(symbol):
                logger.warning(f"Skipping {symbol} due to market closure")
                await asyncio.sleep(CONFIG['poll_interval'])
                continue
            
            df = fetch_data(symbol, mt5_timeframe, main_bars, timeframe_name)
            if df is None or df.empty:
                logger.warning(f"No data for {timeframe_name}")
                await asyncio.sleep(CONFIG['poll_interval'])
                continue
            
            df = calculate_indicators(df)
            current_time = df.index[-1]
            if last_processed_time == current_time:
                await asyncio.sleep(CONFIG['poll_interval'])
                continue
            
            last_processed_time = current_time
            logger.info(f"Processing data up to {current_time}")
            
            await monitor_trades(df, symbol, active_trades, active_setups, bot, timeframe_name, monitor_bars)
            await check_trade_status(active_trades, active_setups, bot, symbol)
            
            for log in validation_logs:
                save_validation_log(log)
            validation_logs.clear()
            
            await asyncio.sleep(CONFIG['poll_interval'])
        
        except Exception as e:
            logger.error(f"Main loop error: {e}")
            await send_telegram_message(bot, f"Error in bot: {e}", symbol)
            await asyncio.sleep(CONFIG['poll_interval'])

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    asyncio.run(main())