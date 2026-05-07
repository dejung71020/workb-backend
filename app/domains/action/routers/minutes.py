"""
회의록 관련 엔드포인트.
파이프라인 책임은 app.domains.action.minutes_pipeline 모듈이 가진다.
"""
import asyncio
import base64
import logging
from pathlib import Path
from typing import Optional

import markdown
from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.orm import Session

from app.domains.action import repository as action_repo
from app.domains.action.mongo_repository import get_or_build_meeting_summary
from app.domains.action.schemas import (
    ExportResponse,
    MinutesPatchRequest,
    MinutesPdfPreviewRequest,
    MinutesPdfPreviewResponse,
    MinutesResponse,
)
from app.domains.action.services.minutes_builder import build_and_save_minutes, ensure_minutes
from app.domains.action import minutes_repository as minutes_repo
from app.domains.action.minutes_pipeline import (
    data_mapper,
    pdf_renderer,
)
from app.domains.user.dependencies import require_workspace_admin, require_workspace_member
from app.infra.database.session import get_db

router = APIRouter()
logger = logging.getLogger(__name__)

_PDF_OUTPUT_STORE = Path("storage/minutes_generated")


# --------------------------------------------------------------------------- #
# 헬퍼                                                                         #
# --------------------------------------------------------------------------- #

def _enrich_fields_from_db(
    fields: data_mapper.MinuteFields,
    db: Session,
    meeting_id: int,
) -> data_mapper.MinuteFields:
    meeting_row = action_repo.get_meeting(db, meeting_id)
    if not meeting_row:
        return fields
    if not fields.datetime:
        dt_obj = meeting_row.started_at or meeting_row.scheduled_at
        if dt_obj:
            fields.datetime = dt_obj.strftime("%Y년 %m월 %d일 %H:%M")
    if not fields.dept or not fields.author:
        user = action_repo.get_user(db, meeting_row.created_by)
        if user:
            if not fields.dept:
                fields.dept = minutes_repo.get_dept_name(db, user, int(meeting_row.workspace_id))
            if not fields.author:
                fields.author = user.name
    return fields


# --------------------------------------------------------------------------- #
# 회의록 생성 (마크다운 텍스트)                                                #
# --------------------------------------------------------------------------- #

@router.post("/minutes/generate", response_model=ExportResponse)
async def generate_minutes(
    meeting_id: int,
    background_tasks: BackgroundTasks,
    workspace_id: int = Query(..., description="워크스페이스 ID"),
    db: Session = Depends(get_db),
    _admin=Depends(require_workspace_admin),
):
    """회의록 마크다운 텍스트를 비동기로 생성합니다."""
    background_tasks.add_task(
        build_and_save_minutes,
        db=db,
        meeting_id=meeting_id,
    )
    return ExportResponse(status="processing")


# --------------------------------------------------------------------------- #
# 회의록 조회 / 수정                                                           #
# --------------------------------------------------------------------------- #

@router.get("/minutes/ensure", response_model=MinutesResponse)
async def ensure_minutes_endpoint(
    meeting_id: int,
    workspace_id: int = Query(..., description="워크스페이스 ID"),
    db: Session = Depends(get_db),
    _member=Depends(require_workspace_member),
):
    """기존 회의록을 반환하거나, 없으면 기본 양식으로 생성 후 반환합니다.

    저장소: meeting_minutes 테이블 (MeetingMinute 모델), ensure_minutes() 경유.
    """
    minute = ensure_minutes(db, meeting_id)
    return MinutesResponse(
        meeting_id=meeting_id,
        content=minute.content,
        updated_at=minute.updated_at,
    )


@router.get("/minutes", response_model=MinutesResponse)
async def get_minutes(
    meeting_id: int,
    workspace_id: int = Query(..., description="워크스페이스 ID"),
    db: Session = Depends(get_db),
    _member=Depends(require_workspace_member),
):
    minute = action_repo.get_meeting_minute(db, meeting_id)
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
    workspace_id: int = Query(..., description="워크스페이스 ID"),
    db: Session = Depends(get_db),
    _member=Depends(require_workspace_member),
):
    minute = action_repo.get_meeting_minute(db, meeting_id)
    if not minute or not minute.content:
        raise HTTPException(status_code=404, detail="회의록이 없습니다.")
    html_body = markdown.markdown(minute.content, extensions=["tables", "fenced_code"])
    return f"<html><body style='max-width:800px;margin:auto;padding:2rem'>{html_body}</body></html>"


