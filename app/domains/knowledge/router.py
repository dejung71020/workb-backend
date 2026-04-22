# app\domains\knowledge\router.py
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from datetime import datetime
from typing import Optional

from app.core.graph.workflow import knowledge_app
from app.domains.knowledge.schemas import (
    ChatbotMessageRequest, ChatbotMessageResponse, ChatbotSummaryRequest,
    ChatbotSummaryResponse, ChatbotHistoryMessage, ChatbotHistoryResponse
)
from app.domains.knowledge import repository
from app.utils.redis_utils import get_meeting_context
from app.domains.knowledge.agent_utils import summary_node
from app.domains.knowledge.service import ingest_document
from app.domains.knowledge.schemas import DocumentUploadResponse

router = APIRouter()

# 지원 확장자 -> file_type 매핑
_EXT_MAP = {
    "pdf": "pdf",
    "pptx": "pptx",
    "ppt": "ppt",
    "html": "html",
    "htm": "htm",
}

@router.post("/workspace/{workspace_id}/chatbot/message")
async def chatbot_message(workspace_id: int, req: ChatbotMessageRequest):
    meeting_id = req.meeting_id
    state = {
        "meeting_id": meeting_id,
        "workspace_id": workspace_id,
        "user_question": req.message,
        "function_type": "",
        "chat_response": ""
    }
    result = await knowledge_app.ainvoke(state)

    await repository.save_chat_log(meeting_id, req.session_id, "user", req.message, "")
    await repository.save_chat_log(
        meeting_id, req.session_id, "assistant", 
        result["chat_response"], result["function_type"]
    )

    return ChatbotMessageResponse(
        session_id=req.session_id,
        function_type=result["function_type"],
        answer=result["chat_response"],
        result={},
        timestamp=datetime.now()
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
        "user_question": "",
        "function_type": "",
        "chat_response": ""
    }
    result = await summary_node(state)
    await repository.save_meeting_summary(workspace_id, req.meeting_id, result["summary"])

    return ChatbotSummaryResponse(
        summary=result["summary"],
        generated_at=datetime.now()
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
        uploaded_at=datetime.now()
    )