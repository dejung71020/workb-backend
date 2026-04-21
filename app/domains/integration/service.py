# app\domains\integration\service.py
import base64
import json
import logging
from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.graph.state import SharedState
from app.domains.integration import repository
from app.domains.integration.models import Integration, ServiceType
from app.domains.integration.schemas import IntegrationItemResponse, IntegrationListResponse
from app.domains.workspace.repository import get_workspace_by_id
from app.infra.clients.session_manager import ClientSessionManager

logger = logging.getLogger(__name__)


def _encode_state(workspace_id: int) -> str:
    return base64.urlsafe_b64encode(
        json.dumps({"workspace_id": workspace_id}).encode()
    ).decode()


def _decode_state(state: str) -> int:
    data = json.loads(base64.urlsafe_b64decode(state.encode()).decode())
    return data["workspace_id"]


def _integration_response(item: Integration) -> IntegrationItemResponse:
    return IntegrationItemResponse(
        id=item.id,
        service=item.service,
        is_connected=item.is_connected,
        selected_channel_id=item.extra_config.get("channel_id") if item.extra_config else None,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


async def load_integration_settings(state: SharedState, db: Session):
    workspace_id = int(state["workspace_id"])
    integrations = repository.ensure_default_integrations(db, workspace_id)

    integration_settings = {}
    for item in integrations:
        service_name = item.service.value if isinstance(item.service, ServiceType) else str(item.service)
        integration_settings[service_name] = {
            "is_connected": item.is_connected,
            "access_token": item.access_token,
            "extra_config": item.extra_config,
        }
    return {"integration_settings": integration_settings}


def get_integrations(db: Session, workspace_id: int) -> list[Integration]:
    return repository.ensure_default_integrations(db, workspace_id)


def get_integrations_service(db: Session, workspace_id: int) -> IntegrationListResponse:
    workspace = get_workspace_by_id(db, workspace_id)
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="워크스페이스를 찾을 수 없습니다.",
        )

    return IntegrationListResponse(
        integrations=[
            _integration_response(item)
            for item in repository.ensure_default_integrations(db, workspace_id)
        ]
    )


def update_integration_connection_service(
    db: Session,
    workspace_id: int,
    service: ServiceType | str,
    is_connected: bool,
) -> IntegrationItemResponse:
    normalized_service = service if isinstance(service, ServiceType) else ServiceType(service.replace("-", "_"))

    workspace = get_workspace_by_id(db, workspace_id)
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="워크스페이스를 찾을 수 없습니다.",
        )

    repository.ensure_default_integrations(db, workspace_id)
    item = repository.update_integration_connection(
        db=db,
        workspace_id=workspace_id,
        service=normalized_service,
        is_connected=is_connected,
    )
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="연동 정보를 찾을 수 없습니다.",
        )

    return _integration_response(item)


def disconnect_integration(
    db: Session,
    workspace_id: int,
    service: ServiceType,
) -> Integration:
    item = repository.disconnect_integration(db, workspace_id, service)
    if not item:
        raise HTTPException(status_code=404, detail="연동 정보를 찾을 수 없습니다.")
    return item


async def test_integration(db: Session, workspace_id: int, service: ServiceType) -> bool:
    integration = repository.get_integration(db, workspace_id, service)
    if not integration or not integration.is_connected:
        return False
    return True


def get_google_auth_url(workspace_id: int):
    state = _encode_state(workspace_id)
    return (
        "https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={settings.GOOGLE_CLIENT_ID}"
        f"&redirect_uri={settings.GOOGLE_REDIRECT_URI}"
        "&response_type=code"
        "&scope=https://www.googleapis.com/auth/calendar"
        "&access_type=offline"
        "&prompt=consent"
        f"&state={state}"
    )


async def handle_google_callback(db: Session, code: str, state: str) -> int:
    workspace_id = _decode_state(state)
    client = await ClientSessionManager.get_client()

    res = await client.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        },
    )
    res.raise_for_status()
    tokens = res.json()
    expires_at = datetime.now() + timedelta(seconds=tokens.get("expires_in", 3600))

    repository.update_tokens(
        db,
        workspace_id=workspace_id,
        service=ServiceType.google_calendar,
        access_token=tokens["access_token"],
        refresh_token=tokens.get("refresh_token"),
        token_expires_at=expires_at,
    )
    logger.info("Google Calendar 연동 완료 workspace_id=%s", workspace_id)
    return workspace_id


def get_slack_auth_url(workspace_id: int) -> str:
    state = _encode_state(workspace_id)
    return (
        "https://slack.com/oauth/v2/authorize"
        f"?client_id={settings.SLACK_CLIENT_ID}"
        "&scope=chat:write,chat:write.public,channels:join,channels:read,users:read,users:read.email,im:write,files:write,pins:write"
        f"&redirect_uri={settings.SLACK_REDIRECT_URI}"
        f"&state={state}"
    )


