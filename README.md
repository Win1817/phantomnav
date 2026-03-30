# PhantomNav™

**GNSS-Denied UAV Navigation Platform**
Hybrid edge autonomy + Azure AKS cloud intelligence + real-time ground control

---

## System Overview

PhantomNav™ is a full-stack autonomous UAV platform built for operation in
GNSS-denied environments. It combines deterministic onboard autonomy with
cloud-based intelligence and a real-time ground control station.

```
┌─────────────────────────────────────────────────────────────────────┐
│                        UAV  (Edge System)                           │
│                                                                     │
│  IMU ──▶ PhantomCore™ ──▶ /state/estimate ──┐                      │
│  GNSS     (EKF 100Hz)                        │                      │
│                                              ▼                      │
│  Camera─▶ PhantomVision™─▶ /slam/pose ──▶ PhantomFusion™          │
│           (ORB-SLAM 30Hz)   /slam/quality   (50Hz fused pose)      │
│                                              │                      │
│                                              ▼                      │
│                                       PhantomSense™                │
│                                       (confidence 0-100 at 20Hz)   │
│                                              │                      │
│                                              ▼                      │
│                                       PhantomDecision™             │
│                                       (nav FSM at 10Hz)            │
│                                              │                      │
│                        /nav/mode  alerts ◀───┘                     │
│                                                                     │
│       PhantomInterface™ ◀──── All ROS 2 topics                     │
│       (MQTT async gateway)                                          │
└────────────────────┬────────────────────────────────────────────────┘
                     │  MQTT over TLS  /  HTTPS
                     │  async only — UAV never blocks on cloud
┌────────────────────▼────────────────────────────────────────────────┐
│                     Azure AKS  (Cloud Layer)                        │
│                                                                     │
│  Telemetry :8001   Mission :8002   Analytics :8003                 │
│  Fleet :8005       Auth :8006      MQTT Broker :1883               │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │               PhantomOps™  C2 Platform                      │   │
│  │   Backend  FastAPI + WebSocket + MQTT bridge   :9000        │   │
│  │   Frontend React + TypeScript + Recharts       :3000        │   │
│  │   Pages: Fleet, Drone, Missions, Alerts, Analytics          │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  Prometheus :9090      Grafana :3000                               │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Repository Structure

```
phantomnav/
├── edge/
│   ├── phantom_core/          C++ EKF state estimation (100-500 Hz)
│   ├── phantom_vision/        C++ ORB visual odometry (30-60 Hz)
│   ├── phantom_fusion/        C++ adaptive INS+SLAM fusion (50 Hz)
│   ├── phantom_sense/         Python confidence engine (20 Hz)
│   ├── phantom_decision/      Python navigation state machine (10 Hz)
│   └── phantom_interface/     Python async MQTT gateway
│
├── cloud/
│   ├── telemetry-service/     FastAPI — MQTT ingest + PostgreSQL
│   ├── mission-service/       FastAPI — flight plan management
│   ├── analytics-service/     FastAPI — drift + confidence analysis
│   ├── auth-service/          FastAPI — JWT + device identity
│   ├── fleet-service/         FastAPI — UAV registry + health
│   └── phantomops/            Ground control station (C2)
│       ├── backend/           FastAPI + WebSocket + MQTT bridge
│       │   └── routers/       fleet, telemetry, missions, analytics, alerts, auth
│       ├── frontend/          React + TypeScript + Vite
│       │   └── src/
│       │       ├── pages/     FleetPage, DronePage, MissionsPage, AlertsPage, AnalyticsPage
│       │       ├── hooks/     useWebSocket
│       │       ├── store/     Zustand global state
│       │       ├── types/     TypeScript interfaces
│       │       └── utils/     api.ts, format.ts
│       ├── deployment/        K8s manifest + ACR build script
│       └── docker-compose.yml Local dev (extends phantom-net)
│
├── interfaces/
│   └── phantom_msgs/          ROS 2 custom message definitions
│       └── msg/               StateEstimate, SlamPose, FusedPose,
│                              ConfidenceScore, NavMode, PhantomAlert
│
├── deployment/
│   ├── k8s/services/          AKS service manifests + HPA
│   ├── k8s/monitoring/        Prometheus + Grafana + alert rules
│   ├── provision-aks.sh       Full Azure infrastructure provisioning
│   └── build-and-push.sh      Docker build + ACR push pipeline
│
├── simulation/
│   └── scenarios/             AirSim 4-phase GNSS-denied scenario
│
├── config/
│   ├── edge/params.yaml       ROS 2 node parameters (all 6 nodes)
│   ├── edge/phantomnav_edge.launch.py
│   └── mosquitto.conf
│
└── docker-compose.yml         Full local development stack
```

---

## MQTT Topic Schema

| Topic | Direction | QoS | Rate |
|---|---|---|---|
| `phantom/{id}/telemetry` | UAV to Cloud | 0 | 5 Hz |
| `phantom/{id}/confidence` | UAV to Cloud | 0 | 2 Hz |
| `phantom/{id}/status` | UAV to Cloud | 1 | 0.2 Hz |
| `phantom/{id}/alerts` | UAV to Cloud | 1 | On-event |
| `phantom/{id}/command` | Cloud to UAV | 1 | On-demand |
| `phantom/{id}/mission` | Cloud to UAV | 1 | On-demand |

---

## Navigation State Machine

```
GNSS_PRIMARY
    │ GNSS lost > 5s
    ▼
