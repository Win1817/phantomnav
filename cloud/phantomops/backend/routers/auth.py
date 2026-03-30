"""PhantomOps™ — Auth Router (proxies to auth-service)"""

from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import httpx
import jwt as pyjwt
import os
import time

router = APIRouter()
bearer = HTTPBearer(auto_error=False)

JWT_SECRET = os.getenv("JWT_SECRET", "CHANGE_ME_IN_PRODUCTION_USE_256BIT_KEY")
JWT_ALG    = "HS256"


def decode_token(token: str) -> dict:
    try:
        return pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except pyjwt.InvalidTokenError as e:
        raise HTTPException(401, f"Invalid token: {e}")


async def require_operator(
    creds: HTTPAuthorizationCredentials = Depends(bearer)
) -> dict:
    if not creds:
        raise HTTPException(401, "Authorization required")
    return decode_token(creds.credentials)


async def require_admin(
    creds: HTTPAuthorizationCredentials = Depends(bearer)
) -> dict:
    payload = await require_operator(creds)
    if payload.get("role") not in ("admin",):
        raise HTTPException(403, "Admin role required")
    return payload


@router.post("/login")
async def ops_login(body: dict, request: Request):
    """Proxy login to auth-service and return JWT."""
    auth_url = request.app.state.services["auth"]
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(f"{auth_url}/auth/token", json=body, timeout=10)
            return resp.json()
        except httpx.RequestError as e:
            raise HTTPException(503, f"Auth service unavailable: {e}")


@router.post("/validate")
async def validate_token(body: dict, request: Request):
    """Validate a JWT token."""
    token = body.get("token", "")
    payload = decode_token(token)
    return {"valid": True, "payload": payload}


@router.get("/me")
async def me(payload: dict = Depends(require_operator)):
    return payload
