#!/usr/bin/env bash
# ==============================================================================
# Aqua OS: Staging / Dev On-Demand Hibernation Script
# Suspends all Dev containers to free 100% CPU & Memory for Production.
# Preserves all database volumes (pgdata_dev) and container configurations.
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOYMENT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${DEPLOYMENT_DIR}"

COMPOSE_FILE="docker-compose.dev.yml"
PROJECT_NAME="aqua-dev"

echo "=========================================================="
echo " Halting Staging/Dev Stack: Aqua OS Platform             "
echo " Project Name:  ${PROJECT_NAME}                           "
echo " Compose File:  ${COMPOSE_FILE}                           "
echo " Timestamp:     $(date -u +"%Y-%m-%dT%H:%M:%SZ")          "
echo "=========================================================="

echo "--> Stopping development containers..."
docker compose -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}" stop

echo "--> Verifying container states..."
docker compose -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}" ps -a

echo ""
echo "=========================================================="
echo " Staging/Dev Environment Successfully Hibernated!         "
echo " Host RAM & CPU Freed: 100% for 24/7 Production Stack    "
echo " Persistent Volumes (pgdata_dev, redis_data_dev): Intact  "
echo " Resume Command: ./deployment/scripts/start_dev.sh        "
echo "=========================================================="
