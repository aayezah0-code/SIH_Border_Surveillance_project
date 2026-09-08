import asyncio
import logging
from typing import Optional
from fastapi import WebSocket

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    def set_event_loop(self, loop: asyncio.AbstractEventLoop):
        """Register the main running asyncio event loop."""
        self.loop = loop

    async def connect(self, websocket: WebSocket):
        if self.loop is None or not self.loop.is_running():
            self.loop = asyncio.get_running_loop()
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total clients: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WebSocket disconnected. Total clients: {len(self.active_connections)}")

    async def broadcast(self, message: str):
        """
        Send a text message to all connected WebSocket clients.
        Must be called from an async context.
        """
        for connection in list(self.active_connections):
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.error(f"Error sending message to client: {e}")
                self.disconnect(connection)

    def broadcast_from_thread(self, message: str):
        """
        Thread-safe broadcast helper to be called from background OS threads.
        Schedules the async broadcast coroutine onto the main running event loop.
        """
        target_loop = self.loop
        if target_loop is None or not target_loop.is_running():
            try:
                target_loop = asyncio.get_running_loop()
                self.loop = target_loop
            except RuntimeError:
                pass

        if target_loop is not None and target_loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(self.broadcast(message), target_loop)
            except Exception as exc:
                logger.error(f"Failed to dispatch broadcast from thread: {exc}")
        else:
            logger.warning("broadcast_from_thread called but main asyncio event loop is not registered or running.")

manager = ConnectionManager()
