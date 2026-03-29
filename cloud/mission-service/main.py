"""
PhantomNav™ — Mission Service
Manages UAV flight plans, waypoints, and mission lifecycle.
Pushes mission updates to UAV via MQTT (async).

Routes:
  POST /missions/                — create mission
  GET  /missions/{id}           — get mission
  PUT  /missions/{id}/activate  — activate (push to UAV)
  PUT  /missions/{id}/abort     — abort active mission
  GET  /missions/drone/{drone_id}/active
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
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
from datetime import datetime
from typing import Optional, List, AsyncIterator
from pydantic import BaseModel, Field
from enum import Enum

log = logging.getLogger("mission-service")
logging.basicConfig(level=logging.INFO)

DB_DSN       = os.getenv("DATABASE_URL", "postgresql://phantom:phantom@localhost:5432/phantomnav")
MQTT_HOST    = os.getenv("MQTT_HOST",    "localhost")
MQTT_PORT    = int(os.getenv("MQTT_PORT","1883"))


# ─────────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────────
class MissionStatus(str, Enum):
    PLANNED   = "PLANNED"
    ACTIVE    = "ACTIVE"
    PAUSED    = "PAUSED"
    COMPLETED = "COMPLETED"
    ABORTED   = "ABORTED"


class Waypoint(BaseModel):
    seq: int
    x: float; y: float; z: float      # NED, meters from origin
    hold_time_s: float = 0.0
    action: Optional[str] = None       # e.g. "LAND", "PHOTO", "HOVER"


class MissionCreate(BaseModel):
    drone_id: str
    name: str
    description: Optional[str] = ""
    waypoints: List[Waypoint] = Field(min_length=1)
    max_speed_ms: float = 5.0
    return_home: bool = True
    gnss_required: bool = False        # Allow GNSS-denied missions


class Mission(MissionCreate):
    id: str
    status: MissionStatus = MissionStatus.PLANNED
    created_at: float
    activated_at: Optional[float] = None
    completed_at: Optional[float] = None


# ─────────────────────────────────────────────────────────────
# Database
# ─────────────────────────────────────────────────────────────
class MissionDB:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    @classmethod
    async def create(cls, dsn: str) -> "MissionDB":
        pool = await asyncpg.create_pool(dsn, min_size=2, max_size=5)
        db = cls(pool)
        await db._migrate()
        return db

    async def _migrate(self):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS missions (
                    id           TEXT PRIMARY KEY,
                    drone_id     TEXT NOT NULL,
                    name         TEXT NOT NULL,
                    description  TEXT,
                    status       TEXT NOT NULL DEFAULT 'PLANNED',
                    waypoints    JSONB NOT NULL,
                    max_speed_ms FLOAT DEFAULT 5.0,
                    return_home  BOOLEAN DEFAULT TRUE,
                    gnss_required BOOLEAN DEFAULT FALSE,
                    created_at   DOUBLE PRECISION NOT NULL,
                    activated_at DOUBLE PRECISION,
                    completed_at DOUBLE PRECISION
                );
                CREATE INDEX IF NOT EXISTS idx_missions_drone
                    ON missions(drone_id, status);
            """)

    async def insert(self, m: Mission) -> Mission:
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO missions
                  (id, drone_id, name, description, status,
                   waypoints, max_speed_ms, return_home, gnss_required, created_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
            """,
                m.id, m.drone_id, m.name, m.description, m.status.value,
                json.dumps([w.model_dump() for w in m.waypoints]),
                m.max_speed_ms, m.return_home, m.gnss_required, m.created_at
            )
        return m

    async def get(self, mission_id: str) -> Optional[dict]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM missions WHERE id = $1", mission_id)
            if not row:
                return None
            d = dict(row)
            d['waypoints'] = json.loads(d['waypoints'])
            return d

    async def update_status(self, mission_id: str,
                            status: MissionStatus,
                            timestamp_field: Optional[str] = None):
        async with self.pool.acquire() as conn:
            if timestamp_field:
                await conn.execute(f"""
                    UPDATE missions SET status=$1, {timestamp_field}=$2 WHERE id=$3
                """, status.value, time.time(), mission_id)
            else:
                await conn.execute(
                    "UPDATE missions SET status=$1 WHERE id=$2",
                    status.value, mission_id)

    async def active_for_drone(self, drone_id: str) -> Optional[dict]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM missions
                WHERE drone_id = $1 AND status = 'ACTIVE'
                ORDER BY activated_at DESC LIMIT 1
            """, drone_id)
            if not row:
                return None
            d = dict(row)
            d['waypoints'] = json.loads(d['waypoints'])
            return d


