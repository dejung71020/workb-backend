# app\domains\meeting\service.py
from collections import defaultdict
from datetime import datetime, time

from fastapi import HTTPException, status
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.domains.meeting.models import Meeting, MeetingParticipant, MeetingStatus
from app.domains.meeting.schemas import (
    CreateMeetingRequest,
    CreateMeetingResponse,
    CreateMeetingResponseData,
    DeleteMeetingResponse,
    MeetingDetailOut,
    MeetingDetailParticipantOut,
    MeetingDetailResponse,
    UpdateMeetingRequest,
    MeetingSearchData,
    MeetingSearchItemOut,
    MeetingSearchParams,
    MeetingSearchParticipantOut,
    MeetingSearchResponse,
    MeetingHistoryItemOut,
    MeetingHistoryResponse,
)
from app.domains.user.models import User
from app.domains.intelligence.models import Decision, MeetingMinute, MinutePhoto, ReviewRequest
from app.domains.action.models import ActionItem, Report, WbsEpic, WbsTask
from app.domains.meeting.models import Agenda, AgendaItem
from app.domains.meeting.repository import MeetingHistoryRepository


class MeetingCreateService:
    """회의 생성(트랜잭션: meetings + meeting_participants)."""

    @staticmethod
    def create_meeting(
        db: Session,
        workspace_id: int,
        created_by: int,
        payload: CreateMeetingRequest,
    ) -> CreateMeetingResponse:
        now = (
            datetime.now(payload.scheduled_at.tzinfo)
            if getattr(payload.scheduled_at, "tzinfo", None) is not None
            else datetime.now()
        )
        if payload.scheduled_at < now:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="현재보다 이전 시간으로 회의를 예약할 수 없습니다.",
            )

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


class MeetingDeleteService:
    """회의 삭제(연관 데이터 포함)."""

    @staticmethod
    def delete_meeting(
        db: Session,
        workspace_id: int,
        meeting_id: int,
        current_user_id: int,
    ) -> DeleteMeetingResponse:
        # NOTE: 권한 체크는 추후 워크스페이스 멤버십/role로 확장.
        meeting = (
            db.query(Meeting)
            .filter(Meeting.id == meeting_id, Meeting.workspace_id == workspace_id)
            .one_or_none()
        )
        if meeting is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="회의를 찾을 수 없습니다.",
            )

        try:
            # 1) 회의록(분) + 하위 리소스
            minute = (
                db.query(MeetingMinute)
                .filter(MeetingMinute.meeting_id == meeting_id)
                .one_or_none()
            )
            if minute is not None:
                db.query(MinutePhoto).filter(MinutePhoto.minute_id == minute.id).delete(
                    synchronize_session=False
                )
                db.query(ReviewRequest).filter(
                    ReviewRequest.minute_id == minute.id
                ).delete(synchronize_session=False)
                db.delete(minute)

            # 2) decisions
            db.query(Decision).filter(Decision.meeting_id == meeting_id).delete(
                synchronize_session=False
            )

            # 3) agendas + items
            agenda_ids = [
                int(a.id)
                for a in db.query(Agenda.id).filter(Agenda.meeting_id == meeting_id).all()
            ]
            if agenda_ids:
                db.query(AgendaItem).filter(AgendaItem.agenda_id.in_(agenda_ids)).delete(
                    synchronize_session=False
                )
                db.query(Agenda).filter(Agenda.id.in_(agenda_ids)).delete(
                    synchronize_session=False
                )

            # 4) meeting participants
            db.query(MeetingParticipant).filter(
                MeetingParticipant.meeting_id == meeting_id
            ).delete(synchronize_session=False)

            # 5) action items / reports
            db.query(ActionItem).filter(ActionItem.meeting_id == meeting_id).delete(
                synchronize_session=False
            )
            db.query(Report).filter(Report.meeting_id == meeting_id).delete(
                synchronize_session=False
            )

            # 6) wbs: tasks -> epics
            epic_ids = [
                int(e.id)
                for e in db.query(WbsEpic.id).filter(WbsEpic.meeting_id == meeting_id).all()
            ]
            if epic_ids:
                db.query(WbsTask).filter(WbsTask.epic_id.in_(epic_ids)).delete(
                    synchronize_session=False
                )
                db.query(WbsEpic).filter(WbsEpic.id.in_(epic_ids)).delete(
                    synchronize_session=False
                )

            # 7) finally meeting
            db.delete(meeting)

            db.commit()
        except HTTPException:
            db.rollback()
            raise
        except Exception:
            db.rollback()
            raise

        return DeleteMeetingResponse(success=True, message="OK")


