"""
PhantomNav™ — Analytics Service
Analyzes drift patterns, confidence trends, and navigation performance.
Exposes computed metrics for dashboards and model training.

Routes:
  GET /analytics/{drone_id}/drift-summary
  GET /analytics/{drone_id}/confidence-trend
  GET /analytics/{drone_id}/gnss-events
  GET /analytics/fleet/summary
"""

from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncpg
import numpy as np
import logging
import os
import time
from typing import Optional, List, AsyncIterator
from pydantic import BaseModel

log = logging.getLogger("analytics-service")
logging.basicConfig(level=logging.INFO)

DB_DSN = os.getenv("DATABASE_URL",
                    "postgresql://phantom:phantom@localhost:5432/phantomnav")


# ─────────────────────────────────────────────────────────────
# Analytics Engine
# ─────────────────────────────────────────────────────────────
class AnalyticsEngine:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    @classmethod
    async def create(cls, dsn: str) -> "AnalyticsEngine":
        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)
        return cls(pool)

    # ── Drift analysis ─────────────────────────────────────────
    async def drift_summary(self, drone_id: str,
                            window_s: float = 3600) -> dict:
        """
        Summarize drift statistics over a sliding time window.
        Drift = displacement between pure INS and fused pose.
        """
        since = time.time() - window_s
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT ts, drift_m, w_ins, w_slam, gnss_valid
                FROM telemetry
                WHERE drone_id = $1 AND ts >= $2
                ORDER BY ts ASC
            """, drone_id, since)

        if not rows:
            return {"drone_id": drone_id, "status": "no_data",
                    "window_s": window_s}

        drifts    = np.array([r['drift_m'] for r in rows])
        w_slam    = np.array([r['w_slam']  for r in rows])
        gnss_ok   = np.array([r['gnss_valid'] for r in rows])

        # Detect drift events: drift exceeding 2 std above mean
        mean_d  = float(np.mean(drifts))
        std_d   = float(np.std(drifts))
        spikes  = int(np.sum(drifts > mean_d + 2.0 * std_d))

        # GNSS loss segments
        gnss_loss_segments = _count_segments(~gnss_ok)

        # Drift rate: linear regression slope (m/s)
        times = np.array([r['ts'] for r in rows])
        if len(times) > 2:
            slope = float(np.polyfit(times - times[0], drifts, 1)[0])
        else:
            slope = 0.0

        return {
            "drone_id":          drone_id,
            "window_s":          window_s,
            "sample_count":      len(rows),
            "drift_m": {
                "mean":  round(mean_d,  3),
                "std":   round(std_d,   3),
                "max":   round(float(np.max(drifts)),  3),
                "p95":   round(float(np.percentile(drifts, 95)), 3),
            },
            "drift_rate_m_per_s": round(slope, 5),
            "drift_spikes":       spikes,
            "gnss_loss_segments": gnss_loss_segments,
            "slam_usage": {
                "mean_weight":   round(float(np.mean(w_slam)), 3),
                "max_weight":    round(float(np.max(w_slam)),  3),
            },
            "computed_at": time.time(),
        }

    # ── Confidence trend ────────────────────────────────────────
    async def confidence_trend(
            self, drone_id: str,
            window_s: float = 3600,
            bucket_s: float = 60) -> dict:
        """
        Time-bucketed confidence statistics.
        """
        since = time.time() - window_s
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT ts, score, level
                FROM confidence
                WHERE drone_id = $1 AND ts >= $2
                ORDER BY ts ASC
            """, drone_id, since)

        if not rows:
            return {"drone_id": drone_id, "status": "no_data"}

        ts_arr    = np.array([r['ts'] for r in rows])
        sc_arr    = np.array([r['score'] for r in rows])
        levels    = [r['level'] for r in rows]

        # Level distribution
        from collections import Counter
        level_dist = dict(Counter(levels))

        # Bucketed trend
        t0      = ts_arr[0]
        buckets = []
        n_buckets = max(1, int(window_s / bucket_s))
        for i in range(n_buckets):
            lo = t0 + i * bucket_s
            hi = lo + bucket_s
            mask = (ts_arr >= lo) & (ts_arr < hi)
            if np.any(mask):
                sub = sc_arr[mask]
                buckets.append({
                    "t_start": round(lo, 1),
                    "mean":    round(float(np.mean(sub)), 2),
                    "min":     round(float(np.min(sub)),  2),
                })

        # Degradation events: confidence drops > 20 points in < 10 s
        deg_events = _count_rapid_drops(ts_arr, sc_arr, drop=20.0, window=10.0)

        return {
            "drone_id":          drone_id,
            "window_s":          window_s,
            "bucket_s":          bucket_s,
            "sample_count":      len(rows),
            "overall": {
                "mean":  round(float(np.mean(sc_arr)), 2),
                "min":   round(float(np.min(sc_arr)),  2),
                "p5":    round(float(np.percentile(sc_arr, 5)), 2),
            },
            "level_distribution": level_dist,
            "degradation_events": deg_events,
            "trend_buckets":      buckets,
            "computed_at":        time.time(),
        }

    # ── GNSS event log ─────────────────────────────────────────
    async def gnss_events(self, drone_id: str, limit: int = 50) -> dict:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT ts, code, message, confidence_at, nav_mode
                FROM alerts
                WHERE drone_id = $1
                  AND code IN ('GNSS_LOST', 'GNSS_RECOVERED')
                ORDER BY ts DESC LIMIT $2
            """, drone_id, limit)
        return {
            "drone_id": drone_id,
            "events":   [dict(r) for r in rows],
        }

    # ── Fleet summary ──────────────────────────────────────────
    async def fleet_summary(self) -> dict:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT DISTINCT ON (drone_id) drone_id,
                       ts, drift_m, gnss_valid, w_slam
                FROM telemetry
                ORDER BY drone_id, ts DESC
            """)
            conf_rows = await conn.fetch("""
                SELECT DISTINCT ON (drone_id) drone_id, score, level
                FROM confidence
                ORDER BY drone_id, ts DESC
            """)

        conf_map = {r['drone_id']: dict(r) for r in conf_rows}
        fleet = []
        for r in rows:
            d = dict(r)
            d['confidence'] = conf_map.get(r['drone_id'])
            fleet.append(d)

        return {"fleet": fleet, "drone_count": len(fleet),
                "computed_at": time.time()}


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
def _count_segments(mask: np.ndarray) -> int:
    """Count contiguous True segments in a boolean array."""
    if len(mask) == 0:
        return 0
    changes = np.diff(mask.astype(int))
    return int(np.sum(changes == 1)) + (1 if mask[0] else 0)


