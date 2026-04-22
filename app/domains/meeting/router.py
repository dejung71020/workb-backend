from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user_id, require_workspace_admin
from app.db.session import get_db
from app.domains.meeting.agenda_service import AgendaService, agenda_item_to_out
from app.domains.meeting.schemas import (
    AgendaBulkCreateRequest,
    AgendaBulkCreateResponse,
    AgendaItemCreatedOut,
    AgendaItemDeleteResponse,
    AgendaItemPatch,
    AgendaItemPatchResponse,
    CreateMeetingRequest,
    CreateMeetingResponse,
    DeleteMeetingResponse,
    MeetingDetailResponse,
    MeetingHistoryResponse,
    UpdateMeetingRequest,
)
from app.domains.meeting.service import (
    MeetingCreateService,
    MeetingDeleteService,
    MeetingDetailService,
    MeetingHistoryService,
    MeetingUpdateService,
)

router = APIRouter()


@router.post(
    "/workspaces/{workspace_id}",
    response_model=CreateMeetingResponse,
    status_code=201,
)
def create_workspace_meeting(
    workspace_id: int,
    body: CreateMeetingRequest,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(require_workspace_admin),
):
    """
    워크스페이스에 회의를 예약·생성합니다.

    - meetings + meeting_participants 를 단일 트랜잭션으로 저장
    - 생성자는 참석자에 포함되며 is_host=1
    """
    try:
        return MeetingCreateService.create_meeting(
            db, workspace_id, current_user_id, body
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"회의 생성 중 오류가 발생했습니다: {e}",
        )


@router.get(
    "/workspaces/{workspace_id}/history",
    response_model=MeetingHistoryResponse,
)
def get_workspace_meetings_history(
    workspace_id: int,
    db: Session = Depends(get_db),
    keyword: Optional[str] = Query(None, description="검색어(제목/회의록 포함)"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    """
    회의 히스토리 검색:

    - meetings.title OR meeting_minutes.content/summary (outer join)
    - scheduled_at 최신순
    - page/size 페이징
    """
    return MeetingHistoryService.get_history(db, workspace_id, keyword, page, size)


@router.get(
    "/workspaces/{workspace_id}/{meeting_id}",
    response_model=MeetingDetailResponse,
)
def get_workspace_meeting(
    workspace_id: int,
    meeting_id: int,
    db: Session = Depends(get_db),
):
    """워크스페이스 내 단일 회의 조회 (참석자 목록 포함)."""
    return MeetingDetailService.get_meeting(db, workspace_id, meeting_id)


@router.delete(
    "/workspaces/{workspace_id}/{meeting_id}",
    response_model=DeleteMeetingResponse,
)
def delete_workspace_meeting(
    workspace_id: int,
    meeting_id: int,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(require_workspace_admin),
):
    """회의 및 연관 데이터 삭제."""
    try:
        return MeetingDeleteService.delete_meeting(
            db=db,
            workspace_id=workspace_id,
            meeting_id=meeting_id,
            current_user_id=current_user_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"회의 삭제 중 오류가 발생했습니다: {e}",
        )


@router.patch(
    "/workspaces/{workspace_id}/{meeting_id}",
    response_model=CreateMeetingResponse,
)
def patch_workspace_meeting(
    workspace_id: int,
    meeting_id: int,
    body: UpdateMeetingRequest,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(require_workspace_admin),
):
    """회의 정보 수정."""
    try:
        return MeetingUpdateService.update_meeting(
            db=db,
            workspace_id=workspace_id,
            meeting_id=meeting_id,
            current_user_id=current_user_id,
            payload=body,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"회의 수정 중 오류가 발생했습니다: {e}",
        )


@router.post(
    "/{meeting_id}/agenda",
    response_model=AgendaBulkCreateResponse,
    status_code=201,
)
def create_meeting_agenda_items(
    meeting_id: int,
    body: AgendaBulkCreateRequest,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    """
    회의에 아젠다 항목을 일괄 등록합니다.

    - `meetings` 존재 검증
    - `agendas` 부모가 없으면 생성 (`created_by` = 현재 사용자)
    - `agenda_items` 벌크 삽입 (단일 트랜잭션)
    """
    try:
        agenda_id, rows = AgendaService.bulk_create_items(
            db, meeting_id, current_user_id, body
        )
        return AgendaBulkCreateResponse(
            agenda_id=agenda_id,
            items=[
                AgendaItemCreatedOut(
                    id=int(r.id), title=r.title, order_index=int(r.order_index)
                )
                for r in rows
            ],
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"아젠다 등록 중 오류가 발생했습니다: {e}",
        )


@router.patch(
    "/{meeting_id}/agenda/items/{item_id}",
    response_model=AgendaItemPatchResponse,
)
def patch_meeting_agenda_item(
    meeting_id: int,
    item_id: int,
    body: AgendaItemPatch,
    db: Session = Depends(get_db),
):
    """아젠다 항목 부분 수정 (요청에 포함된 필드만 반영)."""
    try:
        row = AgendaService.patch_item(db, meeting_id, item_id, body)
        return AgendaItemPatchResponse(data=agenda_item_to_out(row))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"아젠다 수정 중 오류가 발생했습니다: {e}",
        )


@router.delete(
    "/{meeting_id}/agenda/items/{item_id}",
    response_model=AgendaItemDeleteResponse,
)
def delete_meeting_agenda_item(
    meeting_id: int,
    item_id: int,
    db: Session = Depends(get_db),
):
    """아젠다 항목 삭제 (hard delete)."""
    try:
        AgendaService.delete_item(db, meeting_id, item_id)
        return AgendaItemDeleteResponse()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"아젠다 삭제 중 오류가 발생했습니다: {e}",
        )
