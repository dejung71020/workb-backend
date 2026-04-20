# app\domains\workspace\repository.py
from datetime import datetime, timedelta
from sqlalchemy import and_
from sqlalchemy.orm import Session

from collections import defaultdict

from app.domains.meeting.models import Meeting, MeetingParticipant, MeetingStatus
from app.domains.user.models import User
from app.domains.action.models import ActionItem, ActionStatus


class DashboardRepository:

    @staticmethod
    def get_meetings_by_workspace(db: Session, workspace_id: int) -> list[Meeting]:
        return (
            db.query(Meeting)
            .filter(Meeting.workspace_id == workspace_id)
            .order_by(Meeting.scheduled_at.desc())
            .all()
        )

    @staticmethod
    def get_participants_for_meetings(
        db: Session, meeting_ids: list[int]
    ) -> dict[int, list[tuple[int, str]]]:
        """meeting_id → [(user_id, name), ...] 참석자 목록 (회의·사용자 id 순)."""
        if not meeting_ids:
            return {}
        rows = (
            db.query(MeetingParticipant.meeting_id, User.id, User.name)
            .join(User, User.id == MeetingParticipant.user_id)
            .filter(MeetingParticipant.meeting_id.in_(meeting_ids))
            .order_by(MeetingParticipant.meeting_id, MeetingParticipant.id)
            .all()
        )
        by_mid: dict[int, list[tuple[int, str]]] = defaultdict(list)
        for meeting_id, user_id, name in rows:
            by_mid[int(meeting_id)].append((int(user_id), str(name)))
        return dict(by_mid)

    @staticmethod
    def get_done_meetings_this_week(
        db: Session, workspace_id: int, week_start: datetime, week_end: datetime
    ) -> list[Meeting]:
        return (
            db.query(Meeting)
            .filter(
                and_(
                    Meeting.workspace_id == workspace_id,
                    Meeting.status == MeetingStatus.done,
                    Meeting.ended_at >= week_start,
                    Meeting.ended_at < week_end,
                )
            )
            .all()
        )

    @staticmethod
    def get_pending_action_items(db: Session, workspace_id: int) -> list[dict]:
        rows = (
            db.query(
                ActionItem.id,
                ActionItem.content,
                ActionItem.due_date,
                Meeting.title.label("meeting_title"),
            )
            .join(Meeting, ActionItem.meeting_id == Meeting.id)
            .filter(
                and_(
                    Meeting.workspace_id == workspace_id,
                    ActionItem.status == ActionStatus.pending,
                )
            )
            .order_by(ActionItem.due_date.asc())
            .all()
        )
        return [
            {
                "id": r.id,
                "content": r.content,
                "due_date": r.due_date,
                "meeting_title": r.meeting_title,
            }
            for r in rows
        ]
