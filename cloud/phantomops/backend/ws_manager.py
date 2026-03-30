"""
PhantomOps™ — WebSocket Connection Manager
Manages all active WebSocket connections and routes messages to subscribers.
"""

import asyncio
import json
import logging
import uuid
from typing import Dict, Set, Optional
from fastapi import WebSocket

log = logging.getLogger("phantomops.ws")


class ConnectionManager:
    """
    Manages WebSocket connections with subscription-based routing.
    Clients can subscribe to specific drone IDs or wildcard "*".
    """

    def __init__(self):
        # client_id → WebSocket
        self._connections: Dict[str, WebSocket] = {}
        # client_id → set of subscribed drone_ids ("*" = all)
        self._subscriptions: Dict[str, Set[str]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> str:
        await websocket.accept()
        client_id = str(uuid.uuid4())[:8]
        async with self._lock:
            self._connections[client_id] = websocket
            self._subscriptions[client_id] = {"*"}  # default: subscribe to all
        return client_id

    def disconnect(self, client_id: str):
        self._connections.pop(client_id, None)
        self._subscriptions.pop(client_id, None)

    async def handle_client_message(self, client_id: str, msg: dict):
        """Handle control messages from the UI client."""
        msg_type = msg.get("type")

        if msg_type == "subscribe":
            drones = msg.get("drones", ["*"])
            async with self._lock:
                self._subscriptions[client_id] = set(drones)
            log.debug(f"Client {client_id} subscribed to: {drones}")

        elif msg_type == "ping":
            ws = self._connections.get(client_id)
            if ws:
                await ws.send_text(json.dumps({"type": "pong", "ts": __import__("time").time()}))

    async def broadcast(self, drone_id: str, event_type: str, payload: dict):
        """
        Broadcast a message to all clients subscribed to this drone_id.
        Thread-safe; dead connections are pruned automatically.
        """
        message = json.dumps({
            "type":     event_type,
            "drone_id": drone_id,
            "ts":       __import__("time").time(),
            "data":     payload,
        })

        dead_clients = []
        for client_id, ws in list(self._connections.items()):
            subs = self._subscriptions.get(client_id, set())
            if "*" in subs or drone_id in subs:
                try:
                    await ws.send_text(message)
                except Exception:
                    dead_clients.append(client_id)

        for cid in dead_clients:
            self.disconnect(cid)

    async def send_system(self, event_type: str, payload: dict):
        """Broadcast a system-level message to all connected clients."""
        message = json.dumps({
            "type": event_type,
            "ts":   __import__("time").time(),
            "data": payload,
        })
        dead_clients = []
        for client_id, ws in list(self._connections.items()):
            try:
                await ws.send_text(message)
            except Exception:
                dead_clients.append(client_id)
        for cid in dead_clients:
            self.disconnect(cid)

    def connection_count(self) -> int:
        return len(self._connections)
