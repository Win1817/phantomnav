#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# PhantomNav™ — Azure AKS Infrastructure Provisioning
# Provisions: Resource Group, ACR, AKS, PostgreSQL, Key Vault
#
# Prerequisites:
#   az login
#   az account set --subscription <SUB_ID>
#
# Usage:
#   ./provision-aks.sh [prod|staging]
# ─────────────────────────────────────────────────────────────

set -euo pipefail

ENV=${1:-staging}
LOCATION="southeastasia"           # Closest to PH
RG="rg-phantomnav-${ENV}"
AKS_NAME="aks-phantomnav-${ENV}"
ACR_NAME="phantomacr${ENV}"        # Must be globally unique, no hyphens
PG_SERVER="pg-phantomnav-${ENV}"
KV_NAME="kv-phantomnav-${ENV}"

echo "══════════════════════════════════════════════"
echo "  PhantomNav™ AKS Provisioning"
echo "  Environment : ${ENV}"
echo "  Location    : ${LOCATION}"
echo "  Resource Grp: ${RG}"
echo "══════════════════════════════════════════════"

# ── 1. Resource Group ─────────────────────────────────────────
echo "[1/7] Creating resource group..."
az group create \
  --name "$RG" \
  --location "$LOCATION" \
  --tags project=phantomnav environment="$ENV"

# ── 2. Azure Container Registry ──────────────────────────────
echo "[2/7] Creating Azure Container Registry..."
az acr create \
  --resource-group "$RG" \
  --name "$ACR_NAME" \
  --sku Standard \
  --admin-enabled false \
  --location "$LOCATION"

ACR_ID=$(az acr show --name "$ACR_NAME" --query id -o tsv)
echo "  ACR ID: $ACR_ID"

# ── 3. AKS Cluster ────────────────────────────────────────────
echo "[3/7] Creating AKS cluster (this takes ~5 min)..."
az aks create \
  --resource-group "$RG" \
  --name "$AKS_NAME" \
  --location "$LOCATION" \
  --node-count 3 \
  --node-vm-size Standard_D4s_v3 \
  --min-count 2 \
  --max-count 10 \
  --enable-cluster-autoscaler \
  --network-plugin azure \
  --network-policy calico \
  --generate-ssh-keys \
  --enable-managed-identity \
  --attach-acr "$ACR_NAME" \
  --enable-addons monitoring \
  --workspace-resource-id "" \
  --kubernetes-version 1.29 \
  --tags project=phantomnav environment="$ENV"

# ── 4. Get kubeconfig ─────────────────────────────────────────
echo "[4/7] Fetching kubeconfig..."
az aks get-credentials \
  --resource-group "$RG" \
  --name "$AKS_NAME" \
  --overwrite-existing

# ── 5. Azure PostgreSQL Flexible Server ───────────────────────
echo "[5/7] Creating PostgreSQL Flexible Server..."
PG_PASSWORD=$(openssl rand -base64 24 | tr -d '/+=')
az postgres flexible-server create \
  --resource-group "$RG" \
  --name "$PG_SERVER" \
  --location "$LOCATION" \
  --admin-user phantom \
  --admin-password "$PG_PASSWORD" \
  --sku-name Standard_D2s_v3 \
  --tier GeneralPurpose \
  --storage-size 64 \
  --version 16 \
  --high-availability ZoneRedundant \
  --database-name phantomnav

echo "  PostgreSQL password stored — saving to Key Vault..."

# ── 6. Azure Key Vault ────────────────────────────────────────
echo "[6/7] Creating Key Vault..."
az keyvault create \
  --resource-group "$RG" \
  --name "$KV_NAME" \
  --location "$LOCATION" \
  --sku standard \
  --enable-rbac-authorization true

# Store secrets
JWT_SECRET=$(openssl rand -base64 32)
az keyvault secret set --vault-name "$KV_NAME" \
  --name "postgres-password" --value "$PG_PASSWORD" > /dev/null
az keyvault secret set --vault-name "$KV_NAME" \
  --name "jwt-secret" --value "$JWT_SECRET" > /dev/null
echo "  Secrets stored in Key Vault: $KV_NAME"

# ── 7. Deploy PhantomNav ──────────────────────────────────────
echo "[7/7] Applying Kubernetes manifests..."

# Namespace + ConfigMap first
kubectl apply -f deployment/k8s/services/phantomnav-services.yaml

# Update secrets from Key Vault
PG_PASS=$(az keyvault secret show \
  --vault-name "$KV_NAME" --name "postgres-password" \
  --query value -o tsv)
JWT_SEC=$(az keyvault secret show \
  --vault-name "$KV_NAME" --name "jwt-secret" \
  --query value -o tsv)

kubectl create secret generic phantom-secrets \
  --namespace phantomnav \
  --from-literal=POSTGRES_PASSWORD="$PG_PASS" \
  --from-literal=JWT_SECRET="$JWT_SEC" \
  --dry-run=client -o yaml | kubectl apply -f -

# Monitoring stack
kubectl apply -f deployment/k8s/monitoring/observability.yaml

echo ""
echo "══════════════════════════════════════════════"
echo "  PhantomNav™ AKS Provisioning COMPLETE"
echo "══════════════════════════════════════════════"
echo "  AKS Cluster : $AKS_NAME"
echo "  ACR         : ${ACR_NAME}.azurecr.io"
echo "  PostgreSQL  : ${PG_SERVER}.postgres.database.azure.com"
echo "  Key Vault   : $KV_NAME"
echo ""
echo "  Next steps:"
echo "  1. Build & push images: ./scripts/build-and-push.sh"
echo "  2. Check pods: kubectl get pods -n phantomnav"
echo "  3. Access Grafana: kubectl port-forward -n phantomnav svc/grafana 3000:3000"
echo "══════════════════════════════════════════════"
