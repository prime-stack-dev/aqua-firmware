#!/usr/bin/env bash
# Production Deployment & Verification Script for AWS EC2 Graviton (ARM64)
# Aqua OS Platform: Automated Stack Launch & Verification
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOYMENT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${DEPLOYMENT_DIR}"

echo "=========================================================="
echo " Starting Production Stack Deployment: Aqua OS Platform   "
echo " Target Architecture: AWS Graviton (ARM64)                "
echo " Working Directory: ${DEPLOYMENT_DIR}                     "
echo "=========================================================="

# 1. Validate Docker Compose Specification
echo "--> Validating docker-compose.yml specification..."
docker compose --env-file .env.production config > /dev/null

# 2. Build and Launch Containers
echo "--> Building and starting services with Docker Compose..."
docker compose --env-file .env.production up -d --build

# 3. Wait for PostgreSQL / TimescaleDB Healthy Status
echo "--> Waiting for database to become healthy..."
until docker compose ps postgres-db | grep -q "(healthy)"; do
  echo "    Waiting for postgres-db healthcheck..."
  sleep 3
done

# 4. Execute Alembic Migrations
echo "--> Running Alembic database migrations inside backend container..."
docker compose exec backend alembic upgrade head

# 5. Display Service Status and Container Health
echo "--> Checking container status..."
docker compose ps

# 6. Verify FastAPI Health Endpoint
echo "--> Testing FastAPI /health endpoint..."
curl -fsS http://localhost:8000/health || (echo "Healthcheck failed!" && exit 1)
echo ""

# 7. Verify MQTT Broker Connectivity
echo "--> Verifying MQTT broker connectivity..."
docker compose exec backend python -c "
import paho.mqtt.client as mqtt, os, json
client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id='deploy-verifier')
client.username_pw_set(os.environ['MQTT_USERNAME'], os.environ['MQTT_PASSWORD'])
client.connect(os.environ['MQTT_BROKER_HOST'], int(os.environ['MQTT_BROKER_PORT']))
client.loop_start()
payload = json.dumps({'ts': '2026-11-09T14:30:00Z', 'dissolved_oxygen': 6.5, 'temperature': 28.0})
info = client.publish('aqua/devices/SIM-00001/telemetry', payload, qos=1)
info.wait_for_publish(timeout=5)
client.loop_stop()
client.disconnect()
print('Successfully published test telemetry payload via MQTT QoS 1')
"

echo "=========================================================="
echo " Production Deployment Completed Successfully!           "
echo "=========================================================="
