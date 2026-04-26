# app\domains\integration\router.py
from fastapi import APIRouter, Depends, HTTPException, Query, Body, status
from typing import Optional
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.infra.database.session import get_db
from app.domains.action.schemas import ExportResponse
from app.domains.integration import repository, service
from app.domains.integration.models import Integration, ServiceType
from app.domains.integration.schemas import (
    IntegrationListResponse,
    IntegrationResponse,
    JiraConnectRequest,
    KakaoConnectRequest,
    OAuthUrlResponse,
    SlackChannelSelectRequest,
    SlackChannelItem,
    SlackChannelListResponse,
    TestIntegrationResponse,
    GoogleCalendarEventsResponse,
    GoogleCalendarEventItem,
)
from app.domains.user.dependencies import require_workspace_admin, require_workspace_member

router = APIRouter()

FRONTEND_INTEGRATIONS = f"{settings.FRONTEND_URL}/settings/integrations"


def _to_response(item: Integration) -> IntegrationResponse:
    return IntegrationResponse(
        id=item.id,
        service=item.service,
        is_connected=item.is_connected,
        selected_channel_id=item.extra_config.get("channel_id") if item.extra_config else None,
        updated_at=item.updated_at,
    )


@router.get("/workspaces/{workspace_id}", response_model=IntegrationListResponse)
async def get_integrations(
    workspace_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(require_workspace_admin),
) -> IntegrationListResponse:
    items = service.get_integrations(db, workspace_id)
    return IntegrationListResponse(integrations=[_to_response(item) for item in items])


@router.patch(
    "/workspaces/{workspace_id}/{service_name}/connect",
    response_model=IntegrationResponse,
    status_code=status.HTTP_200_OK,
)
async def connect_integration_for_dev(
    workspace_id: int,
    service_name: ServiceType,
    db: Session = Depends(get_db),
    _admin=Depends(require_workspace_admin),
) -> IntegrationResponse:
    item = repository.get_integration(db, workspace_id, service_name)
    if item is None:
        item = Integration(
            workspace_id=workspace_id,
            service=service_name,
            is_connected=True,
        )
        db.add(item)
    else:
        item.is_connected = True
    db.commit()
    db.refresh(item)
    return _to_response(item)


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
    _admin=Depends(require_workspace_admin),
) -> IntegrationResponse:
    item = service.disconnect_integration(db, workspace_id, service_name)
    if item is None:
        raise HTTPException(status_code=404, detail="연동 정보를 찾을 수 없습니다.")
    return _to_response(item)


@router.post("/workspaces/{workspace_id}/{service_name}/test", response_model=TestIntegrationResponse)
async def test_webhook(
    workspace_id: int,
    service_name: ServiceType,
    db: Session = Depends(get_db),
    _admin=Depends(require_workspace_admin),
):
    success = await service.test_integration(db, workspace_id, service_name)
    if not success:
        raise HTTPException(status_code=400, detail="연동 상태 확인 불가")
    return TestIntegrationResponse(success=True, message="연결 성공")


@router.get("/google/auth", response_model=OAuthUrlResponse)
async def google_auth(
    workspace_id: int = Query(..., description="워크스페이스 ID"),
    _admin=Depends(require_workspace_admin),
) -> OAuthUrlResponse:
    try:
        return OAuthUrlResponse(auth_url=service.get_google_auth_url(workspace_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/google/callback")
async def google_callback(code: str, state: str, db: Session = Depends(get_db)):
    try:
        await service.handle_google_callback(db, code, state)
        return RedirectResponse(f"{FRONTEND_INTEGRATIONS}?service=google_calendar&status=connected")
    except Exception:
        return RedirectResponse(f"{FRONTEND_INTEGRATIONS}?service=google_calendar&status=error")


@router.get("/slack/auth", response_model=OAuthUrlResponse)
async def slack_auth(
    workspace_id: int = Query(..., description="워크스페이스 ID"),
    _admin=Depends(require_workspace_admin),
) -> OAuthUrlResponse:
    return OAuthUrlResponse(auth_url=service.get_slack_auth_url(workspace_id))


@router.get("/slack/callback")
async def slack_callback(code: str, state: str, db: Session = Depends(get_db)):
    try:
        await service.handle_slack_callback(db, code, state)
        return RedirectResponse(f"{FRONTEND_INTEGRATIONS}?service=slack&status=connected")
    except Exception:
        return RedirectResponse(f"{FRONTEND_INTEGRATIONS}?service=slack&status=error")


@router.get("/notion/auth", response_model=OAuthUrlResponse)
async def notion_auth(
    workspace_id: int = Query(..., description="워크스페이스 ID"),
    _admin=Depends(require_workspace_admin),
) -> OAuthUrlResponse:
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
    _admin=Depends(require_workspace_admin),
) -> IntegrationResponse:
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
    _admin=Depends(require_workspace_admin),
) -> IntegrationResponse:
    item = service.connect_kakao(db, workspace_id, body.api_key)
    return _to_response(item)


@router.get("/workspaces/{workspace_id}/slack/channels", response_model=SlackChannelListResponse)
async def list_slack_channels(
    workspace_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(require_workspace_admin),
):
    try:
        channels = await service.get_slack_channel(db, workspace_id)
        return SlackChannelListResponse(channels=channels)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/google/events", response_model=GoogleCalendarEventsResponse)
async def list_google_calendar_events(
    workspace_id: int = Query(..., description="워크스페이스 ID"),
    time_min: Optional[str] = Query(None, description="조회 시작 시각 (ISO 8601)"),
    max_results: int = Query(50, description="최대 반환 건수"),
    db: Session = Depends(get_db),
    _admin=Depends(require_workspace_member),
):
    try:
        events = await service.list_google_calendar_events(db, workspace_id, time_min, max_results)
        return GoogleCalendarEventsResponse(
            events=[GoogleCalendarEventItem(**e) for e in events]
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/slack/channel", response_model=ExportResponse)
async def select_slack_channel(
    workspace_id: int = Query(..., description="워크스페이스 ID"),
    body: SlackChannelSelectRequest = Body(...),
    db: Session = Depends(get_db),
    _admin=Depends(require_workspace_admin),
):
    await service.save_slack_channel(db, workspace_id, body.channel_id)
    return ExportResponse(status="ok")