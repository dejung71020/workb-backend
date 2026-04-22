# app\domains\knowledge\router.py
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.graph.workflow import knowledge_app
from app.domains.knowledge.schemas import (
    ChatbotMessageRequest, ChatbotMessageResponse,
    ChatbotSummaryResponse, ChatbotHistoryMessage, ChatbotHistoryResponse,
)
from app.domains.meeting.schemas import MeetingSearchParams, MeetingSearchResponse
from app.domains.meeting.service import MeetingSearchService
from app.domains.knowledge import repository
from app.utils.redis_utils import get_meeting_context
from app.domains.knowledge.agent_utils import summary_node

router = APIRouter()


@router.get(
    "/workspaces/{workspace_id}/meetings/search",
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


@router.post("/meetings/{meeting_id}/chatbot/message")
async def chatbot_message(meeting_id: str, req: ChatbotMessageRequest):
    state = {
        "meeting_id": meeting_id,
        "user_question": req.message,
        "function_type": "",
        "chat_response": ""
    }
    result = knowledge_app.invoke(state)

    repository.save_chat_log(meeting_id, req.session_id, "user", req.message, "")
    repository.save_chat_log(
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

@router.get("/meetings/{meeting_id}/chatbot/history", response_model=ChatbotHistoryResponse)
async def chatbot_history(meeting_id: str, session_id: str):
    logs = repository.get_chat_history(meeting_id, session_id)
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

@router.post("/meetings/{meeting_id}/chatbot/summary", response_model=ChatbotSummaryResponse)
async def chatbot_summary(meeting_id: str):
    state = {
        "meeting_id": meeting_id,
        "user_question": "",
        "function_type": "",
        "chat_response": ""
    }
    result = summary_node(state)
    return ChatbotSummaryResponse(
        summary=result["summary"],
        generated_at=datetime.now()
    )