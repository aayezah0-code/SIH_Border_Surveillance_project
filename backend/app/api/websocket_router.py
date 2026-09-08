import logging
import json
from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.websockets.manager import manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["WebSockets"])

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # We don't expect much client->server data currently,
            # but we need to keep the connection open and read
            # so we detect disconnects.
            data = await websocket.receive_text()
            logger.debug(f"Received WS message: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@router.post("/ws/test-broadcast")
async def test_broadcast():
    """
    Development-only endpoint: sends a test alert event to all connected
    WebSocket clients so Phase 5 can be verified end-to-end without needing
    an uploaded video.  Remove or guard with env flag before production.
    """
    payload = json.dumps({
        "type": "alert",
        "data": {
            "alert_type": "Phase 5 Test Alert",
            "severity": "High",
            "time": datetime.now().strftime("%H:%M:%S"),
            "camera": "Test Harness",
            "description": "Real broadcast from the live uvicorn ConnectionManager.",
        },
    })
    await manager.broadcast(payload)
    return {
        "status": "broadcast_sent",
        "connected_clients": len(manager.active_connections),
        "payload": payload,
    }
