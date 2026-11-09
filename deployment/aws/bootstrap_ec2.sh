#!/usr/bin/env bash
# ==============================================================================
# AWS EC2 Graviton (ARM64) User-Data Bootstrap Script
# Aqua OS Platform: Automated Host OS Hardening & Toolchain Provisioning
# Target OS: Ubuntu 24.04 LTS / 22.04 LTS (aarch64) on AWS EC2 Graviton
# ==============================================================================
set -euo pipefail
IFS=$'\n\t'

exec > >(tee -a /var/log/aqua_bootstrap.log) 2>&1
echo "=========================================================="
echo " Starting Aqua OS EC2 Graviton Bootstrap                  "
echo " Architecture: $(uname -m)                                "
echo " Kernel:       $(uname -r)                                "
echo " Date:         $(date -u +"%Y-%m-%dT%H:%M:%SZ")           "
echo "=========================================================="

export DEBIAN_FRONTEND=noninteractive

# ------------------------------------------------------------------------------
# 1. System Package Updates & Prerequisites
# ------------------------------------------------------------------------------
echo "--> [1/9] Updating system packages and installing baseline tools..."
apt-get update -y
apt-get upgrade -y -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold"
apt-get install -y \
  ca-certificates \
  curl \
  gnupg \
  lsb-release \
  jq \
  git \
  ufw \
  htop \
  net-tools \
  unzip \
  tar \
  gzip \
  nginx \
  certbot \
  python3-certbot-nginx

# ------------------------------------------------------------------------------
# 2. Swap Memory Allocation (4GB on EBS gp3 / NVMe)
# Essential for t4g.small/medium to prevent Linux OOM Killer on DB containers
# ------------------------------------------------------------------------------
echo "--> [2/9] Configuring 4GB Swap Space..."
SWAPFILE="/swapfile"
if [ ! -f "${SWAPFILE}" ]; then
  echo "    Allocating 4GB swapfile..."
  fallocate -l 4G "${SWAPFILE}" || dd if=/dev/zero of="${SWAPFILE}" bs=1M count=4096
  chmod 600 "${SWAPFILE}"
  mkswap "${SWAPFILE}"
  swapon "${SWAPFILE}"
  
  if ! grep -q "${SWAPFILE}" /etc/fstab; then
    echo "${SWAPFILE} none swap sw 0 0" >> /etc/fstab
  fi
  
  # Optimize kernel swappiness (prioritize keeping active database pages in RAM)
  sysctl vm.swappiness=10
  sysctl vm.vfs_cache_pressure=50
  cat << 'EOF' > /etc/sysctl.d/99-aqua-memory.conf
vm.swappiness=10
vm.vfs_cache_pressure=50
EOF
  echo "    Swap space created and tuned successfully."
else
  echo "    Swapfile already exists. Skipping."
fi

# ------------------------------------------------------------------------------
# 3. Docker Log Daemon Hardening
# Limits container logs to 50MB x 3 files to prevent EBS root disk saturation
# ------------------------------------------------------------------------------
echo "--> [3/9] Hardening Docker daemon configuration (log rotation)..."
mkdir -p /etc/docker
cat << 'EOF' > /etc/docker/daemon.json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "50m",
    "max-file": "3"
  },
  "default-ulimits": {
    "nofile": {
      "Name": "nofile",
      "Hard": 65535,
      "Soft": 65535
    }
  }
}
EOF

# ------------------------------------------------------------------------------
# 4. Install Docker Engine & Compose Plugin (ARM64 Official Repo)
# ------------------------------------------------------------------------------
echo "--> [4/9] Installing Docker Engine (aarch64) from official Docker repos..."
mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg --yes

ARCH="$(dpkg --print-architecture)"
CODENAME="$(lsb_release -cs)"
echo "deb [arch=${ARCH} signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${CODENAME} stable" > /etc/apt/sources.list.d/docker.list

apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

systemctl daemon-reload
systemctl enable --now docker

# Add 'ubuntu' non-root user to docker group
if id "ubuntu" &>/dev/null; then
  usermod -aG docker ubuntu
  echo "    Added user 'ubuntu' to docker group."
fi

# ------------------------------------------------------------------------------
# 5. Install AWS CLI v2 (ARM64 / aarch64)
# ------------------------------------------------------------------------------
echo "--> [5/9] Installing AWS CLI v2 for ARM64..."
if ! command -v aws &>/dev/null; then
  cd /tmp
  curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-aarch64.zip" -o "awscliv2.zip"
  unzip -q awscliv2.zip
  ./aws/install --update
  rm -rf aws awscliv2.zip
  echo "    AWS CLI installed: $(aws --version)"
else
  echo "    AWS CLI already installed: $(aws --version)"
fi

