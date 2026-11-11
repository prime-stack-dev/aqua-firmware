#!/usr/bin/env bash
# ==============================================================================
# Aqua OS: Staging / Dev On-Demand Wakeup Script
# Wakes up the suspended Dev stack on AWS EC2 Graviton.
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOYMENT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${DEPLOYMENT_DIR}"

COMPOSE_FILE="docker-compose.dev.yml"
ENV_FILE=".env.dev"
PROJECT_NAME="aqua-dev"

echo "=========================================================="
echo " Waking up Staging/Dev Stack: Aqua OS Platform            "
echo " Project Name:  ${PROJECT_NAME}                           "
echo " Compose File:  ${COMPOSE_FILE}                           "
echo " Env File:      ${ENV_FILE}                               "
echo " Timestamp:     $(date -u +"%Y-%m-%dT%H:%M:%SZ")          "
echo "=========================================================="

if [ ! -f "${ENV_FILE}" ]; then
  echo "[-] ERROR: Missing ${ENV_FILE} configuration file in ${DEPLOYMENT_DIR}" >&2
  exit 1
fi

EXISTING_CONTAINERS="$(docker compose -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}" ps -q 2>/dev/null || true)"

if [ -n "${EXISTING_CONTAINERS}" ]; then
  echo "--> Resuming existing stopped containers..."
  docker compose -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" start
else
  echo "--> No stopped containers found. Starting stack up in background..."
  docker compose -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" up -d
fi

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
  sleep 2
done

echo "--> Waiting for backend (dev_aqua_backend) to become healthy..."
COUNT=0
until docker compose -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}" ps backend | grep -q "(healthy)"; do
  COUNT=$((COUNT + 1))
  if [ "${COUNT}" -ge "${MAX_RETRIES}" ]; then
    echo "[-] ERROR: Backend failed to reach healthy state within timeout." >&2
    docker compose -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}" logs backend
    exit 1
  fi
  echo "    Waiting for backend healthcheck (${COUNT}/${MAX_RETRIES})..."
  sleep 2
done

API_PORT="$(grep -E '^API_PORT=' "${ENV_FILE}" | cut -d '=' -f2 || echo "8001")"
API_PORT="${API_PORT:-8001}"
echo "--> Verifying Dev FastAPI /health endpoint on port ${API_PORT}..."
curl -fsS "http://localhost:${API_PORT}/health" || (echo "[-] Healthcheck failed on port ${API_PORT}!" && exit 1)
echo ""

echo "=========================================================="
echo " Staging/Dev Environment Active!                          "
echo " FastAPI API:  http://localhost:${API_PORT}               "
echo " Swagger Docs: http://localhost:${API_PORT}/docs          "
echo " MQTT Broker:  localhost:1884                             "
echo " Database:     aquadb_dev (host port 5433)                "
echo " Stop Command: ./deployment/scripts/stop_dev.sh           "
echo "=========================================================="
