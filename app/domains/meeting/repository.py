# app\domains\meeting\repository.py
from __future__ import annotations

from sqlalchemy import desc, func, or_
from sqlalchemy.orm import Session

from app.domains.intelligence.models import MeetingMinute
from app.domains.meeting.models import Meeting


class MeetingHistoryRepository:
    @staticmethod
    def search_history(
        db: Session,
        workspace_id: int,
        keyword: str | None,
        page: int,
        size: int,
    ) -> tuple[int, list[tuple[Meeting, MeetingMinute | None]]]:
        q = (
            db.query(Meeting, MeetingMinute)
            .outerjoin(MeetingMinute, MeetingMinute.meeting_id == Meeting.id)
            .filter(Meeting.workspace_id == workspace_id)
        )

        if keyword is not None:
            kw = keyword.strip()
            if kw:
                like = f"%{kw}%"
                q = q.filter(
                    or_(
                        Meeting.title.ilike(like),
                        MeetingMinute.content.ilike(like),
                        MeetingMinute.summary.ilike(like),
                    )
                )

        total = q.with_entities(func.count(Meeting.id)).scalar() or 0

        rows = (
            # MySQL does not support "NULLS LAST" syntax.
            # Push NULL scheduled_at to the end, then sort by datetime desc.
            q.order_by(Meeting.scheduled_at.is_(None), desc(Meeting.scheduled_at))
            .offset((page - 1) * size)
            .limit(size)
            .all()
        )

        return int(total), rows