# ------------------------------------------------------------------------------
# 6. Ensure AWS SSM Agent is Active (Zero-Trust CLI Access)
# ------------------------------------------------------------------------------
echo "--> [6/9] Verifying AWS Systems Manager (SSM) Agent..."
if snap list amazon-ssm-agent &>/dev/null; then
  systemctl enable --now snap.amazon-ssm-agent.amazon-ssm-agent.service || true
elif command -v amazon-ssm-agent &>/dev/null; then
  systemctl enable --now amazon-ssm-agent || true
else
  echo "    Installing SSM Agent via snap..."
  snap install amazon-ssm-agent --classic || true
  systemctl enable --now snap.amazon-ssm-agent.amazon-ssm-agent.service || true
fi

# ------------------------------------------------------------------------------
# 7. Self-Signed SSL Certificate Generation (Fallback for IP-based HTTPS)
# ------------------------------------------------------------------------------
echo "--> [7/9] Generating fallback self-signed SSL certificate for IP access..."
SSL_DIR="/etc/ssl/aqua"
mkdir -p "${SSL_DIR}"
if [ ! -f "${SSL_DIR}/selfsigned.crt" ]; then
  openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout "${SSL_DIR}/selfsigned.key" \
    -out "${SSL_DIR}/selfsigned.crt" \
    -subj "/C=US/ST=State/L=City/O=AquaOS/OU=DevOps/CN=aquaos-ec2-fallback"
  chmod 600 "${SSL_DIR}/selfsigned.key"
  echo "    Self-signed certificate generated at ${SSL_DIR}."
fi

# ------------------------------------------------------------------------------
# 8. Configure Nginx Reverse Proxy (IP-Based Routing for Dev & Prod)
# ------------------------------------------------------------------------------
echo "--> [8/9] Deploying Nginx reverse proxy configuration..."
cat << 'EOF' > /etc/nginx/sites-available/aqua
# ==============================================================================
# Aqua OS Platform: Reverse Proxy Configuration (IP & Domain Routing)
# Routing Strategy (Without Dedicated Domain):
#   - Port 80 / 443 (default): Routes to Production API (http://127.0.0.1:8000)
#   - Port 80 / 443 (path /dev/): Routes to Development API (http://127.0.0.1:8001)
#   - Port 8080: Directly routes to Development API (http://127.0.0.1:8001)
# ==============================================================================

# --- Upstream Definitions ---
upstream aqua_prod_backend {
    server 127.0.0.1:8000;
    keepalive 32;
}

upstream aqua_dev_backend {
    server 127.0.0.1:8001;
    keepalive 16;
}

# --- HTTP Server (Port 80) ---
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

    client_max_body_size 20M;

    # Gzip Compression
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml;
    gzip_min_length 1000;

    # Security Headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Development API Route (Path-based: /dev/)
    location /dev/ {
        rewrite ^/dev/(.*) /$1 break;
        proxy_pass http://aqua_dev_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
        proxy_connect_timeout 10s;
    }

    # Production API Route (Default: /)
    location / {
        proxy_pass http://aqua_prod_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
        proxy_connect_timeout 10s;
    }
}

# --- HTTPS Server (Port 443 with Fallback SSL) ---
server {
    listen 443 ssl default_server;
    listen [::]:443 ssl default_server;
    server_name _;

    ssl_certificate /etc/ssl/aqua/selfsigned.crt;
    ssl_certificate_key /etc/ssl/aqua/selfsigned.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    client_max_body_size 20M;

    # Security Headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Development API Route (/dev/)
    location /dev/ {
        rewrite ^/dev/(.*) /$1 break;
        proxy_pass http://aqua_dev_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }

    # Production API Route (Default)
    location / {
        proxy_pass http://aqua_prod_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }
}

# --- Development API Port (Port 8080 Dedicated Ingress) ---
server {
    listen 8080;
    listen [::]:8080;
    server_name _;

    location / {
        proxy_pass http://aqua_dev_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }
}
EOF

# Activate site and remove default
rm -f /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/aqua /etc/nginx/sites-enabled/aqua

nginx -t
systemctl restart nginx
systemctl enable nginx

# ------------------------------------------------------------------------------
# 9. Host Firewall & Target Working Directory
# ------------------------------------------------------------------------------
echo "--> [9/9] Setting up UFW firewall and working directory..."
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment "SSH"
ufw allow 80/tcp comment "HTTP Ingress"
ufw allow 443/tcp comment "HTTPS Ingress"
ufw allow 8080/tcp comment "Dev API Ingress"
ufw allow 1883/tcp comment "Production MQTT Broker"
ufw allow 1884/tcp comment "Development MQTT Broker"
ufw --force enable

# Prepare standard project directory
mkdir -p /opt/aqua-firmware
if id "ubuntu" &>/dev/null; then
  chown -R ubuntu:ubuntu /opt/aqua-firmware
fi

echo "=========================================================="
echo " Aqua OS EC2 Graviton Bootstrap Completed Successfully!   "
echo " Host is configured for Docker, Compose, Swap, and Nginx. "
echo "=========================================================="
