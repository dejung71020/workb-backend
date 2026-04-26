# app/domains/action/routers/minutes.py
import markdown
from fastapi import APIRouter, Depends, BackgroundTasks, Query, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.infra.database.session import get_db
from app.domains.action import repository
from app.domains.action.schemas import MinutesResponse, MinutesPatchRequest, ExportResponse
from app.domains.action.services.minutes_builder import build_and_save_minutes
from app.domains.user.dependencies import require_workspace_admin, require_workspace_member

router = APIRouter()

@router.post("/minutes/generate", response_model=ExportResponse)
async def generate_minutes(
    meeting_id: int,
    background_tasks: BackgroundTasks,
    workspace_id: int = Query(..., description="워크스페이스 ID"),
    db: Session = Depends(get_db),
    _admin = Depends(require_workspace_admin),
):
    background_tasks.add_task(
        build_and_save_minutes,
        db=db,
        meeting_id=meeting_id
    )
    return ExportResponse(status="processing")

@router.get("/minutes", response_model=MinutesResponse)
async def get_minutes(
    meeting_id: int,
    db: Session = Depends(get_db),
    _member = Depends(require_workspace_member),
):
    minute = repository.get_meeting_minute(db, meeting_id)
    if not minute:
        raise HTTPException(status_code=404, detail="회의록이 없습니다.")
    return MinutesResponse(
        meeting_id=meeting_id,
        content=minute.content,
        updated_at=minute.updated_at,
    )

@router.get("/minutes/view", response_class=HTMLResponse)
async def view_minutes(
    meeting_id: int,
    db: Session = Depends(get_db),
    _member = Depends(require_workspace_member),
):
    minute = repository.get_meeting_minute(db, meeting_id)
    if not minute or not minute.content:
        raise HTTPException(status_code=404, detail="회의록이 없습니다.")
    html_body = markdown.markdown(minute.content, extensions=['tables', "fenced_code"])
    return f"<html><body style='max-width:800px;margin:auto;padding:2rem'>{html_body}</body></html>"

@router.patch("/minutes", response_model=MinutesResponse)
async def patch_minutes(
    meeting_id: int,
    body: MinutesPatchRequest,
    db: Session = Depends(get_db),
    _admin = Depends(require_workspace_admin),
):
    minute = repository.get_meeting_minute(db, meeting_id)
    if not minute:
        raise HTTPException(status_code=404, detail="회의록이 없습니다.")
    minute.content = body.content
    db.commit()
    db.refresh(minute)
    return MinutesResponse(
        meeting_id=minute.meeting_id,
        content=minute.content,
        updated_at=minute.updated_at,
    )
