import eventlet
# Must be the very first thing to avoid issues with other imports
eventlet.monkey_patch()

from flask import Flask, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from flask_restful import Api, Resource
from models import engine  # Assuming your SQLAlchemy engine is defined in models.py
import os
import threading
import time
import socket
import logging

# Assuming generate_holding_time_vs_profitability is in chart_generator.py (adjust as needed)
from chart_generator import generate_holding_time_vs_profitability

app = Flask(__name__, static_folder='static', static_url_path='/static')
api = Api(app)
# Configure SocketIO to use eventlet
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# MT5 Configuration
MT5_LOGIN = 590338389
MT5_PASSWORD = "!c7XzdfMWK"
MT5_SERVER = "FxPro-MT5 Demo"
MT5_PATH = r"C:\\Program Files\\MetaTrader 5\\terminal64.exe"
SYMBOL = "GOLD"
EXCHANGE_RATE = 1.0
TELEGRAM_USER_ID = "7336312249"
PLOT_PATH = r"C:\Users\FCumm\FxPRO\Grok\Live\New\plots"

# Configure logging
logging.basicConfig(level=logging.INFO)

# Initialize MT5
if not mt5.initialize(login=MT5_LOGIN, server=MT5_SERVER, password=MT5_PASSWORD, path=MT5_PATH):
    print("MT5 initialization failed:", mt5.last_error())
    exit(1)

def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return None
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    last_rsi = rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else None
    last_loss = loss.iloc[-1] if not pd.isna(loss.iloc[-1]) else 0
    return last_rsi if last_loss != 0 else 0

def calculate_ma(prices, period=20):
    if len(prices) < period:
        return None
    return prices.rolling(window=period).mean().iloc[-1]

# Serve index.html
@app.route('/')
def serve_index():
    user_id = request.args.get('user')
    if user_id != TELEGRAM_USER_ID:
        print(f"Unauthorized access: Expected user {TELEGRAM_USER_ID}, got {user_id}")
        return jsonify({"error": "Unauthorized"}), 401
    return send_from_directory(app.static_folder, 'index.html')

# Serve chart images
@app.route('/images/<filename>')
def serve_image(filename):
    try:
        return send_from_directory(PLOT_PATH, filename)
    except Exception as e:
        print(f"Error serving image {filename}: {str(e)}")
        return jsonify({"error": "Image not found"}), 404

class AuthResource(Resource):
    def check_auth(self):
        user_id = request.headers.get('X-User-ID')
        print(f"API request - X-User-ID: {user_id}")
        if user_id != TELEGRAM_USER_ID:
            print(f"Unauthorized API access: Expected user {TELEGRAM_USER_ID}, got {user_id}")
        return user_id == TELEGRAM_USER_ID

class PriceData(AuthResource):
    def get(self):
        if not self.check_auth():
            return {"error": "Unauthorized"}, 401
        tick = mt5.symbol_info_tick(SYMBOL)
        if tick is None:
            return {"error": "Failed to fetch price data"}, 500
        return {"price": tick.bid, "time": datetime.now().isoformat()}

class Trades(AuthResource):
    def get(self):
        if not self.check_auth():
            return {"error": "Unauthorized"}, 401
        try:
            start_date = request.args.get('start')
            end_date = request.args.get('end')
            query = "SELECT * FROM trades WHERE trade_type = 'CLOSE_BUY' ORDER BY timestamp DESC LIMIT 10"
            params = {}
            if start_date and end_date:
                query += " AND timestamp BETWEEN :start AND :end"
                params['start'] = datetime.fromisoformat(start_date)
                params['end'] = datetime.fromisoformat(end_date)
            elif start_date:
                query += " AND timestamp >= :start"
                params['start'] = datetime.fromisoformat(start_date)
            elif end_date:
                query += " AND timestamp <= :end"
                params['end'] = datetime.fromisoformat(end_date)
            df = pd.read_sql_query(query, engine, params=params)
            return df.to_dict(orient='records')
        except Exception as e:
            print(f"Trades error: {str(e)}")
            return {"error": str(e)}, 500