INS_SLAM_FUSION  ◀──── GNSS recovered (stable 15s)
    │ confidence < 40
    ▼
INS_ONLY
    │ confidence < 25
    ▼
SAFE_MODE
    │ confidence < 12
    ▼
EMERGENCY_HOLD
```

---

## Confidence Score

```
confidence = (
  0.35 x imu_stability   +   accelerometer/gyro variance
  0.35 x slam_quality    +   ORB feature tracking ratio
  0.20 x drift_penalty   +   fusion drift magnitude
  0.10 x gnss_factor         GNSS fix accuracy
) x 100
```

Smoothed with exponential moving average alpha=0.15.

---

## Service Port Map

| Service | Port |
|---|---|
| Telemetry Service | 8001 |
| Mission Service | 8002 |
| Analytics Service | 8003 |
| Fleet Service | 8005 |
| Auth Service | 8006 |
| PhantomOps Backend | 9000 |
| PhantomOps Frontend | 3000 |
| MQTT Broker | 1883 / 8883 (TLS) |
| Prometheus | 9090 |
| Grafana | 3001 |

---

## Build Phases

| Phase | Deliverable | Status |
|---|---|---|
| 1 | PhantomCore EKF | Done |
| 2 | PhantomVision SLAM | Done |
| 3 | PhantomFusion | Done |
| 4 | PhantomSense + PhantomDecision | Done |
| 5 | Cloud microservices + MQTT | Done |
| 6 | AKS deployment + observability | Done |
| 7 | PhantomOps C2 dashboard | Done |

---

## Key Design Principles

**Edge-first safety** — The UAV operates fully autonomously with zero cloud dependency.
Cloud loss has no effect on navigation.

**Covariance-driven fusion** — SLAM/INS weights are computed from real-time position
variance. INS divergence automatically increases SLAM contribution.

**Debounced state transitions** — Mode changes require the trigger condition to hold
for a configurable window (default 2s) to prevent chattering.

**Async cloud bridge** — PhantomInterface runs MQTT in a background thread entirely
decoupled from the ROS 2 spin loop.

**Golden rules**
1. UAV must work without cloud
2. Cloud must never block navigation
3. All edge-cloud communication is asynchronous

---

See **DEPLOYMENT.md** for full step-by-step deployment instructions.
