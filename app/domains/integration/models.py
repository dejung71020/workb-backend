# app\domains\integration\models.py
import enum

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, JSON, String, func

from app.infra.database.base import Base


class ServiceType(str, enum.Enum):
    jira = "jira"
    slack = "slack"
    notion = "notion"
    google_calendar = "google_calendar"
    kakao = "kakao"


class Integration(Base):
    __tablename__ = "integrations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False)
    service = Column(Enum(ServiceType), nullable=False)
    is_connected = Column(Boolean, default=False, nullable=False)
    access_token = Column(String(1000), nullable=True)
    refresh_token = Column(String(1000), nullable=True)
    token_expires_at = Column(DateTime, nullable=True)
    extra_config = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
