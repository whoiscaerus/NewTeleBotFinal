# === Real-Time MT5 PPO Trading Bot for GOLD with Enhanced Telegram Features ===
# Version: 2025-04-30
# Features:
# - Supports date range filtering for equity curves, drawdown curves, trade history, and analytics
# - Alerts for monthly profit > 5% and drawdown > 5% from peak
# - Future equity outlook projection
# - Heatmap of trades, feature importance, pause/resume, win rate, heartbeat, period comparison, CSV export, return stats, decision log
# - Trade decisions aligned with 15-minute candle formation
# - Configurable trade decision notifications via Telegram
# Fixes:
# - Uses Matplotlib 'Agg' backend to resolve threading issues
# - Ensures proper figure closure to prevent resource leaks
# - Added /alert command implementation
# - Enhanced Telegram instructions
# - Fixed observation shape for PPO model
# - Removed trade confidence features
# - Implemented all-in position sizing
# - Fixed MinMaxScaler feature names warning
# - Restored console output for decisions
# - Adjusted prediction threshold for more frequent trading
# - Fixed equity calculation by updating EXCHANGE_RANGE to 1.0 (April 25, 2025)
# - Added debug logging for raw and converted equity in execute_trade
# - Removed duplicate compute_analytics function
# - Fixed SQLite timestamp parameter binding
# - Enhanced error handling in fetch_market_data
# - Improved file path consistency using os.path.join
# - Added thread safety for heartbeat notifications
# - Migrated CSV logging to SQLite for trades, predictions, and decisions
# Additional Fixes Applied:
# - Corrected feature name "Close THERE" to "Close"
# - Enhanced thread safety with heartbeat_lock
# - Standardized logging using logging module instead of print
# - Added comprehensive error handling
# - Added docstrings for major functions
# - Included type hints for better readability
# - Ensured resource management with 'with' statements
# - Refactored execute_trade for clarity and to strictly follow PPO model predictions
# - Added new candle detection for 15-minute intervals
# - Added notification toggle for trade decisions
# Updates in this Version:
# - Modified database interactions to use SQLAlchemy engine instead of sqlite3.connect for consistency
# - Fixed SQL execution in execute_trade and log_trade using sqlalchemy.text
# - Added detailed logging to main trading loop for debugging
# - Removed duplicate directory creation block
# New Fixes in this Update:
# - Increased CANDLE_CHECK_WINDOW to 30 seconds to improve 15-minute candle detection
# - Reduced CHECK_INTERVAL to 10 seconds for more frequent checks
# - Moved command queue processing outside candle detection to ensure timely report delivery
# - Set logging level to DEBUG for better visibility
# - Added engine.dispose() and sys.exit(0) to ensure proper script termination
# - Added timeout to Telegram API requests to prevent hanging
# Latest Fixes:
# - Updated database interactions to handle timestamp as DateTime instead of String
# - Adjusted schema to use auto-incrementing id as primary key in models.py
# - Ensured compatibility with updated models.py where predictions table now has a symbol column
# New Additions in this Update:
# - Added /help command and inline button to provide detailed command explanations
# Fixes in this Update:
# - Handle empty trade logs gracefully in chart generation functions
# - Increased Telegram polling timeout to 30 seconds with retry logic
# - Updated main loop to handle None chart paths when trade log is empty
# Fixes in this Update (2025-04-28):
# - Fixed /help command and "Help" inline button by restructuring get_help_message() to return a list of sections
# - Updated notify() to handle lists of messages for better Telegram compatibility
# - Removed duplicate get_help_message() function
# Fixes in this Update (2025-04-30):
# - Added circuit breaker pattern to handle network switches (mobile data to Wi-Fi)
# - Increased Telegram API timeouts (connect timeout to 15s, read timeout to 45s)
# - Throttled check_alerts() to run every 15 minutes instead of every 10 seconds to reduce trade log warnings
# Fixes in this Update (2025-05-01):
# - Increased CANDLE_CHECK_WINDOW to 60 seconds for more lenient candle detection
# - Added debug logging in is_new_candle() to track candle timestamps and time differences
# - Added periodic logging of trading state in the main loop
# - Moved command processing after trading logic to prioritize candle checks

import MetaTrader5 as mt5
import pandas as pd
import pytz
import numpy as np
import time
import requests
from sklearn.preprocessing import MinMaxScaler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from stable_baselines3 import PPO
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.helpers import escape_markdown
from flask import Flask, jsonify
import torch
import joblib
import os
import matplotlib
matplotlib.use('Agg')  # Use non-GUI backend to avoid threading issues
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime, timedelta
import logging
import threading
import queue
import sys
import psutil  # For Bot Health Check
import json
from typing import Optional, Tuple, List, Dict, Any
from sqlalchemy import create_engine, text
from models import Base
from typing import Optional, Tuple, List, Dict, Any, Union

# === CONFIG ===
VERBOSE: bool = True
SYMBOL: str = "GOLD"
TIMEFRAME: int = mt5.TIMEFRAME_M15
SEQUENCE_LENGTH: int = 50
CHECK_INTERVAL: int = 10  # Main loop check interval (seconds)
CANDLE_CHECK_WINDOW: int = 60  # ±60 seconds around 15-minute mark (increased for better detection)
ALERT_CHECK_INTERVAL: int = 900  # Check alerts every 15 minutes (900 seconds)
FEATURES: List[str] = [
    "Close_15M", "Volume_15M", "Close_4H", "Volume_4H", "Close", "Volume",
    "RSI_4H", "ATR_4H", "RSI_Daily", "ATR_Daily", "pivot", "r1", "s1", "r2", "s2"
]
EXCHANGE_RATE: float = 1.0  # USD to GBP (Updated to 1.0 on April 25, 2025)
MIN_POSITION_SIZE: float = 0.01
TRADE_DB_PATH: str = os.path.join("C:\\", "Users", "FCumm", "FxPRO", "Grok", "Live", "New", "Live Output", "trades.db")
ANALYTICS_REPORT_PATH: str = os.path.join("C:\\", "Users", "FCumm", "FxPRO", "Grok", "Live", "New", "analytics_report.txt")
PLOT_PATH: str = os.path.join("C:\\", "Users", "FCumm", "FxPRO", "Grok", "Live", "New", "plots")
EXPORT_PATH: str = os.path.join("C:\\", "Users", "FCumm", "FxPRO", "Grok", "Live", "New", "exports")
ANALYTICS_INTERVAL: int = 86400  # 24 hours
REPORT_INTERVAL: int = 4 * 3600  # 4 hours for scheduled reports
MAX_DRAWDOWN_THRESHOLD: float = 0.1  # 10% max drawdown
MIN_EQUITY_THRESHOLD: float = 500.0  # Minimum equity in GBP

# === Network Resilience Config ===
TELEGRAM_MAX_FAILURES: int = 5  # Max consecutive failures before circuit breaker trips
TELEGRAM_BACKOFF_TIME: int = 300  # Backoff time in seconds (5 minutes) after circuit breaker trips
MT5_MAX_FAILURES: int = 5  # Max consecutive MT5 connection failures
MT5_BACKOFF_TIME: int = 300  # Backoff time in seconds (5 minutes) after MT5 circuit breaker trips

# === Database Setup with SQLAlchemy ===
try:
    engine = create_engine(f"sqlite:///{TRADE_DB_PATH}", pool_size=5, max_overflow=10)
    logging.info("SQLAlchemy engine created successfully.")
    print("SQLAlchemy engine created successfully.")
except Exception as e:
    print(f"Failed to create SQLAlchemy engine: {e}")
    logging.error(f"Failed to create SQLAlchemy engine: {e}")
    sys.exit(1)

# === Setup Logging ===
try:
    log_dir: str = os.path.join("C:\\", "Users", "FCumm", "FxPRO", "Grok", "Live", "New")
    os.makedirs(log_dir, exist_ok=True)
    print(f"Log directory ensured: {log_dir}")
    timestamp: str = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file: str = os.path.join(log_dir, f"trading_bot_{timestamp}.log")
    print(f"Attempting to create log file: {log_file}")
    logging.basicConfig(
        filename=log_file,
        filemode='w',
        level=logging.DEBUG,  # Changed to DEBUG for more detailed logging
        format='%(asctime)s - %(levelname)s - %(message)s',
        force=True  # Force logging to override any existing handlers
    )
    # Force flush after initial log
    logging.info("Logging configured successfully.")
    logging.getLogger().handlers[0].flush()  # Flush the log to ensure it's written
    print("Logging configured successfully.")
except Exception as e:
    print(f"Failed to configure logging: {e}")
    logging.error(f"Failed to configure logging: {e}")
    sys.exit(1)

# === Ensure Output Directories Exist ===
try:
    os.makedirs(PLOT_PATH, exist_ok=True)
    os.makedirs(EXPORT_PATH, exist_ok=True)
    logging.info(f"Directories ensured: {PLOT_PATH}, {EXPORT_PATH}")
    print(f"Directories ensured: {PLOT_PATH}, {EXPORT_PATH}")
except Exception as e:
    error_msg = f"Failed to create directories: {e}"
    print(error_msg)
    logging.error(error_msg)
    sys.exit(1)

# === MT5 Login Info ===
MT5_LOGIN: int = 590338389
MT5_PASSWORD: str = "!c7XzdfMWK"
MT5_SERVER: str = "FxPro-MT5 Demo"
MT5_PATH = r"C:\\Program Files\\MetaTrader 5\\terminal64.exe"

# === Telegram Bot Info ===
TELEGRAM_BOT_TOKEN: str = "8195080561:AAF8TPQwr0jRMmWM2cE09Ddkn3-yFpacTX4"
TELEGRAM_USER_ID: str = "7336312249"

# === Load Model and Scaler Paths ===
model_path = r"C:\\Users\\FCumm\\FxPRO\\Grok\\New\\LSTM_PPO_TradingAgent.zip"
scaler_path = r"C:\\Users\\FCumm\\FxPRO\\Grok\\New\\minmax_scaler_exported.pkl"

# === Global Variables ===
command_queue: queue.Queue = queue.Queue()
live_position_tracking: bool = False
live_position_message_id: Optional[int] = None
last_live_position_update: datetime = datetime.now()
LIVE_POSITION_UPDATE_INTERVAL: float = 5  # Update every 0.2 seconds
live_position_logging: bool = True  # Logging enabled by default
last_candle_timestamp: Optional[datetime] = None
mt5_lock = threading.Lock()
stop_flag: bool = False
price_alerts: List[Tuple[float, str, bool, str]] = []
scheduled_reports: bool = False
last_report_time: datetime = datetime.now()
position_monitoring_enabled: bool = False
last_position_update: datetime = datetime.now()
drawdown_alert_triggered: bool = False
equity_alert_triggered: bool = False
profit_alert_triggered: bool = False
last_prediction_time: Optional[datetime] = None
trading_paused: bool = False
last_heartbeat_time: datetime = datetime.now()
last_alert_check: datetime = datetime.now()
heartbeat_interval: Optional[float] = None
heartbeat_lock: threading.Lock = threading.Lock()
latest_analytics: Dict[str, Any] = {}
notification_settings: Dict[str, bool] = {
    "BUY": True,
    "CLOSE_BUY": True,
    "HOLD": True,
    "LIVE_TRACKING": True  # Placeholder, actual control via live_position_tracking
}
telegram_failure_count: int = 0  # Track consecutive Telegram failures
mt5_failure_count: int = 0  # Track consecutive MT5 connection failures

def init_trade_db() -> None:
    """
    Initialize the SQLite database for storing trades, predictions, and decisions using SQLAlchemy models.
    Also handle schema migrations if necessary.
    """
    try:
        # Create all tables defined in the models
        Base.metadata.create_all(engine)
        logging.info(f"Initialized trade database at {TRADE_DB_PATH} with indexes.")

        # Check if the 'symbol' column exists in the 'predictions' table and add it if missing
        with engine.connect() as conn:
            result = conn.execute(text("PRAGMA table_info(predictions)"))
            columns = [row[1] for row in result.fetchall()]
            if 'symbol' not in columns:
                logging.info("Adding 'symbol' column to 'predictions' table.")
                conn.execute(text("ALTER TABLE predictions ADD COLUMN symbol TEXT"))
                logging.info("'symbol' column added successfully.")
            else:
                logging.info("'symbol' column already exists in 'predictions' table.")

    except Exception as e:
        logging.error(f"Failed to initialize trade database: {e}")
        notify(f"Error initializing trade database: {e}")
        sys.exit(1)

def parse_date_range(text: str) -> Tuple[datetime, datetime]:
    """
    Parse a date range string into start and end datetime objects.

    Args:
        text: Date range string (e.g., "thismonth", "lastmonth", "YYYY-MM-DD to YYYY-MM-DD").

    Returns:
        Tuple of (start_date, end_date) as datetime objects.

    Raises:
        ValueError: If the date range format is invalid.
    """
    try:
        text = text.lower()
        now: datetime = datetime.now()
        
        if text == "thismonth":
            start_date: datetime = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            end_date: datetime = now
            return start_date, end_date
        elif text == "lastmonth":
            end_date: datetime = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0) - timedelta(seconds=1)
            start_date: datetime = end_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            return start_date, end_date
        elif text == "lastweek":
            end_date: datetime = now
            start_date: datetime = now - timedelta(days=7)
            return start_date, end_date
        elif "to" in text:
            dates: List[str] = text.split(" to ")
            if len(dates) != 2:
                raise ValueError("Invalid date range format. Use 'YYYY-MM-DD to YYYY-MM-DD'.")
            start_date: datetime = datetime.strptime(dates[0].strip(), "%Y-%m-%d")
            end_date: datetime = datetime.strptime(dates[1].strip(), "%Y-%m-%d")
            return start_date, end_date
        else:
            raise ValueError("Unrecognized date range. Use 'thismonth', 'lastmonth', 'lastweek', or 'YYYY-MM-DD to YYYY-MM-DD'.")
    except Exception as e:
        raise ValueError(f"Failed to parse date range: {e}")

def regenerate_charts() -> None:
    """
    Regenerate all charts periodically to ensure the dashboard has up-to-date visuals.
    Handles errors for each chart generation to prevent bot crashes.
    """
    try:
        # Equity Curve
        try:
            chart_path, _ = generate_equity_curve()
            if chart_path:
                logging.info("Equity curve chart regenerated successfully.")
            else:
                logging.warning("Equity curve chart regeneration returned no chart path.")
        except Exception as e:
            logging.error(f"Failed to regenerate equity curve chart: {e}")

        # Drawdown Curve
        try:
            chart_path, _, _ = generate_drawdown_curve()
            if chart_path:
                logging.info("Drawdown curve chart regenerated successfully.")
            else:
                logging.warning("Drawdown curve chart regeneration returned no chart path.")
        except Exception as e:
            logging.error(f"Failed to regenerate drawdown curve chart: {e}")

        # Daily P/L Histogram
        try:
            chart_path, _ = generate_daily_pl_histogram()
            if chart_path:
                logging.info("Daily P/L histogram chart regenerated successfully.")
            else:
                logging.warning("Daily P/L histogram chart regeneration returned no chart path.")
        except Exception as e:
            logging.error(f"Failed to regenerate daily P/L histogram chart: {e}")

        # Future Equity Outlook
        try:
            chart_path, _ = generate_future_equity_outlook()
            if chart_path:
                logging.info("Future equity outlook chart regenerated successfully.")
            else:
                logging.warning("Future equity outlook chart regeneration returned no chart path.")
        except Exception as e:
            logging.error(f"Failed to regenerate future equity outlook chart: {e}")

        # Trade Heatmap
        try:
            chart_path = generate_trade_heatmap()
            if chart_path:
                logging.info("Trade heatmap chart regenerated successfully.")
            else:
                logging.warning("Trade heatmap chart regeneration returned no chart path.")
        except Exception as e:
            logging.error(f"Failed to regenerate trade heatmap chart: {e}")

        # Trade Duration Distribution
        try:
            chart_path, _ = generate_trade_duration_distribution()
            if chart_path:
                logging.info("Trade duration distribution chart regenerated successfully.")
            else:
                logging.warning("Trade duration distribution chart regeneration returned no chart path.")
        except Exception as e:
            logging.error(f"Failed to regenerate trade duration distribution chart: {e}")

        # Sharpe Ratio Trend
        try:
            chart_path, _ = generate_sharpe_ratio_trend()
            if chart_path:
                logging.info("Sharpe ratio trend chart regenerated successfully.")
            else:
                logging.warning("Sharpe ratio trend chart regeneration returned no chart path.")
        except Exception as e:
            logging.error(f"Failed to regenerate Sharpe ratio trend chart: {e}")

        # Feature Importance
        try:
            chart_path = generate_feature_importance()
            if chart_path:
                logging.info("Feature importance chart regenerated successfully.")
            else:
                logging.warning("Feature importance chart regeneration returned no chart path.")
        except Exception as e:
            logging.error(f"Failed to regenerate feature importance chart: {e}")

        logging.info("Chart regeneration cycle completed.")

    except Exception as e:
        logging.error(f"Unexpected error during chart regeneration: {e}")
        notify(f"❌ **Error During Chart Regeneration:** {e}")

def launch_mini_app(chat_id: str = TELEGRAM_USER_ID) -> None:
    """
    Launch the Mini App via an inline button.
    """
    mini_app_url = f"https://bd56-90-219-124-98.ngrok-free.app/?user={TELEGRAM_USER_ID}"
    # Create InlineKeyboardMarkup object
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(text="Launch Dashboard", web_app=WebAppInfo(url=mini_app_url))]
    ])
    notify("📊 *Launch Trading Dashboard:*", chat_id, reply_markup=keyboard, parse_mode="MarkdownV2")

def notify(
    text: str | List[str],
    chat_id: str = TELEGRAM_USER_ID,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    parse_mode: str = "MarkdownV2"
) -> None:
    """
    Send a notification to Telegram with proper escaping based on parse mode.
    """
    global telegram_failure_count
    TELEGRAM_MESSAGE_LIMIT: int = 4096
    url: str = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    RETRIES: int = 3
    DELAY_BETWEEN_MESSAGES: float = 1.0

    def escape_markdown_v2(text: str) -> str:
        """Escape special characters for MarkdownV2."""
        special_chars = r'_[]()~`>#+-=|{}.!'
        for char in special_chars:
            text = text.replace(char, f'\\{char}')
        return text

    if isinstance(text, str):
        messages = [text]
    else:
        messages = text

    for i, message in enumerate(messages):
        # Apply escaping only if parse_mode is MarkdownV2
        if parse_mode == "MarkdownV2":
            message = escape_markdown_v2(message)
        if len(message) <= TELEGRAM_MESSAGE_LIMIT:
            chunks = [message]
        else:
            chunks = []
            current_chunk = ""
            for line in message.split("\n"):
                if len(current_chunk) + len(line) + 1 > TELEGRAM_MESSAGE_LIMIT:
                    chunks.append(current_chunk.strip())
                    current_chunk = line + "\n"
                else:
                    current_chunk += line + "\n"
            if current_chunk.strip():
                chunks.append(current_chunk.strip())

        for j, chunk in enumerate(chunks):
            for attempt in range(RETRIES):
                try:
                    payload = {
                        "chat_id": chat_id,
                        "text": chunk,
                        "parse_mode": parse_mode,
                    }
                    if reply_markup:
                        payload["reply_markup"] = reply_markup.to_json()
                    response = requests.post(
                        url,
                        json=payload,
                        timeout=(15, 45)
                    )
                    response.raise_for_status()
                    logging.info(f"Telegram notification sent (Section {i+1}, Chunk {j+1}): {chunk[:50]}...")
                    telegram_failure_count = 0
                    time.sleep(DELAY_BETWEEN_MESSAGES)
                    break
                except requests.exceptions.HTTPError as e:
                    telegram_failure_count += 1
                    logging.error(f"Attempt {attempt+1}/{RETRIES} - Telegram HTTP error: {e}")
                    if attempt == RETRIES - 1:
                        logging.error(f"Failed to send Telegram notification: {chunk[:50]}...")
                    time.sleep(2 ** attempt)
                except requests.exceptions.RequestException as e:
                    telegram_failure_count += 1
                    logging.error(f"Attempt {attempt+1}/{RETRIES} - Telegram network error: {e}")
                    if attempt == RETRIES - 1:
                        logging.error(f"Failed to send Telegram notification: {chunk[:50]}...")
                    time.sleep(2 ** attempt)
                except Exception as e:
                    telegram_failure_count += 1
                    logging.error(f"Attempt {attempt+1}/{RETRIES} - Unexpected Telegram error: {e}")
                    if attempt == RETRIES - 1:
                        logging.error(f"Failed to send Telegram notification: {chunk[:50]}...")
                    time.sleep(2 ** attempt)

def send_photo(file_path: str, caption: str = "Chart", chat_id: str = TELEGRAM_USER_ID) -> None:
    """
    Send a photo to Telegram.

    Args:
        file_path: Path to the photo file.
        caption: Caption for the photo.
        chat_id: Telegram chat ID to send the photo to.
    """
    global telegram_failure_count
    url: str = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    # Remove asterisks from caption and wrap in <b> tags for bold formatting
    cleaned_caption = caption.replace("*", "")  # Remove any asterisks
    bold_caption = f"<b>{cleaned_caption}</b>"  # Apply bold formatting
    try:
        with open(file_path, 'rb') as photo:
            files: Dict[str, Any] = {'photo': photo}
            data: Dict[str, Any] = {'chat_id': chat_id, 'caption': bold_caption, 'parse_mode': 'HTML'}
            response = requests.post(url, files=files, data=data, timeout=(15, 45))
            response.raise_for_status()
        logging.info(f"Telegram photo sent to {chat_id}: {file_path}")
        telegram_failure_count = 0  # Reset failure count on success
    except Exception as e:
        telegram_failure_count += 1
        logging.error(f"Failed to send Telegram photo to {chat_id}: {e}")
        notify(f"Error sending chart: {e}", chat_id)


