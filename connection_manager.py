from fastapi import WebSocket

import models


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[dict] = []

    async def connect(self, websocket: WebSocket, user: models.User):
        await websocket.accept()
        self.active_connections.append({"websocket": websocket, "user": user})

    def disconnect(self, websocket: WebSocket):
        self.active_connections = [
            conn for conn in self.active_connections if conn["websocket"] is not websocket
        ]

    async def broadcast(self, message: dict):
        stale = []
        for conn in self.active_connections:
            user = conn["user"]
            target_barangay = message.get("barangay_id")
            if (
                user.role == "city_admin"
                or target_barangay is None
                or target_barangay == user.barangay_id
            ):
                try:
                    await conn["websocket"].send_json(message)
                except Exception:
                    stale.append(conn["websocket"])
        for ws in stale:
            self.disconnect(ws)


manager = ConnectionManager()