class MeetingUpdateService:
    """회의 수정(회의 + 참석자)."""

    @staticmethod
    def update_meeting(
        db: Session,
        workspace_id: int,
        meeting_id: int,
        current_user_id: int,
        payload: UpdateMeetingRequest,
    ) -> CreateMeetingResponse:
        meeting = (
            db.query(Meeting)
            .filter(Meeting.id == meeting_id, Meeting.workspace_id == workspace_id)
            .one_or_none()
        )
        if meeting is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="회의를 찾을 수 없습니다.",
            )

        now = (
            datetime.now(payload.scheduled_at.tzinfo)
            if getattr(payload.scheduled_at, "tzinfo", None) is not None
            else datetime.now()
        )
        if payload.scheduled_at < now:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="현재보다 이전 시간으로 회의를 예약할 수 없습니다.",
            )

        try:
            meeting.title = payload.title
            meeting.meeting_type = payload.meeting_type
            meeting.scheduled_at = payload.scheduled_at

            # 참석자 갱신: 기존 제거 후 재삽입 (생성자는 host 유지)
            db.query(MeetingParticipant).filter(
                MeetingParticipant.meeting_id == meeting_id
            ).delete(synchronize_session=False)

            ordered_user_ids: list[int] = [meeting.created_by]
            for uid in payload.participant_ids:
                if uid != meeting.created_by and uid not in ordered_user_ids:
                    ordered_user_ids.append(uid)

            for uid in ordered_user_ids:
                db.add(
                    MeetingParticipant(
                        meeting_id=meeting.id,
                        user_id=uid,
                        is_host=(uid == meeting.created_by),
                    )
                )

            db.commit()
            db.refresh(meeting)
        except HTTPException:
            db.rollback()
            raise
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


class MeetingHistoryService:
    """회의 히스토리 검색 (제목 + 회의록 content/summary, outerjoin)."""

    @staticmethod
    def get_history(
        db: Session,
        workspace_id: int,
        keyword: str | None,
        page: int,
        size: int,
    ) -> MeetingHistoryResponse:
        page = max(int(page), 1)
        size = max(min(int(size), 100), 1)

        total, rows = MeetingHistoryRepository.search_history(
            db=db,
            workspace_id=workspace_id,
            keyword=keyword,
            page=page,
            size=size,
        )

        items: list[MeetingHistoryItemOut] = []
        for meeting, minute in rows:
            items.append(
                MeetingHistoryItemOut(
                    id=int(meeting.id),
                    title=meeting.title,
                    status=(
                        meeting.status.value
                        if isinstance(meeting.status, MeetingStatus)
                        else str(meeting.status)
                    ),
                    scheduled_at=meeting.scheduled_at,
                    started_at=meeting.started_at,
                    ended_at=meeting.ended_at,
                    summary=(minute.summary if minute else None),
                )
            )

        return MeetingHistoryResponse(total=total, page=page, meetings=items)


class MeetingDetailService:
    """워크스페이스 소속 회의 단건 조회 (상세·참석자)."""

    @staticmethod
    def get_meeting(db: Session, workspace_id: int, meeting_id: int) -> MeetingDetailResponse:
        meeting = (
            db.query(Meeting)
            .filter(Meeting.id == meeting_id, Meeting.workspace_id == workspace_id)
            .one_or_none()
        )
        if meeting is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="회의를 찾을 수 없습니다.",
            )

        rows = (
            db.query(MeetingParticipant, User.name)
            .join(User, User.id == MeetingParticipant.user_id)
            .filter(MeetingParticipant.meeting_id == meeting_id)
            .order_by(MeetingParticipant.id)
            .all()
        )
        participants = [
            MeetingDetailParticipantOut(user_id=int(mp.user_id), name=str(name))
            for mp, name in rows
        ]

        status_str = (
            meeting.status.value
            if isinstance(meeting.status, MeetingStatus)
            else str(meeting.status)
        )

        return MeetingDetailResponse(
            success=True,
            data=MeetingDetailOut(
                id=int(meeting.id),
                title=str(meeting.title),
                status=status_str,
                meeting_type=meeting.meeting_type,
                scheduled_at=meeting.scheduled_at,
                started_at=meeting.started_at,
                ended_at=meeting.ended_at,
                participants=participants,
            ),
            message="OK",
        )
