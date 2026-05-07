import logging
from sqlalchemy.orm import Session

from app.domains.action.mongo_repository import get_or_build_meeting_summary
from app.domains.intelligence.models import MeetingMinute, MinuteStatus
from app.domains.meeting.models import Meeting, MeetingParticipant
from app.domains.notification import service as notification_service
from app.domains.notification.models import NotificationType
from app.domains.user.models import User
from app.utils.time_utils import now_kst

logger = logging.getLogger(__name__)


async def build_and_save_minutes(
    db: Session,
    meeting_id: int,
) -> MeetingMinute:
    """회의록을 생성하고 DB에 저장합니다. 기존 회의록이 있으면 덮어씁니다."""
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).one_or_none()
    if meeting is None:
        raise ValueError(f"회의를 찾을 수 없습니다. (meeting_id: {meeting_id})")
    workspace_id = int(meeting.workspace_id) if meeting else 0
    summary = await get_or_build_meeting_summary(meeting_id, workspace_id)
    if summary is None:
        raise ValueError(
            f"knowledge 요약(meeting_summaries)이 없어 회의록을 생성할 수 없습니다. (meeting_id: {meeting_id})"
        )
    content = _format_minutes(summary)

    existing = (
        db.query(MeetingMinute)
        .filter(MeetingMinute.meeting_id == meeting_id)
        .first()
    )
    if existing:
        existing.content = content
        existing.updated_at = now_kst()
        db.commit()
        db.refresh(existing)
        return existing

    minute = MeetingMinute(
        meeting_id=meeting_id,
        content=content,
        summary=(summary or {}).get("overview_summary", ""),
        status=MinuteStatus.draft,
        created_at=now_kst(),
        updated_at=now_kst(),
    )
    db.add(minute)
    db.commit()
    db.refresh(minute)

    _notify_participants(db, meeting_id)
    return minute


def _notify_participants(db: Session, meeting_id: int) -> None:
    try:
        meeting = db.query(Meeting).filter(Meeting.id == meeting_id).one_or_none()
        if meeting is None:
            return
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
        logger.exception("참석자 알림 전송 실패 (meeting_id=%d)", meeting_id)


def _as_dict(item: object, text_key: str = "content") -> dict:
    """항목이 str이면 {text_key: item} 딕셔너리로 정규화합니다."""
    if isinstance(item, dict):
        return item
    return {text_key: str(item)}


def _build_default_minutes(db: Session, meeting_id: int) -> str:
    """DB 정보만으로 기본 양식을 생성합니다. LLM·요약 불필요.

    저장소: meeting_minutes 테이블 (MeetingMinute 모델).
    일시는 scheduled_at 우선, 없으면 started_at.
    """
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()

    lines: list[str] = ["## 개요"]
    if meeting:
        dt_obj = meeting.scheduled_at or meeting.started_at
        lines.append(f"- 일시: {dt_obj.strftime('%Y년 %m월 %d일 %H:%M')}" if dt_obj else "- 일시: ")
        participants = (
            db.query(User.name)
            .join(MeetingParticipant, MeetingParticipant.user_id == User.id)
            .filter(MeetingParticipant.meeting_id == meeting_id)
            .all()
        )
        names = ", ".join(row.name for row in participants if row.name)
        lines.append(f"- 참석자: {names}" if names else "- 참석자: ")
    else:
        lines += ["- 일시: ", "- 참석자: "]

    lines += [
        "",
        "## 논의 사항",
        "",
        "## 결정 사항",
        "",
        "## 액션 아이템",
        "",
        "## 미결/특이 사항",
        "",
    ]
    return "\n".join(lines)


def ensure_minutes(db: Session, meeting_id: int) -> MeetingMinute:
    """기존 회의록을 반환하거나, 없으면 기본 양식으로 생성 후 반환합니다.

    저장소: meeting_minutes 테이블 (MeetingMinute 모델).
    """
    existing = db.query(MeetingMinute).filter(MeetingMinute.meeting_id == meeting_id).first()
    if existing:
        return existing

    content = _build_default_minutes(db, meeting_id)
    minute = MeetingMinute(
        meeting_id=meeting_id,
        content=content,
        summary="",
        status=MinuteStatus.draft,
        created_at=now_kst(),
        updated_at=now_kst(),
    )
    db.add(minute)
    db.commit()
    db.refresh(minute)
    return minute


def _format_minutes(summary: dict) -> str:
    lines: list[str] = []
    meetings = summary.get("meetings", []) or []
    first_meeting = meetings[0] if meetings and isinstance(meetings[0], dict) else {}

    title = first_meeting.get("title", "")
    date_text = first_meeting.get("date", "")
    attendees = summary.get("attendees", []) or first_meeting.get("attendees", []) or []

    if title:
        lines += ["## 제목", str(title), ""]
    if date_text:
        lines += ["## 일시", str(date_text), ""]
    if attendees:
        lines += ["## 참석자"]
        lines.extend(f"- {str(name)}" for name in attendees if str(name).strip())
        lines.append("")

    overview_summary = summary.get("overview_summary", "")
    if overview_summary:
        lines += ["## 개요", str(overview_summary), ""]

    agenda_items = summary.get("agenda_items", []) or []
    if agenda_items:
        lines += ["## 주요 안건"]
        lines.extend(f"{idx}. {str(item)}" for idx, item in enumerate(agenda_items, 1))
        lines.append("")

    discussion_items = summary.get("discussion_items", []) or []
    if discussion_items:
        lines += ["## 논의 사항"]
        for raw in discussion_items:
            item = _as_dict(raw, "content")
            topic = str(item.get("topic", "")).strip()
            content = str(item.get("content", "")).strip()
            if topic:
                lines.append(f"### {topic}")
            if content:
                lines.append(content)
        lines.append("")

    decisions = summary.get("decisions", []) or []
    if decisions:
        lines += ["## 결정 사항"]
        for raw in decisions:
            d = _as_dict(raw, "decision")
            text = str(d.get("decision", "") or d.get("content", "")).strip()
            if text:
                lines.append(f"- {text}")
        lines.append("")

    action_items = summary.get("action_items", []) or []
    if action_items:
        lines += ["## 액션 아이템"]
        for raw in action_items:
            a = _as_dict(raw, "content")
            content = str(a.get("content", "")).strip()
            if not content:
                continue
            assignee = str(a.get("assignee", "") or "").strip()
            deadline = str(a.get("deadline", "") or "").strip()
            prefix = f"{assignee}: " if assignee else ""
            suffix = f" (~{deadline})" if deadline else ""
            lines.append(f"- {prefix}{content}{suffix}")
        lines.append("")

    pending_items = summary.get("pending_items", []) or []
    if pending_items:
        lines += ["## 미결 사항"]
        for raw in pending_items:
            p = _as_dict(raw, "content")
            content = str(p.get("content", "")).strip()
            if content:
                lines.append(f"- {content}")

    return "\n".join(lines)
