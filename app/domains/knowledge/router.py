# app\domains\knowledge\router.py
import uuid
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from datetime import date
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.graph.workflow import knowledge_app
from app.domains.workspace.deps import require_workspace_member
from app.domains.knowledge.schemas import (
    ChatbotHistoryMessage,
    ChatbotHistoryResponse,
    ChatbotMessageRequest,
    ChatbotMessageResponse,
    ChatbotSummaryRequest,
    ChatbotSummaryResponse,
    DocumentUploadResponse,
    PastMeetingsResponse,
    PastMeetingItem,
)
from app.domains.meeting.schemas import MeetingSearchParams, MeetingSearchResponse
from app.domains.meeting.service import MeetingSearchService
from app.domains.knowledge import repository
from app.utils.redis_utils import get_meeting_context
from app.utils.time_utils import now_kst
from app.domains.knowledge.agent_utils import summary_node
from app.domains.knowledge.service import ingest_document

router = APIRouter()


@router.get(
    "/workspaces/{workspace_id}/meetings/search",
    response_model=MeetingSearchResponse,
)
def search_workspace_meetings(
    workspace_id: int,
    db: Session = Depends(get_db),
    _member: int = Depends(require_workspace_member),
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


# 지원 확장자 -> file_type 매핑
_EXT_MAP = {
    "pdf": "pdf",
    "pptx": "pptx",
    "ppt": "ppt",
    "html": "html",
    "htm": "htm",
}

@router.post("/workspace/{workspace_id}/chatbot/message")
async def chatbot_message(workspace_id: int, req: ChatbotMessageRequest, session_id: Optional[str] = None):
    session_id = session_id or str(uuid.uuid4())
    meeting_id = req.meeting_id # 회의 중일 때만 전달
    state = {
        "meeting_id": meeting_id,
        "workspace_id": workspace_id,
        "user_question": req.message,
        "past_meeting_ids": req.past_meeting_ids,
        "function_type": "",
        "chat_response": ""
    }
    result = await knowledge_app.ainvoke(state)

    await repository.save_chat_log(meeting_id, session_id, "user", req.message, "")
    await repository.save_chat_log(
        meeting_id, session_id, "assistant", 
        result["chat_response"], result["function_type"]
    )

    return ChatbotMessageResponse(
        session_id=session_id,
        function_type=result["function_type"],
        answer=result["chat_response"],
        result={"sources": result.get("web_sources", [])},
        timestamp=now_kst()
    )

@router.get("/workspace/{workspace_id}/chatbot/history", response_model=ChatbotHistoryResponse)
async def chatbot_history(workspace_id: int, session_id: str):
    logs = await repository.get_chat_history(workspace_id, session_id)
    return ChatbotHistoryResponse(
        messages=[
            ChatbotHistoryMessage(
                role=log["role"],
                content=log["content"],
                function_type=log["function_type"],
                timestamp=log["timestamp"]
            ) for log in logs
        ]
    )

@router.post("/workspace/{workspace_id}/chatbot/summary", response_model=ChatbotSummaryResponse)
async def chatbot_summary(workspace_id: int, req: ChatbotSummaryRequest):
    state = {
        "meeting_id": req.meeting_id,
        "workspace_id": workspace_id,
        "past_meeting_ids": req.past_meeting_ids,
        "user_question": "",
        "function_type": "",
        "chat_response": ""
    }
    result = await summary_node(state)
    await repository.save_meeting_summary(workspace_id, req.meeting_id, result["summary"])

    return ChatbotSummaryResponse(
        summary=result["summary"],
        generated_at=now_kst()
    )

@router.get("/workspace/{workspace_id}/past_meetings", response_model=PastMeetingsResponse)
async def get_past_meetings(workspace_id: int):
    meetings = await repository.get_past_meetings(workspace_id)
    return PastMeetingsResponse(
        meetings=[PastMeetingItem(**m) for m in meetings],
        total=len(meetings),
    )

@router.post("/workspaces/{workspace_id}/documents", response_model=DocumentUploadResponse)
async def upload_document(
    workspace_id: int,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
):
    """
    내부 문서 업로드 -> ChromaDB 임베딩 저장.
    같은 파일 재업로드 시 기존 벡터를 덮어씀 (중복 없음).
    스캔 이미지 PDF처럼 텍스트 추출 불가 시 422 반환.
    """
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    file_type = _EXT_MAP.get(ext)
    if not file_type:
        raise HTTPException(status_code=415, detail=f"지원하지 않는 파일 형식: .{ext}")

    file_bytes = await file.read()

    try:
        result = ingest_document(
            workspace_id=workspace_id,
            filename=file.filename,
            file_type=file_type,
            file_bytes=file_bytes,
            title=title
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return DocumentUploadResponse(
        doc_id=result["doc_id"],
        chunks=result["chunks"],
        title=result["title"],
        uploaded_at=now_kst()
    )