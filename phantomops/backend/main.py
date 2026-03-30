"""
PhantomOps™ — Ops Backend API
Aggregation, orchestration, and WebSocket gateway for the PhantomNav™ platform.

Architecture:
  MQTT → ingest → Redis pub/sub → WebSocket → UI
  UI   → REST  → proxy         → AKS services
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from contextlib import asynccontextmanager
import asyncio
import aiomqtt
import httpx
import json
import logging
import os
import time
from typing import Optional, AsyncIterator
from collections import defaultdict

from routers import fleet, telemetry, missions, analytics, auth, alerts
from ws_manager import ConnectionManager
from mqtt_bridge import MQTTBridge

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
log = logging.getLogger("phantomops")

# ─────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────
FLEET_SERVICE_URL     = os.getenv("FLEET_SERVICE_URL",     "http://localhost:8005")
TELEMETRY_SERVICE_URL = os.getenv("TELEMETRY_SERVICE_URL", "http://localhost:8001")
MISSION_SERVICE_URL   = os.getenv("MISSION_SERVICE_URL",   "http://localhost:8002")
ANALYTICS_SERVICE_URL = os.getenv("ANALYTICS_SERVICE_URL", "http://localhost:8003")
AUTH_SERVICE_URL      = os.getenv("AUTH_SERVICE_URL",      "http://localhost:8006")
MQTT_HOST             = os.getenv("MQTT_HOST",             "localhost")
MQTT_PORT             = int(os.getenv("MQTT_PORT",         "1883"))
OPS_PORT              = int(os.getenv("PORT",              "9000"))

# Global instances
ws_manager: Optional[ConnectionManager] = None
mqtt_bridge: Optional[MQTTBridge] = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global ws_manager, mqtt_bridge

    ws_manager = ConnectionManager()
    mqtt_bridge = MQTTBridge(
        host=MQTT_HOST,
        port=MQTT_PORT,
        ws_manager=ws_manager,
    )

    # Inject into app state for routers
    app.state.ws_manager = ws_manager
    app.state.mqtt_bridge = mqtt_bridge
    app.state.services = {
        "fleet":     FLEET_SERVICE_URL,
        "telemetry": TELEMETRY_SERVICE_URL,
        "mission":   MISSION_SERVICE_URL,
        "analytics": ANALYTICS_SERVICE_URL,
        "auth":      AUTH_SERVICE_URL,
    }

    # Start MQTT bridge in background
    mqtt_task = asyncio.create_task(mqtt_bridge.run())

    log.info("PhantomOps™ Backend started.")
    log.info(f"  Fleet:     {FLEET_SERVICE_URL}")
    log.info(f"  Telemetry: {TELEMETRY_SERVICE_URL}")
    log.info(f"  MQTT:      {MQTT_HOST}:{MQTT_PORT}")

    yield

    mqtt_task.cancel()
    try:
        await mqtt_task
    except asyncio.CancelledError:
        pass
    log.info("PhantomOps™ Backend stopped.")


app = FastAPI(
    title="PhantomOps™ Ops API",
    version="1.0.0",
    description="Real-time UAV command, monitoring, and analytics platform",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────────────────────
# Routers
# ─────────────────────────────────────────────────────────────
app.include_router(auth.router,      prefix="/api/auth",      tags=["auth"])
app.include_router(fleet.router,     prefix="/api/fleet",     tags=["fleet"])
app.include_router(telemetry.router, prefix="/api/telemetry", tags=["telemetry"])
app.include_router(missions.router,  prefix="/api/missions",  tags=["missions"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])
app.include_router(alerts.router,    prefix="/api/alerts",    tags=["alerts"])


# ─────────────────────────────────────────────────────────────
# WebSocket endpoint
# ─────────────────────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Main WebSocket endpoint. Clients subscribe to drone events here.
    Message format: { "type": "subscribe", "drones": ["drone-001", "*"] }
    """
    manager: ConnectionManager = app.state.ws_manager
    client_id = await manager.connect(websocket)
    log.info(f"WebSocket client connected: {client_id}")

    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                await manager.handle_client_message(client_id, msg)
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        manager.disconnect(client_id)
        log.info(f"WebSocket client disconnected: {client_id}")


# ─────────────────────────────────────────────────────────────
# Health + metrics
# ─────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    manager: ConnectionManager = app.state.ws_manager
    return {
        "status": "ok",
        "service": "phantomops",
        "ts": time.time(),
        "ws_connections": manager.connection_count(),
    }


@app.get("/metrics")
async def metrics():
    manager: ConnectionManager = app.state.ws_manager
    bridge: MQTTBridge = app.state.mqtt_bridge
    return {
        "ws_connections": manager.connection_count(),
        "mqtt_connected": bridge.connected,
        "messages_relayed": bridge.messages_relayed,
        "ts": time.time(),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=OPS_PORT, reload=False)
