"""
PhantomNav™ — Auth Service
Handles device registration, JWT issuance, and token validation.
All other services validate tokens against this service.

Routes:
  POST /auth/device/register   — register UAV device
  POST /auth/token             — issue JWT
  POST /auth/token/validate    — validate token (used by other services)
  GET  /auth/device/{id}       — device info
  DELETE /auth/device/{id}     — revoke device
"""

from fastapi import FastAPI, HTTPException, Depends, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from contextlib import asynccontextmanager
import asyncpg
import jwt as pyjwt
import bcrypt
import os
import time
import uuid
import logging
from typing import Optional, AsyncIterator
from pydantic import BaseModel

log = logging.getLogger("auth-service")
logging.basicConfig(level=logging.INFO)

DB_DSN     = os.getenv("DATABASE_URL", "postgresql://phantom:phantom@localhost:5432/phantomnav")
JWT_SECRET = os.getenv("JWT_SECRET",   "CHANGE_ME_IN_PRODUCTION_USE_256BIT_KEY")
JWT_ALG    = "HS256"
TOKEN_TTL  = int(os.getenv("TOKEN_TTL_S", "86400"))   # 24 hours default
bearer     = HTTPBearer(auto_error=False)


# ─────────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────────
class DeviceRegister(BaseModel):
    drone_id: str
    name: str
    secret: str       # Pre-shared secret (bcrypt-hashed at rest)
    capabilities: list[str] = []

class TokenRequest(BaseModel):
    drone_id: str
    secret: str

class TokenValidateRequest(BaseModel):
    token: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: float
    drone_id: str


# ─────────────────────────────────────────────────────────────
# Database
# ─────────────────────────────────────────────────────────────
class AuthDB:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    @classmethod
    async def create(cls, dsn: str) -> "AuthDB":
        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)
        db = cls(pool)
        await db._migrate()
        return db

    async def _migrate(self):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS devices (
                    id            TEXT PRIMARY KEY,
                    drone_id      TEXT UNIQUE NOT NULL,
                    name          TEXT NOT NULL,
                    secret_hash   BYTEA NOT NULL,
                    capabilities  JSONB DEFAULT '[]',
                    active        BOOLEAN DEFAULT TRUE,
                    created_at    DOUBLE PRECISION NOT NULL,
                    last_token_at DOUBLE PRECISION
                );

                CREATE TABLE IF NOT EXISTS revoked_tokens (
                    jti        TEXT PRIMARY KEY,
                    revoked_at DOUBLE PRECISION NOT NULL
                );
            """)
        log.info("Auth schema ready.")

    async def register(self, req: DeviceRegister) -> dict:
        secret_hash = bcrypt.hashpw(req.secret.encode(), bcrypt.gensalt())
        device_id   = str(uuid.uuid4())
        async with self.pool.acquire() as conn:
            try:
                await conn.execute("""
                    INSERT INTO devices
                      (id, drone_id, name, secret_hash, capabilities, created_at)
                    VALUES ($1,$2,$3,$4,$5,$6)
                """,
                    device_id, req.drone_id, req.name,
                    secret_hash,
                    str(req.capabilities),
                    time.time()
                )
            except asyncpg.UniqueViolationError:
                raise HTTPException(409,
                    f"Device {req.drone_id} already registered.")
        return {"id": device_id, "drone_id": req.drone_id}

    async def get_device(self, drone_id: str) -> Optional[dict]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM devices WHERE drone_id=$1 AND active=TRUE",
                drone_id)
            return dict(row) if row else None

    async def verify_secret(self, drone_id: str, secret: str) -> bool:
        device = await self.get_device(drone_id)
        if not device:
            return False
        return bcrypt.checkpw(secret.encode(), device['secret_hash'])

    async def stamp_token(self, drone_id: str):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE devices SET last_token_at=$1 WHERE drone_id=$2",
                time.time(), drone_id)

    async def revoke_device(self, drone_id: str):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE devices SET active=FALSE WHERE drone_id=$1", drone_id)

    async def is_token_revoked(self, jti: str) -> bool:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT 1 FROM revoked_tokens WHERE jti=$1", jti)
            return row is not None


# ─────────────────────────────────────────────────────────────
# JWT helpers
# ─────────────────────────────────────────────────────────────
def issue_token(drone_id: str, device_id: str) -> TokenResponse:
    now     = int(time.time())
    exp     = now + TOKEN_TTL
    jti     = str(uuid.uuid4())
    payload = {
        "sub":      drone_id,
        "device_id": device_id,
        "iat":      now,
        "exp":      exp,
        "jti":      jti,
        "type":     "device",
    }
    token = pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)
    return TokenResponse(access_token=token, expires_at=exp, drone_id=drone_id)


def decode_token(token: str) -> dict:
    try:
        return pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except pyjwt.InvalidTokenError as e:
        raise HTTPException(401, f"Invalid token: {e}")


# ─────────────────────────────────────────────────────────────
# FastAPI
# ─────────────────────────────────────────────────────────────
db_instance: Optional[AuthDB] = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global db_instance
    db_instance = await AuthDB.create(DB_DSN)
    log.info("Auth Service started.")
    yield
    await db_instance.pool.close()


app = FastAPI(title="PhantomNav Auth Service",
              version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])


def get_db() -> AuthDB:
    if db_instance is None:
        raise RuntimeError("DB not initialized")
    return db_instance


async def require_admin(
    creds: Optional[HTTPAuthorizationCredentials] = Security(bearer)
) -> dict:
    """Admin-level auth for management endpoints."""
    if not creds:
        raise HTTPException(401, "Authorization required")
    payload = decode_token(creds.credentials)
    if payload.get("type") != "admin":
        raise HTTPException(403, "Admin token required")
    return payload


@app.get("/health")
async def health():
    return {"status": "ok", "service": "auth", "ts": time.time()}


@app.post("/auth/device/register", status_code=201)
async def register_device(
    req: DeviceRegister,
    db: AuthDB = Depends(get_db),
):
    result = await db.register(req)
    log.info(f"Device registered: {req.drone_id}")
    return result


@app.post("/auth/token", response_model=TokenResponse)
async def issue_device_token(
    req: TokenRequest,
    db: AuthDB = Depends(get_db),
):
    verified = await db.verify_secret(req.drone_id, req.secret)
    if not verified:
        raise HTTPException(401, "Invalid drone_id or secret")

    device = await db.get_device(req.drone_id)
    token  = issue_token(req.drone_id, device['id'])
    await db.stamp_token(req.drone_id)
    log.info(f"Token issued for {req.drone_id}")
    return token


@app.post("/auth/token/validate")
async def validate_token(
    req: TokenValidateRequest,
    db: AuthDB = Depends(get_db),
):
    payload = decode_token(req.token)
    jti     = payload.get("jti", "")
    revoked = await db.is_token_revoked(jti)
    if revoked:
        raise HTTPException(401, "Token revoked")
    return {
        "valid":    True,
        "drone_id": payload.get("sub"),
        "exp":      payload.get("exp"),
    }


@app.get("/auth/device/{drone_id}")
async def get_device(drone_id: str, db: AuthDB = Depends(get_db)):
    device = await db.get_device(drone_id)
    if not device:
        raise HTTPException(404, "Device not found")
    safe = dict(device)
    safe.pop("secret_hash", None)
    return safe


@app.delete("/auth/device/{drone_id}", status_code=204)
async def revoke_device(drone_id: str, db: AuthDB = Depends(get_db)):
    await db.revoke_device(drone_id)
    log.info(f"Device revoked: {drone_id}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8006")))
