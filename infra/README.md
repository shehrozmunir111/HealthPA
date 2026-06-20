# Deploying HealthPA to AWS with Terraform

A free-tier-friendly, production-shaped deployment you can put on your résumé.

## What you get

```
                    ┌──────────────────────────── AWS VPC ────────────────────────────┐
   Internet ──►  Caddy (:80/:443, auto-HTTPS)                                          │
                    │     ├── serves the built React/Vite frontend                     │
                    │     └── /api/*  ─► FastAPI (uvicorn)  ─┐                          │
                    │                    Celery worker + beat │  ── all on ONE EC2      │
                    │                    Redis                │     t3.micro (free tier)│
                    │                                         └─► RDS PostgreSQL        │
                    │                                             (private subnet)      │
                    │   EC2 IAM role ─► SES (email), S3 (uploads), SSM (secrets)        │
                    └──────────────────────────────────────────────────────────────────┘
```

| Concern | How it's handled | Résumé talking point |
|---|---|---|
| Infra | 100% Terraform | "Infrastructure as Code" |
| Secrets | SSM Parameter Store (SecureString) + EC2 IAM role | "No static credentials; least-privilege IAM" |
| DB | Managed RDS, private subnet, SG-locked | "Managed Postgres, network isolation" |
| TLS | Caddy auto-issues Let's Encrypt | "Automated HTTPS" |
| Email | SES via instance role | "Transactional email on SES" |
| Reboots | systemd unit restarts the stack | "Self-healing host" |

**Cost:** $0 for ~12 months on a new AWS account (t3.micro EC2, db.t3.micro RDS, S3, SES all free-tier). After 12 months roughly $15–20/mo. The Elastic IP is free *while attached to a running instance*.

---

## Prerequisites (one-time)

1. **AWS account** + [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) configured:
   ```bash
   aws configure          # paste an admin Access Key / Secret
   aws sts get-caller-identity   # confirm it works
   ```
2. **Terraform** ≥ 1.5 — https://developer.hashicorp.com/terraform/install
3. **Verify SES** so email actually sends:
   ```bash
   aws ses verify-email-identity --email-address noreply@yourdomain.com --region us-east-1
   # click the link in the email AWS sends you
   ```
   New SES accounts are in *sandbox mode* — you can only send TO verified addresses. Verify your test recipients too, or request production access in the SES console.
4. **Create an EC2 key pair** (for SSH), save the .pem somewhere safe:
   ```bash
   aws ec2 create-key-pair --key-name healthpa-key \
     --query 'KeyMaterial' --output text > healthpa-key.pem
   chmod 600 healthpa-key.pem
   ```
5. **Push this repo to GitHub** (the EC2 host clones it). Private repo? Create a fine-grained PAT and use `https://<TOKEN>@github.com/you/HealthPA.git` as `git_repo_url`.

---

## Deploy

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars`:
- `ssh_allowed_cidr` → `curl ifconfig.me` then add `/32`
- `ec2_key_name` → `healthpa-key`
- `git_repo_url` → your repo URL
- `db_password`, `app_secret_key` (`python -c "import secrets; print(secrets.token_hex(32))"`)
- `groq_api_key`, `openai_api_key`, `pinecone_api_key`, `ses_sender_email`, `admin_email`

Then:

```bash
terraform init
terraform plan      # review what will be created (~25 resources)
terraform apply     # type "yes"
```

RDS takes ~5–10 min. When it finishes you'll see outputs:

```
app_url  = "http://<elastic-ip>"
ssh_command = "ssh -i <your-key>.pem ec2-user@<elastic-ip>"
```

The EC2 user_data script then needs ~3–5 min to install Docker, clone the repo, build images, run migrations, and start everything. Watch it:

```bash
ssh -i healthpa-key.pem ec2-user@<elastic-ip>
sudo tail -f /var/log/cloud-init-output.log     # bootstrap progress
cd /opt/healthpa && sudo docker compose -f infra/docker-compose.prod.yml ps
```

Open `app_url` in a browser. Done. 🎉

---

## Add a domain + HTTPS (optional, recommended)

1. In your DNS provider, add an **A record** → the `app_public_ip` output.
2. Set `domain_name = "app.yourdomain.com"` in `terraform.tfvars`.
3. `terraform apply` (this updates the SSM env + re-bootstraps the host).

Caddy will automatically obtain a Let's Encrypt certificate. Your app is now on `https://app.yourdomain.com`.

---

## Day-2 operations

**Change a secret / config:** edit the SSM parameter, then re-pull on the host.
```bash
# easiest: change the value in terraform.tfvars then `terraform apply`
# then on the host:
ssh -i healthpa-key.pem ec2-user@<ip>
cd /opt/healthpa
sudo aws ssm get-parameter --region us-east-1 --name /healthpa/env \
  --with-decryption --query 'Parameter.Value' --output text | sudo tee .env >/dev/null
sudo docker compose -f infra/docker-compose.prod.yml up -d
```

**Deploy new code:**
```bash
ssh -i healthpa-key.pem ec2-user@<ip>
cd /opt/healthpa
sudo git pull
sudo docker compose -f infra/docker-compose.prod.yml up -d --build
sudo docker compose -f infra/docker-compose.prod.yml exec -T api alembic upgrade head
```

**Logs:**
```bash
sudo docker compose -f infra/docker-compose.prod.yml logs -f api
sudo docker compose -f infra/docker-compose.prod.yml logs -f celery_worker
```

**Migrations manually** (if the boot-time run failed):
```bash
sudo docker compose -f infra/docker-compose.prod.yml exec -T api alembic upgrade head
```

---

## Tear down (stop all billing)

```bash
cd infra/terraform
terraform destroy      # type "yes"
```
This deletes EC2, RDS, S3, IAM, VPC — everything. (Empty the S3 bucket first if `destroy` complains about a non-empty bucket.)

---

## Level up: CI/CD with GitHub Actions

Instead of SSHing to deploy, add `.github/workflows/deploy.yml` that, on push to `main`:
1. SSH into the host (store the .pem and IP as repo secrets), or
2. Better: build images in CI → push to **Amazon ECR** → host pulls.

Ask me and I'll generate this workflow + the ECR Terraform.

---

## Notes & gotchas

- **Single instance = single point of failure.** Fine for a portfolio/demo. For real HA you'd move to ECS Fargate behind an ALB with ≥2 tasks — costs money, not free tier. The Terraform here is intentionally the cheap-but-real version.
- **Celery beat** stores its schedule in `/tmp` inside the container; fine for one instance.
- **OCR uploads** currently live on the EC2 EBS volume. To use the S3 bucket instead, point your storage code at the `uploads_bucket` output (the instance role already has access).
- **Free-tier guardrails:** RDS storage autoscaling is disabled and Multi-AZ is off on purpose so you can't silently leave the free tier. Set up an [AWS Budgets](https://console.aws.amazon.com/billing/home#/budgets) alert at $1 for peace of mind.
- **boto3 + instance role:** the production `.env` ships with empty AWS keys on purpose — boto3 picks up the EC2 role automatically, so no long-lived keys exist anywhere.
