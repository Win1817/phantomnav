# PhantomNav™

**GNSS-Denied UAV Navigation Platform**  
*Hybrid edge autonomy + Azure AKS cloud intelligence*

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      UAV (Edge System)                          │
│                                                                 │
│  IMU ──▶ PhantomCore™ ──▶ /state/estimate ──┐                  │
│  GNSS     (EKF 100Hz)                        │                  │
│                                              ▼                  │
│  Camera ─▶ PhantomVision™ ─▶ /slam/pose ──▶ PhantomFusion™    │
│            (ORB-SLAM 30Hz)   /slam/quality   (50Hz)            │
│                                              │                  │
│                                              ▼ /fusion/pose     │
│                                       PhantomSense™            │
│                                       (confidence 20Hz)        │
│                                              │                  │
│                                              ▼ /confidence/score│
│                                       PhantomDecision™         │
│                                       (10Hz state machine)     │
│                                              │                  │
│                              /nav/mode ◀────┘                  │
│                              /alerts                            │
│                                                                 │
│  PhantomInterface™ ◀──── All topics                            │
│  (MQTT Gateway)                                                 │
└──────────────────┬──────────────────────────────────────────────┘
                   │  MQTT (TLS) / HTTPS
                   │  async only
┌──────────────────▼──────────────────────────────────────────────┐
│                    Azure AKS Cloud                              │
│                                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│  │  Telemetry  │  │   Mission   │  │  Analytics  │            │
│  │  Service    │  │  Service    │  │  Service    │            │
│  │  :8001      │  │  :8002      │  │  :8003      │            │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘            │
│         │                │                 │                   │
│         └────────────────┼─────────────────┘                  │
│                          ▼                                      │
│                    PostgreSQL (Azure)                           │
│                                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│  │    Fleet    │  │    Auth     │  │    MQTT     │            │
│  │  Service    │  │  Service    │  │   Broker    │            │
│  │  :8005      │  │  :8006      │  │  (EMQX)     │            │
│  └─────────────┘  └─────────────┘  └─────────────┘            │
└─────────────────────────────────────────────────────────────────┘
```

## MQTT Topic Schema

| Topic | Direction | QoS | Rate |
|---|---|---|---|
| `phantom/{id}/telemetry` | UAV → Cloud | 0 | 5 Hz |
| `phantom/{id}/confidence`| UAV → Cloud | 0 | 2 Hz |
| `phantom/{id}/status`    | UAV → Cloud | 1 | 0.2 Hz |
| `phantom/{id}/alerts`    | UAV → Cloud | 1 | On-event |
| `phantom/{id}/command`   | Cloud → UAV | 1 | On-demand |
| `phantom/{id}/mission`   | Cloud → UAV | 1 | On-demand |

## Navigation State Machine

```
GNSS_PRIMARY
    │ GNSS lost > 5s
    ▼
INS_SLAM_FUSION  ◀──── GNSS recovered (15s stable)
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

## Confidence Score Formula

```
confidence = (
  0.35 × imu_stability  +    # Accelerometer/gyro variance
  0.35 × slam_quality   +    # ORB feature tracking ratio
  0.20 × drift_penalty  +    # Fusion drift magnitude
  0.10 × gnss_factor         # GNSS accuracy factor
) × 100
```

Smoothed with exponential moving average (α = 0.15).

## Project Structure

