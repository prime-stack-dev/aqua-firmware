#!/usr/bin/env bash
# ==============================================================================
# Development Deployment Script for AWS EC2 Graviton (ARM64)
# Aqua OS Platform: Dev Stack Automation (API: 8001, MQTT: 1884, DB: aquadb_dev)
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOYMENT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${DEPLOYMENT_DIR}"

COMPOSE_FILE="docker-compose.dev.yml"
ENV_FILE=".env.dev"
PROJECT_NAME="aqua-dev"

echo "=========================================================="
echo " Starting Development Stack Deployment: Aqua OS Platform  "
echo " Target Architecture: AWS Graviton (ARM64)                "
echo " Compose File:        ${COMPOSE_FILE}                     "
echo " Environment File:    ${ENV_FILE}                         "
echo " Project Name:        ${PROJECT_NAME}                     "
echo " Working Directory:   ${DEPLOYMENT_DIR}                   "
echo "=========================================================="

# 1. Pre-flight Environment Validation
if [ ! -f "${ENV_FILE}" ]; then
  echo "[-] ERROR: Missing ${ENV_FILE} configuration file in ${DEPLOYMENT_DIR}" >&2
  echo "    Please create ${ENV_FILE} with appropriate development credentials." >&2
  exit 1
fi

# 2. Validate Docker Compose Specification
echo "--> Validating ${COMPOSE_FILE} configuration..."
docker compose -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" config > /dev/null
echo "    Specification syntax OK."

# 3. Build and Launch Containers
echo "--> Building and starting development services..."
docker compose -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" up -d --build

# 4. Wait for Dev PostgreSQL / TimescaleDB Healthy Status
echo "--> Waiting for database (dev_aqua_postgres) to become healthy..."
MAX_RETRIES=24
COUNT=0
until docker compose -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}" ps postgres-db | grep -q "(healthy)"; do
  COUNT=$((COUNT + 1))
  if [ "${COUNT}" -ge "${MAX_RETRIES}" ]; then
    echo "[-] ERROR: Database failed to reach healthy state within timeout." >&2
    docker compose -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}" logs postgres-db
    exit 1
  fi
  echo "    Waiting for postgres-db healthcheck (${COUNT}/${MAX_RETRIES})..."
  sleep 3
done
echo "    Database is healthy!"

# 5. Execute Alembic Migrations on Dev Database
echo "--> Executing Alembic database migrations on aquadb_dev..."
docker compose -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}" exec backend alembic upgrade head
echo "    Migrations successfully applied."

# 6. Display Service Status
echo "--> Dev Stack Status:"
docker compose -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}" ps

# 7. Verify FastAPI Health Endpoint (Port 8001)
echo "--> Testing Dev FastAPI /health endpoint on port 8001..."
API_PORT="$(grep -E '^API_PORT=' "${ENV_FILE}" | cut -d '=' -f2 || echo "8001")"
API_PORT="${API_PORT:-8001}"
curl -fsS "http://localhost:${API_PORT}/health" || (echo "[-] Healthcheck failed on port ${API_PORT}!" && exit 1)
echo ""

echo "=========================================================="
echo " Development Deployment Completed Successfully!           "
echo " FastAPI API: http://localhost:${API_PORT}                "
echo " MQTT Broker: localhost:1884                              "
echo " Database:    aquadb_dev (host port 5433)                 "
echo "=========================================================="
