# PhantomOps™

**Real-Time UAV Command, Monitoring & Analytics Platform**  
*Integrated with PhantomNav™ edge stack and Azure AKS cloud services*

---

## Architecture

```
[ PhantomNav™ UAV Edge ]
         │
         ▼ MQTT (phantom/{id}/*)
[ PhantomOps™ Backend ]  ←─ aggregates AKS microservices
         │
         ▼ WebSocket (/ws)
[ PhantomOps™ Frontend ] ← React + TypeScript UI
```

## Stack

| Layer | Tech |
|---|---|
| **Frontend** | React 18 + TypeScript + Vite + Recharts |
| **State**    | Zustand (real-time store) |
| **Backend**  | FastAPI + asyncio + aiomqtt |
| **Real-time**| WebSocket (persistent, auto-reconnect) |
| **Infra**    | Docker Compose → Azure AKS |

## Features

### Fleet Dashboard
- Live drone blips on tactical radar display
- Status indicators: Active / Warning / Critical / Offline
- Confidence score bar per drone
- GNSS validity indicator

### UAV Detail View
- Live confidence gauge (0–100) with SVG arc
- Real-time confidence + sub-score chart (recharts)
- Position display in NED frame (x, y, z + vx, vy, vz)
- Fusion state: INS/SLAM weight bar + drift estimate
- Sub-score breakdown: IMU stability, SLAM quality, drift penalty, GNSS factor

### Mission Control
- Waypoint builder (NED coordinates)
- Create → Activate → Abort lifecycle
- Quick commands: RTL, Emergency Hold, Safe Mode
- Waypoint altitude profile visualizer
- MQTT delivery confirmation

### Alerts Panel
- Real-time push via WebSocket
- Severity color coding: INFO / WARNING / ERROR / CRITICAL
- Telemetry snapshot at alert time (confidence + nav mode)
- Unread badge counter

### Analytics Dashboard
- Drift summary: mean, std, max, p95, rate
- Confidence trend: bucketed time series
- Level distribution: NOMINAL / DEGRADED / CRITICAL / UNSAFE
- GNSS event log with timestamps

## Quick Start

### Local (Docker Compose)

```bash
# 1. Start PhantomNav™ cloud stack first (in phantomnav/)
cd phantomnav/
docker compose up -d

# 2. Start PhantomOps™ (shares the phantom-net network)
cd phantomops/
docker compose up -d

# 3. Open UI
open http://localhost:3000

# 4. Run the PhantomNav™ sim to generate live data
cd ~/ros2_ws/src/phantomnav
python3 simulation/scenarios/gnss_denied_sim.py
```

> **DEV BYPASS**: On the login page, click "DEV BYPASS (LOCAL ONLY)" to skip auth during development.

### Backend Only (dev)

```bash
cd phantomops/backend
pip install -r requirements.txt

MQTT_HOST=localhost \
FLEET_SERVICE_URL=http://localhost:8005 \
TELEMETRY_SERVICE_URL=http://localhost:8001 \
MISSION_SERVICE_URL=http://localhost:8002 \
ANALYTICS_SERVICE_URL=http://localhost:8003 \
AUTH_SERVICE_URL=http://localhost:8006 \
uvicorn main:app --reload --port 9000
```

### Frontend Only (dev)

```bash
cd phantomops/frontend
npm install
npm run dev
# → http://localhost:3000
# Proxies /api and /ws to localhost:9000
```

## WebSocket Protocol

**Client → Server:**
```json
{ "type": "subscribe", "drones": ["drone-001", "*"] }
{ "type": "ping" }
```

**Server → Client:**
```json
{ "type": "phantom_telemetry",   "drone_id": "drone-001", "ts": 1234567890.0, "data": {...} }
{ "type": "phantom_confidence",  "drone_id": "drone-001", "ts": ...,           "data": {...} }
{ "type": "phantom_status",      "drone_id": "drone-001", "ts": ...,           "data": {...} }
{ "type": "phantom_alerts",      "drone_id": "drone-001", "ts": ...,           "data": {...} }
{ "type": "mqtt_connected",      "ts": ...,               "data": {...} }
{ "type": "mqtt_disconnected",   "ts": ...,               "data": {...} }
```

## REST API

| Method | Path | Description |
|---|---|---|
| `GET`  | `/health`                          | Service health + WS count |
| `GET`  | `/metrics`                         | Prometheus-style metrics |
| `POST` | `/api/auth/login`                  | Authenticate → JWT |
| `GET`  | `/api/fleet/summary`               | All drones (live cache) |
| `GET`  | `/api/fleet/drones/{id}/health`    | Drone health status |
| `GET`  | `/api/telemetry/{id}/latest`       | Latest telemetry (live or DB) |
| `GET`  | `/api/telemetry/{id}/history`      | Historical telemetry |
| `GET`  | `/api/telemetry/{id}/confidence`   | Latest confidence score |
| `POST` | `/api/missions/`                   | Create mission |
| `PUT`  | `/api/missions/{id}/activate`      | Activate + push to UAV |
| `PUT`  | `/api/missions/{id}/abort`         | Abort + send MQTT command |
| `POST` | `/api/missions/{id}/command`       | Direct MQTT command |
| `GET`  | `/api/analytics/{id}/drift`        | Drift summary |
| `GET`  | `/api/analytics/{id}/confidence-trend` | Confidence trend |
| `GET`  | `/api/alerts/{id}`                 | Alert/event log |

## AKS Deployment

```bash
# Set env
export ACR_NAME=phantomnavacr
export JWT_SECRET=your-256-bit-secret

# Build & deploy
chmod +x phantomops/deployment/build-and-push.sh
./phantomops/deployment/build-and-push.sh staging
```

Exposes via HTTPS ingress at `https://ops.phantomnav.io` with:
- TLS termination (cert-manager + Let's Encrypt)
- WebSocket upgrade headers
- HPA: 2–10 replicas based on CPU

## Design Decisions

**No polling**: All real-time data flows through a single persistent WebSocket connection. The UI never polls REST endpoints for live data.

**In-memory cache**: The backend maintains a per-drone state cache fed by MQTT. Fleet summary endpoints respond in < 1ms without touching the DB.

**Decoupled from edge**: Like PhantomNav™ itself, PhantomOps™ degrades gracefully — MQTT loss shows a banner, services going down show stale data with timestamps.

**WebSocket fan-out**: A single MQTT subscription fans out to N WebSocket clients. Adding 100 UI users adds zero MQTT overhead.