class Images(AuthResource):
    def get(self):
        if not self.check_auth():
            return {"error": "Unauthorized"}, 401
        try:
            # Generate the Holding Time vs. Profitability chart
            chart_path, message = generate_holding_time_vs_profitability()
            if chart_path:
                logging.info(f"Successfully generated holding_time_vs_profitability chart at {chart_path}")
            else:
                logging.warning(f"Failed to generate holding_time_vs_profitability chart: {message}")

            # List all available images in PLOT_PATH
            images = [f for f in os.listdir(PLOT_PATH) if f.endswith('.png')]
            logging.info(f"Images available in {PLOT_PATH}: {images}")
            return jsonify(images)
        except Exception as e:
            logging.error(f"Images endpoint error: {str(e)}")
            return {"error": str(e)}, 500

class Positions(AuthResource):
    def get(self):
        if not self.check_auth():
            return {"error": "Unauthorized"}, 401
        positions = mt5.positions_get(symbol=SYMBOL)
        if positions is None:
            return {"error": "Failed to fetch positions"}, 500
        position_data = []
        tick = mt5.symbol_info_tick(SYMBOL)
        account_info = mt5.account_info()
        if not tick or not account_info:
            return {"error": "Failed to fetch market or account data"}, 500

        equity_gbp = account_info.equity * EXCHANGE_RATE
        current_price = tick.bid

        for pos in positions:
            pos_dict = pos._asdict()
            entry_price = pos_dict['price_open']
            profit_usd = pos_dict['profit']
            profit_gbp = profit_usd * EXCHANGE_RATE
            pips = (current_price - entry_price) * 10 if pos_dict['type'] == mt5.POSITION_TYPE_BUY else (entry_price - current_price) * 10
            equity_percentage = (profit_gbp / equity_gbp * 100) if equity_gbp != 0 else 0.0

            pos_dict.update({
                'current_price': float(current_price),
                'pips': float(pips),
                'profit_gbp': float(profit_gbp),
                'equity_percentage': float(equity_percentage),
                'last_updated': datetime.now().isoformat()
            })
            position_data.append(pos_dict)
        return position_data

class Metrics(AuthResource):
    def get(self):
        if not self.check_auth():
            return {"error": "Unauthorized"}, 401
        try:
            query = "SELECT timestamp, equity, profit_loss, trade_type, price, symbol FROM trades"
            df = pd.read_sql_query(query, engine)
            if df.empty:
                return {
                    "starting_equity": 0.0,
                    "current_equity": 0.0,
                    "equity_change": 0.0,
                    "equity_change_pct": 0.0,
                    "avg_drawdown": 0.0,
                    "max_drawdown": 0.0,
                    "avg_return_per_trade": 0.0,
                    "avg_pips_per_trade": 0.0,
                    "total_trades": 0,
                    "win_rate": 0.0,
                    "total_pl": 0.0,
                    "sharpe_ratio": 0.0
                }
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.sort_values('timestamp')
            starting_equity = df['equity'].iloc[0]
            current_equity = df['equity'].iloc[-1]
            equity_change = current_equity - starting_equity
            equity_change_pct = (equity_change / starting_equity * 100) if starting_equity != 0 else 0.0
            equity_series = df['equity'].values
            peak = np.maximum.accumulate(equity_series)
            drawdown = (peak - equity_series) / peak
            avg_drawdown = drawdown.mean() * 100 if len(drawdown) > 0 else 0.0
            max_drawdown = drawdown.max() * 100 if len(drawdown) > 0 else 0.0
            close_trades = df[df['trade_type'] == 'CLOSE_BUY']
            total_trades = len(close_trades)
            total_pl = close_trades['profit_loss'].sum() if not close_trades.empty else 0.0
            win_rate = (close_trades['profit_loss'] > 0).mean() if not close_trades.empty else 0.0
            avg_return_per_trade = close_trades['profit_loss'].mean() if not close_trades.empty else 0.0
            pips_list = []
            for _, close_trade in close_trades.iterrows():
                close_time = close_trade['timestamp']
                close_price = close_trade['price']
                symbol = close_trade['symbol']
                buy_trades = df[(df['trade_type'] == 'BUY') & (df['symbol'] == symbol) & (df['timestamp'] < close_time)]
                if not buy_trades.empty:
                    open_price = buy_trades.iloc[-1]['price']
                    pips = (close_price - open_price) * 10
                    pips_list.append(pips)
            avg_pips_per_trade = np.mean(pips_list) if pips_list else 0.0
            df.set_index('timestamp', inplace=True)
            daily_equity = df['equity'].resample('D').last().ffill()
            daily_returns = daily_equity.pct_change().dropna()
            sharpe_ratio = 0.0
            if len(daily_returns) > 1:
                mean_daily_return = daily_returns.mean()
                std_daily_return = daily_returns.std()
                annualized_mean_return = mean_daily_return * 252
                annualized_std = std_daily_return * np.sqrt(252)
                risk_free_rate_annual = 0.04
                sharpe_ratio = (annualized_mean_return - risk_free_rate_annual) / annualized_std if annualized_std != 0 else 0.0
            return {
                "starting_equity": float(starting_equity),
                "current_equity": float(current_equity),
                "equity_change": float(equity_change),
                "equity_change_pct": float(equity_change_pct),
                "avg_drawdown": float(avg_drawdown),
                "max_drawdown": float(max_drawdown),
                "avg_return_per_trade": float(avg_return_per_trade),
                "avg_pips_per_trade": float(avg_pips_per_trade),
                "total_trades": int(total_trades),
                "win_rate": float(win_rate),
                "total_pl": float(total_pl),
                "sharpe_ratio": float(sharpe_ratio)
            }
        except Exception as e:
            print(f"Metrics error: {str(e)}")
            return {"error": str(e)}, 500

