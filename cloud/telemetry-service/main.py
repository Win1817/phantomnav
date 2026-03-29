"""
PhantomNav™ — Telemetry Service
Ingests UAV telemetry via MQTT, persists to PostgreSQL,
and emits events to downstream consumers.

Routes:
  GET  /health
  GET  /telemetry/{drone_id}/latest
  GET  /telemetry/{drone_id}/history?limit=N&since=ts
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
from datetime import datetime, timezone
from typing import Optional, AsyncIterator
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("telemetry-service")

# ─────────────────────────────────────────────────────────────
# Config (environment variables with defaults)
# ─────────────────────────────────────────────────────────────
DB_DSN        = os.getenv("DATABASE_URL",  "postgresql://phantom:phantom@localhost:5432/phantomnav")
MQTT_HOST     = os.getenv("MQTT_HOST",     "localhost")
MQTT_PORT     = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER     = os.getenv("MQTT_USER",     "")
MQTT_PASS     = os.getenv("MQTT_PASS",     "")
SERVICE_PORT  = int(os.getenv("PORT",      "8001"))

# ─────────────────────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────────────────────
class PoseSnapshot(BaseModel):
    x: float; y: float; z: float
    qw: float; qx: float; qy: float; qz: float

class VelocitySnapshot(BaseModel):
    vx: float; vy: float; vz: float

class FusionMeta(BaseModel):
    w_ins: float; w_slam: float; drift_m: float

class TelemetryRecord(BaseModel):
    drone_id: str
    ts: float
    pose: PoseSnapshot
    velocity: VelocitySnapshot
    fusion: FusionMeta
    gnss_valid: bool
    received_at: Optional[datetime] = None

class ConfidenceRecord(BaseModel):
    drone_id: str
    ts: float
    score: float
    level: str
    sub_scores: dict

# ─────────────────────────────────────────────────────────────
# Database layer
# ─────────────────────────────────────────────────────────────
class TelemetryDB:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    @classmethod
    async def create(cls, dsn: str) -> "TelemetryDB":
        pool = await asyncpg.create_pool(dsn, min_size=2, max_size=10)
        db = cls(pool)
        await db._migrate()
        return db

    async def _migrate(self):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS telemetry (
                    id          BIGSERIAL PRIMARY KEY,
                    drone_id    TEXT NOT NULL,
                    ts          DOUBLE PRECISION NOT NULL,
                    received_at TIMESTAMPTZ DEFAULT NOW(),
                    x FLOAT, y FLOAT, z FLOAT,
                    qw FLOAT, qx FLOAT, qy FLOAT, qz FLOAT,
                    vx FLOAT, vy FLOAT, vz FLOAT,
                    w_ins FLOAT, w_slam FLOAT, drift_m FLOAT,
                    gnss_valid BOOLEAN
                );
                CREATE INDEX IF NOT EXISTS idx_tel_drone_ts
                    ON telemetry(drone_id, ts DESC);

                CREATE TABLE IF NOT EXISTS confidence (
                    id          BIGSERIAL PRIMARY KEY,
                    drone_id    TEXT NOT NULL,
                    ts          DOUBLE PRECISION NOT NULL,
                    received_at TIMESTAMPTZ DEFAULT NOW(),
                    score       FLOAT NOT NULL,
                    level       TEXT NOT NULL,
                    sub_scores  JSONB
                );
                CREATE INDEX IF NOT EXISTS idx_conf_drone_ts
                    ON confidence(drone_id, ts DESC);

                CREATE TABLE IF NOT EXISTS alerts (
                    id          BIGSERIAL PRIMARY KEY,
                    drone_id    TEXT NOT NULL,
                    ts          DOUBLE PRECISION NOT NULL,
                    received_at TIMESTAMPTZ DEFAULT NOW(),
                    severity    INT NOT NULL,
                    source      TEXT,
                    code        TEXT,
                    message     TEXT,
                    nav_mode    INT,
                    confidence_at FLOAT
                );
            """)
        log.info("Database schema ready.")

    async def insert_telemetry(self, r: TelemetryRecord):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO telemetry
                  (drone_id, ts, x, y, z, qw, qx, qy, qz,
                   vx, vy, vz, w_ins, w_slam, drift_m, gnss_valid)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)
            """,
                r.drone_id, r.ts,
                r.pose.x, r.pose.y, r.pose.z,
                r.pose.qw, r.pose.qx, r.pose.qy, r.pose.qz,
                r.velocity.vx, r.velocity.vy, r.velocity.vz,
                r.fusion.w_ins, r.fusion.w_slam, r.fusion.drift_m,
                r.gnss_valid
            )

    async def insert_confidence(self, r: ConfidenceRecord):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO confidence (drone_id, ts, score, level, sub_scores)
                VALUES ($1, $2, $3, $4, $5)
            """, r.drone_id, r.ts, r.score, r.level, json.dumps(r.sub_scores))

    async def insert_alert(self, payload: dict):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO alerts
                  (drone_id, ts, severity, source, code, message, nav_mode, confidence_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
            """,
                payload.get('drone_id'), payload.get('ts', time.time()),
                payload.get('severity', 0), payload.get('source', ''),
                payload.get('code', ''), payload.get('message', ''),
                payload.get('nav_mode'), payload.get('confidence'))

    async def latest_telemetry(self, drone_id: str) -> Optional[dict]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM telemetry
                WHERE drone_id = $1
                ORDER BY ts DESC LIMIT 1
            """, drone_id)
            return dict(row) if row else None

    async def history_telemetry(
            self, drone_id: str, limit: int, since: float) -> list[dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM telemetry
                WHERE drone_id = $1 AND ts >= $2
                ORDER BY ts DESC LIMIT $3
            """, drone_id, since, limit)
            return [dict(r) for r in rows]

    async def latest_confidence(self, drone_id: str) -> Optional[dict]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM confidence
                WHERE drone_id = $1
                ORDER BY ts DESC LIMIT 1
            """, drone_id)
            return dict(row) if row else None


