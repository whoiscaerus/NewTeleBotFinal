import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.app.core.websockets import manager

router = APIRouter()
logger = logging.getLogger(__name__)


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time updates.
    Clients connect to /ws (or /api/v1/ws if mounted there).
    """
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive and listen for client messages (e.g. pings)
            data = await websocket.receive_text()
            # We can handle client messages here if needed
            # For now, we just echo or ignore
            await websocket.send_text(f"Message received: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)
