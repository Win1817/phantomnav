"""PhantomOps™ — Telemetry Router"""

from fastapi import APIRouter, HTTPException, Request, Depends, Query
import httpx
from mqtt_bridge import get_drone_state
from routers.auth import require_operator

router = APIRouter()


@router.get("/{drone_id}/latest")
async def latest_telemetry(drone_id: str, request: Request, _=Depends(require_operator)):
    """Return latest telemetry — prefers live MQTT cache, falls back to service."""
    live = get_drone_state(drone_id)
    if live and live.get("telemetry"):
        return {"source": "live", "data": live["telemetry"], "confidence": live.get("confidence")}

    tel_url = request.app.state.services["telemetry"]
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{tel_url}/telemetry/{drone_id}/latest", timeout=5)
            if resp.status_code == 200:
                return {"source": "db", "data": resp.json()}
            raise HTTPException(404, "No telemetry found")
        except httpx.RequestError as e:
            raise HTTPException(503, f"Telemetry service unavailable: {e}")


@router.get("/{drone_id}/history")
async def telemetry_history(
    drone_id: str,
    request: Request,
    limit: int = Query(200, ge=1, le=5000),
    since: float = Query(None),
    _=Depends(require_operator),
):
    tel_url = request.app.state.services["telemetry"]
    params = {"limit": limit}
    if since:
        params["since"] = since
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                f"{tel_url}/telemetry/{drone_id}/history", params=params, timeout=10)
            return resp.json()
        except httpx.RequestError as e:
            raise HTTPException(503, f"Telemetry service unavailable: {e}")


@router.get("/{drone_id}/confidence")
async def latest_confidence(drone_id: str, request: Request, _=Depends(require_operator)):
    live = get_drone_state(drone_id)
    if live and live.get("confidence") is not None:
        return {
            "source":     "live",
            "drone_id":   drone_id,
            "score":      live.get("confidence"),
            "level":      live.get("conf_level"),
            "sub_scores": live.get("sub_scores", {}),
        }

    tel_url = request.app.state.services["telemetry"]
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{tel_url}/confidence/{drone_id}/latest", timeout=5)
            return resp.json()
        except httpx.RequestError as e:
            raise HTTPException(503, f"Telemetry service unavailable: {e}")