class Indicators(AuthResource):
    def get(self):
        if not self.check_auth():
            return {"error": "Unauthorized"}, 401
        if not mt5.terminal_info().connected:
            print("MT5 terminal not connected")
            return {"error": "MT5 terminal not connected"}, 500
        try:
            rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M15, 0, 50)
            if rates is None or len(rates) < 50:
                print(f"Failed to fetch rates for {SYMBOL}: {mt5.last_error()}")
                return {"error": "Insufficient data for indicators"}, 500
            df = pd.DataFrame(rates)
            close_prices = df['close']
            rsi = calculate_rsi(close_prices)
            ma = calculate_ma(close_prices)
            return {"rsi": rsi, "ma": ma}
        except Exception as e:
            print(f"Indicators error: {str(e)}")
            return {"error": str(e)}, 500

class HistoricalData(AuthResource):
    def get(self):
        if not self.check_auth():
            return {"error": "Unauthorized"}, 401
        if not mt5.terminal_info().connected:
            print("MT5 terminal not connected")
            return {"error": "MT5 terminal not connected"}, 500
        try:
            # Fixed to 15m timeframe and 48 hours of data
            timeframe = '15m'
            end_date = datetime.now()
            start_date = end_date - timedelta(hours=48)

            print(f"Requesting historical data from {start_date} to {end_date} for {SYMBOL} on timeframe {timeframe}")

            mt5_timeframe = mt5.TIMEFRAME_M15  # Fixed to 15-minute candlesticks

            rates = mt5.copy_rates_range(SYMBOL, mt5_timeframe, start_date, end_date)
            if rates is None or len(rates) == 0:
                error_code = mt5.last_error()
                print(f"Failed to fetch historical rates for {SYMBOL}: Error code {error_code}")
                return {"error": f"No historical data available (Error {error_code})"}, 500

            print(f"Fetched {len(rates)} historical rates")
            print(f"Rates dtype: {rates.dtype}")
            print(f"Sample rate: {rates[0] if len(rates) > 0 else 'No data'}")

            df = pd.DataFrame(rates)
            if df.empty:
                return {"error": "No historical data available after conversion"}, 500

            required_columns = ['time', 'open', 'high', 'low', 'close']
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                print(f"Missing columns in rates data: {missing_columns}")
                return {"error": f"Missing columns in rates data: {missing_columns}"}, 500

            # Convert time to milliseconds and filter to exactly 48 hours
            now = datetime.now().timestamp() * 1000
            min_time = (now - (48 * 60 * 60 * 1000))  # 48 hours in milliseconds
            data = [
                {
                    "timestamp": int(row['time'] * 1000),
                    "open": float(row['open']),
                    "high": float(row['high']),
                    "low": float(row['low']),
                    "close": float(row['close'])
                }
                for _, row in df.iterrows() if int(row['time'] * 1000) >= min_time
            ]
            print(f"Returning {len(data)} data points after truncation to 48 hours")
            return {"data": data}
        except Exception as e:
            print(f"Historical data error: {str(e)}")
            return {"error": str(e)}, 500

