import json
import logging
import re

from sqlalchemy.orm import Session

from app.domains.intelligence.models import MeetingMinute, MinutePhoto, MinuteStatus
from app.domains.meeting.models import Meeting, MeetingParticipant
from app.domains.notification import service as notification_service
from app.domains.notification.models import NotificationType
from app.domains.user.models import User
from app.utils.time_utils import now_kst

logger = logging.getLogger(__name__)


def parse_meeting_minute_summary(raw_summary: str | None) -> dict | None:
    """meeting_minutes.summary(text)를 회의록 포맷 dict로 변환합니다."""
    if not raw_summary or not str(raw_summary).strip():
        return None

    text = str(raw_summary).strip()
    try:
        parsed = json.loads(text)
    except Exception:
        return {"overview_summary": text}

    if not isinstance(parsed, dict):
        return {"overview_summary": text}

    inner = parsed.get("summary")
    if isinstance(inner, dict):
        parsed = inner

    return parsed


async def build_and_save_minutes(
    db: Session,
    meeting_id: int,
) -> MeetingMinute:
    """DB 테이블에서 데이터를 수집하고 LLM으로 회의록을 생성해 저장합니다."""
    from langchain_openai import ChatOpenAI
    from app.core.config import settings
    from app.domains.action.models import WbsEpic, WbsTask, ActionItem
    from app.domains.action import minutes_repository as minutes_repo

    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).one_or_none()
    if not meeting:
        raise ValueError(f"회의를 찾을 수 없습니다. (meeting_id: {meeting_id})")

    # ── 기본 메타 ────────────────────────────────────────────────────────
    dt_obj = meeting.started_at or meeting.scheduled_at
    datetime_str = dt_obj.strftime("%Y년 %m월 %d일 %H:%M") if dt_obj else ""
    date_str = dt_obj.strftime("%Y-%m-%d") if dt_obj else ""

    creator = db.query(User).filter(User.id == meeting.created_by).first()
    creator_name = creator.name if creator else ""
    dept_name = (
        minutes_repo.get_dept_name(db, creator, int(meeting.workspace_id))
        if creator
        else ""
    )

    # ── 참석자 ──────────────────────────────────────────────────────────
    attendee_rows = (
        db.query(User.name)
        .join(MeetingParticipant, MeetingParticipant.user_id == User.id)
        .filter(MeetingParticipant.meeting_id == meeting_id)
        .all()
    )
    attendee_names = [row.name for row in attendee_rows if row.name]

    # ── 결정 사항 ────────────────────────────────────────────────────────
    from app.domains.intelligence.models import Decision
    decisions = (
        db.query(Decision)
        .filter(Decision.meeting_id == meeting_id)
        .order_by(Decision.detected_at)
        .all()
    )

    # ── WBS 에픽/태스크 ──────────────────────────────────────────────────
    epics = (
        db.query(WbsEpic)
        .filter(WbsEpic.meeting_id == meeting_id)
        .order_by(WbsEpic.order_index)
        .all()
    )
    epic_ids = [e.id for e in epics]
    tasks = (
        db.query(WbsTask)
        .filter(WbsTask.epic_id.in_(epic_ids))
        .order_by(WbsTask.order_index)
        .all()
        if epic_ids
        else []
    )

    # ── 액션 아이템 ──────────────────────────────────────────────────────
    action_items_rows = (
        db.query(ActionItem)
        .filter(ActionItem.meeting_id == meeting_id)
        .all()
    )
    action_assignee_ids = [
        a.assignee_id for a in action_items_rows if a.assignee_id
    ]
    action_assignees: dict[int, str] = {}
    if action_assignee_ids:
        users = db.query(User).filter(User.id.in_(action_assignee_ids)).all()
        action_assignees = {u.id: u.name for u in users}

    # ── 사진 ────────────────────────────────────────────────────────────
    existing_minute = (
        db.query(MeetingMinute)
        .filter(MeetingMinute.meeting_id == meeting_id)
        .first()
    )
    photo_urls: list[str] = []
    if existing_minute:
        photos = (
            db.query(MinutePhoto)
            .filter(MinutePhoto.minute_id == existing_minute.id)
            .order_by(MinutePhoto.taken_at.asc())
            .all()
        )
        photo_urls = [p.photo_url for p in photos if p.photo_url]

    # ── 프롬프트용 텍스트 변환 ───────────────────────────────────────────
    decisions_text = (
        "\n".join(
            f"- {d.content} ({'확정' if d.is_confirmed else '미확정'})"
            for d in decisions
        )
        or "(없음)"
    )
    epics_text = (
        "\n".join(f"- {e.title}" for e in epics) or "(없음)"
    )
    tasks_text = (
        "\n".join(
            f"- [{t.assignee_name or '미정'}] {t.title}"
            f" / {t.status.value} / {t.progress}%"
            f" / ~{t.due_date.isoformat() if t.due_date else '미정'}"
            for t in tasks
        )
        or "(없음)"
    )
    action_items_text = (
        "\n".join(
            f"- {action_assignees.get(a.assignee_id, '미정') if a.assignee_id else '미정'}:"
            f" {a.content}"
            f" (~{a.due_date.isoformat() if a.due_date else '미정'})"
            f" [{a.status.value}]"
            for a in action_items_rows
        )
        or "(없음)"
    )

    # ── LLM 호출 ─────────────────────────────────────────────────────────
    llm = ChatOpenAI(model="gpt-4o-mini", api_key=settings.OPENAI_API_KEY)

    prompt = f"""다음 회의 데이터를 바탕으로 회의록 JSON을 작성하세요.

[회의 제목] {meeting.title}
[회의 일시] {datetime_str}
[참석자] {', '.join(attendee_names) or '(없음)'}

[결정 사항]
{decisions_text}

[WBS 에픽]
{epics_text}

[WBS 태스크]
{tasks_text}

[액션 아이템]
{action_items_text}

반드시 아래 JSON 형식으로만 답변하세요.

{{
    "meetings": [{{"title": "{meeting.title}", "date": "{date_str}", "attendees": {json.dumps(attendee_names, ensure_ascii=False)}}}],
    "overview_summary": "전체 회의 내용 요약 (2~4문장)",
    "agenda_items": ["안건1", "안건2", ...],
    "discussion_items": [{{"topic": "주제명", "content": "구체적으로 논의된 내용"}}],
    "decisions": ["결정 사항 (결론/근거 포함)", ...],
    "action_items": [{{"assignee": "담당자 또는 null", "content": "할 일", "deadline": "기한 또는 null"}}],
    "pending_items": [{{"content": "미결 사항 내용"}}]
}}"""

    result = await llm.ainvoke(prompt)
    json_match = re.search(r"\{.*\}", result.content, re.DOTALL)
    try:
        summary_dict = json.loads(json_match.group()) if json_match else {}
    except json.JSONDecodeError:
        summary_dict = {}

    content = _format_minutes(summary_dict)

    # ── DB 저장 ──────────────────────────────────────────────────────────
    now = now_kst()
    if existing_minute:
        existing_minute.content = content
        existing_minute.updated_at = now
        db.commit()
        db.refresh(existing_minute)
        return existing_minute

    minute = MeetingMinute(
        meeting_id=meeting_id,
        content=content,
        status=MinuteStatus.draft,
        created_at=now,
        updated_at=now,
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
    if isinstance(item, dict):
        return item
    return {text_key: str(item)}


def _build_default_minutes(db: Session, meeting_id: int) -> str:
    """DB 정보만으로 기본 양식을 생성합니다. LLM·요약 불필요."""
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
    """기존 회의록을 반환하거나, 없으면 기본 양식으로 생성 후 반환합니다."""
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
        lines += [f"- 일시: {date_text}"]
    if attendees:
        lines += [f"- 참석자: {', '.join(str(n) for n in attendees if str(n).strip())}"]
    if date_text or attendees:
        lines.append("")

    overview_summary = summary.get("overview_summary", "")
    if overview_summary:
        lines += ["## 개요", str(overview_summary), ""]

    agenda_items = summary.get("agenda_items", []) or []
    if agenda_items:
        lines += ["## 안건"]
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
