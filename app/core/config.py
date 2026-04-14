# app\core\config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    """
    .env 파일의 환경 변수를 읽고 관리하는 클래스
    데이터 타입 검증과 기본값 설정을 수행
    """
    # 1. 시스템 기본 설정
    ENV : str = "dev"
    DEBUG : bool
    DATABASE_URL: Optional[str] = None
    SECRET_KEY: str = "secret_key"
    ALGORITHM: str = "HS256"
    REDIS_URL: str = "redis://localhost:6379"
    MONGODB_URL: str = "mongodb://localhost:27017"
    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8000
    # 2. AI 
    OPENAI_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    TAVILY_API_KEY: Optional[str] = None

    # 3. 외부 인프라
    SLACK_WEBHOOK_URL: Optional[str] = None
    SLACK_BOT_TOKEN: Optional[str] = None
    SLACK_DEFAULT_CHANNEL_ID: Optional[str] = None

    JIRA_INSTANCE_URL: Optional[str] = None
    JIRA_API_KEY: Optional[str] = None
    JIRA_CLIENT_ID: Optional[str] = None
    JIRA_CLIENT_SECRET: Optional[str] = None
    REDIRECT_URI: str = "http://localhost:8000/api/v1/integrations/jira/callback"

    # .env 읽기 위한 설정
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore'
    )

# 전역 설정 객체 생성
settings = Settings()