def send_inline_keyboard(chat_id: str = TELEGRAM_USER_ID) -> None:
    """
    Send an inline keyboard menu to Telegram with notification status indicators.
    """
    global telegram_failure_count
    url: str = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    # Define notification button text based on notification_settings
    buy_notify_text = f"BUY Notify: {'ON' if notification_settings['BUY'] else 'OFF'}"
    close_notify_text = f"CLOSE Notify: {'ON' if notification_settings['CLOSE_BUY'] else 'OFF'}"
    hold_notify_text = f"HOLD Notify: {'ON' if notification_settings['HOLD'] else 'OFF'}"
    keyboard: Dict[str, Any] = {
        "inline_keyboard": [
            [
                {"text": "Check Status", "callback_data": "status"},
                {"text": "Check Price", "callback_data": "price"},
                {"text": "View Chart", "callback_data": "chart"},
            ],
            [
                {"text": "Toggle Schedule", "callback_data": "schedule"},
                {"text": "Toggle Monitoring", "callback_data": "monitor"},
                {"text": "Toggle Live Tracking", "callback_data": "toggle_livetracking"},
            ],
            [
                {"text": "Pause Trading", "callback_data": "pause"},
                {"text": "Resume Trading", "callback_data": "resume"},
                {"text": "Health Check", "callback_data": "health"},
            ],
            [
                {"text": "Manual BUY", "callback_data": "buy"},
                {"text": "Manual CLOSE", "callback_data": "close"},
                {"text": "View Position", "callback_data": "position"},
            ],
            [
                {"text": "Equity Curve", "callback_data": "equity"},
                {"text": "Drawdowns", "callback_data": "drawdown"},
                {"text": "Dashboard", "callback_data": "dashboard"},
            ],
            [
                {"text": "Calmar Trend", "callback_data": "calmartrend"},
                {"text": "Sortino Trend", "callback_data": "sortinotrend"},
                {"text": "Monte Carlo", "callback_data": "montecarlo"},
            ],
            [
                {"text": "Hourly P/L", "callback_data": "hourlypl"},
                {"text": "Day-of-Week P/L", "callback_data": "dayofweekpl"},
                {"text": "Trade Clustering", "callback_data": "tradeclustering"},
            ],
            [
                {"text": "Future Outlook", "callback_data": "outlook"},
                {"text": "Trade Heatmap", "callback_data": "heatmaptrades"},
                {"text": "Daily P/L Histogram", "callback_data": "dailypl"},
            ],
            [
                {"text": "Monthly Performance", "callback_data": "monthlypl"},
                {"text": "Trade Duration", "callback_data": "tradeduration"},
                {"text": "Sharpe Trend", "callback_data": "sharpetrend"},
            ],
            [
                {"text": "Feature Importance", "callback_data": "featureimportance"},
                {"text": "Recent Trades", "callback_data": "log"},
                {"text": "Analytics Report", "callback_data": "report"},
            ],
            [
                {"text": "Profit Factor", "callback_data": "profitfactor"},
                {"text": "Recovery Factor", "callback_data": "recoveryfactor"},
                {"text": "Win Rate", "callback_data": "winrate"},
            ],
            [
                {"text": "Return Stats", "callback_data": "returnstats"},
                {"text": "Win/Loss Streaks", "callback_data": "winlossstreaks"},
                {"text": "Holding vs. Profit", "callback_data": "holdingvsprofit"},
            ],
            [
                {"text": "Transaction Costs", "callback_data": "transactioncosts"},
                {"text": "Overtrading", "callback_data": "overtrading"},
                {"text": "Decision Log", "callback_data": "decisionlog"},
            ],
            [
                {"text": buy_notify_text, "callback_data": "togglenotify_buy"},
                {"text": close_notify_text, "callback_data": "togglenotify_close_buy"},
                {"text": hold_notify_text, "callback_data": "togglenotify_hold"},
            ],
            [
                {"text": "Help", "callback_data": "help"},
            ],
            [
                {"text": "Launch Dashboard", "callback_data": "dashboard_mini_app"},
            ],
            
        ]
    }

    command_list = (
        "Commands with Parameters:\n\n"
        "- /alert <price> [above|below] [recurring]\n"
        "  Set a price alert, e.g., /alert 2500 above recurring\n\n"
        "- /log [buy|close_buy] [thismonth|lastmonth|lastweek|YYYY-MM-DD to YYYY-MM-DD]\n"
        "  View trades, e.g., /log buy lastmonth\n\n"
        "- /report [thismonth|lastmonth|lastweek|YYYY-MM-DD to YYYY-MM-DD]\n"
        "  Generate report, e.g., /report 2025-04-01 to 2025-04-30\n\n"
        "- /equity [thismonth|lastmonth|lastweek|YYYY-MM-DD to YYYY-MM-DD]\n"
        "  View equity curve, e.g., /equity thismonth\n\n"
        "- /drawdown [thismonth|lastmonth|lastweek|YYYY-MM-DD to YYYY-MM-DD]\n"
        "  View drawdowns, e.g., /drawdown lastweek\n\n"
        "- /dashboard [thismonth|lastmonth|lastweek|YYYY-MM-DD to YYYY-MM-DD]\n"
        "  View dashboard, e.g., /dashboard thismonth\n\n"
        "- /heartbeat [X]\n"
        "  Set bot to send 'I'm alive' messages every X hours, e.g., /heartbeat 4\n\n"
        "- /compare period1 period2\n"
        "  Compare performance between two periods, e.g., /compare lastmonth thismonth\n\n"
        "- /exportcsv [thismonth|lastmonth|lastweek|YYYY-MM-DD to YYYY-MM-DD]\n"
        "  Export trade history to CSV, e.g., /exportcsv lastmonth\n\n"
        "- /decisionlog [symbol]\n"
        "  View last 5 decisions, e.g., /decisionlog GOLD\n\n"
        "- /togglenotify <type>\n"
        "  Toggle notifications for trade decisions, e.g., /togglenotify HOLD\n\n"
        "- /setpositionsize <size>\n"
        "  Set position size for BUY trades, e.g., /setpositionsize 0.1"
    )
    notify(command_list, chat_id)

    payload: Dict[str, Any] = {
        "chat_id": chat_id,
        "text": "Choose an action:",
        "reply_markup": json.dumps(keyboard),
    }
    try:
        response = requests.post(url, json=payload, timeout=(15, 45))
        response.raise_for_status()
        logging.info(f"Inline keyboard sent to {chat_id}")
        telegram_failure_count = 0
    except Exception as e:
        telegram_failure_count += 1
        logging.error(f"Error sending inline keyboard: {e}")
        notify(f"Error sending inline keyboard: {e}", chat_id)

def send_live_position_logging_keyboard(chat_id: str = TELEGRAM_USER_ID) -> None:
    """
    Send an inline keyboard with options to toggle live position logging and return to main menu.
    """
    global telegram_failure_count
    url: str = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    keyboard: Dict[str, Any] = {
        "inline_keyboard": [
            [
                {"text": f"Live Position Logging: {'ON' if live_position_logging else 'OFF'}", "callback_data": "toggle_live_logging"},
            ]
        ]
    }
    payload: Dict[str, Any] = {
        "chat_id": chat_id,
        "text": "Live Position Tracking Options:",
        "reply_markup": json.dumps(keyboard),
    }
    try:
        response = requests.post(url, json=payload, timeout=(15, 45))
        response.raise_for_status()
        logging.info(f"Live position logging keyboard sent to {chat_id}")
        telegram_failure_count = 0
    except Exception as e:
        telegram_failure_count += 1
        logging.error(f"Error sending live position logging keyboard: {e}")
        notify(f"Error sending live position logging keyboard: {e}", chat_id)

def update_live_position_message(chat_id: str = TELEGRAM_USER_ID) -> None:
    """
    Send or update a Telegram message with live position details every 0.2 seconds.
    Updates profit/loss, pips, and equity percentage change. Logging controlled by live_position_logging.
    """
    global live_position_message_id, telegram_failure_count, live_position_logging
    url: str = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    edit_url: str = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageText"

    def escape_markdown_v2(text: str) -> str:
        """Escape special characters for Telegram MarkdownV2."""
        special_chars = r'_[]()~`>#+-=|{}.!'
        for char in special_chars:
            text = text.replace(char, f'\\{char}')
        return text

    try:
        with mt5_lock:
            positions = mt5.positions_get(symbol=SYMBOL)
            tick = mt5.symbol_info_tick(SYMBOL)
            account_info = mt5.account_info()

        if not tick or not account_info:
            if live_position_logging:
                logging.error("Failed to fetch market data for live position update.")
            return

        equity_gbp: float = account_info.equity * EXCHANGE_RATE
        current_price: float = tick.bid

        if not positions:
            if live_position_message_id:
                # Position closed, update message one last time and reset
                text: str = escape_markdown_v2(
                    "ℹ️ *No Open Positions.*\n"
                    "Live tracking stopped."
                )
                payload: Dict[str, Any] = {
                    "chat_id": chat_id,
                    "message_id": live_position_message_id,
                    "text": text,
                    "parse_mode": "MarkdownV2"
                }
                try:
                    response = requests.post(edit_url, json=payload, timeout=(15, 45))
                    response.raise_for_status()
                    if live_position_logging:
                        logging.info(f"Live position message updated: No open positions.")
                    telegram_failure_count = 0
                except Exception as e:
                    telegram_failure_count += 1
                    if live_position_logging:
                        logging.error(f"Failed to update live position message: {e}, Response: {response.text if 'response' in locals() else 'No response'}")
                    live_position_message_id = None
            return

        position = positions[0]
        open_price: float = position.price_open
        profit_usd: float = position.profit
        profit_gbp: float = profit_usd * EXCHANGE_RATE
        pips: float = round((current_price - open_price) * 10, 1) if position.type == mt5.ORDER_TYPE_BUY else round((open_price - current_price) * 10, 1)
        equity_percentage: float = (profit_gbp / equity_gbp * 100) if equity_gbp != 0 else 0.0

        # Format numbers to avoid floating-point issues and escape MarkdownV2 characters
        text: str = escape_markdown_v2(
            f"📈 *Live Position Update ({SYMBOL})*\n"
            f"---\n"
            f"💵 *Current Price:* ${current_price:.2f}\n"
            f"💵 *Open Price:* ${open_price:.2f}\n"
            f"📏 *Pips:* {pips:+.1f}\n"
            f"💷 *Profit/Loss:* £{profit_gbp:.2f}\n"
            f"📊 *Equity Impact:* {equity_percentage:+.2f}%\n"
            f"🕒 *Last Updated:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        if live_position_message_id:
            # Update existing message
            payload: Dict[str, Any] = {
                "chat_id": chat_id,
                "message_id": live_position_message_id,
                "text": text,
                "parse_mode": "MarkdownV2"
            }
            try:
                response = requests.post(edit_url, json=payload, timeout=(15, 45))
                response.raise_for_status()
                if live_position_logging:
                    logging.info(f"Live position message updated: Profit £{profit_gbp:.2f}, Pips {pips:.1f}")
                telegram_failure_count = 0
            except Exception as e:
                telegram_failure_count += 1
                if live_position_logging:
                    logging.error(f"Failed to update live position message: {e}, Response: {response.text if 'response' in locals() else 'No response'}")
                live_position_message_id = None  # Reset to try sending a new message
        else:
            # Send new message
            payload: Dict[str, Any] = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "MarkdownV2"
            }
            try:
                response = requests.post(url, json=payload, timeout=(15, 45))
                response.raise_for_status()
                live_position_message_id = response.json().get("result", {}).get("message_id")
                if live_position_logging:
                    logging.info(f"Live position message sent: Message ID {live_position_message_id}")
                telegram_failure_count = 0
            except Exception as e:
                telegram_failure_count += 1
                if live_position_logging:
                    logging.error(f"Failed to send live position message: {e}, Response: {response.text if 'response' in locals() else 'No response'}")

    except Exception as e:
        telegram_failure_count += 1
        if live_position_logging:
            logging.error(f"Error in live position update: {e}")

