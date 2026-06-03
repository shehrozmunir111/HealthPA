"""
Core Configuration & Settings
$0 Infra Focus - Environment-based configuration
"""

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