# ─────────────────────────────────────────────────────────────
# MQTT ingestion loop
# ─────────────────────────────────────────────────────────────
async def mqtt_ingestion_loop(db: TelemetryDB):
    """Async MQTT subscriber — never blocks the FastAPI event loop."""
    retry_delay = 5
    while True:
        try:
            async with aiomqtt.Client(
                hostname=MQTT_HOST,
                port=MQTT_PORT,
                username=MQTT_USER or None,
                password=MQTT_PASS or None,
            ) as client:
                log.info(f"MQTT connected to {MQTT_HOST}:{MQTT_PORT}")
                await client.subscribe("phantom/+/telemetry")
                await client.subscribe("phantom/+/confidence")
                await client.subscribe("phantom/+/alerts")

                async for message in client.messages:
                    topic   = str(message.topic)
                    payload = json.loads(message.payload.decode())
                    parts   = topic.split("/")  # phantom/{id}/{type}

                    if len(parts) < 3:
                        continue
                    msg_type = parts[2]

                    try:
                        if msg_type == "telemetry":
                            rec = TelemetryRecord(**payload)
                            await db.insert_telemetry(rec)
                        elif msg_type == "confidence":
                            rec = ConfidenceRecord(**payload)
                            await db.insert_confidence(rec)
                        elif msg_type == "alerts":
                            await db.insert_alert(payload)
                    except Exception as e:
                        log.warning(f"Failed to persist {msg_type}: {e}")

        except Exception as e:
            log.error(f"MQTT error: {e}. Retrying in {retry_delay}s...")
            await asyncio.sleep(retry_delay)


# ─────────────────────────────────────────────────────────────
# FastAPI app
# ─────────────────────────────────────────────────────────────
db_instance: Optional[TelemetryDB] = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global db_instance
    db_instance = await TelemetryDB.create(DB_DSN)
    # Launch MQTT ingestion as background task
    task = asyncio.create_task(mqtt_ingestion_loop(db_instance))
    log.info("Telemetry Service started.")
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await db_instance.pool.close()


app = FastAPI(
    title="PhantomNav Telemetry Service",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db() -> TelemetryDB:
    if db_instance is None:
        raise RuntimeError("DB not initialized")
    return db_instance


@app.get("/health")
async def health():
    return {"status": "ok", "service": "telemetry", "ts": time.time()}


@app.get("/telemetry/{drone_id}/latest")
async def get_latest(drone_id: str, db: TelemetryDB = Depends(get_db)):
    rec = await db.latest_telemetry(drone_id)
    if not rec:
        raise HTTPException(404, f"No telemetry for drone: {drone_id}")
    return rec


@app.get("/telemetry/{drone_id}/history")
async def get_history(
    drone_id: str,
    limit: int = Query(100, ge=1, le=10000),
    since: float = Query(default_factory=lambda: time.time() - 3600),
    db: TelemetryDB = Depends(get_db),
):
    return await db.history_telemetry(drone_id, limit, since)


@app.get("/confidence/{drone_id}/latest")
async def get_confidence(drone_id: str, db: TelemetryDB = Depends(get_db)):
    rec = await db.latest_confidence(drone_id)
    if not rec:
        raise HTTPException(404, f"No confidence data for drone: {drone_id}")
    return rec


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=SERVICE_PORT)
