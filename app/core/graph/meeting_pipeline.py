"""
LangGraph pipeline for meeting lifecycle and post-meeting artifacts.

Flow:
  meeting_start -> realtime_diarization -> postprocess_diarization -> wbs -> minutes

The actual realtime diarization is performed by the ASR/WebSocket service. This
graph coordinates the persisted backend steps around that service.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from app.domains.action.models import ActionItem, ActionStatus, Priority
from app.domains.action.mongo_repository import get_meeting_summary
from app.domains.action.services.minutes_builder import build_and_save_minutes
from app.domains.action.services.wbs_builder import build_wbs_template
from app.domains.intelligence.repository import save_utterances
from app.domains.meeting.models import MeetingParticipant
from app.domains.meeting.service import MeetingLifecycleService
from app.domains.user.models import User
from app.utils.time_utils import now_kst
from app.utils.redis_utils import r as redis_client

logger = logging.getLogger(__name__)

PipelineMode = Literal["start", "complete"]


class MeetingPipelineState(TypedDict, total=False):
    workspace_id: int
    meeting_id: int
    mode: PipelineMode
    realtime_utterance_count: int
    postprocessed_utterance_count: int
    summary: dict[str, Any]
    wbs: dict[str, Any]
    minutes_id: int
    errors: list[str]


def _append_error(state: MeetingPipelineState, message: str) -> dict[str, list[str]]:
    return {"errors": [*(state.get("errors") or []), message]}


async def meeting_start_node(state: MeetingPipelineState) -> dict[str, Any]:
    db = _session()
    try:
        MeetingLifecycleService.start_meeting(
            db,
            int(state["workspace_id"]),
            int(state["meeting_id"]),
        )
        return {}
    finally:
        db.close()


async def realtime_diarization_node(state: MeetingPipelineState) -> dict[str, Any]:
    """Observe realtime ASR output stored in Redis.

    Realtime speaker separation itself is owned by the ASR service. The pipeline
    records whether utterances are available so later nodes can persist them if
    the ASR service has not already written MongoDB utterances.
    """
    meeting_id = int(state["meeting_id"])
    count = await redis_client.llen(f"meeting:{meeting_id}:utterances")
    return {"realtime_utterance_count": int(count)}


async def postprocess_diarization_node(state: MeetingPipelineState) -> dict[str, Any]:
    """Persist final utterances and create the structured meeting summary."""
    meeting_id = int(state["meeting_id"])
    workspace_id = int(state["workspace_id"])

    utterances = await _collect_redis_utterances(meeting_id)
    if utterances:
        await save_utterances(
            str(meeting_id),
            {
                "meeting_id": meeting_id,
                "utterances": utterances,
            },
        )

    report_state = {
        "meeting_id": meeting_id,
        "workspace_id": workspace_id,
        "past_meeting_ids": None,
        "user_question": "",
        "function_type": "",
        "chat_response": "",
    }
    try:
        from app.domains.knowledge.agent_utils import quick_report_node

        await quick_report_node(report_state)
    except Exception as exc:
        logger.exception("quick_report failed in meeting pipeline: meeting_id=%s", meeting_id)
        return _append_error(state, f"quick_report 실패: {exc}")

    summary = get_meeting_summary(meeting_id) or {}
    db = _session()
    try:
        _persist_action_items_from_summary(db, meeting_id, workspace_id, summary)
    finally:
        db.close()

    return {
        "postprocessed_utterance_count": len(utterances),
        "summary": summary,
    }


async def wbs_node(state: MeetingPipelineState) -> dict[str, Any]:
    db = _session()
    try:
        wbs = await build_wbs_template(db, int(state["meeting_id"]))
        return {"wbs": wbs}
    except Exception as exc:
        logger.exception("WBS generation failed in meeting pipeline: meeting_id=%s", state.get("meeting_id"))
        return _append_error(state, f"WBS 생성 실패: {exc}")
    finally:
        db.close()


async def minutes_node(state: MeetingPipelineState) -> dict[str, Any]:
    db = _session()
    try:
        minute = await build_and_save_minutes(db, int(state["meeting_id"]))
        return {"minutes_id": int(minute.id)}
    except Exception as exc:
        logger.exception("minutes generation failed in meeting pipeline: meeting_id=%s", state.get("meeting_id"))
        return _append_error(state, f"회의록 생성 실패: {exc}")
    finally:
        db.close()


def _route_mode(state: MeetingPipelineState) -> str:
    return "meeting_start" if state.get("mode") == "start" else "postprocess_diarization"


def _build_graph():
    builder = StateGraph(MeetingPipelineState)
    builder.add_node("meeting_start", meeting_start_node)
    builder.add_node("realtime_diarization", realtime_diarization_node)
    builder.add_node("postprocess_diarization", postprocess_diarization_node)
    builder.add_node("wbs", wbs_node)
    builder.add_node("minutes", minutes_node)

    builder.add_conditional_edges(
        START,
        _route_mode,
        {
            "meeting_start": "meeting_start",
            "postprocess_diarization": "postprocess_diarization",
        },
    )
    builder.add_edge("meeting_start", "realtime_diarization")
    builder.add_edge("realtime_diarization", END)
    builder.add_edge("postprocess_diarization", "wbs")
    builder.add_edge("wbs", "minutes")
    builder.add_edge("minutes", END)
    return builder.compile()


meeting_pipeline_graph = _build_graph()


async def run_meeting_start_pipeline(
    workspace_id: int,
    meeting_id: int,
) -> MeetingPipelineState:
    return await meeting_pipeline_graph.ainvoke({
        "workspace_id": workspace_id,
        "meeting_id": meeting_id,
        "mode": "start",
        "errors": [],
    })


async def run_meeting_completion_pipeline(
    workspace_id: int,
    meeting_id: int,
) -> MeetingPipelineState:
    return await meeting_pipeline_graph.ainvoke({
        "workspace_id": workspace_id,
        "meeting_id": meeting_id,
        "mode": "complete",
        "errors": [],
    })


def _session() -> Session:
    from app.infra.database.session import SessionLocal

    return SessionLocal()


async def _collect_redis_utterances(meeting_id: int) -> list[dict[str, Any]]:
    utterance_key = f"meeting:{meeting_id}:utterances"
    speaker_key = f"meeting:{meeting_id}:speakers"

    raw_utterances = await redis_client.lrange(utterance_key, 0, -1)
    raw_speakers = await redis_client.hgetall(speaker_key)

    speaker_map: dict[str, str] = {}
    for raw_key, raw_value in raw_speakers.items():
        key = raw_key.decode() if isinstance(raw_key, bytes) else str(raw_key)
        value = raw_value.decode() if isinstance(raw_value, bytes) else str(raw_value)
        speaker_map[key] = value

    utterances: list[dict[str, Any]] = []
    for seq, raw in enumerate(raw_utterances):
        try:
            payload = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
        except (TypeError, json.JSONDecodeError):
            continue

        content = payload.get("content") or payload.get("text") or ""
        if not str(content).strip():
            continue

        speaker_ref = payload.get("speaker_id")
        mapped_user_id = speaker_map.get(str(speaker_ref)) if speaker_ref is not None else None
        speaker_id = int(mapped_user_id) if mapped_user_id and mapped_user_id.isdigit() else None
        speaker_label = payload.get("speaker") or payload.get("speaker_label")
        if not speaker_label:
            speaker_label = f"User {speaker_id}" if speaker_id else "알 수 없음"

        utterances.append({
            "seq": seq,
            "speaker_id": speaker_id,
            "speaker_label": speaker_label,
            "timestamp": payload.get("timestamp"),
            "content": str(content).strip(),
            "text": str(content).strip(),
            "start": payload.get("start", 0.0),
            "end": payload.get("end", 0.0),
            "confidence": payload.get("confidence"),
        })

    return utterances


def _persist_action_items_from_summary(
    db: Session,
    meeting_id: int,
    workspace_id: int,
    summary: dict[str, Any],
) -> None:
    action_items = summary.get("action_items") if isinstance(summary, dict) else None
    if not action_items:
        return

    existing_contents = {
        content
        for (content,) in db.query(ActionItem.content)
        .filter(ActionItem.meeting_id == meeting_id)
        .all()
    }

    participants = (
        db.query(User)
        .join(MeetingParticipant, MeetingParticipant.user_id == User.id)
        .filter(MeetingParticipant.meeting_id == meeting_id)
        .all()
    )
    if not participants:
        participants = db.query(User).filter(User.workspace_id == workspace_id).all()

    user_by_name = {user.name.strip(): user for user in participants if user.name}

    for raw in action_items:
        if not isinstance(raw, dict):
            content = str(raw).strip()
            assignee_name = ""
            deadline = None
            urgency = "normal"
            priority = "medium"
        else:
            content = str(raw.get("content") or "").strip()
            assignee_name = str(raw.get("assignee") or "").strip()
            deadline = raw.get("deadline")
            urgency = str(raw.get("urgency") or "normal")
            priority = _normalize_priority(str(raw.get("priority") or "medium"))

        if not content or content in existing_contents:
            continue

        assignee = user_by_name.get(assignee_name)
        db.add(ActionItem(
            meeting_id=meeting_id,
            content=content,
            assignee_id=int(assignee.id) if assignee else None,
            due_date=_parse_date(deadline),
            status=ActionStatus.pending,
            detected_at=now_kst().replace(tzinfo=None),
            priority=Priority(priority),
            urgency=urgency[:20],
        ))
        existing_contents.add(content)

    db.commit()


def _normalize_priority(value: str) -> str:
    value = value.lower()
    if value in {"high", "critical", "medium", "low"}:
        return value
    if value == "normal":
        return "medium"
    return "medium"


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text or text.lower() in {"none", "null", "없음"}:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None
