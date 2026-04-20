# app\domains\workspace\service.py
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from app.domains.meeting.models import MeetingStatus
from app.domains.workspace.repository import DashboardRepository
from app.domains.workspace.schemas import (
    DashboardResponse,
    DashboardParticipantItem,
    MeetingItem,
    MeetingsGroup,
    WeeklySummary,
    PendingActionItemResponse,
)


class DashboardService:

    @staticmethod
    def get_dashboard(db: Session, workspace_id: int) -> DashboardResponse:
        # 1) 회의 목록을 상태별로 분류
        today = datetime.now()
        # 금주 기준: 일(00:00) ~ 다음 일(00:00)
        week_start = (today - timedelta(days=(today.weekday() + 1) % 7)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        week_end = week_start + timedelta(days=7)

        meetings = DashboardRepository.get_meetings_by_workspace(db, workspace_id)
        # 홈 탭(진행/예정/완료)은 금주(일~토)만 표시
        def _in_this_week(m) -> bool:
            dt = m.started_at or m.scheduled_at or m.ended_at
            return dt is not None and week_start <= dt < week_end

        meetings = [m for m in meetings if _in_this_week(m)]
        meeting_ids = [int(m.id) for m in meetings]
        participants_by = DashboardRepository.get_participants_for_meetings(db, meeting_ids)

        grouped: dict[str, list[MeetingItem]] = {
            "in_progress": [],
            "scheduled": [],
            "done": [],
        }
        for m in meetings:
            plist = participants_by.get(int(m.id), [])
            item = MeetingItem(
                id=m.id,
                title=m.title,
                status=m.status.value if isinstance(m.status, MeetingStatus) else m.status,
                scheduled_at=m.scheduled_at,
                started_at=m.started_at,
                ended_at=m.ended_at,
                meeting_type=m.meeting_type,
                participants=[
                    DashboardParticipantItem(user_id=uid, name=name) for uid, name in plist
                ],
            )
            if m.status == MeetingStatus.in_progress:
                grouped["in_progress"].append(item)
            elif m.status == MeetingStatus.scheduled:
                grouped["scheduled"].append(item)
            else:
                grouped["done"].append(item)

        meetings_group = MeetingsGroup(**grouped)

        # 2) 주간 요약 — 금주(일~토) 기준 done 회의 집계
        done_this_week = DashboardRepository.get_done_meetings_this_week(
            db, workspace_id, week_start, week_end
        )

        total_duration_min = 0.0
        for m in done_this_week:
            if m.started_at and m.ended_at:
                delta = (m.ended_at - m.started_at).total_seconds() / 60
                total_duration_min += max(delta, 0)

        weekly_summary = WeeklySummary(
            total_count=len(done_this_week),
            total_duration_min=round(total_duration_min, 1),
            summary_cards=[],
        )

        # 3) 미결 액션 아이템
        pending_rows = DashboardRepository.get_pending_action_items(db, workspace_id)
        pending_action_items = [PendingActionItemResponse(**r) for r in pending_rows]

        # 4) 다음 회의 제안 — AI 모듈 연동 전이므로 None
        next_meeting_suggestion = None

        return DashboardResponse(
            meetings=meetings_group,
            weekly_summary=weekly_summary,
            pending_action_items=pending_action_items,
            next_meeting_suggestion=next_meeting_suggestion,
        )