def _count_rapid_drops(ts: np.ndarray, scores: np.ndarray,
                        drop: float, window: float) -> int:
    count = 0
    for i in range(1, len(ts)):
        if ts[i] - ts[i-1] <= window and scores[i-1] - scores[i] >= drop:
            count += 1
    return count


# ─────────────────────────────────────────────────────────────
# FastAPI
# ─────────────────────────────────────────────────────────────
engine_instance: Optional[AnalyticsEngine] = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global engine_instance
    engine_instance = await AnalyticsEngine.create(DB_DSN)
    log.info("Analytics Service started.")
    yield
    await engine_instance.pool.close()


app = FastAPI(title="PhantomNav Analytics Service",
              version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])


def get_engine() -> AnalyticsEngine:
    if engine_instance is None:
        raise RuntimeError("Engine not initialized")
    return engine_instance


@app.get("/health")
async def health():
    return {"status": "ok", "service": "analytics", "ts": time.time()}


@app.get("/analytics/{drone_id}/drift-summary")
async def drift_summary(
    drone_id: str,
    window_s: float = Query(3600, ge=60),
    eng: AnalyticsEngine = Depends(get_engine),
):
    return await eng.drift_summary(drone_id, window_s)


@app.get("/analytics/{drone_id}/confidence-trend")
async def confidence_trend(
    drone_id: str,
    window_s: float  = Query(3600, ge=60),
    bucket_s: float  = Query(60,   ge=10),
    eng: AnalyticsEngine = Depends(get_engine),
):
    return await eng.confidence_trend(drone_id, window_s, bucket_s)


@app.get("/analytics/{drone_id}/gnss-events")
async def gnss_events(
    drone_id: str,
    limit: int = Query(50, ge=1, le=500),
    eng: AnalyticsEngine = Depends(get_engine),
):
    return await eng.gnss_events(drone_id, limit)


@app.get("/analytics/fleet/summary")
async def fleet_summary(eng: AnalyticsEngine = Depends(get_engine)):
    return await eng.fleet_summary()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8003")))
