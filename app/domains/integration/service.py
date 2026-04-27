# app\domains\integration\service.py
import json
import base64
import logging
from datetime import datetime, timedelta, timezone
from app.utils.time_utils import now_kst, KST

from sqlalchemy.orm import Session
from typing import List

from app.core.graph.state import SharedState
from app.domains.integration.models import Integration, ServiceType
from app.domains.integration import repository
from app.infra.clients.session_manager import ClientSessionManager
from app.core.config import settings
from app.infra.clients.slack import SlackClient
from app.infra.clients.google import GoogleCalendarClient

logger= logging.getLogger(__name__)

# --- state  인코딩, 디코딩 (OAuth state parameters) ---
def _encode_state(workspace_id: int) -> str:
    return base64.urlsafe_b64encode(
        json.dumps({"workspace_id": workspace_id}).encode()
    ).decode()

def _decode_state(state: str) -> int:
    data = json.loads(base64.urlsafe_b64decode(state.encode()).decode())
    return data['workspace_id']

# --- LangGraph Node ---

async def load_integration_settings(state: SharedState, db: Session):
    """
    DB에서 워크스페이스 연동 설정을 읽어 SharedSate에 올린다.
    회의 시작 시 supervisor가 이노드를 호출한다.
    """
    workspace_id = int(state['workspace_id'])
    integrations = repository.get_integrations(db, workspace_id)

    integration_settings = {}
    for item in integrations:
        integration_settings[item.service.value] = {
            "is_connected": item.is_connected,
            "access_token": item.access_token,
            "extra_config": item.extra_config,
        }
    return {"integration_settings": integration_settings}

# --- 비즈니스 로직 ---
def get_integrations(db: Session, workspace_id: int) -> List[Integration]:
    return repository.get_integrations(db, workspace_id)

def disconnect_integration(
        db: Session,
        workspace_id: int,
        service: ServiceType
) -> Integration:
    """
    연동 해제
    is_connected=False, webhook_url 삭제
    """
    return repository.disconnect_integration(db, workspace_id, service)

async def test_integration(db: Session, workspace_id: int, service: ServiceType) -> bool:
    """
    저장된 토큰으로 실제 API 연결 확인
    """
    integration = repository.get_integration(db, workspace_id, service)
    if not integration or not integration.is_connected:
        return False
    # 서비스 ping 로직 향후 추가
    return True




#===============================================================
#
#                OAuth API
#
#===============================================================



# --- Google Calendar OAuth ---

def get_google_auth_url(workspace_id: int):
    if not settings.GOOGLE_CLIENT_ID:
        raise ValueError("GOOGLE_CLIENT_ID가 설정되어 있지 않습니다. (.env 또는 환경변수 확인)")
    if not settings.GOOGLE_REDIRECT_URI:
        raise ValueError("GOOGLE_REDIRECT_URI가 설정되어 있지 않습니다. (.env 또는 환경변수 확인)")
    state = _encode_state(workspace_id)
    params = (
        f"https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={settings.GOOGLE_CLIENT_ID}"
        f"&redirect_uri={settings.GOOGLE_REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=https://www.googleapis.com/auth/calendar"
        f"&access_type=offline"
        f"&prompt=consent"
        f"&state={state}"
    )
    return params

async def handle_google_callback(db: Session, code: str, state: str) -> int:
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise ValueError("Google OAuth 설정이 누락되었습니다. (GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET 확인)")
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

    expires_at = now_kst() + timedelta(seconds=tokens.get("expires_in", 3600))

    repository.update_tokens(
        db,
        workspace_id=workspace_id,
        service=ServiceType.google_calendar,
        access_token=tokens['access_token'],
        refresh_token=tokens.get('refresh_token'),
        token_expires_at=expires_at,
    )
    logger.info(f"GOOGLE Calender 연동 완료 {workspace_id}번")
    return workspace_id

# --- Slack OAuth ---

