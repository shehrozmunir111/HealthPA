#!/bin/bash
set -euxo pipefail

# ── 1. Install Docker, compose plugin, git ───────────────────────────
dnf update -y
dnf install -y docker git
systemctl enable --now docker

DOCKER_CONFIG=/usr/local/lib/docker
mkdir -p $DOCKER_CONFIG/cli-plugins
curl -SL "https://github.com/docker/compose/releases/download/v2.29.7/docker-compose-linux-x86_64" \
  -o $DOCKER_CONFIG/cli-plugins/docker-compose
chmod +x $DOCKER_CONFIG/cli-plugins/docker-compose

# ── 2. Pull the application code ──────────────────────────────────────
APP_DIR=/opt/${project_prefix}
rm -rf "$APP_DIR"
git clone --branch ${git_branch} --depth 1 "${git_repo_url}" "$APP_DIR"

# ── 3. Fetch the .env from SSM (decrypted via the instance role) ──────
aws ssm get-parameter \
  --region ${aws_region} \
  --name "${ssm_env_name}" \
  --with-decryption \
  --query 'Parameter.Value' \
  --output text > "$APP_DIR/.env"
chmod 600 "$APP_DIR/.env"

# ── 4. Build & start the stack ───────────────────────────────────────
cd "$APP_DIR"
docker compose -f infra/docker-compose.prod.yml up -d --build

# ── 5. Run database migrations once the DB is reachable ──────────────
sleep 20
docker compose -f infra/docker-compose.prod.yml exec -T api alembic upgrade head || \
  echo "WARNING: alembic upgrade failed — run it manually (see infra/README.md)"

# ── 6. Survive reboots ───────────────────────────────────────────────
cat >/etc/systemd/system/${project_prefix}.service <<UNIT
[Unit]
Description=HealthPA stack
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$APP_DIR
ExecStart=/usr/local/lib/docker/cli-plugins/docker-compose -f infra/docker-compose.prod.yml up -d
ExecStop=/usr/local/lib/docker/cli-plugins/docker-compose -f infra/docker-compose.prod.yml down

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable ${project_prefix}.service
