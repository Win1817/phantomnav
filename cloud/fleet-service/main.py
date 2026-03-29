"""
PhantomNav™ — Fleet Service
UAV registry, health monitoring, and last-known-state tracking.

Routes:
  POST /fleet/drones/           — register drone
  GET  /fleet/drones/           — list all
  GET  /fleet/drones/{id}       — drone detail
  GET  /fleet/drones/{id}/health— health snapshot
  PUT  /fleet/drones/{id}/heartbeat — update heartbeat
"""

from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncpg
import asyncio
import aiomqtt
import json
import logging
import os
import time
import uuid
from typing import Optional, List, AsyncIterator
from pydantic import BaseModel
from enum import Enum

log = logging.getLogger("fleet-service")
logging.basicConfig(level=logging.INFO)

DB_DSN    = os.getenv("DATABASE_URL", "postgresql://phantom:phantom@localhost:5432/phantomnav")
MQTT_HOST = os.getenv("MQTT_HOST",    "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT","1883"))


class DroneStatus(str, Enum):
    ONLINE   = "ONLINE"
    OFFLINE  = "OFFLINE"
    WARNING  = "WARNING"
    CRITICAL = "CRITICAL"


class DroneRegister(BaseModel):
    drone_id: str
    name: str
    model: str = "Generic"
    capabilities: List[str] = []
    home_lat: float = 0.0
    home_lon: float = 0.0


class DroneHealth(BaseModel):
    drone_id: str
    status: DroneStatus
    last_seen: float
    confidence_score: Optional[float] = None
    confidence_level: Optional[str]  = None
    nav_mode: Optional[str]          = None
    gnss_available: bool             = False
    drift_m: Optional[float]         = None
    age_s: float                      = 0.0  # seconds since last telemetry


# ─────────────────────────────────────────────────────────────
# Database
# ─────────────────────────────────────────────────────────────
class FleetDB:
    STALE_THRESHOLD_S  = 30.0    # seconds before OFFLINE
    WARN_THRESHOLD_S   = 10.0    # seconds before WARNING

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    @classmethod
    async def create(cls, dsn: str) -> "FleetDB":
        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)
        db = cls(pool)
        await db._migrate()
        return db

    async def _migrate(self):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS drones (
                    id           TEXT PRIMARY KEY,
                    drone_id     TEXT UNIQUE NOT NULL,
                    name         TEXT NOT NULL,
                    model        TEXT,
                    capabilities JSONB DEFAULT '[]',
                    home_lat     FLOAT DEFAULT 0,
                    home_lon     FLOAT DEFAULT 0,
                    registered_at DOUBLE PRECISION NOT NULL,
                    last_seen     DOUBLE PRECISION,
                    last_confidence FLOAT,
                    last_nav_mode   TEXT,
                    last_gnss_ok    BOOLEAN DEFAULT FALSE,
                    last_drift_m    FLOAT
                );
            """)

    async def register(self, req: DroneRegister) -> dict:
        did = str(uuid.uuid4())
        async with self.pool.acquire() as conn:
            try:
                await conn.execute("""
                    INSERT INTO drones
                      (id, drone_id, name, model, capabilities,
                       home_lat, home_lon, registered_at)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                """,
                    did, req.drone_id, req.name, req.model,
                    json.dumps(req.capabilities),
                    req.home_lat, req.home_lon, time.time())
            except asyncpg.UniqueViolationError:
                raise HTTPException(409, f"Drone {req.drone_id} already exists")
        return {"id": did, "drone_id": req.drone_id}

    async def list_drones(self) -> List[dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM drones ORDER BY registered_at DESC")
            return [dict(r) for r in rows]

    async def get_drone(self, drone_id: str) -> Optional[dict]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM drones WHERE drone_id=$1", drone_id)
            return dict(row) if row else None

    async def update_heartbeat(self, drone_id: str, payload: dict):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE drones
                SET last_seen=$1,
                    last_confidence=$2,
                    last_nav_mode=$3,
                    last_gnss_ok=$4,
                    last_drift_m=$5
                WHERE drone_id=$6
            """,
                time.time(),
                payload.get('confidence'),
                payload.get('nav_mode'),
                payload.get('gnss_available', False),
                payload.get('drift_m'),
                drone_id
            )

    async def health(self, drone_id: str) -> DroneHealth:
        d = await self.get_drone(drone_id)
        if not d:
            raise HTTPException(404, f"Drone {drone_id} not found")

        now      = time.time()
        last     = d.get('last_seen') or 0.0
        age_s    = now - last

        if age_s > self.STALE_THRESHOLD_S:
            status = DroneStatus.OFFLINE
        elif age_s > self.WARN_THRESHOLD_S:
            status = DroneStatus.WARNING
        else:
            conf = d.get('last_confidence') or 100.0
            if conf < 20:
                status = DroneStatus.CRITICAL
            elif conf < 40:
                status = DroneStatus.WARNING
            else:
                status = DroneStatus.ONLINE

        return DroneHealth(
            drone_id=drone_id,
            status=status,
            last_seen=last,
            confidence_score=d.get('last_confidence'),
            nav_mode=d.get('last_nav_mode'),
            gnss_available=d.get('last_gnss_ok', False),
            drift_m=d.get('last_drift_m'),
            age_s=round(age_s, 1),
        )


