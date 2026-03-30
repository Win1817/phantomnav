#!/bin/bash
# ─────────────────────────────────────────────────────────────
# PhantomOps™ — Build & Push to Azure Container Registry
# Usage: ./build-and-push.sh [staging|production]
# ─────────────────────────────────────────────────────────────
set -euo pipefail

ENV="${1:-staging}"
ACR_NAME="${ACR_NAME:-phantomnavacr}"
IMAGE_TAG="${IMAGE_TAG:-$(git rev-parse --short HEAD)}"

echo "=== PhantomOps™ Build & Push ==="
echo "  Environment: $ENV"
echo "  ACR:         $ACR_NAME"
echo "  Tag:         $IMAGE_TAG"
echo

# Login to ACR
az acr login --name "$ACR_NAME"

# Build & push backend
echo "--- Building phantomops-backend ---"
docker build -t "$ACR_NAME.azurecr.io/phantomops-backend:$IMAGE_TAG" \
             -t "$ACR_NAME.azurecr.io/phantomops-backend:$ENV-latest" \
             ./backend
docker push "$ACR_NAME.azurecr.io/phantomops-backend:$IMAGE_TAG"
docker push "$ACR_NAME.azurecr.io/phantomops-backend:$ENV-latest"

# Build & push frontend
echo "--- Building phantomops-frontend ---"
docker build -t "$ACR_NAME.azurecr.io/phantomops-frontend:$IMAGE_TAG" \
             -t "$ACR_NAME.azurecr.io/phantomops-frontend:$ENV-latest" \
             ./frontend
docker push "$ACR_NAME.azurecr.io/phantomops-frontend:$IMAGE_TAG"
docker push "$ACR_NAME.azurecr.io/phantomops-frontend:$ENV-latest"

echo
echo "=== Deploy to AKS ==="
# Replace image tags in manifest and apply
export ACR_NAME IMAGE_TAG
envsubst < deployment/k8s/phantomops.yaml | kubectl apply -f -

kubectl rollout status deployment/phantomops-backend  -n phantomops --timeout=120s
kubectl rollout status deployment/phantomops-frontend -n phantomops --timeout=120s

echo
echo "✅ PhantomOps™ deployed."
echo "   https://ops.phantomnav.io"