def generate_daily_pl_histogram(start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> Tuple[Optional[str], str]:
    """
    Generate a histogram of daily profit/loss from closed trades.

    Args:
        start_date: Start date for the data range.
        end_date: End date for the data range.

    Returns:
        Tuple of (chart_path, title). Returns (None, message) if trade log is empty.
    """
    try:
        query: str = "SELECT timestamp, profit_loss FROM trades WHERE trade_type = 'CLOSE_BUY'"
        params: Dict[str, Any] = {}
        if start_date and end_date:
            query += " AND timestamp BETWEEN :start_date AND :end_date"
            params = {"start_date": start_date, "end_date": end_date}
        df: pd.DataFrame = pd.read_sql_query(query, engine, params=params)

        if df.empty or 'profit_loss' not in df.columns or 'timestamp' not in df.columns:
            logging.info("No closed trades available to plot daily P/L histogram.")
            return None, "No closed trades available to plot daily P/L histogram."

        # Aggregate profit/loss by day
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df['date'] = df['timestamp'].dt.date
        daily_pl = df.groupby('date')['profit_loss'].sum()

        plt.figure(figsize=(10, 5))
        plt.hist(daily_pl, bins=20, edgecolor='black', color='purple')
        plt.title("Daily Profit/Loss Histogram", fontweight='bold')
        plt.xlabel("Daily Profit/Loss (£)")
        plt.ylabel("Frequency")
        plt.grid(True)

        if start_date and end_date:
            plt.title(f"Daily Profit/Loss Histogram\n{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}", fontweight='bold')

        chart_path: str = os.path.join(PLOT_PATH, "daily_pl_histogram.png")
        plt.savefig(chart_path)
        plt.close()
        return chart_path, "Daily Profit/Loss Histogram"
    except Exception as e:
        logging.error(f"Failed to generate daily P/L histogram: {e}")
        raise

def generate_equity_curve(start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> Tuple[Optional[str], str]:
    """
    Generate an equity curve chart and detailed performance statistics.

    Args:
        start_date: Start date for the data range.
        end_date: End date for the data range.

    Returns:
        Tuple of (chart_path, detailed_text). Returns (None, message) if trade log is empty.
    """
    try:
        query: str = "SELECT timestamp, equity, profit_loss, trade_type, price, symbol FROM trades"
        params: Dict[str, Any] = {}
        if start_date and end_date:
            query += " WHERE timestamp BETWEEN :start_date AND :end_date"
            params = {"start_date": start_date, "end_date": end_date}
        df: pd.DataFrame = pd.read_sql_query(query, engine, params=params)

        if df.empty or 'equity' not in df.columns or 'timestamp' not in df.columns:
            logging.info("Trade log is empty or missing required columns. Returning placeholder message.")
            return None, "No trades available to plot equity curve."

        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values('timestamp')

        # Calculate equity curve statistics
        starting_equity: float = df['equity'].iloc[0]
        current_equity: float = df['equity'].iloc[-1]
        equity_change: float = current_equity - starting_equity
        equity_change_pct: float = (equity_change / starting_equity * 100) if starting_equity != 0 else 0.0

        # Calculate drawdown
        equity_series: np.ndarray = df['equity'].values
        peak: np.ndarray = np.maximum.accumulate(equity_series)
        drawdown: np.ndarray = (peak - equity_series) / peak
        avg_drawdown_pct: float = drawdown.mean() * 100 if len(drawdown) > 0 else 0.0
        avg_drawdown_gbp: float = ((peak - equity_series) * EXCHANGE_RATE).mean() if len(equity_series) > 0 else 0.0
        max_drawdown_pct: float = drawdown.max() * 100 if len(drawdown) > 0 else 0.0

        # Calculate returns and pips for CLOSE_BUY trades
        close_trades: pd.DataFrame = df[df['trade_type'] == 'CLOSE_BUY']
        total_trades: int = len(close_trades)
        if total_trades > 0:
            avg_return_gbp: float = close_trades['profit_loss'].mean()
            avg_return_pct: float = (avg_return_gbp / starting_equity * 100) if starting_equity != 0 else 0.0
            # Calculate pips (requires matching BUY trades)
            pips_list: List[float] = []
            for _, close_trade in close_trades.iterrows():
                close_time = close_trade['timestamp']
                close_price = close_trade['price']
                symbol = close_trade['symbol']
                # Find the matching BUY trade
                buy_trades = df[(df['trade_type'] == 'BUY') & (df['symbol'] == symbol) & (df['timestamp'] < close_time)]
                if not buy_trades.empty:
                    open_price = buy_trades.iloc[-1]['price']
                    pips = round((close_price - open_price) * 10, 1)  # 1 pip = 0.1 for GOLD
                    pips_list.append(pips)
            avg_pips: float = np.mean(pips_list) if pips_list else 0.0
        else:
            avg_return_gbp = 0.0
            avg_return_pct = 0.0
            avg_pips = 0.0

        # Additional metrics from compute_analytics and compute_winrate
        analytics: Dict[str, Any] = compute_analytics()
        win_stats: Dict[str, float] = compute_winrate()
        total_pl: float = analytics['total_pl']
        win_rate: float = win_stats['win_rate']
        sharpe_ratio: float = analytics['sharpe_ratio']

        # Format detailed text output
        title: str = f"{SYMBOL} Equity Curve"
        if start_date and end_date:
            title += f"\n{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"
        detailed_text: str = (
            f"📈 *{title}*\n"
            f"----------------------------------------\n"
            f"💷 *Starting Equity:* £{starting_equity:.2f}\n"
            f"💷 *Current Equity:* £{current_equity:.2f}\n"
            f"📊 *Equity Change:* £{equity_change:.2f} ({equity_change_pct:+.2f}%)\n"
            f"📉 *Average Drawdown:* £{avg_drawdown_gbp:.2f} ({avg_drawdown_pct:.2f}%)\n"
            f"📉 *Max Drawdown:* {max_drawdown_pct:.2f}%\n"
            f"💸 *Average Return per Trade:* £{avg_return_gbp:.2f} ({avg_return_pct:.2f}%)\n"
            f"📏 *Average Pips per Trade:* {avg_pips:+.1f}\n"
            f"🔢 *Total Trades:* {total_trades}\n"
            f"🏆 *Win Rate:* {win_rate:.2%}\n"
            f"💷 *Total Profit/Loss:* £{total_pl:.2f}\n"
            f"📈 *Sharpe Ratio:* {sharpe_ratio:.2f}"
        )

        # Generate equity curve chart
        plt.figure(figsize=(10, 5))
        plt.plot(df['timestamp'], df['equity'], label='Equity (£)', color='green')
        plt.title(title, fontweight='bold')
        plt.xlabel("Time")
        plt.ylabel("Equity (GBP)")
        plt.legend()
        plt.grid()
        chart_path: str = os.path.join(PLOT_PATH, "equity_curve.png")
        plt.savefig(chart_path)
        plt.close()

        return chart_path, detailed_text

    except Exception as e:
        logging.error(f"Failed to generate equity curve: {e}")
        return None, f"Error generating equity curve: {e}"

def generate_drawdown_curve(start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> Tuple[Optional[str], float, str]:
    """
    Generate a drawdown curve chart.

    Args:
        start_date: Start date for the data range.
        end_date: End date for the data range.

    Returns:
        Tuple of (chart_path, max_drawdown, title). Returns (None, 0.0, message) if trade log is empty.
    """
    try:
        query: str = "SELECT timestamp, equity FROM trades"
        params: Dict[str, Any] = {}
        if start_date and end_date:
            query += " WHERE timestamp BETWEEN :start_date AND :end_date"
            params = {"start_date": start_date, "end_date": end_date}
        df: pd.DataFrame = pd.read_sql_query(query, engine, params=params)

        if df.empty or 'equity' not in df.columns or 'timestamp' not in df.columns:
            logging.info("Trade log is empty or missing required columns. Returning placeholder message.")
            return None, 0.0, "No trades available to plot drawdown curve."

        df['timestamp'] = pd.to_datetime(df['timestamp'])
        equity_series: np.ndarray = df['equity'].values
        peak: np.ndarray = np.maximum.accumulate(equity_series)
        drawdown: np.ndarray = (peak - equity_series) / peak
        max_drawdown: float = drawdown.max() if len(drawdown) > 0 else 0.0

        plt.figure(figsize=(10, 5))
        plt.plot(df['timestamp'], drawdown * 100, label='Drawdown (%)', color='red')
        title: str = f"{SYMBOL} Drawdown Curve"
        if start_date and end_date:
            title += f"\n{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"
        plt.title(title, fontweight='bold')
        plt.xlabel("Time")
        plt.ylabel("Drawdown (%)")
        plt.legend()
        plt.grid()
        chart_path: str = os.path.join(PLOT_PATH, "drawdown_curve.png")
        plt.savefig(chart_path)
        plt.close()
        return chart_path, max_drawdown, title
    except Exception as e:
        logging.error(f"Failed to generate drawdown curve: {e}")
        raise

def generate_future_equity_outlook(forecast_months: int = 12) -> Tuple[str, float]:
    """
    Generate a future equity outlook chart based on historical returns.

    Args:
        forecast_months: Number of months to forecast.

    Returns:
        Tuple of (chart_path, avg_monthly_return).
    """
    try:
        df: pd.DataFrame = pd.read_sql_query("SELECT timestamp, equity FROM trades", engine)

        if df.empty or 'equity' not in df.columns or 'timestamp' not in df.columns:
            raise Exception("Trade log is empty or missing required columns.")

        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values('timestamp')

        monthly_returns: List[float] = []
        df['month'] = df['timestamp'].dt.to_period('M')
        monthly_groups = df.groupby('month')
        for month, group in monthly_groups:
            initial_equity: float = group['equity'].iloc[0]
            final_equity: float = group['equity'].iloc[-1]
            monthly_return: float = (final_equity - initial_equity) / initial_equity if initial_equity != 0 else 0.0
            monthly_returns.append(monthly_return)

        avg_monthly_return: float = np.mean(monthly_returns) if monthly_returns else 0.0
        if avg_monthly_return == 0.0:
            raise Exception("No historical returns available to project future equity.")

        last_equity: float = df['equity'].iloc[-1]
        last_date: datetime = df['timestamp'].iloc[-1]
        future_dates: List[datetime] = [last_date + timedelta(days=30 * i) for i in range(forecast_months)]
        future_equity: List[float] = [last_equity * (1 + avg_monthly_return) ** i for i in range(forecast_months)]

        plt.figure(figsize=(10, 5))
        plt.plot(df['timestamp'], df['equity'], label='Historical Equity (£)', color='blue')
        plt.plot(future_dates, future_equity, label=f'Projected Equity (Avg {avg_monthly_return*100:.2f}%/month)', color='orange', linestyle='--')
        
        plt.title(f"{SYMBOL} Equity Curve with Future Outlook", fontweight='bold')
        plt.xlabel("Time")
        plt.ylabel("Equity (GBP)")
        plt.legend()
        plt.grid()
        chart_path: str = os.path.join(PLOT_PATH, "equity_outlook.png")
        plt.savefig(chart_path)
        plt.close()

        return chart_path, avg_monthly_return
    except Exception as e:
        logging.error(f"Failed to generate future equity outlook: {e}")
        raise

def generate_trade_heatmap() -> str:
    """
    Generate a trade heatmap showing profit/loss by time of day.

    Returns:
        Path to the generated heatmap chart.
    """
    try:
        df: pd.DataFrame = pd.read_sql_query("SELECT timestamp, profit_loss FROM trades", engine)

        if df.empty or 'timestamp' not in df.columns or 'profit_loss' not in df.columns:
            raise Exception("Trade log is empty or missing required columns.")

        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df['hour'] = df['timestamp'].dt.hour
        df['day'] = df['timestamp'].dt.day_name()

        heatmap_data: pd.DataFrame = df.pivot_table(
            values='profit_loss',
            index='day',
            columns='hour',
            aggfunc='mean',
            fill_value=0
        )
        day_order: List[str] = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        heatmap_data = heatmap_data.reindex(day_order)

        plt.figure(figsize=(12, 6))
        sns.heatmap(heatmap_data, cmap='RdYlGn', annot=True, fmt='.2f', cbar_kws={'label': 'Avg Profit/Loss (£)'})
        plt.title(f"{SYMBOL} Trade Heatmap by Time of Day", fontweight='bold')
        plt.xlabel("Hour of Day (UTC)")
        plt.ylabel("Day of Week")
        chart_path: str = os.path.join(PLOT_PATH, "trade_heatmap.png")
        plt.savefig(chart_path)
        plt.close()
        return chart_path
    except Exception as e:
        logging.error(f"Failed to generate trade heatmap: {e}")
        raise

def generate_trade_duration_distribution(start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> Tuple[Optional[str], str]:
    """
    Generate a histogram of trade durations (time between BUY and CLOSE_BUY).

    Args:
        start_date: Start date for the data range.
        end_date: End date for the data range.

    Returns:
        Tuple of (chart_path, title). Returns (None, message) if trade log is empty or no matching trades.
    """
    try:
        query: str = "SELECT timestamp, trade_type, symbol FROM trades WHERE trade_type IN ('BUY', 'CLOSE_BUY')"
        params: Dict[str, Any] = {}
        if start_date and end_date:
            query += " AND timestamp BETWEEN :start_date AND :end_date"
            params = {"start_date": start_date, "end_date": end_date}
        df: pd.DataFrame = pd.read_sql_query(query, engine, params=params)

        if df.empty or 'timestamp' not in df.columns or 'trade_type' not in df.columns:
            logging.info("No trades available to plot trade duration distribution.")
            return None, "No trades available to plot trade duration distribution."

        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values('timestamp')

        durations: List[float] = []
        buy_trades = df[df['trade_type'] == 'BUY']
        close_trades = df[df['trade_type'] == 'CLOSE_BUY']

        for _, close in close_trades.iterrows():
            close_time = close['timestamp']
            symbol = close['symbol']
            matching_buy = buy_trades[(buy_trades['symbol'] == symbol) & (buy_trades['timestamp'] < close_time)]
            if not matching_buy.empty:
                buy_time = matching_buy.iloc[-1]['timestamp']
                duration_hours = (close_time - buy_time).total_seconds() / 3600  # Convert to hours
                durations.append(duration_hours)

        if not durations:
            logging.info("No matching BUY and CLOSE_BUY trades found for duration calculation.")
            return None, "No matching trades found to plot trade duration distribution."

        plt.figure(figsize=(10, 5))
        plt.hist(durations, bins=20, edgecolor='black', color='orange')
        plt.title("Trade Duration Distribution", fontweight='bold')
        plt.xlabel("Duration (Hours)")
        plt.ylabel("Frequency")
        plt.grid(True)

        if start_date and end_date:
            plt.title(f"Trade Duration Distribution\n{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}", fontweight='bold')

        chart_path: str = os.path.join(PLOT_PATH, "trade_duration.png")
        plt.savefig(chart_path)
        plt.close()
        return chart_path, "Trade Duration Distribution"
    except Exception as e:
        logging.error(f"Failed to generate trade duration distribution: {e}")
        raise

def generate_sharpe_ratio_trend() -> Tuple[Optional[str], str]:
    """
    Generate a line chart of rolling monthly Sharpe Ratio over time.

    Returns:
        Tuple of (chart_path, title). Returns (None, message) if trade log is empty.
    """
    try:
        df: pd.DataFrame = pd.read_sql_query("SELECT timestamp, equity FROM trades", engine)

        if df.empty or 'equity' not in df.columns or 'timestamp' not in df.columns:
            logging.info("No trades available to plot Sharpe Ratio trend.")
            return None, "No trades available to plot Sharpe Ratio trend."

        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values('timestamp')
        df.set_index('timestamp', inplace=True)

        # Resample to daily equity and calculate daily returns
        daily_equity = df['equity'].resample('D').last().ffill()
        daily_returns = daily_equity.pct_change().dropna()

        # Calculate rolling monthly Sharpe Ratio (30-day window)
        sharpe_ratios = []
        dates = []
        window_days = 30
        risk_free_rate_annual = 0.04  # 4% annual risk-free rate
        risk_free_rate_daily = risk_free_rate_annual / 252

        for i in range(window_days, len(daily_returns)):
            window_returns = daily_returns.iloc[i-window_days:i]
            if len(window_returns) < 2:
                continue
            mean_daily_return = window_returns.mean()
            std_daily_return = window_returns.std()
            annualized_mean_return = mean_daily_return * 252
            annualized_std = std_daily_return * np.sqrt(252)
            annualized_risk_free_rate = risk_free_rate_daily * 252
            sharpe_ratio = (annualized_mean_return - annualized_risk_free_rate) / annualized_std if annualized_std != 0 else 0.0
            sharpe_ratios.append(sharpe_ratio)
            dates.append(daily_returns.index[i])

        if not sharpe_ratios:
            logging.info("Insufficient data to calculate Sharpe Ratio trend.")
            return None, "Insufficient data to plot Sharpe Ratio trend."

        plt.figure(figsize=(10, 5))
        plt.plot(dates, sharpe_ratios, label='Rolling Sharpe Ratio (30-day)', color='blue')
        plt.title("Sharpe Ratio Trend (Rolling 30-Day)", fontweight='bold')
        plt.xlabel("Date")
        plt.ylabel("Sharpe Ratio")
        plt.legend()
        plt.grid(True)

        chart_path: str = os.path.join(PLOT_PATH, "sharpe_trend.png")
        plt.savefig(chart_path)
        plt.close()
        return chart_path, "Sharpe Ratio Trend"
    except Exception as e:
        logging.error(f"Failed to generate Sharpe Ratio trend: {e}")
        raise

def generate_feature_importance() -> str:
    """
    Generate a feature importance chart based on correlation with decisions.

    Returns:
        Path to the generated feature importance chart.
    """
    try:
        df: pd.DataFrame = pd.read_sql_query("SELECT action_label, features FROM predictions", engine)

        if df.empty:
            raise Exception("Prediction log is empty.")

        feature_data: List[List[float]] = []
        for _, row in df.iterrows():
            features: Dict[str, float] = json.loads(row['features'])
            feature_data.append([features.get(f, 0.0) for f in FEATURES])
        feature_df: pd.DataFrame = pd.DataFrame(feature_data, columns=FEATURES)
        feature_df['action_label'] = df['action_label']

        feature_df['action_numeric'] = feature_df['action_label'].map({'BUY': 0, 'CLOSE_BUY': 1, 'HOLD': 2})
        correlations: pd.Series = feature_df[FEATURES + ['action_numeric']].corr()['action_numeric'].drop('action_numeric')
        
        plt.figure(figsize=(10, 5))
        correlations.sort_values().plot(kind='barh', color='skyblue')
        plt.title(f"{SYMBOL} Feature Importance (Correlation with Decisions)", fontweight='bold')
        plt.xlabel("Correlation Coefficient")
        plt.ylabel("Feature")
        chart_path: str = os.path.join(PLOT_PATH, "feature_importance.png")
        plt.savefig(chart_path)
        plt.close()
        return chart_path
    except Exception as e:
        logging.error(f"Failed to generate feature importance: {e}")
        raise

def compute_winrate() -> Dict[str, float]:
    """
    Compute win rate and related statistics.

    Returns:
        Dictionary containing win rate, average win, average loss, expectancy, and total trades.
    """
    try:
        df: pd.DataFrame = pd.read_sql_query("SELECT trade_type, profit_loss FROM trades", engine)

        if df.empty:
            return {
                'win_rate': 0.0,
                'avg_win': 0.0,
                'avg_loss': 0.0,
                'expectancy': 0.0,
                'total_trades': 0
            }

        trades: pd.DataFrame = df[df['trade_type'] == 'CLOSE_BUY']
        total_trades: int = len(trades)
        if total_trades == 0:
            return {
                'win_rate': 0.0,
                'avg_win': 0.0,
                'avg_loss': 0.0,
                'expectancy': 0.0,
                'total_trades': 0
            }

        wins: pd.DataFrame = trades[trades['profit_loss'] > 0]
        losses: pd.DataFrame = trades[trades['profit_loss'] < 0]
        win_rate: float = len(wins) / total_trades if total_trades > 0 else 0.0
        avg_win: float = wins['profit_loss'].mean() if not wins.empty else 0.0
        avg_loss: float = losses['profit_loss'].mean() if not losses.empty else 0.0
        loss_rate: float = len(losses) / total_trades if total_trades > 0 else 0.0
        expectancy: float = (win_rate * avg_win) + (loss_rate * avg_loss) if total_trades > 0 else 0.0

        return {
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'expectancy': expectancy,
            'total_trades': total_trades
        }
    except Exception as e:
        logging.error(f"Failed to compute win rate: {e}")
        return {
            'win_rate': 0.0,
            'avg_win': 0.0,
            'avg_loss': 0.0,
            'expectancy': 0.0,
            'total_trades': 0
        }
def generate_sortino_ratio_trend(start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> Tuple[Optional[str], str]:
    """
    Generate a line chart of rolling monthly Sortino Ratio over time, focusing on downside risk.

    Args:
        start_date: Start date for the data range.
        end_date: End date for the data range.

    Returns:
        Tuple of (chart_path, title). Returns (None, message) if trade log is empty.
    """
    try:
        query: str = "SELECT timestamp, equity FROM trades"
        params: Dict[str, Any] = {}
        if start_date and end_date:
            query += " WHERE timestamp BETWEEN :start_date AND :end_date"
            params = {"start_date": start_date, "end_date": end_date}
        df: pd.DataFrame = pd.read_sql_query(query, engine, params=params)

        if df.empty or 'equity' not in df.columns or 'timestamp' not in df.columns:
            logging.info("No trades available to plot Sortino Ratio trend.")
            return None, "No trades available to plot Sortino Ratio trend."

        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values('timestamp')
        df.set_index('timestamp', inplace=True)

        # Resample to daily equity and calculate daily returns
        daily_equity = df['equity'].resample('D').last().ffill()
        daily_returns = daily_equity.pct_change().dropna()

        # Calculate rolling monthly Sortino Ratio (30-day window)
        sortino_ratios = []
        dates = []
        window_days = 30
        risk_free_rate_annual = 0.04  # 4% annual risk-free rate
        risk_free_rate_daily = risk_free_rate_annual / 252
        target_return_daily = 0.0  # Target return (can be risk-free rate or 0)

        for i in range(window_days, len(daily_returns)):
            window_returns = daily_returns.iloc[i-window_days:i]
            if len(window_returns) < 2:
                continue
            mean_daily_return = window_returns.mean()
            # Calculate downside deviation (returns below target)
            downside_returns = window_returns[window_returns < target_return_daily]
            downside_deviation = np.sqrt(np.mean(downside_returns**2)) if len(downside_returns) > 0 else 0.0
            annualized_mean_return = mean_daily_return * 252
            annualized_downside_dev = downside_deviation * np.sqrt(252)
            annualized_risk_free_rate = risk_free_rate_daily * 252
            sortino_ratio = (annualized_mean_return - annualized_risk_free_rate) / annualized_downside_dev if annualized_downside_dev != 0 else 0.0
            sortino_ratios.append(sortino_ratio)
            dates.append(daily_returns.index[i])

        if not sortino_ratios:
            logging.info("Insufficient data to calculate Sortino Ratio trend.")
            return None, "Insufficient data to plot Sortino Ratio trend."

        plt.figure(figsize=(10, 5))
        plt.plot(dates, sortino_ratios, label='Rolling Sortino Ratio (30-day)', color='purple')
        plt.title("Sortino Ratio Trend (Rolling 30-Day)", fontweight='bold')
        plt.xlabel("Date")
        plt.ylabel("Sortino Ratio")
        plt.legend()
        plt.grid(True)

        chart_path: str = os.path.join(PLOT_PATH, "sortino_trend.png")
        plt.savefig(chart_path)
        plt.close()
        return chart_path, "Sortino Ratio Trend"
    except Exception as e:
        logging.error(f"Failed to generate Sortino Ratio trend: {e}")
        raise

def compute_return_stats() -> Dict[str, float]:
    """
    Compute return statistics including compound return, annualized return, and volatility.

    Returns:
        Dictionary containing compound return, annualized return, and volatility.
    """
    try:
        df: pd.DataFrame = pd.read_sql_query("SELECT timestamp, equity FROM trades", engine)

        if df.empty or 'equity' not in df.columns or 'timestamp' not in df.columns:
            return {
                'compound_return': 0.0,
                'annualized_return': 0.0,
                'volatility': 0.0
            }

        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values('timestamp')
        initial_equity: float = df['equity'].iloc[0]
        final_equity: float = df['equity'].iloc[-1]
        compound_return: float = (final_equity - initial_equity) / initial_equity if initial_equity != 0 else 0.0

        time_span: float = (df['timestamp'].iloc[-1] - df['timestamp'].iloc[0]).total_seconds() / (365 * 24 * 3600)
        annualized_return: float = ((final_equity / initial_equity) ** (1 / time_span) - 1) if initial_equity != 0 and time_span > 0 else 0.0

        returns: pd.Series = df['equity'].pct_change().dropna()
        volatility: float = returns.std() * np.sqrt(252) if not returns.empty else 0.0

        return {
            'compound_return': compound_return,
            'annualized_return': annualized_return,
            'volatility': volatility
        }
    except Exception as e:
        logging.error(f"Failed to compute return stats: {e}")
        return {
            'compound_return': 0.0,
            'annualized_return': 0.0,
            'volatility': 0.0
        }

def export_trade_history(start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> str:
    """
    Export trade history to a CSV file.

    Args:
        start_date: Start date for the data range.
        end_date: End date for the data range.

    Returns:
        Path to the exported CSV file.
    """
    try:
        query: str = "SELECT * FROM trades"
        params: Dict[str, Any] = {}
        if start_date and end_date:
            query += " WHERE timestamp BETWEEN :start_date AND :end_date"
            params = {"start_date": start_date, "end_date": end_date}
        df: pd.DataFrame = pd.read_sql_query(query, engine, params=params)

        if df.empty:
            raise Exception("Trade log is empty or no trades found for the specified period.")

        export_filename: str = f"trade_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        export_path: str = os.path.join(EXPORT_PATH, export_filename)
        df.to_csv(export_path, index=False)
        return export_path
    except Exception as e:
        logging.error(f"Failed to export trade history: {e}")
        raise

def compare_periods(period1: str, period2: str) -> str:
    """
    Compare performance between two periods.

    Args:
        period1: First period (e.g., "thismonth").
        period2: Second period (e.g., "lastmonth").

    Returns:
        Comparison text.
    """
    try:
        start1, end1 = parse_date_range(period1)
        start2, end2 = parse_date_range(period2)
        analytics1: Dict[str, Any] = compute_analytics(start1, end1)
        analytics2: Dict[str, Any] = compute_analytics(start2, end2)

        comparison_text: str = "Performance Comparison\n"
        comparison_text += f"Period 1: {period1}\n"
        comparison_text += f"Period 2: {period2}\n"
        comparison_text += "----------------------------------------\n"
        comparison_text += f"Total Trades:\n  Period 1: {analytics1['total_trades']}\n  Period 2: {analytics2['total_trades']}\n"
        comparison_text += f"Win Rate:\n  Period 1: {analytics1['win_rate']:.2%}\n  Period 2: {analytics2['win_rate']:.2%}\n"
        comparison_text += f"Total P/L:\n  Period 1: £{analytics1['total_pl']:.2f}\n  Period 2: £{analytics2['total_pl']:.2f}\n"
        comparison_text += f"Max Drawdown:\n  Period 1: {analytics1['max_drawdown']:.2%}\n  Period 2: {analytics2['max_drawdown']:.2%}\n"
        comparison_text += f"Sharpe Ratio:\n  Period 1: {analytics1['sharpe_ratio']:.2f}\n  Period 2: {analytics2['sharpe_ratio']:.2f}\n"

        return comparison_text
    except Exception as e:
        logging.error(f"Failed to compare periods: {e}")
        return f"Error comparing periods: {e}"

def get_mt5_server_time() -> datetime:
    """
    Get the current server time from MT5.

    Returns:
        Current server time as a datetime object in UTC.
    """
    global mt5_failure_count
    try:
        with mt5_lock:
            # MT5 provides server time in seconds since epoch (UTC)
            server_time = mt5.terminal_info().server_time
            if not server_time:
                raise Exception("Unable to fetch MT5 server time.")
            # Convert to datetime in UTC
            server_dt = datetime.fromtimestamp(server_time, tz=pytz.UTC)
        logging.debug(f"MT5 Server Time (UTC): {server_dt}, System Time (UTC): {datetime.now(pytz.UTC)}")
        mt5_failure_count = 0
        return server_dt
    except Exception as e:
        mt5_failure_count += 1
        logging.error(f"Failed to get MT5 server time: {e}")
        # Fallback to system time in UTC if MT5 server time is unavailable
        system_time = datetime.now(pytz.UTC)
        logging.warning(f"Falling back to system time (UTC): {system_time}")
        return system_time

def get_decision_log(symbol: str = SYMBOL, limit: int = 5, offset: int = 0) -> Tuple[str, Optional[InlineKeyboardMarkup], int, int]:
    """
    Retrieve the decision log for a given symbol with pagination.

    Args:
        symbol: Symbol to retrieve decisions for.
        limit: Maximum number of decisions to retrieve per page.
        offset: Offset for pagination (starting point).

    Returns:
        Tuple of (formatted decision log text, inline keyboard markup, current offset, total decisions).
        Returns (text, None, offset, 0) if no decisions.
    """
    try:
        # Get total number of decisions
        with engine.connect() as conn:
            total_query = text("SELECT COUNT(*) FROM decisions WHERE symbol = :symbol")
            total = conn.execute(total_query, {"symbol": symbol}).scalar()

        if total == 0:
            return f"No decisions logged for {symbol}.", None, offset, 0

        # Fetch decisions with pagination
        query: str = """
            SELECT timestamp, symbol, action
            FROM decisions
            WHERE symbol = :symbol
            ORDER BY timestamp DESC
            LIMIT :limit OFFSET :offset
        """
        params: Dict[str, Any] = {"symbol": symbol, "limit": limit, "offset": offset}
        df: pd.DataFrame = pd.read_sql_query(query, engine, params=params)

        if df.empty:
            return f"No more decisions logged for {symbol}.", None, offset, total

        # Format the message with bold header and actions
        message: str = f"📊 *Recent Decisions for {symbol} (Showing {offset + 1}-{offset + len(df)} of {total})* 📊\n"
        for idx, entry in df.iterrows():
            timestamp = pd.to_datetime(entry['timestamp']).strftime('%Y-%m-%d %H:%M')
            action = entry['action']
            message += f"{offset + idx + 1}. 🕒 {timestamp}  |  *{symbol}* - *{action}*\n"

        # Add inline buttons with pagination
        keyboard = []
        nav_buttons = []
        if offset > 0:
            nav_buttons.append(InlineKeyboardButton("Previous", callback_data=f"decisions_prev_{offset - limit}"))
        if offset + limit < total:
            nav_buttons.append(InlineKeyboardButton("Next", callback_data=f"decisions_next_{offset + limit}"))
        if nav_buttons:
            keyboard.append(nav_buttons)
        keyboard.append([InlineKeyboardButton("View Trades", callback_data="view_trades")])
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None

        logging.info(f"Retrieved decision log: {message}")
        return message, reply_markup, offset, total
    except Exception as e:
        logging.error(f"Failed to get decision log: {e}")
        return f"Error retrieving decision log: {e}", None, offset, 0

def generate_price_chart() -> str:
    """
    Generate a price chart for the symbol.

    Returns:
        Path to the generated price chart.
    """
    try:
        rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, 100)
        if rates is None or len(rates) == 0:
            raise Exception("Unable to fetch price data.")
        df: pd.DataFrame = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')

        plt.figure(figsize=(10, 5))
        plt.plot(df['time'], df['close'], label='Close Price', color='blue')
        plt.title(f"{SYMBOL} Price Chart (M15)", fontweight='bold')
        plt.xlabel("Time")
        plt.ylabel("Price (USD)")
        plt.legend()
        plt.grid()
        chart_path: str = os.path.join(PLOT_PATH, "price_chart.png")
        plt.savefig(chart_path)
        plt.close()
        return chart_path
    except Exception as e:
        logging.error(f"Failed to generate price chart: {e}")
        raise

def compute_analytics(start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> Dict[str, Any]:
    try:
        query: str = "SELECT * FROM trades"
        params: Dict[str, Any] = {}
        if start_date and end_date:
            query += " WHERE timestamp BETWEEN :start_date AND :end_date"
            params = {"start_date": start_date, "end_date": end_date}
        df: pd.DataFrame = pd.read_sql_query(query, engine, params=params)

        if df.empty:
            logging.warning("Trade log is empty or no trades in the specified date range")
            return {
                'total_trades': 0,
                'win_rate': 0.0,
                'total_pl': 0.0,
                'max_drawdown': 0.0,
                'sharpe_ratio': 0.0,
                'monthly_profit': 0.0
            }

        df['timestamp'] = pd.to_datetime(df['timestamp'])
        numeric_cols: List[str] = ['price', 'position_size', 'equity', 'profit_loss', 'capital_change',
                                   'capital_change_percent', 'cumulative_profit_loss', 'win_rate',
                                   'average_profit_per_trade', 'sharpe_ratio', 'max_drawdown']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        total_trades: int = len(df[df['trade_type'] == 'CLOSE_BUY'])
        wins: int = len(df[(df['trade_type'] == 'CLOSE_BUY') & (df['profit_loss'] > 0)])
        win_rate: float = wins / total_trades if total_trades > 0 else 0.0
        total_pl: float = df['profit_loss'].sum()

        equity_series: np.ndarray = df['equity'].values
        peak: np.ndarray = np.maximum.accumulate(equity_series)
        drawdown: np.ndarray = (peak - equity_series) / peak
        max_drawdown: float = drawdown.max() if len(drawdown) > 0 else 0.0

        # Filter out HOLD actions for Sharpe ratio calculation
        df_trades = df[df['trade_type'].isin(['BUY', 'CLOSE_BUY'])].copy()
        if df_trades.empty or len(df_trades) < 2:
            sharpe_ratio = 0.0
        else:
            # Resample to daily intervals to capture unrealized P/L and ensure consistent frequency
            df.set_index('timestamp', inplace=True)
            daily_equity = df['equity'].resample('D').last().ffill()  # Use all data to capture equity changes
            daily_returns = daily_equity.pct_change().dropna()

            # Filter trades and align with daily equity
            df_trades.set_index('timestamp', inplace=True)
            trade_days = df_trades.index.floor('D').unique()
            daily_trade_equity = daily_equity[daily_equity.index.floor('D').isin(trade_days)]
            daily_trade_returns = daily_trade_equity.pct_change().dropna()

            if len(daily_trade_returns) < 2:
                sharpe_ratio = 0.0
            else:
                # Annualized mean return (daily return * 252)
                mean_daily_return = daily_trade_returns.mean()
                annualized_mean_return = mean_daily_return * 252

                # Annualized standard deviation (daily std * sqrt(252))
                std_daily_return = daily_trade_returns.std()
                annualized_std = std_daily_return * np.sqrt(252)

                # Risk-free rate (e.g., 4% per year)
                risk_free_rate_annual = 0.04
                risk_free_rate_daily = risk_free_rate_annual / 252
                annualized_risk_free_rate = risk_free_rate_daily * 252

                # Sharpe ratio
                if annualized_std != 0:
                    sharpe_ratio = (annualized_mean_return - annualized_risk_free_rate) / annualized_std
                else:
                    sharpe_ratio = 0.0

        df.reset_index(inplace=True)
        df['month'] = df['timestamp'].dt.to_period('M')
        monthly_groups = df.groupby('month')
        monthly_profit: float = 0.0
        for month, group in monthly_groups:
            initial_equity: float = group['equity'].iloc[0]
            final_equity: float = group['equity'].iloc[-1]
            profit: float = (final_equity - initial_equity) / initial_equity if initial_equity != 0 else 0.0
            monthly_profit = profit

        return {
            'total_trades': total_trades,
            'win_rate': win_rate,
            'total_pl': total_pl,
            'max_drawdown': max_drawdown,
            'sharpe_ratio': sharpe_ratio,
            'monthly_profit': monthly_profit
        }
    except Exception as e:
        logging.error(f"Failed to compute analytics: {e}")
        return {
            'total_trades': 0,
            'win_rate': 0.0,
            'total_pl': 0.0,
            'max_drawdown': 0.0,
            'sharpe_ratio': 0.0,
            'monthly_profit': 0.0
        }

def generate_dashboard(start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> Tuple[str, Optional[str], Optional[str]]:
    try:
        analytics: Dict[str, Any] = compute_analytics(start_date, end_date)
        equity_chart, equity_title = generate_equity_curve(start_date, end_date)
        drawdown_chart, max_drawdown, drawdown_title = generate_drawdown_curve(start_date, end_date)
        
        # Add new metrics
        profit_factor_stats = compute_profit_factor(start_date, end_date)
        recovery_factor_stats = compute_recovery_factor(start_date, end_date)
        win_loss_stats = compute_win_loss_streaks(start_date, end_date)
        transaction_costs = compute_transaction_costs(start_date, end_date)
        overtrading_stats = compute_overtrading_metrics(start_date, end_date)

        dashboard_text: str = (
            f"---\n"
            f"🔢 *Total Trades:* {analytics['total_trades']}\n"
            f"🏆 *Win Rate:* {analytics['win_rate']:.2%}\n"
            f"💷 *Total P/L:* £{analytics['total_pl']:.2f}\n"
            f"📉 *Max Drawdown:* {analytics['max_drawdown']:.2%}\n"
            f"📈 *Sharpe Ratio:* {analytics['sharpe_ratio']:.2f}\n"
            f"📈 *Profit Factor:* {profit_factor_stats['profit_factor']:.2f}\n"
            f"📈 *Recovery Factor:* {recovery_factor_stats['recovery_factor']:.2f}\n"
            f"🏆 *Longest Win Streak:* {win_loss_stats['longest_win_streak']}\n"
            f"📉 *Longest Loss Streak:* {win_loss_stats['longest_loss_streak']}\n"
            f"💸 *Transaction Costs:* £{transaction_costs['total_costs']:.2f}\n"
            f"📊 *Trades per Day:* {overtrading_stats['trades_per_day']:.2f}"
        )

        return dashboard_text, equity_chart, drawdown_chart
    except Exception as e:
        logging.error(f"Failed to generate dashboard: {e}")
        raise

def check_alerts() -> None:
    """
    Check for profit and drawdown alerts.
    """
    global drawdown_alert_triggered, profit_alert_triggered
    try:
        now: datetime = datetime.now()
        start_of_month: datetime = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        analytics: Dict[str, Any] = compute_analytics(start_date=start_of_month, end_date=now)
        monthly_profit: float = analytics['monthly_profit']
        if monthly_profit > 0.05 and not profit_alert_triggered:
            notify(f"Monthly Profit Alert: Profit exceeds 5% at {monthly_profit:.2%} for the month!")
            profit_alert_triggered = True
        elif monthly_profit <= 0.05:
            profit_alert_triggered = False

        df: pd.DataFrame = pd.read_sql_query("SELECT equity FROM trades", engine)

        if df.empty or 'equity' not in df.columns:
            logging.warning("Trade log is empty or missing equity column")
            return

        df['equity'] = pd.to_numeric(df['equity'], errors='coerce')
        df = df.dropna(subset=['equity'])
        if df.empty:
            logging.warning("No valid equity data for drawdown calculation")
            return

        equity_series: np.ndarray = df['equity'].values
        peak: np.ndarray = np.maximum.accumulate(equity_series)
        drawdown: np.ndarray = (peak - equity_series) / peak
        current_drawdown: float = drawdown[-1] if len(drawdown) > 0 else 0.0
        if current_drawdown > 0.05 and not drawdown_alert_triggered:
            notify(f"Drawdown Alert: Current drawdown exceeds 5% at {current_drawdown:.2%}!")
            drawdown_alert_triggered = True
        elif current_drawdown <= 0.05:
            drawdown_alert_triggered = False
    except Exception as e:
        logging.error(f"Failed to check alerts: {e}")

def get_trade_log(
    trade_type: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = 10,
    offset: int = 0
) -> Tuple[str, Optional[InlineKeyboardMarkup], int, int]:
    """
    Retrieve the trade log with pagination and include a Details button for each trade.
    """
    try:
        # Build the query for counting total trades
        total_query: str = "SELECT COUNT(*) FROM trades"
        params: Dict[str, Any] = {}
        conditions: List[str] = []
        if trade_type:
            conditions.append("trade_type = :trade_type")
            params["trade_type"] = trade_type
        if start_date and end_date:
            conditions.append("timestamp BETWEEN :start_date AND :end_date")
            params["start_date"] = start_date.strftime('%Y-%m-%d %H:%M:%S')
            params["end_date"] = end_date.strftime('%Y-%m-%d %H:%M:%S')
        elif start_date:
            conditions.append("timestamp >= :start_date")
            params["start_date"] = start_date.strftime('%Y-%m-%d %H:%M:%S')
        elif end_date:
            conditions.append("timestamp <= :end_date")
            params["end_date"] = end_date.strftime('%Y-%m-%d %H:%M:%S')

        if conditions:
            total_query += " WHERE " + " AND ".join(conditions)

        with engine.connect() as conn:
            total = conn.execute(text(total_query), params).scalar()

        if total == 0:
            return "No trades found for the specified criteria.", None, offset, 0

        # Fetch trades with pagination
        query: str = """
            SELECT id, timestamp, trade_type, symbol, price, position_size, unit_label, profit_loss, equity
            FROM trades
        """
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY timestamp DESC LIMIT :limit OFFSET :offset"
        params["limit"] = limit
        params["offset"] = offset

        df: pd.DataFrame = pd.read_sql_query(query, engine, params=params)
        if df.empty:
            return "No more trades found for the specified criteria.", None, offset, total

        # Format the trade log message
        trade_type_str: str = trade_type if trade_type else "All"
        period_text: str = (
            f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"
            if start_date and end_date
            else "All Time" if not start_date and not end_date
            else f"Past {int((datetime.now() - start_date).days)} days" if start_date else f"Up to {end_date.strftime('%Y-%m-%d')}"
        )
        message: str = (
            f"📊 *Trade Log: {trade_type_str} ({period_text})*\n"
            f"Showing {offset + 1}-{min(offset + len(df), total)} of {total} trades\n"
            "----------------------------------------\n"
        )

        # Create inline keyboard with pagination, time range filters, and details buttons
        keyboard = []
        for idx, row in df.iterrows():
            timestamp = pd.to_datetime(row['timestamp']).strftime('%Y-%m-%d %H:%M')
            trade_type = row['trade_type']
            symbol = row['symbol']
            close_price = row['price']
            position_size = row['position_size']
            profit_loss = row['profit_loss']
            equity = row['equity']
            trade_id = row['id']
            
            # Fetch the matching BUY trade for pip calculation
            if trade_type == "CLOSE_BUY":
                query_open = """
                    SELECT price FROM trades
                    WHERE trade_type = 'BUY' AND symbol = :symbol AND timestamp < :close_time
                    ORDER BY timestamp DESC LIMIT 1
                """
                params_open = {
                    "symbol": symbol,
                    "close_time": timestamp
                }
                df_open = pd.read_sql_query(query_open, engine, params=params_open)
                open_price = df_open['price'].iloc[0] if not df_open.empty else close_price
                pips = round((close_price - open_price) * 10, 1)  # 1 pip = 0.1 for GOLD
            else:
                pips = 0.0  # No pip for open positions

            message += (
                f"{offset + idx + 1}. 🕒 {timestamp}\n"
                f"🔁 *{symbol}* - *{trade_type}*\n"
                f"📈 Price: ${close_price:.2f}\n"
                f"🎯 Size: {position_size} {row['unit_label']}\n"
                f"💷 P/L: £{profit_loss:.2f} | Pips: {pips:+.1f}\n"
                f"📊 Equity: £{equity:.2f}\n"
                f"----------------------------------------\n"
            )
            # Add Details button for CLOSE_BUY trades
            if trade_type == "CLOSE_BUY":
                keyboard.append([InlineKeyboardButton("Details", callback_data=f"trade_details_{trade_id}")])

        # Add pagination buttons
        nav_buttons = []
        if offset > 0:
            nav_buttons.append(InlineKeyboardButton("Previous", callback_data=f"trades_prev_{max(0, offset - limit)}"))
        if offset + limit < total:
            nav_buttons.append(InlineKeyboardButton("Next", callback_data=f"trades_next_{offset + limit}"))
        if nav_buttons:
            keyboard.append(nav_buttons)

        # Add time range filter buttons
        filter_buttons = [
            InlineKeyboardButton("Past Week", callback_data="log_week"),
            InlineKeyboardButton("Past Month", callback_data="log_month"),
            InlineKeyboardButton("Past 3 Months", callback_data="log_3months"),
            InlineKeyboardButton("Past 6 Months", callback_data="log_6months"),
            InlineKeyboardButton("Past 9 Months", callback_data="log_9months"),
            InlineKeyboardButton("Past 12 Months", callback_data="log_12months"),
            InlineKeyboardButton("Most Recent", callback_data="log_most_recent"),
            InlineKeyboardButton("All Time", callback_data="log_all")
        ]
        keyboard.append([filter_buttons[i] for i in range(0, 4)])
        keyboard.append([filter_buttons[i] for i in range(4, 8)])

        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        logging.info(f"Retrieved trade log: {len(df)} trades, offset {offset}, total {total}")
        return message, reply_markup, offset, total
    except Exception as e:
        logging.error(f"Failed to get trade log: {e}")
        return f"Error retrieving trade log: {e}", None, offset, 0

def check_price_alerts() -> None:
    """
    Check for price alerts and notify if triggered.
    """
    global mt5_failure_count
    try:
        tick = mt5.symbol_info_tick(SYMBOL)
        if not tick:
            mt5_failure_count += 1
            return
        current_price: float = tick.bid
        new_alerts: List[Tuple[float, str, bool, str]] = []
        for alert in price_alerts:
            price, condition, recurring, chat_id = alert
            triggered: bool = False
            if condition == "above" and current_price >= price:
                notify(f"Price Alert: {SYMBOL} is above ${price:.2f} | Current: ${current_price:.2f}", chat_id)
                triggered = True
            elif condition == "below" and current_price <= price:
                notify(f"Price Alert: {SYMBOL} is below ${price:.2f} | Current: ${current_price:.2f}", chat_id)
                triggered = True
            if not triggered or recurring:
                new_alerts.append(alert)
        price_alerts.clear()
        price_alerts.extend(new_alerts)
        mt5_failure_count = 0  # Reset failure count on success
    except Exception as e:
        mt5_failure_count += 1
        logging.error(f"Failed to check price alerts: {e}")

def get_trade_profit_gbp(position_ticket: int) -> float:
    """
    Get the profit of a trade in GBP.

    Args:
        position_ticket: Position ticket ID.

    Returns:
        Profit in GBP.
    """
    global mt5_failure_count
    try:
        history = mt5.history_deals_get(position=position_ticket)
        if not history:
            return 0.0
        total_profit: float = sum(deal.profit for deal in history)
        profit_gbp: float = total_profit * EXCHANGE_RATE
        mt5_failure_count = 0  # Reset failure count on success
        return profit_gbp
    except Exception as e:
        mt5_failure_count += 1
        logging.error(f"Failed to get trade profit for position {position_ticket}: {e}")
        return 0.0

def calculate_max_position_size(current_price: float, symbol_info: Any, is_spread_betting: bool = False) -> Tuple[float, str]:
    """
    Calculate the maximum position size based on available margin.

    Args:
        current_price: Current price of the symbol.
        symbol_info: Symbol information from MT5.

    Returns:
        Tuple of (position_size, unit_label).
    """
    global mt5_failure_count
    try:
        if not symbol_info:
            raise Exception("Symbol info not available.")
        account_info = mt5.account_info()
        if not account_info:
            raise Exception("Unable to get account info.")
        equity: float = account_info.equity * EXCHANGE_RATE
        free_margin: float = account_info.margin_free
        if equity < MIN_EQUITY_THRESHOLD:
            raise Exception(f"Equity too low: £{equity:.2f} < £{MIN_EQUITY_THRESHOLD:.2f}")

        margin_1_lot: float = mt5.order_calc_margin(mt5.ORDER_TYPE_BUY, SYMBOL, 1.0, current_price)
        if margin_1_lot <= 0:
            raise Exception("Unable to calculate margin for 1 lot.")

        position_size: float = (free_margin / EXCHANGE_RATE) / margin_1_lot
        position_size = max(MIN_POSITION_SIZE, position_size)
        unit_label: str = "lots"
        mt5_failure_count = 0  # Reset failure count on success
        return position_size, unit_label
    except Exception as e:
        mt5_failure_count += 1
        logging.error(f"Failed to calculate position size: {e}")
        raise

def get_atr(timeframe: int, period: int) -> float:
    """
    Calculate the Average True Range (ATR) for a given timeframe.

    Args:
        timeframe: MT5 timeframe (e.g., mt5.TIMEFRAME_H4).
        period: Period for ATR calculation.

    Returns:
        ATR value.
    """
    try:
        rates = mt5.copy_rates_from_pos(SYMBOL, timeframe, 0, period + 1)
        if rates is None or len(rates) < period + 1:
            return 0.0
        df: pd.DataFrame = pd.DataFrame(rates)
        high_low: pd.Series = df['high'] - df['low']
        high_close: pd.Series = (df['high'] - df['close'].shift()).abs()
        low_close: pd.Series = (df['low'] - df['close'].shift()).abs()
        true_range: pd.Series = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr: float = true_range.rolling(window=period).mean().iloc[-1]
        return atr
    except Exception as e:
        logging.error(f"Failed to calculate ATR for timeframe {timeframe}: {e}")
        return 0.0

def fetch_market_data() -> Tuple[Optional[np.ndarray], Optional[Dict[str, float]]]:
    """
    Fetch market data and compute features for prediction.

    Returns:
        Tuple of (feature_sequence, features). Returns (None, None) if data fetch fails.
    """
    global mt5_failure_count
    retries: int = 3
    for attempt in range(retries):
        try:
            # Use a lock to ensure thread-safe access to MT5
            with mt5_lock:
                # Fetch M15 data
                rates_15m = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, SEQUENCE_LENGTH)
                if rates_15m is None or len(rates_15m) < SEQUENCE_LENGTH:
                    raise Exception(f"Insufficient M15 data: {len(rates_15m) if rates_15m is not None else 'None'} bars.")
                df_15m: pd.DataFrame = pd.DataFrame(rates_15m)
                df_15m['time'] = pd.to_datetime(df_15m['time'], unit='s')

                # Fetch H4 data
                rates_4h = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_H4, 0, SEQUENCE_LENGTH)
                if rates_4h is None or len(rates_4h) < SEQUENCE_LENGTH:
                    raise Exception(f"Insufficient H4 data: {len(rates_4h) if rates_4h is not None else 'None'} bars.")
                df_4h: pd.DataFrame = pd.DataFrame(rates_4h)
                df_4h['time'] = pd.to_datetime(df_4h['time'], unit='s')

                # Fetch Daily data
                rates_daily = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_D1, 0, 30)
                if rates_daily is None or len(rates_daily) < 30:
                    raise Exception(f"Insufficient Daily data: {len(rates_daily) if rates_daily is not None else 'None'} bars.")
                df_daily: pd.DataFrame = pd.DataFrame(rates_daily)
                df_daily['time'] = pd.to_datetime(df_daily['time'], unit='s')

            # Create a DataFrame to store all features
            features_df = pd.DataFrame(index=range(SEQUENCE_LENGTH))

            # Compute M15 features
            features_df['Close_15M'] = df_15m['close'].astype(float)
            features_df['Volume_15M'] = df_15m['tick_volume'].astype(int)

            # Compute H4 features
            features_df['Close_4H'] = df_4h['close'].reindex(features_df.index, method='ffill').astype(float)
            features_df['Volume_4H'] = df_4h['tick_volume'].reindex(features_df.index, method='ffill').astype(int)

            # Compute RSI and ATR for H4
            delta_4h = df_4h['close'].diff()
            if len(delta_4h) >= 14:
                gain_4h = delta_4h.where(delta_4h > 0, 0).rolling(window=14, min_periods=14).mean()
                loss_4h = (-delta_4h.where(delta_4h < 0, 0)).rolling(window=14, min_periods=14).mean()
                rs_4h = gain_4h / loss_4h
                rsi_4h = 100 - (100 / (1 + rs_4h))
                features_df['RSI_4H'] = rsi_4h.reindex(features_df.index, method='ffill').fillna(0.0)
            else:
                features_df['RSI_4H'] = 0.0
            with mt5_lock:  # Lock for ATR computation
                atr_4h = get_atr(mt5.TIMEFRAME_H4, 14)
            features_df['ATR_4H'] = atr_4h if not np.isnan(atr_4h) else 0.0

            # Compute RSI and ATR for Daily
            delta_daily = df_daily['close'].diff()
            if len(delta_daily) >= 14:
                gain_daily = delta_daily.where(delta_daily > 0, 0).rolling(window=14, min_periods=14).mean()
                loss_daily = (-delta_daily.where(delta_daily < 0, 0)).rolling(window=14, min_periods=14).mean()
                rs_daily = gain_daily / loss_daily
                rsi_daily = 100 - (100 / (1 + rs_daily))
                features_df['RSI_Daily'] = rsi_daily.reindex(features_df.index, method='ffill').fillna(0.0)
            else:
                features_df['RSI_Daily'] = 0.0
            with mt5_lock:  # Lock for ATR computation
                atr_daily = get_atr(mt5.TIMEFRAME_D1, 14)
            features_df['ATR_Daily'] = atr_daily if not np.isnan(atr_daily) else 0.0

            # Compute basic features
            features_df['Close'] = df_15m['close'].astype(float)
            features_df['Volume'] = df_15m['tick_volume'].astype(int)

            # Compute pivot points
            high = df_15m['high'].astype(float)
            low = df_15m['low'].astype(float)
            close = df_15m['close'].astype(float)
            features_df['pivot'] = (high + low + close) / 3
            features_df['r1'] = 2 * features_df['pivot'] - low
            features_df['s1'] = 2 * features_df['pivot'] - high
            features_df['r2'] = features_df['pivot'] + (high - low)
            features_df['s2'] = features_df['pivot'] - (high - low)

            # Ensure all columns are numeric and handle NaNs
            for col in FEATURES:
                features_df[col] = pd.to_numeric(features_df[col], errors='coerce').fillna(0.0)

            # Prepare feature array
            feature_array = features_df[FEATURES].to_numpy()

            # Get the latest features for logging
            latest_features = features_df[FEATURES].iloc[-1].to_dict()

            mt5_failure_count = 0  # Reset failure count on success
            logging.info("Market data fetched and features computed successfully.")
            return feature_array, latest_features

        except Exception as e:
            mt5_failure_count += 1
            logging.error(f"Failed to fetch market data on attempt {attempt+1}/{retries}: {e}")
            if attempt == retries - 1:
                notify(f"Failed to fetch market data after {retries} attempts: {e}")
            time.sleep(2 ** attempt)

    return None, None

def is_new_candle() -> bool:
    """
    Check if a new 15-minute candle has formed by comparing the latest candle timestamp
    with the previously recorded timestamp, using MT5 data only.

    Returns:
        True if a new candle is detected, False otherwise.
    """
    global mt5_failure_count, last_candle_timestamp
    try:
        # Fetch the two most recent candles
        rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, 2)  # Get 2 candles to compare
        if rates is None or len(rates) < 2:
            logging.warning(f"Unable to fetch rates for candle detection: {mt5.last_error()}")
            mt5_failure_count += 1
            return False

        # Get the timestamp of the latest candle
        latest_candle_time = pd.to_datetime(rates[0]['time'], unit='s')
        
        # Log the latest and previous candle timestamps for debugging
        previous_candle_time = pd.to_datetime(rates[1]['time'], unit='s')
        logging.debug(
            f"Candle check - Latest candle: {latest_candle_time}, "
            f"Previous candle: {previous_candle_time}, "
            f"Last recorded candle: {last_candle_timestamp}"
        )

        # If this is the first check, initialize last_candle_timestamp and return False
        if last_candle_timestamp is None:
            last_candle_timestamp = latest_candle_time
            logging.debug("Initialized last_candle_timestamp. Waiting for next candle.")
            mt5_failure_count = 0
            return False

        # Check if the latest candle timestamp has changed since the last check
        if latest_candle_time > last_candle_timestamp:
            logging.info(f"New candle detected: {latest_candle_time}")
            last_candle_timestamp = latest_candle_time
            mt5_failure_count = 0
            return True
        
        # No new candle
        mt5_failure_count = 0
        return False
    except Exception as e:
        mt5_failure_count += 1
        logging.error(f"Failed to check for new candle: {e}")
        return False

def make_prediction(model: PPO, scaler: MinMaxScaler, feature_sequence: np.ndarray) -> Tuple[int, str]:
    """
    Make a prediction using the PPO model.

    Args:
        model: Trained PPO model.
        scaler: Fitted MinMaxScaler.
        feature_sequence: Feature sequence for prediction as a numpy array.

    Returns:
        Tuple of (action, action_label).
    """
    try:
        # Validate feature sequence shape
        if feature_sequence.shape[1] != len(FEATURES):
            raise ValueError(f"Feature sequence has {feature_sequence.shape[1]} features, expected {len(FEATURES)}")
        
        # Convert NumPy array to DataFrame with feature names
        feature_df = pd.DataFrame(feature_sequence, columns=FEATURES)
        scaled_features: np.ndarray = scaler.transform(feature_df)
        scaled_features_tensor: torch.Tensor = torch.tensor(scaled_features, dtype=torch.float32).unsqueeze(0)
        action, _ = model.predict(scaled_features_tensor, deterministic=True)
        action = int(action[0])
        action_label: str = "BUY" if action == 0 else "CLOSE_BUY" if action == 1 else "HOLD"
        return action, action_label
    except Exception as e:
        logging.error(f"Failed to make prediction: {e}")
        return 2, "HOLD"

def execute_trade(action: int, action_label: str, current_price: float, features: Dict[str, float]) -> None:
    """
    Execute a trade based on the model's prediction.

    Args:
        action: Action index (0: BUY, 1: CLOSE_BUY, 2: HOLD).
        action_label: Action label ("BUY", "CLOSE_BUY", "HOLD").
        current_price: Current price of the symbol.
        features: Features used for the prediction.
    """
    global mt5_failure_count, notification_settings
    try:
        with mt5_lock:
            positions = mt5.positions_get(symbol=SYMBOL)
            symbol_info = mt5.symbol_info(SYMBOL)
            account_info = mt5.account_info()
            if not account_info:
                mt5_failure_count += 1
                raise Exception("Unable to fetch account info.")
            equity_raw: float = account_info.equity
            equity_gbp: float = equity_raw * EXCHANGE_RATE
            logging.debug(f"Equity raw: {equity_raw}, Converted to GBP: {equity_gbp}")

        # Check minimum equity threshold
        if equity_gbp < MIN_EQUITY_THRESHOLD:
            notify(f"Equity below threshold: £{equity_gbp:.2f} < £{MIN_EQUITY_THRESHOLD:.2f}. Trading halted.")
            return

        # Calculate drawdown by fetching historical equity
        try:
            with engine.connect() as conn:
                df = pd.read_sql_query("SELECT equity FROM trades ORDER BY timestamp", engine)
            if not df.empty and 'equity' in df.columns:
                df['equity'] = pd.to_numeric(df['equity'], errors='coerce').dropna()
                if not df.empty:
                    equity_series = df['equity'].values
                    peak = np.maximum.accumulate(equity_series)
                    drawdown = (peak - equity_series) / peak
                    current_drawdown = drawdown[-1] if len(drawdown) > 0 else 0.0
                    if current_drawdown > MAX_DRAWDOWN_THRESHOLD:
                        notify(f"Max drawdown exceeded: {current_drawdown:.2%} > {MAX_DRAWDOWN_THRESHOLD:.2%}. Trading halted.")
                        return
        except Exception as e:
            logging.error(f"Failed to calculate drawdown: {e}")
            notify(f"Error calculating drawdown: {e}")

        reasoning: str = f"Action {action_label} based on PPO model prediction with features: {features}"

        # Log the decision with a commit
        with engine.connect() as conn:
            conn.execute(
                text("INSERT INTO decisions (timestamp, symbol, action, reasoning) VALUES (:timestamp, :symbol, :action, :reasoning)"),
                {"timestamp": datetime.now(), "symbol": SYMBOL, "action": action_label, "reasoning": reasoning}
            )
            conn.commit()  # Explicitly commit the transaction

        # Execute trade logic
        if action_label == "BUY" and not positions:
            with mt5_lock:
                position_size: float = 0.2  # Hardcoded position size
                unit_label: str = "lots"    # Hardcoded unit label
                request: Dict[str, Any] = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": SYMBOL,
                    "volume": position_size,
                    "type": mt5.ORDER_TYPE_BUY,
                    "price": current_price,
                    "deviation": 20,
                    "magic": 234000,
                    "comment": "PPO BUY",
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": mt5.ORDER_FILLING_IOC,
                }
                result = mt5.order_send(request)
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                if notification_settings.get("BUY", True):
                    notify(f"BUY {SYMBOL} at ${current_price:.2f} | Size: {position_size} {unit_label} | Equity: £{equity_gbp:.2f}")
                log_trade(datetime.now(), "BUY", SYMBOL, current_price, position_size, "lots", 0.0, equity_gbp, reasoning, features)
                logging.info(f"BUY {SYMBOL} at ${current_price:.2f}, Size: {position_size} {unit_label}")
                # Disable BUY notifications
                notification_settings["BUY"] = False
                logging.info("BUY notifications disabled due to open position.")
                notify("🔔 *BUY Notifications Disabled* until position is closed.", parse_mode="MarkdownV2")
            else:
                error_msg: str = f"BUY failed: {result.comment} (retcode: {result.retcode})"
                notify(error_msg)
                logging.error(error_msg)
        elif action_label == "CLOSE_BUY" and positions:
            position = positions[0]
            position_ticket: int = position.ticket
            position_volume: float = position.volume
            open_price: float = position.price_open
            pips: float = round((current_price - open_price) * 10, 1)  # 1 pip = 0.1 for GOLD
            with mt5_lock:
                request: Dict[str, Any] = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": SYMBOL,
                    "volume": position_volume,
                    "type": mt5.ORDER_TYPE_SELL,
                    "position": position_ticket,
                    "price": current_price,
                    "deviation": 20,
                    "magic": 234000,
                    "comment": "PPO CLOSE",
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": mt5.ORDER_FILLING_IOC,
                }
                result = mt5.order_send(request)
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                with mt5_lock:
                    profit_loss_gbp: float = get_trade_profit_gbp(position_ticket)
                if notification_settings.get("CLOSE_BUY", True):
                    notify(f"CLOSE {SYMBOL} at ${current_price:.2f} | Profit/Loss: £{profit_loss_gbp:.2f} | Pips: {pips:+.1f} | Equity: £{equity_gbp:.2f}")
                log_trade(datetime.now(), "CLOSE_BUY", SYMBOL, current_price, position_volume, "lots", profit_loss_gbp, equity_gbp, reasoning, features)
                logging.info(f"CLOSE {SYMBOL} at ${current_price:.2f}, Profit/Loss: £{profit_loss_gbp:.2f}, Pips: {pips:+.1f}")
                # Re-enable BUY notifications
                notification_settings["BUY"] = True
                logging.info("BUY notifications re-enabled after position closed.")
                notify("🔔 *BUY Notifications Re-enabled* after position closed.", parse_mode="MarkdownV2")
            else:
                error_msg: str = f"CLOSE failed: {result.comment} (retcode: {result.retcode})"
                notify(error_msg)
                logging.error(error_msg)
        elif action_label == "HOLD":
            log_trade(datetime.now(), "HOLD", SYMBOL, current_price, 0.0, "lots", 0.0, equity_gbp, reasoning, features)
            logging.info(f"HOLD position for {SYMBOL} at ${current_price:.2f}")
        mt5_failure_count = 0  # Reset failure count on success
    except Exception as e:
        mt5_failure_count += 1
        logging.error(f"Failed to execute trade: {e}")
        notify(f"Error executing trade: {e}")

def get_help_message() -> List[str]:
    """
    Generate the help message with command explanations.

    Returns:
        List of message sections to comply with Telegram's 4096-character limit.
    """
    try:
        help_text = (
            "<b>Trading Bot Help Menu</b>\n\n"
            "Below is a list of available commands and inline buttons with their descriptions.\n\n"
            "<b>Commands with Parameters:</b>\n"
            "- <code>/start</code>\n"
            "  Starts the bot and sends the inline keyboard.\n\n"
            "- <code>/dailypl [thismonth|lastmonth|lastweek|YYYY-MM-DD to YYYY-MM-DD]</code>\n"
            "  Generate a histogram of daily profit/loss. Example: <code>/dailypl thismonth</code>\n\n"
            "- <code>/alert &lt;price&gt; [above|below] [recurring]</code>\n"
            "  Set a price alert. Example: <code>/alert 2500 above recurring</code>\n"
            "  Triggers when price goes above/below the specified value. 'recurring' makes it repeat.\n\n"
            "- <code>/log [buy|close_buy] [thismonth|lastmonth|lastweek|YYYY-MM-DD to YYYY-MM-DD]</code>\n"
            "  View trade history. Example: <code>/log buy lastmonth</code>\n"
            "  Filters trades by type and date range.\n\n"
            "- <code>/report [thismonth|lastmonth|lastweek|YYYY-MM-DD to YYYY-MM-DD]</code>\n"
            "  Generate analytics report. Example: <code>/report 2025-04-01 to 2025-04-30</code>\n"
            "  Shows performance metrics for the specified period.\n\n"
            "- <code>/equity [thismonth|lastmonth|lastweek|YYYY-MM-DD to YYYY-MM-DD]</code>\n"
            "  View equity curve. Example: <code>/equity thismonth</code>\n"
            "  Plots equity over time.\n\n"
            "- <code>/drawdown [thismonth|lastmonth|lastweek|YYYY-MM-DD to YYYY-MM-DD]</code>\n"
            "  View drawdown curve. Example: <code>/drawdown lastweek</code>\n"
            "  Shows drawdown percentages over time.\n\n"
            "- <code>/dashboard [thismonth|lastmonth|lastweek|YYYY-MM-DD to YYYY-MM-DD]</code>\n"
            "  View trading dashboard. Example: <code>/dashboard thismonth</code>\n"
            "  Displays analytics and charts.\n\n"
            "- <code>/heartbeat &lt;X&gt;</code>\n"
            "  Set bot to send 'I'm alive' messages every X hours. Example: <code>/heartbeat 4</code>\n"
            "  Set to 0 to disable.\n\n"
            "- <code>/compare period1 period2</code>\n"
            "  Compare performance between two periods. Example: <code>/compare lastmonth thismonth</code>\n"
            "  Shows metrics side by side.\n\n"
            "- <code>/exportcsv [thismonth|lastmonth|lastweek|YYYY-MM-DD to YYYY-MM-DD]</code>\n"
            "  Export trade history to CSV. Example: <code>/exportcsv lastmonth</code>\n"
            "  Downloads trade data.\n\n"
            "- <code>/decisionlog [symbol]</code>\n"
            "  View last 5 decisions. Example: <code>/decisionlog GOLD</code>\n"
            "  Shows recent trading decisions.\n\n"
            "- <code>/setpositionsize &lt;size&gt;</code>\n"
            "  Set position size for BUY trades. Example: <code>/setpositionsize 0.1</code>\n"
            "  Sets the position size in lots (minimum 0.01).\n\n"
            "- <code>/monthlypl [thismonth|lastmonth|lastweek|YYYY-MM-DD to YYYY-MM-DD]</code>\n"
            "  Generate a bar chart of monthly profit/loss. Example: <code>/monthlypl thismonth</code>\n\n"
            "- <code>/togglenotify &lt;type&gt;</code>\n"
            "  Toggle notifications for trade decisions. Example: <code>/togglenotify HOLD</code>\n"
            "  Types: BUY, CLOSE_BUY, HOLD.\n\n"
            "- <code>/tradeduration [thismonth|lastmonth|lastweek|YYYY-MM-DD to YYYY-MM-DD]</code>\n"
            "  Generate a histogram of trade durations. Example: <code>/tradeduration lastmonth</code>\n\n"
            "- <code>/sharpetrend</code>\n"
            "  Generate a line chart of rolling Sharpe Ratio over time. Example: <code>/sharpetrend</code>\n\n"
            "- <code>/help</code>\n"
            "  Displays this help menu.\n\n"
            "<b>Inline Buttons:</b>\n"
            "- <b>Check Status</b>: Shows bot status (equity, position, pause state).\n"
            "- <b>Check Price</b>: Displays current market price.\n"
            "- <b>View Chart</b>: Sends a recent price chart.\n"
            "- <b>Daily P/L</b>: Generates a histogram of daily profit/loss.\n"
            "- <b>View Position</b>: Shows current open position details.\n"
            "- <b>Calmar Ratio Trend</b>: How much return you're making compared to the worst drawdown.\n"
            "- <b>Sortino Ratio Trend</b>: How much return are you making for each unit of bad risk.\n"
            "- <b>Help</b>: Displays this help menu.\n"
            "- <b>Monte Carlo Simulation</b>: Generates a Monte Carlo simulation for equity projection. It’s a way to test how reliable your strategy is by simulating many random versions of the future.\n"
            "- <b>Hourly P/L</b>: Generates an hourly performance chart.\n"
            "- <b>Day-of-Week P/L</b>: Generates a day-of-week performance chart.\n"
            "- <b>Trade Clustering</b>: Generates a trade clustering chart.\n"
            "- <b>Profit Factor</b>: How many £ you make for every £ you lose.\n"
            "- <b>Recovery Factor</b>: How well your strategy recovers from its worst loss, higher is better.\n"
            "- <b>Win/Loss Streaks</b>: Shows win/loss streak statistics.\n"
            "- <b>Transaction Costs</b>: Shows transaction costs.\n"
            "- <b>Overtrading Metrics</b>: Shows overtrading metrics.\n"
            "- <b>Holding Time vs. Profit</b>: Generates a holding time vs. profitability chart.\n"
            "- <b>Recent Trades</b>: Displays recent trade history (options: all, week, month, 3/6/9/12 months, most recent).\n"
            "- <b>Analytics Report</b>: Generates a performance report.\n"
            "- <b>Toggle Schedule</b>: Enables/disables scheduled reports every 4 hours.\n"
            "- <b>Toggle Monitoring</b>: Enables/disables position monitoring every 15 minutes.\n"
            "- <b>Stop Bot</b>: Stops the bot.\n"
            "- <b>Equity Curve</b>: Sends equity curve chart.\n"
            "- <b>Drawdowns</b>: Sends drawdown curve chart.\n"
            "- <b>Dashboard</b>: Sends dashboard with analytics and charts.\n"
            "- <b>Manual BUY</b>: Opens a position manually.\n"
            "- <b>Sharpe Ratio Trend</b>: How much return you’re getting for the risk you take.\n"
            "- <b>Trade Duration</b>: Generates a trade duration distribution chart.\n"
            "- <b>Monthly P/L</b>: Generates a monthly performance chart.\n"
            "- <b>Manual CLOSE</b>: Closes the current position.\n"
            "- <b>Health Check</b>: Runs a bot health check.\n"
            "- <b>Future Outlook</b>: Projects future equity based on historical returns.\n"
            "- <b>Trade Heatmap</b>: Shows trade profitability by time of day.\n"
            "- <b>Feature Importance</b>: Displays feature importance for predictions.\n"
            "- <b>Pause Trading</b>: Pauses automated trading.\n"
            "- <b>Resume Trading</b>: Resumes automated trading.\n"
            "- <b>Win Rate</b>: Shows win rate and related statistics.\n"
            "- <b>Return Stats</b>: Displays return statistics (compound, annualized, volatility).\n"
            "- <b>Decision Log</b>: Shows recent trading decisions.\n"
            "- <b>Toggle BUY Notify</b>: Toggles BUY notifications.\n"
            "- <b>Toggle CLOSE Notify</b>: Toggles CLOSE_BUY notifications.\n"
            "- <b>Toggle HOLD Notify</b>: Toggles HOLD notifications.\n\n"
            "<b>Notes:</b>\n"
            "- Use date ranges like 'thismonth', 'lastmonth', 'lastweek', or 'YYYY-MM-DD to YYYY-MM-DD'.\n"
            "- All prices are in USD, profits/losses in GBP.\n"
            "- Ensure position size is set with /setpositionsize before manual or automated BUY trades.\n"
            "- Contact support if issues persist."
        )

        # Split into sections to avoid Telegram's 4096-character limit
        sections = []
        current_section = ""
        for line in help_text.split("\n"):
            if len(current_section) + len(line) + 1 > 4096:
                sections.append(current_section.strip())
                current_section = line + "\n"
            else:
                current_section += line + "\n"
        if current_section.strip():
            sections.append(current_section.strip())

        return sections
    except Exception as e:
        logging.error(f"Failed to generate help message: {e}")
        return [f"Error generating help message: {e}"]
    
def generate_calmar_ratio_trend(start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> Tuple[Optional[str], str]:
    """
    Generate a line chart of rolling Calmar Ratio over time.

    Args:
        start_date: Start date for the data range.
        end_date: End date for the data range.

    Returns:
        Tuple of (chart_path, title). Returns (None, message) if trade log is empty.
    """
    try:
        query: str = "SELECT timestamp, equity FROM trades"
        params: Dict[str, Any] = {}
        if start_date and end_date:
            query += " WHERE timestamp BETWEEN :start_date AND :end_date"
            params = {"start_date": start_date, "end_date": end_date}
        df: pd.DataFrame = pd.read_sql_query(query, engine, params=params)

        if df.empty or 'equity' not in df.columns or 'timestamp' not in df.columns:
            logging.info("No trades available to plot Calmar Ratio trend.")
            return None, "No trades available to plot Calmar Ratio trend."

        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values('timestamp')
        df.set_index('timestamp', inplace=True)

        # Resample to daily equity
        daily_equity = df['equity'].resample('D').last().ffill()
        daily_returns = daily_equity.pct_change().dropna()

        # Calculate rolling Calmar Ratio (30-day window)
        calmar_ratios = []
        dates = []
        window_days = 30

        for i in range(window_days, len(daily_equity)):
            window_equity = daily_equity.iloc[i-window_days:i]
            window_returns = daily_returns.iloc[i-window_days:i]
            if len(window_returns) < 2:
                continue
            # Annualized return
            initial_equity = window_equity.iloc[0]
            final_equity = window_equity.iloc[-1]
            period_years = window_days / 365.0
            annualized_return = ((final_equity / initial_equity) ** (1 / period_years) - 1) if initial_equity != 0 else 0.0
            # Maximum drawdown
            peak = window_equity.cummax()
            drawdown = (peak - window_equity) / peak
            max_drawdown = drawdown.max() if len(drawdown) > 0 else 0.0
            # Calmar Ratio
            calmar_ratio = annualized_return / max_drawdown if max_drawdown != 0 else 0.0
            calmar_ratios.append(calmar_ratio)
            dates.append(daily_equity.index[i])

        if not calmar_ratios:
            logging.info("Insufficient data to calculate Calmar Ratio trend.")
            return None, "Insufficient data to plot Calmar Ratio trend."

        plt.figure(figsize=(10, 5))
        plt.plot(dates, calmar_ratios, label='Rolling Calmar Ratio (30-day)', color='green')
        plt.title("Calmar Ratio Trend (Rolling 30-Day)", fontweight='bold')
        plt.xlabel("Date")
        plt.ylabel("Calmar Ratio")
        plt.legend()
        plt.grid(True)

        chart_path: str = os.path.join(PLOT_PATH, "calmar_trend.png")
        plt.savefig(chart_path)
        plt.close()
        return chart_path, "Calmar Ratio Trend"
    except Exception as e:
        logging.error(f"Failed to generate Calmar Ratio trend: {e}")
        raise

def compute_profit_factor(start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> Dict[str, float]:
    """
    Compute the Profit Factor (gross profits / gross losses).

    Args:
        start_date: Start date for the data range.
        end_date: End date for the data range.

    Returns:
        Dictionary containing profit factor, gross profits, and gross losses.
    """
    try:
        query: str = "SELECT profit_loss FROM trades WHERE trade_type = 'CLOSE_BUY'"
        params: Dict[str, Any] = {}
        if start_date and end_date:
            query += " AND timestamp BETWEEN :start_date AND :end_date"
            params = {"start_date": start_date, "end_date": end_date}
        df: pd.DataFrame = pd.read_sql_query(query, engine, params=params)

        if df.empty or 'profit_loss' not in df.columns:
            return {
                'profit_factor': 0.0,
                'gross_profits': 0.0,
                'gross_losses': 0.0
            }

        gross_profits = df[df['profit_loss'] > 0]['profit_loss'].sum()
        gross_losses = abs(df[df['profit_loss'] < 0]['profit_loss'].sum())
        profit_factor = gross_profits / gross_losses if gross_losses != 0 else float('inf') if gross_profits > 0 else 0.0

        return {
            'profit_factor': profit_factor,
            'gross_profits': gross_profits,
            'gross_losses': gross_losses
        }
    except Exception as e:
        logging.error(f"Failed to compute profit factor: {e}")
        return {
            'profit_factor': 0.0,
            'gross_profits': 0.0,
            'gross_losses': 0.0
        }

def compute_recovery_factor(start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> Dict[str, float]:
    """
    Compute the Recovery Factor (absolute return / maximum drawdown).

    Args:
        start_date: Start date for the data range.
        end_date: End date for the data range.

    Returns:
        Dictionary containing recovery factor, absolute return, and maximum drawdown.
    """
    try:
        query: str = "SELECT timestamp, equity FROM trades"
        params: Dict[str, Any] = {}
        if start_date and end_date:
            query += " WHERE timestamp BETWEEN :start_date AND :end_date"
            params = {"start_date": start_date, "end_date": end_date}
        df: pd.DataFrame = pd.read_sql_query(query, engine, params=params)

        if df.empty or 'equity' not in df.columns or 'timestamp' not in df.columns:
            return {
                'recovery_factor': 0.0,
                'absolute_return': 0.0,
                'max_drawdown': 0.0
            }

        df = df.sort_values('timestamp')
        initial_equity = df['equity'].iloc[0]
        final_equity = df['equity'].iloc[-1]
        absolute_return = (final_equity - initial_equity) / initial_equity if initial_equity != 0 else 0.0

        equity_series = df['equity'].values
        peak = np.maximum.accumulate(equity_series)
        drawdown = (peak - equity_series) / peak
        max_drawdown = drawdown.max() if len(drawdown) > 0 else 0.0

        recovery_factor = absolute_return / max_drawdown if max_drawdown != 0 else float('inf') if absolute_return > 0 else 0.0

        return {
            'recovery_factor': recovery_factor,
            'absolute_return': absolute_return,
            'max_drawdown': max_drawdown
        }
    except Exception as e:
        logging.error(f"Failed to compute recovery factor: {e}")
        return {
            'recovery_factor': 0.0,
            'absolute_return': 0.0,
            'max_drawdown': 0.0
        }
    
def generate_hourly_performance(start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> Tuple[Optional[str], str]:
    """
    Generate a bar chart of profit/loss by hour of the day.

    Args:
        start_date: Start date for the data range.
        end_date: End date for the data range.

    Returns:
        Tuple of (chart_path, title). Returns (None, message) if trade log is empty.
    """
    try:
        query: str = "SELECT timestamp, profit_loss FROM trades WHERE trade_type = 'CLOSE_BUY'"
        params: Dict[str, Any] = {}
        if start_date and end_date:
            query += " AND timestamp BETWEEN :start_date AND :end_date"
            params = {"start_date": start_date, "end_date": end_date}
        df: pd.DataFrame = pd.read_sql_query(query, engine, params=params)

        if df.empty or 'profit_loss' not in df.columns or 'timestamp' not in df.columns:
            logging.info("No closed trades available to plot hourly performance.")
            return None, "No closed trades available to plot hourly performance."

        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df['hour'] = df['timestamp'].dt.hour
        hourly_pl = df.groupby('hour')['profit_loss'].sum()

        plt.figure(figsize=(10, 5))
        hourly_pl.plot(kind='bar', color='teal')
        plt.title("Profit/Loss by Hour of Day", fontweight='bold')
        plt.xlabel("Hour of Day (UTC)")
        plt.ylabel("Profit/Loss (£)")
        plt.grid(True)

        chart_path: str = os.path.join(PLOT_PATH, "hourly_performance.png")
        plt.savefig(chart_path)
        plt.close()
        return chart_path, "Hourly Performance"
    except Exception as e:
        logging.error(f"Failed to generate hourly performance chart: {e}")
        raise

def generate_day_of_week_performance(start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> Tuple[Optional[str], str]:
    """
    Generate a bar chart of profit/loss by day of the week.

    Args:
        start_date: Start date for the data range.
        end_date: End date for the data range.

    Returns:
        Tuple of (chart_path, title). Returns (None, message) if trade log is empty.
    """
    try:
        query: str = "SELECT timestamp, profit_loss FROM trades WHERE trade_type = 'CLOSE_BUY'"
        params: Dict[str, Any] = {}
        if start_date and end_date:
            query += " AND timestamp BETWEEN :start_date AND :end_date"
            params = {"start_date": start_date, "end_date": end_date}
        df: pd.DataFrame = pd.read_sql_query(query, engine, params=params)

        if df.empty or 'profit_loss' not in df.columns or 'timestamp' not in df.columns:
            logging.info("No closed trades available to plot day-of-week performance.")
            return None, "No closed trades available to plot day-of-week performance."

        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df['day'] = df['timestamp'].dt.day_name()
        day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        day_pl = df.groupby('day')['profit_loss'].sum().reindex(day_order)

        plt.figure(figsize=(10, 5))
        day_pl.plot(kind='bar', color='coral')
        plt.title("Profit/Loss by Day of Week", fontweight='bold')
        plt.xlabel("Day of Week")
        plt.ylabel("Profit/Loss (£)")
        plt.grid(True)

        chart_path: str = os.path.join(PLOT_PATH, "day_of_week_performance.png")
        plt.savefig(chart_path)
        plt.close()
        return chart_path, "Day-of-Week Performance"
    except Exception as e:
        logging.error(f"Failed to generate day-of-week performance chart: {e}")
        raise

def compute_win_loss_streaks(start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> Dict[str, int]:
    """
    Compute the longest winning and losing streaks.

    Args:
        start_date: Start date for the data range.
        end_date: End date for the data range.

    Returns:
        Dictionary containing longest win streak and longest loss streak.
    """
    try:
        query: str = "SELECT timestamp, profit_loss FROM trades WHERE trade_type = 'CLOSE_BUY'"
        params: Dict[str, Any] = {}
        if start_date and end_date:
            query += " AND timestamp BETWEEN :start_date AND :end_date"
            params = {"start_date": start_date, "end_date": end_date}
        df: pd.DataFrame = pd.read_sql_query(query, engine, params=params)

        if df.empty or 'profit_loss' not in df.columns:
            return {
                'longest_win_streak': 0,
                'longest_loss_streak': 0
            }

        df = df.sort_values('timestamp')
        outcomes = (df['profit_loss'] > 0).astype(int)  # 1 for win, 0 for loss

        current_streak = 1
        max_win_streak = 0
        max_loss_streak = 0
        current_type = outcomes.iloc[0] if len(outcomes) > 0 else None

        for i in range(1, len(outcomes)):
            if outcomes.iloc[i] == current_type:
                current_streak += 1
            else:
                if current_type == 1:
                    max_win_streak = max(max_win_streak, current_streak)
                else:
                    max_loss_streak = max(max_loss_streak, current_streak)
                current_type = outcomes.iloc[i]
                current_streak = 1

        # Handle the last streak
        if current_type == 1:
            max_win_streak = max(max_win_streak, current_streak)
        else:
            max_loss_streak = max(max_loss_streak, current_streak)

        return {
            'longest_win_streak': max_win_streak,
            'longest_loss_streak': max_loss_streak
        }
    except Exception as e:
        logging.error(f"Failed to compute win/loss streaks: {e}")
        return {
            'longest_win_streak': 0,
            'longest_loss_streak': 0
        }
    
def generate_trade_clustering(start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> Tuple[Optional[str], str]:
    """
    Generate a histogram of trade frequency by day to detect clustering.

    Args:
        start_date: Start date for the data range.
        end_date: End date for the data range.

    Returns:
        Tuple of (chart_path, title). Returns (None, message) if trade log is empty.
    """
    try:
        query: str = "SELECT timestamp FROM trades WHERE trade_type IN ('BUY', 'CLOSE_BUY')"
        params: Dict[str, Any] = {}
        if start_date and end_date:
            query += " AND timestamp BETWEEN :start_date AND :end_date"
            params = {"start_date": start_date, "end_date": end_date}
        df: pd.DataFrame = pd.read_sql_query(query, engine, params=params)

        if df.empty or 'timestamp' not in df.columns:
            logging.info("No trades available to plot trade clustering.")
            return None, "No trades available to plot trade clustering."

        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df['date'] = df['timestamp'].dt.date
        trade_counts = df.groupby('date').size()

        plt.figure(figsize=(10, 5))
        trade_counts.plot(kind='hist', bins=30, edgecolor='black', color='indigo')
        plt.title("Trade Clustering (Trades per Day)", fontweight='bold')
        plt.xlabel("Date")
        plt.ylabel("Number of Trades")
        plt.grid(True)

        chart_path: str = os.path.join(PLOT_PATH, "trade_clustering.png")
        plt.savefig(chart_path)
        plt.close()
        return chart_path, "Trade Clustering"
    except Exception as e:
        logging.error(f"Failed to generate trade clustering chart: {e}")
        raise

def compute_transaction_costs(start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> Dict[str, float]:
    """
    Compute the total cost of spreads and commissions.

    Args:
        start_date: Start date for the data range.
        end_date: End date for the data range.

    Returns:
        Dictionary containing total transaction costs, spread costs, and commission costs.
    """
    try:
        query: str = "SELECT timestamp, position_size FROM trades WHERE trade_type IN ('BUY', 'CLOSE_BUY')"
        params: Dict[str, Any] = {}
        if start_date and end_date:
            query += " AND timestamp BETWEEN :start_date AND :end_date"
            params = {"start_date": start_date, "end_date": end_date}
        df: pd.DataFrame = pd.read_sql_query(query, engine, params=params)

        if df.empty or 'position_size' not in df.columns:
            return {
                'total_costs': 0.0,
                'spread_costs': 0.0,
                'commission_costs': 0.0
            }

        # Estimate spread and commission (adjust these values based on your broker's rates)
        spread_per_lot = 0.5  # Example: $0.5 per lot per trade (GOLD spread)
        commission_per_lot = 0.3  # Example: $0.3 per lot per trade (round-trip)

        total_trades = len(df)
        total_lots = df['position_size'].sum()
        spread_costs = total_trades * spread_per_lot * EXCHANGE_RATE
        commission_costs = total_lots * commission_per_lot * EXCHANGE_RATE
        total_costs = spread_costs + commission_costs

        return {
            'total_costs': total_costs,
            'spread_costs': spread_costs,
            'commission_costs': commission_costs
        }
    except Exception as e:
        logging.error(f"Failed to compute transaction costs: {e}")
        return {
            'total_costs': 0.0,
            'spread_costs': 0.0,
            'commission_costs': 0.0
        }
    
def generate_monte_carlo_simulation(num_simulations: int = 1000, forecast_days: int = 252) -> Tuple[Optional[str], str]:
    """
    Generate Monte Carlo simulations for future returns and drawdowns.

    Args:
        num_simulations: Number of Monte Carlo simulations to run.
        forecast_days: Number of days to forecast.

    Returns:
        Tuple of (chart_path, title). Returns (None, message) if trade log is empty.
    """
    try:
        df: pd.DataFrame = pd.read_sql_query("SELECT timestamp, equity FROM trades", engine)

        if df.empty or 'equity' not in df.columns or 'timestamp' not in df.columns:
            logging.info("No trades available for Monte Carlo simulation.")
            return None, "No trades available for Monte Carlo simulation."

        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values('timestamp')
        daily_equity = df.set_index('timestamp')['equity'].resample('D').last().ffill()
        daily_returns = daily_equity.pct_change().dropna()

        if len(daily_returns) < 2:
            logging.info("Insufficient return data for Monte Carlo simulation.")
            return None, "Insufficient data for Monte Carlo simulation."

        mean_return = daily_returns.mean()
        std_return = daily_returns.std()
        last_equity = daily_equity.iloc[-1]

        simulations = []
        for _ in range(num_simulations):
            sim_equity = [last_equity]
            for _ in range(forecast_days):
                daily_return = np.random.normal(mean_return, std_return)
                new_equity = sim_equity[-1] * (1 + daily_return)
                sim_equity.append(new_equity)
            simulations.append(sim_equity)

        simulations = np.array(simulations)
        median_sim = np.median(simulations, axis=0)
        lower_bound = np.percentile(simulations, 5, axis=0)
        upper_bound = np.percentile(simulations, 95, axis=0)

        dates = pd.date_range(start=df['timestamp'].iloc[-1], periods=forecast_days + 1, freq='D')
        plt.figure(figsize=(10, 5))
        plt.plot(dates, median_sim, label='Median Equity', color='blue')
        plt.fill_between(dates, lower_bound, upper_bound, color='blue', alpha=0.2, label='5th-95th Percentile')
        plt.title("Monte Carlo Simulation of Future Equity", fontweight='bold')
        plt.xlabel("Date")
        plt.ylabel("Equity (£)")
        plt.legend()
        plt.grid(True)

        chart_path: str = os.path.join(PLOT_PATH, "monte_carlo_simulation.png")
        plt.savefig(chart_path)
        plt.close()
        return chart_path, "Monte Carlo Simulation"
    except Exception as e:
        logging.error(f"Failed to generate Monte Carlo simulation: {e}")
        raise

def compute_overtrading_metrics(start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> Dict[str, float]:
    """
    Compute trade frequency metrics to detect potential overtrading.

    Args:
        start_date: Start date for the data range.
        end_date: End date for the data range.

    Returns:
        Dictionary containing average trades per day and per week.
    """
    try:
        query: str = "SELECT timestamp FROM trades WHERE trade_type IN ('BUY', 'CLOSE_BUY')"
        params: Dict[str, Any] = {}
        if start_date and end_date:
            query += " AND timestamp BETWEEN :start_date AND :end_date"
            params = {"start_date": start_date, "end_date": end_date}
        df: pd.DataFrame = pd.read_sql_query(query, engine, params=params)

        if df.empty or 'timestamp' not in df.columns:
            return {
                'trades_per_day': 0.0,
                'trades_per_week': 0.0
            }

        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df['date'] = df['timestamp'].dt.date
        daily_counts = df.groupby('date').size()
        avg_trades_per_day = daily_counts.mean() if len(daily_counts) > 0 else 0.0

        df['week'] = df['timestamp'].dt.to_period('W')
        weekly_counts = df.groupby('week').size()
        avg_trades_per_week = weekly_counts.mean() if len(weekly_counts) > 0 else 0.0

        return {
            'trades_per_day': avg_trades_per_day,
            'trades_per_week': avg_trades_per_week
        }
    except Exception as e:
        logging.error(f"Failed to compute overtrading metrics: {e}")
        return {
            'trades_per_day': 0.0,
            'trades_per_week': 0.0
        }
    
def generate_holding_time_vs_profitability(start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> Tuple[Optional[str], str]:
    """
    Generate a scatter plot of holding time vs. profitability.

    Args:
        start_date: Start date for the data range.
        end_date: End date for the data range.

    Returns:
        Tuple of (chart_path, title). Returns (None, message) if trade log is empty.
    """
    try:
        query: str = "SELECT timestamp, trade_type, symbol, profit_loss FROM trades WHERE trade_type IN ('BUY', 'CLOSE_BUY')"
        params: Dict[str, Any] = {}
        if start_date and end_date:
            query += " AND timestamp BETWEEN :start_date AND :end_date"
            params = {"start_date": start_date, "end_date": end_date}
        df: pd.DataFrame = pd.read_sql_query(query, engine, params=params)

        if df.empty or 'timestamp' not in df.columns or 'trade_type' not in df.columns:
            logging.info("No trades available to plot holding time vs. profitability.")
            return None, "No trades available to plot holding time vs. profitability."

        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values('timestamp')

        durations = []
        profits = []
        buy_trades = df[df['trade_type'] == 'BUY']
        close_trades = df[df['trade_type'] == 'CLOSE_BUY']

        for _, close in close_trades.iterrows():
            close_time = close['timestamp']
            symbol = close['symbol']
            profit = close['profit_loss']
            matching_buy = buy_trades[(buy_trades['symbol'] == symbol) & (buy_trades['timestamp'] < close_time)]
            if not matching_buy.empty:
                buy_time = matching_buy.iloc[-1]['timestamp']
                duration_hours = (close_time - buy_time).total_seconds() / 3600  # Convert to hours
                durations.append(duration_hours)
                profits.append(profit)

        if not durations:
            logging.info("No matching BUY and CLOSE_BUY trades found for analysis.")
            return None, "No matching trades found to plot holding time vs. profitability."

        plt.figure(figsize=(10, 5))
        plt.scatter(durations, profits, alpha=0.5, color='magenta')
        plt.title("Holding Time vs. Profitability", fontweight='bold')
        plt.xlabel("Holding Time (Hours)")
        plt.ylabel("Profit/Loss (£)")
        plt.grid(True)

        chart_path: str = os.path.join(PLOT_PATH, "holding_time_vs_profitability.png")
        plt.savefig(chart_path)
        plt.close()
        return chart_path, "Holding Time vs. Profitability"
    except Exception as e:
        logging.error(f"Failed to generate holding time vs. profitability chart: {e}")
        raise

def generate_monthly_performance_chart(start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> Tuple[Optional[str], str]:
    """
    Generate a bar chart of monthly profit/loss from closed trades.

    Args:
        start_date: Start date for the data range.
        end_date: End date for the data range.

    Returns:
        Tuple of (chart_path, title). Returns (None, message) if trade log is empty.
    """
    try:
        query: str = "SELECT timestamp, profit_loss FROM trades WHERE trade_type = 'CLOSE_BUY'"
        params: Dict[str, Any] = {}
        if start_date and end_date:
            query += " AND timestamp BETWEEN :start_date AND :end_date"
            params = {"start_date": start_date, "end_date": end_date}
        df: pd.DataFrame = pd.read_sql_query(query, engine, params=params)

        if df.empty or 'profit_loss' not in df.columns or 'timestamp' not in df.columns:
            logging.info("No closed trades available to plot monthly performance chart.")
            return None, "No closed trades available to plot monthly performance chart."

        # Aggregate profit/loss by month
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df['month'] = df['timestamp'].dt.to_period('M')
        monthly_pl = df.groupby('month')['profit_loss'].sum()

        plt.figure(figsize=(10, 5))
        monthly_pl.plot(kind='bar', color='teal')
        plt.title("Monthly Profit/Loss", fontweight='bold')
        plt.xlabel("Month")
        plt.ylabel("Profit/Loss (£)")
        plt.grid(True)

        if start_date and end_date:
            plt.title(f"Monthly Profit/Loss\n{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}", fontweight='bold')

        chart_path: str = os.path.join(PLOT_PATH, "monthly_performance.png")
        plt.savefig(chart_path)
        plt.close()
        return chart_path, "Monthly Profit/Loss"
    except Exception as e:
        logging.error(f"Failed to generate monthly performance chart: {e}")
        raise

def log_trade(
    timestamp: datetime,
    trade_type: str,
    symbol: str,
    price: float,
    position_size: float,
    unit_label: str,
    profit_loss: float,
    equity: float,
    reasoning: str,
    features: Dict[str, float]
) -> None:
    """
    Log a trade to the SQLite database.

    Args:
        timestamp: Timestamp of the trade.
        trade_type: Type of trade ("BUY", "CLOSE_BUY", "HOLD").
        symbol: Trading symbol.
        price: Price at which the trade was executed.
        position_size: Size of the position.
        unit_label: Unit of the position size (e.g., "lots").
        profit_loss: Profit or loss from the trade in GBP.
        equity: Current equity in GBP.
        reasoning: Reasoning for the trade decision.
        features: Features used for the prediction.
    """
    try:
        with engine.connect() as conn:
            conn.execute(
                text("""
                    INSERT INTO trades (
                        timestamp, trade_type, symbol, price, position_size, unit_label,
                        profit_loss, equity, reasoning, features
                    ) VALUES (
                        :timestamp, :trade_type, :symbol, :price, :position_size, :unit_label,
                        :profit_loss, :equity, :reasoning, :features
                    )
                """),
                {
                    "timestamp": timestamp,
                    "trade_type": trade_type,
                    "symbol": symbol,
                    "price": price,
                    "position_size": position_size,
                    "unit_label": unit_label,
                    "profit_loss": profit_loss,
                    "equity": equity,
                    "reasoning": reasoning,
                    "features": json.dumps(features)
                }
            )
            conn.commit()  # Explicitly commit the transaction
        logging.info(f"Logged trade: {trade_type} {symbol} at ${price:.2f}")
    except Exception as e:
        logging.error(f"Failed to log trade: {e}")
        notify(f"Error logging trade: {e}")

def log_prediction(timestamp: datetime, symbol: str, action_label: str, features: Dict[str, float]) -> None:
    """
    Log a prediction to the SQLite database.

    Args:
        timestamp: Timestamp of the prediction.
        symbol: Trading symbol.
        action_label: Predicted action ("BUY", "CLOSE_BUY", "HOLD").
        features: Features used for the prediction.
    """
    try:
        with engine.connect() as conn:
            conn.execute(
                text("""
                    INSERT INTO predictions (timestamp, symbol, action_label, features)
                    VALUES (:timestamp, :symbol, :action_label, :features)
                """),
                {
                    "timestamp": timestamp,
                    "symbol": symbol,
                    "action_label": action_label,
                    "features": json.dumps(features)
                }
            )
            conn.commit()  # Explicitly commit the transaction
        logging.info(f"Logged prediction: {action_label} for {symbol}")
    except Exception as e:
        logging.error(f"Failed to log prediction: {e}")
        notify(f"Error logging prediction: {e}")



def handle_telegram_updates(model: PPO, scaler: MinMaxScaler) -> None:
    """
    Handle incoming Telegram updates in a separate thread.

    Args:
        model: Loaded PPO model.
        scaler: Loaded MinMaxScaler.
    """
    global scheduled_reports, position_monitoring_enabled, stop_flag, heartbeat_interval
    global last_position_update, last_report_time, trading_paused, user_position_size
    global telegram_failure_count
    global live_position_logging
    offset: int = 0
    TELEGRAM_POLL_TIMEOUT: int = 30
    RETRIES: int = 3

    # Track pagination state and filters per chat
    decision_log_offset: Dict[str, int] = {}
    trade_log_offset: Dict[str, int] = {}
    trade_log_filters: Dict[str, Dict[str, Any]] = {}

    while not stop_flag:
        try:
            url: str = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
            params: Dict[str, Any] = {"offset": offset, "timeout": TELEGRAM_POLL_TIMEOUT}
            for attempt in range(RETRIES):
                try:
                    response = requests.get(url, params=params, timeout=(15, 45))
                    response.raise_for_status()
                    updates = response.json().get("result", [])
                    telegram_failure_count = 0
                    break
                except requests.exceptions.RequestException as e:
                    telegram_failure_count += 1
                    logging.error(f"Attempt {attempt+1}/{RETRIES} - Failed to fetch Telegram updates: {e}")
                    if attempt == RETRIES - 1:
                        notify(
                            f"❗ *Error:* Failed to fetch updates after {RETRIES} attempts: {str(e)}",
                            parse_mode="MarkdownV2"
                        )
                    time.sleep(2 ** attempt)
                except Exception as e:
                    telegram_failure_count += 1
                    logging.error(f"Attempt {attempt+1}/{RETRIES} - Unexpected error fetching Telegram updates: {e}")
                    if attempt == RETRIES - 1:
                        notify(
                            f"❗ *Unexpected Error:* Unable to fetch updates: {str(e)}",
                            parse_mode="MarkdownV2"
                        )
                    time.sleep(2 ** attempt)

            for update in updates:
                offset = update["update_id"] + 1
                chat_id: str = ""
                text: str = ""
                callback_data: str = ""

                if "message" in update and "text" in update["message"]:
                    chat_id = str(update["message"]["chat"]["id"])
                    text = update["message"]["text"]
                elif "callback_query" in update:
                    chat_id = str(update["callback_query"]["from"]["id"])
                    callback_data = update["callback_query"]["data"]
                    text = callback_data

                if not chat_id or chat_id != TELEGRAM_USER_ID:
                    logging.debug(f"Ignoring update from unauthorized chat_id: {chat_id}")
                    continue

                if chat_id not in decision_log_offset:
                    decision_log_offset[chat_id] = 0
                if chat_id not in trade_log_offset:
                    trade_log_offset[chat_id] = 0
                if chat_id not in trade_log_filters:
                    trade_log_filters[chat_id] = {"trade_type": None, "start_date": None, "end_date": None}

                # Handle commands
                if text.startswith("/start"):
                    send_inline_keyboard(chat_id)
                    notify(
                        "✅ *Bot Started!* Use the inline keyboard or commands to interact. 📲",
                        chat_id,
                        parse_mode="MarkdownV2"
                    )
                elif text.startswith("/dailypl"):
                    try:
                        parts = text.split()
                        start_date = None
                        end_date = None
                        if len(parts) > 1:
                            start_date, end_date = parse_date_range(" ".join(parts[1:]))
                        chart_path, title = generate_daily_pl_histogram(start_date, end_date)
                        if chart_path:
                            send_photo(chart_path, caption=f"{title}", chat_id=chat_id)
                        else:
                            notify(
                                f"📊 *{title}*",
                                chat_id,
                                parse_mode="MarkdownV2"
                            )
                    except Exception as e:
                        notify(
                            f"❗ *Error Generating Daily P/L Histogram:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )                    
                elif text.startswith("/alert"):
                    parts: List[str] = text.split()
                    if len(parts) >= 3:
                        try:
                            price: float = float(parts[1])
                            condition: str = parts[2].lower()
                            recurring: bool = len(parts) > 3 and parts[3].lower() == "recurring"
                            if condition in ["above", "below"]:
                                price_alerts.append((price, condition, recurring, chat_id))
                                notify(
                                    f"🔔 *Price Alert Set:* {condition.capitalize()} $ {price:.2f} {(recurring)} if recurring else ''",
                                    chat_id,
                                    parse_mode="MarkdownV2"
                                )
                            else:
                                notify(
                                    "❌ *Invalid Condition:* Use above or below. Example: /alert 2500 above",
                                    chat_id,
                                    parse_mode="MarkdownV2"
                                )
                        except ValueError:
                            notify(
                                "❌ *Invalid Price:* Use a number. Example: /alert 2500 above",
                                chat_id,
                                parse_mode="MarkdownV2"
                            )
                    else:
                        notify(
                            "ℹ️ *Usage:* /alert <price> [above|below] [recurring]",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif text.startswith("/log"):
                    parts: List[str] = text.split()
                    trade_type: Optional[str] = "CLOSE_BUY"
                    date_range: Optional[str] = " ".join(parts[1:]).lower() if len(parts) > 1 else "all"
                    start_date, end_date = None, None
                    current_date = datetime.now()
                    if date_range == "week":
                        start_date = current_date - timedelta(days=7)
                    elif date_range == "month":
                        start_date = current_date - timedelta(days=30)
                    elif date_range == "3months":
                        start_date = current_date - timedelta(days=90)
                    elif date_range == "6months":
                        start_date = current_date - timedelta(days=180)
                    elif date_range == "9months":
                        start_date = current_date - timedelta(days=270)
                    elif date_range == "12months":
                        start_date = current_date - timedelta(days=365)
                    elif date_range == "most_recent":
                        query = "SELECT id, timestamp FROM trades WHERE trade_type = 'CLOSE_BUY' ORDER BY timestamp DESC LIMIT 1"
                        with engine.connect() as conn:
                            result = conn.execute(text(query)).fetchone()
                        if result:
                            start_date = pd.to_datetime(result[1])
                            end_date = start_date + timedelta(seconds=1)
                        else:
                            start_date = None
                    elif date_range == "all":
                        start_date, end_date = None, None
                    else:
                        try:
                            start_date, end_date = parse_date_range(date_range)
                        except ValueError as e:
                            notify(
                                f"❌ *Invalid Date Range:* {str(e)}. Example: week or 2023-01-01 to 2023-12-31",
                                chat_id,
                                parse_mode="MarkdownV2"
                            )
                            continue

                    trade_log_filters[chat_id] = {"trade_type": trade_type, "start_date": start_date, "end_date": end_date}
                    trade_log_offset[chat_id] = 0

                    try:
                        trade_log_text, reply_markup, current_offset, total = get_trade_log(
                            trade_type, start_date, end_date, offset=trade_log_offset[chat_id]
                        )
                        trade_log_offset[chat_id] = current_offset
                        notify(trade_log_text, chat_id, reply_markup, parse_mode="MarkdownV2")
                    except Exception as e:
                        notify(
                            f"❗ *Error Retrieving Trade Log:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif text.startswith("/report"):
                    date_range: str = " ".join(text.split()[1:]) if len(text.split()) > 1 else ""
                    try:
                        start_date, end_date = parse_date_range(date_range) if date_range else (None, None)
                        analytics = compute_analytics(start_date, end_date)
                        period_text: str = "All Time" if not date_range else date_range
                        report_text: str = (
                            f"📊 *Analytics Report* ({period_text})\n"
                            f"---\n"
                            f"🔢 *Total Trades:* {analytics['total_trades']}\n"
                            f"🏆 *Win Rate:* {analytics['win_rate']:.2%}\n"
                            f"💷 *Total P/L:* £{analytics['total_pl']:.2f}\n"
                            f"📉 *Max Drawdown:* {analytics['max_drawdown']:.2%}\n"
                            f"📈 *Sharpe Ratio:* {analytics['sharpe_ratio']:.2f}"
                        )
                        notify(report_text, chat_id, parse_mode="MarkdownV2")
                    except ValueError as e:
                        notify(
                            f"❌ *Invalid Date Range:* {str(e)}. Example: week or 2023-01-01 to 2023-12-31",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                    except Exception as e:
                        notify(
                            f"❗ *Error Generating Report:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif text.startswith("/equity"):
                    date_range: str = " ".join(text.split()[1:]) if len(text.split()) > 1 else ""
                    try:
                        start_date, end_date = parse_date_range(date_range) if date_range else (None, None)
                        chart_path, title = generate_equity_curve(start_date, end_date)
                        if chart_path:
                            send_photo(chart_path, caption=f"{SYMBOL} Equity Curve", chat_id=chat_id)
                        else:
                            notify(
                                f"📉 *Equity Curve:* {title}",
                                chat_id,
                                parse_mode="MarkdownV2"
                            )
                    except ValueError as e:
                        notify(
                            f"❌ *Invalid Date Range:* {str(e)}. Example: week or 2023-01-01 to 2023-12-31",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                    except Exception as e:
                        notify(
                            f"❗ *Error Generating Equity Curve:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif text.startswith("/drawdown"):
                    date_range: str = " ".join(text.split()[1:]) if len(text.split()) > 1 else ""
                    try:
                        start_date, end_date = parse_date_range(date_range) if date_range else (None, None)
                        chart_path, max_drawdown, title = generate_drawdown_curve(start_date, end_date)
                        if chart_path:
                            send_photo(
                                chart_path,
                                caption=f"{SYMBOL} Drawdown Curve\nMax Drawdown: {max_drawdown:.2%}",
                                chat_id=chat_id
                            )
                        else:
                            notify(
                                f"📉 *Drawdown Curve:* {title}",
                                chat_id,
                                parse_mode="MarkdownV2"
                            )
                    except ValueError as e:
                        notify(
                            f"❌ *Invalid Date Range:* {str(e)}. Example: week or 2023-01-01 to 2023-12-31",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                    except Exception as e:
                        notify(
                            f"❗ *Error Generating Drawdown Curve:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif text.startswith("/dashboard"):
                    date_range: str = " ".join(text.split()[1:]) if len(text.split()) > 1 else ""
                    try:
                        start_date, end_date = parse_date_range(date_range) if date_range else (None, None)
                        dashboard_text, equity_chart, drawdown_chart = generate_dashboard(start_date, end_date)
                        notify(
                            f"📋 *Dashboard*\n---\n{dashboard_text}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                        if equity_chart:
                            send_photo(equity_chart, caption="Equity Curve", chat_id=chat_id)
                        if drawdown_chart:
                            send_photo(drawdown_chart, caption="Drawdown Curve", chat_id=chat_id)
                    except ValueError as e:
                        notify(
                            f"❌ *Invalid Date Range:* {str(e)}. Example: week or 2023-01-01 to 2023-12-31",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                    except Exception as e:
                        notify(
                            f"❗ *Error Generating Dashboard:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif text.startswith("/heartbeat"):
                    try:
                        hours: float = float(text.split()[1]) if len(text.split()) > 1 else 0.0
                        if hours < 0:
                            notify(
                                "❌ *Invalid Heartbeat Interval:* Must be non-negative.",
                                chat_id,
                                parse_mode="MarkdownV2"
                            )
                        else:
                            heartbeat_interval = hours * 3600 if hours > 0 else None
                            status: str = "disabled" if hours == 0 else f"set to {hours} hours"
                            notify(
                                f"💓 *Heartbeat:* {status}.",
                                chat_id,
                                parse_mode="MarkdownV2"
                            )
                    except ValueError:
                        notify(
                            "❌ *Invalid Heartbeat Interval:* Use a number. Example: /heartbeat 2",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif text.startswith("/compare"):
                    parts: List[str] = text.split()
                    if len(parts) >= 3:
                        period1: str = parts[1]
                        period2: str = " ".join(parts[2:])
                        try:
                            comparison_text = compare_periods(period1, period2)
                            notify(
                                f"📊 *Period Comparison*\n---\n{comparison_text}",
                                chat_id,
                                parse_mode="MarkdownV2"
                            )
                        except Exception as e:
                            notify(
                                f"❗ *Error Comparing Periods:* {str(e)}",
                                chat_id,
                                parse_mode="MarkdownV2"
                            )
                    else:
                        notify(
                            "ℹ️ *Usage:* /compare period1 period2",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data == "dashboard_mini_app":
                        launch_mini_app(chat_id)
                elif text.startswith("/exportcsv"):
                    date_range: str = " ".join(text.split()[1:]) if len(text.split()) > 1 else ""
                    try:
                        start_date, end_date = parse_date_range(date_range) if date_range else (None, None)
                        export_path = export_trade_history(start_date, end_date)
                        notify(
                            f"📄 *Trade History Exported:* {export_path}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                    except ValueError as e:
                        notify(
                            f"❌ *Invalid Date Range:* {str(e)}. Example: week or 2023-01-01 to 2023-12-31",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                    except Exception as e:
                        notify(
                            f"❗ *Error Exporting Trade History:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif text.startswith("/decisionlog"):
                    symbol: str = text.split()[1] if len(text.split()) > 1 else SYMBOL
                    decision_log_offset[chat_id] = 0
                    try:
                        decision_log_text, reply_markup, current_offset, total = get_decision_log(symbol, offset=decision_log_offset[chat_id])
                        decision_log_offset[chat_id] = current_offset
                        notify(decision_log_text, chat_id, reply_markup, parse_mode="MarkdownV2")
                    except Exception as e:
                        notify(
                            f"❗ *Error Retrieving Decision Log:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif text.startswith("/setpositionsize"):
                    parts: List[str] = text.split()
                    if len(parts) == 2:
                        try:
                            size: float = float(parts[1])
                            if size <= 0:
                                notify(
                                    "❌ *Invalid Position Size:* Must be positive.",
                                    chat_id,
                                    parse_mode="MarkdownV2"
                                )
                            elif size < MIN_POSITION_SIZE:
                                notify(
                                    f"❌ *Invalid Position Size:* Must be at least {MIN_POSITION_SIZE}.",
                                    chat_id,
                                    parse_mode="MarkdownV2"
                                )
                            else:
                                user_position_size = size
                                notify(
                                    f"✅ *Position Size Set:* {size} lots for BUY trades.",
                                    chat_id,
                                    parse_mode="MarkdownV2"
                                )
                                logging.info(f"User set position size to {size} lots")
                        except ValueError:
                            notify(
                                "❌ *Invalid Position Size:* Use a number. Example: /setpositionsize 0.5",
                                chat_id,
                                parse_mode="MarkdownV2"
                            )
                    else:
                        notify(
                            "ℹ️ *Usage:* /setpositionsize <size>",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif text.startswith("/monthlypl"):
                    try:
                        parts = text.split()
                        start_date = None
                        end_date = None
                        if len(parts) > 1:
                            start_date, end_date = parse_date_range(" ".join(parts[1:]))
                        chart_path, title = generate_monthly_performance_chart(start_date, end_date)
                        if chart_path:
                            send_photo(chart_path, caption=f"{title}", chat_id=chat_id)
                        else:
                            notify(
                                f"📊 *{title}*",
                                chat_id,
                                parse_mode="MarkdownV2"
                            )
                    except Exception as e:
                        notify(
                            f"❗ *Error Generating Monthly Performance Chart:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )        
                elif text.startswith("/togglenotify"):
                    parts: List[str] = text.split()
                    if len(parts) == 2:
                        notify_type: str = parts[1].upper()
                        if notify_type in notification_settings:
                            notification_settings[notify_type] = not notification_settings[notify_type]
                            status: str = "enabled" if notification_settings[notify_type] else "disabled"
                            notify(
                                f"🔔 *{notify_type} Notifications:* {status}.",
                                chat_id,
                                parse_mode="MarkdownV2"
                            )
                        else:
                            notify(
                                "❌ *Invalid Notification Type:* Use BUY, CLOSE_BUY, or HOLD.",
                                chat_id,
                                parse_mode="MarkdownV2"
                            )
                    else:
                        notify(
                            "ℹ️ *Usage:* /togglenotify <type>",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif text.startswith("/tradeduration"):
                    try:
                        parts = text.split()
                        start_date = None
                        end_date = None
                        if len(parts) > 1:
                            start_date, end_date = parse_date_range(" ".join(parts[1:]))
                        chart_path, title = generate_trade_duration_distribution(start_date, end_date)
                        if chart_path:
                            send_photo(chart_path, caption=f"{title}", chat_id=chat_id)
                        else:
                            notify(
                                f"📊 *{title}*",
                                chat_id,
                                parse_mode="MarkdownV2"
                            )
                    except Exception as e:
                        notify(
                            f"❗ *Error Generating Trade Duration Distribution:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif text.startswith("/sharpetrend"):
                    try:
                        chart_path, title = generate_sharpe_ratio_trend()
                        if chart_path:
                            send_photo(chart_path, caption=f"{title}", chat_id=chat_id)
                        else:
                            notify(
                                f"📊 *{title}*",
                                chat_id,
                                parse_mode="MarkdownV2"
                            )
                    except Exception as e:
                        notify(
                            f"❗ *Error Generating Sharpe Ratio Trend:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif text.startswith("/help"):
                    try:
                        help_sections = get_help_message()
                        notify(
                            help_sections,
                            chat_id,
                            parse_mode="HTML"  # Updated to match HTML tags in help message
                        )
                    except Exception as e:
                        notify(
                            f"❗ *Error Retrieving Help:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data == "status":
                    with mt5_lock:
                        account_info = mt5.account_info()
                        positions = mt5.positions_get(symbol=SYMBOL)
                    equity: float = account_info.equity * EXCHANGE_RATE if account_info else 0.0
                    position_text: str = "No open positions." if not positions else (
                        f"Position: {'BUY' if positions[0].type == mt5.ORDER_TYPE_BUY else 'SELL'} {positions[0].volume} lots at $ {positions[0].price_open:.2f}"
                    )
                    status_text: str = (
                        f"🤖 *Bot Status*\n"
                        f"---\n"
                        f"💷 *Equity:* £{equity:.2f}\n"
                        f"📈 *{position_text}*\n"
                        f"⚙️ *Trading:* {'Paused' if trading_paused else 'Active'}\n"
                        f"📅 *Scheduled Reports:* {'On' if scheduled_reports else 'Off'}\n"
                        f"👀 *Position Monitoring:* {'On' if position_monitoring_enabled else 'Off'}"
                    )
                    notify(status_text, chat_id, parse_mode="MarkdownV2")
                elif callback_data == "price":
                    tick = mt5.symbol_info_tick(SYMBOL)
                    if tick:
                        notify(
                            f"📈 *Current {SYMBOL} Price:* ${tick.bid:.2f} / ${tick.ask:.2f}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                    else:
                        notify(
                            "❗ *Error:* Unable to fetch current price.",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data == "chart":
                    try:
                        chart_path = generate_price_chart()
                        send_photo(chart_path, caption=f"{SYMBOL} Price Chart", chat_id=chat_id)
                    except Exception as e:
                        notify(
                            f"❗ *Error Generating Price Chart:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data == "dailypl":
                    try:
                        chart_path, title = generate_daily_pl_histogram()
                        if chart_path:
                            send_photo(chart_path, caption=f"{title}", chat_id=chat_id)
                        else:
                            notify(
                                f"📊 *{title}*",
                                chat_id,
                                parse_mode="MarkdownV2"
                            )
                    except Exception as e:
                        notify(
                            f"❗ *Error Generating Daily P/L Histogram:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data == "position":
                    with mt5_lock:
                        positions = mt5.positions_get(symbol=SYMBOL)
                    if positions:
                        pos = positions[0]
                        profit: float = pos.profit * EXCHANGE_RATE
                        pips: float = round((pos.price_current - pos.price_open) * 10, 1)  # 1 pip = 0.1 for GOLD
                        text = (
                            f"📈 *Open Position*\n"
                            f"---\n"
                            f"🔄 *Type:* {'BUY' if pos.type == mt5.ORDER_TYPE_BUY else 'SELL'}\n"
                            f"📏 *Size:* {pos.volume} lots\n"
                            f"💵 *Open Price:* ${pos.price_open:.2f}\n"
                            f"💵 *Current Price:* ${pos.price_current:.2f}\n"
                            f"💷 *Profit:* £{profit:.2f} | Pips: {pips:+.1f}"
                        )
                        notify(text, chat_id, parse_mode="MarkdownV2")
                    else:
                        notify(
                            "ℹ️ *No Open Positions.*",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data == "calmartrend":
                    try:
                        chart_path, title = generate_calmar_ratio_trend()
                        if chart_path:
                            send_photo(chart_path, caption=f"{title}", chat_id=chat_id)
                        else:
                            notify(
                                f"📊 *{title}*",
                                chat_id,
                                parse_mode="MarkdownV2"
                            )
                    except Exception as e:
                        notify(
                            f"❗ *Error Generating Calmar Ratio Trend:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data == "sortinotrend":
                    try:
                        chart_path, title = generate_sortino_ratio_trend()
                        if chart_path:
                            send_photo(chart_path, caption=f"{title}", chat_id=chat_id)
                        else:
                            notify(
                                f"📊 *{title}*",
                                chat_id,
                                parse_mode="MarkdownV2"
                            )
                    except Exception as e:
                        notify(
                            f"❗ *Error Generating Sortino Ratio Trend:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data == "help":
                    try:
                        help_sections = get_help_message()
                        notify(
                            help_sections,
                            chat_id,
                            parse_mode="HTML"  # Use HTML to match <b> tags in help message
                        )
                    except Exception as e:
                        notify(
                            f"❗ *Error Retrieving Help:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data == "montecarlo":
                    try:
                        chart_path, title = generate_monte_carlo_simulation()
                        if chart_path:
                            send_photo(chart_path, caption=f"{title}", chat_id=chat_id)
                        else:
                            notify(
                                f"📊 *{title}*",
                                chat_id,
                                parse_mode="MarkdownV2"
                            )
                    except Exception as e:
                        notify(
                            f"❗ *Error Generating Monte Carlo Simulation:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data == "hourlypl":
                    try:
                        chart_path, title = generate_hourly_performance()
                        if chart_path:
                            send_photo(chart_path, caption=f"{title}", chat_id=chat_id)
                        else:
                            notify(
                                f"📊 *{title}*",
                                chat_id,
                                parse_mode="MarkdownV2"
                            )
                    except Exception as e:
                        notify(
                            f"❗ *Error Generating Hourly Performance Chart:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data == "dayofweekpl":
                    try:
                        chart_path, title = generate_day_of_week_performance()
                        if chart_path:
                            send_photo(chart_path, caption=f"{title}", chat_id=chat_id)
                        else:
                            notify(
                                f"📊 *{title}*",
                                chat_id,
                                parse_mode="MarkdownV2"
                            )
                    except Exception as e:
                        notify(
                            f"❗ *Error Generating Day-of-Week Performance Chart:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data == "tradeclustering":
                    try:
                        chart_path, title = generate_trade_clustering()
                        if chart_path:
                            send_photo(chart_path, caption=f"{title}", chat_id=chat_id)
                        else:
                            notify(
                                f"📊 *{title}*",
                                chat_id,
                                parse_mode="MarkdownV2"
                            )
                    except Exception as e:
                        notify(
                            f"❗ *Error Generating Trade Clustering Chart:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data == "profitfactor":
                    try:
                        stats = compute_profit_factor()
                        text = (
                            f"📈 *Profit Factor Statistics*\n"
                            f"---\n"
                            f"📊 *Profit Factor:* {stats['profit_factor']:.2f}\n"
                            f"💷 *Gross Profits:* £{stats['gross_profits']:.2f}\n"
                            f"💷 *Gross Losses:* £{stats['gross_losses']:.2f}"
                        )
                        notify(text, chat_id, parse_mode="MarkdownV2")
                    except Exception as e:
                        notify(
                            f"❗ *Error Computing Profit Factor:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data == "recoveryfactor":
                    try:
                        stats = compute_recovery_factor()
                        text = (
                            f"📈 *Recovery Factor Statistics*\n"
                            f"---\n"
                            f"📊 *Recovery Factor:* {stats['recovery_factor']:.2f}\n"
                            f"💷 *Absolute Return:* {stats['absolute_return']:.2%}\n"
                            f"📉 *Max Drawdown:* {stats['max_drawdown']:.2%}"
                        )
                        notify(text, chat_id, parse_mode="MarkdownV2")
                    except Exception as e:
                        notify(
                            f"❗ *Error Computing Recovery Factor:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data == "winlossstreaks":
                    try:
                        stats = compute_win_loss_streaks()
                        text = (
                            f"🏆 *Win/Loss Streak Statistics*\n"
                            f"---\n"
                            f"📈 *Longest Win Streak:* {stats['longest_win_streak']} trades\n"
                            f"📉 *Longest Loss Streak:* {stats['longest_loss_streak']} trades"
                        )
                        notify(text, chat_id, parse_mode="MarkdownV2")
                    except Exception as e:
                        notify(
                            f"❗ *Error Computing Win/Loss Streaks:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data == "transactioncosts":
                    try:
                        stats = compute_transaction_costs()
                        text = (
                            f"💸 *Transaction Costs*\n"
                            f"---\n"
                            f"💷 *Total Costs:* £{stats['total_costs']:.2f}\n"
                            f"📉 *Spread Costs:* £{stats['spread_costs']:.2f}\n"
                            f"📉 *Commission Costs:* £{stats['commission_costs']:.2f}"
                        )
                        notify(text, chat_id, parse_mode="MarkdownV2")
                    except Exception as e:
                        notify(
                            f"❗ *Error Computing Transaction Costs:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data == "overtrading":
                    try:
                        stats = compute_overtrading_metrics()
                        text = (
                            f"📈 *Overtrading Metrics*\n"
                            f"---\n"
                            f"📊 *Trades per Day:* {stats['trades_per_day']:.2f}\n"
                            f"📊 *Trades per Week:* {stats['trades_per_week']:.2f}"
                        )
                        notify(text, chat_id, parse_mode="MarkdownV2")
                    except Exception as e:
                        notify(
                            f"❗ *Error Computing Overtrading Metrics:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data == "holdingvsprofit":
                    try:
                        chart_path, title = generate_holding_time_vs_profitability()
                        if chart_path:
                            send_photo(chart_path, caption=f"{title}", chat_id=chat_id)
                        else:
                            notify(
                                f"📊 *{title}*",
                                chat_id,
                                parse_mode="MarkdownV2"
                            )
                    except Exception as e:
                        notify(
                            f"❗ *Error Generating Holding Time vs. Profitability Chart:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data == "log":
                    trade_log_offset[chat_id] = 0
                    filters = trade_log_filters[chat_id]
                    try:
                        trade_log_text, reply_markup, current_offset, total = get_trade_log(
                            "CLOSE_BUY", filters["start_date"], filters["end_date"], offset=trade_log_offset[chat_id]
                        )
                        trade_log_offset[chat_id] = current_offset
                        notify(trade_log_text, chat_id, reply_markup, parse_mode="MarkdownV2")
                    except Exception as e:
                        notify(
                            f"❗ *Error Retrieving Trade Log:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data == "log_week":
                    current_date = datetime.now()
                    start_date = current_date - timedelta(days=7)
                    trade_log_filters[chat_id] = {"trade_type": "CLOSE_BUY", "start_date": start_date, "end_date": None}
                    trade_log_offset[chat_id] = 0
                    try:
                        trade_log_text, reply_markup, current_offset, total = get_trade_log(
                            "CLOSE_BUY", start_date, None, offset=trade_log_offset[chat_id]
                        )
                        trade_log_offset[chat_id] = current_offset
                        notify(trade_log_text, chat_id, reply_markup, parse_mode="MarkdownV2")
                    except Exception as e:
                        notify(
                            f"❗ *Error Retrieving Trade Log:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data == "toggle_livetracking":
                    global live_position_tracking, live_position_message_id
                    live_position_tracking = not live_position_tracking
                    status: str = "enabled" if live_position_tracking else "disabled"
                    if live_position_tracking:
                        # Send logging options keyboard when enabling live tracking
                        send_live_position_logging_keyboard(chat_id)
                    else:
                        if live_position_message_id:
                            # Update message to indicate tracking stopped
                            text: str = escape_markdown(
                                "ℹ️ *Live Position Tracking Stopped.*\n"
                                "No open positions or tracking disabled."
                            )
                            payload: Dict[str, Any] = {
                                "chat_id": chat_id,
                                "message_id": live_position_message_id,
                                "text": text,
                                "parse_mode": "MarkdownV2"
                            }
                            try:
                                response = requests.post(
                                    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageText",
                                    json=payload,
                                    timeout=(15, 45)
                                )
                                response.raise_for_status()
                                if live_position_logging:
                                    logging.info("Live position message updated: Tracking stopped.")
                                telegram_failure_count = 0
                            except Exception as e:
                                telegram_failure_count += 1
                                if live_position_logging:
                                    logging.error(f"Failed to update live position message: {e}")
                                live_position_message_id = None
                        # Return to main menu when disabling
                        send_inline_keyboard(chat_id)
                    notify(
                        f"🔔 *Live Position Tracking:* {status}.",
                        chat_id,
                        parse_mode="MarkdownV2"
                    )
                elif callback_data == "toggle_live_logging":
                    live_position_logging = not live_position_logging
                    status: str = "enabled" if live_position_logging else "disabled"
                    notify(
                        f"🔔 *Live Position Logging:* {status}.",
                        chat_id,
                        parse_mode="MarkdownV2"
                    )
                    # Refresh logging options keyboard to reflect new state
                    send_live_position_logging_keyboard(chat_id)
                elif callback_data == "main_menu":
                    send_inline_keyboard(chat_id)
                    notify(
                        "🔙 *Returned to Main Menu.*",
                        chat_id,
                        parse_mode="MarkdownV2"
                    )
                elif callback_data == "log_month":
                    current_date = datetime.now()
                    start_date = current_date - timedelta(days=30)
                    trade_log_filters[chat_id] = {"trade_type": "CLOSE_BUY", "start_date": start_date, "end_date": None}
                    trade_log_offset[chat_id] = 0
                    try:
                        trade_log_text, reply_markup, current_offset, total = get_trade_log(
                            "CLOSE_BUY", start_date, None, offset=trade_log_offset[chat_id]
                        )
                        trade_log_offset[chat_id] = current_offset
                        notify(trade_log_text, chat_id, reply_markup, parse_mode="MarkdownV2")
                    except Exception as e:
                        notify(
                            f"❗ *Error Retrieving Trade Log:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data == "log_3months":
                    current_date = datetime.now()
                    start_date = current_date - timedelta(days=90)
                    trade_log_filters[chat_id] = {"trade_type": "CLOSE_BUY", "start_date": start_date, "end_date": None}
                    trade_log_offset[chat_id] = 0
                    try:
                        trade_log_text, reply_markup, current_offset, total = get_trade_log(
                            "CLOSE_BUY", start_date, None, offset=trade_log_offset[chat_id]
                        )
                        trade_log_offset[chat_id] = current_offset
                        notify(trade_log_text, chat_id, reply_markup, parse_mode="MarkdownV2")
                    except Exception as e:
                        notify(
                            f"❗ *Error Retrieving Trade Log:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data == "log_6months":
                    current_date = datetime.now()
                    start_date = current_date - timedelta(days=180)
                    trade_log_filters[chat_id] = {"trade_type": "CLOSE_BUY", "start_date": start_date, "end_date": None}
                    trade_log_offset[chat_id] = 0
                    try:
                        trade_log_text, reply_markup, current_offset, total = get_trade_log(
                            "CLOSE_BUY", start_date, None, offset=trade_log_offset[chat_id]
                        )
                        trade_log_offset[chat_id] = current_offset
                        notify(trade_log_text, chat_id, reply_markup, parse_mode="MarkdownV2")
                    except Exception as e:
                        notify(
                            f"❗ *Error Retrieving Trade Log:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data == "log_9months":
                    current_date = datetime.now()
                    start_date = current_date - timedelta(days=270)
                    trade_log_filters[chat_id] = {"trade_type": "CLOSE_BUY", "start_date": start_date, "end_date": None}
                    trade_log_offset[chat_id] = 0
                    try:
                        trade_log_text, reply_markup, current_offset, total = get_trade_log(
                            "CLOSE_BUY", start_date, None, offset=trade_log_offset[chat_id]
                        )
                        trade_log_offset[chat_id] = current_offset
                        notify(trade_log_text, chat_id, reply_markup, parse_mode="MarkdownV2")
                    except Exception as e:
                        notify(
                            f"❗ *Error Retrieving Trade Log:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data == "log_12months":
                    current_date = datetime.now()
                    start_date = current_date - timedelta(days=365)
                    trade_log_filters[chat_id] = {"trade_type": "CLOSE_BUY", "start_date": start_date, "end_date": None}
                    trade_log_offset[chat_id] = 0
                    try:
                        trade_log_text, reply_markup, current_offset, total = get_trade_log(
                            "CLOSE_BUY", start_date, None, offset=trade_log_offset[chat_id]
                        )
                        trade_log_offset[chat_id] = current_offset
                        notify(trade_log_text, chat_id, reply_markup, parse_mode="MarkdownV2")
                    except Exception as e:
                        notify(
                            f"❗ *Error Retrieving Trade Log:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data == "log_most_recent":
                    query = "SELECT id, timestamp FROM trades WHERE trade_type = 'CLOSE_BUY' ORDER BY timestamp DESC LIMIT 1"
                    with engine.connect() as conn:
                        result = conn.execute(text(query)).fetchone()
                    if result:
                        start_date = pd.to_datetime(result[1])
                        end_date = start_date + timedelta(seconds=1)
                        trade_log_filters[chat_id] = {"trade_type": "CLOSE_BUY", "start_date": start_date, "end_date": end_date}
                        trade_log_offset[chat_id] = 0
                        try:
                            trade_log_text, reply_markup, current_offset, total = get_trade_log(
                                "CLOSE_BUY", start_date, end_date, offset=trade_log_offset[chat_id]
                            )
                            trade_log_offset[chat_id] = current_offset
                            notify(trade_log_text, chat_id, reply_markup, parse_mode="MarkdownV2")
                        except Exception as e:
                            notify(
                                f"❗ *Error Retrieving Trade Log:* {str(e)}",
                                chat_id,
                                parse_mode="MarkdownV2"
                            )
                    else:
                        notify(
                            "ℹ️ *No Trades Found.*",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data == "log_all":
                    trade_log_filters[chat_id] = {"trade_type": "CLOSE_BUY", "start_date": None, "end_date": None}
                    trade_log_offset[chat_id] = 0
                    try:
                        trade_log_text, reply_markup, current_offset, total = get_trade_log(
                            "CLOSE_BUY", None, None, offset=trade_log_offset[chat_id]
                        )
                        trade_log_offset[chat_id] = current_offset
                        notify(trade_log_text, chat_id, reply_markup, parse_mode="MarkdownV2")
                    except Exception as e:
                        notify(
                            f"❗ *Error Retrieving Trade Log:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data == "report":
                    try:
                        analytics = compute_analytics()
                        report_text = (
                            f"📊 *Analytics Report*\n"
                            f"---\n"
                            f"🔢 *Total Trades:* {analytics['total_trades']}\n"
                            f"🏆 *Win Rate:* {analytics['win_rate']:.2%}\n"
                            f"💷 *Total P/L:* £{analytics['total_pl']:.2f}\n"
                            f"📉 *Max Drawdown:* {analytics['max_drawdown']:.2%}\n"
                            f"📈 *Sharpe Ratio:* {analytics['sharpe_ratio']:.2f}"
                        )
                        notify(report_text, chat_id, parse_mode="MarkdownV2")
                    except Exception as e:
                        notify(
                            f"❗ *Error Generating Report:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data == "schedule":
                    scheduled_reports = not scheduled_reports
                    status: str = "enabled" if scheduled_reports else "disabled"
                    notify(
                        f"📅 *Scheduled Reports:* {status}.",
                        chat_id,
                        parse_mode="MarkdownV2"
                    )
                elif callback_data == "monitor":
                    position_monitoring_enabled = not position_monitoring_enabled
                    status: str = "enabled" if position_monitoring_enabled else "disabled"
                    notify(
                        f"👀 *Position Monitoring:* {status}.",
                        chat_id,
                        parse_mode="MarkdownV2"
                    )
                elif callback_data == "stop":
                    stop_flag = True
                    notify(
                        "🛑 *Bot Stopping...*",
                        chat_id,
                        parse_mode="MarkdownV2"
                    )
                    break
                elif callback_data == "equity":
                    try:
                        chart_path, title = generate_equity_curve()
                        if chart_path:
                            send_photo(chart_path, caption=f"{title}", chat_id=chat_id)
                        else:
                            notify(
                                f"📉 *Equity Curve:* {title}",
                                chat_id,
                                parse_mode="MarkdownV2"
                            )
                    except Exception as e:
                        notify(
                            f"❗ *Error Generating Equity Chart:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data == "drawdown":
                    try:
                        chart_path, max_drawdown, title = generate_drawdown_curve()
                        if chart_path:
                            send_photo(
                                chart_path,
                                caption=f"{title}\nMax Drawdown: {max_drawdown:.2%}",
                                chat_id=chat_id
                            )
                        else:
                            notify(
                                f"📉 *Drawdown Curve:* {title}",
                                chat_id,
                                parse_mode="MarkdownV2"
                            )
                    except Exception as e:
                        notify(
                            f"❗ *Error Generating Drawdown Chart:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data == "dashboard":
                    try:
                        dashboard_text, equity_chart, drawdown_chart = generate_dashboard()
                        notify(
                            f"📋 *Dashboard*\n---\n{dashboard_text}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                        if equity_chart:
                            send_photo(equity_chart, caption="Equity Curve", chat_id=chat_id)
                        if drawdown_chart:
                            send_photo(drawdown_chart, caption="Drawdown Curve", chat_id=chat_id)
                    except Exception as e:
                        notify(
                            f"❗ *Error Generating Dashboard:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data == "buy":
                    try:
                        with mt5_lock:
                            tick = mt5.symbol_info_tick(SYMBOL)
                            positions = mt5.positions_get(symbol=SYMBOL)
                            symbol_info = mt5.symbol_info(SYMBOL)
                            account_info = mt5.account_info()
                        if not tick or not symbol_info or not account_info:
                            notify(
                                "❗ *Error:* Unable to fetch market data.",
                                chat_id,
                                parse_mode="MarkdownV2"
                            )
                            continue
                        current_price: float = tick.ask
                        equity_gbp: float = account_info.equity * EXCHANGE_RATE
                        if positions:
                            notify(
                                "❌ *Error:* A position is already open.",
                                chat_id,
                                parse_mode="MarkdownV2"
                            )
                            continue
                        position_size: float = user_position_size if user_position_size is not None else 0.2
                        unit_label: str = "lots"
                        if position_size < MIN_POSITION_SIZE:
                            notify(
                                f"❌ *Invalid Position Size:* {position_size} is below minimum {MIN_POSITION_SIZE}.",
                                chat_id,
                                parse_mode="MarkdownV2"
                            )
                            continue
                        with mt5_lock:
                            request: Dict[str, Any] = {
                                "action": mt5.TRADE_ACTION_DEAL,
                                "symbol": SYMBOL,
                                "volume": position_size,
                                "type": mt5.ORDER_TYPE_BUY,
                                "price": current_price,
                                "deviation": 20,
                                "magic": 234000,
                                "comment": "Manual BUY",
                                "type_time": mt5.ORDER_TIME_GTC,
                                "type_filling": mt5.ORDER_FILLING_IOC,
                            }
                            result = mt5.order_send(request)
                        if result.retcode == mt5.TRADE_RETCODE_DONE:
                            notify(
                                f"✅ *Manual BUY {SYMBOL}*\n"
                                f"---\n"
                                f"💵 *Price:* $ {current_price:.2f}\n"
                                f"📏 *Size:* {position_size} {unit_label}\n"
                                f"💷 *Equity:* £{equity_gbp:.2f}",
                                chat_id,
                                parse_mode="MarkdownV2"
                            )
                            log_trade(
                                datetime.now(), "BUY", SYMBOL, current_price, position_size, unit_label,
                                0.0, equity_gbp, "Manual BUY via Telegram", {}
                            )
                        else:
                            notify(
                                f"❗ *Manual BUY Failed:* {result.comment}",
                                chat_id,
                                parse_mode="MarkdownV2"
                            )
                    except Exception as e:
                        notify(
                            f"❗ *Error Executing Manual BUY:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data == "sharpetrend":
                    try:
                        chart_path, title = generate_sharpe_ratio_trend()
                        if chart_path:
                            send_photo(chart_path, caption=f"{title}", chat_id=chat_id)
                        else:
                            notify(
                                f"📊 *{title}*",
                                chat_id,
                                parse_mode="MarkdownV2"
                            )
                    except Exception as e:
                        notify(
                            f"❗ *Error Generating Sharpe Ratio Trend:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data == "tradeduration":
                    try:
                        chart_path, title = generate_trade_duration_distribution()
                        if chart_path:
                            send_photo(chart_path, caption=f"{title}", chat_id=chat_id)
                        else:
                            notify(
                                f"📊 *{title}*",
                                chat_id,
                                parse_mode="MarkdownV2"
                            )
                    except Exception as e:
                        notify(
                            f"❗ *Error Generating Trade Duration Distribution:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data == "monthlypl":
                    try:
                        chart_path, title = generate_monthly_performance_chart()
                        if chart_path:
                            send_photo(chart_path, caption=f"{title}", chat_id=chat_id)
                        else:
                            notify(
                                f"📊 *{title}*",
                                chat_id,
                                parse_mode="MarkdownV2"
                            )
                    except Exception as e:
                        notify(
                            f"❗ *Error Generating Monthly Performance Chart:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data == "close":
                    try:
                        with mt5_lock:
                            positions = mt5.positions_get(symbol=SYMBOL)
                            tick = mt5.symbol_info_tick(SYMBOL)
                            account_info = mt5.account_info()
                        if not positions:
                            notify(
                                "ℹ️ *No Open Positions to Close.*",
                                chat_id,
                                parse_mode="MarkdownV2"
                            )
                            continue
                        if not tick or not account_info:
                            notify(
                                "❗ *Error:* Unable to fetch market data.",
                                chat_id,
                                parse_mode="MarkdownV2"
                            )
                            continue
                        position = positions[0]
                        position_ticket: int = position.ticket
                        position_volume: float = position.volume
                        current_price: float = tick.bid
                        open_price: float = position.price_open
                        pips: float = round((current_price - open_price) * 10, 1)  # 1 pip = 0.1 for GOLD
                        equity_gbp: float = account_info.equity * EXCHANGE_RATE
                        with mt5_lock:
                            request: Dict[str, Any] = {
                                "action": mt5.TRADE_ACTION_DEAL,
                                "symbol": SYMBOL,
                                "volume": position_volume,
                                "type": mt5.ORDER_TYPE_SELL,
                                "position": position_ticket,
                                "price": current_price,
                                "deviation": 20,
                                "magic": 234000,
                                "comment": "Manual CLOSE",
                                "type_time": mt5.ORDER_TIME_GTC,
                                "type_filling": mt5.ORDER_FILLING_IOC,
                            }
                            result = mt5.order_send(request)
                        if result.retcode == mt5.TRADE_RETCODE_DONE:
                            profit_loss_gbp: float = get_trade_profit_gbp(position_ticket)
                            notify(
                                f"✅ *Manual CLOSE BUY {SYMBOL}*\n"
                                f"---\n"
                                f"💵 *Price:* $ {current_price:.2f}\n"
                                f"📏 *Size:* {position_volume} lots\n"
                                f"💷 *P/L:* £{profit_loss_gbp:.2f} | Pips: {pips:+.1f}\n"
                                f"💷 *Equity:* £{equity_gbp:.2f}",
                                chat_id,
                                parse_mode="MarkdownV2"
                            )
                            log_trade(
                                datetime.now(), "CLOSE_BUY", SYMBOL, current_price, position_volume,
                                "lots", profit_loss_gbp, equity_gbp, "Manual CLOSE via Telegram", {}
                            )
                        else:
                            notify(
                                f"❗ *Manual CLOSE Failed:* {result.comment}",
                                chat_id,
                                parse_mode="MarkdownV2"
                            )
                    except Exception as e:
                        notify(
                            f"❗ *Error Executing Manual CLOSE:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data == "health":
                    try:
                        cpu_usage = psutil.cpu_percent(interval=1)
                        memory = psutil.virtual_memory()
                        disk = psutil.disk_usage('/')
                        health_status = (
                            f"🩺 *Bot Health Check*\n"
                            f"---\n"
                            f"🖥 *CPU Usage:* {cpu_usage:.2f}%\n"
                            f"🧠 *Memory Usage:* {memory.percent:.2f}% ({memory.used / 1024**3:.2f}/{memory.total / 1024**3:.2f} GB)\n"
                            f"💾 *Disk Usage:* {disk.percent:.2f}% ({disk.used / 1024**3:.2f}/{disk.total / 1024**3:.2f} GB)\n"
                            f"🏃 *Running:* {'Yes' if not stop_flag else 'No'}\n"
                            f"⚠️ *MT5 Failures:* {mt5_failure_count}/{MT5_MAX_FAILURES}\n"
                            f"⚠️ *Telegram Failures:* {telegram_failure_count}/{TELEGRAM_MAX_FAILURES}"
                        )
                        notify(health_status, chat_id, parse_mode="MarkdownV2")
                    except Exception as e:
                        notify(
                            f"❗ *Error Performing Health Check:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data == "outlook":
                    try:
                        chart_path, avg_return = generate_future_equity_outlook()
                        send_photo(
                            chart_path,
                            caption=f"Future Equity Outlook\nAvg Monthly Return: {avg_return*100:.2f}%",
                            chat_id=chat_id
                        )
                    except Exception as e:
                        notify(
                            f"❗ *Error Generating Future Outlook:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data == "heatmaptrades":
                    try:
                        chart_path = generate_trade_heatmap()
                        send_photo(chart_path, caption="Trade Heatmap", chat_id=chat_id)
                    except Exception as e:
                        notify(
                            f"❗ *Error Generating Trade Heatmap:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data == "featureimportance":
                    try:
                        chart_path = generate_feature_importance()
                        send_photo(chart_path, caption="Feature Importance", chat_id=chat_id)
                    except Exception as e:
                        notify(
                            f"❗ *Error Generating Feature Importance:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data == "pause":
                    trading_paused = True
                    notify(
                        "⏸ *Trading Paused.*",
                        chat_id,
                        parse_mode="MarkdownV2"
                    )
                elif callback_data == "resume":
                    trading_paused = False
                    notify(
                        "▶️ *Trading Resumed.*",
                        chat_id,
                        parse_mode="MarkdownV2"
                    )
                elif callback_data == "winrate":
                    try:
                        stats = compute_winrate()
                        text = (
                            f"🏆 *Win Rate Statistics*\n"
                            f"---\n"
                            f"📊 *Win Rate:* {stats['win_rate']:.2%}\n"
                            f"💷 *Average Win:* £{stats['avg_win']:.2f}\n"
                            f"💷 *Average Loss:* £{stats['avg_loss']:.2f}\n"
                            f"🎯 *Expectancy:* £{stats['expectancy']:.2f}\n"
                            f"🔢 *Total Trades:* {stats['total_trades']}"
                        )
                        notify(text, chat_id, parse_mode="MarkdownV2")
                    except Exception as e:
                        notify(
                            f"❗ *Error Computing Win Rate:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data == "returnstats":
                    try:
                        stats = compute_return_stats()
                        text = (
                            f"📈 *Return Statistics*\n"
                            f"---\n"
                            f"💸 *Compound Return:* {stats['compound_return']:.2%}\n"
                            f"📅 *Annualized Return:* {stats['annualized_return']:.2%}\n"
                            f"⚖️ *Volatility:* {stats['volatility']:.2%}"
                        )
                        notify(text, chat_id, parse_mode="MarkdownV2")
                    except Exception as e:
                        notify(
                            f"❗ *Error Computing Return Stats:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data == "decisionlog":
                    try:
                        decision_log_offset[chat_id] = 0
                        decision_log_text, reply_markup, current_offset, total = get_decision_log(SYMBOL, offset=decision_log_offset[chat_id])
                        decision_log_offset[chat_id] = current_offset
                        notify(decision_log_text, chat_id, reply_markup, parse_mode="MarkdownV2")
                    except Exception as e:
                        notify(
                            f"❗ *Error Retrieving Decision Log:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data.startswith("decisions_prev_"):
                    new_offset = int(callback_data.split("_")[-1])
                    try:
                        decision_log_text, reply_markup, current_offset, total = get_decision_log(SYMBOL, offset=new_offset)
                        decision_log_offset[chat_id] = current_offset
                        notify(decision_log_text, chat_id, reply_markup, parse_mode="MarkdownV2")
                    except Exception as e:
                        notify(
                            f"❗ *Error Retrieving Decision Log:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data.startswith("decisions_next_"):
                    new_offset = int(callback_data.split("_")[-1])
                    try:
                        decision_log_text, reply_markup, current_offset, total = get_decision_log(SYMBOL, offset=new_offset)
                        decision_log_offset[chat_id] = current_offset
                        notify(decision_log_text, chat_id, reply_markup, parse_mode="MarkdownV2")
                    except Exception as e:
                        notify(
                            f"❗ *Error Retrieving Decision Log:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data.startswith("view_trades"):
                    trade_log_offset[chat_id] = 0
                    filters = trade_log_filters[chat_id]
                    try:
                        trade_log_text, reply_markup, current_offset, total = get_trade_log(
                            "CLOSE_BUY", filters["start_date"], filters["end_date"], offset=trade_log_offset[chat_id]
                        )
                        trade_log_offset[chat_id] = current_offset
                        notify(trade_log_text, chat_id, reply_markup, parse_mode="MarkdownV2")
                    except Exception as e:
                        notify(
                            f"❗ *Error Retrieving Trade Log:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data.startswith("trades_prev_"):
                    new_offset = int(callback_data.split("_")[-1])
                    filters = trade_log_filters[chat_id]
                    try:
                        trade_log_text, reply_markup, current_offset, total = get_trade_log(
                            "CLOSE_BUY", filters["start_date"], filters["end_date"], offset=new_offset
                        )
                        trade_log_offset[chat_id] = current_offset
                        notify(trade_log_text, chat_id, reply_markup, parse_mode="MarkdownV2")
                    except Exception as e:
                        notify(
                            f"❗ *Error Retrieving Trade Log:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data.startswith("trades_next_"):
                    new_offset = int(callback_data.split("_")[-1])
                    filters = trade_log_filters[chat_id]
                    try:
                        trade_log_text, reply_markup, current_offset, total = get_trade_log(
                            "CLOSE_BUY", filters["start_date"], filters["end_date"], offset=new_offset
                        )
                        trade_log_offset[chat_id] = current_offset
                        notify(trade_log_text, chat_id, reply_markup, parse_mode="MarkdownV2")
                    except Exception as e:
                        notify(
                            f"❗ *Error Retrieving Trade Log:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data.startswith("trade_details_"):
                    logging.info(f"Received trade_details callback with data: {callback_data}")
                    try:
                        trade_id_str = callback_data.split("_")[-1]
                        if not trade_id_str.isdigit():
                            logging.error(f"Invalid trade_id format: {trade_id_str}")
                            notify(
                                "❌ *Invalid Trade ID Format.*",
                                chat_id,
                                parse_mode="MarkdownV2"
                            )
                            continue
                        trade_id = int(trade_id_str)
                        logging.info(f"Fetching details for trade_id: {trade_id}")

                        # Fetch the CLOSE_BUY trade
                        query: str = """
                            SELECT * FROM trades
                            WHERE id = :trade_id AND trade_type = 'CLOSE_BUY'
                        """
                        params: Dict[str, Any] = {"trade_id": trade_id}
                        logging.debug(f"Executing CLOSE_BUY query with params: {params}")
                        df: pd.DataFrame = pd.read_sql_query(query, engine, params=params)
                        if df.empty:
                            logging.warning(f"No CLOSE_BUY trade found for trade_id: {trade_id}")
                            notify(
                                "ℹ️ *No Trade Details Available for This Trade.*",
                                chat_id,
                                parse_mode="MarkdownV2"
                            )
                            continue

                        trade = df.iloc[0]
                        logging.info(f"Found CLOSE_BUY trade: {trade.to_dict()}")
                        close_time = pd.to_datetime(trade['timestamp'])
                        symbol = trade['symbol']
                        close_price = trade['price']
                        position_size = trade['position_size']
                        profit_loss = trade['profit_loss']
                        unit = trade['unit_label']

                        # Find the matching BUY trade
                        query_open = """
                            SELECT * FROM trades
                            WHERE trade_type = 'BUY' AND symbol = :symbol
                              AND timestamp < :close_time
                            ORDER BY timestamp DESC LIMIT 1
                        """
                        params_open = {
                            "symbol": symbol,
                            "close_time": close_time.strftime('%Y-%m-%d %H:%M:%S')
                        }
                        logging.debug(f"Executing BUY query with params: {params_open}")
                        df_open = pd.read_sql_query(query_open, engine, params=params_open)

                        if df_open.empty:
                            logging.warning(f"No matching BUY trade found for symbol {symbol} before {close_time}")
                            notify(
                                "ℹ️ *No Matching BUY Trade Found for This CLOSE_BUY Trade.*",
                                chat_id,
                                parse_mode="MarkdownV2"
                            )
                            continue

                        open_trade = df_open.iloc[0]
                        logging.info(f"Found matching BUY trade: {open_trade.to_dict()}")
                        open_price = open_trade['price']
                        open_time = pd.to_datetime(open_trade['timestamp'])

                        # Calculate trade details
                        duration = str(close_time - open_time).split(".")[0]
                        pips = round((close_price - open_price) * 10, 1)  # Assuming GOLD, 1 pip = 0.1 price units

                        # Calculate max drawdown for risk-to-reward
                        with mt5_lock:
                            rates = mt5.copy_rates_range(symbol, TIMEFRAME, open_time, close_time)
                        if rates is None or len(rates) == 0:
                            logging.warning(f"No price data available between {open_time} and {close_time} for {symbol}")
                            max_drawdown = 0.0
                            risk_to_reward = "N/A"
                        else:
                            prices = pd.DataFrame(rates)['low']  # Use low prices for drawdown
                            min_price = prices.min()
                            max_drawdown = (open_price - min_price) * 10  # In pips
                            profit_pips = abs(pips) if profit_loss > 0 else 0.0
                            risk_to_reward = (
                                f"{profit_pips / max_drawdown:.2f}:1" if max_drawdown > 0 and profit_pips > 0
                                else "N/A"
                            )
                            logging.info(f"Calculated: pips={pips}, max_drawdown={max_drawdown}, risk_to_reward={risk_to_reward}")

                        # Format the trade details message
                        details = (
                            f"📋 *Trade Summary*\n"
                            f"---\n"
                            f"🕒 *Open Time:* {open_time.strftime('%Y-%m-%d %H:%M')}\n"
                            f"🕒 *Close Time:* {close_time.strftime('%Y-%m-%d %H:%M')}\n"
                            f"⏱ *Duration:* {duration}\n"
                            f"🔁 *Symbol:* {symbol}\n"
                            f"📈 *Open Price:* $ {open_price:.2f}\n"
                            f"📉 *Close Price:* $ {close_price:.2f}\n"
                            f"📏 *Size:* {position_size} {unit}\n"
                            f"📏 *Total Pips:* {pips:+.1f}\n"
                            f"💷 *Total P/L:* £{profit_loss:.2f}\n"
                            f"⚖️ *Risk:Reward:* {risk_to_reward}"
                        )
                        logging.info(f"Sending trade details to chat_id {chat_id}")
                        notify(details, chat_id, parse_mode="MarkdownV2")
                    except Exception as e:
                        logging.error(f"Failed to retrieve trade details for trade_id {trade_id}: {e}", exc_info=True)
                        notify(
                            "❗ *Unable to Retrieve Trade Details Due to an Internal Error.*",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data == "equity_chart":
                    try:
                        chart_path, title = generate_equity_curve()
                        if chart_path:
                            send_photo(chart_path, caption=f"{title}", chat_id=chat_id)
                        else:
                            notify(
                                f"📉 *Equity Curve:* {title}",
                                chat_id,
                                parse_mode="MarkdownV2"
                            )
                    except Exception as e:
                        notify(
                            f"❗ *Error Generating Equity Chart:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data == "drawdown_chart":
                    try:
                        chart_path, max_drawdown, title = generate_drawdown_curve()
                        if chart_path:
                            send_photo(
                                chart_path,
                                caption=f"{title}\nMax Drawdown: {max_drawdown:.2%}",
                                chat_id=chat_id
                            )
                        else:
                            notify(
                                f"📉 *Drawdown Curve:* {title}",
                                chat_id,
                                parse_mode="MarkdownV2"
                            )
                    except Exception as e:
                        notify(
                            f"❗ *Error Generating Drawdown Chart:* {str(e)}",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                elif callback_data.startswith("togglenotify_"):
                    notify_type: str = callback_data.replace("togglenotify_", "").upper()
                    if notify_type in notification_settings:
                        notification_settings[notify_type] = not notification_settings[notify_type]
                        status: str = "enabled" if notification_settings[notify_type] else "disabled"
                        notify(
                            f"🔔 *{notify_type} Notifications:* {status}.",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )
                    else:
                        notify(
                            "❌ *Invalid Notification Type.*",
                            chat_id,
                            parse_mode="MarkdownV2"
                        )

            if telegram_failure_count >= TELEGRAM_MAX_FAILURES:
                notify(
                    f"⚠️ *Telegram Circuit Breaker Tripped:* {telegram_failure_count} failures. Pausing for {TELEGRAM_BACKOFF_TIME} seconds.",
                    parse_mode="MarkdownV2"
                )
                time.sleep(TELEGRAM_BACKOFF_TIME)
                telegram_failure_count = 0

        except Exception as e:
            telegram_failure_count += 1
            logging.error(f"Error in Telegram thread: {e}")
            time.sleep(5)

def main() -> None:
    """
    Main function to run the trading bot with live position tracking updating every 5 seconds.
    """
    global stop_flag, last_report_time, last_position_update, last_prediction_time
    global trading_paused, last_heartbeat_time, last_alert_check, mt5_failure_count, telegram_failure_count
    global live_position_tracking, last_live_position_update, live_position_logging, latest_analytics

    # Initialize MT5
    if not mt5.initialize(login=MT5_LOGIN, server=MT5_SERVER, password=MT5_PASSWORD, path=MT5_PATH):
        error_msg: str = f"❌ **MT5 Initialization Failed:** {mt5.last_error()}"
        logging.error(error_msg)
        notify(error_msg)
        sys.exit(1)
    logging.info("MT5 initialized successfully.")
    notify("✅ **MT5 Initialized Successfully!**")

    # Initialize trade database
    init_trade_db()
    notify("📊 **Trade Database Initialized!**")

    # Load model and scaler
    try:
        model: PPO = PPO.load(model_path)
        scaler: MinMaxScaler = joblib.load(scaler_path)
        logging.info("Model and scaler loaded successfully.")
        notify("🤖 **Model and Scaler Loaded Successfully!**")
    except Exception as e:
        error_msg: str = f"❌ **Failed to Load Model or Scaler:** {e}"
        logging.error(error_msg)
        notify(error_msg)
        mt5.shutdown()
        sys.exit(1)

    # Start Telegram updates thread
    telegram_thread = threading.Thread(target=handle_telegram_updates, args=(model, scaler), daemon=True)
    telegram_thread.start()
    logging.info("Telegram updates thread started.")
    notify("📲 **Telegram Updates Thread Started!**")

    # Send startup message and simulate /start command
    notify("🚀 **Trading Bot Started!**")
    chat_id: str = TELEGRAM_USER_ID  # Use the predefined user ID
    send_inline_keyboard(chat_id)
    notify(
        "✅ **Bot Started!** Use the inline keyboard or commands to interact. 📲",
        chat_id,
        parse_mode="MarkdownV2"
    )

    last_state_log: datetime = datetime.now()
    STATE_LOG_INTERVAL: int = 300  # Log state every 5 minutes
    CHECK_INTERVAL: float = 5.0  # Check every 5 seconds to align with dashboard polling

    try:
        while not stop_flag:
            now: datetime = datetime.now()

            # Circuit breaker for MT5 failures
            if mt5_failure_count >= MT5_MAX_FAILURES:
                notify(f"⚠️ **MT5 Circuit Breaker Tripped:** {mt5_failure_count} failures. Pausing for {MT5_BACKOFF_TIME} seconds.")
                time.sleep(MT5_BACKOFF_TIME)
                mt5_failure_count = 0
                continue

            # Circuit breaker for Telegram failures
            if telegram_failure_count >= TELEGRAM_MAX_FAILURES:
                notify(f"⚠️ **Telegram Circuit Breaker Tripped:** {telegram_failure_count} failures. Pausing for {TELEGRAM_BACKOFF_TIME} seconds.")
                time.sleep(TELEGRAM_BACKOFF_TIME)
                telegram_failure_count = 0
                continue

            # Periodic state logging
            if (now - last_state_log).total_seconds() >= STATE_LOG_INTERVAL:
                logging.info(
                    f"Trading state - Paused: {trading_paused}, "
                    f"MT5 Failures: {mt5_failure_count}/{MT5_MAX_FAILURES}, "
                    f"Telegram Failures: {telegram_failure_count}/{TELEGRAM_MAX_FAILURES}, "
                    f"Live Tracking: {live_position_tracking}, "
                    f"Live Logging: {live_position_logging}"
                )
                last_state_log = now

            # Compute analytics every 5 seconds for the app
            try:
                latest_analytics = compute_analytics()
                logging.debug(f"Analytics updated: {latest_analytics}")
            except Exception as e:
                logging.error(f"Failed to compute analytics: {e}")

            # Check for new candle and execute trading logic
            if not trading_paused and is_new_candle():
                feature_sequence, features = fetch_market_data()
                if feature_sequence is not None and features is not None:
                    action, action_label = make_prediction(model, scaler, feature_sequence)
                    tick = mt5.symbol_info_tick(SYMBOL)
                    if tick:
                        current_price: float = tick.ask
                        execute_trade(action, action_label, current_price, features)
                        log_prediction(now, SYMBOL, action_label, features)
                        last_prediction_time = now
                        mt5_failure_count = 0  # Reset on successful MT5 operation
                        if notification_settings.get(action_label, True):
                            notify(f"📈 **Action:** {action_label} | **Price:** ${current_price:.2f}")
                    else:
                        mt5_failure_count += 1
                        logging.error("Failed to fetch current price for trade execution.")
                        notify("❌ **Error:** Failed to fetch current price for trade execution.")
                else:
                    mt5_failure_count += 1
                    logging.error("Failed to fetch market data for prediction.")
                    notify("❌ **Error:** Failed to fetch market data for prediction.")

            # Check alerts periodically
            if (now - last_alert_check).total_seconds() >= ALERT_CHECK_INTERVAL:
                check_alerts()
                last_alert_check = now

            # Check price alerts
            check_price_alerts()

            # Send scheduled reports and regenerate charts
            if scheduled_reports and (now - last_report_time).total_seconds() >= REPORT_INTERVAL:
                analytics: Dict[str, Any] = compute_analytics()
                report_text: str = (
                    f"📅 **Scheduled Analytics Report**\n"
                    f"----------------------------------------\n"
                    f"🔢 **Total Trades:** {analytics['total_trades']}\n"
                    f"🏆 **Win Rate:** {analytics['win_rate']:.2%}\n"
                    f"💷 **Total P/L:** £{analytics['total_pl']:.2f}\n"
                    f"📉 **Max Drawdown:** {analytics['max_drawdown']:.2%}\n"
                    f"📈 **Sharpe Ratio:** {analytics['sharpe_ratio']:.2f}\n"
                )
                with open(ANALYTICS_REPORT_PATH, "w") as f:
                    f.write(report_text)
                notify(report_text)
                regenerate_charts()  # Added chart regeneration
                last_report_time = now

            # Position monitoring
            if position_monitoring_enabled and (now - last_position_update).total_seconds() >= 60:
                positions = mt5.positions_get(symbol=SYMBOL)
                if positions:
                    position = positions[0]
                    position_text: str = (
                        f"👁️ **Position Update for {SYMBOL}**\n"
                        f"🎫 **Ticket:** {position.ticket}\n"
                        f"🔄 **Type:** {'BUY' if position.type == mt5.ORDER_TYPE_BUY else 'SELL'}\n"
                        f"📏 **Volume:** {position.volume} lots\n"
                        f"💵 **Open Price:** ${position.price_open:.2f}\n"
                        f"💵 **Current Price:** ${position.price_current:.2f}\n"
                        f"💰 **Profit:** ${position.profit:.2f}"
                    )
                    notify(position_text)
                last_position_update = now

            # Live position tracking update
            if live_position_tracking and (now - last_live_position_update).total_seconds() >= LIVE_POSITION_UPDATE_INTERVAL:
                update_live_position_message()
                last_live_position_update = now

            # Heartbeat notification
            if heartbeat_interval and (now - last_heartbeat_time).total_seconds() >= heartbeat_interval:
                with heartbeat_lock:
                    notify("💓 **I'm Alive!** 🫡")
                    last_heartbeat_time = now

            # Process command queue after trading logic to prioritize candle checks
            try:
                while not command_queue.empty():
                    command: Dict[str, Any] = command_queue.get_nowait()
                    chat_id: str = command.get("chat_id", TELEGRAM_USER_ID)
                    action: str = command.get("action")
                    if action == "dashboard":
                        try:
                            start_date: Optional[datetime] = command.get("start_date")
                            end_date: Optional[datetime] = command.get("end_date")
                            dashboard_text, equity_chart, drawdown_chart = generate_dashboard(start_date, end_date)
                            notify(dashboard_text, chat_id)
                            if equity_chart:
                                send_photo(equity_chart, "Equity Curve", chat_id)
                            if drawdown_chart:
                                send_photo(drawdown_chart, "Drawdown Curve", chat_id)
                        except Exception as e:
                            notify(f"❌ **Error Generating Dashboard:** {e}", chat_id)
            except queue.Empty:
                pass

            time.sleep(CHECK_INTERVAL)

    except KeyboardInterrupt:
        logging.info("Bot stopped by user.")
        notify("🛑 **Bot Stopped by User.**")
    except Exception as e:
        error_msg: str = f"❌ **Unexpected Error in Main Loop:** {e}"
        logging.error(error_msg)
        notify(error_msg)
    finally:
        mt5.shutdown()
        engine.dispose()
        logging.info("Bot shutdown complete.")
        notify("🔚 **Bot Shutdown Complete.**")
        sys.exit(0)

# Flask HTTP Server Integration
from flask import Flask, jsonify
import threading

app = Flask(__name__)

@app.route('/api/price', methods=['GET'])
def get_price():
    with mt5_lock:
        tick = mt5.symbol_info_tick(SYMBOL)
        return jsonify({"price": tick.ask if tick else 0.0})

@app.route('/api/trades', methods=['GET'])
def get_trades():
    with engine.connect() as conn:
        result = conn.execute(text("SELECT id, timestamp, price, profit_loss FROM trades WHERE trade_type = 'CLOSE_BUY' ORDER BY timestamp DESC LIMIT 10"))
        trades = [{"id": row[0], "timestamp": row[1].isoformat(), "price": row[2], "profit_loss": row[3]} for row in result.fetchall()]
        return jsonify(trades)

@app.route('/api/images', methods=['GET'])
def get_images():
    images = [f for f in os.listdir(PLOT_PATH) if f.endswith('.png')]
    return jsonify(images)

@app.route('/api/metrics', methods=['GET'])
def get_metrics():
    global latest_analytics
    if not latest_analytics:
        return jsonify({"error": "Analytics not yet computed"}), 503
    return jsonify(latest_analytics)

def run_server():
    app.run(host='0.0.0.0', port=5000, threaded=True)

# Start server in a separate thread
if __name__ == "__main__":
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    main()