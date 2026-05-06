import logging
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domains.action.mongo_repository import get_meeting_summary, get_meeting_utterances
from app.domains.action.services.minutes_prompt_builder import build_minutes_from_transcript_prompt
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
    summary = get_meeting_summary(meeting_id)
    if summary is not None:
        content = _format_minutes(summary)
    else:
        logger.info(
            "meeting_id=%d 요약 없음 — utterances 폴백으로 회의록 생성 시도",
            meeting_id,
        )
        utterances = get_meeting_utterances(meeting_id)
        if not utterances:
            raise ValueError(
                f"회의 요약과 발화 데이터가 모두 없습니다. (meeting_id: {meeting_id})"
            )
        content = await _generate_from_transcript(utterances)

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


async def _generate_from_transcript(utterances: list[dict]) -> str:
    if not settings.OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY 미설정 — 발화 폴백에서 LLM 호출 불가")
        raise ValueError("회의 요약 데이터가 없고 LLM 키도 설정되지 않아 회의록을 생성할 수 없습니다.")

    from openai import AsyncOpenAI  # noqa: PLC0415

    prompt = build_minutes_from_transcript_prompt(utterances)
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=4000,
        timeout=60.0,
    )
    return response.choices[0].message.content or ""


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

    overview = summary.get("overview", {})
    if isinstance(overview, dict) and overview:
        lines.append("## 개요")
        if overview.get("purpose", ""):
            lines.append(f"- 목적: {overview['purpose']}")
        if overview.get("datetime_str", ""):
            lines.append(f"- 일시: {overview['datetime_str']}")

    attendees = summary.get("attendees", [])
    if attendees:
        lines.append(f"- 참석자: {', '.join(str(a) for a in attendees)}")

    discussion_items = summary.get("discussion_items", [])
    if discussion_items:
        lines.append("\n## 논의 사항")
        for raw in discussion_items:
            item = _as_dict(raw, "content")
            lines.append(f"### {item.get('topic', '')}")
            lines.append(item.get("content", ""))

    decisions = summary.get("decisions", [])
    if decisions:
        lines.append("\n## 결정 사항")
        for raw in decisions:
            d = _as_dict(raw, "decision")
            lines.append(f"- {d.get('decision', '') or d.get('content', '')}")

    action_items = summary.get("action_items", [])
    if action_items:
        lines.append("\n## 액션 아이템")
        for raw in action_items:
            a = _as_dict(raw, "content")
            deadline = f"(~{a['deadline']})" if a.get("deadline") else ""
            lines.append(
                f"- [{a.get('assignee', '')}] {a.get('content', '')} {deadline}".rstrip()
            )

    pending_items = summary.get("pending_items", [])
    if pending_items:
        lines.append("\n## 미결 사항")
        for raw in pending_items:
            p = _as_dict(raw, "content")
            lines.append(f"- {p.get('content', '')}")

    return "\n".join(lines)
