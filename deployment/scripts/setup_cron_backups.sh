#!/usr/bin/env bash
# ==============================================================================
# Aqua OS Platform: Automated Daily Database Backup Cron Job Setup
# Installs a daily cron job at 02:00 UTC to backup aquadb_prod & aquadb_dev to S3
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_SCRIPT="${SCRIPT_DIR}/backup_db_s3.sh"

chmod +x "${BACKUP_SCRIPT}"

CRON_JOB="0 2 * * * ${BACKUP_SCRIPT} >> /var/log/aqua_db_backup.log 2>&1"

# Check if cron job is already installed
if crontab -l 2>/dev/null | grep -Fq "${BACKUP_SCRIPT}"; then
  echo "--> Aqua OS database backup cron job is already installed."
else
  (crontab -l 2>/dev/null || true; echo "${CRON_JOB}") | crontab -
  echo "--> Aqua OS database backup cron job installed successfully:"
  echo "    Schedule: Daily at 02:00 UTC"
  echo "    Log File: /var/log/aqua_db_backup.log"
fi
