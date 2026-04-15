# app\domains\meeting\service.py
from collections import defaultdict
from datetime import datetime, time

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.domains.meeting.models import Meeting, MeetingParticipant, MeetingStatus
from app.domains.meeting.schemas import (
    CreateMeetingRequest,
    CreateMeetingResponse,
    CreateMeetingResponseData,
    MeetingSearchData,
    MeetingSearchItemOut,
    MeetingSearchParams,
    MeetingSearchParticipantOut,
    MeetingSearchResponse,
)
from app.domains.user.models import User
from app.domains.intelligence.models import MeetingMinute


class MeetingCreateService:
    """회의 생성(트랜잭션: meetings + meeting_participants)."""

    @staticmethod
    def create_meeting(
        db: Session,
        workspace_id: int,
        created_by: int,
        payload: CreateMeetingRequest,
    ) -> CreateMeetingResponse:
        meeting = Meeting(
            workspace_id=workspace_id,
            created_by=created_by,
            title=payload.title,
            meeting_type=payload.meeting_type,
            scheduled_at=payload.scheduled_at,
            status=MeetingStatus.scheduled,
            google_calendar_event_id=None,
        )

        try:
            db.add(meeting)
            db.flush()

            if payload.sync_google_calendar:
                # TODO: Google Calendar 연동 모듈 호출 및 event_id 업데이트
                pass

            # 생성자는 항상 참석자에 포함, is_host=1. 나머지는 participant_ids (중복·생성자 중복 제거)
            ordered_user_ids: list[int] = [created_by]
            for uid in payload.participant_ids:
                if uid != created_by and uid not in ordered_user_ids:
                    ordered_user_ids.append(uid)

            for uid in ordered_user_ids:
                db.add(
                    MeetingParticipant(
                        meeting_id=meeting.id,
                        user_id=uid,
                        is_host=(uid == created_by),
                    )
                )

            db.commit()
            db.refresh(meeting)
        except Exception:
            db.rollback()
            raise

        return CreateMeetingResponse(
            success=True,
            data=CreateMeetingResponseData(
                meeting_id=int(meeting.id),
                title=meeting.title,
                scheduled_at=meeting.scheduled_at,
                google_calendar_event_id=meeting.google_calendar_event_id,
            ),
            message="OK",
        )


class MeetingSearchService:
    """워크스페이스 회의 검색 (동적 필터 + 배치 로딩으로 N+1 방지)."""

    @staticmethod
    def search(
        db: Session,
        workspace_id: int,
        params: MeetingSearchParams,
    ) -> MeetingSearchResponse:
        q = db.query(Meeting).filter(Meeting.workspace_id == workspace_id)

        if params.keyword is not None:
            kw = params.keyword.strip()
            if kw:
                q = q.filter(Meeting.title.ilike(f"%{kw}%"))

        if params.from_date is not None:
            q = q.filter(
                Meeting.scheduled_at
                >= datetime.combine(params.from_date, time.min)
            )

        if params.to_date is not None:
            q = q.filter(
                Meeting.scheduled_at
                <= datetime.combine(params.to_date, time.max)
            )

        if params.participant_id is not None:
            q = (
                q.join(
                    MeetingParticipant,
                    MeetingParticipant.meeting_id == Meeting.id,
                ).filter(MeetingParticipant.user_id == params.participant_id)
            ).distinct()

        meetings = q.order_by(desc(Meeting.scheduled_at).nulls_last()).all()

        if not meetings:
            return MeetingSearchResponse(
                success=True,
                data=MeetingSearchData(meetings=[]),
                message="OK",
            )

        m_ids = [int(m.id) for m in meetings]

        # 참석자 + 이름: 회의 ID 단위로 한 번에 조회 (N+1 방지)
        participant_rows = (
            db.query(MeetingParticipant, User.name)
            .join(User, User.id == MeetingParticipant.user_id)
            .filter(MeetingParticipant.meeting_id.in_(m_ids))
            .order_by(MeetingParticipant.meeting_id, MeetingParticipant.id)
            .all()
        )
        participants_by_meeting: dict[int, list[MeetingSearchParticipantOut]] = defaultdict(list)
        for mp, user_name in participant_rows:
            participants_by_meeting[int(mp.meeting_id)].append(
                MeetingSearchParticipantOut(
                    user_id=int(mp.user_id),
                    name=user_name,
                )
            )

        # 회의록 요약: meeting_id IN 한 번에 조회
        minute_rows = (
            db.query(MeetingMinute)
            .filter(MeetingMinute.meeting_id.in_(m_ids))
            .all()
        )
        summary_by_meeting: dict[int, str | None] = {
            int(row.meeting_id): row.summary for row in minute_rows
        }

        items: list[MeetingSearchItemOut] = []
        for m in meetings:
            mid = int(m.id)
            items.append(
                MeetingSearchItemOut(
                    meeting_id=mid,
                    title=m.title,
                    scheduled_at=m.scheduled_at,
                    participants=participants_by_meeting.get(mid, []),
                    summary=summary_by_meeting.get(mid),
                )
            )

        return MeetingSearchResponse(
            success=True,
            data=MeetingSearchData(meetings=items),
            message="OK",
        )
