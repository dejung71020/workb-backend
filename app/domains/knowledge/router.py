# app\domains\knowledge\router.py
from fastapi import APIRouter
from datetime import datetime

from app.core.graph.workflow import knowledge_app
from app.domains.knowledge.schemas import (
    ChatbotMessageRequest, ChatbotMessageResponse, 
    ChatbotSummaryResponse, ChatbotHistoryMessage, ChatbotHistoryResponse
)
from app.domains.knowledge import repository
from app.utils.redis_utils import get_meeting_context
from app.domains.knowledge.agent_utils import summary_node

router = APIRouter()

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
        result="{}",
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
        summary=result["chat_response"],
        generated_at=datetime.now()
    )