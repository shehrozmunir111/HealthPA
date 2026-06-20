# The entire production .env is stored as ONE encrypted SSM parameter.
# The EC2 instance reads it at boot (via its IAM role) and writes /opt/healthpa/.env.
# Nothing secret ever lives in the AMI, user_data, or git.
locals {
  # asyncpg driver + RDS endpoint. Note: alembic may need the sync URL — see infra/README.md.
  database_url = "postgresql+asyncpg://${var.db_username}:${var.db_password}@${aws_db_instance.main.address}:5432/${var.db_name}"

  cors_origins = var.domain_name != "" ? "[\"https://${var.domain_name}\"]" : "[\"*\"]"
  frontend_url = var.domain_name != "" ? "https://${var.domain_name}" : "http://${aws_eip.app.public_ip}"

  env_file = <<-EOT
    PROJECT_NAME=HealthPA
    DEBUG=False
    SECRET_KEY=${var.app_secret_key}
    ALGORITHM=HS256
    ACCESS_TOKEN_EXPIRE_MINUTES=30

    DATABASE_URL=${local.database_url}

    REDIS_URL=redis://redis:6379/0

    CORS_ORIGINS=${local.cors_origins}

    OCR_UPLOAD_DIR=data/ocr_uploads
    MAX_UPLOAD_SIZE=10485760

    AI_ENABLED=True
    CHAT_LLM_PROVIDER=${var.chat_llm_provider}
    CHAT_LLM_MODEL=${var.chat_llm_model}
    GROQ_API_KEY=${var.groq_api_key}
    OPENAI_API_KEY=${var.openai_api_key}
    CHAT_LLM_TEMPERATURE=0.0
    CHAT_MAX_TOKENS=1024

    EMBEDDING_PROVIDER=${var.embedding_provider}
    EMBEDDING_MODEL=${var.embedding_model}
    EMBEDDING_DIM=${var.embedding_dim}

    RAG_VECTOR_BACKEND=pinecone
    PINECONE_API_KEY=${var.pinecone_api_key}
    PINECONE_INDEX=${var.pinecone_index}
    PINECONE_CLOUD=aws
    PINECONE_REGION=${var.aws_region}

    HITL_CHECKPOINTER=postgres
    ENABLE_WEB_SEARCH=True
    TAVILY_API_KEY=${var.tavily_api_key}
    LANGSMITH_TRACING=False

    # No static AWS keys: boto3 uses the EC2 instance role automatically.
    AWS_SES_REGION=${var.aws_region}
    SES_SENDER_EMAIL=${var.ses_sender_email}
    ADMIN_EMAIL=${var.admin_email}
    FAILED_LOGIN_MAX_ATTEMPTS=5

    FRONTEND_URL=${local.frontend_url}
    DOMAIN=${var.domain_name}
  EOT
}

resource "aws_ssm_parameter" "env" {
  name        = "/${var.project_prefix}/env"
  description = "HealthPA production .env"
  type        = "SecureString"
  value       = local.env_file
  tier        = "Advanced" # Standard caps at 4 KB; the env file is larger.

  tags = { Name = "${var.project_prefix}-env" }
}
