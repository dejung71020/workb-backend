# app/domains/action/services/minutes_builder.py
from sqlalchemy.orm import Session
from app.domains.intelligence.models import MeetingMinute, MinuteStatus
from app.domains.action.mongo_repository import get_meeting_summary
from app.utils.time_utils import now_kst
from app.domains.meeting.models import MeetingParticipant, Meeting
from app.domains.notification.models import NotificationType
from app.domains.notification import service as notification_service

async def build_and_save_minutes(db: Session, meeting_id: int) -> MeetingMinute:
    # 회의록을 이미 만들었는지 확인
    existing = db.query(MeetingMinute).filter(
        MeetingMinute.meeting_id==meeting_id
    ).first()
    if existing:
        return existing
    
    summary = get_meeting_summary(meeting_id)
    if not summary:
        raise ValueError(f"회의 요약 데이터가 없습니다. (meeting_id: {meeting_id})")
    
    minute = MeetingMinute(
        meeting_id=meeting_id,
        content=_format_minutes(summary),
        summary=summary.get("overview", {}).get("purpose", ""),
        status=MinuteStatus.draft,
        created_at=now_kst(),
        updated_at=now_kst(),
    )
    db.add(minute)
    db.commit()
    db.refresh(minute)

    # 알림: 회의록 초안 생성 완료 (참석자 전원)
    try:
        meeting = db.query(Meeting).filter(Meeting.id == meeting_id).one_or_none()
        if meeting is not None:
            participant_ids = [
                int(uid)
                for (uid,) in db.query(MeetingParticipant.user_id)
                .filter(MeetingParticipant.meeting_id == meeting_id)
                .all()
            ]
            for uid in participant_ids:
                notification_service.create_notification(
                    db,
                    workspace_id=int(meeting.workspace_id),
                    user_id=uid,
                    type_=NotificationType.minutes_ready,
                    title="회의록 생성 완료",
                    body=f"[{meeting.title}] 회의록 초안이 생성되었습니다. 확인해 보세요.",
                    link=f"/meetings/{meeting_id}/notes",
                    dedupe_key=f"minutes_ready:{meeting_id}",
                )
    except Exception:
        pass

    return minute

def _format_minutes(summary: dict) -> str:
    """
    회의록 형식 템플릿
    """
    lines = []

    overview = summary.get("overview", {})
    if overview:
        lines.append("## 개요")
        if overview.get("purpose", ""):
            lines.append(f"- 목적: {overview['purpose']}")
        if overview.get("datetime_str", ""):
            lines.append(f"- 일시: {overview['datetime_str']}")
    
    # - 참석자 
    attendees = summary.get("attendees", [])
    if attendees:
        lines.append(f"- 참석자: {', '.join(attendees)}")
    
    # \n## 논의 사항
    discussion_items = summary.get("discussion_items", [])
    if discussion_items:
        lines.append("\n## 논의 사항")
        for items in discussion_items:
            lines.append(f"### {items.get('topic', '')}")
            lines.append(f"{items.get('content', '')}")
    
    # \n## 결정 사항
    decisions = summary.get("decisions", [])
    if decisions:
        lines.append("\n## 결정 사항")
        for d in decisions:
            line = f"- {d.get('decision', '')}"
            lines.append(line)

    # \n## 액션 아이템
    action_items = summary.get("action_items", [])
    if action_items:
        lines.append("\n## 액션 아이템")
        for action_item in action_items:
            deadline = f"(~{action_item['deadline']})" if action_item.get('deadline') else ""
            lines.append(f"- [{action_item.get('assignee', '')}] {action_item.get('content', '')} {deadline}")

    # \n## 미결 사항
    pending_items = summary.get("pending_items", [])
    if pending_items:
        lines.append("\n## 미결 사항")
        for p in pending_items:
            lines.append(f"- {p.get('content', '')}")
    
    return "\n".join(lines)