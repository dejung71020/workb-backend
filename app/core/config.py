# app\core\config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    # 1. 시스템 기본 설정
<<<<<<< HEAD
    ENV : str = "dev"
    DEBUG : bool
    RESET_DB_ON_STARTUP: bool = False
=======
    ENV: str = "dev"
    DEBUG: bool = False
>>>>>>> main
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
    SLACK_BOT_TOKEN: Optional[str] = None
    SLACK_CLIENT_ID: Optional[str] = None
    SLACK_CLIENT_SECRET: Optional[str] = None
    SLACK_REDIRECT_URI: Optional[str] = "http://localhost:8000/api/v1/integrations/slack/callback"

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
    NOTION_REDIRECT_URI: str = "http://localhost:8000/api/v1/integrations/notion/callback"

    # 7. 카카오
    KAKAO_REST_API_KEY: Optional[str] = None

    # 8. FRONTEND
    FRONTEND_URL: str = "http://localhost:5173"
    
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore'
    )

settings = Settings()