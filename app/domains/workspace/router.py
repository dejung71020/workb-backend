# app\domains\workspace\router.py
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.infra.database.session import get_db
from app.domains.workspace.schemas import DashboardResponse
from app.domains.workspace.service import DashboardService
from app.domains.meeting.schemas import (
    CreateMeetingRequest,
    CreateMeetingResponse,
    MeetingSearchParams,
    MeetingSearchResponse,
)
from app.domains.meeting.service import MeetingCreateService, MeetingSearchService


def get_current_user_id() -> int:
    """임시: 로그인 완성 전까지 고정 사용자 ID 반환."""
    return 1


router = APIRouter()


@router.get("/{workspace_id}/dashboard", response_model=DashboardResponse)
def get_workspace_dashboard(workspace_id: int, db: Session = Depends(get_db)):
    """
    워크스페이스 홈 대시보드 데이터를 조회합니다.

    - 상태별 회의 목록 (in_progress / scheduled / done)
    - 이번 주 완료 회의 요약 (건수, 총 소요시간)
    - 미결 액션 아이템 (pending)
    - 다음 회의 제안 (추후 AI 연동 예정)
    """
    return DashboardService.get_dashboard(db, workspace_id)


@router.get(
    "/{workspace_id}/meetings/search",
    response_model=MeetingSearchResponse,
)
def search_workspace_meetings(
    workspace_id: int,
    db: Session = Depends(get_db),
    keyword: Optional[str] = Query(None, description="회의 제목 부분 일치 검색"),
    from_date: Optional[date] = Query(None, description="scheduled_at 기준 시작일(포함)"),
    to_date: Optional[date] = Query(None, description="scheduled_at 기준 종료일(포함)"),
    participant_id: Optional[int] = Query(
        None, description="해당 user_id가 참석자로 포함된 회의만"
    ),
):
    """
    키워드·날짜·참석자 조건으로 워크스페이스 내 과거/예정 회의를 검색합니다.
    """
    params = MeetingSearchParams(
        keyword=keyword,
        from_date=from_date,
        to_date=to_date,
        participant_id=participant_id,
    )
    return MeetingSearchService.search(db, workspace_id, params)


@router.post(
    "/{workspace_id}/meetings",
    response_model=CreateMeetingResponse,
    status_code=201,
)
def create_workspace_meeting(
    workspace_id: int,
    body: CreateMeetingRequest,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    """
    워크스페이스에 회의를 예약·생성합니다.

    - meetings + meeting_participants 를 단일 트랜잭션으로 저장
    - 생성자는 참석자에 포함되며 is_host=1
    """
    return MeetingCreateService.create_meeting(
        db, workspace_id, current_user_id, body
    )
