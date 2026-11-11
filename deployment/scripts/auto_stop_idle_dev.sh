#!/usr/bin/env bash
# ==============================================================================
# Aqua OS: Automatic Idle Hibernation Script for Staging / Dev
# Detects lack of developer/testing activity and stops Dev stack to save resources.
# Default Idle Threshold: 120 minutes (2 hours)
# Can be run via crontab: */30 * * * * /opt/aqua-firmware/deployment/scripts/auto_stop_idle_dev.sh >> /var/log/aqua_idle_dev.log 2>&1
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOYMENT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${DEPLOYMENT_DIR}"

IDLE_MINUTES="${1:-120}"
CONTAINER_NAME="dev_aqua_backend"

# 1. Check if Dev stack is running
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
  # Already stopped / hibernated; no action needed
  exit 0
fi

echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Checking activity for ${CONTAINER_NAME} over the last ${IDLE_MINUTES} minutes..."

# 2. Check for recent real API activity (excluding internal healthcheck polls)
RECENT_REQUESTS="$(docker logs "${CONTAINER_NAME}" --since "${IDLE_MINUTES}m" 2>&1 | grep -E "GET|POST|PUT|PATCH|DELETE" | grep -v "/health" | wc -l || true)"

# 3. Check for active TCP connections on Dev API port (8001) or MQTT port (1884)
ACTIVE_CONNECTIONS=0
if command -v ss >/dev/null 2>&1; then
  ACTIVE_CONNECTIONS="$(ss -tan '( sport = :8001 or sport = :1884 )' | grep -v "State" | grep -c "ESTAB" || true)"
elif command -v netstat >/dev/null 2>&1; then
  ACTIVE_CONNECTIONS="$(netstat -tan | grep -E ":8001|:1884" | grep -c "ESTABLISHED" || true)"
fi

echo "    Active non-healthcheck HTTP requests in past ${IDLE_MINUTES}m: ${RECENT_REQUESTS}"
echo "    Active established TCP connections on Dev ports: ${ACTIVE_CONNECTIONS}"

if [ "${RECENT_REQUESTS}" -eq 0 ] && [ "${ACTIVE_CONNECTIONS}" -eq 0 ]; then
  echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Staging/Dev environment has been idle for >${IDLE_MINUTES} minutes. Halting stack..."
  "${SCRIPT_DIR}/stop_dev.sh"
  echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Auto-hibernation complete. 100% EC2 resources reserved for Production."
else
  echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Staging/Dev is actively in use. Leaving stack running."
fi
