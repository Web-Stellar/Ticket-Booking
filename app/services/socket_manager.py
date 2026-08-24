from typing import Dict, List, Set
from fastapi import WebSocket

class WebSocketManager:
    """Manages active WebSocket connections per event for real-time visual seat map updates."""
    def __init__(self):
        # Maps event_id -> Set of active WebSockets
        self.active_connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, event_id: str):
        await websocket.accept()
        if event_id not in self.active_connections:
            self.active_connections[event_id] = set()
        self.active_connections[event_id].add(websocket)

    def disconnect(self, websocket: WebSocket, event_id: str):
        if event_id in self.active_connections:
            self.active_connections[event_id].discard(websocket)
            if not self.active_connections[event_id]:
                del self.active_connections[event_id]

    async def broadcast_seat_update(self, event_id: str, payload: dict):
        """Broadcasts updated seat statuses or waitlist notifications to all clients listening to an event."""
        if event_id in self.active_connections:
            disconnected = []
            for connection in list(self.active_connections[event_id]):
                try:
                    await connection.send_json(payload)
                except Exception:
                    disconnected.append(connection)
            for conn in disconnected:
                self.active_connections[event_id].discard(conn)

ws_manager = WebSocketManager()
