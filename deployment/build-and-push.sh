#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# PhantomNav™ — Build and Push All Cloud Service Images to ACR
#
# Usage:
#   ./build-and-push.sh [staging|prod] [service_name]
#   ./build-and-push.sh staging                  # all services
#   ./build-and-push.sh prod telemetry-service   # single service
# ─────────────────────────────────────────────────────────────

set -euo pipefail

ENV=${1:-staging}
TARGET_SERVICE=${2:-all}
ACR_NAME="phantomacr${ENV}"
ACR_LOGIN="${ACR_NAME}.azurecr.io"
TAG=${IMAGE_TAG:-$(git rev-parse --short HEAD 2>/dev/null || echo "latest")}

SERVICES=(
  telemetry-service
  mission-service
  analytics-service
  auth-service
  fleet-service
)

echo "Building for ACR: $ACR_LOGIN | Tag: $TAG"
az acr login --name "$ACR_NAME"

build_service() {
  local SVC=$1
  local CTX="cloud/${SVC}"
  local IMAGE="${ACR_LOGIN}/${SVC}:${TAG}"
  local IMAGE_LATEST="${ACR_LOGIN}/${SVC}:latest"

  echo ""
  echo "▶ Building ${SVC}..."
  docker build \
    --platform linux/amd64 \
    --cache-from "${IMAGE_LATEST}" \
    --build-arg BUILDKIT_INLINE_CACHE=1 \
    -t "$IMAGE" \
    -t "$IMAGE_LATEST" \
    "$CTX"

  echo "▶ Pushing ${SVC}..."
  docker push "$IMAGE"
  docker push "$IMAGE_LATEST"
  echo "✓ ${SVC} → ${IMAGE}"
}

if [[ "$TARGET_SERVICE" == "all" ]]; then
  for SVC in "${SERVICES[@]}"; do
    build_service "$SVC"
  done
else
  build_service "$TARGET_SERVICE"
fi

echo ""
echo "All images pushed to ${ACR_LOGIN}"
echo "Update AKS deployments:"
echo "  kubectl rollout restart deployment -n phantomnav"