```
phantomnav/
├── edge/
│   ├── phantom_core/       C++ EKF state estimation (100–500 Hz)
│   ├── phantom_vision/     C++ ORB SLAM front-end (30–60 Hz)
│   ├── phantom_fusion/     C++ adaptive INS+SLAM fusion (50 Hz)
│   ├── phantom_sense/      Python confidence engine (20 Hz)
│   ├── phantom_decision/   Python navigation state machine (10 Hz)
│   └── phantom_interface/  Python MQTT cloud gateway
├── cloud/
│   ├── telemetry-service/  FastAPI + asyncpg + aiomqtt
│   ├── mission-service/    FastAPI + PostgreSQL + MQTT push
│   ├── analytics-service/  FastAPI + NumPy drift analysis
│   ├── auth-service/       FastAPI + JWT + bcrypt
│   └── fleet-service/      FastAPI + MQTT health watcher
├── interfaces/
│   └── phantom_msgs/       ROS 2 custom message definitions
├── deployment/
│   ├── k8s/services/       Kubernetes manifests (AKS)
│   ├── k8s/monitoring/     Prometheus + Grafana
│   ├── provision-aks.sh    Azure infra provisioning
│   └── build-and-push.sh   Docker → ACR pipeline
├── simulation/
│   └── scenarios/          AirSim GNSS-denied scenario
├── config/
│   ├── edge/params.yaml    ROS 2 node parameters
│   └── edge/*.launch.py    ROS 2 launch files
└── docker-compose.yml      Local development stack
```

## Quick Start

### Local Development (Cloud Services)

```bash
# Start all cloud services locally
docker compose up -d

# Verify health
curl http://localhost:8001/health   # Telemetry
curl http://localhost:8002/health   # Mission
curl http://localhost:8006/health   # Auth

# Register a test drone
curl -X POST http://localhost:8006/auth/device/register \
  -H "Content-Type: application/json" \
  -d '{"drone_id":"drone-001","name":"Test UAV","secret":"test123"}'
```

### Edge Stack (ROS 2)

```bash
# Build
cd /ros2_ws
colcon build --packages-select \
  phantom_msgs phantom_core phantom_vision \
  phantom_fusion phantom_sense phantom_decision phantom_interface

# Run with simulation
source install/setup.bash
ros2 launch phantomnav phantomnav_edge.launch.py sim:=true

# Monitor topics
ros2 topic echo /confidence/score
ros2 topic echo /nav/mode
ros2 topic echo /fusion/pose
```

### AKS Deployment

```bash
# Provision Azure infrastructure
chmod +x deployment/provision-aks.sh
./deployment/provision-aks.sh staging

# Build and push images
./deployment/build-and-push.sh staging

# Monitor
kubectl get pods -n phantomnav
kubectl logs -n phantomnav deployment/telemetry-service -f
```

## Build Phases

| Phase | Deliverable | Status |
|-------|-------------|--------|
| 1 | PhantomCore™ EKF | ✅ Complete |
| 2 | PhantomVision™ SLAM | ✅ Complete |
| 3 | PhantomFusion™ Fusion | ✅ Complete |
| 4 | PhantomSense™ + PhantomDecision™ | ✅ Complete |
| 5 | PhantomInterface™ + Cloud Services | ✅ Complete |
| 6 | AKS Deployment + Observability | ✅ Complete |

## Success Criteria Verification

| Criterion | Implementation |
|-----------|----------------|
| Survives GNSS loss | PhantomDecision™ state machine, INS+SLAM fallback |
| Outputs stable pose | PhantomFusion™ covariance-weighted fusion at 50 Hz |
| Provides confidence score | PhantomSense™ 0–100 composite score at 20 Hz |
| Integrates with AKS backend | PhantomInterface™ async MQTT gateway |

## Key Design Decisions

**Edge-first safety**: The UAV is fully autonomous without any cloud dependency. Cloud connectivity is bonus intelligence, never a safety requirement.

**Covariance-driven fusion**: SLAM weight is computed from actual position variance, not a fixed parameter. When INS diverges (large covariance), SLAM gets more weight automatically.

**Debounced state transitions**: Navigation mode changes require the trigger condition to hold for a configurable debounce window (default 2s) to prevent chattering.

**Async cloud bridge**: PhantomInterface™ runs MQTT in a background thread completely decoupled from the ROS 2 spin loop. Cloud connectivity loss has zero effect on navigation.
