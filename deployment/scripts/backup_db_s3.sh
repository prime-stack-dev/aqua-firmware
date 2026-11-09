#!/usr/bin/env bash
# ==============================================================================
# Automated Database Backup Script (PostgreSQL / TimescaleDB to Amazon S3)
# Aqua OS Platform: Zero-Downtime Hot Backups for Production & Development
# Runs daily via Cron; streams encrypted pg_dump archives to private S3 bucket.
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOYMENT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${DEPLOYMENT_DIR}"

TIMESTAMP="$(date -u +"%Y%m%d_%H%M%S")"
DATE_DIR="$(date -u +"%Y-%m-%d")"
BACKUP_TEMP_DIR="/tmp/aqua_backups_${TIMESTAMP}"
mkdir -p "${BACKUP_TEMP_DIR}"

# Determine AWS Region & Account
AWS_REGION="${AWS_REGION:-$(aws configure get region || echo "ap-south-1")}"
AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query "Account" --output text 2>/dev/null || echo "")"

if [ -z "${AWS_ACCOUNT_ID}" ]; then
  # Fallback to IMDS if running on EC2
  AWS_ACCOUNT_ID="$(curl -s -m 2 http://169.254.169.254/latest/dynamic/instance-identity/document | jq -r .accountId || echo "000000000000")"
fi

BACKUP_BUCKET="${BACKUP_BUCKET:-aqua-backups-${AWS_ACCOUNT_ID}-${AWS_REGION}}"

echo "=========================================================="
echo " Starting Aqua OS Database S3 Backup Pipeline             "
echo " Timestamp:      ${TIMESTAMP}                             "
echo " Target Bucket:  s3://${BACKUP_BUCKET}/backups/${DATE_DIR}/ "
echo "=========================================================="

# ------------------------------------------------------------------------------
# 1. Backup Production Database (aquadb_prod)
# ------------------------------------------------------------------------------
PROD_DUMP="${BACKUP_TEMP_DIR}/aquadb_prod_${TIMESTAMP}.dump"
echo "--> Dumping production database (aquadb_prod)..."
if docker compose -p aqua-prod -f docker-compose.prod.yml ps postgres-db | grep -q "Up"; then
  docker compose -p aqua-prod -f docker-compose.prod.yml exec -T postgres-db \
    pg_dump -U "${POSTGRES_USER:-aqua_prod}" -d "${POSTGRES_DB:-aquadb_prod}" -Fc > "${PROD_DUMP}"
  echo "    Production dump created: $(du -h "${PROD_DUMP}" | cut -f1)"
else
  echo "[-] WARNING: Production postgres-db container is not running. Skipping."
fi

# ------------------------------------------------------------------------------
# 2. Backup Development Database (aquadb_dev)
# ------------------------------------------------------------------------------
DEV_DUMP="${BACKUP_TEMP_DIR}/aquadb_dev_${TIMESTAMP}.dump"
echo "--> Dumping development database (aquadb_dev)..."
if docker compose -p aqua-dev -f docker-compose.dev.yml ps postgres-db | grep -q "Up"; then
  docker compose -p aqua-dev -f docker-compose.dev.yml exec -T postgres-db \
    pg_dump -U "${POSTGRES_USER:-aqua_dev}" -d "${POSTGRES_DB:-aquadb_dev}" -Fc > "${DEV_DUMP}"
  echo "    Development dump created: $(du -h "${DEV_DUMP}" | cut -f1)"
else
  echo "[-] WARNING: Development postgres-db container is not running. Skipping."
fi

# ------------------------------------------------------------------------------
# 3. Stream Archives to Encrypted Amazon S3
# ------------------------------------------------------------------------------
echo "--> Uploading backup archives to Amazon S3..."
if ls "${BACKUP_TEMP_DIR}"/*.dump 1>/dev/null 2>&1; then
  aws s3 sync "${BACKUP_TEMP_DIR}" "s3://${BACKUP_BUCKET}/backups/${DATE_DIR}/" \
    --sse AES256 \
    --no-progress
  echo "    Upload completed successfully."
else
  echo "[-] No dumps generated. Nothing to upload."
fi

# ------------------------------------------------------------------------------
# 4. Cleanup Local Temporary Files
# ------------------------------------------------------------------------------
rm -rf "${BACKUP_TEMP_DIR}"
echo "--> Local temporary files cleaned up."

echo "=========================================================="
echo " Aqua OS Database Backup Completed Successfully!          "
echo "=========================================================="
