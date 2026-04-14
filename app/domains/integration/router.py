# app\domains\integration\router.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.infra.database.session import get_db
from app.domains.integration.models import ServiceType
from app.domains.integration.schemas import (
    IntegrationResponse,
    IntegrationListResponse,
    IntegrationConnectRequest,
    WebhookTestRequest,
)
from app.domains.integration import service

router = APIRouter()

@router.get("/workspaces/{workspace_id}", response_model=IntegrationListResponse)
async def get_integrations(workspace_id: int, db: Session = Depends(get_db)):
    """
    워크스페이스 연동 목록 전체 조회
    """
    items = service.get_integrations(db, workspace_id)

    integrations = []
    for item in items:
        webhook_url = None
        if item.extra_config:
            webhook_url = item.extra_config.get("webhook_url")  
        integrations.append(
            IntegrationResponse(
                id=item.id,
                service=item.service,
                is_connected=item.is_connected,
                webhook_url=webhook_url,
                updated_at=item.updated_at,
            )
        )
    return IntegrationListResponse(integrations=integrations)

@router.post("/workspaces/{workspace_id}/{service_name}/connect", response_model=IntegrationResponse)
async def connect_integration(
    workspace_id: int,
    service_name: ServiceType,
    body: IntegrationConnectRequest,
    db: Session = Depends(get_db),
):
    """
    서비스 연동 등록 - webhook_url 저장
    """
    item = service.connect_integration(db, workspace_id, service_name, body.n8n_base_url)
    webhook_url = item.extra_config.get("webhook_url") if item.extra_config else None
    return IntegrationResponse(
        id=item.id,
        service=item.service,
        is_connected=item.is_connected,
        webhook_url=webhook_url,
        updated_at=item.updated_at,
    )

@router.post("/workspaces/{workspace_id}/{service_name}/disconnect")
async def disconnect_integration(
    workspace_id: int,
    service_name: ServiceType,
    db: Session = Depends(get_db),
):
    """
    서비스 연동 해제
    """
    item = service.disconnect_integration(db, workspace_id, service_name)
    if not item:
        raise HTTPException(status_code=404, detail="연동 정보를 찾을 수 없습니다.")
    
    return IntegrationResponse(
        id=item.id,
        service=item.service,
        is_connected=item.is_connected,
        webhook_url=None,
        updated_at=item.updated_at,
    )

@router.post("/workspaces/{workspace_id}/{service_name}/test")
async def test_webhook(
    workspace_id: int,
    service_name: ServiceType,
    body: WebhookTestRequest,
    db: Session = Depends(get_db),
):
    """
    webhook_url 테스트
    """
    success = await service.test_webhook(body.webhook_url)
    if not success:
        raise HTTPException(status_code=400, detail="webhook 연결 실패")
    return {
        "success": True,
        "message": "webhook 연결 성공"
    }