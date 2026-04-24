# app\domains\meeting\service.py
from collections import defaultdict
from datetime import datetime, time

from fastapi import HTTPException, status
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.domains.meeting.models import (
    DiarizationMethod,
    Meeting,
    MeetingParticipant,
    MeetingStatus,
    SpeakerProfile,
)
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
    SpeakerProfileItem,
    SpeakerProfileListResponse,
    SpeakerProfileRegisterRequest,
    SpeakerProfileRegisterResponse,
)
from app.domains.user.models import User
from app.domains.intelligence.models import Decision, MeetingMinute, MinutePhoto, ReviewRequest
from app.domains.action.models import ActionItem, Report, WbsEpic, WbsTask
from app.domains.meeting.repository import MeetingHistoryRepository
from app.domains.workspace.models import MemberRole, WorkspaceMember
from app.domains.workspace.repository import get_workspace_membership


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

            # 3) meeting participants
            db.query(MeetingParticipant).filter(
                MeetingParticipant.meeting_id == meeting_id
            ).delete(synchronize_session=False)

            # 4) action items / reports
            db.query(ActionItem).filter(ActionItem.meeting_id == meeting_id).delete(
                synchronize_session=False
            )
            db.query(Report).filter(Report.meeting_id == meeting_id).delete(
                synchronize_session=False
            )

            # 5) wbs: tasks -> epics
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

            # 6) finally meeting
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


def _workspace_role_for_user(
    db: Session,
    workspace_id: int,
    user: User,
) -> str | None:
    membership = get_workspace_membership(db, workspace_id, user.id)
    if membership:
        return membership.role.value
    if user.workspace_id == workspace_id:
        return user.role
    return None


def _speaker_profile_item(
    user: User,
    role: str,
    profile: SpeakerProfile | None,
) -> SpeakerProfileItem:
    return SpeakerProfileItem(
        user_id=user.id,
        name=user.name,
        email=user.email,
        role=role,
        is_verified=bool(profile and profile.is_verified),
        diarization_method=profile.diarization_method.value if profile else None,
        updated_at=profile.updated_at if profile else None,
    )


class SpeakerProfileService:
    @staticmethod
    def list_profiles(
        db: Session,
        workspace_id: int,
        current_user_id: int,
    ) -> SpeakerProfileListResponse:
        current_user = db.query(User).filter(User.id == current_user_id).one_or_none()
        if current_user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="사용자를 찾을 수 없습니다.",
            )

        current_role = _workspace_role_for_user(db, workspace_id, current_user)
        if current_role is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="워크스페이스 멤버만 수행할 수 있습니다.",
            )

        if current_role == MemberRole.admin.value:
            member_rows = (
                db.query(User, WorkspaceMember.role)
                .join(WorkspaceMember, WorkspaceMember.user_id == User.id)
                .filter(WorkspaceMember.workspace_id == workspace_id)
                .order_by(User.id.asc())
                .all()
            )
        else:
            member_rows = [(current_user, MemberRole(current_role))]

        user_ids = [int(user.id) for user, _role in member_rows]
        profile_rows = (
            db.query(SpeakerProfile)
            .filter(
                SpeakerProfile.workspace_id == workspace_id,
                SpeakerProfile.user_id.in_(user_ids),
            )
            .all()
            if user_ids
            else []
        )
        profiles_by_user = {int(profile.user_id): profile for profile in profile_rows}

        return SpeakerProfileListResponse(
            profiles=[
                _speaker_profile_item(
                    user=user,
                    role=role.value if isinstance(role, MemberRole) else str(role),
                    profile=profiles_by_user.get(int(user.id)),
                )
                for user, role in member_rows
            ]
        )

    @staticmethod
    def register_profile(
        db: Session,
        workspace_id: int,
        current_user_id: int,
        payload: SpeakerProfileRegisterRequest,
    ) -> SpeakerProfileRegisterResponse:
        current_user = db.query(User).filter(User.id == current_user_id).one_or_none()
        if current_user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="사용자를 찾을 수 없습니다.",
            )

        current_role = _workspace_role_for_user(db, workspace_id, current_user)
        if current_role is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="워크스페이스 멤버만 수행할 수 있습니다.",
            )

        target_user_id = payload.user_id or current_user_id
        if target_user_id != current_user_id and current_role != MemberRole.admin.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="본인 화자 프로필만 등록할 수 있습니다.",
            )

        target_user = db.query(User).filter(User.id == target_user_id).one_or_none()
        if target_user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="대상 사용자를 찾을 수 없습니다.",
            )

        target_role = _workspace_role_for_user(db, workspace_id, target_user)
        if target_role is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="같은 워크스페이스 멤버만 등록할 수 있습니다.",
            )

        profile = (
            db.query(SpeakerProfile)
            .filter(
                SpeakerProfile.workspace_id == workspace_id,
                SpeakerProfile.user_id == target_user_id,
            )
            .one_or_none()
        )
        if profile is None:
            profile = SpeakerProfile(
                workspace_id=workspace_id,
                user_id=target_user_id,
                diarization_method=DiarizationMethod(payload.diarization_method),
                is_verified=True,
            )
            db.add(profile)
        else:
            profile.diarization_method = DiarizationMethod(payload.diarization_method)
            profile.is_verified = True

        db.commit()
        db.refresh(profile)

        return SpeakerProfileRegisterResponse(
            profile=_speaker_profile_item(target_user, target_role, profile),
            message="화자 프로필이 등록되었습니다.",
        )
