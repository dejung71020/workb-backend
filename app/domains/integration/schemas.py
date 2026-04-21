# app\domains\integration\schemas.py
from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.domains.integration.models import ServiceType


class IntegrationResponse(BaseModel):
    id: int
    service: ServiceType
    is_connected: bool
    selected_channel_id: Optional[str] = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class IntegrationItemResponse(IntegrationResponse):
    pass


class IntegrationListResponse(BaseModel):
    integrations: list[IntegrationResponse]


class JiraConnectRequest(BaseModel):
    domain: str
    email: str
    api_token: str
    project_key: str


class KakaoConnectRequest(BaseModel):
    api_key: str


class SlackChannelSelectRequest(BaseModel):
    channel_id: str


class OAuthUrlResponse(BaseModel):
    auth_url: str
