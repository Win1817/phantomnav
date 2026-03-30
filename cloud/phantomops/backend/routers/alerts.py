"""PhantomOps™ — Alerts Router (serves from telemetry-service alerts table)"""

from fastapi import APIRouter, HTTPException, Request, Depends, Query
import httpx
from routers.auth import require_operator

router = APIRouter()


@router.get("/{drone_id}")
async def get_alerts(
    drone_id: str, request: Request,
    limit: int = Query(50, ge=1, le=500),
    _=Depends(require_operator),
):
    tel_url = request.app.state.services["telemetry"]
    async with httpx.AsyncClient() as client:
        try:
            # The telemetry service stores alerts; we query via analytics gnss-events
            # plus a general alerts endpoint if available
            analytics_url = request.app.state.services["analytics"]
            resp = await client.get(
                f"{analytics_url}/analytics/{drone_id}/gnss-events",
                params={"limit": limit}, timeout=10)
            return resp.json()
        except httpx.RequestError as e:
            raise HTTPException(503, f"Service unavailable: {e}")
