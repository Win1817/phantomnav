# PhantomNav™ — Deployment Guide

Complete step-by-step instructions for all deployment environments:
local development, edge UAV build, and Azure AKS production.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Edge Build — ROS 2 Stack](#2-edge-build--ros-2-stack)
3. [Local Development — Docker Compose](#3-local-development--docker-compose)
4. [PhantomOps C2 Dashboard](#4-phantomops-c2-dashboard)
5. [AKS Production Deployment](#5-aks-production-deployment)
6. [Simulation](#6-simulation)
7. [Observability](#7-observability)
8. [Troubleshooting](#8-troubleshooting)

---

## 1. Prerequisites

### Edge (UAV onboard computer)

| Requirement | Version | Install |
|---|---|---|
| Ubuntu | 22.04 LTS | — |
| ROS 2 Humble | latest | [docs.ros.org](https://docs.ros.org/en/humble/Installation.html) |
| Eigen3 | 3.4+ | `sudo apt install libeigen3-dev` |
| OpenCV | 4.x | `sudo apt install libopencv-dev` |
| Python | 3.10+ | included in Ubuntu 22.04 |

Install all ROS 2 edge dependencies in one shot:

```bash
sudo apt update && sudo apt install -y \
  ros-humble-cv-bridge \
  ros-humble-image-transport \
  ros-humble-sensor-msgs \
  ros-humble-geometry-msgs \
  ros-humble-eigen3-cmake-module \
  libeigen3-dev \
  libopencv-dev \
  python3-pip

pip3 install paho-mqtt numpy
```

### Cloud / DevOps workstation

| Tool | Version | Purpose |
|---|---|---|
| Docker | 24+ | Container build |
| Docker Compose | v2 | Local stack |
| Azure CLI | 2.55+ | AKS provisioning |
| kubectl | 1.29+ | Kubernetes management |
| Node.js | 20+ | Frontend build |
| Python | 3.11+ | Cloud services |

```bash
# Azure CLI
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash

# kubectl
az aks install-cli

# Node.js 20
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

---

## 2. Edge Build — ROS 2 Stack

### 2.1 Clone into workspace

```bash
mkdir -p ~/ros2_ws/src
cd ~/ros2_ws/src
git clone https://github.com/Win1817/phantomnav.git
cd ~/ros2_ws
```

### 2.2 Source ROS 2

```bash
source /opt/ros/humble/setup.bash

# Add to .bashrc permanently
echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc
```

### 2.3 Build all edge packages

Always build `phantom_msgs` first — all other packages depend on it.
colcon handles this automatically when you list all packages together.

```bash
cd ~/ros2_ws

colcon build --packages-select \
  phantom_msgs \
  phantom_core \
  phantom_vision \
  phantom_fusion \
  phantom_sense \
  phantom_decision \
  phantom_interface \
  --symlink-install
```

`--symlink-install` lets you edit Python nodes without rebuilding.

### 2.4 Source the workspace

```bash
source ~/ros2_ws/install/setup.bash

# Add to .bashrc
echo "source ~/ros2_ws/install/setup.bash" >> ~/.bashrc
```

### 2.5 Verify packages loaded

```bash
ros2 pkg list | grep phantom
```

Expected output:
```
phantom_core
phantom_decision
phantom_fusion
phantom_interface
phantom_msgs
phantom_sense
phantom_vision
```

### 2.6 Rebuild after code changes

```bash
# Clean only changed packages
rm -rf ~/ros2_ws/build/phantom_core

# Rebuild
cd ~/ros2_ws
colcon build --packages-select phantom_core --symlink-install
source install/setup.bash
```

---

## 3. Local Development — Docker Compose

Runs all cloud microservices locally on your workstation alongside
the edge ROS 2 stack or the AirSim simulator.

### 3.1 Start the core cloud stack

```bash
cd ~/ros2_ws/src/phantomnav

docker compose up -d
```

This starts:
- PostgreSQL on port 5432
- Mosquitto MQTT broker on ports 1883, 9001
- Telemetry Service on port 8001
- Mission Service on port 8002
- Analytics Service on port 8003
- Auth Service on port 8006
- Fleet Service on port 8005
- Prometheus on port 9090
- Grafana on port 3000

### 3.2 Verify all services healthy

```bash
curl http://localhost:8001/health   # Telemetry
curl http://localhost:8002/health   # Mission
curl http://localhost:8003/health   # Analytics
curl http://localhost:8006/health   # Auth
curl http://localhost:8005/health   # Fleet
```

All should return `{"status": "ok", ...}`.

### 3.3 Register a test drone

```bash
# Register device
curl -X POST http://localhost:8006/auth/device/register \
  -H "Content-Type: application/json" \
  -d '{
    "drone_id": "drone-001",
    "name": "Test UAV Alpha",
    "secret": "phantom_test_secret"
  }'

# Get JWT token
curl -X POST http://localhost:8006/auth/token \
  -H "Content-Type: application/json" \
  -d '{
    "drone_id": "drone-001",
    "secret": "phantom_test_secret"
  }'
```

### 3.4 Register drone in fleet

```bash
curl -X POST http://localhost:8005/fleet/drones/ \
  -H "Content-Type: application/json" \
  -d '{
    "drone_id": "drone-001",
    "name": "Test UAV Alpha",
    "model": "PhantomFrame-v1",
    "capabilities": ["SLAM", "GNSS", "VISION"]
  }'
```

### 3.5 Stop the stack

```bash
docker compose down

# Stop and wipe all data volumes
docker compose down -v
```

---

## 4. PhantomOps C2 Dashboard

PhantomOps is the real-time ground control station. It lives in
`cloud/phantomops/` and shares the `phantom-net` Docker network
with the core stack.

### 4.1 Local development — Docker Compose

Make sure the core stack from Step 3 is running first.

```bash
cd ~/ros2_ws/src/phantomnav/cloud/phantomops

docker compose up -d
```

Open the dashboard: **http://localhost:3000**

PhantomOps backend is available at **http://localhost:9000**
WebSocket endpoint: **ws://localhost:9000/ws**

### 4.2 Frontend development (hot reload)

```bash
cd ~/ros2_ws/src/phantomnav/cloud/phantomops/frontend

npm install
npm run dev
```

Frontend runs at **http://localhost:5173** with Vite hot reload.
Set `VITE_WS_URL=ws://localhost:9000/ws` in a `.env` file if needed.

### 4.3 Backend development (auto reload)

```bash
cd ~/ros2_ws/src/phantomnav/cloud/phantomops/backend

pip install -r requirements.txt

MQTT_HOST=localhost \
FLEET_SERVICE_URL=http://localhost:8005 \
TELEMETRY_SERVICE_URL=http://localhost:8001 \
MISSION_SERVICE_URL=http://localhost:8002 \
ANALYTICS_SERVICE_URL=http://localhost:8003 \
AUTH_SERVICE_URL=http://localhost:8006 \
uvicorn main:app --reload --port 9000
```

### 4.4 PhantomOps environment variables

| Variable | Default | Description |
|---|---|---|
| `PORT` | 9000 | Backend listen port |
| `MQTT_HOST` | localhost | MQTT broker hostname |
| `MQTT_PORT` | 1883 | MQTT broker port |
| `FLEET_SERVICE_URL` | http://localhost:8005 | Fleet service endpoint |
| `TELEMETRY_SERVICE_URL` | http://localhost:8001 | Telemetry service endpoint |
| `MISSION_SERVICE_URL` | http://localhost:8002 | Mission service endpoint |
| `ANALYTICS_SERVICE_URL` | http://localhost:8003 | Analytics service endpoint |
| `AUTH_SERVICE_URL` | http://localhost:8006 | Auth service endpoint |
| `JWT_SECRET` | CHANGE_ME | JWT signing secret |

---

## 5. AKS Production Deployment

### 5.1 Login to Azure

```bash
az login
az account set --subscription <YOUR_SUBSCRIPTION_ID>

# Verify
az account show
```

### 5.2 Provision Azure infrastructure

```bash
cd ~/ros2_ws/src/phantomnav

chmod +x deployment/provision-aks.sh
./deployment/provision-aks.sh staging    # or prod
```

This script provisions:
- Resource Group `rg-phantomnav-staging`
- Azure Container Registry `phantomacrstaging.azurecr.io`
- AKS cluster (3 nodes, autoscale 2–10, Standard_D4s_v3)
- Azure PostgreSQL Flexible Server (16, Zone Redundant HA)
- Azure Key Vault (all secrets stored here)
- Applies base Kubernetes manifests
- Applies Prometheus + Grafana monitoring stack

Wait approximately 10 minutes for AKS provisioning to complete.

### 5.3 Verify cluster is up

```bash
kubectl get nodes
kubectl get pods -n phantomnav
kubectl get pods -n kube-system
```

### 5.4 Build and push all Docker images

```bash
chmod +x deployment/build-and-push.sh

# Build and push all cloud services
./deployment/build-and-push.sh staging

# Or push a single service after changes
./deployment/build-and-push.sh staging telemetry-service
```

### 5.5 Build and push PhantomOps images

```bash
cd ~/ros2_ws/src/phantomnav/cloud/phantomops
chmod +x deployment/build-and-push.sh
./deployment/build-and-push.sh staging
```

### 5.6 Apply PhantomOps Kubernetes manifest

```bash
kubectl apply -f cloud/phantomops/deployment/k8s/phantomops.yaml
```

### 5.7 Verify all pods running

```bash
# Core services
kubectl get pods -n phantomnav

# PhantomOps
kubectl get pods -n phantomops

# Check logs of any pod
kubectl logs -n phantomnav deployment/telemetry-service -f
kubectl logs -n phantomops deployment/phantomops-backend -f
```

Expected state — all pods `Running`:
```
NAME                                  READY   STATUS    RESTARTS
auth-service-xxx                      1/1     Running   0
fleet-service-xxx                     1/1     Running   0
telemetry-service-xxx                 1/1     Running   0
mission-service-xxx                   1/1     Running   0
analytics-service-xxx                 1/1     Running   0
mosquitto-xxx                         1/1     Running   0
```

### 5.8 Rolling update after code changes

```bash
# Rebuild and push new image
./deployment/build-and-push.sh staging telemetry-service

# Roll out new image
kubectl rollout restart deployment/telemetry-service -n phantomnav

# Watch rollout
kubectl rollout status deployment/telemetry-service -n phantomnav
```

### 5.9 Configure UAV to point at cloud

Update `config/edge/params.yaml` on the UAV:

```yaml
phantom_interface_node:
  ros__parameters:
    broker_host: <MOSQUITTO_EXTERNAL_IP>   # kubectl get svc mosquitto -n phantomnav
    broker_port: 8883
    broker_tls:  true
    drone_id:    drone-001
```

Get the MQTT LoadBalancer IP:
```bash
kubectl get svc mosquitto -n phantomnav
# Copy the EXTERNAL-IP column
```

---

## 6. Simulation

### 6.1 Install AirSim

Follow the [AirSim on Ubuntu guide](https://microsoft.github.io/AirSim/build_linux/).
Place the AirSim binary in `~/AirSim/`.

### 6.2 Configure AirSim settings

Place this in `~/Documents/AirSim/settings.json`:

```json
{
  "SeeDocsAt": "https://github.com/Microsoft/AirSim/blob/master/docs/settings.md",
  "SettingsVersion": 1.2,
  "SimMode": "Multirotor",
  "Vehicles": {
    "drone-001": {
      "VehicleType": "SimpleFlight",
      "DefaultVehicleState": "Armed",
      "EnableCollisionPassthrough": false,
      "EnableCollisions": true,
      "RC": { "RemoteControlID": 0 }
    }
  }
}
```

### 6.3 Run the simulation scenario

Terminal 1 — Start AirSim:
```bash
~/AirSim/LinuxNoEditor/AirSimNH.sh -ResX=1280 -ResY=720 -windowed
```

Terminal 2 — Start the edge stack in sim mode:
```bash
source ~/ros2_ws/install/setup.bash

ros2 launch phantomnav phantomnav_edge.launch.py \
  sim:=true \
  drone_id:=drone-001 \
  log_level:=info
```

Terminal 3 — Monitor navigation mode and confidence:
```bash
ros2 topic echo /nav/mode
ros2 topic echo /confidence/score
ros2 topic echo /alerts
```

### 6.4 Simulation phases

The scenario in `simulation/scenarios/gnss_denied_sim.py` runs:

| Phase | Duration | Event |
|---|---|---|
| 1 | 0–30s | Normal flight with GNSS |
| 2 | 30–90s | GNSS signal loss — INS+SLAM takes over |
| 3 | 90–120s | Sensor degradation injected |
| 4 | 120–150s | GNSS recovery + return to home |

Watch the `/nav/mode` topic switch through:
`GNSS_PRIMARY` → `INS_SLAM_FUSION` → `INS_ONLY` → `SAFE_MODE` → recovery.

### 6.5 Run without AirSim (synthetic sensors)

The sim node generates synthetic IMU and GNSS data automatically
when AirSim is not reachable. Just launch the edge stack as normal:

```bash
ros2 launch phantomnav phantomnav_edge.launch.py sim:=true
```

---

## 7. Observability

### 7.1 Prometheus

Local:
```bash
open http://localhost:9090
```

AKS:
```bash
kubectl port-forward -n phantomnav svc/prometheus 9090:9090
open http://localhost:9090
```

Useful queries:
```promql
# Active drone count
count(phantom_confidence_score > 0)

# Drones in GNSS-denied mode
count(phantom_gnss_available == 0)

# Average confidence fleet-wide
avg(phantom_confidence_score)

# Drift above 5m
phantom_drift_m > 5
```

### 7.2 Grafana

Local:
```bash
open http://localhost:3000
# Default credentials: admin / phantomadmin
```

AKS:
```bash
kubectl port-forward -n phantomnav svc/grafana 3001:3000
open http://localhost:3001
```

Add Prometheus as a data source:
- URL: `http://prometheus:9090` (in-cluster) or `http://localhost:9090` (local)
- Access: Server

### 7.3 Service logs

```bash
# Core services
kubectl logs -n phantomnav deployment/telemetry-service --tail=100 -f
kubectl logs -n phantomnav deployment/mission-service --tail=100 -f

# PhantomOps
kubectl logs -n phantomops deployment/phantomops-backend --tail=100 -f

# Edge nodes (on UAV)
ros2 topic echo /alerts
ros2 topic echo /nav/mode
```

### 7.4 Alert rules

Pre-configured Prometheus alerts:

| Alert | Condition | Severity |
|---|---|---|
| DroneLowConfidence | confidence < 20 for 30s | critical |
| DroneGNSSLost | gnss_available == 0 for 60s | warning |
| DroneDriftHigh | drift_m > 10 for 15s | warning |
| ServiceDown | service unreachable for 1m | critical |
| HighMemoryUsage | container memory > 85% for 5m | warning |

---

## 8. Troubleshooting

### colcon build failures

**`package.xml does not exist`**
```bash
# Make sure you pulled latest
cd ~/ros2_ws/src/phantomnav && git pull

# Clean and rebuild
rm -rf ~/ros2_ws/build ~/ros2_ws/install
cd ~/ros2_ws
colcon build --packages-select phantom_msgs ... --symlink-install
```

**`StateMat does not name a type` / Eigen errors**
```bash
# Confirm eigen3-cmake-module is installed
apt list --installed | grep eigen

# If missing
sudo apt install ros-humble-eigen3-cmake-module libeigen3-dev

# Clean phantom_core and rebuild
rm -rf ~/ros2_ws/build/phantom_core
colcon build --packages-select phantom_msgs phantom_core --symlink-install
```

**`failed to create symbolic link ... Is a directory`**
```bash
# Wipe the conflicted package from both build and install
rm -rf ~/ros2_ws/build/phantom_msgs ~/ros2_ws/install/phantom_msgs
colcon build --packages-select phantom_msgs --symlink-install
```

### Docker Compose issues

**Services not connecting to postgres**
```bash
# Check postgres health
docker compose ps postgres
docker compose logs postgres

# Manually check connection
docker exec -it phantom-postgres psql -U phantom -d phantomnav -c "\dt"
```

**MQTT messages not arriving**
```bash
# Subscribe to all phantom topics to verify traffic
docker exec -it phantom-mqtt mosquitto_sub -t "phantom/#" -v

# Check PhantomInterface is publishing
ros2 topic hz /fusion/pose    # should be ~50Hz
```

### AKS issues

**Pods stuck in Pending**
```bash
kubectl describe pod <pod-name> -n phantomnav
# Look for: Insufficient cpu/memory → scale node pool
az aks scale --resource-group rg-phantomnav-staging \
  --name aks-phantomnav-staging --node-count 5
```

**Image pull errors (ErrImagePull)**
```bash
# Verify AKS has ACR pull permission
az aks update \
  --name aks-phantomnav-staging \
  --resource-group rg-phantomnav-staging \
  --attach-acr phantomacrstaging
```

**Services can't reach each other**
```bash
# Test internal DNS
kubectl exec -it deployment/telemetry-service -n phantomnav -- \
  curl http://fleet-service:8005/health
```

### PhantomOps issues

**WebSocket not connecting**
- Confirm backend is running: `curl http://localhost:9000/health`
- Check `VITE_WS_URL` env var matches backend host
- Check browser console for CORS errors

**No live data in dashboard**
- Verify MQTT bridge is connected: `curl http://localhost:9000/metrics`
- Check `mqtt_connected: true` in response
- Confirm UAV PhantomInterface is publishing to broker

---

## Environment Variable Reference

### Core services (docker-compose / K8s ConfigMap)

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `MQTT_HOST` | MQTT broker hostname |
| `MQTT_PORT` | MQTT broker port (default 1883) |

### Auth Service

| Variable | Description |
|---|---|
| `JWT_SECRET` | 256-bit signing key — must match PhantomOps |
| `TOKEN_TTL_S` | Token lifetime in seconds (default 86400) |

### PhantomOps Backend

| Variable | Description |
|---|---|
| `FLEET_SERVICE_URL` | Internal fleet service URL |
| `TELEMETRY_SERVICE_URL` | Internal telemetry service URL |
| `MISSION_SERVICE_URL` | Internal mission service URL |
| `ANALYTICS_SERVICE_URL` | Internal analytics service URL |
| `AUTH_SERVICE_URL` | Internal auth service URL |

### PhantomInterface (edge)

Configure in `config/edge/params.yaml`:

| Parameter | Description |
|---|---|
| `drone_id` | Unique identifier used in all MQTT topics |
| `broker_host` | MQTT broker IP or hostname |
| `broker_port` | 1883 (dev) or 8883 (TLS prod) |
| `broker_tls` | true in production |
| `telemetry_rate_hz` | How often telemetry is published (default 5) |
