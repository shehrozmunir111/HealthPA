from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    """Application settings with environment variable support."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    # Project
    PROJECT_NAME: str = "HealthPA"
    VERSION: str = "0.1.0"
    DEBUG: bool = True
    
    # Security
    SECRET_KEY: str = "change-this-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/healthpa"
    TEST_DATABASE_URL: str = ""
    TEST_DATABASE_SCHEMA: str = "healthpa_test"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]
    
    # File Storage
    OCR_UPLOAD_DIR: str = "data/ocr_uploads"
    MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024  # 10MB
    
    # AI/OpenRouter
    OPENROUTER_API_KEY: str = ""
    
    # AI/Groq
    GROQ_API_KEY: str = ""

    # AI Layer (LangGraph / RAG / HITL)
    # Master switch; when False the grounded layer falls back to the rule/LLM extractor.
    AI_ENABLED: bool = True

    # Chat provider: openai/lmstudio (OpenAI-compatible), groq, or anthropic.
    CHAT_LLM_PROVIDER: str = "openai"
    CHAT_LLM_MODEL: str = "google/gemma-4-12b-qat"
    LLM_BASE_URL: str = "http://localhost:1234/v1"   # LM Studio; "" for cloud
    OPENAI_API_KEY: str = ""                          # falls back to "lm-studio"
    ANTHROPIC_API_KEY: str = ""
    CHAT_LLM_TEMPERATURE: float = 0.0
    CHAT_MAX_TOKENS: int = 1024
    CHAT_LLM_TIMEOUT: int = 60

    # claude_cli provider: use the local Claude Code CLI as the LLM (set CHAT_LLM_PROVIDER=claude_cli; local only, not AWS).
    CLAUDE_CLI_COMMAND: str = "claude"
    CLAUDE_CLI_MODEL: str = "haiku"
    CLAUDE_CLI_DISABLE_THINKING: bool = True

    # Embeddings provider: openai/lmstudio (nomic, 768-dim) or local (hashing, offline/tests).
    EMBEDDING_PROVIDER: str = "openai"
    EMBEDDING_MODEL: str = "text-embedding-nomic-embed-text-v1.5"
    EMBEDDING_BASE_URL: str = ""                       # falls back to LLM_BASE_URL
    EMBEDDING_DIM: int = 768                            # nomic; Pinecone index dim

    # Vector store backend: "pinecone" (prod) | "memory" (tests/offline)
    RAG_VECTOR_BACKEND: str = "pinecone"
    PINECONE_API_KEY: str = ""
    PINECONE_INDEX: str = "healthpa-ai"
    PINECONE_CLOUD: str = "aws"
    PINECONE_REGION: str = "us-east-1"

    # Per-hospital corpus fingerprint cache (skip re-embed when corpus unchanged).
    RAG_STATE_DIR: str = "data/rag_state"

    # Root dir for policy source documents, read per-hospital from "{POLICY_DOCS_DIR}/{hospital_id}/".
    POLICY_DOCS_DIR: str = "data/policies"

    # Retrieval / RAG tuning
    RAG_CHUNK_SIZE: int = 1000
    RAG_CHUNK_OVERLAP: int = 150
    RAG_FETCH_K: int = 12          # candidates pulled before rerank
    RAG_TOP_K: int = 4            # chunks kept after rerank
    RAG_RERANK: bool = True
    RAG_RERANK_LLM: bool = False   # lexical by default; LLM reranker optional
    CHAT_MAX_REWRITES: int = 1     # adaptive-RAG rewrite attempts

    # Long-term (per-coder/hospital) memory
    LONG_TERM_MEMORY: bool = True

    # HITL checkpointer: "postgres" (durable, survives restart) | "memory"
    HITL_CHECKPOINTER: str = "postgres"

    # Web search tool for the policy-QA agent (non-authoritative; not used for code grounding).
    ENABLE_WEB_SEARCH: bool = True
    TAVILY_API_KEY: str = ""

    # Observability (env-gated; forced off in tests)
    LANGSMITH_TRACING: bool = False
    LANGSMITH_PROJECT: str = "HealthPA-AI"
    LANGSMITH_ENDPOINT: str = "https://api.smith.langchain.com"
    LANGSMITH_API_KEY: str = ""

    # Webhooks
    WEBHOOK_URLS: str = ""

    # AWS SES — Email
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_SES_REGION: str = "us-east-1"
    SES_SENDER_EMAIL: str = "noreply@example.com"

    # Admin alert email (receives fraud/lockout notifications)
    ADMIN_EMAIL: str = ""

    # Account lockout threshold
    FAILED_LOGIN_MAX_ATTEMPTS: int = 5

    # Frontend base URL (used in email links)
    FRONTEND_URL: str = "http://localhost:3000"

    @property
    def sync_database_url(self) -> str:
        """Get synchronous database URL for Alembic."""
        return self.DATABASE_URL.replace("+asyncpg", "")

    @property
    def effective_test_database_url(self) -> str:
        """Get the PostgreSQL database URL used for tests."""
        if self.TEST_DATABASE_URL:
            return self.TEST_DATABASE_URL
        return make_url(self.DATABASE_URL).render_as_string(hide_password=False)


@lru_cache()
def get_settings() -> Settings:
    """Cached settings instance."""
    return Settings()


settings = get_settings()