@router.patch("/minutes", response_model=MinutesResponse)
async def patch_minutes(
    meeting_id: int,
    body: MinutesPatchRequest,
    workspace_id: int = Query(..., description="워크스페이스 ID"),
    db: Session = Depends(get_db),
    _admin=Depends(require_workspace_admin),
):
    minute = action_repo.get_meeting_minute(db, meeting_id)
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


# --------------------------------------------------------------------------- #
# PDF 미리보기                                                                 #
# --------------------------------------------------------------------------- #

@router.post("/minutes/pdf-preview", response_model=MinutesPdfPreviewResponse)
async def preview_minutes_pdf(
    meeting_id: int,
    workspace_id: int = Query(..., description="워크스페이스 ID"),
    body: Optional[MinutesPdfPreviewRequest] = Body(default=None),
    db: Session = Depends(get_db),
    _member=Depends(require_workspace_member),
):
    """회의록 PDF를 생성하고 첫 페이지 미리보기(base64 PNG)를 반환합니다."""
    # ── 회의 데이터 수집 ─────────────────────────────────────────────
    if body and body.field_values:
        fields = data_mapper.from_explicit(body.field_values)
        fields = _enrich_fields_from_db(fields, db, meeting_id)
    else:
        summary = await get_or_build_meeting_summary(meeting_id, workspace_id)
        if not summary:
            raise HTTPException(
                status_code=404,
                detail="knowledge 요약(meeting_summaries)이 없습니다. 먼저 knowledge 요약을 생성해주세요.",
            )
        meeting_row = action_repo.get_meeting(db, meeting_id)
        creator_name = ""
        dept_name = ""
        if meeting_row:
            user = action_repo.get_user(db, meeting_row.created_by)
            if user:
                creator_name = user.name
                dept_name = minutes_repo.get_dept_name(db, user, int(meeting_row.workspace_id))
        fields = data_mapper.from_mongo_summary(
            summary,
            meeting_row=meeting_row,
            creator_name=creator_name,
            dept_name=dept_name,
        )

    photos = action_repo.get_meeting_minute_photos(db, meeting_id)
    fields.photo_urls = [str(p.photo_url) for p in photos if p.photo_url]

    # ── PDF 생성 ─────────────────────────────────────────────────────
    _PDF_OUTPUT_STORE.mkdir(parents=True, exist_ok=True)
    output_pdf = _PDF_OUTPUT_STORE / f"{meeting_id}.pdf"

    loop = asyncio.get_event_loop()
    pdf_bytes: bytes

    try:
        logger.info("PDF 생성 시작 (meeting_id=%d, render_mode=html)", meeting_id)
        pdf_bytes = await loop.run_in_executor(
            None, lambda: pdf_renderer.render(fields)
        )
    except Exception as exc:
        logger.error("PDF 생성 오류 (meeting_id=%d): %s", meeting_id, exc)
        raise HTTPException(status_code=500, detail=f"PDF 생성에 실패했습니다: {exc}") from exc

    logger.info(
        "PDF 생성 완료 (meeting_id=%d, render_mode=html)",
        meeting_id,
    )

    try:
        output_pdf.write_bytes(pdf_bytes)
        preview_pngs = await loop.run_in_executor(
            None,
            lambda: pdf_renderer.preview_from_pdf_bytes(pdf_bytes, [0], dpi=150),
        )
    except Exception as exc:
        logger.error("PDF 저장/미리보기 오류 (meeting_id=%d): %s", meeting_id, exc)
        raise HTTPException(status_code=500, detail=f"PDF 생성에 실패했습니다: {exc}") from exc

    pdf_width, pdf_height = pdf_renderer.get_pdf_page_size(pdf_bytes)
    preview_b64 = base64.b64encode(preview_pngs[0]).decode()

    return MinutesPdfPreviewResponse(
        preview_b64=preview_b64,
        field_coords={},
        field_values=fields.to_field_values(),
        pdf_width=pdf_width,
        pdf_height=pdf_height,
    )


# --------------------------------------------------------------------------- #
# PDF 다운로드                                                                 #
# --------------------------------------------------------------------------- #

@router.get("/minutes/pdf")
async def download_minutes_pdf(
    meeting_id: int,
    workspace_id: int = Query(..., description="워크스페이스 ID"),
    _member=Depends(require_workspace_member),
):
    """생성된 회의록 PDF를 다운로드합니다."""
    pdf_path = _PDF_OUTPUT_STORE / f"{meeting_id}.pdf"
    if not pdf_path.exists():
        raise HTTPException(
            status_code=404,
            detail="생성된 PDF가 없습니다. 먼저 미리보기를 생성해주세요.",
        )
    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"minutes_{meeting_id}.pdf",
    )
