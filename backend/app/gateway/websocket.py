"""
PR-083: FastAPI WebSocket Replacement for SocketIO

Replaces Flask-SocketIO with FastAPI WebSocket for real-time market updates.

Legacy SocketIO Events:
- connect: Client connects with ?user_id= auth
- disconnect: Client disconnects
- price_update: Server sends price changes every 1 second
- position_update: Server sends position changes every 1 second

New WebSocket Events:
- Connection: ws://host/ws/market?user_id=<id>
- Message format: {"type": "price"|"position", ...}
"""

import asyncio
import logging
from datetime import datetime

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from backend.app.core.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# Track active WebSocket connections
active_connections: set[WebSocket] = set()

# Track previous position tickets for detecting closes
previous_positions: set[int] = set()


@router.websocket("/ws/market")
async def market_websocket(
    websocket: WebSocket,
    user_id: str = Query(...),
):
    """
    Real-time market data WebSocket.

    Replaces legacy Flask-SocketIO with FastAPI WebSocket.

    Auth:
        Query param: ?user_id=<telegram_user_id>

    Events sent to client:
        1. Price updates (every 1 second):
           {
               "type": "price",
               "symbol": "XAUUSD",
               "bid": 1950.50,
               "ask": 1950.75,
               "time": "2025-01-01T12:00:00"
           }

        2. Position updates (every 1 second):
           {
               "type": "position",
               "ticket": 12345,
               "action": "open"|"update"|"close",
               "entry_price": 1950.50,
               "volume": 0.1,
               "pl": 45.00,
               "type": 0  # 0=buy, 1=sell
           }

    Example client (JavaScript):
        const ws = new WebSocket('ws://localhost:8000/ws/market?user_id=123');
        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.type === 'price') {
                console.log(`Bid: ${data.bid}, Ask: ${data.ask}`);
            } else if (data.type === 'position') {
                console.log(`Position ${data.ticket}: ${data.action}, P&L: ${data.pl}`);
            }
        };
    """
    # Auth validation
    if user_id != settings.gateway.telegram_user_id:
        logger.warning(f"Unauthorized WebSocket connection attempt: {user_id}")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Accept connection
    await websocket.accept()
    active_connections.add(websocket)
    logger.info(f"WebSocket connected: {user_id}")

    try:
        # Start background tasks for price and position updates
        await asyncio.gather(
            send_price_updates(websocket),
            send_position_updates(websocket),
        )
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {user_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
    finally:
        active_connections.discard(websocket)


async def send_price_updates(websocket: WebSocket):
    """
    Send real-time price updates every 1 second.

    Replaces legacy Flask SocketIO price_update_task().

    Legacy:
        socketio.emit('price_update', {
            "symbol": SYMBOL,
            "bid": tick.bid,
            "ask": tick.ask,
            "time": datetime.now().isoformat()
        })

    New:
        await websocket.send_json({
            "type": "price",
            "symbol": SYMBOL,
            "bid": tick.bid,
            "ask": tick.ask,
            "time": datetime.now().isoformat()
        })
    """
    # Import MT5 async wrapper (to be implemented in separate PR)
    # For now, mock the MT5 connection
    # TODO: Replace with real MT5 async calls when PR-XXX (MT5 async) is implemented

    symbol = settings.gateway.trading_symbol  # e.g., "XAUUSD"

    while True:
        try:
            # Mock MT5 tick data (replace with real MT5 call)
            # tick = await mt5_async.symbol_info_tick(symbol)

            # Simulated price data
            # In production: Use real MT5 data
            tick_data = {
                "type": "price",
                "symbol": symbol,
                "bid": 1950.50,  # Mock bid price
                "ask": 1950.75,  # Mock ask price
                "time": datetime.now().isoformat(),
            }

            await websocket.send_json(tick_data)
            # logger.debug(f"Sent price update: {tick_data}")  # Commented to reduce log spam

        except WebSocketDisconnect:
            raise  # Propagate disconnect
        except Exception as e:
            logger.error(f"Price update error: {e}", exc_info=True)
            # Don't raise - continue sending updates

        await asyncio.sleep(1)


async def send_position_updates(websocket: WebSocket):
    """
    Send real-time position updates every 1 second.

    Replaces legacy Flask SocketIO position tracking.

    Legacy:
        # Track closed positions
        previous_positions = {pos.ticket for pos in positions}
        current_positions = {pos.ticket for pos in mt5.positions_get()}

        # Emit close events
        for ticket in previous_positions - current_positions:
            socketio.emit('position_update', {"ticket": ticket, "action": "close"})

        # Emit open/update events
        for pos in positions:
            action = "open" if pos.ticket not in previous_positions else "update"
            socketio.emit('position_update', {
                "ticket": pos.ticket,
                "entry_price": pos.price_open,
                "volume": pos.volume,
                "pl": calculated_pl,
                "type": pos.type,
                "action": action
            })

    New:
        Same logic, but with async/await and WebSocket send_json()
    """
    global previous_positions

    while True:
        try:
            # Mock MT5 positions (replace with real MT5 call)
            # positions = await mt5_async.positions_get(symbol=symbol)

            # Simulated positions (replace with real MT5 data)
            positions = []  # Mock: no positions

            current_tickets = {pos["ticket"] for pos in positions}

            # Detect closed positions
            for ticket in previous_positions - current_tickets:
                await websocket.send_json(
                    {
                        "type": "position",
                        "ticket": ticket,
                        "action": "close",
                    }
                )
                # logger.debug(f"Sent position close: {ticket}")  # Commented to reduce log spam

            # Send open/update events
            for pos in positions:
                action = "open" if pos["ticket"] not in previous_positions else "update"

                # Calculate P&L (same formula as legacy)
                entry_price = pos["price_open"]
                current_price = pos["current_price"]
                volume = pos["volume"]
                position_type = pos["type"]  # 0=buy, 1=sell

                if position_type == 0:  # Buy
                    pl_pips = (current_price - entry_price) * 10
                else:  # Sell
                    pl_pips = (entry_price - current_price) * 10

                pip_value = 1.0
                exchange_rate = settings.gateway.exchange_rate  # e.g., 1.27 for GBP/USD
                pl = pl_pips * volume * pip_value * exchange_rate

                await websocket.send_json(
                    {
                        "type": "position",
                        "ticket": pos["ticket"],
                        "action": action,
                        "entry_price": float(entry_price),
                        "volume": float(volume),
                        "pl": float(pl),
                        "position_type": position_type,
                    }
                )
                # logger.debug(f"Sent position {action}: {pos['ticket']}")  # Commented to reduce log spam

            # Update previous positions
            previous_positions = current_tickets

        except WebSocketDisconnect:
            raise  # Propagate disconnect
        except Exception as e:
            logger.error(f"Position update error: {e}", exc_info=True)
            # Don't raise - continue sending updates

        await asyncio.sleep(1)


async def broadcast_message(message: dict):
    """
    Broadcast message to all connected WebSocket clients.

    Args:
        message: JSON-serializable message to broadcast

    Example:
        await broadcast_message({
            "type": "system",
            "message": "Market closed"
        })
    """
    disconnected = set()

    for connection in active_connections:
        try:
            await connection.send_json(message)
        except Exception as e:
            logger.error(f"Broadcast failed: {e}")
            disconnected.add(connection)

    # Remove disconnected clients
    active_connections.difference_update(disconnected)
