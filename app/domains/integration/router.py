# app\domains\integration\router.py
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from typing import List

from app.infra.database.session import get_db
from app.domains.integration.models import ServiceType
from app.domains.integration.schemas import (
    IntegrationResponse,
    IntegrationListResponse,
    JiraConnectRequest,
    KakaoConnectRequest,
    OAuthUrlResponse,
    SlackChannelSelectRequest,
)
from app.domains.integration import service, repository
from app.core.config import settings

router = APIRouter()

FRONTEND_INTEGRATIONS = f"{settings.FRONTEND_URL}/settings/integrations"

# --- 목록 조회 / 해제/ 테스트 ---

@router.get("/workspaces/{workspace_id}", response_model=IntegrationListResponse)
async def get_integrations(workspace_id: int, db: Session = Depends(get_db)):
    """
    워크스페이스 연동 목록 전체 조회
    """
    items = service.get_integrations(db, workspace_id)

    integrations = []
    for item in items:
        integrations.append(
            IntegrationResponse(
                id=item.id,
                service=item.service,
                is_connected=item.is_connected,
                updated_at=item.updated_at,
                selected_channel_id=item.extra_config.get("channel_id") if item.extra_config else None,
            )
        )
    return IntegrationListResponse(integrations=integrations)

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
        updated_at=item.updated_at,
    )

@router.post("/workspaces/{workspace_id}/{service_name}/test")
async def test_webhook(
    workspace_id: int,
    service_name: ServiceType,
    db: Session = Depends(get_db),
):
    """연결 테스트"""
    success = await service.test_integration(db, workspace_id, service_name)
    if not success:
        raise HTTPException(status_code=400, detail="연동 상태 확인 불가")
    return {"success": True, "message": "webhook 연결 성공"}


#===============================================================
#
#                OAuth API
#
#===============================================================


# --- Google Calendar OAuth ---

@router.get("/google/auth", response_model=OAuthUrlResponse)
async def google_auth(workspace_id: int):
    """
    프론트에서 URL을 받아 window.location.href로 이동
    """
    return OAuthUrlResponse(auth_url=service.get_google_auth_url(workspace_id))

@router.get("/google/callback")
async def google_callback(code: str, state: str, db: Session = Depends(get_db)):
    try:
        workspace_id = await service.handle_google_callback(db, code, state)
        return RedirectResponse(f"{FRONTEND_INTEGRATIONS}?service=google_calendar&status=connected")
    except Exception as e:
        return RedirectResponse(f"{FRONTEND_INTEGRATIONS}?service=google_calendar&status=error")

# --- Slack Auth ---

@router.get("/slack/auth", response_model=OAuthUrlResponse)
async def slack_auth(workspace_id: int):
    return OAuthUrlResponse(auth_url=service.get_slack_auth_url(workspace_id))

@router.get("/slack/callback")
async def slack_callback(code: str, state: str, db: Session = Depends(get_db)):
    try:
        await service.handle_slack_callback(db, code, state)
        return RedirectResponse(f"{FRONTEND_INTEGRATIONS}?service=slack&status=connected")
    
    except Exception as e:
        return RedirectResponse(f"{FRONTEND_INTEGRATIONS}?service=slack&status=error")
    
# --- Notion Auth ---

@router.get("/notion/auth", response_model=OAuthUrlResponse)
async def notion_auth(workspace_id: int):
    return OAuthUrlResponse(auth_url=service.get_notion_auth_url(workspace_id))

@router.get("/notion/callback")
async def notion_callback(code: str, state: str, db: Session = Depends(get_db)):
    try:
        await service.handle_notion_callback(db, code, state)
        return RedirectResponse(f"{FRONTEND_INTEGRATIONS}?service=notion&status=connected")
    except Exception as e:
        return RedirectResponse(f"{FRONTEND_INTEGRATIONS}?service=notion&status=error")


# --- JIRA API Key ---

@router.post("/workspaces/{workspace_id}/jira/connect", response_model=IntegrationResponse)
async def connect_jira(
    workspace_id: int, body: JiraConnectRequest, db: Session = Depends(get_db)
):
    item = service.connect_jira(
        db, workspace_id, body.domain, body.email, body.api_token, body.project_key
    )
    return IntegrationResponse(
        id=item.id, service=item.service, is_connected=item.is_connected,
        updated_at=item.updated_at,
    )


# --- 카카오 API Key ---

@router.post("/workspaces/{workspace_id}/kakao/connect", response_model=IntegrationResponse)
async def connect_kakao(
    workspace_id: int, body: KakaoConnectRequest, db: Session = Depends(get_db)
):
    item = service.connect_kakao(db, workspace_id, body.api_key)
    return IntegrationResponse(
        id=item.id, service=item.service, is_connected=item.is_connected,
        updated_at=item.updated_at,
    )

#===============================================================
#
#                   API service
#
#===============================================================

# Slack API https://localhost:8000/api/v1/integrations/workspaces/1/slack/channels
@router.get("/workspaces/{workspace_id}/slack/channels")
async def list_slack_channels(workspace_id: int, db: Session = Depends(get_db)):
    """
    슬랙 채널 목록 조회
    """
    try:
        channels = await service.get_slack_channel(db, workspace_id)
        return {
            "channels": channels
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
@router.patch("/slack/channel")
async def select_slack_channel(
    workspace_id: int,
    body: SlackChannelSelectRequest,
    db: Session = Depends(get_db),
):
    """
    슬랙 채널 선택
    """
    await service.save_slack_channel(db, workspace_id, body.channel_id)
    return {
        "status": "ok"
    }