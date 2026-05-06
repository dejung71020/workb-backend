from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status, UploadFile, File
from sqlalchemy.orm import Session

from app.domains.workspace.deps import require_workspace_admin, require_workspace_member
from app.core.deps import get_current_user_id
from app.core.config import settings
from app.db.session import get_db
from app.core.graph.meeting_pipeline import (
    run_meeting_completion_pipeline,
    run_meeting_start_pipeline,
)

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
from app.domains.knowledge.service import process_meeting_end

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
    return SpeakerProfileService.register_profile(
        db, workspace_id, current_user_id, payload
    )


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
async def start_workspace_meeting(
    workspace_id: int,
    meeting_id: int,
    _member: int = Depends(require_workspace_member),
) -> dict:
    """회의를 진행 중으로 전환하고 LangGraph 시작 파이프라인을 실행합니다."""
    state = await run_meeting_start_pipeline(workspace_id, meeting_id)
    return {
        "status": "ok",
        "pipeline": {
            "realtime_utterance_count": state.get("realtime_utterance_count", 0),
            "errors": state.get("errors", []),
        },
    }


@router.post("/workspaces/{workspace_id}/{meeting_id}/end")
def end_workspace_meeting(
    workspace_id: int,
    meeting_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _member: int = Depends(require_workspace_member),
) -> dict:
    """회의를 완료로 전환하고 후처리 LangGraph 파이프라인을 백그라운드로 실행합니다."""
    MeetingLifecycleService.end_meeting(db, workspace_id, meeting_id)
    background_tasks.add_task(process_meeting_end, meeting_id, workspace_id)
    return {"status": "ok"}


_WAV_CONTENT_TYPES = {"audio/wav", "audio/wave", "audio/x-wav"}
_WAV_MAX_BYTES = 300 * 1024 * 1024  # 300 MB


@router.post("/workspaces/{workspace_id}/{meeting_id}/simulate-wav")
async def simulate_wav_upload(
    workspace_id: int,
    meeting_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _admin: int = Depends(require_workspace_admin),
) -> dict:
    """
    [개발·QA 전용] WAV 파일을 업로드해 실제 회의와 동일한 경로로 처리합니다.

    WAV_SIM_ENABLED=true + 워크스페이스 관리자만 사용 가능.
    처리 완료 후 meeting.status = done, MongoDB utterances 저장.
    """
    if not settings.WAV_SIM_ENABLED:
        raise HTTPException(
            status_code=403,
            detail="WAV_SIM_ENABLED가 비활성화 상태입니다. (.env에서 WAV_SIM_ENABLED=true 로 설정)",
        )

    if not settings.OPENAI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="OPENAI_API_KEY가 설정되지 않아 Whisper를 사용할 수 없습니다.",
        )

    filename = file.filename or ""
    if file.content_type not in _WAV_CONTENT_TYPES and not filename.lower().endswith(
        ".wav"
    ):
        raise HTTPException(
            status_code=400, detail="WAV(.wav) 파일만 업로드 가능합니다."
        )

    wav_bytes = await file.read()
    if len(wav_bytes) > _WAV_MAX_BYTES:
        raise HTTPException(status_code=400, detail="파일 크기가 300MB를 초과합니다.")
    if len(wav_bytes) == 0:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")

    from app.domains.meeting.wav_simulation import run_wav_simulation

    count = await run_wav_simulation(
        db, workspace_id, meeting_id, wav_bytes, settings.OPENAI_API_KEY
    )

    return {"status": "ok", "meeting_id": meeting_id, "utterance_count": count}


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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="빈 파일입니다."
        )

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
