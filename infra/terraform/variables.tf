variable "aws_region" {
  description = "AWS region to deploy into. Keep it the same as your SES region."
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (dev/staging/prod)."
  type        = string
  default     = "prod"
}

variable "project_prefix" {
  description = "Prefix for all resource names so they are easy to find/delete."
  type        = string
  default     = "healthpa"
}

# ── Networking ───────────────────────────────────────────────────────
variable "vpc_cidr" {
  type    = string
  default = "10.20.0.0/16"
}

variable "ssh_allowed_cidr" {
  description = "Your public IP for SSH access, e.g. 203.0.113.4/32. Find it: curl ifconfig.me"
  type        = string
}

# ── EC2 ──────────────────────────────────────────────────────────────
variable "instance_type" {
  description = "t3.micro and t2.micro are free-tier eligible (750 hrs/mo for 12 months)."
  type        = string
  default     = "t3.micro"
}

variable "ec2_key_name" {
  description = "Name of an existing EC2 key pair for SSH. Create one in the console first, or via aws ec2 create-key-pair."
  type        = string
}

variable "root_volume_gb" {
  description = "Root EBS size. Free tier covers 30 GB gp3 total."
  type        = number
  default     = 20
}

# ── App config ───────────────────────────────────────────────────────
variable "git_repo_url" {
  description = "HTTPS clone URL of the HealthPA repo the instance will pull. For a private repo, embed a token: https://<token>@github.com/you/HealthPA.git"
  type        = string
}

variable "git_branch" {
  type    = string
  default = "main"
}

variable "domain_name" {
  description = "Optional. If you point a domain's A record at the EC2 IP, Caddy will auto-issue HTTPS. Leave empty to serve plain HTTP on port 80."
  type        = string
  default     = ""
}

# ── Database ─────────────────────────────────────────────────────────
variable "db_name" {
  type    = string
  default = "healthpa"
}

variable "db_username" {
  type    = string
  default = "healthpa_admin"
}

variable "db_password" {
  description = "RDS master password. Set in terraform.tfvars (gitignored). Min 8 chars."
  type        = string
  sensitive   = true
}

variable "db_instance_class" {
  description = "db.t3.micro / db.t4g.micro are free-tier eligible (750 hrs/mo for 12 months)."
  type        = string
  default     = "db.t3.micro"
}

variable "db_allocated_storage" {
  description = "Free tier covers 20 GB of RDS storage."
  type        = number
  default     = 20
}

# ── Application secrets (written to SSM SecureString) ─────────────────
# These mirror .env.example. Put the real values in terraform.tfvars.
variable "app_secret_key" {
  type      = string
  sensitive = true
}

variable "groq_api_key" {
  type      = string
  default   = ""
  sensitive = true
}

variable "openai_api_key" {
  type      = string
  default   = ""
  sensitive = true
}

variable "pinecone_api_key" {
  type      = string
  default   = ""
  sensitive = true
}

variable "tavily_api_key" {
  type      = string
  default   = ""
  sensitive = true
}

variable "ses_sender_email" {
  description = "A verified SES identity (email or domain)."
  type        = string
}

variable "admin_email" {
  type = string
}

# Non-secret AI knobs (override defaults if you like)
variable "chat_llm_provider" {
  type    = string
  default = "groq"
}

variable "chat_llm_model" {
  type    = string
  default = "llama-3.3-70b-versatile"
}

variable "embedding_provider" {
  type    = string
  default = "openai"
}

variable "embedding_model" {
  type    = string
  default = "text-embedding-3-small"
}

variable "embedding_dim" {
  type    = number
  default = 1536
}

variable "pinecone_index" {
  type    = string
  default = "healthpa-ai"
}