# ─────────────────────────────────────────────────────────────
# MQTT push to UAV
# ─────────────────────────────────────────────────────────────
async def push_mission_to_uav(drone_id: str, mission: dict):
    """Push mission payload to UAV via MQTT (QoS 1, retained)."""
    try:
        async with aiomqtt.Client(hostname=MQTT_HOST, port=MQTT_PORT) as client:
            payload = json.dumps({
                'event':    'MISSION_UPDATE',
                'ts':       time.time(),
                'mission':  mission,
            })
            topic = f"phantom/{drone_id}/mission"
            await client.publish(topic, payload, qos=1, retain=True)
            log.info(f"Mission pushed to {topic}")
    except Exception as e:
        log.error(f"Failed to push mission to UAV: {e}")


async def send_abort_command(drone_id: str, mission_id: str):
    """Send ABORT command to UAV."""
    try:
        async with aiomqtt.Client(hostname=MQTT_HOST, port=MQTT_PORT) as client:
            payload = json.dumps({
                'event':      'MISSION_ABORT',
                'mission_id': mission_id,
                'ts':         time.time(),
            })
            await client.publish(
                f"phantom/{drone_id}/command", payload, qos=1)
    except Exception as e:
        log.error(f"Failed to send abort: {e}")


# ─────────────────────────────────────────────────────────────
# FastAPI
# ─────────────────────────────────────────────────────────────
db_instance: Optional[MissionDB] = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global db_instance
    db_instance = await MissionDB.create(DB_DSN)
    log.info("Mission Service started.")
    yield
    await db_instance.pool.close()


app = FastAPI(title="PhantomNav Mission Service", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])


def get_db() -> MissionDB:
    if db_instance is None:
        raise RuntimeError("DB not initialized")
    return db_instance


@app.get("/health")
async def health():
    return {"status": "ok", "service": "mission", "ts": time.time()}


@app.post("/missions/", response_model=dict, status_code=201)
async def create_mission(
    body: MissionCreate,
    db: MissionDB = Depends(get_db)
):
    mission = Mission(
        id=str(uuid.uuid4()),
        created_at=time.time(),
        **body.model_dump()
    )
    await db.insert(mission)
    log.info(f"Mission created: {mission.id} for drone {mission.drone_id}")
    return {"id": mission.id, "status": mission.status}


@app.get("/missions/{mission_id}")
async def get_mission(mission_id: str, db: MissionDB = Depends(get_db)):
    m = await db.get(mission_id)
    if not m:
        raise HTTPException(404, f"Mission {mission_id} not found")
    return m


@app.put("/missions/{mission_id}/activate")
async def activate_mission(
    mission_id: str,
    background_tasks: BackgroundTasks,
    db: MissionDB = Depends(get_db),
):
    m = await db.get(mission_id)
    if not m:
        raise HTTPException(404, "Mission not found")
    if m['status'] not in (MissionStatus.PLANNED, MissionStatus.PAUSED):
        raise HTTPException(400, f"Cannot activate mission in status: {m['status']}")

    await db.update_status(mission_id, MissionStatus.ACTIVE, "activated_at")
    m['status'] = MissionStatus.ACTIVE
    background_tasks.add_task(push_mission_to_uav, m['drone_id'], m)
    return {"id": mission_id, "status": MissionStatus.ACTIVE}


@app.put("/missions/{mission_id}/abort")
async def abort_mission(
    mission_id: str,
    background_tasks: BackgroundTasks,
    db: MissionDB = Depends(get_db),
):
    m = await db.get(mission_id)
    if not m:
        raise HTTPException(404, "Mission not found")
    await db.update_status(mission_id, MissionStatus.ABORTED, "completed_at")
    background_tasks.add_task(send_abort_command, m['drone_id'], mission_id)
    return {"id": mission_id, "status": MissionStatus.ABORTED}


@app.get("/missions/drone/{drone_id}/active")
async def get_active_mission(drone_id: str, db: MissionDB = Depends(get_db)):
    m = await db.active_for_drone(drone_id)
    if not m:
        raise HTTPException(404, f"No active mission for drone: {drone_id}")
    return m


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8002")))
