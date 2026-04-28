from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status, UploadFile, File
from sqlalchemy.orm import Session

from app.domains.workspace.deps import require_workspace_admin, require_workspace_member
from app.core.deps import get_current_user_id
from app.db.session import get_db

from app.domains.meeting.schemas import (
    CreateMeetingRequest,
    CreateMeetingResponse,
    DeleteMeetingResponse,
    MeetingDetailResponse,
    MeetingHistoryResponse,
    MinutePhotoUploadResponse,
    MinutePhotoOut,
    SpeakerProfileListResponse,
    SpeakerProfileRegisterRequest,
    SpeakerProfileRegisterResponse,
    UpdateMeetingRequest,
)
from app.domains.meeting.service import (
    MeetingCreateService,
    MeetingDeleteService,
    MeetingDetailService,
    MeetingHistoryService,
    MeetingLifecycleService,
    MeetingUpdateService,
    MinutePhotoService,
    SpeakerProfileService,
)

router = APIRouter()


@router.post(
    "/workspaces/{workspace_id}",
    response_model=CreateMeetingResponse,
    status_code=201,
)
async def create_workspace_meeting(
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
        return await MeetingCreateService.create_meeting(
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
    _member: int = Depends(require_workspace_member),
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
    "/workspaces/{workspace_id}/speaker-profiles",
    response_model=SpeakerProfileListResponse,
)
def list_workspace_speaker_profiles(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(require_workspace_member),
):
    """
    화자 프로필 목록을 조회합니다.
    관리자는 워크스페이스 전체, 멤버는 본인 프로필만 조회합니다.
    """
    return SpeakerProfileService.list_profiles(db, workspace_id, current_user_id)


@router.post(
    "/workspaces/{workspace_id}/speaker-profiles",
    response_model=SpeakerProfileRegisterResponse,
    status_code=status.HTTP_200_OK,
)
def register_workspace_speaker_profile(
    workspace_id: int,
    payload: SpeakerProfileRegisterRequest,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    """
    화자 프로필을 등록합니다.
    관리자는 모든 멤버, 멤버는 본인만 등록할 수 있습니다.
    """
    return SpeakerProfileService.register_profile(db, workspace_id, current_user_id, payload)


@router.get(
    "/workspaces/{workspace_id}/{meeting_id}",
    response_model=MeetingDetailResponse,
)
def get_workspace_meeting(
    workspace_id: int,
    meeting_id: int,
    db: Session = Depends(get_db),
    _member: int = Depends(require_workspace_member),
):
    """워크스페이스 내 단일 회의 조회 (참석자 목록 포함)."""
    return MeetingDetailService.get_meeting(db, workspace_id, meeting_id)


@router.delete(
    "/workspaces/{workspace_id}/{meeting_id}",
    response_model=DeleteMeetingResponse,
)
async def delete_workspace_meeting(
    workspace_id: int,
    meeting_id: int,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(require_workspace_admin),
):
    """회의 및 연관 데이터 삭제."""
    try:
        return await MeetingDeleteService.delete_meeting(
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
async def patch_workspace_meeting(
    workspace_id: int,
    meeting_id: int,
    body: UpdateMeetingRequest,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(require_workspace_admin),
):
    """회의 정보 수정."""
    try:
        return await MeetingUpdateService.update_meeting(
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


@router.post("/workspaces/{workspace_id}/{meeting_id}/start")
def start_workspace_meeting(
    workspace_id: int,
    meeting_id: int,
    db: Session = Depends(get_db),
    _member: int = Depends(require_workspace_member),
) -> dict:
    """회의를 진행 중으로 전환합니다."""
    MeetingLifecycleService.start_meeting(db, workspace_id, meeting_id)
    return {"status": "ok"}


@router.post("/workspaces/{workspace_id}/{meeting_id}/end")
def end_workspace_meeting(
    workspace_id: int,
    meeting_id: int,
    db: Session = Depends(get_db),
    _member: int = Depends(require_workspace_member),
) -> dict:
    """회의를 완료로 전환합니다."""
    MeetingLifecycleService.end_meeting(db, workspace_id, meeting_id)
    return {"status": "ok"}


@router.post(
    "/workspaces/{workspace_id}/{meeting_id}/minute-photos",
    response_model=MinutePhotoUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_minute_photo(
    workspace_id: int,
    meeting_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user_id: int = Depends(require_workspace_member),
) -> MinutePhotoUploadResponse:
    """
    진행 중 회의에서 캡처한 이미지를 저장하고 minute_photos에 기록합니다.

    - 파일 저장: storage/meetings/{meeting_id}/minute_photos/{filename}.png
    - DB 저장: minute_photos(minute_id, photo_url, taken_at, taken_by)
    """
    filename = (file.filename or "").lower()
    if filename.endswith(".png"):
        ext = "png"
    elif filename.endswith(".jpg") or filename.endswith(".jpeg"):
        ext = "jpg"
    elif filename.endswith(".webp"):
        ext = "webp"
    else:
        # 캔버스 캡처 기본값은 png, 확장자 없으면 png로 처리
        ext = "png"

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="빈 파일입니다.")

    try:
        photo = MinutePhotoService.save_captured_photo(
            db=db,
            workspace_id=workspace_id,
            meeting_id=meeting_id,
            taken_by_user_id=current_user_id,
            image_bytes=image_bytes,
            ext=ext,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"이미지 저장 중 오류가 발생했습니다: {e}",
        )

    return MinutePhotoUploadResponse(
        success=True,
        photo=MinutePhotoOut(
            id=int(photo.id),
            minute_id=int(photo.minute_id),
            photo_url=str(photo.photo_url),
            taken_at=photo.taken_at,
            taken_by=int(photo.taken_by),
        ),
        message="OK",
    )
