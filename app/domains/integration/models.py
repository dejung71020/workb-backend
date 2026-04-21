# app\domains\integration\models.py
from sqlalchemy import Column, BigInteger, String, Enum, DateTime, Boolean, ForeignKey, Text, JSON, func
from app.infra.database.base import Base
import enum

class ServiceType(str, enum.Enum):
    jira             = "jira"
    slack            = "slack"
    notion           = "notion"
    google_calendar  = "google_calendar"
    kakao            = "kakao"

class Integration(Base):
    __tablename__ = "integrations"

    id               = Column(BigInteger, primary_key=True, autoincrement=True)
    workspace_id     = Column(BigInteger, ForeignKey("workspaces.id"), nullable=False)
    service          = Column(Enum(ServiceType), nullable=False)
    access_token     = Column(Text, nullable=True)
    refresh_token    = Column(Text, nullable=True)
    token_expires_at = Column(DateTime, nullable=True)
    extra_config     = Column(JSON, nullable=True)
    is_connected     = Column(Boolean, default=False)
    updated_at       = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)