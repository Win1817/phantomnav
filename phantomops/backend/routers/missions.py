"""PhantomOps™ — Missions Router"""

from fastapi import APIRouter, HTTPException, Request, Depends
import httpx
from routers.auth import require_operator

router = APIRouter()


async def _proxy(method: str, url: str, **kwargs):
    async with httpx.AsyncClient() as client:
        try:
            fn = getattr(client, method)
            resp = await fn(url, timeout=10, **kwargs)
            if resp.status_code >= 400:
                raise HTTPException(resp.status_code, resp.text)
            return resp.json()
        except httpx.RequestError as e:
            raise HTTPException(503, f"Mission service unavailable: {e}")


@router.post("/", status_code=201)
async def create_mission(body: dict, request: Request, _=Depends(require_operator)):
    mission_url = request.app.state.services["mission"]
    return await _proxy("post", f"{mission_url}/missions/", json=body)


@router.get("/{mission_id}")
async def get_mission(mission_id: str, request: Request, _=Depends(require_operator)):
    mission_url = request.app.state.services["mission"]
    return await _proxy("get", f"{mission_url}/missions/{mission_id}")


@router.put("/{mission_id}/activate")
async def activate_mission(mission_id: str, request: Request, _=Depends(require_operator)):
    mission_url = request.app.state.services["mission"]
    result = await _proxy("put", f"{mission_url}/missions/{mission_id}/activate")

    # Also push via MQTT for immediate delivery
    bridge = request.app.state.mqtt_bridge
    mission_data = await _proxy("get", f"{mission_url}/missions/{mission_id}")
    drone_id = mission_data.get("drone_id", "")
    if drone_id:
        await bridge.send_mission(drone_id, {
            "event": "MISSION_ACTIVATE",
            "mission_id": mission_id,
            "mission": mission_data,
        })

    return result


@router.put("/{mission_id}/abort")
async def abort_mission(mission_id: str, request: Request, _=Depends(require_operator)):
    mission_url = request.app.state.services["mission"]
    result = await _proxy("put", f"{mission_url}/missions/{mission_id}/abort")

    mission_data = await _proxy("get", f"{mission_url}/missions/{mission_id}")
    drone_id = mission_data.get("drone_id", "")
    bridge = request.app.state.mqtt_bridge
    if drone_id:
        await bridge.send_command(drone_id, {
            "event": "MISSION_ABORT",
            "mission_id": mission_id,
        })

    return result


@router.get("/drone/{drone_id}/active")
async def active_mission(drone_id: str, request: Request, _=Depends(require_operator)):
    mission_url = request.app.state.services["mission"]
    return await _proxy("get", f"{mission_url}/missions/drone/{drone_id}/active")


@router.post("/{drone_id}/command")
async def send_command(drone_id: str, body: dict, request: Request, _=Depends(require_operator)):
    """Send arbitrary command directly to drone via MQTT."""
    bridge = request.app.state.mqtt_bridge
    await bridge.send_command(drone_id, body)
    return {"ok": True, "drone_id": drone_id, "command": body}
