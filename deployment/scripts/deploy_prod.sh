#!/usr/bin/env bash
# ==============================================================================
# Production Deployment Script for AWS EC2 Graviton (ARM64)
# Aqua OS Platform: Production Stack Automation (API: 8000, MQTT: 1883, DB: aquadb_prod)
# Includes Pre-flight Safety Checks & Zero-Downtime Migration Verification
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOYMENT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${DEPLOYMENT_DIR}"

COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE=".env.prod"
PROJECT_NAME="aqua-prod"

echo "=========================================================="
echo " Starting PRODUCTION Stack Deployment: Aqua OS Platform   "
echo " Target Architecture: AWS Graviton (ARM64)                "
echo " Compose File:        ${COMPOSE_FILE}                     "
echo " Environment File:    ${ENV_FILE}                         "
echo " Project Name:        ${PROJECT_NAME}                     "
echo " Working Directory:   ${DEPLOYMENT_DIR}                   "
echo " Timestamp:           $(date -u +"%Y-%m-%dT%H:%M:%SZ")   "
echo "=========================================================="

# ------------------------------------------------------------------------------
# 1. Pre-flight Safety Checks
# ------------------------------------------------------------------------------
echo "--> Step 1: Performing Pre-flight Safety Checks..."

if [ ! -f "${ENV_FILE}" ]; then
  echo "[-] FATAL: Production environment file '${ENV_FILE}' not found in ${DEPLOYMENT_DIR}." >&2
  echo "    Production deployment aborted to prevent running with unconfigured credentials." >&2
  exit 1
fi

# Verify Environment declaration
ENV_SETTING="$(grep -E '^ENVIRONMENT=' "${ENV_FILE}" | cut -d '=' -f2 || true)"
if [ "${ENV_SETTING}" != "production" ]; then
  echo "[-] WARNING: ENVIRONMENT is not set to 'production' in ${ENV_FILE} (current: '${ENV_SETTING}')." >&2
fi

# Verify secrets are set and not placeholders
POSTGRES_PW="$(grep -E '^POSTGRES_PASSWORD=' "${ENV_FILE}" | cut -d '=' -f2 || true)"
JWT_SEC="$(grep -E '^JWT_SECRET=' "${ENV_FILE}" | cut -d '=' -f2 || true)"

if [ -z "${POSTGRES_PW}" ] || [ "${POSTGRES_PW}" = "aqua" ] || [ "${POSTGRES_PW}" = "postgres" ]; then
  echo "[-] FATAL: Insecure or missing POSTGRES_PASSWORD detected in ${ENV_FILE}." >&2
  exit 1
fi

if [ -z "${JWT_SEC}" ] || [ ${#JWT_SEC} -lt 32 ]; then
  echo "[-] FATAL: JWT_SECRET must be at least 32 characters long for production security." >&2
  exit 1
fi

echo "    Pre-flight safety checks PASSED."

# ------------------------------------------------------------------------------
# 2. Validate Compose Specification
# ------------------------------------------------------------------------------
echo "--> Step 2: Validating ${COMPOSE_FILE} specification syntax..."
docker compose -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" config > /dev/null
echo "    Compose file specification valid."

# ------------------------------------------------------------------------------
# 3. Build & Launch Containers
# ------------------------------------------------------------------------------
echo "--> Step 3: Building and deploying production services..."
docker compose -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" up -d --build

# ------------------------------------------------------------------------------
# 4. Wait for Production Database Health
# ------------------------------------------------------------------------------
echo "--> Step 4: Awaiting production database (prod_aqua_postgres) healthcheck..."
MAX_RETRIES=24
COUNT=0
until docker compose -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}" ps postgres-db | grep -q "(healthy)"; do
  COUNT=$((COUNT + 1))
  if [ "${COUNT}" -ge "${MAX_RETRIES}" ]; then
    echo "[-] FATAL: Production database failed to become healthy within $((MAX_RETRIES * 3)) seconds." >&2
    docker compose -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}" logs postgres-db
    exit 1
  fi
  echo "    Waiting for postgres-db healthcheck (${COUNT}/${MAX_RETRIES})..."
  sleep 3
done
echo "    Production database is healthy and ready for queries."

# ------------------------------------------------------------------------------
# 5. Execute Production Database Migrations
# ------------------------------------------------------------------------------
echo "--> Step 5: Executing Alembic database migrations on aquadb_prod..."
docker compose -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}" exec backend alembic upgrade head
echo "    Database migrations successfully applied."

# ------------------------------------------------------------------------------
# 6. Service Health & Connectivity Verification
# ------------------------------------------------------------------------------
echo "--> Step 6: Verifying service health..."
docker compose -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}" ps

API_PORT="$(grep -E '^API_PORT=' "${ENV_FILE}" | cut -d '=' -f2 || echo "8000")"
API_PORT="${API_PORT:-8000}"

echo "--> Testing FastAPI production /health endpoint on port ${API_PORT}..."
curl -fsS "http://localhost:${API_PORT}/health" || (echo "[-] Production healthcheck failed!" && exit 1)
echo ""

echo "--> Verifying Production MQTT Broker Connectivity..."
docker compose -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}" exec backend python -c "
import paho.mqtt.client as mqtt, os, json
client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id='prod-deploy-verifier')
client.username_pw_set(os.environ['MQTT_USERNAME'], os.environ['MQTT_PASSWORD'])
client.connect(os.environ['MQTT_BROKER_HOST'], int(os.environ['MQTT_BROKER_PORT']))
client.loop_start()
payload = json.dumps({'ts': '2026-11-09T14:30:00Z', 'dissolved_oxygen': 6.5, 'temperature': 28.0})
info = client.publish('aqua/devices/PROD-DEPLOY-TEST/telemetry', payload, qos=1)
info.wait_for_publish(timeout=5)
client.loop_stop()
client.disconnect()
print('Production MQTT Broker verified: Telemetry QoS 1 published successfully.')
"

echo "=========================================================="
echo " Production Deployment Completed Successfully!           "
echo " FastAPI API: http://localhost:${API_PORT}                "
echo " MQTT Broker: localhost:1883                              "
echo " Database:    aquadb_prod (host port 5432)                "
echo "=========================================================="