async def handle_slack_callback(db: Session, code: str, state: str) -> int:
    workspace_id = _decode_state(state)
    client = await ClientSessionManager.get_client()

    res = await client.post(
        "https://slack.com/api/oauth.v2.access",
        data={
            "code": code,
            "client_id": settings.SLACK_CLIENT_ID,
            "client_secret": settings.SLACK_CLIENT_SECRET,
            "redirect_uri": settings.SLACK_REDIRECT_URI,
        },
    )
    res.raise_for_status()
    data = res.json()

    repository.update_tokens(
        db,
        workspace_id=workspace_id,
        service=ServiceType.slack,
        access_token=data["access_token"],
        extra_config={"team_id": data.get("team", {}).get("id", "")},
    )
    logger.info("Slack 연동 완료 workspace_id=%s", workspace_id)
    return workspace_id


def get_notion_auth_url(workspace_id: int) -> str:
    state = _encode_state(workspace_id)
    return (
        "https://api.notion.com/v1/oauth/authorize"
        f"?client_id={settings.NOTION_CLIENT_ID}"
        f"&redirect_uri={settings.NOTION_REDIRECT_URI}"
        "&response_type=code"
        f"&state={state}"
    )


async def handle_notion_callback(db: Session, code: str, state: str) -> int:
    workspace_id = _decode_state(state)
    client = await ClientSessionManager.get_client()

    credentials = base64.b64encode(
        f"{settings.NOTION_CLIENT_ID}:{settings.NOTION_CLIENT_SECRET}".encode()
    ).decode()

    res = await client.post(
        "https://api.notion.com/v1/oauth/token",
        json={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.NOTION_REDIRECT_URI,
        },
        headers={"Authorization": f"Basic {credentials}"},
    )
    res.raise_for_status()
    data = res.json()

    repository.update_tokens(
        db,
        workspace_id=workspace_id,
        service=ServiceType.notion,
        access_token=data["access_token"],
        extra_config={"workspace_name": data.get("workspace_name", "")},
    )
    logger.info("Notion 연동 완료 workspace_id=%s", workspace_id)
    return workspace_id


def connect_jira(
    db: Session,
    workspace_id: int,
    domain: str,
    email: str,
    api_token: str,
    project_key: str,
) -> Integration:
    return repository.update_tokens(
        db,
        workspace_id=workspace_id,
        service=ServiceType.jira,
        access_token=api_token,
        extra_config={"domain": domain, "email": email, "project_key": project_key},
    )


def connect_kakao(db: Session, workspace_id: int, api_key: str) -> Integration:
    return repository.update_tokens(
        db,
        workspace_id=workspace_id,
        service=ServiceType.kakao,
        access_token=api_key,
    )


async def get_valid_google_token(db: Session, workspace_id: int) -> str:
    integration = repository.get_integration(db, workspace_id, ServiceType.google_calendar)
    if not integration or not integration.access_token:
        raise ValueError("Google Calendar 연동이 필요합니다.")

    if integration.token_expires_at and integration.token_expires_at < datetime.now() + timedelta(minutes=5):
        client = await ClientSessionManager.get_client()
        res = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "refresh_token": integration.refresh_token,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "grant_type": "refresh_token",
            },
        )
        res.raise_for_status()
        tokens = res.json()
        expires_at = datetime.now() + timedelta(seconds=tokens.get("expires_in", 3600))
        repository.update_tokens(
            db,
            workspace_id,
            ServiceType.google_calendar,
            access_token=tokens["access_token"],
            refresh_token=integration.refresh_token,
            token_expires_at=expires_at,
        )
        return tokens["access_token"]

    return integration.access_token


from app.infra.clients.slack import SlackClient


async def get_slack_channel(db: Session, workspace_id: int) -> list[dict]:
    integration = repository.get_integration(db, workspace_id, ServiceType.slack)
    if not integration or not integration.access_token:
        raise ValueError("Slack 연동이 되어있지 않거나 토큰이 없습니다.")

    slack_client = SlackClient(integration.access_token)
    return await slack_client.get_public_channels()


async def save_slack_channel(db: Session, workspace_id: int, channel_id: str) -> Integration:
    integration = repository.get_integration(db, workspace_id, ServiceType.slack)
    if not integration or not integration.access_token:
        raise ValueError("Slack 연동이 안 되어있습니다.")

    extra_config = {**(integration.extra_config or {}), "channel_id": channel_id}
    return repository.update_tokens(
        db,
        workspace_id=workspace_id,
        access_token=integration.access_token,
        service=ServiceType.slack,
        extra_config=extra_config,
    )
