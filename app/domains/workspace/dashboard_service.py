"""워크스페이스 홈 대시보드 집계."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.domains.action.models import ActionItem, ActionStatus
from app.domains.meeting.models import Meeting, MeetingParticipant, MeetingStatus
from app.domains.user.models import User
from app.domains.workspace.models import Workspace
from app.domains.workspace.schemas import (
    DashboardMeetingOut,
    DashboardMeetingsBundle,
    DashboardParticipantOut,
    DashboardResponse,
    PendingActionItemOut,
    WeeklySummaryOut,
)

def _status_value(m: Meeting) -> str:
    s = m.status
    return s.value if hasattr(s, "value") else str(s)


def _week_start_local(d: date) -> datetime:
    monday = d - timedelta(days=d.weekday())
    return datetime.combine(monday, datetime.min.time())


class DashboardService:
    @staticmethod
    def get_dashboard(db: Session, workspace_id: int) -> DashboardResponse:
        ws = db.query(Workspace).filter(Workspace.id == workspace_id).one_or_none()
        if ws is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="워크스페이스를 찾을 수 없습니다.",
            )

        meetings = (
            db.query(Meeting).filter(Meeting.workspace_id == workspace_id).all()
        )
        m_ids = [int(m.id) for m in meetings]
        parts_by_mid: dict[int, list[DashboardParticipantOut]] = defaultdict(list)
        if m_ids:
            rows = (
                db.query(MeetingParticipant, User)
                .join(User, User.id == MeetingParticipant.user_id)
                .filter(MeetingParticipant.meeting_id.in_(m_ids))
                .all()
            )
            for mp, u in rows:
                parts_by_mid[int(mp.meeting_id)].append(
                    DashboardParticipantOut(user_id=int(u.id), name=str(u.name))
                )

        def to_out(m: Meeting) -> DashboardMeetingOut:
            return DashboardMeetingOut(
                id=int(m.id),
                title=str(m.title),
                status=_status_value(m),
                scheduled_at=m.scheduled_at,
                started_at=m.started_at,
                ended_at=m.ended_at,
                meeting_type=m.meeting_type,
                participants=parts_by_mid.get(int(m.id), []),
            )

        in_progress: list[DashboardMeetingOut] = []
        scheduled: list[DashboardMeetingOut] = []
        done: list[DashboardMeetingOut] = []
        for m in meetings:
            st = _status_value(m)
            if st == MeetingStatus.in_progress.value:
                in_progress.append(to_out(m))
            elif st == MeetingStatus.scheduled.value:
                scheduled.append(to_out(m))
            elif st == MeetingStatus.done.value:
                done.append(to_out(m))

        _min = datetime(1970, 1, 1)
        _max = datetime(9999, 12, 31, 23, 59, 59)
        in_progress.sort(
            key=lambda x: x.started_at or x.scheduled_at or _min,
            reverse=True,
        )
        scheduled.sort(key=lambda x: (x.scheduled_at is None, x.scheduled_at or _max))
        done.sort(
            key=lambda x: x.ended_at or x.started_at or _min,
            reverse=True,
        )

        today = date.today()
        week_start_naive = _week_start_local(today)
        week_done_count = 0
        total_minutes = 0
        for m in meetings:
            if _status_value(m) != MeetingStatus.done.value or m.ended_at is None:
                continue
            ended = m.ended_at
            ended_cmp = ended.replace(tzinfo=None) if ended.tzinfo else ended
            if ended_cmp >= week_start_naive:
                week_done_count += 1
                if m.started_at:
                    start = m.started_at
                    start_cmp = start.replace(tzinfo=None) if start.tzinfo else start
                    delta = ended_cmp - start_cmp
                    total_minutes += max(0, int(delta.total_seconds() // 60))

        weekly = WeeklySummaryOut(
            total_count=week_done_count,
            total_duration_min=total_minutes,
            summary_cards=[],
        )

        pending_rows = (
            db.query(ActionItem, Meeting.title)
            .join(Meeting, Meeting.id == ActionItem.meeting_id)
            .filter(
                Meeting.workspace_id == workspace_id,
                ActionItem.status == ActionStatus.pending,
            )
            .order_by(ActionItem.id.asc())
            .all()
        )
        pending_items = [
            PendingActionItemOut(
                id=int(ai.id),
                content=str(ai.content),
                due_date=ai.due_date,
                meeting_title=str(title),
            )
            for ai, title in pending_rows
        ]

        return DashboardResponse(
            meetings=DashboardMeetingsBundle(
                in_progress=in_progress,
                scheduled=scheduled,
                done=done,
            ),
            weekly_summary=weekly,
            pending_action_items=pending_items,
            next_meeting_suggestion=None,
        )