def get_slack_auth_url(workspace_id: int) -> str:
    state = _encode_state(workspace_id)
    return (
        f"https://slack.com/oauth/v2/authorize"
        f"?client_id={settings.SLACK_CLIENT_ID}"
        f"&scope=chat:write,chat:write.public,channels:join,channels:read,users:read,users:read.email,im:write,files:write,pins:write"
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

    bot_token = data['access_token']
    team_id = data.get("team", {}).get("id", "")

    repository.update_tokens(
        db,
        workspace_id=workspace_id,
        service=ServiceType.slack,
        access_token=bot_token,
        extra_config={"team_id": team_id},
    )
    logger.info(f"slack 연동 완료 {workspace_id}번")
    return workspace_id

# --- Notion OAuth ---
def get_notion_auth_url(workspace_id: int) -> str:
    state = _encode_state(workspace_id)
    return (
        f"https://api.notion.com/v1/oauth/authorize"
        f"?client_id={settings.NOTION_CLIENT_ID}"
        f"&redirect_uri={settings.NOTION_REDIRECT_URI}"
        f"&response_type=code"
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
    logger.info(f"Notion 연동 완료 (workspace_id={workspace_id})")
    return workspace_id


# --- JIRA API Key ---

def connect_jira(
    db: Session, workspace_id: int, domain: str, email: str, api_token: str, project_key: str
) -> Integration:
    return repository.update_tokens(
        db,
        workspace_id=workspace_id,
        service=ServiceType.jira,
        access_token=api_token,
        extra_config={"domain": domain, "email": email, "project_key": project_key},
    )


# --- 카카오 API Key ---

def connect_kakao(db: Session, workspace_id: int, api_key: str) -> Integration:
    return repository.update_tokens(
        db,
        workspace_id=workspace_id,
        service=ServiceType.kakao,
        access_token=api_key,
    )


# --- Google Token 확인 및 갱신 ---

async def get_valid_google_token(db: Session, workspace_id: int) -> str:
    integration = repository.get_integration(db, workspace_id, ServiceType.google_calendar)
    if not integration or not integration.access_token:
        raise ValueError("Google Calendar 연동이 필요합니다.")

    expires_at = integration.token_expires_at
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=KST)
    if expires_at and expires_at < now_kst() + timedelta(minutes=5):
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
        expires_at = now_kst() + timedelta(seconds=tokens.get("expires_in", 3600))
        repository.update_tokens(
            db, workspace_id, ServiceType.google_calendar,
            access_token=tokens["access_token"],
            refresh_token=integration.refresh_token,
            token_expires_at=expires_at,
        )
        return tokens["access_token"]

    return integration.access_token

#===============================================================
#
#                   API service
#
#===============================================================

# Slack API
async def get_slack_channel(db: Session, workspace_id: int) -> List[dict]:
    """
    슬랙 연동후 채널을 선택하기 위해 채널 목록 반환
    """
    integration = repository.get_integration(db, workspace_id, ServiceType.slack)
    if not integration or not integration.access_token:
        raise ValueError("Slack 연동이 되어있지 않거나 토큰이 없습니다.")
    
    slack_client = SlackClient(integration.access_token)
    return await slack_client.get_public_channels()


async def save_slack_channel(db: Session, workspace_id: int, channel_id: str) -> Integration:
    """
    유저가 선택한 Slack 채널 ID를 extra_config 에 저장
    """
    integration = repository.get_integration(db, workspace_id, ServiceType.slack)
    if not integration or not integration.access_token:
        raise ValueError("Slack 연동이 안 되어있습니다.")
    
    extra_config = {**(integration.extra_config or {}) , "channel_id": channel_id}
    return repository.update_tokens(
        db,
        workspace_id=workspace_id,
        access_token=integration.access_token,
        service=ServiceType.slack,
        extra_config=extra_config,
    )

# Google Calendar API
async def list_google_calendar_events(
    db: Session,
    workspace_id: int,
    time_min: str = None,
    max_results: int = 50,
) -> list:
    
    access_token = await get_valid_google_token(db, workspace_id)
    client = GoogleCalendarClient(access_token)
    result = await client.list_events(time_min=time_min, max_results=max_results)
    events = []
    for item in result.get("items", []):
        start = item.get("start", {})
        end = item.get("end", {})
        events.append({
            "id": item.get("id", ""),
            "title": item.get("summary", "(제목 없음)"),
            "start": start.get("dateTime") or start.get("date", ""),
            "end": end.get("dateTime") or end.get("date", ""),
            "description": item.get("description"),
            "html_link": item.get("htmlLink"),
        })
    return events


