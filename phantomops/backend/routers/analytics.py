"""PhantomOps™ — Analytics Router"""

from fastapi import APIRouter, HTTPException, Request, Depends, Query
import httpx
from routers.auth import require_operator

router = APIRouter()


async def _get(url: str, params: dict = None):
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, params=params, timeout=15)
            if resp.status_code >= 400:
                raise HTTPException(resp.status_code, resp.text)
            return resp.json()
        except httpx.RequestError as e:
            raise HTTPException(503, f"Analytics service unavailable: {e}")


@router.get("/{drone_id}/drift")
async def drift_summary(
    drone_id: str, request: Request,
    window_s: float = Query(3600, ge=60),
    _=Depends(require_operator),
):
    analytics_url = request.app.state.services["analytics"]
    return await _get(f"{analytics_url}/analytics/{drone_id}/drift-summary",
                      {"window_s": window_s})


@router.get("/{drone_id}/confidence-trend")
async def confidence_trend(
    drone_id: str, request: Request,
    window_s: float = Query(3600, ge=60),
    bucket_s: float = Query(60, ge=10),
    _=Depends(require_operator),
):
    analytics_url = request.app.state.services["analytics"]
    return await _get(f"{analytics_url}/analytics/{drone_id}/confidence-trend",
                      {"window_s": window_s, "bucket_s": bucket_s})


@router.get("/{drone_id}/gnss-events")
async def gnss_events(
    drone_id: str, request: Request,
    limit: int = Query(50),
    _=Depends(require_operator),
):
    analytics_url = request.app.state.services["analytics"]
    return await _get(f"{analytics_url}/analytics/{drone_id}/gnss-events",
                      {"limit": limit})


@router.get("/fleet/summary")
async def fleet_analytics(request: Request, _=Depends(require_operator)):
    analytics_url = request.app.state.services["analytics"]
    return await _get(f"{analytics_url}/analytics/fleet/summary")
