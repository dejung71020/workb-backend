# app\domains\integration\schemas.py
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from app.domains.integration.models import ServiceType

# --- Response Schemas ---
class IntegrationResponse(BaseModel):
    "연동 단일 항목 응답"
    id: int
    service: ServiceType
    is_connected: bool
    selected_channel_id: Optional[str] = None
    
    updated_at: datetime

    class Config:
        from_attributes = True

class IntegrationListResponse(BaseModel):
    """연동 목록 응답"""
    integrations: List[IntegrationResponse]

# --- Request Scheams (API Key 방식) ---

class JiraConnectRequest(BaseModel):
    domain: str         # http://company.atlassian.net/
    email: str          # Atlassian 계정 이메일
    api_token: str      # Atlassian API Token
    project_key: str    # PROJ

class KakaoConnectRequest(BaseModel):
    api_key: str        # kakao REST API Key

class SlackChannelSelectRequest(BaseModel):
    channel_id: str
    
# -- OAuth Response ---

class OAuthUrlResponse(BaseModel):
    auth_url: str

# --- Slack ---
class SlackChannelItem(BaseModel):
    id: str
    name: str

class SlackChannelListResponse(BaseModel):
    channels: List[SlackChannelItem]

class TestIntegrationResponse(BaseModel):
    success: bool
    message: str

class GoogleCalendarEventItem(BaseModel):
    id: str
    title: str
    start: str
    end: str
    description: Optional[str] = None
    html_link: Optional[str] = None

class GoogleCalendarEventsResponse(BaseModel):
    events: List[GoogleCalendarEventItem]