#!/bin/bash
set -euxo pipefail

# ── 1. Swap — two full stacks on a 1 GB t3.micro need the headroom ───
if [ ! -f /swapfile ]; then
  dd if=/dev/zero of=/swapfile bs=1M count=6144
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
  sysctl -w vm.swappiness=60
fi

# ── 2. Install Docker, compose plugin, git, postgres client ──────────
dnf update -y
dnf install -y docker git postgresql15
systemctl enable --now docker

DOCKER_CONFIG=/usr/local/lib/docker
mkdir -p $DOCKER_CONFIG/cli-plugins
curl -SL "https://github.com/docker/compose/releases/download/v2.29.7/docker-compose-linux-x86_64" \
  -o $DOCKER_CONFIG/cli-plugins/docker-compose
chmod +x $DOCKER_CONFIG/cli-plugins/docker-compose

# ── 3. Create the second database on the shared RDS instance ─────────
# expense-forecasting uses its own database, but the same RDS server.
export PGPASSWORD='${db_pass}'
if ! psql -h ${db_host} -U ${db_user} -p 5432 -d ${db_name} -tAc \
      "SELECT 1 FROM pg_database WHERE datname='expenseforecast_db'" | grep -q 1; then
  psql -h ${db_host} -U ${db_user} -p 5432 -d ${db_name} \
    -c "CREATE DATABASE expenseforecast_db"
fi
unset PGPASSWORD

# ── 4. HealthPA: clone, fetch env, build & start ─────────────────────
APP1=/opt/${project_prefix}
rm -rf "$APP1"
git clone --branch ${git_branch} --depth 1 "${git_repo_url}" "$APP1"
aws ssm get-parameter --region ${aws_region} --name "${ssm_env_name}" \
  --with-decryption --query 'Parameter.Value' --output text > "$APP1/.env"
chmod 600 "$APP1/.env"

cd "$APP1"
docker compose -f infra/docker-compose.prod.yml up -d --build
sleep 20
docker compose -f infra/docker-compose.prod.yml exec -T api alembic upgrade head || \
  echo "WARNING: HealthPA alembic upgrade failed — run it manually (see infra/README.md)"

# ── 5. expense-forecasting: clone, fetch env, build & start ──────────
# Built AFTER HealthPA (sequential) to keep peak memory down on t3.micro.
APP2=/opt/expense
rm -rf "$APP2"
git clone --branch ${expense_git_branch} --depth 1 "${expense_git_repo_url}" "$APP2"
aws ssm get-parameter --region ${aws_region} --name "${expense_ssm_env_name}" \
  --with-decryption --query 'Parameter.Value' --output text > "$APP2/.env"
chmod 600 "$APP2/.env"

cd "$APP2"
docker compose -f infra/docker-compose.prod.yml up -d --build

# ── 6. Survive reboots: one systemd unit per app ─────────────────────
cat >/etc/systemd/system/${project_prefix}.service <<UNIT
[Unit]
Description=HealthPA stack
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$APP1
ExecStart=/usr/bin/docker compose -f infra/docker-compose.prod.yml up -d
ExecStop=/usr/bin/docker compose -f infra/docker-compose.prod.yml down

[Install]
WantedBy=multi-user.target
UNIT

cat >/etc/systemd/system/expense.service <<UNIT
[Unit]
Description=expense-forecasting stack
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$APP2
ExecStart=/usr/bin/docker compose -f infra/docker-compose.prod.yml up -d
ExecStop=/usr/bin/docker compose -f infra/docker-compose.prod.yml down

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable ${project_prefix}.service expense.service
