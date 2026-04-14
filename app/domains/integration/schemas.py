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
    webhook_url: Optional[str]= None # extra_config['webhook_url']에 추출

    updated_at: datetime

    class Config:
        from_attributes = True

class IntegrationListResponse(BaseModel):
    """연동 목록 응답"""
    integrations: List[IntegrationResponse]


# --- Request Schemas ---
class IntegrationConnectRequest(BaseModel):
    """
    서비스 연동 등록 요청.
    n8n 서버 주소만 입력하면 백엔드가 webhook_url 자동 조합.
    n8n_base_url = "http://localhost:5678"
    -> "http://localhost:5678/webhook/google-calendar-ws1"
    """
    n8n_base_url: str

class WebhookTestRequest(BaseModel):
    """
    Webhook_url 테스트
    """
    webhook_url: str