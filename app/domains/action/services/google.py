# app/domains/action/services/google.py
import logging
from datetime import datetime, timedelta
from typing import List

from sqlalchemy.orm import Session

from app.domains.integration.models import ServiceType
from app.domains.integration import repository as integration_repo
from app.domains.integration.service import get_valid_google_token
from app.domains.action import repository
from app.domains.action.mongo_repository import get_meeting_summary
from app.infra.clients.google import GoogleCalendarClient
from app.infra.clients.slack import SlackClient

logger = logging.getLogger(__name__)

async def export_google_calendar(
        db: Session,
        workspace_id: int,
        meeting_id: int
) -> None:
    """
    회의 종료 후 구글 캘린더 이벤트에 회의록 요약을 첨부.
    - meeting.google_calendar_event_id가 있으면 description PATCH
    - meeting.google_calendar_event_id가 없으면 새 이벤트 생성
    """
    try:
        access_token = await get_valid_google_token(db, workspace_id)
        client = GoogleCalendarClient(access_token)

        meeting = repository.get_meeting(db, meeting_id)
        if not meeting:
            raise ValueError(f"회의 (id={meeting_id})를 찾을 수 없습니다.") 
        
        summary = get_meeting_summary(meeting_id)
        attendees = summary.get("attendees", [])
        overview = summary.get("overview", {})
        decisions = summary.get("decisions", [])
        action_items = summary.get("action_items", [])

        lines = []
        if overview:
            lines.append(f"[목적] {overview.get('purpose', '')}")
            lines.append(f"[일시] {overview.get('datetime_str', '')}")

        if decisions:
            lines.append("\n[결정 사항]")
            lines.extend(f"- {d.get('decision', '')}" for d in decisions)

        if action_items:
            lines.append("\n[액션 아이템]")
            for a in action_items:
                deadline = f"(~{a.get('deadline', '')})" if a.get("deadline") else ""
                lines.append(f"- [{a.get('assignee', '')}] {a.get('content', '')} {deadline}")
        
        if attendees:
            lines.append(f"\n[참석자] {', '.join(attendees)}")
        
        description = "\n".join(lines)

        if meeting.google_calendar_event_id:
            await client.update_event_description(
                event_id=meeting.google_calendar_event_id,
                description=description,
            )
        
        else:
            started = meeting.started_at or meeting.scheduled_at or datetime.now()
            ended = meeting.ended_at or (started + timedelta(hours=1))
            await client.create_event(
                title=meeting.title,
                start_datetime=started.strftime("%Y-%m-%dT%H:%M:%S"),
                end_datetime=ended.strftime("%Y-%m-%dT%H:%M:%S"),
                description=description,
            )
        
        logger.info(f"[Google Calendar Export] 완료 - meeting_id={meeting_id}")

    except Exception as e:
        logger.error(f"[Google Calendar Export] 실패 - meeting_id = {meeting_id} - error_code = {e}")

async def suggest_next_meeting(
        db: Session,
        workspace_id: int,
        meeting_id: int,
        duration_minutes: int = 60,
) -> List[str]:
    """
    Slack 채널 멤버 이메일을 수집하여 Google Freebusy API로
    -> 구글 이메일이 대부분인 슬랙 채널 멤버 이메일로 가정
    2주 이내 평일 09:00-18:00 기준 전원이 비어있는 슬록 3개를 추천한다.
    구글 이메일이 없는 멤버는 제외된다.

    args:
        duration_minutes: 회의 소요 시간 기본값 - 60분
    
    return:
        추천 시간 리스트 레코드 3개
    """
    slack_integration = integration_repo.get_integration(db, workspace_id, ServiceType.slack)
    if not slack_integration or not slack_integration.access_token:
        raise ValueError("Slack 연동이 필요합니다.")
    
    channel_id = (slack_integration.extra_config or {}).get("channel_id")
    if not channel_id:
        raise ValueError("Slack 기본 채널이 설정되지 않았습니다.")
    
    slack_client = SlackClient(slack_integration.access_token)
    member_ids = slack_client.get_channel_members(channel_id=channel_id)

    attendee_emails = []
    for uid in member_ids:
        id_name_email = await slack_client.get_user_info(uid)
        if id_name_email:
            attendee_emails.append(id_name_email.get("email", ""))
    
    if not id_name_email:
        raise ValueError("Slack 채널에서 수집된 이메일이 없습니다.")
    
    access_token = await get_valid_google_token(db, workspace_id)
    client = GoogleCalendarClient(access_token)

    now = datetime.now()
    time_min = now.strftime("%Y-%m-%dT%H:%M:%S+09:00")
    time_max = (now + timedelta(days=14)).strftime("%Y-%M-%dT%H:%M:%s+09:00")

    freebusy = await client.get_free_slots(
        calendar_ids=attendee_emails,
        time_min=time_min,
        time_max=time_max,
    )

    busy_intervals: List[tuple] = []
    for cal in freebusy.get("calendars", {}).values():
        for slot in cal.get("busy", []):
            start = datetime.fromisoformat(slot['start'].replace("Z", "+00:00"))
            end = datetime.fromisoformat(slot["end"].replace("Z", "+00:00"))
            busy_intervals.append((start, end))
    
    suggestions: List[str] = []
    
    

async def register_next_meeting(
        db: Session,
        workspace_id: int,
        meeting_id: int,
        duration_minutes: int = 60,
) -> List[str]:
    """

    """
    pass
