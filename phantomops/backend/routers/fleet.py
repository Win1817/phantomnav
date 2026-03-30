"""PhantomOps™ — Fleet Router"""

from fastapi import APIRouter, HTTPException, Request, Depends
import httpx
import time
from mqtt_bridge import get_drone_cache, get_drone_state
from routers.auth import require_operator

router = APIRouter()


@router.get("/drones")
async def list_drones(request: Request, _=Depends(require_operator)):
    """List all drones — merges fleet-service data with live MQTT cache."""
    fleet_url = request.app.state.services["fleet"]
    cache = get_drone_cache()

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{fleet_url}/fleet/drones/", timeout=5)
            fleet_data = resp.json() if resp.status_code == 200 else []
    except Exception:
        fleet_data = []

    # Merge fleet registry with live state
    result = []
    seen_ids = set()
    for drone in fleet_data:
        did = drone.get("drone_id")
        seen_ids.add(did)
        live = cache.get(did, {})
        result.append({
            **drone,
            "live": {
                "confidence":  live.get("confidence"),
                "conf_level":  live.get("conf_level"),
                "nav_mode":    live.get("nav_mode"),
                "gnss_valid":  live.get("gnss_valid"),
                "last_seen":   live.get("last_seen"),
                "telemetry":   live.get("telemetry"),
            }
        })

    # Add drones seen on MQTT but not in fleet registry
    for did, live in cache.items():
        if did not in seen_ids:
            result.append({
                "drone_id": did,
                "name": did,
                "model": "Unknown",
                "registered_at": live.get("first_seen"),
                "live": {
                    "confidence": live.get("confidence"),
                    "conf_level": live.get("conf_level"),
                    "nav_mode":   live.get("nav_mode"),
                    "gnss_valid": live.get("gnss_valid"),
                    "last_seen":  live.get("last_seen"),
                    "telemetry":  live.get("telemetry"),
                }
            })

    return result


@router.get("/drones/{drone_id}")
async def get_drone(drone_id: str, request: Request, _=Depends(require_operator)):
    fleet_url = request.app.state.services["fleet"]
    cache = get_drone_state(drone_id) or {}

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{fleet_url}/fleet/drones/{drone_id}", timeout=5)
            fleet_data = resp.json() if resp.status_code == 200 else {}
    except Exception:
        fleet_data = {}

    return {**fleet_data, "live": cache}


@router.get("/drones/{drone_id}/health")
async def drone_health(drone_id: str, request: Request, _=Depends(require_operator)):
    fleet_url = request.app.state.services["fleet"]
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{fleet_url}/fleet/drones/{drone_id}/health", timeout=5)
            return resp.json()
        except Exception as e:
            raise HTTPException(503, f"Fleet service unavailable: {e}")


@router.get("/summary")
async def fleet_summary(request: Request, _=Depends(require_operator)):
    """Fast in-memory fleet summary — no service call needed."""
    cache = get_drone_cache()
    now = time.time()
    summary = []
    for drone_id, state in cache.items():
        age = now - state.get("last_seen", 0)
        conf = state.get("confidence", 0) or 0
        if age > 30:
            status = "offline"
        elif conf < 20:
            status = "critical"
        elif conf < 40:
            status = "warning"
        else:
            status = "active"

        pos = {}
        tel = state.get("telemetry", {})
        if tel and "pose" in tel:
            pos = tel["pose"]

        summary.append({
            "drone_id":   drone_id,
            "status":     status,
            "confidence": conf,
            "conf_level": state.get("conf_level", ""),
            "nav_mode":   state.get("nav_mode", ""),
            "gnss_valid": state.get("gnss_valid", False),
            "last_seen":  state.get("last_seen"),
            "age_s":      round(age, 1),
            "position":   pos,
        })

    return {
        "drones":      summary,
        "total":       len(summary),
        "active":      sum(1 for d in summary if d["status"] == "active"),
        "warning":     sum(1 for d in summary if d["status"] == "warning"),
        "critical":    sum(1 for d in summary if d["status"] == "critical"),
        "offline":     sum(1 for d in summary if d["status"] == "offline"),
        "computed_at": now,
    }
