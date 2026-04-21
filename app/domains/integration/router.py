# app\domains\integration\router.py
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domains.integration import service
from app.domains.integration.models import ServiceType
from app.domains.integration.schemas import (
    IntegrationResponse,
    IntegrationListResponse,
    JiraConnectRequest,
    KakaoConnectRequest,
    OAuthUrlResponse,
    SlackChannelSelectRequest,
)
from app.infra.database.session import get_db

router = APIRouter()

FRONTEND_INTEGRATIONS = f"{settings.FRONTEND_URL}/settings/integrations"


def _to_response(item) -> IntegrationResponse:
    return IntegrationResponse(
        id=item.id,
        service=item.service,
        is_connected=item.is_connected,
        selected_channel_id=item.extra_config.get("channel_id") if item.extra_config else None,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.get("/workspaces/{workspace_id}", response_model=IntegrationListResponse)
async def get_integrations(workspace_id: int, db: Session = Depends(get_db)):
    return service.get_integrations_service(db, workspace_id)


@router.patch(
    "/workspaces/{workspace_id}/{service_name}/connect",
    response_model=IntegrationResponse,
    status_code=status.HTTP_200_OK,
)
async def connect_integration_for_dev(
    workspace_id: int,
    service_name: ServiceType,
    db: Session = Depends(get_db),
):
    return service.update_integration_connection_service(
        db=db,
        workspace_id=workspace_id,
        service=service_name,
        is_connected=True,
    )


@router.patch(
    "/workspaces/{workspace_id}/{service_name}/disconnect",
    response_model=IntegrationResponse,
    status_code=status.HTTP_200_OK,
)
@router.post(
    "/workspaces/{workspace_id}/{service_name}/disconnect",
    response_model=IntegrationResponse,
    status_code=status.HTTP_200_OK,
)
async def disconnect_integration(
    workspace_id: int,
    service_name: ServiceType,
    db: Session = Depends(get_db),
):
    item = service.disconnect_integration(db, workspace_id, service_name)
    return _to_response(item)


@router.post("/workspaces/{workspace_id}/{service_name}/test")
async def test_webhook(
    workspace_id: int,
    service_name: ServiceType,
    db: Session = Depends(get_db),
):
    success = await service.test_integration(db, workspace_id, service_name)
    if not success:
        raise HTTPException(status_code=400, detail="연동 상태 확인 불가")
    return {"success": True, "message": "webhook 연결 성공"}


@router.get("/google/auth", response_model=OAuthUrlResponse)
async def google_auth(workspace_id: int):
    return OAuthUrlResponse(auth_url=service.get_google_auth_url(workspace_id))


@router.get("/google/callback")
async def google_callback(code: str, state: str, db: Session = Depends(get_db)):
    try:
        await service.handle_google_callback(db, code, state)
        return RedirectResponse(f"{FRONTEND_INTEGRATIONS}?service=google_calendar&status=connected")
    except Exception:
        return RedirectResponse(f"{FRONTEND_INTEGRATIONS}?service=google_calendar&status=error")


@router.get("/slack/auth", response_model=OAuthUrlResponse)
async def slack_auth(workspace_id: int):
    return OAuthUrlResponse(auth_url=service.get_slack_auth_url(workspace_id))


@router.get("/slack/callback")
async def slack_callback(code: str, state: str, db: Session = Depends(get_db)):
    try:
        await service.handle_slack_callback(db, code, state)
        return RedirectResponse(f"{FRONTEND_INTEGRATIONS}?service=slack&status=connected")
    except Exception:
        return RedirectResponse(f"{FRONTEND_INTEGRATIONS}?service=slack&status=error")


@router.get("/notion/auth", response_model=OAuthUrlResponse)
async def notion_auth(workspace_id: int):
    return OAuthUrlResponse(auth_url=service.get_notion_auth_url(workspace_id))


@router.get("/notion/callback")
async def notion_callback(code: str, state: str, db: Session = Depends(get_db)):
    try:
        await service.handle_notion_callback(db, code, state)
        return RedirectResponse(f"{FRONTEND_INTEGRATIONS}?service=notion&status=connected")
    except Exception:
        return RedirectResponse(f"{FRONTEND_INTEGRATIONS}?service=notion&status=error")


@router.post("/workspaces/{workspace_id}/jira/connect", response_model=IntegrationResponse)
async def connect_jira(
    workspace_id: int,
    body: JiraConnectRequest,
    db: Session = Depends(get_db),
):
    item = service.connect_jira(
        db,
        workspace_id,
        body.domain,
        body.email,
        body.api_token,
        body.project_key,
    )
    return _to_response(item)


@router.post("/workspaces/{workspace_id}/kakao/connect", response_model=IntegrationResponse)
async def connect_kakao(
    workspace_id: int,
    body: KakaoConnectRequest,
    db: Session = Depends(get_db),
):
    item = service.connect_kakao(db, workspace_id, body.api_key)
    return _to_response(item)


@router.get("/workspaces/{workspace_id}/slack/channels")
async def list_slack_channels(workspace_id: int, db: Session = Depends(get_db)):
    try:
        channels = await service.get_slack_channel(db, workspace_id)
        return {"channels": channels}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/slack/channel")
async def select_slack_channel(
    workspace_id: int,
    body: SlackChannelSelectRequest,
    db: Session = Depends(get_db),
):
    await service.save_slack_channel(db, workspace_id, body.channel_id)
    return {"status": "ok"}
