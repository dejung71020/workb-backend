# app\core\config.py
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # 1. 시스템 기본 설정
    ENV: str = "dev"
    DEBUG: bool = False
    RESET_DB_ON_STARTUP: bool = False
    DATABASE_URL: Optional[str] = None
    SECRET_KEY: str = "secret_key"
    ALGORITHM: str = "HS256"
    REDIS_URL: str = "redis://localhost:6379"
    MONGODB_URL: str = "mongodb://localhost:27017"
    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8001

    # 2. AI
    OPENAI_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    TAVILY_API_KEY: Optional[str] = None

    # 3. Slack
    SLACK_CLIENT_ID: Optional[str] = None
    SLACK_CLIENT_SECRET: Optional[str] = None
    SLACK_REDIRECT_URI: Optional[str] = "https://localhost/api/v1/integrations/slack/callback"

    # 4. JIRA
    JIRA_INSTANCE_URL: Optional[str] = None
    JIRA_API_KEY: Optional[str] = None
    JIRA_CLIENT_ID: Optional[str] = None
    JIRA_CLIENT_SECRET: Optional[str] = None
    REDIRECT_URI: str = "http://localhost:8000/api/v1/integrations/jira/callback"

    # 5. Google
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/integrations/google/callback"

    # 6. Notion
    NOTION_CLIENT_ID: Optional[str] = None
    NOTION_CLIENT_SECRET: Optional[str] = None
    NOTION_REDIRECT_URI: str = "https://localhost/api/v1/integrations/notion/callback"

    # 7. 카카오
    KAKAO_REST_API_KEY: Optional[str] = None

    # 8. FRONTEND
    FRONTEND_URL: str = "http://localhost:5173"

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug(cls, value):
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "prod", "production", "false", "0", "no", "off"}:
                return False
            if normalized in {"debug", "dev", "development", "true", "1", "yes", "on"}:
                return True
        return value

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