# ─────────────────────────────────────────────────────────────
# MQTT watcher: auto-update heartbeats from telemetry stream
# ─────────────────────────────────────────────────────────────
async def mqtt_status_watcher(db: FleetDB):
    retry = 5
    while True:
        try:
            async with aiomqtt.Client(hostname=MQTT_HOST, port=MQTT_PORT) as client:
                log.info("Fleet MQTT watcher connected.")
                await client.subscribe("phantom/+/status")
                await client.subscribe("phantom/+/confidence")

                async for message in client.messages:
                    topic  = str(message.topic)
                    parts  = topic.split("/")
                    if len(parts) < 3:
                        continue
                    drone_id = parts[1]
                    msg_type = parts[2]

                    try:
                        payload = json.loads(message.payload.decode())
                        if msg_type in ("status", "confidence"):
                            await db.update_heartbeat(drone_id, {
                                'confidence':    payload.get('score'),
                                'nav_mode':      payload.get('nav_mode_name'),
                                'gnss_available':payload.get('gnss_available', False),
                            })
                    except Exception as e:
                        log.warning(f"Heartbeat update error: {e}")
        except Exception as e:
            log.error(f"Fleet MQTT error: {e}. Retry in {retry}s")
            await asyncio.sleep(retry)


# ─────────────────────────────────────────────────────────────
# FastAPI
# ─────────────────────────────────────────────────────────────
db_instance: Optional[FleetDB] = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global db_instance
    db_instance = await FleetDB.create(DB_DSN)
    task = asyncio.create_task(mqtt_status_watcher(db_instance))
    log.info("Fleet Service started.")
    yield
    task.cancel()
    await db_instance.pool.close()


app = FastAPI(title="PhantomNav Fleet Service",
              version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])


def get_db() -> FleetDB:
    if db_instance is None:
        raise RuntimeError("DB not initialized")
    return db_instance


@app.get("/health")
async def health():
    return {"status": "ok", "service": "fleet", "ts": time.time()}


@app.post("/fleet/drones/", status_code=201)
async def register_drone(req: DroneRegister, db: FleetDB = Depends(get_db)):
    return await db.register(req)


@app.get("/fleet/drones/")
async def list_drones(db: FleetDB = Depends(get_db)):
    return await db.list_drones()


@app.get("/fleet/drones/{drone_id}")
async def get_drone(drone_id: str, db: FleetDB = Depends(get_db)):
    d = await db.get_drone(drone_id)
    if not d:
        raise HTTPException(404, f"Drone {drone_id} not found")
    return d


@app.get("/fleet/drones/{drone_id}/health", response_model=DroneHealth)
async def drone_health(drone_id: str, db: FleetDB = Depends(get_db)):
    return await db.health(drone_id)


@app.put("/fleet/drones/{drone_id}/heartbeat")
async def manual_heartbeat(
    drone_id: str, payload: dict, db: FleetDB = Depends(get_db)):
    await db.update_heartbeat(drone_id, payload)
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8005")))
