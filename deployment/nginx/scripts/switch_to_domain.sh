#!/usr/bin/env bash
# ==============================================================================
# Aqua OS Platform: Automatic Domain Setup & Let's Encrypt SSL Provisioning
# Usage: sudo ./switch_to_domain.sh <DOMAIN> <ADMIN_EMAIL>
# Example: sudo ./switch_to_domain.sh aquaos.com admin@aquaos.com
# ==============================================================================
set -euo pipefail

if [ "$#" -lt 2 ]; then
  echo "[-] ERROR: Missing required arguments."
  echo "    Usage: sudo $0 <DOMAIN> <ADMIN_EMAIL>"
  echo "    Example: sudo $0 aquaos.com devops@aquaos.com"
  exit 1
fi

DOMAIN="$1"
ADMIN_EMAIL="$2"
PROD_DOMAIN="api.${DOMAIN}"
DEV_DOMAIN="api-dev.${DOMAIN}"

echo "=========================================================="
echo " Upgrading Aqua OS Nginx to Dedicated Domain with SSL      "
echo " Production Domain:  ${PROD_DOMAIN}                       "
echo " Development Domain: ${DEV_DOMAIN}                        "
echo " Admin Email:        ${ADMIN_EMAIL}                       "
echo "=========================================================="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NGINX_CONF_DIR="/etc/nginx/sites-available"
TEMPLATE_FILE="$(cd "${SCRIPT_DIR}/../conf.d" && pwd)/aqua_domain.conf.template"

# 1. Obtain Let's Encrypt SSL Certificates using Certbot
echo "--> Requesting Let's Encrypt certificates for ${PROD_DOMAIN} and ${DEV_DOMAIN}..."
certbot certonly --nginx \
  --non-interactive \
  --agree-tos \
  --email "${ADMIN_EMAIL}" \
  -d "${PROD_DOMAIN}" \
  -d "${DEV_DOMAIN}"

# 2. Render Nginx Configuration from Template
echo "--> Generating Nginx configuration file..."
sed -e "s/api\.YOUR_DOMAIN\.com/${PROD_DOMAIN}/g" \
    -e "s/api-dev\.YOUR_DOMAIN\.com/${DEV_DOMAIN}/g" \
    -e "s/YOUR_DOMAIN\.com/${DOMAIN}/g" \
    "${TEMPLATE_FILE}" > "${NGINX_CONF_DIR}/aqua"

# 3. Test and Reload Nginx
echo "--> Testing Nginx configuration..."
nginx -t
systemctl reload nginx

echo "=========================================================="
echo " Domain & SSL Setup Complete!                              "
echo " Production API:  https://${PROD_DOMAIN}                  "
echo " Development API: https://${DEV_DOMAIN}                   "
echo "=========================================================="