previous_positions = set()
def price_update_task():
    while True:
        if mt5.terminal_info().connected:
            tick = mt5.symbol_info_tick(SYMBOL)
            if tick:
                print(f"Emitting price update at {datetime.now().isoformat()}: Symbol={SYMBOL}, Bid={tick.bid}, Ask={tick.ask}")
                socketio.emit('price_update', {
                    "symbol": SYMBOL,
                    "bid": float(tick.bid),
                    "ask": float(tick.ask),
                    "time": datetime.now().isoformat()
                })
            else:
                print(f"Failed to fetch tick data for {SYMBOL} at {datetime.now().isoformat()}: {mt5.last_error()}")
            positions = mt5.positions_get(symbol=SYMBOL)
            if positions:
                current_tickets = {pos.ticket for pos in positions}
                for ticket in list(previous_positions - current_tickets):
                    socketio.emit('position_update', {"ticket": ticket, "action": "close"})
                previous_positions = current_tickets
                for pos in positions:
                    pos_dict = pos._asdict()
                    entry_price = pos_dict['price_open']
                    current_price = tick.bid if pos_dict['type'] == mt5.POSITION_TYPE_BUY else tick.ask
                    volume = pos_dict['volume']
                    pip_value = 1.0
                    pl_pips = (current_price - entry_price) * 10 if pos_dict['type'] == mt5.POSITION_TYPE_BUY else (entry_price - current_price) * 10
                    pl = pl_pips * volume * pip_value * EXCHANGE_RATE
                    pos_dict['pl'] = float(pl)
                    socketio.emit('position_update', {
                        "ticket": pos.ticket,
                        "entry_price": float(entry_price),
                        "volume": float(volume),
                        "pl": float(pl),
                        "type": pos_dict['type'],
                        "action": "open" if pos.ticket not in previous_positions else "update"
                    })
        else:
            print(f"MT5 not connected at {datetime.now().isoformat()}")
        time.sleep(1)

# WebSocket handlers
@socketio.on('connect')
def handle_connect():
    user_id = request.args.get('user_id')
    if user_id != TELEGRAM_USER_ID:
        print(f"Unauthorized WebSocket connection: Expected user {TELEGRAM_USER_ID}, got {user_id}")
        return False
    print(f"WebSocket client connected: {user_id}")

@socketio.on('disconnect')
def handle_disconnect():
    print("WebSocket client disconnected")

# Start the price update task in a separate thread
price_thread = threading.Thread(target=price_update_task, daemon=True)
price_thread.start()

api.add_resource(PriceData, '/api/price')
api.add_resource(Trades, '/api/trades')
api.add_resource(Images, '/api/images')
api.add_resource(Positions, '/api/positions')
api.add_resource(Metrics, '/api/metrics')
api.add_resource(Indicators, '/api/indicators')
api.add_resource(HistoricalData, '/api/historical')

def find_available_port(host='0.0.0.0', start_port=5000, max_attempts=10):
    port = start_port
    for attempt in range(max_attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((host, port))
                return port
        except OSError as e:
            if e.errno == 10048:  # Port already in use
                port += 1
                print(f"Port {port-1} is in use, trying port {port}...")
            else:
                raise e
    raise Exception(f"Could not find an available port after {max_attempts} attempts")

if __name__ == '__main__':
    try:
        port = find_available_port()
        print(f"Starting server on port {port}...")
        socketio.run(app, host='0.0.0.0', port=port)
    except Exception as e:
        print(f"Failed to start server: {str(e)}")
        raise